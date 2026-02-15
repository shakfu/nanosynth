"""Embedded SuperCollider synthesis engine lifecycle management."""

import atexit
import concurrent.futures
import enum
import logging
import os
import platform
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal

if TYPE_CHECKING:
    from nanosynth.osc import OscArgument

logger = logging.getLogger(__name__)

DEFAULT_IP_ADDRESS = "127.0.0.1"
DEFAULT_PORT = 57110


class BootStatus(enum.IntEnum):
    """State machine for the embedded engine lifecycle."""

    OFFLINE = 0
    BOOTING = 1
    ONLINE = 2
    QUITTING = 3


class ServerCannotBoot(Exception):
    """Raised when the embedded scsynth engine fails to start."""

    pass


@dataclass(frozen=True)
class Options:
    """SuperCollider server options configuration.

    All fields have sensible defaults. The most commonly adjusted options:

    - ``verbosity`` -- log level (0 = silent, default).
    - ``sample_rate`` -- preferred sample rate (None = use hardware default).
    - ``output_bus_channel_count`` / ``input_bus_channel_count`` -- number
      of hardware I/O channels.
    - ``memory_size`` -- real-time memory pool in KB (default 8192).
    - ``block_size`` -- control block size in samples (default 64).
    - ``ugen_plugins_path`` -- override UGen plugin search path (normally
      auto-detected from the installed wheel or ``SC_PLUGIN_PATH``).
    """

    audio_bus_channel_count: int = 1024
    block_size: int = 64
    buffer_count: int = 1024
    control_bus_channel_count: int = 16384
    hardware_buffer_size: int | None = None
    input_bus_channel_count: int = 8
    input_device: str | None = None
    input_stream_mask: str = ""
    ip_address: str = DEFAULT_IP_ADDRESS
    load_synthdefs: bool = True
    maximum_logins: int = 1
    maximum_node_count: int = 1024
    maximum_synthdef_count: int = 1024
    memory_locking: bool = False
    memory_size: int = 8192
    output_bus_channel_count: int = 8
    output_device: str | None = None
    output_stream_mask: str = ""
    password: str | None = None
    port: int = DEFAULT_PORT
    protocol: str = "udp"
    random_number_generator_count: int = 64
    realtime: bool = True
    restricted_path: str | None = None
    safety_clip: Literal["inf"] | int | None = None
    sample_rate: int | None = None
    ugen_plugins_path: str | None = None
    verbosity: int = 0
    wire_buffer_count: int = 64
    zero_configuration: bool = False

    def __post_init__(self) -> None:
        if self.audio_bus_channel_count < (
            self.input_bus_channel_count + self.output_bus_channel_count
        ):
            raise ValueError("Insufficient audio buses")

    @property
    def first_private_bus_id(self) -> int:
        return self.output_bus_channel_count + self.input_bus_channel_count

    @property
    def private_audio_bus_channel_count(self) -> int:
        return (
            self.audio_bus_channel_count
            - self.input_bus_channel_count
            - self.output_bus_channel_count
        )


def find_ugen_plugins_path() -> Path | None:
    """Find the UGen plugins directory for the embedded scsynth.

    Searches:
    1. The ``SC_PLUGIN_PATH`` environment variable.
    2. Bundled plugins (installed in wheel alongside this package).
    3. Common SuperCollider installation plugin directories.
    """
    # 1. Explicit environment variable
    env_path = os.environ.get("SC_PLUGIN_PATH")
    if env_path:
        path = Path(env_path)
        if path.is_dir():
            return path
    # 2. Bundled plugins (installed in wheel alongside this package)
    bundled = Path(__file__).parent / "plugins"
    if bundled.is_dir():
        return bundled
    # Editable installs: __file__ points to source tree, compiled extensions
    # and plugins are in site-packages. Check next to _scsynth extension.
    try:
        from nanosynth import _scsynth

        bundled = Path(_scsynth.__file__).parent / "plugins"
        if bundled.is_dir():
            return bundled
    except (ImportError, TypeError):
        pass
    # 3. Common system installation paths
    system = platform.system()
    if system == "Darwin":
        candidates = [
            Path("/Applications/SuperCollider.app/Contents/Resources/plugins"),
            Path(
                "/Applications/SuperCollider/SuperCollider.app"
                "/Contents/Resources/plugins"
            ),
        ]
    elif system == "Linux":
        candidates = [
            Path("/usr/lib/SuperCollider/plugins"),
            Path("/usr/local/lib/SuperCollider/plugins"),
        ]
    else:
        candidates = list[Path]()
    for path in candidates:
        if path.is_dir():
            return path
    return None


def _options_to_world_kwargs(options: Options) -> dict[str, Any]:
    """Map Options fields to _scsynth.world_new keyword arguments."""
    kwargs: dict[str, Any] = {
        "num_audio_bus_channels": options.audio_bus_channel_count,
        "num_input_bus_channels": options.input_bus_channel_count,
        "num_output_bus_channels": options.output_bus_channel_count,
        "num_control_bus_channels": options.control_bus_channel_count,
        "block_size": options.block_size,
        "num_buffers": options.buffer_count,
        "max_nodes": options.maximum_node_count,
        "max_graph_defs": options.maximum_synthdef_count,
        "max_wire_bufs": options.wire_buffer_count,
        "num_rgens": options.random_number_generator_count,
        "max_logins": options.maximum_logins,
        "realtime_memory_size": options.memory_size,
        "load_graph_defs": 1 if options.load_synthdefs else 0,
        "memory_locking": options.memory_locking,
        "realtime": options.realtime,
        "verbosity": options.verbosity,
        "rendezvous": options.zero_configuration,
        "shared_memory_id": options.port,
    }
    if options.sample_rate is not None:
        kwargs["preferred_sample_rate"] = options.sample_rate
    if options.hardware_buffer_size is not None:
        kwargs["preferred_hardware_buffer_size"] = options.hardware_buffer_size
    ugen_path = options.ugen_plugins_path or find_ugen_plugins_path()
    if ugen_path:
        kwargs["ugen_plugins_path"] = str(ugen_path)
    else:
        logger.warning(
            "No UGen plugins path found. The engine will boot without UGen "
            "plugins and produce no audio. Set the SC_PLUGIN_PATH environment "
            "variable or install nanosynth from a wheel with bundled plugins."
        )
    if options.restricted_path is not None:
        kwargs["restricted_path"] = options.restricted_path
    if options.password:
        kwargs["password"] = options.password
    if options.input_device:
        kwargs["in_device_name"] = options.input_device
    if options.output_device:
        kwargs["out_device_name"] = options.output_device
    if options.input_stream_mask:
        kwargs["input_streams_enabled"] = options.input_stream_mask
    if options.output_stream_mask:
        kwargs["output_streams_enabled"] = options.output_stream_mask
    if options.safety_clip is not None:
        kwargs["safety_clip_threshold"] = float(options.safety_clip)
    return kwargs


class EmbeddedProcessProtocol:
    """Process protocol that runs scsynth in-process via libscsynth."""

    _active_world: bool = False
    _active_world_lock: threading.Lock = threading.Lock()

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
        atexit.register(self.quit)
        self.boot_future: concurrent.futures.Future[bool] = concurrent.futures.Future()
        self.exit_future: concurrent.futures.Future[int] = concurrent.futures.Future()
        self._world: Any = None
        self.thread: threading.Thread | None = None

    def boot(self, options: Options) -> None:
        """Boot the embedded scsynth engine with the given options.

        Creates a World via libscsynth, opens a UDP port for OSC
        communication, installs print and reply callbacks, and starts
        a daemon thread that waits for engine shutdown.

        Raises:
            ServerCannotBoot: If a World is already active, or if
                World_New or World_OpenUDP fails.
        """
        self.options = options
        label = self.name or hex(id(self))
        logger.info(
            f"[{options.ip_address}:{options.port}/{label}] booting (embedded) ..."
        )
        if self.status != BootStatus.OFFLINE:
            logger.info(
                f"[{options.ip_address}:{options.port}/{label}] ... already booted!"
            )
            return
        self.status = BootStatus.BOOTING
        self.error_text = ""
        self.buffer_ = ""

        from nanosynth._scsynth import set_print_func, world_new, world_open_udp  # type: ignore[import-untyped]

        self.boot_future = concurrent.futures.Future()
        self.exit_future = concurrent.futures.Future()

        with EmbeddedProcessProtocol._active_world_lock:
            if EmbeddedProcessProtocol._active_world:
                self.boot_future.set_result(False)
                self.status = BootStatus.OFFLINE
                raise ServerCannotBoot("An embedded scsynth World is already running")
            EmbeddedProcessProtocol._active_world = True

        world_kwargs = _options_to_world_kwargs(options)

        try:
            self._world = world_new(**world_kwargs)
        except RuntimeError as exc:
            with EmbeddedProcessProtocol._active_world_lock:
                EmbeddedProcessProtocol._active_world = False
            self.boot_future.set_result(False)
            self.status = BootStatus.OFFLINE
            raise ServerCannotBoot(str(exc)) from exc

        if not world_open_udp(self._world, options.ip_address, options.port):
            from nanosynth._scsynth import world_cleanup

            world_cleanup(self._world)
            self._world = None
            with EmbeddedProcessProtocol._active_world_lock:
                EmbeddedProcessProtocol._active_world = False
            self.boot_future.set_result(False)
            self.status = BootStatus.OFFLINE
            raise ServerCannotBoot("World_OpenUDP failed")

        def _on_print(text: str, _label: str = label) -> None:
            self.buffer_ += text
            if "\n" in self.buffer_:
                complete, _, self.buffer_ = self.buffer_.rpartition("\n")
                for line in complete.splitlines():
                    logger.info(f"[scsynth/{_label}] {line}")

        set_print_func(_on_print)

        if self._reply_callback is not None:
            from nanosynth._scsynth import set_reply_func

            set_reply_func(self._reply_callback)

        self.status = BootStatus.ONLINE
        self.boot_future.set_result(True)
        if self.on_boot_callback:
            self.on_boot_callback()

        self.thread = threading.Thread(target=self._wait_for_quit, daemon=True)
        self.thread.start()

    def _wait_for_quit(self) -> None:
        from nanosynth._scsynth import set_print_func, world_wait_for_quit

        world_wait_for_quit(self._world, False)
        set_print_func(None)
        was_quitting = self.status == BootStatus.QUITTING
        self.status = BootStatus.OFFLINE
        self._world = None
        with EmbeddedProcessProtocol._active_world_lock:
            EmbeddedProcessProtocol._active_world = False
        self.exit_future.set_result(0)
        if was_quitting and self.on_quit_callback:
            self.on_quit_callback()
        elif not was_quitting and self.on_panic_callback:
            self.on_panic_callback()

    def _shutdown(self) -> None:
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                from nanosynth._scsynth import world_cleanup

                if self._world is not None:
                    world_cleanup(self._world, False)
                self.thread.join()
        self.status = BootStatus.OFFLINE
        with EmbeddedProcessProtocol._active_world_lock:
            EmbeddedProcessProtocol._active_world = False

    def send_packet(self, data: bytes) -> bool:
        """Send a raw OSC packet to the engine."""
        if self.status != BootStatus.ONLINE or self._world is None:
            raise RuntimeError("Server is not running")
        from nanosynth._scsynth import world_send_packet

        result: bool = world_send_packet(self._world, data)
        return result

    def send_msg(self, address: str | int, *args: "OscArgument") -> bool:
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
            from nanosynth._scsynth import set_reply_func

            set_reply_func(callback)

    def quit(self) -> None:
        """Shut down the embedded scsynth engine.

        No-op if the engine is not currently online. Blocks until the
        engine thread has joined (up to 5 seconds, then force-cleanup).
        """
        label = self.name or hex(id(self))
        logger.info(
            f"[{self.options.ip_address}:{self.options.port}/{label}] quitting ..."
        )
        if self.status != BootStatus.ONLINE:
            logger.info(
                f"[{self.options.ip_address}:{self.options.port}/{label}] "
                "... already quit!"
            )
            return
        self.status = BootStatus.QUITTING
        self._shutdown()
        logger.info(
            f"[{self.options.ip_address}:{self.options.port}/{label}] ... quit!"
        )
