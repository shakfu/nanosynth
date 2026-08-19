"""NodeProxy and Ndef -- live coding with hot-swappable synth definitions.

A ``NodeProxy`` owns a private audio bus, a source synth, and a monitor
synth.  Hot-swapping replaces only the source synth while the monitor
stays in place, enabling seamless audio transitions.

``Ndef`` is a global named proxy registry for concise live-coding::

    from nanosynth.proxy import Ndef

    Ndef(server, "pad", lambda: SinOsc.ar(440) * 0.3)
    Ndef(server, "pad").play()
    Ndef(server, "pad", lambda: Saw.ar(220) * 0.2)  # hot-swap
    Ndef(server, "pad").clear()
"""

from __future__ import annotations

import weakref
from collections.abc import Callable
from typing import Any, ClassVar

from .enums import AddAction, DoneAction
from .exceptions import EngineError
from .server import Bus, Server, Synth
from .synthdef import SynthDef, SynthDefBuilder


class NodeProxy:
    """Hot-swappable synth node backed by a private audio bus.

    The proxy owns:
    - A private audio bus (allocated via ``server.audio_bus()``)
    - A source synth (writes to the private bus)
    - A monitor synth (reads from private bus, writes to hardware output)

    Swapping the source replaces only the source synth.  The monitor
    stays in place, so the output bus never changes.

    Args:
        server: The Server instance.
        num_channels: Number of audio channels for the private bus.
    """

    def __init__(self, server: Server, num_channels: int = 2) -> None:
        self._server = server
        self._num_channels = num_channels
        self._bus: Bus | None = None
        self._source_synth: Synth | None = None
        self._monitor_synth: Synth | None = None
        self._source_value: Callable[..., Any] | SynthDef | None = None
        self._version = 0
        self._monitor_playing = False

    def _ensure_bus(self) -> Bus:
        """Lazily allocate the private audio bus."""
        if self._bus is None:
            self._bus = self._server.audio_bus(self._num_channels)
        return self._bus

    @property
    def bus(self) -> Bus | None:
        """The private audio bus, or None if not yet allocated."""
        return self._bus

    @property
    def is_playing(self) -> bool:
        """Whether the monitor is currently active."""
        return self._monitor_playing

    @property
    def source(self) -> Callable[..., Any] | SynthDef | None:
        """The current source (callable, SynthDef, or None)."""
        return self._source_value

    @source.setter
    def source(self, value: Callable[..., Any] | SynthDef | None) -> None:
        """Set the source.

        - Callable: wrapped in SynthDefBuilder automatically with an ASR
          envelope for clean crossfade.
        - SynthDef: used directly (must write to Out.ar with a ``bus`` param).
        - None: clear the source (free synth, keep bus/monitor).
        """
        if value is None:
            self._clear_source()
            self._source_value = None
            return

        bus = self._ensure_bus()

        if callable(value) and not isinstance(value, SynthDef):
            synthdef = self._build_source_synthdef(value)
        elif isinstance(value, SynthDef):
            synthdef = value
        else:
            raise TypeError(
                f"source must be callable, SynthDef, or None, got {type(value)}"
            )

        # Send the new SynthDef
        self._server.send_synthdef(synthdef)

        # Release old source synth (triggers ASR release -> FREE_SYNTH)
        if self._source_synth is not None:
            self._server.set(self._source_synth, gate=0.0)

        # Create new source synth writing to private bus
        self._source_synth = self._server.synth(
            synthdef.effective_name,
            out=float(bus.bus_id),
        )
        self._source_value = value
        self._version += 1

    def _build_source_synthdef(self, func: Callable[..., Any]) -> SynthDef:
        """Wrap a callable in a SynthDef with ASR envelope for crossfade."""
        from .envelopes import EnvGen, Envelope
        from .ugens.inout import Out

        name = f"__proxy_{id(self)}_{self._version}__"
        bus = self._ensure_bus()
        with SynthDefBuilder(out=float(bus.bus_id), gate=1.0) as builder:
            sig = func()
            env = EnvGen.kr(
                envelope=Envelope.asr(attack_time=0.01, sustain=1.0, release_time=0.01),
                gate=builder["gate"],
                done_action=DoneAction.FREE_SYNTH,
            )
            Out.ar(bus=builder["out"], source=sig * env)  # type: ignore[attr-defined]
        return builder.build(name=name)

    def _ensure_monitor_synthdef(self) -> str:
        """Build and send the monitor SynthDef (cached on server by channel count)."""
        from .ugens.inout import In, Out

        name = f"__proxy_monitor_{self._num_channels}ch__"
        if name in self._server._synthdefs:
            return name

        with SynthDefBuilder(in_bus=0.0, out_bus=0.0) as builder:
            sig = In.ar(bus=builder["in_bus"], channel_count=self._num_channels)  # type: ignore[attr-defined]
            Out.ar(bus=builder["out_bus"], source=sig)  # type: ignore[attr-defined]
        synthdef = builder.build(name=name)
        self._server.send_synthdef(synthdef)
        return name

    def play(self, out: int = 0, num_channels: int | None = None) -> None:
        """Start monitoring (create monitor synth reading from private bus).

        Args:
            out: Hardware output bus index.
            num_channels: Override channel count (defaults to proxy's channel count).
        """
        if self._monitor_playing:
            return

        bus = self._ensure_bus()
        monitor_name = self._ensure_monitor_synthdef()
        self._monitor_synth = self._server.synth(
            monitor_name,
            action=AddAction.ADD_TO_TAIL,
            target=1,
            in_bus=float(bus.bus_id),
            out_bus=float(out),
        )
        self._monitor_playing = True

    def stop(self) -> None:
        """Stop monitoring (free monitor synth).  Source keeps running."""
        if self._monitor_synth is not None:
            self._server.free(self._monitor_synth)
            self._monitor_synth = None
        self._monitor_playing = False

    def _clear_source(self) -> None:
        """Free the source synth if running."""
        if self._source_synth is not None:
            self._server.free(self._source_synth)
            self._source_synth = None

    def clear(self) -> None:
        """Free everything: source synth, monitor synth, bus."""
        self._clear_source()
        self.stop()
        if self._bus is not None:
            self._bus.free()
            self._bus = None
        self._source_value = None

    def set(self, **params: float) -> None:
        """Set parameters on the running source synth.

        Raises:
            EngineError: If no source synth is running.
        """
        if self._source_synth is None:
            raise EngineError("No source synth is running")
        self._source_synth.set(**params)


# ---------------------------------------------------------------------------
# Ndef -- named proxy registry
# ---------------------------------------------------------------------------

_MISSING: object = object()


class Ndef:
    """Global registry of named NodeProxy instances.

    ``Ndef`` is a factory that returns (or creates) a ``NodeProxy`` for a
    given server + name pair.  If a *source* is provided, it is assigned
    to the proxy.

    Usage::

        Ndef(server, "pad", lambda: SinOsc.ar(440) * 0.3)
        Ndef(server, "pad").play()
        Ndef(server, "pad", lambda: Saw.ar(220) * 0.2)  # hot-swap
        Ndef(server, "pad").clear()

        Ndef.clear_all(server)
    """

    # Keyed on the Server object (identity), not id(server): an int key can be
    # reused after a server is garbage-collected, silently aliasing a fresh
    # server onto stale proxies. A WeakKeyDictionary keys on identity and drops
    # a server's entry automatically if the server is ever collected. Note the
    # proxies still hold a strong reference to their server, so a server with
    # registered Ndef proxies is pinned alive until ``clear_all`` -- call it to
    # release both the proxies and the server.
    _registry: ClassVar[weakref.WeakKeyDictionary[Server, dict[str, NodeProxy]]] = (
        weakref.WeakKeyDictionary()
    )

    def __new__(  # type: ignore[misc]
        cls,
        server: Server,
        name: str,
        source: Callable[..., Any] | SynthDef | None = _MISSING,  # type: ignore[assignment]
    ) -> NodeProxy:
        proxies = cls._registry.get(server)
        if proxies is None:
            proxies = {}
            cls._registry[server] = proxies
        proxy = proxies.get(name)
        if proxy is None:
            proxy = NodeProxy(server)
            proxies[name] = proxy
        if source is not _MISSING:
            proxy.source = source
        return proxy

    @classmethod
    def clear_all(cls, server: Server) -> None:
        """Clear all proxies associated with *server*."""
        proxies = cls._registry.pop(server, None)
        if proxies:
            for proxy in proxies.values():
                proxy.clear()
