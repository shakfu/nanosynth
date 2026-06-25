"""Tests for Server.sync(), reply matchers, and waiter cleanup."""

from unittest.mock import MagicMock

import pytest

from nanosynth.osc import OscMessage
from nanosynth.scsynth import BootStatus
from nanosynth.server import Server


@pytest.fixture()
def server() -> Server:
    s = Server()
    s._protocol = MagicMock()
    s._protocol.status = BootStatus.ONLINE
    return s


def _auto_reply(server: Server, reply_address: str, transform) -> None:
    """Make send_packet synchronously dispatch a reply for each sent message.

    ``transform(msg)`` returns an OscMessage to dispatch back, or None.
    """

    def side_effect(data: bytes) -> None:
        msg = OscMessage.from_datagram(data)
        reply = transform(msg)
        if reply is not None:
            server._dispatch_reply(reply.to_datagram())

    server._protocol.send_packet.side_effect = side_effect


class TestSync:
    def test_sync_returns_true_when_synced(self, server: Server) -> None:
        _auto_reply(
            server,
            "/synced",
            lambda m: (
                OscMessage("/synced", m.contents[0]) if m.address == "/sync" else None
            ),
        )
        assert server.sync(timeout=2.0) is True

    def test_sync_sends_unique_ids(self, server: Server) -> None:
        seen: list[int] = []
        _auto_reply(
            server,
            "/synced",
            lambda m: (
                seen.append(m.contents[0]) or OscMessage("/synced", m.contents[0])
                if m.address == "/sync"
                else None
            ),
        )
        server.sync(timeout=2.0)
        server.sync(timeout=2.0)
        assert len(seen) == 2 and seen[0] != seen[1]

    def test_sync_returns_false_on_timeout(self, server: Server) -> None:
        # No reply path (default mock): sync should time out and return False.
        assert server.sync(timeout=0.05) is False

    def test_sync_ignores_mismatched_id(self, server: Server) -> None:
        # Reply with the wrong sync id; the matcher must reject it, so sync
        # times out rather than resolving on an unrelated /synced.
        _auto_reply(
            server,
            "/synced",
            lambda m: (
                OscMessage("/synced", m.contents[0] + 999)
                if m.address == "/sync"
                else None
            ),
        )
        assert server.sync(timeout=0.1) is False


class TestReplyMatcher:
    def test_matcher_accepts_only_matching_reply(self, server: Server) -> None:
        result = server.wait_for_reply(
            "/done", timeout=0.1, match=lambda m: m.contents[0] == "/d_recv"
        )
        # Nothing dispatched -> times out.
        assert result is None

    def test_nonmatching_reply_leaves_waiter_registered(self, server: Server) -> None:
        import threading

        got: list[object] = []

        def waiter() -> None:
            got.append(
                server.wait_for_reply(
                    "/done", timeout=2.0, match=lambda m: m.contents[0] == "/d_recv"
                )
            )

        t = threading.Thread(target=waiter)
        t.start()
        # A non-matching /done must NOT resolve the waiter.
        server._dispatch_reply(OscMessage("/done", "/b_alloc").to_datagram())
        assert "/done" in server._pending_replies  # still waiting
        # The matching /done resolves it.
        server._dispatch_reply(OscMessage("/done", "/d_recv").to_datagram())
        t.join(timeout=2.0)
        assert got and got[0] is not None
        assert got[0].contents[0] == "/d_recv"

    def test_timeout_removes_waiter(self, server: Server) -> None:
        # M4 regression: a timed-out waiter must not linger in _pending_replies.
        assert server.wait_for_reply("/done", timeout=0.05) is None
        assert "/done" not in server._pending_replies

    def test_multiple_waiters_partial_match(self, server: Server) -> None:
        import threading

        results: dict[str, object] = {}

        def wait(key: str, sub: str) -> None:
            results[key] = server.wait_for_reply(
                "/done", timeout=2.0, match=lambda m: m.contents[0] == sub
            )

        t1 = threading.Thread(target=wait, args=("a", "/d_recv"))
        t2 = threading.Thread(target=wait, args=("b", "/b_alloc"))
        t1.start()
        t2.start()
        server._dispatch_reply(OscMessage("/done", "/d_recv").to_datagram())
        t1.join(timeout=2.0)
        # a resolved, b still pending
        assert results.get("a") is not None
        assert "b" not in results
        server._dispatch_reply(OscMessage("/done", "/b_alloc").to_datagram())
        t2.join(timeout=2.0)
        assert results.get("b") is not None
