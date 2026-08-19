"""Tests for node lifecycle notifications (/notify, /n_go, /n_end, ...)."""

import threading
import time
from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from nanosynth.osc import OscMessage
from nanosynth.scsynth import BootStatus
from nanosynth.server import NodeEvent, Server


def _wait_until(
    predicate: Callable[[], object], timeout: float = 2.0, interval: float = 0.005
) -> bool:
    """Poll ``predicate`` until truthy or timeout. Used instead of a fixed sleep
    so dispatching a reply cannot race the waiter thread's registration (M18)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


@pytest.fixture()
def server() -> Server:
    s = Server()
    s._protocol = MagicMock()
    s._protocol.status = BootStatus.ONLINE
    return s


def _auto_notify(server: Server) -> None:
    """Reply ``/done /notify`` whenever a ``/notify`` command is sent."""

    def side_effect(data: bytes) -> None:
        msg = OscMessage.from_datagram(data)
        if msg.address == "/notify":
            server._dispatch_reply(OscMessage("/done", "/notify", 0, 1).to_datagram())

    server._protocol.send_packet.side_effect = side_effect


def _sent_addresses(server: Server) -> list[str]:
    return [
        str(OscMessage.from_datagram(c[0][0]).address)
        for c in server._protocol.send_packet.call_args_list
    ]


class TestEnableDisable:
    def test_enable_sends_notify_1(self, server: Server) -> None:
        _auto_notify(server)
        server.enable_notifications()
        assert server._notifications_enabled is True
        notify = [
            OscMessage.from_datagram(c[0][0])
            for c in server._protocol.send_packet.call_args_list
            if OscMessage.from_datagram(c[0][0]).address == "/notify"
        ]
        assert notify and notify[0].contents[0] == 1

    def test_enable_is_idempotent(self, server: Server) -> None:
        _auto_notify(server)
        server.enable_notifications()
        server.enable_notifications()
        assert _sent_addresses(server).count("/notify") == 1

    def test_disable_sends_notify_0(self, server: Server) -> None:
        _auto_notify(server)
        server.enable_notifications()
        server.disable_notifications()
        assert server._notifications_enabled is False
        last = OscMessage.from_datagram(
            server._protocol.send_packet.call_args_list[-1][0][0]
        )
        assert last.address == "/notify" and last.contents[0] == 0

    def test_boot_resets_enabled_flag(self, server: Server) -> None:
        server._notifications_enabled = True
        server.boot()  # mock protocol
        assert server._notifications_enabled is False


class TestParsing:
    def test_synth_event(self, server: Server) -> None:
        _auto_notify(server)
        got: list[NodeEvent] = []
        server.on_node(got.append)
        server._dispatch_reply(OscMessage("/n_go", 1001, 1, -1, -1, 0).to_datagram())
        server._dispatch_reply(OscMessage("/n_end", 1001, 1, -1, -1, 0).to_datagram())
        assert [e.action for e in got] == ["go", "end"]
        assert got[0].node_id == 1001
        assert got[0].parent_group_id == 1
        assert got[0].is_group is False
        assert got[0].head_node_id is None

    def test_group_event_has_head_tail(self, server: Server) -> None:
        _auto_notify(server)
        got: list[NodeEvent] = []
        server.on_node(got.append)
        server._dispatch_reply(
            OscMessage("/n_go", 1, 0, -1, -1, 1, 1001, 1002).to_datagram()
        )
        e = got[0]
        assert e.is_group is True
        assert e.head_node_id == 1001
        assert e.tail_node_id == 1002

    def test_all_actions(self, server: Server) -> None:
        _auto_notify(server)
        got: list[NodeEvent] = []
        server.on_node(got.append)
        for address in ("/n_go", "/n_end", "/n_off", "/n_on", "/n_move"):
            server._dispatch_reply(OscMessage(address, 1, 0, -1, -1, 0).to_datagram())
        assert [e.action for e in got] == ["go", "end", "off", "on", "move"]


class TestHandlers:
    def test_remove_unregistered_is_noop(self, server: Server) -> None:
        _auto_notify(server)
        got: list[NodeEvent] = []
        server.on_node(got.append)
        server.remove_node_handler(lambda e: None)  # never registered -> no-op
        # The original handler is still registered:
        server._dispatch_reply(OscMessage("/n_go", 1, 0, -1, -1, 0).to_datagram())
        assert len(got) == 1

    def test_removed_handler_stops_receiving(self, server: Server) -> None:
        _auto_notify(server)
        got: list[NodeEvent] = []
        cb = got.append
        server.on_node(cb)
        server.remove_node_handler(cb)
        server._dispatch_reply(OscMessage("/n_go", 1, 0, -1, -1, 0).to_datagram())
        assert got == []

    def test_handler_exception_isolated(self, server: Server) -> None:
        _auto_notify(server)
        good: list[NodeEvent] = []

        def boom(event: NodeEvent) -> None:
            raise RuntimeError("handler error")

        server.on_node(boom)
        server.on_node(good.append)
        server._dispatch_reply(OscMessage("/n_go", 1, 0, -1, -1, 0).to_datagram())
        assert len(good) == 1  # the bad handler did not block the good one


class TestWaitForNodeFree:
    def test_returns_true_on_end(self, server: Server) -> None:
        _auto_notify(server)
        server.enable_notifications()
        result: dict[str, bool] = {}

        def waiter() -> None:
            result["r"] = server.wait_for_node_free(1001, timeout=2.0)

        t = threading.Thread(target=waiter)
        t.start()
        # Wait until the waiter has registered before dispatching, so the reply
        # cannot arrive first and be missed on slow CI (M18).
        assert _wait_until(lambda: server._pending_replies.get("/n_end"))
        server._dispatch_reply(OscMessage("/n_end", 1001, 1, -1, -1, 0).to_datagram())
        t.join(timeout=2.0)
        assert result["r"] is True

    def test_timeout_returns_false(self, server: Server) -> None:
        _auto_notify(server)
        server.enable_notifications()
        assert server.wait_for_node_free(1001, timeout=0.05) is False

    def test_ignores_other_nodes(self, server: Server) -> None:
        _auto_notify(server)
        server.enable_notifications()
        result: dict[str, bool] = {}

        def waiter() -> None:
            result["r"] = server.wait_for_node_free(1001, timeout=0.3)

        t = threading.Thread(target=waiter)
        t.start()
        # Wait until the waiter has registered before dispatching, so the reply
        # cannot arrive first and be missed on slow CI (M18).
        assert _wait_until(lambda: server._pending_replies.get("/n_end"))
        # A different node ending must not resolve the wait.
        server._dispatch_reply(OscMessage("/n_end", 2002, 1, -1, -1, 0).to_datagram())
        t.join(timeout=1.0)
        assert result["r"] is False


class TestSynthHelpers:
    def test_synth_wait_free_delegates(self, server: Server) -> None:
        _auto_notify(server)
        node = server.synth("x")
        server.enable_notifications()
        result: dict[str, bool] = {}

        def waiter() -> None:
            result["r"] = node.wait_free(timeout=2.0)

        t = threading.Thread(target=waiter)
        t.start()
        # Wait until the waiter has registered before dispatching, so the reply
        # cannot arrive first and be missed on slow CI (M18).
        assert _wait_until(lambda: server._pending_replies.get("/n_end"))
        server._dispatch_reply(
            OscMessage("/n_end", int(node), 1, -1, -1, 0).to_datagram()
        )
        t.join(timeout=2.0)
        assert result["r"] is True

    def test_synth_on_free_fires_once(self, server: Server) -> None:
        _auto_notify(server)
        node = server.synth("x")
        nid = int(node)
        fired: list[int] = []
        node.on_free(lambda e: fired.append(e.node_id))
        # Dispatch /n_end twice; the one-shot handler must fire exactly once.
        for _ in range(2):
            server._dispatch_reply(
                OscMessage("/n_end", nid, 1, -1, -1, 0).to_datagram()
            )
        assert fired == [nid]


def test_node_event_exported() -> None:
    import nanosynth

    assert "NodeEvent" in nanosynth.__all__
    assert hasattr(nanosynth, "NodeEvent")
