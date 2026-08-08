"""High-level Server class wrapping the embedded scsynth engine."""

from __future__ import annotations

import contextlib
import itertools
import logging
import struct
import threading
from collections.abc import Callable, Iterator
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, SupportsInt, Union

from .enums import AddAction
from .exceptions import EngineError, OscError
from .osc import OscBundle, OscMessage
from .scsynth import BootStatus, EmbeddedProcessProtocol, Options

if TYPE_CHECKING:
    from .osc import OscArgument
    from .supernova import EmbeddedSupernovaProtocol
    from .synthdef import SynthDef

    ServerProtocol = Union[EmbeddedProcessProtocol, EmbeddedSupernovaProtocol]
else:
    ServerProtocol = EmbeddedProcessProtocol

logger = logging.getLogger(__name__)


def _osc_int(value: Any) -> int:
    """Coerce a decoded OSC argument to int (values are concrete at runtime)."""
    return int(value)


def _osc_float(value: Any) -> float:
    """Coerce a decoded OSC argument to float."""
    return float(value)


def _require_numpy() -> Any:
    """Import numpy, raising a clear error if it is not installed."""
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - exercised without numpy
        raise ImportError(
            "numpy is required for direct buffer data exchange; install it "
            "with `pip install numpy` or `pip install nanosynth[numpy]`."
        ) from exc
    return numpy


# ---------------------------------------------------------------------------
# ID allocators
# ---------------------------------------------------------------------------


class _NodeIdAllocator:
    """Monotonic node-id allocator that wraps within scsynth's id space.

    Node ids are deliberately *not* reclaimed on free: a synth created with a
    self-freeing ``DoneAction`` frees itself server-side without notifying the
    client, so a free-list would either leak those ids or risk handing out an
    id while its node is still alive. Instead ids cycle through a large range,
    keeping the value bounded (no unbounded Python-int growth) while making
    collision with a still-living node astronomically unlikely.
    """

    def __init__(self, initial: int = 1000, maximum: int = 0x07FFFFFF) -> None:
        self._initial = initial
        self._maximum = maximum
        self._next = initial
        self._lock = threading.Lock()

    def allocate(self) -> int:
        with self._lock:
            node_id = self._next
            nxt = node_id + 1
            self._next = self._initial if nxt > self._maximum else nxt
            return node_id

    def reset(self) -> None:
        with self._lock:
            self._next = self._initial


class _BlockAllocator:
    """Free-list allocator over ``[start, start + size)`` for buffers and buses.

    Hands out the lowest available contiguous block, reclaims freed blocks for
    reuse (coalescing adjacent free ranges), and raises ``EngineError`` when
    the range is exhausted. ``allocated`` exposes the set of live base ids for
    inspection. Thread-safe.
    """

    def __init__(self, size: int, start: int = 0, *, name: str = "id") -> None:
        self._start = start
        self._stop = start + size
        self._name = name
        # Free intervals as [lo, hi) pairs, kept sorted and coalesced.
        self._free: list[list[int]] = [[start, self._stop]] if size > 0 else []
        self._sizes: dict[int, int] = {}  # base -> channel count
        self.allocated: set[int] = set()
        self._lock = threading.Lock()

    def allocate(self, count: int = 1) -> int:
        if count < 1:
            raise ValueError("count must be >= 1")
        with self._lock:
            for interval in self._free:
                lo, hi = interval
                if hi - lo >= count:
                    base = lo
                    if hi - lo == count:
                        self._free.remove(interval)
                    else:
                        interval[0] = lo + count
                    self._sizes[base] = count
                    self.allocated.add(base)
                    return base
            raise EngineError(
                f"{self._name} allocator exhausted "
                f"(range {self._start}..{self._stop}, requested {count})"
            )

    def reserve(self, base: int, count: int = 1) -> None:
        """Carve a specific block out of the free list (for explicit ids)."""
        with self._lock:
            if base in self._sizes:
                return
            hi = base + count
            new_free: list[list[int]] = []
            for lo_i, hi_i in self._free:
                if hi_i <= base or lo_i >= hi:
                    new_free.append([lo_i, hi_i])
                    continue
                if lo_i < base:
                    new_free.append([lo_i, base])
                if hi_i > hi:
                    new_free.append([hi, hi_i])
            self._free = new_free
            self._sizes[base] = count
            self.allocated.add(base)

    def free(self, base: int) -> None:
        with self._lock:
            count = self._sizes.pop(base, None)
            self.allocated.discard(base)
            if count is None:
                return
            self._insert_free(base, base + count)

    def _insert_free(self, lo: int, hi: int) -> None:
        free = self._free
        i = 0
        while i < len(free) and free[i][0] < lo:
            i += 1
        free.insert(i, [lo, hi])
        merged: list[list[int]] = []
        for interval in free:
            if merged and interval[0] <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], interval[1])
            else:
                merged.append(interval)
        self._free = merged


# ---------------------------------------------------------------------------
# Node proxy objects
# ---------------------------------------------------------------------------


class Synth:
    """Lightweight proxy for a synth node on the server.

    Wraps a node ID with convenience methods and int-compatibility.
    Returned by ``Server.synth()`` and ``Server.managed_synth()``.

    Supports ``int()`` conversion, equality with plain ints, and use as
    a context manager (frees the node on exit)::

        node = server.synth("sine", frequency=440.0)
        node.set(frequency=880.0)
        node.free()

        with server.synth("sine") as node:
            ...  # freed on exit
    """

    __slots__ = ("_server", "_node_id", "_name")

    def __init__(self, server: Server, node_id: int, name: str) -> None:
        self._server = server
        self._node_id = node_id
        self._name = name

    def __repr__(self) -> str:
        return f"<Synth {self._node_id} ({self._name})>"

    def __int__(self) -> int:
        return self._node_id

    def __index__(self) -> int:
        return self._node_id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Synth):
            return self._node_id == other._node_id
        if isinstance(other, int):
            return self._node_id == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._node_id)

    def __enter__(self) -> Synth:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        if self._server.is_running:
            self.free()

    @property
    def node_id(self) -> int:
        return self._node_id

    @property
    def name(self) -> str:
        return self._name

    def set(self, **params: float) -> None:
        """Set parameter values on this synth."""
        self._server.set(self._node_id, **params)

    def free(self) -> None:
        """Free this synth node."""
        self._server.free(self._node_id)

    def wait_free(self, timeout: float = 5.0) -> bool:
        """Block until this node is freed (e.g. by a self-freeing envelope).

        Returns ``True`` if it ended, ``False`` on timeout. See
        :meth:`Server.wait_for_node_free`.
        """
        return self._server.wait_for_node_free(self._node_id, timeout=timeout)

    def on_free(self, callback: Callable[[NodeEvent], None]) -> None:
        """Call *callback* once, when this node is freed.

        The handler unregisters itself after firing. Enables notifications.
        """
        server = self._server
        node_id = self._node_id

        def handler(event: NodeEvent) -> None:
            if event.action == "end" and event.node_id == node_id:
                server.remove_node_handler(handler)
                callback(event)

        server.on_node(handler)


class Group:
    """Lightweight proxy for a group node on the server.

    Same shape as ``Synth`` but without a name field. Returned by
    ``Server.group()`` and ``Server.managed_group()``.
    """

    __slots__ = ("_server", "_node_id")

    def __init__(self, server: Server, node_id: int) -> None:
        self._server = server
        self._node_id = node_id

    def __repr__(self) -> str:
        return f"<Group {self._node_id}>"

    def __int__(self) -> int:
        return self._node_id

    def __index__(self) -> int:
        return self._node_id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Group):
            return self._node_id == other._node_id
        if isinstance(other, int):
            return self._node_id == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._node_id)

    def __enter__(self) -> Group:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        if self._server.is_running:
            self.free()

    @property
    def node_id(self) -> int:
        return self._node_id

    def free(self) -> None:
        """Free this group node."""
        self._server.free(self._node_id)


class ParGroup(Group):
    """Lightweight proxy for a parallel group node on the server.

    A ParGroup evaluates its child nodes in parallel across CPU cores.
    Same interface as ``Group`` but created with ``/p_new`` instead of
    ``/g_new``.
    """

    def __repr__(self) -> str:
        return f"<ParGroup {self._node_id}>"


class Bus:
    """Lightweight proxy for an allocated bus on the server.

    Wraps a bus ID with convenience methods and int-compatibility.
    Returned by ``Server.audio_bus()`` and ``Server.control_bus()``.

    Supports ``int()`` conversion and use as a context manager
    (frees the bus on exit)::

        bus = server.audio_bus(2)
        # use int(bus) or bus.bus_id as a synth param
        node = server.synth("fx", in_bus=float(int(bus)))
        bus.free()
    """

    __slots__ = ("_server", "_bus_id", "_num_channels", "_rate")

    def __init__(
        self, server: Server, bus_id: int, num_channels: int, rate: str
    ) -> None:
        self._server = server
        self._bus_id = bus_id
        self._num_channels = num_channels
        self._rate = rate

    def __repr__(self) -> str:
        return f"<Bus {self._bus_id} ({self._rate}, {self._num_channels}ch)>"

    def __int__(self) -> int:
        return self._bus_id

    def __index__(self) -> int:
        return self._bus_id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Bus):
            return self._bus_id == other._bus_id and self._rate == other._rate
        if isinstance(other, int):
            return self._bus_id == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._bus_id, self._rate))

    @property
    def bus_id(self) -> int:
        """The server-side bus index."""
        return self._bus_id

    @property
    def num_channels(self) -> int:
        """Number of contiguous channels this bus spans."""
        return self._num_channels

    @property
    def rate(self) -> str:
        """Bus rate: ``"audio"`` or ``"control"``."""
        return self._rate

    def set(self, *values: float) -> None:
        """Set control bus value(s). Only valid for control-rate buses.

        Args:
            *values: One value per channel.

        Raises:
            RuntimeError: If called on an audio-rate bus.
        """
        if self._rate != "control":
            raise EngineError("set() is only valid for control-rate buses")
        if len(values) == 1:
            self._server.send_msg("/c_set", self._bus_id, values[0])
        else:
            args: list[OscArgument] = []
            for i, v in enumerate(values):
                args.append(self._bus_id + i)
                args.append(float(v))
            self._server.send_msg("/c_set", *args)

    def free(self) -> None:
        """Return this bus to the allocator pool."""
        self._server.free_bus(self)


@dataclass
class _RecordingState:
    """Tracks active recording state."""

    path: str
    buffer_id: int
    synth_node_id: int


@dataclass(frozen=True)
class ServerStatus:
    """Snapshot of the engine's state, from ``/status.reply``."""

    num_ugens: int
    num_synths: int
    num_groups: int
    num_synthdefs: int
    average_cpu: float
    peak_cpu: float
    nominal_sample_rate: float
    actual_sample_rate: float


@dataclass(frozen=True)
class ServerVersion:
    """Engine version information, from ``/version.reply``."""

    program: str
    major: int
    minor: int
    patch: str
    branch: str
    commit: str


@dataclass
class NodeInfo:
    """A node in the server's node tree, from ``/g_queryTree.reply``.

    Groups have ``is_group=True`` and populated ``children``; synths have
    ``is_group=False``, a ``synthdef`` name, and (if queried with controls) a
    ``controls`` mapping of name -> value (a float, or a bus-mapping string
    like ``"c1"``/``"a0"``).
    """

    node_id: int
    is_group: bool
    synthdef: str | None = None
    controls: dict[str, float | str] = field(default_factory=dict)
    children: list[NodeInfo] = field(default_factory=list)


# Engine node-notification addresses -> short action names.
_NODE_EVENT_ACTIONS = {
    "/n_go": "go",
    "/n_end": "end",
    "/n_off": "off",
    "/n_on": "on",
    "/n_move": "move",
}


@dataclass(frozen=True)
class NodeEvent:
    """A node lifecycle notification from the engine.

    ``action`` is one of ``"go"`` (created), ``"end"`` (freed), ``"off"``
    (paused), ``"on"`` (resumed), or ``"move"``. Delivered only while
    notifications are enabled (see :meth:`Server.enable_notifications`).
    """

    action: str
    node_id: int
    parent_group_id: int
    prev_node_id: int
    next_node_id: int
    is_group: bool
    head_node_id: int | None = None
    tail_node_id: int | None = None


def _parse_node_event(msg: OscMessage) -> NodeEvent:
    c = msg.contents
    is_group = bool(_osc_int(c[4]))
    head = _osc_int(c[5]) if is_group and len(c) > 5 else None
    tail = _osc_int(c[6]) if is_group and len(c) > 6 else None
    return NodeEvent(
        action=_NODE_EVENT_ACTIONS[str(msg.address)],
        node_id=_osc_int(c[0]),
        parent_group_id=_osc_int(c[1]),
        prev_node_id=_osc_int(c[2]),
        next_node_id=_osc_int(c[3]),
        is_group=is_group,
        head_node_id=head,
        tail_node_id=tail,
    )


class _ReplyEvent:
    """One-shot waiter for a single OSC reply, with an optional matcher.

    ``match`` lets a waiter accept only a reply satisfying a predicate (e.g. a
    ``/done`` whose first argument is the originating command), so unrelated
    replies at the same address do not resolve it.
    """

    __slots__ = ("_event", "message", "_match")

    def __init__(self, match: Callable[[OscMessage], bool] | None = None) -> None:
        self._event = threading.Event()
        self.message: OscMessage | None = None
        self._match = match

    def matches(self, msg: OscMessage) -> bool:
        if self._match is None:
            return True
        try:
            return self._match(msg)
        except Exception:  # noqa: BLE001 -- a bad matcher must not wedge dispatch
            return False

    def set(self, msg: OscMessage) -> None:
        self.message = msg
        self._event.set()

    def wait(self, timeout: float | None = None) -> OscMessage | None:
        self._event.wait(timeout=timeout)
        return self.message


class Server:
    """High-level wrapper around the embedded scsynth engine.

    Manages the full boot-send-quit lifecycle, node ID allocation,
    SynthDef dispatch, and common OSC commands.

    Can be used as a context manager::

        with Server() as s:
            s.send_synthdef(my_synthdef)
            node = s.synth("my_synth", frequency=880.0)
            ...
    """

    def __init__(
        self,
        options: Options | None = None,
        *,
        protocol: ServerProtocol | None = None,
    ) -> None:
        self._options = options or Options()
        self._protocol: ServerProtocol = protocol or EmbeddedProcessProtocol()
        self._node_allocator = _NodeIdAllocator()
        self._buffer_allocator = _BlockAllocator(
            self._options.buffer_count, name="buffer"
        )
        self._audio_bus_allocator = _BlockAllocator(
            self._options.private_audio_bus_channel_count,
            start=self._options.first_private_bus_id,
            name="audio bus",
        )
        self._control_bus_allocator = _BlockAllocator(
            self._options.control_bus_channel_count, name="control bus"
        )
        # Live base-id sets, owned by the allocators and exposed for inspection.
        self._allocated_buffers = self._buffer_allocator.allocated
        self._allocated_audio_buses = self._audio_bus_allocator.allocated
        self._allocated_control_buses = self._control_bus_allocator.allocated
        self._sync_id_counter = itertools.count(1)
        self._synthdefs: set[str] = set()
        self._reply_handlers: dict[str, list[Callable[..., Any]]] = {}
        self._pending_replies: dict[str, list[_ReplyEvent]] = {}
        self._reply_lock = threading.Lock()
        self._recording: _RecordingState | None = None
        self._recorder_synthdefs: dict[int, str] = {}  # channel_count -> name
        self._node_handlers: list[Callable[[NodeEvent], None]] = []
        self._notifications_enabled = False
        self._node_dispatch_installed = False
        # Per-thread stack of open ``at()`` capture buffers. Thread-local so a
        # bundle opened on one thread never swallows another thread's messages.
        self._bundle_local = threading.local()

    def __enter__(self) -> Server:
        self.boot()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        self.quit()

    def __repr__(self) -> str:
        status = "running" if self.is_running else "stopped"
        return f"<Server ({status})>"

    # -- Lifecycle -------------------------------------------------------------

    def boot(self) -> None:
        """Boot the embedded scsynth engine and create the default group."""
        self._protocol.set_reply_callback(self._dispatch_reply)
        # A fresh World has no /notify registration; re-enable lazily on next use.
        self._notifications_enabled = False
        self._protocol.boot(self._options)
        # Create the default group (group 1, add to head of root node 0)
        self.send_msg("/g_new", 1, 0, 0)

    def quit(self) -> None:
        """Shut down the embedded engine."""
        if not self.is_running:
            return
        # Send /quit OSC for scsynth (triggers internal shutdown).
        # Supernova handles shutdown via terminate() in its quit() method,
        # so sending /quit would cause a double-shutdown crash.
        from .supernova import EmbeddedSupernovaProtocol

        if not isinstance(self._protocol, EmbeddedSupernovaProtocol):
            self.send_msg("/quit")
        self._protocol.quit()

    @property
    def is_running(self) -> bool:
        """Whether the engine is currently online."""
        return self._protocol.status == BootStatus.ONLINE

    @property
    def options(self) -> Options:
        """The server's ``Options`` configuration."""
        return self._options

    # -- Node ID allocation ----------------------------------------------------

    def next_node_id(self) -> int:
        """Return a unique node ID (cycling from 1000 within scsynth's range)."""
        return self._node_allocator.allocate()

    # -- OSC -------------------------------------------------------------------

    def _bundle_stack(self) -> list[list[OscBundle | OscMessage]]:
        """This thread's stack of open ``at()`` capture buffers."""
        stack: list[list[OscBundle | OscMessage]] | None = getattr(
            self._bundle_local, "stack", None
        )
        if stack is None:
            stack = []
            self._bundle_local.stack = stack
        return stack

    def _dispatch(self, packet: OscBundle | OscMessage) -> None:
        """Send *packet*, or capture it if an ``at()`` block is open."""
        stack = self._bundle_stack()
        if stack:
            stack[-1].append(packet)
            return
        self._protocol.send_packet(packet.to_datagram())

    def send_msg(self, address: str, *args: OscArgument) -> None:
        """Send an OSC message to the engine.

        Inside a :meth:`at` block the message is captured into that bundle
        instead of being sent immediately.
        """
        self._dispatch(OscMessage(address, *args))

    def send_bundle(
        self,
        contents: SequenceABC[OscBundle | OscMessage],
        timestamp: float | None = None,
    ) -> None:
        """Send *contents* as a single atomic OSC bundle.

        Args:
            contents: ``OscMessage`` and/or ``OscBundle`` instances.
            timestamp: Unix epoch seconds (the ``time.time()`` domain) at which
                the engine should execute the contents, or ``None`` for
                "immediately". A timestamp in the past executes on arrival.

        Bundling is what makes timing sample-accurate: the engine applies every
        message in the bundle on the same control block, at the requested time,
        independent of when Python got round to sending it.
        """
        self._dispatch(OscBundle(timestamp=timestamp, contents=tuple(contents)))

    @contextlib.contextmanager
    def at(self, timestamp: float | None = None) -> Iterator[None]:
        """Capture messages sent in this block into one timestamped bundle.

        Every ``Server`` method that sends OSC (``synth``, ``set``, ``free``,
        ``group``, ...) routes through :meth:`send_msg`, so it can be used
        unchanged inside the block::

            with server.at(time.time() + 0.2):
                synth = server.synth("default", freq=440)

        Node IDs are still allocated eagerly, so the returned proxies are
        usable immediately. The bundle is sent when the block exits; if the
        block raises, nothing is sent. Blocks may nest, producing nested OSC
        bundles. An empty block sends nothing.

        Args:
            timestamp: Unix epoch seconds, or ``None`` for "immediately".
        """
        stack = self._bundle_stack()
        captured: list[OscBundle | OscMessage] = []
        stack.append(captured)
        try:
            yield
        finally:
            stack.pop()
        if not captured:
            return
        self._dispatch(OscBundle(timestamp=timestamp, contents=tuple(captured)))

    # -- Reply handling --------------------------------------------------------

    def _dispatch_reply(self, data: bytes) -> None:
        """Route an incoming OSC reply to registered handlers and waiters."""
        try:
            msg = OscMessage.from_datagram(data)
        except (ValueError, IndexError, struct.error, OscError, RuntimeError):
            logger.debug("Failed to decode OSC reply (%d bytes)", len(data))
            return
        address = str(msg.address)
        with self._reply_lock:
            handlers = list(self._reply_handlers.get(address, []))
            waiters = self._pending_replies.get(address, [])
            matched = [w for w in waiters if w.matches(msg)]
            remaining = [w for w in waiters if w not in matched]
            if remaining:
                self._pending_replies[address] = remaining
            else:
                self._pending_replies.pop(address, None)
        for handler in handlers:
            try:
                handler(msg)
            except Exception:  # noqa: BLE001  -- isolate user callbacks
                logger.exception("Reply handler error for %s", address)
        for waiter in matched:
            waiter.set(msg)

    def on(self, address: str, callback: Callable[..., Any]) -> None:
        """Register a persistent handler for replies at *address*."""
        with self._reply_lock:
            self._reply_handlers.setdefault(address, []).append(callback)

    def off(self, address: str, callback: Callable[..., Any]) -> None:
        """Remove a previously registered handler."""
        with self._reply_lock:
            handlers = self._reply_handlers.get(address, [])
            try:
                handlers.remove(callback)
            except ValueError:
                pass
            if not handlers:
                self._reply_handlers.pop(address, None)

    def _register_waiter(self, address: str, event: _ReplyEvent) -> None:
        with self._reply_lock:
            self._pending_replies.setdefault(address, []).append(event)

    def _unregister_waiter(self, address: str, event: _ReplyEvent) -> None:
        with self._reply_lock:
            waiters = self._pending_replies.get(address)
            if waiters and event in waiters:
                waiters.remove(event)
                if not waiters:
                    self._pending_replies.pop(address, None)

    def wait_for_reply(
        self,
        address: str,
        timeout: float = 5.0,
        match: Callable[[OscMessage], bool] | None = None,
    ) -> OscMessage | None:
        """Block until a matching reply arrives at *address*, or timeout.

        Returns the decoded OscMessage, or None on timeout. On timeout the
        waiter is removed so it cannot be spuriously resolved by a later reply.
        """
        event = _ReplyEvent(match)
        self._register_waiter(address, event)
        result = event.wait(timeout=timeout)
        if result is None:
            self._unregister_waiter(address, event)
        return result

    def send_msg_sync(
        self,
        address: str,
        *args: OscArgument,
        reply_address: str,
        timeout: float = 5.0,
        match: Callable[[OscMessage], bool] | None = None,
    ) -> OscMessage | None:
        """Send a message and wait for a matching reply at *reply_address*.

        Returns the decoded reply OscMessage, or None on timeout.
        """
        event = _ReplyEvent(match)
        self._register_waiter(reply_address, event)
        self.send_msg(address, *args)
        result = event.wait(timeout=timeout)
        if result is None:
            self._unregister_waiter(reply_address, event)
        return result

    def sync(self, timeout: float = 5.0) -> bool:
        """Block until the engine has processed all prior async commands.

        Sends ``/sync`` with a unique id and waits for the matching
        ``/synced`` reply -- the canonical scsynth round-trip barrier. Returns
        ``True`` once synced, or ``False`` on timeout (e.g. a mock server with
        no reply path). Concurrent ``sync()`` calls are matched by id.
        """
        sync_id = next(self._sync_id_counter)
        reply = self.send_msg_sync(
            "/sync",
            sync_id,
            reply_address="/synced",
            timeout=timeout,
            match=lambda m: bool(m.contents) and m.contents[0] == sync_id,
        )
        return reply is not None

    # -- Introspection & control -----------------------------------------------

    def status(self, timeout: float = 5.0) -> ServerStatus:
        """Query engine status via ``/status``.

        Returns a :class:`ServerStatus` (CPU load, sample rate, and node /
        synth / group / synthdef / ugen counts). Raises ``EngineError`` if no
        ``/status.reply`` arrives within *timeout*.
        """
        reply = self.send_msg_sync(
            "/status", reply_address="/status.reply", timeout=timeout
        )
        if reply is None:
            raise EngineError("no /status.reply received (is the engine running?)")
        c = reply.contents
        # /status.reply: [unused, #ugens, #synths, #groups, #synthdefs,
        #                 avgCPU, peakCPU, nominalSR, actualSR]
        return ServerStatus(
            num_ugens=_osc_int(c[1]),
            num_synths=_osc_int(c[2]),
            num_groups=_osc_int(c[3]),
            num_synthdefs=_osc_int(c[4]),
            average_cpu=_osc_float(c[5]),
            peak_cpu=_osc_float(c[6]),
            nominal_sample_rate=_osc_float(c[7]),
            actual_sample_rate=_osc_float(c[8]),
        )

    def version(self, timeout: float = 5.0) -> ServerVersion:
        """Query engine version via ``/version``.

        Raises ``EngineError`` if no ``/version.reply`` arrives within *timeout*.
        """
        reply = self.send_msg_sync(
            "/version", reply_address="/version.reply", timeout=timeout
        )
        if reply is None:
            raise EngineError("no /version.reply received (is the engine running?)")
        c = reply.contents
        return ServerVersion(
            program=str(c[0]),
            major=_osc_int(c[1]),
            minor=_osc_int(c[2]),
            patch=str(c[3]),
            branch=str(c[4]),
            commit=str(c[5]),
        )

    def query_tree(
        self,
        group: SupportsInt = 0,
        *,
        controls: bool = False,
        timeout: float = 5.0,
    ) -> NodeInfo:
        """Query the node tree under *group* via ``/g_queryTree``.

        Returns the queried group as a :class:`NodeInfo` with nested
        ``children``. With ``controls=True`` each synth's current control
        values are included. Raises ``EngineError`` on timeout.
        """
        group_id = int(group)
        reply = self.send_msg_sync(
            "/g_queryTree",
            group_id,
            1 if controls else 0,
            reply_address="/g_queryTree.reply",
            timeout=timeout,
            match=lambda m: len(m.contents) >= 2 and m.contents[1] == group_id,
        )
        if reply is None:
            raise EngineError("no /g_queryTree.reply received")
        c = list(reply.contents)
        with_controls = bool(c[0])
        # c[1] = queried group id, c[2] = its child count, then a depth-first
        # flat stream of nodes.
        root = NodeInfo(node_id=_osc_int(c[1]), is_group=True)
        idx = 3
        for _ in range(_osc_int(c[2])):
            child, idx = self._parse_tree_node(c, idx, with_controls)
            root.children.append(child)
        return root

    def _parse_tree_node(
        self, c: list[Any], idx: int, with_controls: bool
    ) -> tuple[NodeInfo, int]:
        node_id = _osc_int(c[idx])
        child_count = _osc_int(c[idx + 1])
        idx += 2
        if child_count == -1:
            # Synth: synthdef name, then optional control name/value pairs.
            synthdef = str(c[idx])
            idx += 1
            controls: dict[str, float | str] = {}
            if with_controls:
                num_controls = _osc_int(c[idx])
                idx += 1
                for _ in range(num_controls):
                    name, value = c[idx], c[idx + 1]
                    controls[str(name)] = value
                    idx += 2
            return NodeInfo(node_id, False, synthdef=synthdef, controls=controls), idx
        node = NodeInfo(node_id, True)
        for _ in range(child_count):
            child, idx = self._parse_tree_node(c, idx, with_controls)
            node.children.append(child)
        return node, idx

    def dump_tree(self, group: SupportsInt = 0, *, controls: bool = False) -> None:
        """Print the node tree under *group* to the engine's console/log.

        Sends ``/g_dumpTree`` (no reply); output appears in the scsynth log.
        For programmatic access use :meth:`query_tree`.
        """
        self.send_msg("/g_dumpTree", int(group), 1 if controls else 0)

    def reset(self) -> None:
        """Free all nodes, clear the scheduler, and reset node-id allocation.

        The engine equivalent of a "panic" / cmd-period: frees every node
        (``/g_freeAll 0``), clears pending scheduled bundles (``/clearSched``),
        and recreates the default group. Loaded SynthDefs, buffers, and buses
        are left intact (``/g_freeAll`` does not free them); only the node-id
        allocator is reset.
        """
        self.send_msg("/g_freeAll", 0)
        self.send_msg("/clearSched")
        self.send_msg("/g_new", 1, 0, 0)
        self._node_allocator.reset()

    # -- Node lifecycle notifications ------------------------------------------

    def enable_notifications(self, timeout: float = 1.0) -> None:
        """Register for node lifecycle notifications (``/notify 1``).

        Once enabled, the engine sends ``/n_go``/``/n_end``/``/n_off``/
        ``/n_on``/``/n_move`` as nodes are created, freed (including by a
        self-freeing ``DoneAction``), paused, resumed, or moved. Idempotent.
        Called automatically by :meth:`on_node` and :meth:`wait_for_node_free`.

        Waits for the engine's ``/done /notify`` so that registration is in
        effect before any subsequent node command -- otherwise the first
        node's ``/n_go`` can be missed. Falls back to fire-and-forget on
        timeout (e.g. a mock server with no reply path).
        """
        if not self._node_dispatch_installed:
            for address in _NODE_EVENT_ACTIONS:
                self.on(address, self._dispatch_node_event)
            self._node_dispatch_installed = True
        if self._notifications_enabled:
            return
        self.send_msg_sync(
            "/notify",
            1,
            reply_address="/done",
            match=lambda m: bool(m.contents) and m.contents[0] == "/notify",
            timeout=timeout,
        )
        self._notifications_enabled = True

    def disable_notifications(self) -> None:
        """Unregister from node lifecycle notifications (``/notify 0``)."""
        if not self._notifications_enabled:
            return
        self.send_msg("/notify", 0)
        self._notifications_enabled = False

    def _dispatch_node_event(self, msg: OscMessage) -> None:
        try:
            event = _parse_node_event(msg)
        except (IndexError, ValueError, KeyError):
            logger.debug("Malformed node notification: %s", msg.address)
            return
        for handler in list(self._node_handlers):
            try:
                handler(event)
            except Exception:  # noqa: BLE001 -- isolate user callbacks
                logger.exception("Node-event handler error")

    def on_node(self, callback: Callable[[NodeEvent], None]) -> None:
        """Register *callback* to receive every :class:`NodeEvent`.

        Enables notifications if not already on. Callbacks run on the reply
        thread, so they must be non-blocking.
        """
        self.enable_notifications()
        with self._reply_lock:
            self._node_handlers.append(callback)

    def remove_node_handler(self, callback: Callable[[NodeEvent], None]) -> None:
        """Remove a callback previously registered with :meth:`on_node`."""
        with self._reply_lock:
            try:
                self._node_handlers.remove(callback)
            except ValueError:
                pass

    def wait_for_node_free(self, node_id: SupportsInt, timeout: float = 5.0) -> bool:
        """Block until *node_id* is freed (``/n_end``), or *timeout*.

        Returns ``True`` if the node ended, ``False`` on timeout. Enables
        notifications if needed. Register the wait *before* the node can free
        itself (e.g. right after creating a self-freeing synth), or the
        ``/n_end`` may arrive first and be missed.
        """
        self.enable_notifications()
        target = int(node_id)
        reply = self.wait_for_reply(
            "/n_end",
            timeout=timeout,
            match=lambda m: bool(m.contents) and _osc_int(m.contents[0]) == target,
        )
        return reply is not None

    # -- SynthDef management ---------------------------------------------------

    def send_synthdef(self, synthdef: SynthDef) -> None:
        """Send a compiled SynthDef to the engine via /d_recv.

        Waits for the engine to confirm loading (``/done /d_recv``)
        before returning, so the SynthDef is ready for immediate use.
        Falls back to fire-and-forget if no reply arrives (e.g. mock
        servers in tests).
        """
        name = synthdef.effective_name
        compiled = synthdef.compile()
        # scsynth replies "/done /d_recv" -- match the sub-command so a /done
        # from an unrelated async command cannot resolve this wait early.
        self.send_msg_sync(
            "/d_recv",
            compiled,
            reply_address="/done",
            timeout=0.1,
            match=lambda m: bool(m.contents) and m.contents[0] == "/d_recv",
        )
        self._synthdefs.add(name)

    def load_synthdef(self, path: str | Path) -> None:
        """Load a .scsyndef file into the engine via /d_load.

        Args:
            path: Path to the .scsyndef file.
        """
        self.send_msg("/d_load", str(Path(path).resolve()))

    # -- Convenience -----------------------------------------------------------

    def synth(
        self,
        name: str,
        target: int = 1,
        action: AddAction | int = AddAction.ADD_TO_HEAD,
        **params: float,
    ) -> Synth:
        """Create a synth node. Returns a Synth proxy.

        Args:
            name: SynthDef name.
            target: Target node for placement.
            action: Add action (AddAction enum or int 0-4).
            **params: Initial synth parameter values.
        """
        node_id = self.next_node_id()
        args: list[OscArgument] = [name, node_id, int(action), int(target)]
        for key, value in params.items():
            args.append(key)
            args.append(float(value))
        self.send_msg("/s_new", *args)
        return Synth(self, node_id, name)

    def group(
        self, target: int = 0, action: AddAction | int = AddAction.ADD_TO_HEAD
    ) -> Group:
        """Create a group node. Returns a Group proxy.

        Args:
            target: Target node for placement.
            action: Add action (AddAction enum or int 0-4).
        """
        node_id = self.next_node_id()
        self.send_msg("/g_new", node_id, int(action), int(target))
        return Group(self, node_id)

    def par_group(
        self, target: int = 0, action: AddAction | int = AddAction.ADD_TO_HEAD
    ) -> ParGroup:
        """Create a parallel group node. Returns a ParGroup proxy.

        A ParGroup evaluates its child nodes in parallel across CPU cores.

        Args:
            target: Target node for placement.
            action: Add action (AddAction enum or int 0-4).
        """
        node_id = self.next_node_id()
        self.send_msg("/p_new", node_id, int(action), int(target))
        return ParGroup(self, node_id)

    def free(self, node_id: SupportsInt) -> None:
        """Free a node by ID (accepts int or Synth/Group proxy)."""
        self.send_msg("/n_free", int(node_id))

    @contextlib.contextmanager
    def managed_synth(
        self,
        name: str,
        target: int = 1,
        action: AddAction | int = AddAction.ADD_TO_HEAD,
        **params: float,
    ) -> Iterator[Synth]:
        """Create a synth and free it on context exit.

        Usage::

            with server.managed_synth("sine", frequency=440.0) as node:
                time.sleep(1)
            # node freed automatically
        """
        node = self.synth(name, target=target, action=action, **params)
        try:
            yield node
        finally:
            if self.is_running:
                self.free(node)

    @contextlib.contextmanager
    def managed_group(
        self,
        target: int = 0,
        action: AddAction | int = AddAction.ADD_TO_HEAD,
    ) -> Iterator[Group]:
        """Create a group and free it on context exit."""
        node = self.group(target=target, action=action)
        try:
            yield node
        finally:
            if self.is_running:
                self.free(node)

    @contextlib.contextmanager
    def managed_par_group(
        self,
        target: int = 0,
        action: AddAction | int = AddAction.ADD_TO_HEAD,
    ) -> Iterator[ParGroup]:
        """Create a parallel group and free it on context exit."""
        node = self.par_group(target=target, action=action)
        try:
            yield node
        finally:
            if self.is_running:
                self.free(node)

    def set(self, node_id: SupportsInt, **params: float) -> None:
        """Set parameter values on a running node.

        Args:
            node_id: The node to modify (int or Synth/Group proxy).
            **params: Parameter name-value pairs.
        """
        args: list[OscArgument] = [int(node_id)]
        for key, value in params.items():
            args.append(key)
            args.append(float(value))
        self.send_msg("/n_set", *args)

    # -- Buffer management -----------------------------------------------------

    def next_buffer_id(self) -> int:
        """Return a unique buffer ID, reusing freed ids (from 0)."""
        return self._buffer_allocator.allocate()

    def alloc_buffer(
        self,
        num_frames: int,
        num_channels: int = 1,
        buffer_id: int | None = None,
    ) -> int:
        """Allocate an empty buffer. Returns the buffer ID.

        Args:
            num_frames: Number of sample frames.
            num_channels: Number of channels.
            buffer_id: Explicit buffer ID, or None for auto-allocation.
        """
        if buffer_id is None:
            buffer_id = self.next_buffer_id()
        else:
            self._buffer_allocator.reserve(buffer_id)
        self.send_msg("/b_alloc", buffer_id, num_frames, num_channels)
        return buffer_id

    def read_buffer(
        self,
        path: str,
        buffer_id: int | None = None,
        start_frame: int = 0,
        num_frames: int = -1,
    ) -> int:
        """Allocate a buffer and read a sound file into it. Returns the buffer ID.

        Args:
            path: Path to the sound file.
            buffer_id: Explicit buffer ID, or None for auto-allocation.
            start_frame: Frame offset into the file.
            num_frames: Number of frames to read (-1 for entire file).
        """
        if buffer_id is None:
            buffer_id = self.next_buffer_id()
        else:
            self._buffer_allocator.reserve(buffer_id)
        self.send_msg("/b_allocRead", buffer_id, path, start_frame, num_frames)
        return buffer_id

    def write_buffer(
        self,
        buffer_id: int,
        path: str,
        header_format: str = "wav",
        sample_format: str = "int16",
        num_frames: int = -1,
        start_frame: int = 0,
        leave_open: bool = False,
    ) -> None:
        """Write buffer contents to a sound file.

        Args:
            buffer_id: Buffer to write.
            path: Destination file path.
            header_format: File format (e.g. "wav", "aiff").
            sample_format: Sample format (e.g. "int16", "float").
            num_frames: Number of frames to write (-1 for all).
            start_frame: Starting frame in the buffer.
            leave_open: If True, keep the file open for streaming
                (used by DiskOut for recording).
        """
        self.send_msg(
            "/b_write",
            buffer_id,
            path,
            header_format,
            sample_format,
            num_frames,
            start_frame,
            1 if leave_open else 0,
        )

    def free_buffer(self, buffer_id: int) -> None:
        """Free a buffer by ID and return it to the allocator pool."""
        self.send_msg("/b_free", buffer_id)
        self._buffer_allocator.free(buffer_id)

    def zero_buffer(self, buffer_id: int) -> None:
        """Zero all samples in a buffer."""
        self.send_msg("/b_zero", buffer_id)

    def close_buffer(self, buffer_id: int) -> None:
        """Close the sound file associated with a buffer (after b_write)."""
        self.send_msg("/b_close", buffer_id)

    # -- Direct buffer data exchange (numpy) -----------------------------------

    def _buffer_protocol(self) -> Any:
        """Return the protocol if it supports direct buffer access (scsynth)."""
        proto = self._protocol
        if not hasattr(proto, "buffer_get"):
            raise EngineError(
                "Direct buffer data access requires the embedded scsynth engine "
                "(not supported by the supernova protocol)."
            )
        return proto

    def buffer_info(self, buffer_id: SupportsInt) -> tuple[int, int, float]:
        """Return ``(frames, channels, sample_rate)`` for an allocated buffer.

        Requires the embedded scsynth engine.
        """
        return self._buffer_protocol().buffer_info(int(buffer_id))  # type: ignore[no-any-return]

    def get_buffer_data(self, buffer_id: SupportsInt) -> Any:
        """Copy a buffer's samples into a numpy array of shape ``(frames, channels)``.

        This is a direct in-process memory copy -- no OSC round-trip and no
        datagram-size limit -- which is the main advantage of the embedded
        engine. The buffer must already be allocated. The copy reads the live
        buffer, so a synth writing it concurrently may produce a torn read.

        Requires numpy and the embedded scsynth engine.
        """
        _require_numpy()
        return self._buffer_protocol().buffer_get(int(buffer_id))

    def set_buffer_data(self, buffer_id: SupportsInt, data: Any) -> None:
        """Copy a numpy array into an allocated buffer's samples.

        ``data`` may be 1-D (mono) or 2-D ``(frames, channels)``; it is coerced
        to contiguous float32 and its shape must match the buffer exactly. This
        is a direct in-process memory write; a synth reading the buffer
        concurrently may glitch.

        Requires numpy and the embedded scsynth engine.
        """
        np = _require_numpy()
        arr = np.ascontiguousarray(data, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        if arr.ndim != 2:
            raise ValueError("data must be 1-D (mono) or 2-D (frames, channels)")
        self._buffer_protocol().buffer_set(int(buffer_id), arr)

    def alloc_buffer_from_array(self, data: Any, *, sync: bool = True) -> int:
        """Allocate a buffer sized to ``data`` and fill it. Returns the buffer ID.

        Convenience for loading a numpy array (wavetable, sample, window) into
        the engine. ``data`` may be 1-D (mono) or 2-D ``(frames, channels)``.
        By default waits (``/sync``) for the allocation to complete before
        writing; pass ``sync=False`` if you have already synced.

        Requires numpy and the embedded scsynth engine.
        """
        np = _require_numpy()
        arr = np.ascontiguousarray(data, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        if arr.ndim != 2:
            raise ValueError("data must be 1-D (mono) or 2-D (frames, channels)")
        frames, channels = int(arr.shape[0]), int(arr.shape[1])
        buffer_id = self.alloc_buffer(frames, channels)
        if sync:
            self.sync()
        self.set_buffer_data(buffer_id, arr)
        return buffer_id

    @contextlib.contextmanager
    def managed_buffer(
        self,
        num_frames: int,
        num_channels: int = 1,
    ) -> Iterator[int]:
        """Allocate a buffer and free it on context exit."""
        buffer_id = self.alloc_buffer(num_frames, num_channels)
        try:
            yield buffer_id
        finally:
            if self.is_running:
                self.free_buffer(buffer_id)

    @contextlib.contextmanager
    def managed_read_buffer(
        self,
        path: str,
        start_frame: int = 0,
        num_frames: int = -1,
    ) -> Iterator[int]:
        """Read a sound file into a buffer and free it on context exit."""
        buffer_id = self.read_buffer(
            path, start_frame=start_frame, num_frames=num_frames
        )
        try:
            yield buffer_id
        finally:
            if self.is_running:
                self.free_buffer(buffer_id)

    # -- Bus allocation --------------------------------------------------------

    def audio_bus(self, num_channels: int = 1) -> Bus:
        """Allocate private audio bus(es). Returns a Bus proxy.

        Audio buses are allocated from the private range, starting after
        the hardware I/O buses (at ``options.first_private_bus_id``).

        Args:
            num_channels: Number of contiguous channels to allocate.
        """
        bus_id = self._audio_bus_allocator.allocate(num_channels)
        return Bus(self, bus_id, num_channels, "audio")

    def control_bus(self, num_channels: int = 1) -> Bus:
        """Allocate control bus(es). Returns a Bus proxy.

        Args:
            num_channels: Number of contiguous channels to allocate.
        """
        bus_id = self._control_bus_allocator.allocate(num_channels)
        return Bus(self, bus_id, num_channels, "control")

    def free_bus(self, bus: Bus) -> None:
        """Return a bus to the allocator pool.

        Args:
            bus: The Bus proxy to free.
        """
        if bus.rate == "audio":
            self._audio_bus_allocator.free(bus.bus_id)
        else:
            self._control_bus_allocator.free(bus.bus_id)

    @contextlib.contextmanager
    def managed_audio_bus(self, num_channels: int = 1) -> Iterator[Bus]:
        """Allocate an audio bus and free it on context exit."""
        bus = self.audio_bus(num_channels)
        try:
            yield bus
        finally:
            self.free_bus(bus)

    @contextlib.contextmanager
    def managed_control_bus(self, num_channels: int = 1) -> Iterator[Bus]:
        """Allocate a control bus and free it on context exit."""
        bus = self.control_bus(num_channels)
        try:
            yield bus
        finally:
            self.free_bus(bus)

    # -- Recording -------------------------------------------------------------

    def _ensure_recorder_synthdef(self, num_channels: int) -> str:
        """Build and send the recorder SynthDef for the given channel count.

        Returns the SynthDef name.
        """
        if num_channels in self._recorder_synthdefs:
            return self._recorder_synthdefs[num_channels]

        from .synthdef import SynthDefBuilder
        from .ugens.diskio import DiskOut
        from .ugens.inout import In

        name = f"__nanosynth_recorder_{num_channels}ch__"
        with SynthDefBuilder(buffer_id=0.0, bus=0.0) as builder:
            sig = In.ar(bus=builder["bus"], channel_count=num_channels)  # type: ignore[attr-defined]
            DiskOut.ar(buffer_id=builder["buffer_id"], source=sig)  # type: ignore[attr-defined]
        synthdef = builder.build(name=name)
        self.send_synthdef(synthdef)
        self._recorder_synthdefs[num_channels] = name
        return name

    def record(
        self,
        path: str | Path,
        *,
        num_channels: int | None = None,
        bus: int = 0,
        header_format: str = "wav",
        sample_format: str = "int16",
    ) -> None:
        """Start recording server audio output to a file.

        Args:
            path: Destination file path.
            num_channels: Number of channels to record. Defaults to
                ``options.output_bus_channel_count``.
            bus: Bus index to record from (default 0 = main output).
            header_format: File format (``"wav"`` or ``"aiff"``).
            sample_format: Sample encoding (``"int16"``, ``"int24"``,
                ``"float"``).

        Raises:
            RuntimeError: If already recording.
        """
        if self._recording is not None:
            raise EngineError("Already recording. Call stop_recording() first.")

        if num_channels is None:
            num_channels = self._options.output_bus_channel_count

        path_str = str(path)

        # 1. Allocate a disk-streaming buffer (65536 frames is SC convention)
        buffer_id = self.alloc_buffer(65536, num_channels)

        # 2. Open the buffer for writing with leave_open=True
        self.write_buffer(
            buffer_id,
            path_str,
            header_format=header_format,
            sample_format=sample_format,
            num_frames=-1,
            start_frame=0,
            leave_open=True,
        )

        # 3. Wait for the buffer to actually open on the server before the
        #    DiskOut synth starts writing into it.
        self.sync()

        # 4. Send the recorder SynthDef
        sd_name = self._ensure_recorder_synthdef(num_channels)

        # 5. Create recorder synth at tail of root group (group 0)
        node_id = self.next_node_id()
        self.send_msg(
            "/s_new",
            sd_name,
            node_id,
            int(AddAction.ADD_TO_TAIL),
            0,  # target = root group
            "buffer_id",
            float(buffer_id),
            "bus",
            float(bus),
        )

        self._recording = _RecordingState(
            path=path_str,
            buffer_id=buffer_id,
            synth_node_id=node_id,
        )
        logger.info("Recording to %s", path_str)

    def stop_recording(self) -> None:
        """Stop recording and finalize the audio file.

        Safe to call when not recording (no-op).
        """
        if self._recording is None:
            return

        rec = self._recording
        self._recording = None

        # 1. Free the recorder synth
        self.free(rec.synth_node_id)

        # 2. Flush the freed synth's final samples before closing the file.
        self.sync()

        # 3. Close and free the buffer
        self.close_buffer(rec.buffer_id)
        self.free_buffer(rec.buffer_id)

        logger.info("Stopped recording: %s", rec.path)

    @property
    def is_recording(self) -> bool:
        """Whether the server is currently recording."""
        return self._recording is not None
