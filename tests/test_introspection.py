"""Tests for server introspection: status, version, query_tree, reset."""

from unittest.mock import MagicMock

import pytest

from nanosynth.exceptions import EngineError
from nanosynth.osc import OscMessage
from nanosynth.scsynth import BootStatus
from nanosynth.server import NodeInfo, Server, ServerStatus, ServerVersion


@pytest.fixture()
def server() -> Server:
    s = Server()
    s._protocol = MagicMock()
    s._protocol.status = BootStatus.ONLINE
    return s


def _auto_reply(server: Server, transform) -> None:
    def side_effect(data: bytes) -> None:
        reply = transform(OscMessage.from_datagram(data))
        if reply is not None:
            server._dispatch_reply(reply.to_datagram())

    server._protocol.send_packet.side_effect = side_effect


class TestStatus:
    def test_parses_status_reply(self, server: Server) -> None:
        _auto_reply(
            server,
            lambda m: (
                OscMessage(
                    "/status.reply", 1, 10, 3, 2, 5, 0.12, 0.34, 48000.0, 48000.0
                )
                if m.address == "/status"
                else None
            ),
        )
        st = server.status(timeout=2.0)
        assert isinstance(st, ServerStatus)
        assert (st.num_ugens, st.num_synths, st.num_groups, st.num_synthdefs) == (
            10,
            3,
            2,
            5,
        )
        assert st.average_cpu == pytest.approx(0.12)
        assert st.peak_cpu == pytest.approx(0.34)
        assert st.actual_sample_rate == pytest.approx(48000.0)

    def test_timeout_raises(self, server: Server) -> None:
        with pytest.raises(EngineError, match="status"):
            server.status(timeout=0.05)


class TestVersion:
    def test_parses_version_reply(self, server: Server) -> None:
        _auto_reply(
            server,
            lambda m: (
                OscMessage("/version.reply", "scsynth", 3, 14, ".1", "dev", "abc123")
                if m.address == "/version"
                else None
            ),
        )
        v = server.version(timeout=2.0)
        assert isinstance(v, ServerVersion)
        assert v.program == "scsynth"
        assert (v.major, v.minor) == (3, 14)
        assert v.commit == "abc123"

    def test_timeout_raises(self, server: Server) -> None:
        with pytest.raises(EngineError, match="version"):
            server.version(timeout=0.05)


class TestQueryTree:
    def test_parses_nested_tree_with_controls(self, server: Server) -> None:
        # flag=1; root group 0 with 1 child: group 1 with 1 child:
        # synth 1001 "test" with control freq=440.0.
        reply = OscMessage(
            "/g_queryTree.reply",
            1,  # controls included
            0,  # queried group id
            1,  # root child count
            1,  # node id
            1,  # child count (group)
            1001,  # node id
            -1,  # synth
            "test",  # synthdef
            1,  # numControls
            "freq",
            440.0,
        )
        _auto_reply(server, lambda m: reply if m.address == "/g_queryTree" else None)
        root = server.query_tree(0, controls=True, timeout=2.0)
        assert isinstance(root, NodeInfo)
        assert root.node_id == 0 and root.is_group
        grp = root.children[0]
        assert grp.node_id == 1 and grp.is_group
        synth = grp.children[0]
        assert synth.node_id == 1001
        assert not synth.is_group
        assert synth.synthdef == "test"
        assert synth.controls == {"freq": 440.0}

    def test_parses_synth_without_controls(self, server: Server) -> None:
        reply = OscMessage("/g_queryTree.reply", 0, 0, 1, 1001, -1, "sine")
        _auto_reply(server, lambda m: reply if m.address == "/g_queryTree" else None)
        root = server.query_tree(0, timeout=2.0)
        synth = root.children[0]
        assert synth.synthdef == "sine"
        assert synth.controls == {}

    def test_matches_queried_group_id(self, server: Server) -> None:
        # A reply for a different group must not resolve the wait.
        _auto_reply(
            server,
            lambda m: (
                OscMessage("/g_queryTree.reply", 0, 99, 0)
                if m.address == "/g_queryTree"
                else None
            ),
        )
        with pytest.raises(EngineError):
            server.query_tree(0, timeout=0.1)

    def test_empty_group(self, server: Server) -> None:
        _auto_reply(
            server,
            lambda m: (
                OscMessage("/g_queryTree.reply", 0, 0, 0)
                if m.address == "/g_queryTree"
                else None
            ),
        )
        root = server.query_tree(0, timeout=2.0)
        assert root.children == []


class TestReset:
    def test_sends_freeall_clearsched_gnew(self, server: Server) -> None:
        server.reset()
        addresses = [
            OscMessage.from_datagram(c[0][0]).address
            for c in server._protocol.send_packet.call_args_list
        ]
        assert addresses == ["/g_freeAll", "/clearSched", "/g_new"]

    def test_recreates_default_group(self, server: Server) -> None:
        server.reset()
        gnew = OscMessage.from_datagram(
            server._protocol.send_packet.call_args_list[-1][0][0]
        )
        assert gnew.address == "/g_new"
        assert gnew.contents[0] == 1  # default group id

    def test_resets_node_allocator(self, server: Server) -> None:
        server.next_node_id()
        server.next_node_id()
        server.reset()
        assert server.next_node_id() == 1000

    def test_leaves_buffer_allocator_intact(self, server: Server) -> None:
        buf = server.alloc_buffer(1024)
        server.reset()
        # Buffers are not freed by /g_freeAll, so the allocation stands.
        assert buf in server._allocated_buffers


class TestDumpTree:
    def test_sends_g_dumptree(self, server: Server) -> None:
        server.dump_tree(0, controls=True)
        msg = OscMessage.from_datagram(server._protocol.send_packet.call_args[0][0])
        assert msg.address == "/g_dumpTree"
        assert msg.contents == (0, 1)


class TestExports:
    def test_types_exported(self) -> None:
        import nanosynth

        for name in ("ServerStatus", "ServerVersion", "NodeInfo"):
            assert name in nanosynth.__all__
            assert hasattr(nanosynth, name)
