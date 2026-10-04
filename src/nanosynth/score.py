"""Non-real-time (NRT) score rendering for offline audio synthesis."""

from __future__ import annotations

import contextlib
import itertools
import struct
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, SupportsFloat

from .enums import AddAction
from .osc import OscBundle, OscMessage
from .scsynth import Options, find_ugen_plugins_path
from ._controls import Controls, control_args

if TYPE_CHECKING:
    from .patterns import Event
    from .synthdef import SynthDef

# Delay of the terminal guard bundle after the last event. One 64-sample block
# lasts <= 10 ms at any rate >= 6.4 kHz, so the final event renders at least one
# block before /g_freeAll frees it.
_GUARD_EPSILON = 0.01


class Score:
    """A sequence of timestamped OSC bundles for offline (NRT) rendering.

    Build a score by adding OSC messages at specific timestamps, then call
    ``render()`` to produce an audio file without real-time audio hardware.

    Example::

        from nanosynth import Score, SynthDefBuilder, SinOsc, Out

        with SynthDefBuilder(freq=440.0) as b:
            Out.ar(bus=0, source=SinOsc.ar(frequency=b["freq"]) * 0.3)
        sd = b.build(name="sine")

        score = Score()
        score.add_synthdef(0.0, sd)
        node = score.add_synth(0.0, "sine", node_id=None, freq=440.0)
        score.add(1.0, OscMessage("/n_free", node))
        score.render("output.wav", sample_rate=44100)
    """

    def __init__(self) -> None:
        self._entries: list[tuple[float, list[OscMessage]]] = []
        self._node_ids = itertools.count(1000)
        # IDs passed explicitly to add_synth(), which allocation must skip.
        self._explicit_ids: set[int] = set()

    @classmethod
    def from_pattern(
        cls,
        pattern: Iterable[Event],
        duration: float,
        *,
        bpm: float = 120.0,
        synthdefs: Iterable[SynthDef] = (),
    ) -> Score:
        """Schedule an event pattern into a new score.

        Uses the same event-to-command logic as realtime :class:`Player`
        playback (chords, gate release after ``sustain``, Pmono). Events
        starting at or after *duration* are dropped; held Pmono synths are
        released at the end of the stream or at *duration*, whichever is
        earlier.

        Args:
            pattern: Event pattern, e.g. a ``Pbind``. May be infinite.
            duration: Cut-off for event onsets, in seconds.
            bpm: Tempo used to convert beats to seconds.
            synthdefs: SynthDefs to load at time 0, ahead of every event.
        """
        from .patterns import Rest, _event_delta, _send_event

        score = cls()
        for synthdef in synthdefs:
            score.add_synthdef(0.0, synthdef)
        target = _ScoreTarget(score)
        mono_synths: dict[str, Any] = {}
        beat_dur = 60.0 / bpm
        now = 0.0
        for event in pattern:
            if now >= duration:
                break
            if not isinstance(event.get("dur"), Rest):
                _send_event(target, event, now, beat_dur, mono_synths)
            now += _event_delta(event) * beat_dur
        for node_id in mono_synths.values():
            score.add_set(min(now, duration), node_id, gate=0.0)
        return score

    def add(self, time: float, messages: list[OscMessage] | OscMessage) -> None:
        """Add OSC message(s) at the given time (seconds)."""
        if isinstance(messages, OscMessage):
            messages = [messages]
        self._entries.append((time, list(messages)))

    def add_synthdef(self, time: float, synthdef: SynthDef) -> None:
        """Add a /d_recv command for a SynthDef at the given time."""
        compiled = synthdef.compile()
        self._entries.append((time, [OscMessage("/d_recv", compiled)]))

    def next_node_id(self) -> int:
        """Return a node ID not yet used in this score (counting from 1000)."""
        while (node_id := next(self._node_ids)) in self._explicit_ids:
            pass
        return node_id

    def add_synth(
        self,
        time: float,
        name: str,
        node_id: int | None = -1,
        add_action: AddAction | int = AddAction.ADD_TO_HEAD,
        target: int = 0,
        *,
        controls: Controls = None,
        **params: float,
    ) -> int:
        """Add a /s_new command at the given time. Returns the node ID.

        Args:
            time: Onset in seconds.
            name: SynthDef name.
            node_id: Explicit node ID; ``-1`` (default) for an engine-assigned
                one that cannot be addressed later; ``None`` to allocate an
                addressable one from this score.
            add_action: Add action (AddAction enum or int 0-4).
            target: Target node for placement (NRT has only root group 0).
            controls: Values for any control name, including ones that
                collide with this method's parameters (``time``, ``target``,
                ...).
            **params: Initial synth parameter values.
        """
        args = control_args(controls, params)
        if node_id is None:
            node_id = self.next_node_id()
        elif node_id >= 0:
            self._explicit_ids.add(node_id)
        message = OscMessage(
            "/s_new", name, node_id, int(add_action), int(target), *args
        )
        self._entries.append((time, [message]))
        return node_id

    def add_set(
        self,
        time: float,
        node_id: int,
        *,
        controls: Controls = None,
        **params: float,
    ) -> None:
        """Add a /n_set command at the given time.

        *controls* takes any control name, including ``time`` and ``node_id``.
        """
        args = control_args(controls, params)
        self._entries.append((time, [OscMessage("/n_set", int(node_id), *args)]))

    def sort(self) -> None:
        """Sort entries by time (in-place, stable)."""
        self._entries.sort(key=lambda e: e[0])

    def duration(self) -> float:
        """Return the timestamp of the last entry, or 0.0 if empty."""
        if not self._entries:
            return 0.0
        return max(t for t, _ in self._entries)

    def to_binary(self) -> bytes:
        """Serialize to SC's binary command file format.

        Format: repeated ``[int32 packet_size][OSC bundle datagram]``.
        The bundle timestamp is the raw time in seconds (no NTP epoch).

        A non-empty score ends with a guard bundle (``/g_freeAll 0`` then
        ``/c_set 0 0``) shortly after the last event. Freeing all nodes before
        engine shutdown prevents crashes from delay UGens whose buffers are
        released during World cleanup while synths still reference them.
        """
        if not self._entries:
            return b""
        result = bytearray()
        # scsynth consumes the NRT command stream sequentially; logical time
        # only moves forward, so entries MUST be emitted in timestamp order or a
        # late-added earlier event is processed at the wrong (later) time. Sort
        # stably so equal-timestamp entries keep insertion order (e.g. a /d_recv
        # stays ahead of the /s_new that uses it).
        entries = sorted(self._entries, key=lambda e: e[0])
        guard = [OscMessage("/g_freeAll", 0), OscMessage("/c_set", 0, 0)]
        entries.append((entries[-1][0] + _GUARD_EPSILON, guard))
        for time, messages in entries:
            bundle = OscBundle(timestamp=time, contents=messages)
            datagram = bundle.to_datagram(realtime=False)
            result.extend(struct.pack(">i", len(datagram)))
            result.extend(datagram)
        return bytes(result)

    def render(
        self,
        output_path: str | Path,
        *,
        sample_rate: int = 44100,
        header_format: str = "WAV",
        sample_format: str = "int16",
        input_path: str | Path | None = None,
        output_channels: int = 2,
        input_channels: int = 0,
        options: Options | None = None,
    ) -> None:
        """Render this score to an audio file (non-real-time).

        Writes ``to_binary()`` to a temp file, then invokes the embedded
        scsynth NRT renderer.

        Args:
            output_path: Path for the output audio file.
            sample_rate: Output sample rate in Hz.
            header_format: Audio file format ("WAV" or "AIFF").
            sample_format: Sample encoding ("int16", "int24", "float").
            input_path: Optional input audio file for NRT processing.
            output_channels: Number of output channels.
            input_channels: Number of input channels.
            options: Optional Options for engine configuration overrides.
        """
        from . import _scsynth

        binary_data = self.to_binary()

        # Resolve options
        opts = options or Options()
        plugins_path = opts.ugen_plugins_path
        if plugins_path is None:
            found = find_ugen_plugins_path()
            if found is not None:
                plugins_path = str(found)

        # Write to a temp file and close it before calling the C++ renderer.
        # On Windows, NamedTemporaryFile with delete=True holds an exclusive
        # lock that prevents the engine from opening the file.
        cmd_fd, cmd_path = tempfile.mkstemp(suffix=".osc")
        try:
            with open(cmd_fd, "wb") as cmd_file:
                cmd_file.write(binary_data)

            kwargs: dict[str, Any] = {}
            if opts.hardware_buffer_size is not None:
                kwargs["preferred_hardware_buffer_size"] = opts.hardware_buffer_size
            _scsynth.world_nrt_render(
                cmd_filename=cmd_path,
                output_filename=str(output_path),
                sample_rate=sample_rate,
                input_filename=str(input_path) if input_path else None,
                header_format=header_format,
                sample_format=sample_format,
                num_output_bus_channels=output_channels,
                num_input_bus_channels=input_channels,
                block_size=opts.block_size,
                num_buffers=opts.buffer_count,
                max_nodes=opts.maximum_node_count,
                max_graph_defs=opts.maximum_synthdef_count,
                realtime_memory_size=opts.memory_size,
                verbosity=opts.verbosity,
                ugen_plugins_path=plugins_path,
                num_audio_bus_channels=opts.audio_bus_channel_count,
                num_control_bus_channels=opts.control_bus_channel_count,
                max_wire_bufs=opts.wire_buffer_count,
                num_rgens=opts.random_number_generator_count,
                **kwargs,
            )
        finally:
            Path(cmd_path).unlink(missing_ok=True)


class _ScoreTarget:
    """Adapts a Score to the ``at``/``synth``/``set`` calls of ``_send_event``."""

    def __init__(self, score: Score) -> None:
        self._score = score
        self._time = 0.0

    @contextlib.contextmanager
    def at(self, time: float) -> Iterator[None]:
        self._time = time
        yield

    def synth(
        self,
        name: str,
        /,
        *,
        controls: Mapping[str, SupportsFloat] | None = None,
        **params: float,
    ) -> int:
        # node_id=None: pattern releases need an addressable node.
        return self._score.add_synth(
            self._time, name, None, controls={**(controls or {}), **params}
        )

    def set(
        self,
        node_id: int,
        /,
        *,
        controls: Mapping[str, SupportsFloat] | None = None,
        **params: float,
    ) -> None:
        self._score.add_set(
            self._time, node_id, controls={**(controls or {}), **params}
        )
