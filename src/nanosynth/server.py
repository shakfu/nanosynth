"""High-level Server class wrapping the embedded scsynth engine."""

from __future__ import annotations

import contextlib
import itertools
import logging
import struct
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, SupportsInt, Union

from .enums import AddAction
from .exceptions import EngineError, OscError
from .osc import OscMessage
from .scsynth import BootStatus, EmbeddedProcessProtocol, Options

if TYPE_CHECKING:
    from .osc import OscArgument
    from .supernova import EmbeddedSupernovaProtocol
    from .synthdef import SynthDef

    ServerProtocol = Union[EmbeddedProcessProtocol, EmbeddedSupernovaProtocol]
else:
    ServerProtocol = EmbeddedProcessProtocol

logger = logging.getLogger(__name__)


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

    def send_msg(self, address: str, *args: OscArgument) -> None:
        """Send an OSC message to the engine."""
        self._protocol.send_packet(OscMessage(address, *args).to_datagram())

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
