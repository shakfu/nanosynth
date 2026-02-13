"""Basic tests for scsynth module."""

import pytest

from nanosynth.scsynth import BootStatus, Options, _options_to_world_kwargs


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
    @pytest.mark.xfail(reason="requires build with NANOSYNTH_EMBED_SCSYNTH=ON")
    def test_import_scsynth(self):
        from nanosynth import _scsynth  # noqa: F401
