"""Tests for NodeProxy and Ndef (live coding proxy system).

All tests use a mock server to avoid booting audio.
Source callables use real UGens (they compile without a running server).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from nanosynth.exceptions import EngineError
from nanosynth.proxy import Ndef, NodeProxy
from nanosynth.scsynth import BootStatus
from nanosynth.server import Server
from nanosynth.synthdef import SynthDefBuilder
from nanosynth.ugens.osc import SinOsc
from nanosynth.ugens.inout import Out


def _sine_source() -> Any:
    """A minimal UGen callable for testing."""
    return SinOsc.ar(frequency=440)  # type: ignore[attr-defined]


@pytest.fixture()
def server() -> Server:
    """Server with mocked protocol (no audio engine needed)."""
    s = Server()
    s._protocol = MagicMock()
    s._protocol.status = BootStatus.ONLINE
    return s


# ---------------------------------------------------------------------------
# NodeProxy
# ---------------------------------------------------------------------------


class TestNodeProxy:
    def test_initial_state(self, server: Server) -> None:
        proxy = NodeProxy(server)
        assert proxy.bus is None
        assert proxy.source is None
        assert proxy.is_playing is False

    def test_bus_allocated_on_source_set(self, server: Server) -> None:
        proxy = NodeProxy(server)
        proxy.source = _sine_source
        assert proxy.bus is not None
        assert proxy.bus.num_channels == 2

    def test_source_setter_with_callable(self, server: Server) -> None:
        proxy = NodeProxy(server)
        proxy.source = _sine_source
        assert proxy.source is _sine_source
        # Verify synthdef was sent and synth was created
        assert server._protocol.send_packet.call_count >= 2  # d_recv + s_new

    def test_source_setter_with_synthdef(self, server: Server) -> None:
        with SynthDefBuilder(out=0.0) as builder:
            Out.ar(bus=builder["out"], source=SinOsc.ar())  # type: ignore[attr-defined]
        sd = builder.build(name="test_source")

        proxy = NodeProxy(server)
        proxy.source = sd
        assert proxy.source is sd

    def test_source_setter_none_clears(self, server: Server) -> None:
        proxy = NodeProxy(server)
        proxy.source = _sine_source
        proxy.source = None
        assert proxy.source is None

    def test_source_swap_frees_old(self, server: Server) -> None:
        proxy = NodeProxy(server)
        proxy.source = _sine_source
        first_call_count = server._protocol.send_packet.call_count

        # Swap source -- should send gate=0 for old + d_recv + s_new for new
        proxy.source = _sine_source
        assert server._protocol.send_packet.call_count > first_call_count

    def test_version_increments(self, server: Server) -> None:
        proxy = NodeProxy(server)
        assert proxy._version == 0
        proxy.source = _sine_source
        assert proxy._version == 1
        proxy.source = _sine_source
        assert proxy._version == 2

    def test_play_creates_monitor(self, server: Server) -> None:
        proxy = NodeProxy(server)
        proxy.source = _sine_source
        initial_count = server._protocol.send_packet.call_count

        proxy.play()
        assert proxy.is_playing is True
        # Should have sent d_recv (monitor synthdef) + s_new (monitor synth)
        assert server._protocol.send_packet.call_count > initial_count

    def test_play_idempotent(self, server: Server) -> None:
        proxy = NodeProxy(server)
        proxy.source = _sine_source
        proxy.play()
        count_after_first = server._protocol.send_packet.call_count

        proxy.play()  # second call should be no-op
        assert server._protocol.send_packet.call_count == count_after_first

    def test_stop_clears_monitor(self, server: Server) -> None:
        proxy = NodeProxy(server)
        proxy.source = _sine_source
        proxy.play()
        assert proxy.is_playing is True

        proxy.stop()
        assert proxy.is_playing is False

    def test_stop_when_not_playing_is_noop(self, server: Server) -> None:
        proxy = NodeProxy(server)
        proxy.stop()  # should not raise

    def test_clear_frees_everything(self, server: Server) -> None:
        proxy = NodeProxy(server)
        proxy.source = _sine_source
        proxy.play()

        proxy.clear()
        assert proxy.source is None
        assert proxy.bus is None
        assert proxy.is_playing is False

    def test_set_params(self, server: Server) -> None:
        proxy = NodeProxy(server)
        proxy.source = _sine_source
        proxy.set(frequency=880.0)
        # The set should have been sent (last send_packet call)
        assert server._protocol.send_packet.call_count > 0

    def test_set_without_source_raises(self, server: Server) -> None:
        proxy = NodeProxy(server)
        with pytest.raises(EngineError, match="No source synth"):
            proxy.set(frequency=440.0)

    def test_invalid_source_type_raises(self, server: Server) -> None:
        proxy = NodeProxy(server)
        with pytest.raises(TypeError, match="callable, SynthDef, or None"):
            proxy.source = 42  # type: ignore[assignment]

    def test_custom_channel_count(self, server: Server) -> None:
        proxy = NodeProxy(server, num_channels=4)
        proxy.source = _sine_source
        assert proxy.bus is not None
        assert proxy.bus.num_channels == 4


# ---------------------------------------------------------------------------
# Ndef
# ---------------------------------------------------------------------------


class TestNdef:
    def setup_method(self) -> None:
        """Clear the registry before each test."""
        Ndef._registry.clear()

    def test_creates_proxy(self, server: Server) -> None:
        proxy = Ndef(server, "test")
        assert isinstance(proxy, NodeProxy)

    def test_returns_same_proxy(self, server: Server) -> None:
        p1 = Ndef(server, "test")
        p2 = Ndef(server, "test")
        assert p1 is p2

    def test_different_names_different_proxies(self, server: Server) -> None:
        p1 = Ndef(server, "a")
        p2 = Ndef(server, "b")
        assert p1 is not p2

    def test_sets_source(self, server: Server) -> None:
        proxy = Ndef(server, "test", _sine_source)
        assert proxy.source is _sine_source

    def test_hot_swap(self, server: Server) -> None:
        def other_source() -> Any:
            return SinOsc.ar(frequency=880)  # type: ignore[attr-defined]

        Ndef(server, "test", _sine_source)
        proxy = Ndef(server, "test", other_source)
        assert proxy.source is other_source

    def test_no_source_arg_does_not_overwrite(self, server: Server) -> None:
        Ndef(server, "test", _sine_source)
        proxy = Ndef(server, "test")
        assert proxy.source is _sine_source

    def test_clear_all(self, server: Server) -> None:
        Ndef(server, "a", _sine_source)
        Ndef(server, "b", _sine_source)
        Ndef.clear_all(server)
        assert len(Ndef._registry) == 0

    def test_clear_all_scoped_to_server(self) -> None:
        s1 = Server()
        s1._protocol = MagicMock()
        s1._protocol.status = BootStatus.ONLINE

        s2 = Server()
        s2._protocol = MagicMock()
        s2._protocol.status = BootStatus.ONLINE

        Ndef(s1, "a", _sine_source)
        Ndef(s2, "a", _sine_source)

        Ndef.clear_all(s1)
        # s2's proxy should still be in the registry
        assert any(k[0] == id(s2) for k in Ndef._registry)
        assert not any(k[0] == id(s1) for k in Ndef._registry)

    def test_source_none_clears(self, server: Server) -> None:
        Ndef(server, "test", _sine_source)
        proxy = Ndef(server, "test", None)
        assert proxy.source is None
