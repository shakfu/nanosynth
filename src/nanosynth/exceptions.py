"""Nanosynth exception hierarchy.

All nanosynth-specific exceptions inherit from :class:`NanosynthError`,
enabling ``except NanosynthError`` as a catch-all for library errors while
still allowing fine-grained handling of specific failure modes.

Hierarchy::

    NanosynthError
    +-- OscError            # OSC encode/decode failures
    +-- EngineError         # Audio engine lifecycle errors
    |   +-- ServerCannotBoot
    +-- MidiError           # MIDI port/callback errors
    +-- SynthDefError       # SynthDef graph construction errors
"""


class NanosynthError(Exception):
    """Base class for all nanosynth-specific exceptions."""


class OscError(NanosynthError, ValueError):
    """Raised on OSC message/bundle encoding or decoding failures.

    Also a :class:`ValueError`, since a decode failure is a malformed-value
    error; this keeps ``except ValueError`` working while both the native and
    pure-Python codecs raise this single type for parity.
    """


class EngineError(NanosynthError):
    """Raised on audio engine lifecycle errors (boot, quit, send)."""


class ServerCannotBoot(EngineError):
    """Raised when the embedded scsynth engine fails to start."""


class MidiError(NanosynthError):
    """Raised on MIDI port discovery, open, or callback errors."""


class SynthDefError(NanosynthError):
    """Raised for SynthDef graph construction errors (e.g. cross-scope UGen references)."""
