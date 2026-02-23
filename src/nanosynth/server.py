"""High-level Server class wrapping the embedded scsynth engine."""

from __future__ import annotations

import contextlib
import itertools
import logging
import struct
import threading
import time
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
    """One-shot waiter for a single OSC reply."""

    __slots__ = ("_event", "message")

    def __init__(self) -> None:
        self._event = threading.Event()
        self.message: OscMessage | None = None

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
        self._node_id_counter = itertools.count(1000)
        self._buffer_id_counter = itertools.count(0)
        self._allocated_buffers: set[int] = set()
        self._audio_bus_counter = itertools.count(self._options.first_private_bus_id)
        self._control_bus_counter = itertools.count(0)
        self._allocated_audio_buses: set[int] = set()
        self._allocated_control_buses: set[int] = set()
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
        """Return a unique node ID (monotonically increasing from 1000)."""
        return next(self._node_id_counter)

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
            waiters = self._pending_replies.pop(address, [])
        for handler in handlers:
            try:
                handler(msg)
            except Exception:  # noqa: BLE001  -- isolate user callbacks
                logger.exception("Reply handler error for %s", address)
        for waiter in waiters:
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

    def wait_for_reply(self, address: str, timeout: float = 5.0) -> OscMessage | None:
        """Block until a reply arrives at *address*, or timeout.

        Returns the decoded OscMessage, or None on timeout.
        """
        event = _ReplyEvent()
        with self._reply_lock:
            self._pending_replies.setdefault(address, []).append(event)
        return event.wait(timeout=timeout)

    def send_msg_sync(
        self,
        address: str,
        *args: OscArgument,
        reply_address: str,
        timeout: float = 5.0,
    ) -> OscMessage | None:
        """Send a message and wait for a reply at *reply_address*.

        Returns the decoded reply OscMessage, or None on timeout.
        """
        event = _ReplyEvent()
        with self._reply_lock:
            self._pending_replies.setdefault(reply_address, []).append(event)
        self.send_msg(address, *args)
        return event.wait(timeout=timeout)

    # -- SynthDef management ---------------------------------------------------

    def send_synthdef(self, synthdef: SynthDef) -> None:
        """Send a compiled SynthDef to the engine via /d_recv.

        Waits for the engine to confirm loading (``/done /d_recv``)
        before returning, so the SynthDef is ready for immediate use.
        """
        name = synthdef.effective_name
        compiled = synthdef.compile()
        self.send_msg_sync("/d_recv", compiled, reply_address="/done")
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
        """Return a unique buffer ID (monotonically increasing from 0)."""
        return next(self._buffer_id_counter)

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
        self.send_msg("/b_alloc", buffer_id, num_frames, num_channels)
        self._allocated_buffers.add(buffer_id)
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
        self.send_msg("/b_allocRead", buffer_id, path, start_frame, num_frames)
        self._allocated_buffers.add(buffer_id)
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
        """Free a buffer by ID."""
        self.send_msg("/b_free", buffer_id)
        self._allocated_buffers.discard(buffer_id)

    def zero_buffer(self, buffer_id: int) -> None:
        """Zero all samples in a buffer."""
        self.send_msg("/b_zero", buffer_id)

    def close_buffer(self, buffer_id: int) -> None:
        """Close the sound file associated with a buffer (after b_write)."""
        self.send_msg("/b_close", buffer_id)

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
        bus_id = next(self._audio_bus_counter)
        # For multi-channel, advance the counter for remaining channels
        for _ in range(num_channels - 1):
            next(self._audio_bus_counter)
        self._allocated_audio_buses.add(bus_id)
        return Bus(self, bus_id, num_channels, "audio")

    def control_bus(self, num_channels: int = 1) -> Bus:
        """Allocate control bus(es). Returns a Bus proxy.

        Args:
            num_channels: Number of contiguous channels to allocate.
        """
        bus_id = next(self._control_bus_counter)
        for _ in range(num_channels - 1):
            next(self._control_bus_counter)
        self._allocated_control_buses.add(bus_id)
        return Bus(self, bus_id, num_channels, "control")

    def free_bus(self, bus: Bus) -> None:
        """Return a bus to the allocator pool.

        Args:
            bus: The Bus proxy to free.
        """
        if bus.rate == "audio":
            self._allocated_audio_buses.discard(bus.bus_id)
        else:
            self._allocated_control_buses.discard(bus.bus_id)

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

        # 3. Brief pause for buffer to open on the server
        time.sleep(0.1)

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

        # 2. Brief pause to let final samples flush
        time.sleep(0.1)

        # 3. Close and free the buffer
        self.close_buffer(rec.buffer_id)
        self.free_buffer(rec.buffer_id)

        logger.info("Stopped recording: %s", rec.path)

    @property
    def is_recording(self) -> bool:
        """Whether the server is currently recording."""
        return self._recording is not None
