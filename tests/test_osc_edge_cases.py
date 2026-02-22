"""Edge case tests for the OSC codec.

Covers: NTP timestamp edge cases, deeply nested bundles, special characters
in addresses, format_datagram debug utility, equality edge cases,
to_list/to_osc methods, repr/str methods, and find_free_port.
"""

import struct
from unittest.mock import patch

import pytest

import nanosynth.osc
from nanosynth.osc import (
    OscBundle,
    OscMessage,
    find_free_port,
    format_datagram,
)


@pytest.fixture(params=["native", "python"])
def osc_backend(request, monkeypatch):
    if request.param == "python":
        monkeypatch.setattr("nanosynth.osc._osc_native", None)
    elif nanosynth.osc._osc_native is None:
        pytest.skip("C++ OSC extension not available")


# ---------------------------------------------------------------------------
# NTP timestamp edge cases
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("osc_backend")
class TestNtpTimestamps:
    def test_zero_timestamp(self):
        """Timestamp of 0.0 (NTP epoch) round-trips correctly."""
        msg = OscMessage("/test", 1)
        bundle = OscBundle(timestamp=0.0, contents=(msg,))
        datagram = bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert decoded.timestamp == pytest.approx(0.0, abs=1e-3)

    def test_small_fractional_timestamp(self):
        """Sub-second timestamps preserve fractional precision."""
        msg = OscMessage("/test", 1)
        bundle = OscBundle(timestamp=0.001, contents=(msg,))
        datagram = bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert decoded.timestamp == pytest.approx(0.001, abs=1e-3)

    def test_large_timestamp(self):
        """Large timestamps (year ~2034) round-trip correctly."""
        large_ts = 2000000000.0  # ~2033
        msg = OscMessage("/test", 1)
        bundle = OscBundle(timestamp=large_ts, contents=(msg,))
        datagram = bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert decoded.timestamp == pytest.approx(large_ts, abs=1.0)

    def test_none_timestamp_is_immediate(self):
        """None timestamp encodes as 'immediately' marker (NTP value 1)."""
        msg = OscMessage("/test", 1)
        bundle = OscBundle(timestamp=None, contents=(msg,))
        datagram = bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert decoded.timestamp is None

    def test_nonrealtime_timestamp(self):
        """realtime=False skips NTP delta offset."""
        msg = OscMessage("/test")
        bundle = OscBundle(timestamp=1.0, contents=(msg,))
        datagram = bundle.to_datagram(realtime=False)
        # The raw NTP timestamp should encode 1.0 directly (no NTP_DELTA)
        # Bundle format: "#bundle\0" (8) + timestamp (8) + ...
        ts_bytes = datagram[8:16]
        ts_ntp = struct.unpack(">Q", ts_bytes)[0]
        ts_seconds = ts_ntp / (2.0**32.0)
        assert abs(ts_seconds - 1.0) < 0.001


# ---------------------------------------------------------------------------
# Deeply nested bundles
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("osc_backend")
class TestDeepNesting:
    def test_three_level_nesting(self):
        """Three levels of nested bundles round-trip correctly."""
        msg = OscMessage("/deep", 42)
        level3 = OscBundle(timestamp=3.0, contents=(msg,))
        level2 = OscBundle(timestamp=2.0, contents=(level3,))
        level1 = OscBundle(timestamp=1.0, contents=(level2,))
        datagram = level1.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert decoded.timestamp == pytest.approx(1.0, abs=1e-3)
        inner2 = decoded.contents[0]
        assert isinstance(inner2, OscBundle)
        assert inner2.timestamp == pytest.approx(2.0, abs=1e-3)
        inner3 = inner2.contents[0]
        assert isinstance(inner3, OscBundle)
        assert inner3.timestamp == pytest.approx(3.0, abs=1e-3)
        assert inner3.contents[0] == msg

    def test_five_level_nesting(self):
        """Five levels of nested bundles round-trip correctly."""
        msg = OscMessage("/leaf", 99)
        bundle = OscBundle(contents=(msg,))
        for i in range(4):
            bundle = OscBundle(timestamp=float(i), contents=(bundle,))
        datagram = bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        # Walk down 4 levels to reach the message
        current = decoded
        for _ in range(4):
            assert len(current.contents) == 1
            current = current.contents[0]
            assert isinstance(current, OscBundle)
        assert len(current.contents) == 1
        assert isinstance(current.contents[0], OscMessage)
        assert current.contents[0].address == "/leaf"

    def test_mixed_nesting(self):
        """Bundle containing both messages and nested bundles."""
        msg1 = OscMessage("/a", 1)
        msg2 = OscMessage("/b", 2)
        inner = OscBundle(timestamp=1.0, contents=(msg2,))
        outer = OscBundle(contents=(msg1, inner))
        datagram = outer.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert len(decoded.contents) == 2
        assert isinstance(decoded.contents[0], OscMessage)
        assert decoded.contents[0].address == "/a"
        assert isinstance(decoded.contents[1], OscBundle)
        assert decoded.contents[1].contents[0].address == "/b"


# ---------------------------------------------------------------------------
# Special characters in OSC addresses
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("osc_backend")
class TestAddressEdgeCases:
    def test_address_with_underscores(self):
        """Addresses with underscores round-trip correctly."""
        msg = OscMessage("/s_new", 1)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/s_new"

    def test_address_with_digits(self):
        """Addresses with digits round-trip correctly."""
        msg = OscMessage("/bus/123/set", 1.0)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/bus/123/set"

    def test_address_with_dots(self):
        """Addresses with dots round-trip correctly."""
        msg = OscMessage("/synth.freq", 440.0)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/synth.freq"

    def test_long_address(self):
        """Long addresses (up to padding boundary) round-trip correctly."""
        addr = "/" + "a" * 200
        msg = OscMessage(addr, 1)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == addr

    def test_minimal_address(self):
        """Single-character address round-trips correctly."""
        msg = OscMessage("/", 1)
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/"

    def test_osc_wildcard_characters(self):
        """OSC pattern-matching characters in addresses round-trip correctly."""
        for addr in ["/foo*", "/bar?", "/baz[0-9]", "/{a,b}"]:
            msg = OscMessage(addr, 1)
            datagram = msg.to_datagram()
            decoded = OscMessage.from_datagram(datagram)
            assert decoded.address == addr


# ---------------------------------------------------------------------------
# Equality edge cases
# ---------------------------------------------------------------------------


class TestEqualityEdgeCases:
    def test_message_not_equal_to_non_message(self):
        """OscMessage != non-OscMessage object."""
        msg = OscMessage("/test", 1)
        assert msg != "not a message"
        assert msg != 42
        assert msg != None  # noqa: E711

    def test_message_different_address(self):
        """OscMessages with different addresses are not equal."""
        a = OscMessage("/foo", 1)
        b = OscMessage("/bar", 1)
        assert a != b

    def test_message_different_contents(self):
        """OscMessages with different contents are not equal."""
        a = OscMessage("/test", 1)
        b = OscMessage("/test", 2)
        assert a != b

    def test_bundle_not_equal_to_non_bundle(self):
        """OscBundle != non-OscBundle object."""
        msg = OscMessage("/test")
        bundle = OscBundle(contents=(msg,))
        assert bundle != "not a bundle"
        assert bundle != 42

    def test_bundle_different_timestamp(self):
        """OscBundles with different timestamps are not equal."""
        msg = OscMessage("/test")
        a = OscBundle(timestamp=1.0, contents=(msg,))
        b = OscBundle(timestamp=2.0, contents=(msg,))
        assert a != b

    def test_bundle_different_contents(self):
        """OscBundles with different contents are not equal."""
        a = OscBundle(contents=(OscMessage("/a"),))
        b = OscBundle(contents=(OscMessage("/b"),))
        assert a != b


# ---------------------------------------------------------------------------
# format_datagram, str, repr
# ---------------------------------------------------------------------------


class TestFormatAndRepr:
    def test_format_datagram_basic(self):
        """format_datagram produces hex dump with size header."""
        data = b"\x00\x01\x02\x03"
        result = format_datagram(data)
        assert "size 4" in result

    def test_format_datagram_longer(self):
        """format_datagram handles data longer than 16 bytes."""
        data = bytes(range(32))
        result = format_datagram(data)
        lines = result.split("\n")
        assert len(lines) >= 3  # header + 2 data lines

    def test_format_datagram_ascii_display(self):
        """format_datagram shows printable ASCII characters."""
        data = b"Hello World!\x00\x00\x00\x00"
        result = format_datagram(data)
        assert "Hello World!" in result

    def test_message_str(self):
        """str(OscMessage) produces a hex dump."""
        msg = OscMessage("/test", 42)
        result = str(msg)
        assert "size" in result

    def test_bundle_str(self):
        """str(OscBundle) produces a hex dump."""
        bundle = OscBundle(contents=(OscMessage("/test"),))
        result = str(bundle)
        assert "size" in result

    def test_bundle_repr_with_timestamp(self):
        """repr(OscBundle) shows timestamp when present."""
        msg = OscMessage("/test")
        bundle = OscBundle(timestamp=1.5, contents=(msg,))
        result = repr(bundle)
        assert "OscBundle" in result
        assert "1.5" in result

    def test_bundle_repr_no_timestamp(self):
        """repr(OscBundle) without timestamp omits it."""
        msg = OscMessage("/test")
        bundle = OscBundle(contents=(msg,))
        result = repr(bundle)
        assert "OscBundle" in result
        assert "contents=" in result

    def test_bundle_repr_empty(self):
        """repr(OscBundle) with no timestamp and no contents."""
        bundle = OscBundle(contents=())
        result = repr(bundle)
        assert "OscBundle" in result


# ---------------------------------------------------------------------------
# to_list and to_osc methods
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("osc_backend")
class TestToListAndToOsc:
    def test_message_to_list(self):
        """OscMessage.to_list() returns [address, arg1, arg2, ...]."""
        msg = OscMessage("/test", 1, "hello", 3.14)
        result = msg.to_list()
        assert result[0] == "/test"
        assert result[1] == 1
        assert result[2] == "hello"

    def test_message_to_list_with_nested(self):
        """OscMessage.to_list() recurses into nested messages."""
        inner = OscMessage("/inner", 42)
        outer = OscMessage("/outer", inner)
        result = outer.to_list()
        assert result[0] == "/outer"
        assert isinstance(result[1], list)
        assert result[1][0] == "/inner"

    def test_bundle_to_list(self):
        """OscBundle.to_list() returns [timestamp, [contents...]]."""
        msg = OscMessage("/test", 1)
        bundle = OscBundle(timestamp=1.0, contents=(msg,))
        result = bundle.to_list()
        assert result[0] == 1.0
        assert isinstance(result[1], list)

    def test_message_to_osc(self):
        """OscMessage.to_osc() returns self."""
        msg = OscMessage("/test")
        assert msg.to_osc() is msg

    def test_bundle_to_osc(self):
        """OscBundle.to_osc() returns self."""
        bundle = OscBundle(contents=(OscMessage("/test"),))
        assert bundle.to_osc() is bundle


# ---------------------------------------------------------------------------
# find_free_port
# ---------------------------------------------------------------------------


class TestFindFreePort:
    def test_returns_positive_int(self):
        """find_free_port() returns a positive integer."""
        port = find_free_port()
        assert isinstance(port, int)
        assert port > 0

    def test_returns_different_ports(self):
        """Two calls to find_free_port() return different ports (usually)."""
        ports = {find_free_port() for _ in range(5)}
        # At least 2 distinct ports in 5 tries
        assert len(ports) >= 2


# ---------------------------------------------------------------------------
# Unsupported type encoding
# ---------------------------------------------------------------------------


class TestEncodingErrors:
    def test_unsupported_type_raises(self):
        """Encoding an unsupported type raises TypeError."""
        # Force pure Python path to hit the TypeError
        with patch.object(nanosynth.osc, "_osc_native", None):
            msg = OscMessage("/test", object())
            with pytest.raises(TypeError, match="Cannot encode"):
                msg.to_datagram()


# ---------------------------------------------------------------------------
# No-args and empty messages
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("osc_backend")
class TestEmptyMessages:
    def test_message_no_args(self):
        """OscMessage with no arguments round-trips correctly."""
        msg = OscMessage("/trigger")
        datagram = msg.to_datagram()
        decoded = OscMessage.from_datagram(datagram)
        assert decoded.address == "/trigger"
        assert decoded.contents == ()

    def test_bundle_empty_contents(self):
        """OscBundle with no messages round-trips correctly."""
        bundle = OscBundle(contents=())
        datagram = bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert len(decoded.contents) == 0

    def test_bundle_many_messages(self):
        """OscBundle with many messages round-trips correctly."""
        msgs = tuple(OscMessage(f"/msg{i}", i) for i in range(20))
        bundle = OscBundle(contents=msgs)
        datagram = bundle.to_datagram()
        decoded = OscBundle.from_datagram(datagram)
        assert len(decoded.contents) == 20
        for i, content in enumerate(decoded.contents):
            assert isinstance(content, OscMessage)
            assert content.address == f"/msg{i}"
