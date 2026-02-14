"""High-level Server class wrapping the embedded scsynth engine."""

from __future__ import annotations

import contextlib
import itertools
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from .osc import OscMessage
from .scsynth import BootStatus, EmbeddedProcessProtocol, Options

if TYPE_CHECKING:
    from .osc import OscArgument
    from .synthdef import SynthDef

logger = logging.getLogger(__name__)


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
        self._synthdefs: set[str] = set()

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
