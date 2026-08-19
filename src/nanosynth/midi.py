"""MIDI input support via embedded RtMidi.

Provides parsed MIDI message types and a ``MidiIn`` class for receiving
MIDI input from hardware controllers.

This module requires the ``_midi`` C extension (built by default with
``NANOSYNTH_EMBED_MIDI=ON``).  If unavailable, importing this module
raises ``ImportError``.

Basic usage::

    from nanosynth.midi import MidiIn, NoteOn

    midi = MidiIn(port=0)
    midi.on_note_on(lambda msg: print(f"Note {msg.note} vel {msg.velocity}"))
    # ...
    midi.close()

    # Or as context manager:
    with MidiIn(port=0) as midi:
        midi.on_cc(lambda msg: print(f"CC {msg.control} = {msg.value}"))
        input("Press Enter to quit...")
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from . import _midi  # type: ignore[attr-defined]
from .exceptions import EngineError, MidiError

if TYPE_CHECKING:
    from .server import Server, Synth


# ---------------------------------------------------------------------------
# MIDI Message Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NoteOn:
    """MIDI Note On message."""

    channel: int
    note: int
    velocity: int


@dataclass(frozen=True, slots=True)
class NoteOff:
    """MIDI Note Off message."""

    channel: int
    note: int
    velocity: int


@dataclass(frozen=True, slots=True)
class ControlChange:
    """MIDI Control Change (CC) message."""

    channel: int
    control: int
    value: int


@dataclass(frozen=True, slots=True)
class PitchBend:
    """MIDI Pitch Bend message.

    Value range is 0--16383, with 8192 as center (no bend).
    """

    channel: int
    value: int


# Union of all message types
MidiMessage = NoteOn | NoteOff | ControlChange | PitchBend


# ---------------------------------------------------------------------------
# MIDI byte parsing (pure Python, fully testable without hardware)
# ---------------------------------------------------------------------------


def _parse(data: bytes) -> MidiMessage | None:
    """Parse raw MIDI bytes into a message object.

    Returns ``None`` for unrecognized or incomplete messages.
    Velocity-0 note-on is treated as note-off (standard MIDI convention).
    """
    if len(data) < 1:
        return None

    status = data[0]
    msg_type = status & 0xF0
    channel = status & 0x0F

    if msg_type == 0x90 and len(data) >= 3:
        # Note On (velocity 0 = Note Off)
        note = data[1]
        velocity = data[2]
        if velocity == 0:
            return NoteOff(channel=channel, note=note, velocity=0)
        return NoteOn(channel=channel, note=note, velocity=velocity)

    if msg_type == 0x80 and len(data) >= 3:
        # Note Off
        return NoteOff(channel=channel, note=data[1], velocity=data[2])

    if msg_type == 0xB0 and len(data) >= 3:
        # Control Change
        return ControlChange(channel=channel, control=data[1], value=data[2])

    if msg_type == 0xE0 and len(data) >= 3:
        # Pitch Bend (14-bit value: LSB first, then MSB)
        value = data[1] | (data[2] << 7)
        return PitchBend(channel=channel, value=value)

    return None


# ---------------------------------------------------------------------------
# MidiIn class
# ---------------------------------------------------------------------------


class MidiIn:
    """MIDI input port.

    Args:
        port: Port to open.  ``None`` opens a virtual port,
            ``int`` opens by index, ``str`` matches by name.

    Raises:
        ImportError: If the ``_midi`` C extension is not available.
        RuntimeError: If the requested port cannot be opened.
    """

    def __init__(self, port: int | str | None = None) -> None:
        self._handle: Any = None
        self._on_note_on: list[Callable[[NoteOn], None]] = []
        self._on_note_off: list[Callable[[NoteOff], None]] = []
        self._on_cc: list[Callable[[ControlChange], None]] = []
        self._on_pitch_bend: list[Callable[[PitchBend], None]] = []

        if port is None:
            self._handle = _midi.open_virtual_input("nanosynth")
        elif isinstance(port, int):
            self._handle = _midi.open_input(port, "nanosynth")
        elif isinstance(port, str):
            ports = _midi.list_input_ports()
            for i, name in enumerate(ports):
                if port in name:
                    self._handle = _midi.open_input(i, "nanosynth")
                    break
            if self._handle is None:
                raise MidiError(f"No MIDI port matching {port!r}")
        else:
            raise TypeError(f"port must be int, str, or None, got {type(port)}")

        _midi.set_callback(self._handle, self._raw_callback)

    def _raw_callback(self, data: bytes) -> None:
        """Dispatch raw MIDI bytes to registered handlers."""
        msg = _parse(data)
        if msg is None:
            return
        # Iterate over a snapshot: this runs on RtMidi's native callback thread
        # while on_*/off_* may append/remove from the user thread. Snapshotting
        # (an atomic list copy under the GIL) avoids "list changed size during
        # iteration" and missed/double dispatch (M7).
        if isinstance(msg, NoteOn):
            for note_on_cb in list(self._on_note_on):
                note_on_cb(msg)
        elif isinstance(msg, NoteOff):
            for note_off_cb in list(self._on_note_off):
                note_off_cb(msg)
        elif isinstance(msg, ControlChange):
            for cc_cb in list(self._on_cc):
                cc_cb(msg)
        elif isinstance(msg, PitchBend):
            for pb_cb in list(self._on_pitch_bend):
                pb_cb(msg)

    def close(self) -> None:
        """Close the MIDI input port."""
        if self._handle is not None:
            _midi.clear_callback(self._handle)
            _midi.close_input(self._handle)
            self._handle = None

    def __enter__(self) -> MidiIn:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -- Handler registration --------------------------------------------------

    def on_note_on(self, callback: Callable[[NoteOn], None]) -> None:
        """Register a handler for Note On messages."""
        self._on_note_on.append(callback)

    def on_note_off(self, callback: Callable[[NoteOff], None]) -> None:
        """Register a handler for Note Off messages."""
        self._on_note_off.append(callback)

    def on_cc(self, callback: Callable[[ControlChange], None]) -> None:
        """Register a handler for Control Change messages."""
        self._on_cc.append(callback)

    def on_pitch_bend(self, callback: Callable[[PitchBend], None]) -> None:
        """Register a handler for Pitch Bend messages."""
        self._on_pitch_bend.append(callback)

    def off_note_on(self, callback: Callable[[NoteOn], None]) -> None:
        """Remove a Note On handler."""
        try:
            self._on_note_on.remove(callback)
        except ValueError:
            pass

    def off_note_off(self, callback: Callable[[NoteOff], None]) -> None:
        """Remove a Note Off handler."""
        try:
            self._on_note_off.remove(callback)
        except ValueError:
            pass

    def off_cc(self, callback: Callable[[ControlChange], None]) -> None:
        """Remove a Control Change handler."""
        try:
            self._on_cc.remove(callback)
        except ValueError:
            pass

    def off_pitch_bend(self, callback: Callable[[PitchBend], None]) -> None:
        """Remove a Pitch Bend handler."""
        try:
            self._on_pitch_bend.remove(callback)
        except ValueError:
            pass

    # -- Static methods --------------------------------------------------------

    @staticmethod
    def list_ports() -> list[str]:
        """Return a list of available MIDI input port names."""
        return list(_midi.list_input_ports())


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------


def midi_note_map(
    midi_in: MidiIn,
    server: Server,
    synthdef_name: str,
    **fixed_params: float,
) -> Callable[[], None]:
    """Map MIDI note-on to synth creation and note-off to gate release.

    Creates a synth for each note-on with ``freq`` derived from the MIDI
    note number.  On note-off, sends ``gate=0`` to the corresponding synth.

    Args:
        midi_in: The MidiIn instance to listen on.
        server: The Server to create synths on.
        synthdef_name: Name of the SynthDef to instantiate.
        **fixed_params: Additional fixed parameters for all synths.

    Returns:
        A cleanup function that removes the handlers.
    """
    active: dict[tuple[int, int], Synth] = {}  # (channel, note) -> Synth

    def on_note_on(msg: NoteOn) -> None:
        key = (msg.channel, msg.note)
        # A Note-On for a still-held key (fast retrigger, held key, or a missed
        # Note-Off) would otherwise overwrite the entry and drop the previous
        # synth's handle un-gated -> a stuck voice. Gate the old one off first
        # (M8).
        previous = active.pop(key, None)
        if previous is not None:
            server.set(previous, gate=0.0)
        freq = 440.0 * (2.0 ** ((msg.note - 69.0) / 12.0))
        amp = msg.velocity / 127.0
        params = {**fixed_params, "freq": freq, "amp": amp}
        synth = server.synth(synthdef_name, **params)
        active[key] = synth

    def on_note_off(msg: NoteOff) -> None:
        key = (msg.channel, msg.note)
        synth = active.pop(key, None)
        if synth is not None:
            server.set(synth, gate=0.0)

    midi_in.on_note_on(on_note_on)
    midi_in.on_note_off(on_note_off)

    def cleanup() -> None:
        midi_in.off_note_on(on_note_on)
        midi_in.off_note_off(on_note_off)
        # Gate off any voices still held so cleanup does not leave notes ringing
        # (M8). Tolerate a dead server -- the synths died with it.
        for synth in list(active.values()):
            try:
                server.set(synth, gate=0.0)
            except (EngineError, OSError):
                pass
        active.clear()

    return cleanup


def midi_cc_map(
    midi_in: MidiIn,
    server: Server,
    synth: Synth | int,
    cc_map: dict[int, str],
    *,
    range_min: float = 0.0,
    range_max: float = 1.0,
) -> Callable[[], None]:
    """Map MIDI CC numbers to synth parameters.

    Each CC value (0--127) is linearly scaled to ``[range_min, range_max]``
    and sent as the mapped parameter name.

    Args:
        midi_in: The MidiIn instance to listen on.
        server: The Server for parameter updates.
        synth: Target synth (Synth proxy or node ID).
        cc_map: Mapping of CC number to parameter name.
        range_min: Output range minimum.
        range_max: Output range maximum.

    Returns:
        A cleanup function that removes the handler.
    """

    def on_cc(msg: ControlChange) -> None:
        param_name = cc_map.get(msg.control)
        if param_name is not None:
            scaled = range_min + (msg.value / 127.0) * (range_max - range_min)
            server.set(synth, **{param_name: scaled})

    midi_in.on_cc(on_cc)

    def cleanup() -> None:
        midi_in.off_cc(on_cc)

    return cleanup
