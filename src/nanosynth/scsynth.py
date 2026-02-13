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
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)

DEFAULT_IP_ADDRESS = "127.0.0.1"
DEFAULT_PORT = 57110


class BootStatus(enum.IntEnum):
    OFFLINE = 0
    BOOTING = 1
    ONLINE = 2
    QUITTING = 3


class ServerCannotBoot(Exception):
    pass


@dataclass(frozen=True)
class Options:
    """SuperCollider server options configuration."""

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
        atexit.register(self.quit)
        self.boot_future: concurrent.futures.Future[bool] = concurrent.futures.Future()
        self.exit_future: concurrent.futures.Future[int] = concurrent.futures.Future()
        self._world: Any = None
        self.thread: threading.Thread | None = None

    def boot(self, options: Options) -> None:
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

        if EmbeddedProcessProtocol._active_world:
            self.boot_future.set_result(False)
            self.status = BootStatus.OFFLINE
            raise ServerCannotBoot("An embedded scsynth World is already running")

        world_kwargs = _options_to_world_kwargs(options)

        try:
            self._world = world_new(**world_kwargs)
        except RuntimeError as exc:
            self.boot_future.set_result(False)
            self.status = BootStatus.OFFLINE
            raise ServerCannotBoot(str(exc)) from exc

        if not world_open_udp(self._world, options.ip_address, options.port):
            from nanosynth._scsynth import world_cleanup

            world_cleanup(self._world)
            self._world = None
            self.boot_future.set_result(False)
            self.status = BootStatus.OFFLINE
            raise ServerCannotBoot("World_OpenUDP failed")

        EmbeddedProcessProtocol._active_world = True

        def _on_print(text: str, _label: str = label) -> None:
            self.buffer_ += text
            if "\n" in self.buffer_:
                complete, _, self.buffer_ = self.buffer_.rpartition("\n")
                for line in complete.splitlines():
                    logger.info(f"[scsynth/{_label}] {line}")

        set_print_func(_on_print)

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
        EmbeddedProcessProtocol._active_world = False

    def quit(self) -> None:
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
