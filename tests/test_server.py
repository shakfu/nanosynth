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


class TestBufferManagement:
    """Tests for buffer allocation, read, write, free, and context managers."""

    @pytest.fixture()
    def server(self) -> Server:
        s = Server()
        s._protocol = MagicMock()
        s._protocol.status = BootStatus.ONLINE
        return s

    def test_buffer_id_starts_at_zero(self, server: Server) -> None:
        assert server.next_buffer_id() == 0

    def test_buffer_id_monotonically_increasing(self, server: Server) -> None:
        ids = [server.next_buffer_id() for _ in range(5)]
        assert ids == [0, 1, 2, 3, 4]

    def test_alloc_buffer_sends_b_alloc(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        buf_id = server.alloc_buffer(1024, 2)
        data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(data)
        assert msg.address == "/b_alloc"
        assert msg.contents[0] == buf_id
        assert msg.contents[1] == 1024
        assert msg.contents[2] == 2

    def test_alloc_buffer_auto_id(self, server: Server) -> None:
        id1 = server.alloc_buffer(512)
        id2 = server.alloc_buffer(512)
        assert id1 == 0
        assert id2 == 1

    def test_alloc_buffer_explicit_id(self, server: Server) -> None:
        buf_id = server.alloc_buffer(512, buffer_id=42)
        assert buf_id == 42

    def test_alloc_buffer_tracks(self, server: Server) -> None:
        buf_id = server.alloc_buffer(512)
        assert buf_id in server._allocated_buffers

    def test_read_buffer_sends_b_alloc_read(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        buf_id = server.read_buffer("/tmp/test.wav")
        data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(data)
        assert msg.address == "/b_allocRead"
        assert msg.contents[0] == buf_id
        assert msg.contents[1] == "/tmp/test.wav"
        assert msg.contents[2] == 0  # start_frame
        assert msg.contents[3] == -1  # num_frames

    def test_read_buffer_explicit_id(self, server: Server) -> None:
        buf_id = server.read_buffer("/tmp/test.wav", buffer_id=10)
        assert buf_id == 10
        assert 10 in server._allocated_buffers

    def test_write_buffer_sends_b_write(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        server.write_buffer(
            5, "/tmp/out.wav", header_format="aiff", sample_format="float"
        )
        data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(data)
        assert msg.address == "/b_write"
        assert msg.contents[0] == 5
        assert msg.contents[1] == "/tmp/out.wav"
        assert msg.contents[2] == "aiff"
        assert msg.contents[3] == "float"

    def test_free_buffer_sends_b_free(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        buf_id = server.alloc_buffer(512)
        server.free_buffer(buf_id)
        data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(data)
        assert msg.address == "/b_free"
        assert msg.contents[0] == buf_id

    def test_free_buffer_untracks(self, server: Server) -> None:
        buf_id = server.alloc_buffer(512)
        assert buf_id in server._allocated_buffers
        server.free_buffer(buf_id)
        assert buf_id not in server._allocated_buffers

    def test_zero_buffer_sends_b_zero(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        server.zero_buffer(3)
        data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(data)
        assert msg.address == "/b_zero"
        assert msg.contents[0] == 3

    def test_close_buffer_sends_b_close(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        server.close_buffer(7)
        data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(data)
        assert msg.address == "/b_close"
        assert msg.contents[0] == 7

    def test_managed_buffer_yields_id(self, server: Server) -> None:
        with server.managed_buffer(2048, 2) as buf_id:
            assert buf_id == 0
            assert buf_id in server._allocated_buffers

    def test_managed_buffer_frees_on_exit(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        with server.managed_buffer(1024) as buf_id:
            pass
        last_data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(last_data)
        assert msg.address == "/b_free"
        assert msg.contents[0] == buf_id
        assert buf_id not in server._allocated_buffers

    def test_managed_buffer_frees_on_exception(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        with pytest.raises(RuntimeError):
            with server.managed_buffer(1024) as buf_id:
                raise RuntimeError("boom")
        last_data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(last_data)
        assert msg.address == "/b_free"
        assert msg.contents[0] == buf_id

    def test_managed_read_buffer_yields_id(self, server: Server) -> None:
        with server.managed_read_buffer("/tmp/test.wav") as buf_id:
            assert buf_id == 0
            assert buf_id in server._allocated_buffers

    def test_managed_read_buffer_frees_on_exit(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        with server.managed_read_buffer("/tmp/test.wav") as buf_id:
            pass
        last_data = server._protocol.send_packet.call_args[0][0]
        msg = OscMessage.from_datagram(last_data)
        assert msg.address == "/b_free"
        assert msg.contents[0] == buf_id

    def test_managed_buffer_skips_free_if_stopped(self) -> None:
        s = Server()
        s._protocol = MagicMock()
        s._protocol.status = BootStatus.ONLINE
        with s.managed_buffer(1024):
            s._protocol.status = BootStatus.OFFLINE
        # send_packet called once for /b_alloc, but NOT for /b_free
        assert s._protocol.send_packet.call_count == 1


class TestReplyHandling:
    """Tests for reply dispatch, on/off handlers, and wait_for_reply."""

    @pytest.fixture()
    def server(self) -> Server:
        s = Server()
        s._protocol = MagicMock()
        s._protocol.status = BootStatus.ONLINE
        return s

    def test_on_registers_handler(self, server: Server) -> None:
        cb = MagicMock()
        server.on("/done", cb)
        assert cb in server._reply_handlers["/done"]

    def test_off_removes_handler(self, server: Server) -> None:
        cb = MagicMock()
        server.on("/done", cb)
        server.off("/done", cb)
        assert "/done" not in server._reply_handlers

    def test_off_nonexistent_is_noop(self, server: Server) -> None:
        cb = MagicMock()
        server.off("/done", cb)  # should not raise

    def test_dispatch_reply_calls_handler(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        cb = MagicMock()
        server.on("/done", cb)
        reply_msg = OscMessage("/done", "/b_alloc", 0)
        server._dispatch_reply(reply_msg.to_datagram())
        cb.assert_called_once()
        received_msg = cb.call_args[0][0]
        assert isinstance(received_msg, OscMessage)
        assert received_msg.address == "/done"

    def test_dispatch_reply_resolves_waiter(self, server: Server) -> None:
        import threading

        from nanosynth.osc import OscMessage

        result: list[OscMessage | None] = [None]

        def waiter() -> None:
            result[0] = server.wait_for_reply("/done", timeout=2.0)

        t = threading.Thread(target=waiter)
        t.start()
        # Give the waiter time to register
        import time

        time.sleep(0.05)
        reply_msg = OscMessage("/done", "/b_alloc", 0)
        server._dispatch_reply(reply_msg.to_datagram())
        t.join(timeout=2.0)
        assert result[0] is not None
        assert result[0].address == "/done"

    def test_wait_for_reply_timeout_returns_none(self, server: Server) -> None:
        result = server.wait_for_reply("/nonexistent", timeout=0.05)
        assert result is None

    def test_send_msg_sync_with_mock(self, server: Server) -> None:
        import threading

        from nanosynth.osc import OscMessage

        result: list[OscMessage | None] = [None]

        def caller() -> None:
            result[0] = server.send_msg_sync(
                "/b_alloc",
                0,
                1024,
                1,
                reply_address="/done",
                timeout=2.0,
            )

        t = threading.Thread(target=caller)
        t.start()
        import time

        time.sleep(0.05)
        reply_msg = OscMessage("/done", "/b_alloc", 0)
        server._dispatch_reply(reply_msg.to_datagram())
        t.join(timeout=2.0)
        assert result[0] is not None
        assert result[0].address == "/done"
        # Verify the original message was sent
        server._protocol.send_packet.assert_called_once()

    def test_dispatch_invalid_data_does_not_raise(self, server: Server) -> None:
        server._dispatch_reply(b"\x00\x00\x00")  # invalid OSC data

    def test_multiple_handlers_all_called(self, server: Server) -> None:
        from nanosynth.osc import OscMessage

        cb1 = MagicMock()
        cb2 = MagicMock()
        server.on("/done", cb1)
        server.on("/done", cb2)
        reply_msg = OscMessage("/done", 42)
        server._dispatch_reply(reply_msg.to_datagram())
        cb1.assert_called_once()
        cb2.assert_called_once()
