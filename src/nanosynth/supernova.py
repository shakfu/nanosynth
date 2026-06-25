"""Embedded supernova (parallel DSP engine) lifecycle management."""

import atexit
import concurrent.futures
import logging
import threading
from typing import Any, Callable

from .exceptions import EngineError, ServerCannotBoot
from .scsynth import BootStatus, Options, _options_to_world_kwargs

logger = logging.getLogger(__name__)


def _options_to_supernova_kwargs(options: Options) -> dict[str, Any]:
    """Map Options fields to _supernova.supernova_new keyword arguments.

    Same field mapping as ``_options_to_world_kwargs()`` but targeting
    supernova's parameter names.  The ``threads`` parameter controls
    supernova's DSP thread count (defaults to hardware concurrency).
    """
    # Start from the shared scsynth mapping (most fields are identical)
    kwargs = _options_to_world_kwargs(options)

    # Remove scsynth-specific keys not used by supernova
    kwargs.pop("rendezvous", None)
    kwargs.pop("realtime", None)
    kwargs.pop("max_logins", None)

    # supernova uses int32_t for hardware_buffer_size (vs uint32_t in scsynth)
    if "preferred_hardware_buffer_size" in kwargs:
        kwargs["preferred_hardware_buffer_size"] = int(
            kwargs["preferred_hardware_buffer_size"]
        )

    # supernova uses uint16_t for load_graph_defs
    if "load_graph_defs" in kwargs:
        kwargs["load_graph_defs"] = int(kwargs["load_graph_defs"])

    # supernova threads: default 0 means "use hardware_concurrency()" in C++
    kwargs["threads"] = 0

    return kwargs


class EmbeddedSupernovaProtocol:
    """Process protocol that runs supernova in-process via libsupernova.

    Drop-in replacement for ``EmbeddedProcessProtocol`` that uses
    supernova's parallel DSP engine instead of scsynth.  Supports the
    same ``boot`` / ``quit`` / ``send_packet`` / ``set_reply_callback``
    interface so it can be used with ``Server``.

    Only one supernova instance may be active per process (singleton
    ``nova_server`` global).
    """

    _active: bool = False
    _active_lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        *,
        name: str | None = None,
        on_boot_callback: Callable[[], None] | None = None,
        on_panic_callback: Callable[[], None] | None = None,
        on_quit_callback: Callable[[], None] | None = None,
    ) -> None:
        self.name = name
        self.on_boot_callback = on_boot_callback
        self.on_panic_callback = on_panic_callback
        self.on_quit_callback = on_quit_callback
        self.status = BootStatus.OFFLINE
        self.options = Options()
        self.buffer_ = ""
        self.error_text = ""
        self._reply_callback: Callable[[bytes], None] | None = None
        # atexit cleanup is (un)registered around the booted lifetime, not in
        # __init__, so never-booted protocol objects do not accumulate atexit
        # callbacks (each would hold a strong ref and run at interpreter exit).
        self.boot_future: concurrent.futures.Future[bool] = concurrent.futures.Future()
        self.exit_future: concurrent.futures.Future[int] = concurrent.futures.Future()
        self._server: Any = None
        self.thread: threading.Thread | None = None

    def boot(self, options: Options) -> None:
        """Boot the embedded supernova engine with the given options.

        Creates a nova_server, opens the audio backend, installs print
        and reply callbacks, and starts a daemon thread for the event loop.

        Raises:
            ServerCannotBoot: If a supernova instance is already active,
                or if nova_server construction or audio setup fails.
        """
        self.options = options
        label = self.name or hex(id(self))
        logger.info(
            f"[{options.ip_address}:{options.port}/{label}] "
            "booting (embedded supernova) ..."
        )
        if self.status != BootStatus.OFFLINE:
            logger.info(
                f"[{options.ip_address}:{options.port}/{label}] ... already booted!"
            )
            return
        self.status = BootStatus.BOOTING
        self.error_text = ""
        self.buffer_ = ""
        # Ensure exactly one atexit cleanup for this booted instance.
        atexit.unregister(self.quit)
        atexit.register(self.quit)

        from nanosynth._supernova import set_print_func, supernova_new  # type: ignore[import-untyped]

        self.boot_future = concurrent.futures.Future()
        self.exit_future = concurrent.futures.Future()

        with EmbeddedSupernovaProtocol._active_lock:
            if EmbeddedSupernovaProtocol._active:
                self.boot_future.set_result(False)
                self.status = BootStatus.OFFLINE
                raise ServerCannotBoot(
                    "An embedded supernova instance is already running"
                )
            EmbeddedSupernovaProtocol._active = True

        supernova_kwargs = _options_to_supernova_kwargs(options)

        try:
            self._server = supernova_new(**supernova_kwargs)
        except RuntimeError as exc:
            with EmbeddedSupernovaProtocol._active_lock:
                EmbeddedSupernovaProtocol._active = False
            self.boot_future.set_result(False)
            self.status = BootStatus.OFFLINE
            raise ServerCannotBoot(str(exc)) from exc

        def _on_print(text: str, _label: str = label) -> None:
            self.buffer_ += text
            if "\n" in self.buffer_:
                complete, _, self.buffer_ = self.buffer_.rpartition("\n")
                for line in complete.splitlines():
                    logger.info(f"[supernova/{_label}] {line}")

        set_print_func(_on_print)

        if self._reply_callback is not None:
            from nanosynth._supernova import set_reply_func

            set_reply_func(self._reply_callback)

        # Bring the engine online. Anything that raises from here on must not
        # leave the global _active flag set, or every subsequent boot would
        # raise ServerCannotBoot for the life of the process. The run thread
        # is started last so this rollback never has to coordinate with a
        # running _run_loop.
        try:
            self.status = BootStatus.ONLINE
            if self.on_boot_callback:
                self.on_boot_callback()
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()
        except BaseException as exc:
            self._abort_partial_boot()
            raise ServerCannotBoot(f"boot failed after server creation: {exc}") from exc

        self.boot_future.set_result(True)

    def _abort_partial_boot(self) -> None:
        """Tear down a server whose boot failed before the run loop started.

        Safe to call only when no ``_run_loop`` thread is active, so server
        teardown cannot race the event loop. Always clears ``_active`` so
        future boots can proceed.
        """
        from nanosynth._supernova import set_print_func, supernova_cleanup

        set_print_func(None)
        if self._server is not None:
            supernova_cleanup(self._server)
            self._server = None
        self.status = BootStatus.OFFLINE
        with EmbeddedSupernovaProtocol._active_lock:
            EmbeddedSupernovaProtocol._active = False
        if not self.boot_future.done():
            self.boot_future.set_result(False)

    def _run_loop(self) -> None:
        """Run supernova's event loop (blocks until terminate)."""
        from nanosynth._supernova import set_print_func, supernova_run

        supernova_run(self._server)
        set_print_func(None)
        was_quitting = self.status == BootStatus.QUITTING
        self.status = BootStatus.OFFLINE
        with EmbeddedSupernovaProtocol._active_lock:
            EmbeddedSupernovaProtocol._active = False
        self.exit_future.set_result(0)
        if was_quitting and self.on_quit_callback:
            self.on_quit_callback()
        elif not was_quitting and self.on_panic_callback:
            self.on_panic_callback()

    def _shutdown(self) -> None:
        """Shut down the event loop and clean up."""
        # quit() has already sent supernova_terminate, which makes
        # supernova_run return; _run_loop then resolves exit_future. When the
        # run thread is alive, wait on that future so we only delete the
        # nova_server after its event loop has provably exited, instead of
        # racing supernova_cleanup against a thread still inside supernova_run
        # (a use-after-free on self._server). exit_future is only ever resolved
        # by the run thread, so we wait on it only while that thread is alive.
        if self.thread is not None and self.thread.is_alive():
            try:
                self.exit_future.result(timeout=5)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "supernova event loop did not exit within 5s; cleaning up anyway"
                )
            self.thread.join(timeout=5)
        # Deactivate audio and delete nova_server now that the loop has exited.
        if self._server is not None:
            from nanosynth._supernova import supernova_cleanup

            supernova_cleanup(self._server)
        self._server = None
        self.status = BootStatus.OFFLINE
        with EmbeddedSupernovaProtocol._active_lock:
            EmbeddedSupernovaProtocol._active = False

    def send_packet(self, data: bytes) -> bool:
        """Send a raw OSC packet to the engine."""
        if self.status != BootStatus.ONLINE or self._server is None:
            raise EngineError("Server is not running")
        from nanosynth._supernova import supernova_send_packet

        result: bool = supernova_send_packet(self._server, data)
        return result

    def send_msg(self, address: str | int, *args: "Any") -> bool:
        """Send an OSC message to the engine."""
        from nanosynth.osc import OscMessage

        return self.send_packet(OscMessage(address, *args).to_datagram())

    def set_reply_callback(self, callback: Callable[[bytes], None] | None) -> None:
        """Set (or clear) the callback for OSC replies from the engine.

        If the engine is already booted, the callback is installed immediately.
        Otherwise it will be installed on the next boot.

        Args:
            callback: A callable receiving raw OSC bytes, or None to clear.
        """
        self._reply_callback = callback
        if self.status == BootStatus.ONLINE:
            from nanosynth._supernova import set_reply_func

            set_reply_func(callback)

    def quit(self) -> None:
        """Shut down the embedded supernova engine.

        No-op if the engine is not currently online.  Blocks until the
        engine thread has joined (up to 5 seconds, then force-cleanup).
        """
        label = self.name or hex(id(self))
        logger.info(
            f"[{self.options.ip_address}:{self.options.port}/{label}] quitting ..."
        )
        if self.status != BootStatus.ONLINE or self._server is None:
            logger.info(
                f"[{self.options.ip_address}:{self.options.port}/{label}] "
                "... already quit!"
            )
            return
        self.status = BootStatus.QUITTING
        # Send terminate signal to unblock the event loop
        from nanosynth._supernova import supernova_terminate

        supernova_terminate(self._server)
        self._shutdown()
        atexit.unregister(self.quit)
        logger.info(
            f"[{self.options.ip_address}:{self.options.port}/{label}] ... quit!"
        )
