"""Forced cross-path parity tests for the OSC codec.

CLAUDE.md requires the native (C++) and pure-Python OSC paths to stay
compatible. These tests run identical inputs through *both* paths in a single
test (rather than parametrizing one path per run) and assert byte-identical
encoding, identical decoding, and identical exception types on malformed input.
"""

import contextlib

import pytest

import nanosynth.osc as osc_mod
from nanosynth.exceptions import OscError
from nanosynth.osc import OscBundle, OscMessage

pytestmark = pytest.mark.skipif(
    osc_mod._osc_native is None,
    reason="C++ OSC extension not available; nothing to compare against",
)


@contextlib.contextmanager
def _native(enabled: bool):
    """Temporarily force the native or pure-Python OSC path."""
    saved = osc_mod._osc_native
    osc_mod._osc_native = saved if enabled else None
    try:
        yield
    finally:
        osc_mod._osc_native = saved


def _encode_both(msg: OscMessage) -> tuple[bytes, bytes]:
    with _native(True):
        native = msg.to_datagram()
    with _native(False):
        python = msg.to_datagram()
    return native, python


def _decode_msg_both(datagram: bytes) -> tuple[OscMessage, OscMessage]:
    with _native(True):
        native = OscMessage.from_datagram(datagram)
    with _native(False):
        python = OscMessage.from_datagram(datagram)
    return native, python


REPRESENTATIVE_MESSAGES = [
    OscMessage("/s_new", "default", 1000, 0, 1),
    OscMessage("/n_set", 1000, "freq", 440.0, "amp", 0.25),
    OscMessage("/flags", True, False, None),
    OscMessage("/blob", b"\x00\x01\x02\x03\x04"),
    OscMessage("/mixed", 1, 2.5, "three", b"four", True),
    OscMessage("/array", [1, 2, 3], "after"),
    OscMessage("/empty"),
    OscMessage("/unicode", "café", "naïve", "日本語"),
]


@pytest.mark.parametrize("msg", REPRESENTATIVE_MESSAGES, ids=lambda m: str(m.address))
def test_encode_byte_identical(msg: OscMessage) -> None:
    native, python = _encode_both(msg)
    assert native == python, f"encode divergence for {msg!r}"


@pytest.mark.parametrize("msg", REPRESENTATIVE_MESSAGES, ids=lambda m: str(m.address))
def test_decode_identical(msg: OscMessage) -> None:
    datagram = msg.to_datagram()
    native, python = _decode_msg_both(datagram)
    assert native == python
    assert native == msg


def test_unicode_roundtrip_both_paths() -> None:
    msg = OscMessage("/text", "héllo wörld", "λ", "emoji-free")
    for enabled in (True, False):
        with _native(enabled):
            decoded = OscMessage.from_datagram(msg.to_datagram())
        assert decoded == msg


def test_nested_bundle_encode_identical() -> None:
    inner = OscBundle(
        timestamp=None, contents=(OscMessage("/inner", 1), OscMessage("/inner2", 2.0))
    )
    outer = OscBundle(timestamp=None, contents=(OscMessage("/outer", "x"), inner))
    with _native(True):
        native = outer.to_datagram()
    with _native(False):
        python = outer.to_datagram()
    assert native == python


# Malformed datagrams: every path must raise OscError (not RuntimeError /
# ValueError / struct.error / IndexError), so `except OscError` is portable
# across builds.
MALFORMED_MESSAGES = [
    pytest.param(b"hello", id="address-without-null-terminator"),
    pytest.param(b"/a\x00\x00,i\x00\x00\x00\x00", id="truncated-int-arg"),
    pytest.param(b"/a\x00\x00,s\x00\x00no-terminator", id="truncated-string-arg"),
]


@pytest.mark.parametrize("datagram", MALFORMED_MESSAGES)
def test_malformed_message_raises_oscerror_both_paths(datagram: bytes) -> None:
    for enabled in (True, False):
        with _native(enabled):
            with pytest.raises(OscError):
                OscMessage.from_datagram(datagram)


@pytest.mark.parametrize(
    "datagram",
    [
        pytest.param(b"\x00\x00\x00\x00", id="not-a-bundle"),
        pytest.param(b"not-a-bundle-prefix", id="wrong-prefix"),
    ],
)
def test_malformed_bundle_raises_oscerror_both_paths(datagram: bytes) -> None:
    for enabled in (True, False):
        with _native(enabled):
            with pytest.raises(OscError):
                OscBundle.from_datagram(datagram)


def test_oscerror_is_valueerror() -> None:
    # Back-compat: OSC decode failures remain catchable as ValueError.
    assert issubclass(OscError, ValueError)
