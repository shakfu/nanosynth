"""Minimal standalone OSC message/bundle encode/decode."""

import contextlib
import datetime
import socket
import struct
import time
from collections.abc import Iterator, Sequence as SequenceABC
from typing import Any, Union

from .exceptions import OscError

try:
    from . import _osc as _osc_native  # type: ignore[attr-defined]
except ImportError:
    _osc_native = None

BUNDLE_PREFIX = b"#bundle\x00"
IMMEDIATELY = struct.pack(">Q", 1)
NTP_TIMESTAMP_TO_SECONDS = 1.0 / 2.0**32.0
SECONDS_TO_NTP_TIMESTAMP = 2.0**32.0
SYSTEM_EPOCH = datetime.date(*time.gmtime(0)[0:3])
NTP_EPOCH = datetime.date(1900, 1, 1)
NTP_DELTA = (SYSTEM_EPOCH - NTP_EPOCH).days * 24 * 3600


OscArgument = Union[
    "OscBundle",
    "OscMessage",
    SequenceABC["OscArgument"],
    bool,
    bytes,
    float,
    str,
    None,
]


def _group_by_count(iterable: SequenceABC[Any], count: int) -> Iterator[list[Any]]:
    """Split an iterable into chunks of ``count`` items."""
    iterator = iter(iterable)
    result: list[Any] = []
    for item in iterator:
        result.append(item)
        if len(result) == count:
            yield result
            result = []
    if result:
        yield result


def format_datagram(datagram: bytes | bytearray) -> str:
    result: list[str] = ["size {}".format(len(datagram))]
    index = 0
    while index < len(datagram):
        hex_blocks = []
        ascii_block = ""
        for chunk in _group_by_count(datagram[index : index + 16], 4):
            hex_block = []
            for byte in chunk:
                if 31 < int(byte) < 127:
                    char = chr(int(byte))
                else:
                    char = "."
                ascii_block += char
                hexed = hex(byte)[2:].zfill(2)
                hex_block.append(hexed)
            hex_blocks.append(" ".join(hex_block))
        line = "{: >4}   ".format(index)
        line += "{: <53}".format("  ".join(hex_blocks))
        line += "|{}|".format(ascii_block)
        result.append(line)
        index += 16
    return "\n".join(result)


class OscMessage:
    """An Open Sound Control message with an address pattern and typed arguments.

    Supports encoding to and decoding from the OSC binary wire format.
    Contents can be ints, floats, strings, bytes, bools, None, nested
    messages/bundles, or arrays. Uses C++ acceleration when available,
    falling back to a pure-Python implementation.

    Args:
        address: OSC address pattern (e.g. ``"/s_new"``) or integer address.
        contents: Typed arguments (int, float, str, bytes, bool, None,
            OscMessage, OscBundle, or sequences thereof).
    """

    def __init__(self, address: int | str, *contents: OscArgument) -> None:
        if not isinstance(address, (str, int)):
            raise ValueError(f"address must be int or str, got {address}")
        self.address = address
        self.contents = tuple(contents)

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return False
        assert isinstance(other, OscMessage)
        if self.address != other.address:
            return False
        if self.contents != other.contents:
            return False
        return True

    def __repr__(self) -> str:
        return "{}({})".format(
            type(self).__name__,
            ", ".join(repr(_) for _ in [self.address, *self.contents]),
        )

    def __str__(self) -> str:
        return format_datagram(bytearray(self.to_datagram()))

    @staticmethod
    def _decode_blob(data: bytes) -> tuple[bytes, bytes]:
        if len(data) < 4:
            raise OscError("truncated blob size")
        actual_length, remainder = struct.unpack(">I", data[:4])[0], data[4:]
        # Reject a truncated datagram instead of silently returning a short
        # blob (the slice below would otherwise just yield fewer bytes).
        if len(remainder) < actual_length:
            raise OscError(
                f"truncated blob: declared {actual_length} bytes, "
                f"{len(remainder)} available"
            )
        padded_length = actual_length
        if actual_length % 4 != 0:
            padded_length = (actual_length // 4 + 1) * 4
        return remainder[:padded_length][:actual_length], remainder[padded_length:]

    @staticmethod
    def _decode_string(data: bytes) -> tuple[str, bytes]:
        actual_length = data.index(b"\x00")
        padded_length = (actual_length // 4 + 1) * 4
        return str(data[:actual_length], "utf-8"), data[padded_length:]

    @staticmethod
    def _encode_string(value: str) -> bytes:
        # UTF-8 to match the native C++ codec (real-world OSC uses UTF-8,
        # despite the 1.0 spec nominally specifying ASCII).
        result = value.encode("utf-8") + b"\x00"
        if len(result) % 4 != 0:
            width = (len(result) // 4 + 1) * 4
            result = result.ljust(width, b"\x00")
        return result

    @staticmethod
    def _encode_blob(value: bytes) -> bytes:
        result = bytes(struct.pack(">I", len(value)) + value)
        if len(result) % 4 != 0:
            width = (len(result) // 4 + 1) * 4
            result = result.ljust(width, b"\x00")
        return result

    @classmethod
    def _encode_value(cls, value: OscArgument) -> tuple[str, bytes]:
        type_tags, encoded_value = "", b""
        if isinstance(value, (OscBundle, OscMessage)):
            type_tags += "b"
            encoded_value = cls._encode_blob(value.to_datagram())
        elif isinstance(value, (bytearray, bytes)):
            type_tags += "b"
            encoded_value = cls._encode_blob(bytes(value))
        elif isinstance(value, str):
            type_tags += "s"
            encoded_value = cls._encode_string(value)
        elif isinstance(value, bool):
            type_tags += "T" if value else "F"
        elif isinstance(value, float):
            type_tags += "f"
            encoded_value += struct.pack(">f", value)
        elif isinstance(value, int):
            type_tags += "i"
            encoded_value += struct.pack(">i", value)
        elif value is None:
            type_tags += "N"
        elif isinstance(value, SequenceABC):
            type_tags += "["
            for sub_value in value:
                sub_type_tags, sub_encoded_value = cls._encode_value(sub_value)
                type_tags += sub_type_tags
                encoded_value += sub_encoded_value
            type_tags += "]"
        else:
            message = "Cannot encode {!r}".format(value)
            raise TypeError(message)
        return type_tags, encoded_value

    def to_datagram(self) -> bytes:
        """Encode this message to an OSC binary datagram."""
        if _osc_native is not None:
            if isinstance(self.address, str):
                return bytes(_osc_native.encode_message(self.address, *self.contents))
            else:
                return bytes(
                    _osc_native.encode_message_int(self.address, *self.contents)
                )
        # Fallback: pure Python
        if isinstance(self.address, str):
            encoded_address = self._encode_string(self.address)
        else:
            # Integer (command-number) address: a send-side optimization for
            # outgoing commands. Note the asymmetry -- from_datagram always
            # decodes the address as a string, so an int-addressed message does
            # not round-trip. This is latent: engine replies are always
            # string-addressed, and int addresses are only ever encoded, never
            # decoded back.
            encoded_address = struct.pack(">i", self.address)
        encoded_type_tags = ","
        encoded_contents = b""
        for value in self.contents or ():
            type_tags, encoded_value = self._encode_value(value)
            encoded_type_tags += type_tags
            encoded_contents += encoded_value
        return (
            encoded_address + self._encode_string(encoded_type_tags) + encoded_contents
        )

    @classmethod
    def from_datagram(cls, datagram: bytes) -> "OscMessage":
        """Decode an OSC binary datagram into an OscMessage.

        Raises ``OscError`` on malformed input (both the native and
        pure-Python paths).
        """
        if _osc_native is not None:
            address, contents = _osc_native.decode_message(datagram)
            return cls(address, *contents)
        # Fallback: pure Python. Wrap low-level decode failures as OscError so
        # the contract matches the native path.
        try:
            remainder = datagram
            address, remainder = cls._decode_string(remainder)
            type_tags, remainder = cls._decode_string(remainder)
            contents_list: list[OscArgument] = []
            array_stack: list[list[OscArgument]] = [contents_list]
            for type_tag in type_tags[1:]:
                if type_tag == "i":
                    value = struct.unpack(">i", remainder[:4])[0]
                    remainder = remainder[4:]
                    array_stack[-1].append(value)
                elif type_tag == "f":
                    value = struct.unpack(">f", remainder[:4])[0]
                    remainder = remainder[4:]
                    array_stack[-1].append(value)
                elif type_tag == "d":
                    value = struct.unpack(">d", remainder[:8])[0]
                    remainder = remainder[8:]
                    array_stack[-1].append(value)
                elif type_tag == "s":
                    value, remainder = cls._decode_string(remainder)
                    array_stack[-1].append(value)
                elif type_tag == "b":
                    blob, remainder = cls._decode_blob(remainder)
                    parsed: OscArgument = blob
                    # A blob is decoded back into a nested OscBundle/OscMessage
                    # when its bytes parse as one (the inverse of encoding a
                    # nested message/bundle as a blob -- see test_nested_message
                    # / test_nested_bundle). This is an intentional, tested
                    # feature; the trade-off is that a raw blob whose bytes
                    # happen to form valid OSC also decodes as a message (M6,
                    # accepted -- there is no marker to distinguish the two).
                    for class_ in (OscBundle, OscMessage):
                        try:
                            parsed = class_.from_datagram(blob)
                            break
                        except (ValueError, IndexError, struct.error):
                            pass
                    array_stack[-1].append(parsed)
                elif type_tag == "T":
                    array_stack[-1].append(True)
                elif type_tag == "F":
                    array_stack[-1].append(False)
                elif type_tag == "N":
                    array_stack[-1].append(None)
                elif type_tag == "[":
                    array: list[OscArgument] = []
                    array_stack[-1].append(array)
                    array_stack.append(array)
                elif type_tag == "]":
                    array_stack.pop()
                else:
                    raise OscError(f"Unable to parse type {type_tag!r}")
            return cls(address, *contents_list)
        except OscError:
            raise
        except (ValueError, IndexError, struct.error) as exc:
            raise OscError(f"malformed OSC message: {exc}") from exc

    def to_list(self) -> list[Any]:
        """Convert to a nested list representation: ``[address, arg1, arg2, ...]``."""
        result: list[Any] = [self.address]
        for x in self.contents:
            if isinstance(x, (OscMessage, OscBundle)):
                result.append(x.to_list())
            else:
                result.append(x)
        return result

    def to_osc(self) -> "OscMessage":
        """Return self (identity, for protocol compatibility with OscBundle)."""
        return self


class OscBundle:
    """A timestamped collection of OSC messages and/or nested bundles.

    Bundles allow multiple messages to be dispatched atomically at a
    specified time. A ``None`` timestamp means "immediately".

    Args:
        timestamp: Unix epoch seconds (the ``time.time()`` domain) at which to
            execute the contents, or ``None`` for immediate execution. The
            NTP-epoch conversion (seconds since 1900-01-01) is applied on the
            wire only when encoding with ``realtime=True``; the stored and
            decoded value is always Unix seconds.
        contents: Sequence of ``OscMessage`` and/or ``OscBundle`` instances.
    """

    def __init__(
        self,
        timestamp: float | None = None,
        *,
        contents: SequenceABC["OscBundle | OscMessage"],
    ) -> None:
        prototype = (OscMessage, type(self))
        self.timestamp = timestamp
        contents = contents or ()
        for x in contents or ():
            if not isinstance(x, prototype):
                raise ValueError(contents)
        self.contents = tuple(contents)

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return False
        assert isinstance(other, OscBundle)
        if self.timestamp != other.timestamp:
            return False
        if self.contents != other.contents:
            return False
        return True

    def __repr__(self) -> str:
        parts = ["{}(".format(type(self).__name__)]
        if self.timestamp is not None:
            parts.append(f"timestamp={self.timestamp}")
            if self.contents:
                parts.append(", ")
        if self.contents:
            parts.append(f"contents={list(self.contents)!r}")
        parts.append(")")
        return "".join(parts)

    def __str__(self) -> str:
        return format_datagram(bytearray(self.to_datagram()))

    @staticmethod
    def _decode_date(data: bytes) -> tuple[float | None, bytes]:
        data, remainder = data[:8], data[8:]
        if data == IMMEDIATELY:
            return None, remainder
        date = (struct.unpack(">Q", data)[0] / SECONDS_TO_NTP_TIMESTAMP) - NTP_DELTA
        return date, remainder

    @staticmethod
    def _encode_date(seconds: float | None, realtime: bool = True) -> bytes:
        if seconds is None:
            return IMMEDIATELY
        if realtime:
            seconds = seconds + NTP_DELTA
        if seconds >= 4294967296:  # 2**32
            seconds = seconds % 4294967296
        return struct.pack(">Q", int(seconds * SECONDS_TO_NTP_TIMESTAMP))

    @classmethod
    def from_datagram(cls, datagram: bytes) -> "OscBundle":
        """Decode an OSC binary datagram into an OscBundle.

        Raises ``OscError`` on malformed input (both the native and
        pure-Python paths).
        """
        if not datagram.startswith(BUNDLE_PREFIX):
            raise OscError("datagram is not a bundle")
        if _osc_native is not None:
            timestamp, element_datagrams = _osc_native.decode_bundle(datagram)
            contents: list[OscBundle | OscMessage] = []
            for elem in element_datagrams:
                if elem.startswith(BUNDLE_PREFIX):
                    contents.append(cls.from_datagram(elem))
                else:
                    contents.append(OscMessage.from_datagram(elem))
            return cls(timestamp=timestamp, contents=tuple(contents))
        # Fallback: pure Python. Wrap low-level decode failures as OscError.
        try:
            remainder = datagram[8:]
            timestamp, remainder = cls._decode_date(remainder)
            contents_list: list[OscBundle | OscMessage] = []
            while len(remainder):
                length = struct.unpack(">i", remainder[:4])[0]
                remainder = remainder[4:]
                item: OscBundle | OscMessage
                if remainder.startswith(BUNDLE_PREFIX):
                    item = cls.from_datagram(remainder[:length])
                else:
                    item = OscMessage.from_datagram(remainder[:length])
                contents_list.append(item)
                remainder = remainder[length:]
            return cls(timestamp=timestamp, contents=tuple(contents_list))
        except OscError:
            raise
        except (ValueError, IndexError, struct.error) as exc:
            raise OscError(f"malformed OSC bundle: {exc}") from exc

    def to_datagram(self, realtime: bool = True) -> bytes:
        """Encode this bundle to an OSC binary datagram."""
        datagram: bytes = BUNDLE_PREFIX
        datagram += self._encode_date(self.timestamp, realtime=realtime)
        for content in self.contents:
            content_datagram = content.to_datagram()
            datagram += struct.pack(">i", len(content_datagram))
            datagram += content_datagram
        return datagram

    def to_list(self) -> list[Any]:
        result: list[Any] = [self.timestamp]
        result.append([x.to_list() for x in self.contents])
        return result

    def to_osc(self) -> "OscBundle":
        return self


def find_free_port() -> int:
    """Find and return an available UDP port number."""
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(s.getsockname()[1])
