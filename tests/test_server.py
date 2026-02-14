"""Tests for the high-level Server class."""

from unittest.mock import MagicMock, patch

import pytest

from nanosynth.scsynth import BootStatus, Options
from nanosynth.server import Server


class TestServerInit:
    def test_default_options(self) -> None:
        """Server() uses default Options when none provided."""
        s = Server()
        assert s._options == Options()

    def test_custom_options(self) -> None:
        """Server(options=...) stores the provided Options."""
        opts = Options(port=57111, verbosity=1)
        s = Server(options=opts)
        assert s._options is opts

    def test_repr_stopped(self) -> None:
        s = Server()
        assert "stopped" in repr(s)

    def test_is_running_false_initially(self) -> None:
        s = Server()
        assert s.is_running is False


class TestNodeIdAllocation:
    def test_starts_at_1000(self) -> None:
        s = Server()
        assert s.next_node_id() == 1000

    def test_monotonically_increasing(self) -> None:
        s = Server()
        ids = [s.next_node_id() for _ in range(5)]
        assert ids == [1000, 1001, 1002, 1003, 1004]


class TestServerWithMockedProtocol:
    """Tests using a mocked EmbeddedProcessProtocol to avoid booting audio."""

    @pytest.fixture()
    def server(self) -> Server:
        s = Server()
        s._protocol = MagicMock()
        s._protocol.status = BootStatus.ONLINE
        return s

    def test_send_msg(self, server: Server) -> None:
        server.send_msg("/test", 1, 2.0, "hello")
        server._protocol.send_packet.assert_called_once()
        data = server._protocol.send_packet.call_args[0][0]
        assert isinstance(data, bytes)

    def test_is_running_when_online(self, server: Server) -> None:
        assert server.is_running is True

    def test_send_synthdef(self, server: Server) -> None:
        sd = MagicMock()
        sd.effective_name = "test_sd"
        sd.compile.return_value = b"SCgf_data"
        server.send_synthdef(sd)
        assert "test_sd" in server._synthdefs
        server._protocol.send_packet.assert_called_once()

    def test_synth_returns_node_id(self, server: Server) -> None:
        node_id = server.synth("my_synth", frequency=440.0)
        assert node_id == 1000
        server._protocol.send_packet.assert_called_once()

    def test_synth_increments_id(self, server: Server) -> None:
        id1 = server.synth("s1")
        id2 = server.synth("s2")
        assert id2 == id1 + 1

    def test_group_returns_node_id(self, server: Server) -> None:
        node_id = server.group(target=1, action=0)
        assert node_id == 1000

    def test_free_sends_n_free(self, server: Server) -> None:
        server.free(1000)
        server._protocol.send_packet.assert_called_once()

    def test_set_sends_n_set(self, server: Server) -> None:
        server.set(1000, frequency=880.0, amplitude=0.5)
        server._protocol.send_packet.assert_called_once()

    def test_quit_when_not_running(self) -> None:
        """quit() is a no-op when not running."""
        s = Server()
        s._protocol = MagicMock()
        s._protocol.status = BootStatus.OFFLINE
        s.quit()
        s._protocol.send_packet.assert_not_called()
        s._protocol._shutdown.assert_not_called()

    def test_context_manager(self) -> None:
        """Context manager calls boot on enter and quit on exit."""
        s = Server()
        s._protocol = MagicMock()
        s._protocol.status = BootStatus.ONLINE
        with patch.object(s, "boot") as mock_boot, patch.object(s, "quit") as mock_quit:
            with s:
                mock_boot.assert_called_once()
            mock_quit.assert_called_once()


class TestServerOscEncoding:
    """Verify that OSC messages are correctly encoded."""

    @pytest.fixture()
    def server(self) -> Server:
        s = Server()
        s._protocol = MagicMock()
        s._protocol.status = BootStatus.ONLINE
        return s

    def test_synth_osc_message(self, server: Server) -> None:
        """synth() sends /s_new with correct argument order."""
        from nanosynth.osc import OscMessage

        server.synth("sine", target=1, action=0, frequency=440.0)
        data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(data)
        assert msg.address == "/s_new"
        assert msg.contents[0] == "sine"
        assert msg.contents[1] == 1000  # node id
        assert msg.contents[2] == 0  # action
        assert msg.contents[3] == 1  # target

    def test_group_osc_message(self, server: Server) -> None:
        """group() sends /g_new with correct arguments."""
        from nanosynth.osc import OscMessage

        server.group(target=1, action=1)
        data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(data)
        assert msg.address == "/g_new"
        assert msg.contents[0] == 1000
        assert msg.contents[1] == 1
        assert msg.contents[2] == 1

    def test_set_osc_message(self, server: Server) -> None:
        """set() sends /n_set with flattened key-value pairs."""
        from nanosynth.osc import OscMessage

        server.set(1000, frequency=880.0)
        data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(data)
        assert msg.address == "/n_set"
        assert msg.contents[0] == 1000
        assert msg.contents[1] == "frequency"
        # OSC float encoding
        assert abs(msg.contents[2] - 880.0) < 0.01


class TestManagedSynth:
    """Tests for managed_synth and managed_group context managers."""

    @pytest.fixture()
    def server(self) -> Server:
        s = Server()
        s._protocol = MagicMock()
        s._protocol.status = BootStatus.ONLINE
        return s

    def test_managed_synth_yields_node_id(self, server: Server) -> None:
        with server.managed_synth("test") as node_id:
            assert node_id == 1000

    def test_managed_synth_frees_on_exit(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        with server.managed_synth("test") as node_id:
            pass
        # Last call should be /n_free
        last_data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(last_data)
        assert msg.address == "/n_free"
        assert msg.contents[0] == node_id

    def test_managed_synth_frees_on_exception(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        with pytest.raises(RuntimeError):
            with server.managed_synth("test") as node_id:
                raise RuntimeError("boom")
        last_data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(last_data)
        assert msg.address == "/n_free"
        assert msg.contents[0] == node_id

    def test_managed_synth_skips_free_if_server_stopped(self) -> None:
        """If the server has already quit, don't try to free."""
        s = Server()
        s._protocol = MagicMock()
        s._protocol.status = BootStatus.ONLINE
        with s.managed_synth("test"):
            s._protocol.status = BootStatus.OFFLINE
        # send_packet called once for /s_new, but NOT for /n_free
        assert s._protocol.send_packet.call_count == 1

    def test_managed_synth_forwards_params(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        with server.managed_synth("sine", frequency=440.0):
            # Check the /s_new message had the param
            first_data = server._protocol.send_packet.call_args_list[0][0][0]
            msg = OscMessage.from_datagram(first_data)
            assert msg.address == "/s_new"
            assert "frequency" in msg.contents

    def test_managed_group_yields_node_id(self, server: Server) -> None:
        with server.managed_group(target=1) as node_id:
            assert node_id == 1000

    def test_managed_group_frees_on_exit(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        with server.managed_group() as node_id:
            pass
        last_data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(last_data)
        assert msg.address == "/n_free"
        assert msg.contents[0] == node_id
