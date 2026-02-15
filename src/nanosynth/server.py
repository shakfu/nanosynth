"""High-level Server class wrapping the embedded scsynth engine."""

from __future__ import annotations

import contextlib
import itertools
import logging
import threading
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from .osc import OscMessage
from .scsynth import BootStatus, EmbeddedProcessProtocol, Options

if TYPE_CHECKING:
    from .osc import OscArgument
    from .synthdef import SynthDef

logger = logging.getLogger(__name__)


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

    def __init__(self, options: Options | None = None) -> None:
        self._options = options or Options()
        self._protocol = EmbeddedProcessProtocol()
        self._node_id_counter = itertools.count(1000)
        self._buffer_id_counter = itertools.count(0)
        self._allocated_buffers: set[int] = set()
        self._synthdefs: set[str] = set()
        self._reply_handlers: dict[str, list[Callable[..., Any]]] = {}
        self._pending_replies: dict[str, list[_ReplyEvent]] = {}
        self._reply_lock = threading.Lock()

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
        """Shut down the embedded scsynth engine."""
        if not self.is_running:
            return
        self.send_msg("/quit")
        self._protocol._shutdown()

    @property
    def is_running(self) -> bool:
        """Whether the engine is currently online."""
        return self._protocol.status == BootStatus.ONLINE

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
        except Exception:
            logger.debug("Failed to decode OSC reply (%d bytes)", len(data))
            return
        address = str(msg.address)
        with self._reply_lock:
            handlers = list(self._reply_handlers.get(address, []))
            waiters = self._pending_replies.pop(address, [])
        for handler in handlers:
            try:
                handler(msg)
            except Exception:
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
        """Send a compiled SynthDef to the engine via /d_recv."""
        name = synthdef.effective_name
        compiled = synthdef.compile()
        self.send_msg("/d_recv", compiled)
        self._synthdefs.add(name)

    # -- Convenience -----------------------------------------------------------

    def synth(
        self,
        name: str,
        target: int = 1,
        action: int = 0,
        **params: float,
    ) -> int:
        """Create a synth node. Returns the allocated node ID.

        Args:
            name: SynthDef name.
            target: Target node for placement.
            action: Add action (0=head, 1=tail, 2=before, 3=after, 4=replace).
            **params: Initial synth parameter values.
        """
        node_id = self.next_node_id()
        args: list[OscArgument] = [name, node_id, action, target]
        for key, value in params.items():
            args.append(key)
            args.append(float(value))
        self.send_msg("/s_new", *args)
        return node_id

    def group(self, target: int = 0, action: int = 0) -> int:
        """Create a group node. Returns the allocated node ID.

        Args:
            target: Target node for placement.
            action: Add action (0=head, 1=tail, 2=before, 3=after, 4=replace).
        """
        node_id = self.next_node_id()
        self.send_msg("/g_new", node_id, action, target)
        return node_id

    def free(self, node_id: int) -> None:
        """Free a node by ID."""
        self.send_msg("/n_free", node_id)

    @contextlib.contextmanager
    def managed_synth(
        self,
        name: str,
        target: int = 1,
        action: int = 0,
        **params: float,
    ) -> Iterator[int]:
        """Create a synth and free it on context exit.

        Usage::

            with server.managed_synth("sine", frequency=440.0) as node_id:
                time.sleep(1)
            # node freed automatically
        """
        node_id = self.synth(name, target=target, action=action, **params)
        try:
            yield node_id
        finally:
            if self.is_running:
                self.free(node_id)

    @contextlib.contextmanager
    def managed_group(
        self,
        target: int = 0,
        action: int = 0,
    ) -> Iterator[int]:
        """Create a group and free it on context exit."""
        node_id = self.group(target=target, action=action)
        try:
            yield node_id
        finally:
            if self.is_running:
                self.free(node_id)

    def set(self, node_id: int, **params: float) -> None:
        """Set parameter values on a running node.

        Args:
            node_id: The node to modify.
            **params: Parameter name-value pairs.
        """
        args: list[OscArgument] = [node_id]
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
    ) -> None:
        """Write buffer contents to a sound file.

        Args:
            buffer_id: Buffer to write.
            path: Destination file path.
            header_format: File format (e.g. "wav", "aiff").
            sample_format: Sample format (e.g. "int16", "float").
            num_frames: Number of frames to write (-1 for all).
            start_frame: Starting frame in the buffer.
        """
        self.send_msg(
            "/b_write",
            buffer_id,
            path,
            header_format,
            sample_format,
            num_frames,
            start_frame,
            0,  # leave_open flag
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
