"""Tests for supernova module."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from nanosynth.scsynth import BootStatus, Options, ServerCannotBoot
from nanosynth.supernova import (
    EmbeddedSupernovaProtocol,
    _options_to_supernova_kwargs,
)


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
        mock_supernova = ModuleType("nanosynth._supernova")
        mock_supernova.set_print_func = MagicMock()  # type: ignore[attr-defined]
        mock_supernova.supernova_new = MagicMock()  # type: ignore[attr-defined]
        mock_supernova.set_reply_func = MagicMock()  # type: ignore[attr-defined]
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


class TestSupernovaExport:
    def test_importable_from_package(self):
        from nanosynth import EmbeddedSupernovaProtocol

        assert EmbeddedSupernovaProtocol is not None

    def test_in_all(self):
        import nanosynth

        assert "EmbeddedSupernovaProtocol" in nanosynth.__all__
