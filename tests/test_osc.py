"""Basic OSC encode/decode round-trip tests."""

import struct

import pytest

import nanosynth.osc
from nanosynth.osc import OscBundle, OscMessage


@pytest.fixture(params=["native", "python"])
def osc_backend(request, monkeypatch):
    if request.param == "python":
        monkeypatch.setattr("nanosynth.osc._osc_native", None)
    elif nanosynth.osc._osc_native is None:
        pytest.skip("C++ OSC extension not available")


@pytest.mark.usefixtures("osc_backend")
class TestOscMessage:
    def test_basic_int(self):
        msg = OscMessage("/test", 42)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/test"
        assert decoded.contents == (42,)

    def test_basic_float(self):
        msg = OscMessage("/test", 1.0)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/test"
        assert decoded.contents == (1.0,)

    def test_basic_string(self):
        msg = OscMessage("/test", "hello")
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/test"
        assert decoded.contents == ("hello",)

    def test_basic_blob(self):
        # Use a blob that won't accidentally parse as an OscMessage.
        # Short blobs without null terminators may get speculatively
        # decoded as nested messages (OSC convention).
        blob = b"\xff" * 17  # too long/messy to be a valid message
        msg = OscMessage("/test", blob)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/test"
        assert decoded.contents == (blob,)

    def test_bool_true(self):
        msg = OscMessage("/test", True)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.contents == (True,)

    def test_bool_false(self):
        msg = OscMessage("/test", False)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.contents == (False,)

    def test_none(self):
        msg = OscMessage("/test", None)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.contents == (None,)

    def test_multiple_args(self):
        msg = OscMessage("/g_new", 0, 0)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded == msg

    def test_array(self):
        msg = OscMessage("/test", [1, 2, 3])
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/test"
        assert decoded.contents == ([1, 2, 3],)

    def test_nested_array(self):
        msg = OscMessage("/test", ["a", ["b", "c"]])
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/test"
        assert decoded.contents == (["a", ["b", "c"]],)

    def test_mixed_types(self):
        blob = b"\xff" * 17
        msg = OscMessage("/foo", 1, 2.5, "hello", True, None, blob)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/foo"
        assert decoded.contents[0] == 1
        assert decoded.contents[2] == "hello"
        assert decoded.contents[3] is True
        assert decoded.contents[4] is None
        assert decoded.contents[5] == blob

    def test_int_address(self):
        msg = OscMessage(42, "hello")
        datagram = msg.to_datagram()
        # Int addresses encode differently (big-endian i32 instead of string)
        assert struct.unpack(">i", datagram[:4])[0] == 42

    def test_nested_message(self):
        inner = OscMessage("/bar")
        msg = OscMessage("/foo", True, inner)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/foo"
        assert decoded.contents[0] is True
        assert isinstance(decoded.contents[1], OscMessage)
        assert decoded.contents[1].address == "/bar"

    def test_equality(self):
        a = OscMessage("/test", 1, 2)
        b = OscMessage("/test", 1, 2)
        c = OscMessage("/test", 1, 3)
        assert a == b
        assert a != c

    def test_repr(self):
        msg = OscMessage("/test", 42)
        assert repr(msg) == "OscMessage('/test', 42)"

    def test_invalid_address(self):
        with pytest.raises(ValueError):
            OscMessage(3.14, 1)  # type: ignore


@pytest.mark.usefixtures("osc_backend")
class TestOscBundle:
    def test_basic_bundle(self):
        msg = OscMessage("/test", 1)
        bundle = OscBundle(contents=(msg,))
        datagram = bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert decoded.timestamp is None
        assert len(decoded.contents) == 1
        assert decoded.contents[0] == msg

    def test_bundle_with_timestamp(self):
        msg = OscMessage("/test", 1)
        bundle = OscBundle(timestamp=1401557034.5, contents=(msg,))
        datagram = bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert decoded.timestamp == pytest.approx(1401557034.5, abs=1e-3)
        assert len(decoded.contents) == 1

    def test_bundle_multiple_messages(self):
        msg_a = OscMessage("/one", 1)
        msg_b = OscMessage("/two", 2)
        bundle = OscBundle(contents=(msg_a, msg_b))
        datagram = bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert len(decoded.contents) == 2
        assert decoded.contents[0] == msg_a
        assert decoded.contents[1] == msg_b

    def test_nested_bundle(self):
        msg = OscMessage("/inner", 1)
        inner = OscBundle(timestamp=1401557034.5, contents=(msg,))
        outer = OscBundle(contents=(inner,))
        datagram = outer.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert decoded.timestamp is None
        assert len(decoded.contents) == 1
        inner_decoded = decoded.contents[0]
        assert isinstance(inner_decoded, OscBundle)
        assert inner_decoded.timestamp == pytest.approx(1401557034.5, abs=1e-3)

    def test_equality(self):
        msg = OscMessage("/test", 1)
        a = OscBundle(contents=(msg,))
        b = OscBundle(contents=(msg,))
        assert a == b

    def test_invalid_contents(self):
        with pytest.raises(ValueError):
            OscBundle(contents=("not a message",))  # type: ignore

    def test_not_a_bundle(self):
        with pytest.raises((ValueError, RuntimeError)):
            OscBundle.from_datagram(b"\x00\x00\x00\x00")

    def test_message_in_bundle_round_trip(self):
        """Full round-trip: bundle containing a message with an embedded bundle."""
        inner_msg = OscMessage("/bar", "baz", 3.0)
        inner_bundle = OscBundle(contents=(inner_msg,))
        outer_msg = OscMessage("/foo", 1, inner_bundle)
        outer_bundle = OscBundle(contents=(outer_msg,))
        datagram = outer_bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert len(decoded.contents) == 1
        decoded_msg = decoded.contents[0]
        assert isinstance(decoded_msg, OscMessage)
        assert decoded_msg.address == "/foo"
        assert decoded_msg.contents[0] == 1
