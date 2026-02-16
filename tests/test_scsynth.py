"""Basic tests for scsynth module."""

import sys
import threading
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from nanosynth.enums import AddAction
from nanosynth.scsynth import (
    BootStatus,
    EmbeddedProcessProtocol,
    Options,
    ServerCannotBoot,
    _options_to_world_kwargs,
    find_ugen_plugins_path,
)


class TestOptions:
    def test_defaults(self):
        opts = Options()
        assert opts.audio_bus_channel_count == 1024
        assert opts.block_size == 64
        assert opts.buffer_count == 1024
        assert opts.input_bus_channel_count == 8
        assert opts.output_bus_channel_count == 8
        assert opts.ip_address == "127.0.0.1"
        assert opts.port == 57110
        assert opts.realtime is True

    def test_custom_options(self):
        opts = Options(
            audio_bus_channel_count=2048,
            block_size=128,
            port=57111,
        )
        assert opts.audio_bus_channel_count == 2048
        assert opts.block_size == 128
        assert opts.port == 57111

    def test_insufficient_audio_buses(self):
        with pytest.raises(ValueError, match="Insufficient audio buses"):
            Options(
                audio_bus_channel_count=4,
                input_bus_channel_count=8,
                output_bus_channel_count=8,
            )

    def test_frozen(self):
        opts = Options()
        with pytest.raises(AttributeError):
            opts.port = 9999  # type: ignore

    def test_first_private_bus_id(self):
        opts = Options()
        assert opts.first_private_bus_id == 16  # 8 in + 8 out

    def test_private_audio_bus_channel_count(self):
        opts = Options()
        assert opts.private_audio_bus_channel_count == 1008  # 1024 - 8 - 8


class TestOptionsToWorldKwargs:
    def test_default_mapping(self):
        opts = Options()
        kwargs = _options_to_world_kwargs(opts)
        assert kwargs["num_audio_bus_channels"] == 1024
        assert kwargs["num_input_bus_channels"] == 8
        assert kwargs["num_output_bus_channels"] == 8
        assert kwargs["num_control_bus_channels"] == 16384
        assert kwargs["block_size"] == 64
        assert kwargs["num_buffers"] == 1024
        assert kwargs["max_nodes"] == 1024
        assert kwargs["max_graph_defs"] == 1024
        assert kwargs["max_wire_bufs"] == 64
        assert kwargs["num_rgens"] == 64
        assert kwargs["max_logins"] == 1
        assert kwargs["realtime_memory_size"] == 8192
        assert kwargs["load_graph_defs"] == 1
        assert kwargs["memory_locking"] is False
        assert kwargs["realtime"] is True
        assert kwargs["verbosity"] == 0
        assert kwargs["rendezvous"] is False  # zero_configuration default
        assert kwargs["shared_memory_id"] == 57110  # port

    def test_optional_fields(self):
        opts = Options(
            sample_rate=48000,
            hardware_buffer_size=512,
            password="secret",
            input_device="Built-in",
            output_device="Built-in",
            restricted_path="/tmp",
        )
        kwargs = _options_to_world_kwargs(opts)
        assert kwargs["preferred_sample_rate"] == 48000
        assert kwargs["preferred_hardware_buffer_size"] == 512
        assert kwargs["password"] == "secret"
        assert kwargs["in_device_name"] == "Built-in"
        assert kwargs["out_device_name"] == "Built-in"
        assert kwargs["restricted_path"] == "/tmp"

    def test_load_synthdefs_false(self):
        opts = Options(load_synthdefs=False)
        kwargs = _options_to_world_kwargs(opts)
        assert kwargs["load_graph_defs"] == 0

    def test_stream_masks(self):
        opts = Options(input_stream_mask="0011", output_stream_mask="1100")
        kwargs = _options_to_world_kwargs(opts)
        assert kwargs["input_streams_enabled"] == "0011"
        assert kwargs["output_streams_enabled"] == "1100"

    def test_safety_clip(self):
        opts = Options(safety_clip=1)
        kwargs = _options_to_world_kwargs(opts)
        assert kwargs["safety_clip_threshold"] == 1.0

    def test_ugen_plugins_path_from_options(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        opts = Options(ugen_plugins_path=str(plugins_dir))
        kwargs = _options_to_world_kwargs(opts)
        assert kwargs["ugen_plugins_path"] == str(plugins_dir)


class TestFindUgenPluginsPath:
    def test_returns_path_or_none(self):
        result = find_ugen_plugins_path()
        # On dev machines this should find plugins; in bare CI it might not
        assert result is None or result.is_dir()

    def test_env_var_override(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "my_plugins"
        plugins_dir.mkdir()
        monkeypatch.setenv("SC_PLUGIN_PATH", str(plugins_dir))
        result = find_ugen_plugins_path()
        assert result == plugins_dir

    def test_env_var_nonexistent_dir_skipped(self, monkeypatch):
        monkeypatch.setenv("SC_PLUGIN_PATH", "/nonexistent/path/xyz")
        # Should fall through to other search paths, not crash
        result = find_ugen_plugins_path()
        assert result is None or result.is_dir()


class TestBootStatus:
    def test_values(self):
        assert BootStatus.OFFLINE == 0
        assert BootStatus.BOOTING == 1
        assert BootStatus.ONLINE == 2
        assert BootStatus.QUITTING == 3


class TestScynthImport:
    def test_import_scsynth(self):
        from nanosynth import _scsynth  # noqa: F401


def _make_mock_scsynth_module(
    wait_event: threading.Event | None = None,
) -> ModuleType:
    """Create a mock _scsynth C extension module.

    If wait_event is provided, world_wait_for_quit blocks until the event
    is set, simulating the real blocking behavior.
    """
    mod = ModuleType("nanosynth._scsynth")
    mod.set_print_func = MagicMock()  # type: ignore[attr-defined]
    mod.set_reply_func = MagicMock()  # type: ignore[attr-defined]
    mod.world_new = MagicMock(return_value="fake_world")  # type: ignore[attr-defined]
    mod.world_open_udp = MagicMock(return_value=True)  # type: ignore[attr-defined]
    mod.world_send_packet = MagicMock(return_value=True)  # type: ignore[attr-defined]
    if wait_event is not None:
        mod.world_wait_for_quit = MagicMock(  # type: ignore[attr-defined]
            side_effect=lambda _w, _b: wait_event.wait()
        )
    else:
        mod.world_wait_for_quit = MagicMock()  # type: ignore[attr-defined]
    mod.world_cleanup = MagicMock()  # type: ignore[attr-defined]
    return mod


class TestEmbeddedProcessProtocol:
    @pytest.fixture(autouse=True)
    def _reset_active_world(self):
        yield
        EmbeddedProcessProtocol._active_world = False

    def test_initial_state_is_offline(self):
        proto = EmbeddedProcessProtocol()
        assert proto.status == BootStatus.OFFLINE

    def test_quit_when_offline_is_noop(self):
        proto = EmbeddedProcessProtocol()
        proto.quit()
        assert proto.status == BootStatus.OFFLINE

    def test_send_packet_when_offline_raises(self):
        proto = EmbeddedProcessProtocol()
        with pytest.raises(RuntimeError, match="not running"):
            proto.send_packet(b"\x00")

    def test_send_msg_when_offline_raises(self):
        proto = EmbeddedProcessProtocol()
        with pytest.raises(RuntimeError, match="not running"):
            proto.send_msg("/test")

    def test_name_stored(self):
        proto = EmbeddedProcessProtocol(name="test-server")
        assert proto.name == "test-server"

    def test_callbacks_stored(self):
        on_boot = MagicMock()
        on_quit = MagicMock()
        on_panic = MagicMock()
        proto = EmbeddedProcessProtocol(
            on_boot_callback=on_boot,
            on_quit_callback=on_quit,
            on_panic_callback=on_panic,
        )
        assert proto.on_boot_callback is on_boot
        assert proto.on_quit_callback is on_quit
        assert proto.on_panic_callback is on_panic

    def test_boot_raises_when_world_already_active(self, monkeypatch):
        mock_scsynth = _make_mock_scsynth_module()
        monkeypatch.setitem(sys.modules, "nanosynth._scsynth", mock_scsynth)
        EmbeddedProcessProtocol._active_world = True
        proto = EmbeddedProcessProtocol()
        with pytest.raises(ServerCannotBoot, match="already running"):
            proto.boot(Options())
        assert proto.status == BootStatus.OFFLINE

    def test_set_reply_callback_none_accepted(self):
        proto = EmbeddedProcessProtocol()
        proto.set_reply_callback(None)
        assert proto._reply_callback is None

    def test_set_reply_callback_stores(self):
        def my_callback(data: bytes) -> None:
            pass

        proto = EmbeddedProcessProtocol()
        proto.set_reply_callback(my_callback)
        assert proto._reply_callback is my_callback


class TestScynthBootLifecycle:
    """Test boot, wait_for_quit, and quit lifecycle with mocked _scsynth module."""

    @pytest.fixture(autouse=True)
    def _reset_active_world(self):
        yield
        EmbeddedProcessProtocol._active_world = False

    @pytest.fixture()
    def wait_event(self):
        return threading.Event()

    @pytest.fixture()
    def mock_mod(self, monkeypatch, wait_event):
        mod = _make_mock_scsynth_module(wait_event=wait_event)
        monkeypatch.setitem(sys.modules, "nanosynth._scsynth", mod)
        return mod

    def _stop(self, proto, wait_event):
        """Release the blocking wait and join the thread."""
        wait_event.set()
        if proto.thread:
            proto.thread.join(timeout=2)

    def test_boot_success(self, mock_mod, wait_event):
        proto = EmbeddedProcessProtocol()
        proto.boot(Options())

        assert proto.status == BootStatus.ONLINE
        assert proto._world == "fake_world"
        assert EmbeddedProcessProtocol._active_world is True
        mock_mod.world_new.assert_called_once()
        mock_mod.world_open_udp.assert_called_once()
        mock_mod.set_print_func.assert_called_once()
        assert proto.boot_future.result() is True
        assert proto.thread is not None
        assert proto.thread.daemon is True
        self._stop(proto, wait_event)

    def test_boot_calls_on_boot_callback(self, mock_mod, wait_event):
        on_boot = MagicMock()
        proto = EmbeddedProcessProtocol(on_boot_callback=on_boot)
        proto.boot(Options())

        on_boot.assert_called_once()
        self._stop(proto, wait_event)

    def test_boot_installs_reply_callback(self, mock_mod, wait_event):
        def my_reply(data: bytes) -> None:
            pass

        proto = EmbeddedProcessProtocol()
        proto.set_reply_callback(my_reply)
        proto.boot(Options())

        mock_mod.set_reply_func.assert_called_once_with(my_reply)
        self._stop(proto, wait_event)

    def test_boot_when_already_booted_is_noop(self, mock_mod, wait_event):
        proto = EmbeddedProcessProtocol()
        proto.boot(Options())
        mock_mod.world_new.assert_called_once()

        # Second boot should be a no-op (status is ONLINE, not OFFLINE)
        proto.boot(Options())
        mock_mod.world_new.assert_called_once()  # not called again
        self._stop(proto, wait_event)

    def test_boot_world_new_failure(self, mock_mod, wait_event):
        mock_mod.world_new.side_effect = RuntimeError("audio driver error")
        proto = EmbeddedProcessProtocol()

        with pytest.raises(ServerCannotBoot, match="audio driver error"):
            proto.boot(Options())

        assert proto.status == BootStatus.OFFLINE
        assert EmbeddedProcessProtocol._active_world is False
        assert proto.boot_future.result() is False

    def test_boot_open_udp_failure(self, mock_mod, wait_event):
        mock_mod.world_open_udp.return_value = False
        proto = EmbeddedProcessProtocol()

        with pytest.raises(ServerCannotBoot, match="World_OpenUDP failed"):
            proto.boot(Options())

        assert proto.status == BootStatus.OFFLINE
        assert EmbeddedProcessProtocol._active_world is False
        mock_mod.world_cleanup.assert_called_once_with("fake_world")

    def test_wait_for_quit_callback(self, mock_mod, wait_event):
        on_quit = MagicMock()
        proto = EmbeddedProcessProtocol(on_quit_callback=on_quit)
        proto.boot(Options())
        proto.status = BootStatus.QUITTING

        wait_event.set()
        proto.thread.join(timeout=2)

        assert proto.status == BootStatus.OFFLINE
        on_quit.assert_called_once()
        assert EmbeddedProcessProtocol._active_world is False
        assert proto._world is None

    def test_wait_for_quit_panic_callback(self, mock_mod, wait_event):
        on_panic = MagicMock()
        proto = EmbeddedProcessProtocol(on_panic_callback=on_panic)
        proto.boot(Options())
        # Status is ONLINE (not QUITTING) when wait loop exits -> panic
        wait_event.set()
        proto.thread.join(timeout=2)

        on_panic.assert_called_once()

    def test_send_packet_when_online(self, mock_mod, wait_event):
        proto = EmbeddedProcessProtocol()
        proto.boot(Options())

        result = proto.send_packet(b"\x00\x00\x00\x00")
        assert result is True
        mock_mod.world_send_packet.assert_called_once_with(
            "fake_world", b"\x00\x00\x00\x00"
        )
        self._stop(proto, wait_event)

    def test_send_msg_when_online(self, mock_mod, wait_event):
        proto = EmbeddedProcessProtocol()
        proto.boot(Options())

        proto.send_msg("/status")
        mock_mod.world_send_packet.assert_called_once()
        sent_data = mock_mod.world_send_packet.call_args[0][1]
        assert b"/status" in sent_data
        self._stop(proto, wait_event)

    def test_set_reply_callback_when_online(self, mock_mod, wait_event):
        proto = EmbeddedProcessProtocol()
        proto.boot(Options())

        def late_callback(data: bytes) -> None:
            pass

        proto.set_reply_callback(late_callback)
        mock_mod.set_reply_func.assert_called_with(late_callback)
        self._stop(proto, wait_event)

    def test_quit_when_online(self, mock_mod, wait_event):
        proto = EmbeddedProcessProtocol()
        proto.boot(Options())
        assert proto.status == BootStatus.ONLINE

        wait_event.set()
        proto.quit()

        assert proto.status == BootStatus.OFFLINE
        assert EmbeddedProcessProtocol._active_world is False

    def test_shutdown_with_dead_thread(self, mock_mod, wait_event):
        proto = EmbeddedProcessProtocol()
        proto.boot(Options())
        wait_event.set()
        proto.thread.join(timeout=1)

        proto._shutdown()
        assert proto.status == BootStatus.OFFLINE
        assert EmbeddedProcessProtocol._active_world is False

    def test_exit_future_set_after_wait(self, mock_mod, wait_event):
        proto = EmbeddedProcessProtocol()
        proto.boot(Options())
        wait_event.set()
        proto.thread.join(timeout=2)

        assert proto.exit_future.result() == 0


class TestSetReplyFunc:
    def test_set_reply_func_none(self):
        from nanosynth._scsynth import set_reply_func  # type: ignore[import-untyped]

        set_reply_func(None)  # should not raise

    def test_set_reply_func_callable(self):
        from nanosynth._scsynth import set_reply_func  # type: ignore[import-untyped]

        def my_func(data: bytes) -> None:
            pass

        set_reply_func(my_func)  # should not raise
        set_reply_func(None)  # cleanup


class TestAddAction:
    def test_values(self):
        assert AddAction.ADD_TO_HEAD == 0
        assert AddAction.ADD_TO_TAIL == 1
        assert AddAction.ADD_BEFORE == 2
        assert AddAction.ADD_AFTER == 3
        assert AddAction.REPLACE == 4

    def test_int_conversion(self):
        assert int(AddAction.ADD_TO_HEAD) == 0
        assert int(AddAction.REPLACE) == 4

    def test_is_int_enum(self):
        # Can be used wherever int is expected
        assert AddAction.ADD_TO_HEAD == 0
        assert AddAction.ADD_TO_TAIL + 1 == 2
