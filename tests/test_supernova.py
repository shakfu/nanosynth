"""Tests for supernova module."""

import sys
import threading
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from nanosynth.scsynth import BootStatus, Options, ServerCannotBoot
from nanosynth.supernova import (
    EmbeddedSupernovaProtocol,
    _options_to_supernova_kwargs,
)


def _make_mock_supernova_module(
    run_event: threading.Event | None = None,
) -> ModuleType:
    """Create a mock _supernova C extension module.

    If run_event is provided, supernova_run blocks until the event is set,
    simulating the real blocking behavior.
    """
    mod = ModuleType("nanosynth._supernova")
    mod.set_print_func = MagicMock()  # type: ignore[attr-defined]
    mod.set_reply_func = MagicMock()  # type: ignore[attr-defined]
    mod.supernova_new = MagicMock(return_value="fake_server")  # type: ignore[attr-defined]
    if run_event is not None:
        mod.supernova_run = MagicMock(side_effect=lambda _: run_event.wait())  # type: ignore[attr-defined]
    else:
        mod.supernova_run = MagicMock()  # type: ignore[attr-defined]
    mod.supernova_send_packet = MagicMock(return_value=True)  # type: ignore[attr-defined]
    mod.supernova_terminate = MagicMock()  # type: ignore[attr-defined]
    mod.supernova_cleanup = MagicMock()  # type: ignore[attr-defined]
    return mod


class TestOptionsToSupernovaKwargs:
    def test_default_mapping(self):
        opts = Options()
        kwargs = _options_to_supernova_kwargs(opts)
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
        assert kwargs["realtime_memory_size"] == 8192
        assert kwargs["load_graph_defs"] == 1
        assert kwargs["memory_locking"] is False
        assert kwargs["verbosity"] == 0
        assert kwargs["shared_memory_id"] == 57110  # port
        assert kwargs["threads"] == 0  # 0 = use hardware_concurrency

    def test_scsynth_specific_keys_removed(self):
        opts = Options()
        kwargs = _options_to_supernova_kwargs(opts)
        assert "rendezvous" not in kwargs
        assert "realtime" not in kwargs
        assert "max_logins" not in kwargs

    def test_optional_fields(self):
        opts = Options(
            sample_rate=48000,
            hardware_buffer_size=512,
            password="secret",
            input_device="Built-in",
            output_device="Built-in",
        )
        kwargs = _options_to_supernova_kwargs(opts)
        assert kwargs["preferred_sample_rate"] == 48000
        assert kwargs["preferred_hardware_buffer_size"] == 512
        assert kwargs["password"] == "secret"
        assert kwargs["in_device_name"] == "Built-in"
        assert kwargs["out_device_name"] == "Built-in"

    def test_load_synthdefs_false(self):
        opts = Options(load_synthdefs=False)
        kwargs = _options_to_supernova_kwargs(opts)
        assert kwargs["load_graph_defs"] == 0

    def test_custom_options(self):
        opts = Options(
            audio_bus_channel_count=2048,
            block_size=128,
            port=57211,
            memory_size=16384,
        )
        kwargs = _options_to_supernova_kwargs(opts)
        assert kwargs["num_audio_bus_channels"] == 2048
        assert kwargs["block_size"] == 128
        assert kwargs["shared_memory_id"] == 57211
        assert kwargs["realtime_memory_size"] == 16384

    def test_hardware_buffer_size_is_int(self):
        opts = Options(hardware_buffer_size=256)
        kwargs = _options_to_supernova_kwargs(opts)
        assert isinstance(kwargs["preferred_hardware_buffer_size"], int)
        assert kwargs["preferred_hardware_buffer_size"] == 256

    def test_load_graph_defs_is_int(self):
        opts = Options(load_synthdefs=True)
        kwargs = _options_to_supernova_kwargs(opts)
        assert isinstance(kwargs["load_graph_defs"], int)

    def test_stream_masks(self):
        opts = Options(input_stream_mask="0011", output_stream_mask="1100")
        kwargs = _options_to_supernova_kwargs(opts)
        assert kwargs["input_streams_enabled"] == "0011"
        assert kwargs["output_streams_enabled"] == "1100"

    def test_restricted_path(self):
        opts = Options(restricted_path="/tmp/sc")
        kwargs = _options_to_supernova_kwargs(opts)
        assert kwargs["restricted_path"] == "/tmp/sc"

    def test_safety_clip(self):
        opts = Options(safety_clip="inf")
        kwargs = _options_to_supernova_kwargs(opts)
        assert kwargs["safety_clip_threshold"] == float("inf")


class TestEmbeddedSupernovaProtocol:
    @pytest.fixture(autouse=True)
    def _reset_active(self):
        yield
        EmbeddedSupernovaProtocol._active = False

    def test_initial_state_is_offline(self):
        proto = EmbeddedSupernovaProtocol()
        assert proto.status == BootStatus.OFFLINE

    def test_quit_when_offline_is_noop(self):
        proto = EmbeddedSupernovaProtocol()
        proto.quit()
        assert proto.status == BootStatus.OFFLINE

    def test_send_packet_when_offline_raises(self):
        proto = EmbeddedSupernovaProtocol()
        with pytest.raises(RuntimeError, match="not running"):
            proto.send_packet(b"\x00")

    def test_send_msg_when_offline_raises(self):
        proto = EmbeddedSupernovaProtocol()
        with pytest.raises(RuntimeError, match="not running"):
            proto.send_msg("/test")

    def test_name_stored(self):
        proto = EmbeddedSupernovaProtocol(name="test-supernova")
        assert proto.name == "test-supernova"

    def test_callbacks_stored(self):
        on_boot = MagicMock()
        on_quit = MagicMock()
        on_panic = MagicMock()
        proto = EmbeddedSupernovaProtocol(
            on_boot_callback=on_boot,
            on_quit_callback=on_quit,
            on_panic_callback=on_panic,
        )
        assert proto.on_boot_callback is on_boot
        assert proto.on_quit_callback is on_quit
        assert proto.on_panic_callback is on_panic

    def test_boot_raises_when_already_active(self, monkeypatch):
        mock_supernova = _make_mock_supernova_module()
        monkeypatch.setitem(sys.modules, "nanosynth._supernova", mock_supernova)
        EmbeddedSupernovaProtocol._active = True
        proto = EmbeddedSupernovaProtocol()
        with pytest.raises(ServerCannotBoot, match="already running"):
            proto.boot(Options())
        assert proto.status == BootStatus.OFFLINE

    def test_set_reply_callback_none_accepted(self):
        proto = EmbeddedSupernovaProtocol()
        proto.set_reply_callback(None)
        assert proto._reply_callback is None

    def test_set_reply_callback_stores(self):
        def my_callback(data: bytes) -> None:
            pass

        proto = EmbeddedSupernovaProtocol()
        proto.set_reply_callback(my_callback)
        assert proto._reply_callback is my_callback


class TestSupernovaBootLifecycle:
    """Test boot, run, and quit lifecycle with mocked _supernova module."""

    @pytest.fixture(autouse=True)
    def _reset_active(self):
        yield
        EmbeddedSupernovaProtocol._active = False

    @pytest.fixture()
    def run_event(self):
        return threading.Event()

    @pytest.fixture()
    def mock_mod(self, monkeypatch, run_event):
        mod = _make_mock_supernova_module(run_event=run_event)
        monkeypatch.setitem(sys.modules, "nanosynth._supernova", mod)
        return mod

    def _stop(self, proto, run_event):
        """Release the blocking run and join the thread."""
        run_event.set()
        if proto.thread:
            proto.thread.join(timeout=2)

    def test_boot_success(self, mock_mod, run_event):
        proto = EmbeddedSupernovaProtocol()
        proto.boot(Options())

        assert proto.status == BootStatus.ONLINE
        assert proto._server == "fake_server"
        assert EmbeddedSupernovaProtocol._active is True
        mock_mod.supernova_new.assert_called_once()
        mock_mod.set_print_func.assert_called_once()
        assert proto.boot_future.result() is True
        assert proto.thread is not None
        assert proto.thread.daemon is True

        self._stop(proto, run_event)

    def test_boot_calls_on_boot_callback(self, mock_mod, run_event):
        on_boot = MagicMock()
        proto = EmbeddedSupernovaProtocol(on_boot_callback=on_boot)
        proto.boot(Options())

        on_boot.assert_called_once()
        self._stop(proto, run_event)

    def test_boot_installs_reply_callback(self, mock_mod, run_event):
        def my_reply(data: bytes) -> None:
            pass

        proto = EmbeddedSupernovaProtocol()
        proto.set_reply_callback(my_reply)
        proto.boot(Options())

        mock_mod.set_reply_func.assert_called_once_with(my_reply)
        self._stop(proto, run_event)

    def test_boot_when_already_booted_is_noop(self, mock_mod, run_event):
        proto = EmbeddedSupernovaProtocol()
        proto.boot(Options())
        mock_mod.supernova_new.assert_called_once()

        # Second boot should be a no-op (status is ONLINE, not OFFLINE)
        proto.boot(Options())
        mock_mod.supernova_new.assert_called_once()  # not called again
        self._stop(proto, run_event)

    def test_boot_failure_resets_state(self, mock_mod, run_event):
        mock_mod.supernova_new.side_effect = RuntimeError("audio device error")
        proto = EmbeddedSupernovaProtocol()

        with pytest.raises(ServerCannotBoot, match="audio device error"):
            proto.boot(Options())

        assert proto.status == BootStatus.OFFLINE
        assert EmbeddedSupernovaProtocol._active is False
        assert proto.boot_future.result() is False

    def test_run_loop_quit_callback(self, mock_mod, run_event):
        on_quit = MagicMock()
        proto = EmbeddedSupernovaProtocol(on_quit_callback=on_quit)
        proto.boot(Options())
        proto.status = BootStatus.QUITTING

        # Release the blocking run
        run_event.set()
        proto.thread.join(timeout=2)

        assert proto.status == BootStatus.OFFLINE
        on_quit.assert_called_once()
        assert EmbeddedSupernovaProtocol._active is False

    def test_run_loop_panic_callback(self, mock_mod, run_event):
        on_panic = MagicMock()
        proto = EmbeddedSupernovaProtocol(on_panic_callback=on_panic)
        proto.boot(Options())
        # Status is ONLINE (not QUITTING) when run loop exits -> panic
        run_event.set()
        proto.thread.join(timeout=2)

        on_panic.assert_called_once()

    def test_send_packet_when_online(self, mock_mod, run_event):
        proto = EmbeddedSupernovaProtocol()
        proto.boot(Options())

        result = proto.send_packet(b"\x00\x00\x00\x00")
        assert result is True
        mock_mod.supernova_send_packet.assert_called_once_with(
            "fake_server", b"\x00\x00\x00\x00"
        )
        self._stop(proto, run_event)

    def test_send_msg_when_online(self, mock_mod, run_event):
        proto = EmbeddedSupernovaProtocol()
        proto.boot(Options())

        proto.send_msg("/status")
        mock_mod.supernova_send_packet.assert_called_once()
        # Verify it sent an OSC-encoded message
        sent_data = mock_mod.supernova_send_packet.call_args[0][1]
        assert b"/status" in sent_data
        self._stop(proto, run_event)

    def test_set_reply_callback_when_online(self, mock_mod, run_event):
        proto = EmbeddedSupernovaProtocol()
        proto.boot(Options())

        def late_callback(data: bytes) -> None:
            pass

        proto.set_reply_callback(late_callback)
        mock_mod.set_reply_func.assert_called_with(late_callback)
        self._stop(proto, run_event)

    def test_quit_when_online(self, mock_mod, run_event):
        proto = EmbeddedSupernovaProtocol()
        proto.boot(Options())
        assert proto.status == BootStatus.ONLINE

        # Release run loop before quit so _shutdown().thread.join() works
        run_event.set()
        proto.quit()

        mock_mod.supernova_terminate.assert_called_once_with("fake_server")
        mock_mod.supernova_cleanup.assert_called_once_with("fake_server")
        assert proto.status == BootStatus.OFFLINE
        assert proto._server is None
        assert EmbeddedSupernovaProtocol._active is False

    def test_shutdown_cleans_up_server(self, mock_mod, run_event):
        proto = EmbeddedSupernovaProtocol()
        proto.boot(Options())
        run_event.set()
        proto.thread.join(timeout=1)

        proto._shutdown()

        mock_mod.supernova_cleanup.assert_called_once_with("fake_server")
        assert proto._server is None
        assert EmbeddedSupernovaProtocol._active is False

    def test_shutdown_with_no_server_is_safe(self, mock_mod, run_event):
        proto = EmbeddedSupernovaProtocol()
        proto._server = None
        proto.thread = None
        proto._shutdown()
        mock_mod.supernova_cleanup.assert_not_called()

    def test_exit_future_set_after_run(self, mock_mod, run_event):
        proto = EmbeddedSupernovaProtocol()
        proto.boot(Options())
        run_event.set()
        proto.thread.join(timeout=2)

        assert proto.exit_future.result() == 0


class TestServerWithSupernovaProtocol:
    def test_server_accepts_supernova_protocol(self):
        from nanosynth.server import Server

        proto = EmbeddedSupernovaProtocol()
        server = Server(protocol=proto)
        assert server._protocol is proto
        assert not server.is_running

    def test_server_defaults_to_scsynth(self):
        from nanosynth.scsynth import EmbeddedProcessProtocol
        from nanosynth.server import Server

        server = Server()
        assert isinstance(server._protocol, EmbeddedProcessProtocol)

    def test_server_quit_skips_quit_osc_for_supernova(self):
        """Server.quit() should NOT send /quit OSC for supernova protocol."""
        from nanosynth.server import Server

        proto = EmbeddedSupernovaProtocol()
        proto.status = BootStatus.ONLINE
        server = Server(protocol=proto)

        with (
            patch.object(server, "send_msg") as mock_send,
            patch.object(proto, "quit") as mock_quit,
        ):
            server.quit()
            # /quit should NOT be sent for supernova
            mock_send.assert_not_called()
            mock_quit.assert_called_once()

    def test_server_quit_sends_quit_osc_for_scsynth(self):
        """Server.quit() should send /quit OSC for scsynth protocol."""
        from nanosynth.scsynth import EmbeddedProcessProtocol
        from nanosynth.server import Server

        proto = EmbeddedProcessProtocol()
        proto.status = BootStatus.ONLINE
        server = Server(protocol=proto)

        with (
            patch.object(server, "send_msg") as mock_send,
            patch.object(proto, "quit") as mock_quit,
        ):
            server.quit()
            mock_send.assert_called_once_with("/quit")
            mock_quit.assert_called_once()


class TestSupernovaExport:
    def test_importable_from_package(self):
        from nanosynth import EmbeddedSupernovaProtocol

        assert EmbeddedSupernovaProtocol is not None

    def test_in_all(self):
        import nanosynth

        assert "EmbeddedSupernovaProtocol" in nanosynth.__all__
