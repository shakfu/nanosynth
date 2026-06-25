"""Tests for direct numpy buffer data exchange (Python-side validation).

The round-trip against a real engine lives in the gated realtime smoke tests
(buffer storage only exists on a booted World). Here we cover the
engine-agnostic Python logic with mocks: protocol capability checks, shape
coercion, and input validation.
"""

from unittest.mock import MagicMock

import pytest

from nanosynth.exceptions import EngineError
from nanosynth.scsynth import BootStatus
from nanosynth.server import Server

# numpy is an optional dependency; skip this module entirely if it is absent
# (e.g. the cibuildwheel test environment, which installs only pytest).
np = pytest.importorskip("numpy")


@pytest.fixture()
def scsynth_server() -> Server:
    """A Server whose mock protocol advertises buffer_* methods (scsynth-like)."""
    s = Server()
    s._protocol = MagicMock()  # has buffer_get/buffer_set/buffer_info
    s._protocol.status = BootStatus.ONLINE
    return s


class _NoBufferProtocol:
    """Stand-in for a protocol without direct buffer access (e.g. supernova)."""

    status = BootStatus.ONLINE


class TestProtocolCapability:
    def test_get_requires_scsynth(self) -> None:
        s = Server()
        s._protocol = _NoBufferProtocol()  # type: ignore[assignment]
        with pytest.raises(EngineError, match="scsynth"):
            s.get_buffer_data(0)

    def test_set_requires_scsynth(self) -> None:
        s = Server()
        s._protocol = _NoBufferProtocol()  # type: ignore[assignment]
        with pytest.raises(EngineError, match="scsynth"):
            s.set_buffer_data(0, np.zeros((4, 1), np.float32))

    def test_info_requires_scsynth(self) -> None:
        s = Server()
        s._protocol = _NoBufferProtocol()  # type: ignore[assignment]
        with pytest.raises(EngineError, match="scsynth"):
            s.buffer_info(0)


class TestSetBufferData:
    def test_mono_1d_is_reshaped_to_2d(self, scsynth_server: Server) -> None:
        scsynth_server.set_buffer_data(0, np.arange(8, dtype=np.float32))
        passed = scsynth_server._protocol.buffer_set.call_args[0][1]
        assert passed.shape == (8, 1)
        assert passed.dtype == np.float32

    def test_2d_passed_through(self, scsynth_server: Server) -> None:
        scsynth_server.set_buffer_data(0, np.zeros((4, 2), np.float32))
        passed = scsynth_server._protocol.buffer_set.call_args[0][1]
        assert passed.shape == (4, 2)

    def test_coerced_to_float32_contiguous(self, scsynth_server: Server) -> None:
        src = np.asfortranarray(np.zeros((4, 2), dtype=np.float64))
        scsynth_server.set_buffer_data(0, src)
        passed = scsynth_server._protocol.buffer_set.call_args[0][1]
        assert passed.dtype == np.float32
        assert passed.flags["C_CONTIGUOUS"]

    def test_rejects_3d(self, scsynth_server: Server) -> None:
        with pytest.raises(ValueError, match="1-D .* or 2-D"):
            scsynth_server.set_buffer_data(0, np.zeros((2, 2, 2), np.float32))


class TestAllocBufferFromArray:
    def test_allocates_sizes_syncs_and_fills(self, scsynth_server: Server) -> None:
        scsynth_server.sync = MagicMock(return_value=True)  # type: ignore[method-assign]
        wave = np.sin(np.linspace(0, 1, 64)).astype(np.float32)
        buffer_id = scsynth_server.alloc_buffer_from_array(wave)
        # /b_alloc sent with the right frames/channels
        from nanosynth.osc import OscMessage

        alloc_msg = OscMessage.from_datagram(
            scsynth_server._protocol.send_packet.call_args_list[0][0][0]
        )
        assert alloc_msg.address == "/b_alloc"
        assert alloc_msg.contents[1] == 64  # frames
        assert alloc_msg.contents[2] == 1  # channels
        scsynth_server.sync.assert_called_once()
        scsynth_server._protocol.buffer_set.assert_called_once()
        # Returned id is the allocated buffer id.
        assert buffer_id in scsynth_server._allocated_buffers

    def test_rejects_3d(self, scsynth_server: Server) -> None:
        with pytest.raises(ValueError):
            scsynth_server.alloc_buffer_from_array(np.zeros((2, 2, 2), np.float32))
