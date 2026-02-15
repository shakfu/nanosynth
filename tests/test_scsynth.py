"""Basic tests for scsynth module."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from nanosynth.enums import AddAction
from nanosynth.scsynth import (
    BootStatus,
    EmbeddedProcessProtocol,
    Options,
    ServerCannotBoot,
    _options_to_world_kwargs,
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


class TestBootStatus:
    def test_values(self):
        assert BootStatus.OFFLINE == 0
        assert BootStatus.BOOTING == 1
        assert BootStatus.ONLINE == 2
        assert BootStatus.QUITTING == 3


class TestScynthImport:
    def test_import_scsynth(self):
        from nanosynth import _scsynth  # noqa: F401


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
        mock_scsynth = ModuleType("nanosynth._scsynth")
        mock_scsynth.set_print_func = MagicMock()  # type: ignore[attr-defined]
        mock_scsynth.world_new = MagicMock()  # type: ignore[attr-defined]
        mock_scsynth.world_open_udp = MagicMock(return_value=True)  # type: ignore[attr-defined]
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
