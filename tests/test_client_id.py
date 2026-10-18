"""Tests for Options.client_id: sharing one engine with other clients."""

from unittest.mock import MagicMock

import pytest

from nanosynth.osc import OscMessage
from nanosynth.scsynth import BootStatus, Options
from nanosynth.server import Server
from nanosynth.synthdef import SynthDefBuilder
from nanosynth.ugens import Out, SinOsc


def _mocked(options: Options) -> Server:
    s = Server(options)
    s._protocol = MagicMock()
    s._protocol.status = BootStatus.ONLINE
    return s


def _sent(server: Server) -> list[tuple]:
    return [
        tuple(OscMessage.from_datagram(c.args[0]).to_list())
        for c in server._protocol.send_packet.call_args_list
    ]


class TestOptions:
    def test_default_is_none(self) -> None:
        assert Options().client_id is None
        assert Options().default_group_id == 1

    @pytest.mark.parametrize("cid, group", [(0, 1), (1, 0x04000001), (3, 0x0C000001)])
    def test_default_group_id(self, cid: int, group: int) -> None:
        # sclang: nodeAllocator.numIDs * clientID + 1, numIDs = 2 ** 26
        assert Options(client_id=cid, maximum_logins=4).default_group_id == group

    @pytest.mark.parametrize("cid", [-1, 4, 32])
    def test_rejects_out_of_range(self, cid: int) -> None:
        with pytest.raises(ValueError, match="client_id"):
            Options(client_id=cid, maximum_logins=4 if cid != 32 else 64)


class TestSlices:
    """Slices follow sclang 3.14.1 Server.newBusAllocators/newBufferAllocators."""

    OPTS = dict(
        maximum_logins=4,
        buffer_count=1024,
        control_bus_channel_count=16384,
        audio_bus_channel_count=1024,
        input_bus_channel_count=2,
        output_bus_channel_count=2,
    )

    def test_none_uses_whole_range(self) -> None:
        s = Server(Options(**self.OPTS))
        assert s._buffer_allocator.allocate() == 0
        assert s.next_node_id() == 1000

    @pytest.mark.parametrize("cid", [0, 1, 3])
    def test_client_slices(self, cid: int) -> None:
        s = Server(Options(client_id=cid, **self.OPTS))
        assert s._buffer_allocator.allocate() == 256 * cid
        assert s._control_bus_allocator.allocate() == 4096 * cid
        # (1024 - 4) div 4 = 255 private audio channels per client, after I/O
        assert s._audio_bus_allocator.allocate() == 4 + 255 * cid
        assert s.next_node_id() == (cid << 26) | 1000

    def test_slice_is_bounded(self) -> None:
        s = Server(Options(client_id=1, **self.OPTS))
        s._buffer_allocator.allocate(256)
        with pytest.raises(Exception, match="exhausted"):
            s._buffer_allocator.allocate()

    def test_node_ids_wrap_inside_slice(self) -> None:
        s = Server(Options(client_id=2, **self.OPTS))
        alloc = s._node_allocator
        alloc._next = (2 << 26) + 0x03FFFFFF
        assert alloc.allocate() == (2 << 26) + 0x03FFFFFF
        assert alloc.allocate() == (2 << 26) | 1000


class TestPlacement:
    def test_synth_defaults_to_client_group(self) -> None:
        s = _mocked(Options(client_id=1, maximum_logins=4))
        s.synth("sine")
        assert _sent(s)[-1][:5] == ("/s_new", "sine", (1 << 26) | 1000, 0, 0x04000001)

    def test_synth_default_group_without_client_id(self) -> None:
        s = _mocked(Options())
        s.synth("sine")
        assert _sent(s)[-1][4] == 1

    def test_explicit_target_wins(self) -> None:
        s = _mocked(Options(client_id=1, maximum_logins=4))
        s.synth("sine", target=0)
        assert _sent(s)[-1][4] == 0

    def test_synthdef_play_uses_default_group(self) -> None:
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="t")
        s = _mocked(Options(client_id=1, maximum_logins=4))
        sd.play(s)
        assert _sent(s)[-1][4] == 0x04000001

    def test_boot_creates_client_group(self) -> None:
        s = Server(Options(client_id=1, maximum_logins=4), protocol=MagicMock())
        s._protocol.status = BootStatus.ONLINE
        s.boot()
        assert ("/g_new", 0x04000001, 0, 0) in _sent(s)


class TestReset:
    def test_shared_reset_frees_only_own_group(self) -> None:
        s = _mocked(Options(client_id=1, maximum_logins=4))
        s.reset()
        sent = _sent(s)
        assert sent == [("/g_freeAll", 0x04000001)]

    def test_sole_client_reset_unchanged(self) -> None:
        s = _mocked(Options())
        s.reset()
        assert _sent(s) == [("/g_freeAll", 0), ("/clearSched",), ("/g_new", 1, 0, 0)]


class TestNotify:
    def test_notify_requests_client_id(self) -> None:
        s = _mocked(Options(client_id=2, maximum_logins=4))
        s.enable_notifications(timeout=0.01)
        assert ("/notify", 1, 2) in _sent(s)

    def test_notify_without_client_id(self) -> None:
        s = _mocked(Options())
        s.enable_notifications(timeout=0.01)
        assert ("/notify", 1) in _sent(s)


class TestForeignNodes:
    def test_on_free_ignores_other_clients_nodes(self) -> None:
        s = _mocked(Options(client_id=0, maximum_logins=4))
        node = s.synth("sine")
        fired: list[int] = []
        node.on_free(lambda e: fired.append(e.node_id))
        foreign = (1 << 26) | 1000
        s._dispatch_reply(OscMessage("/n_end", foreign, 1, -1, -1, 0).to_datagram())
        assert fired == []
        s._dispatch_reply(OscMessage("/n_end", int(node), 1, -1, -1, 0).to_datagram())
        assert fired == [int(node)]
