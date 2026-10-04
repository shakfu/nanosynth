"""MIDI input and output via embedded RtMidi.

Provides parsed MIDI message types, ``MidiIn`` and ``MidiOut`` ports, and
MIDI clock send (``MidiClockOut``) and receive (``MidiClockIn``) bridged to a
pattern :class:`~nanosynth.patterns.Clock`.

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

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from . import _midi  # type: ignore[attr-defined]
from ._controls import SET_PARAMS, SYNTH_PARAMS, call
from .exceptions import EngineError, MidiError

if TYPE_CHECKING:
    from .patterns import Clock
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


@dataclass(frozen=True, slots=True)
class ProgramChange:
    """MIDI Program Change message."""

    channel: int
    program: int


@dataclass(frozen=True, slots=True)
class Aftertouch:
    """MIDI Channel Pressure (channel aftertouch) message."""

    channel: int
    value: int


@dataclass(frozen=True, slots=True)
class PolyAftertouch:
    """MIDI Polyphonic Key Pressure (per-note aftertouch) message."""

    channel: int
    note: int
    value: int


@dataclass(frozen=True, slots=True)
class SongPosition:
    """MIDI Song Position Pointer, in sixteenth notes (0--16383)."""

    position: int


@dataclass(frozen=True, slots=True)
class TimingClock:
    """MIDI Timing Clock tick (24 per quarter note)."""


@dataclass(frozen=True, slots=True)
class Start:
    """MIDI Start (transport)."""


@dataclass(frozen=True, slots=True)
class Continue:
    """MIDI Continue (transport)."""


@dataclass(frozen=True, slots=True)
class Stop:
    """MIDI Stop (transport)."""


# Union of all message types
MidiMessage = (
    NoteOn
    | NoteOff
    | ControlChange
    | PitchBend
    | ProgramChange
    | Aftertouch
    | PolyAftertouch
    | SongPosition
    | TimingClock
    | Start
    | Continue
    | Stop
)

M = TypeVar("M", bound=MidiMessage)

_REALTIME: dict[int, MidiMessage] = {
    0xF8: TimingClock(),
    0xFA: Start(),
    0xFB: Continue(),
    0xFC: Stop(),
}


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
    if status in _REALTIME:
        return _REALTIME[status]
    if status == 0xF2 and len(data) >= 3:
        return SongPosition(position=data[1] | (data[2] << 7))

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

    if msg_type == 0xC0 and len(data) >= 2:
        return ProgramChange(channel=channel, program=data[1])

    if msg_type == 0xD0 and len(data) >= 2:
        return Aftertouch(channel=channel, value=data[1])

    if msg_type == 0xA0 and len(data) >= 3:
        return PolyAftertouch(channel=channel, note=data[1], value=data[2])

    return None


def _encode(msg: MidiMessage) -> bytes:
    """Encode a message object as raw MIDI bytes (inverse of ``_parse``).

    Raises:
        ValueError: If a field is outside its MIDI range.
    """
    if isinstance(msg, (TimingClock, Start, Continue, Stop)):
        return {TimingClock: b"\xf8", Start: b"\xfa", Continue: b"\xfb", Stop: b"\xfc"}[
            type(msg)
        ]
    if isinstance(msg, SongPosition):
        return bytes([0xF2, *_split14(msg.position)])
    if isinstance(msg, PitchBend):
        return bytes([0xE0 | _channel(msg.channel), *_split14(msg.value)])
    if isinstance(msg, NoteOn):
        status, d1, d2 = 0x90, msg.note, msg.velocity
    elif isinstance(msg, NoteOff):
        status, d1, d2 = 0x80, msg.note, msg.velocity
    elif isinstance(msg, ControlChange):
        status, d1, d2 = 0xB0, msg.control, msg.value
    elif isinstance(msg, PolyAftertouch):
        status, d1, d2 = 0xA0, msg.note, msg.value
    elif isinstance(msg, ProgramChange):
        return bytes([0xC0 | _channel(msg.channel), _data7(msg.program)])
    elif isinstance(msg, Aftertouch):
        return bytes([0xD0 | _channel(msg.channel), _data7(msg.value)])
    else:
        raise TypeError(f"not a MIDI message: {msg!r}")
    return bytes([status | _channel(msg.channel), _data7(d1), _data7(d2)])


def _channel(value: int) -> int:
    if not 0 <= value <= 15:
        raise ValueError(f"MIDI channel must be 0-15, got {value}")
    return value


def _data7(value: int) -> int:
    if not 0 <= value <= 127:
        raise ValueError(f"MIDI data byte must be 0-127, got {value}")
    return value


def _split14(value: int) -> tuple[int, int]:
    if not 0 <= value <= 16383:
        raise ValueError(f"14-bit MIDI value must be 0-16383, got {value}")
    return value & 0x7F, value >> 7


# ---------------------------------------------------------------------------
# MidiIn class
# ---------------------------------------------------------------------------


class MidiIn:
    """MIDI input port.

    Args:
        port: Port to open.  ``None`` opens a virtual port,
            ``int`` opens by index, ``str`` matches by name.
        receive_clock: Deliver Timing Clock ticks (``TimingClock``), which
            RtMidi drops by default. Transport messages arrive either way.

    Raises:
        ImportError: If the ``_midi`` C extension is not available.
        RuntimeError: If the requested port cannot be opened.
    """

    def __init__(
        self, port: int | str | None = None, *, receive_clock: bool = False
    ) -> None:
        self._handle: Any = None
        # Handler lists are replaced, never mutated in place, under _lock; the
        # RtMidi thread reads a list reference without locking.
        self._handlers: dict[type, list[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()

        if port is None:
            self._handle = _midi.open_virtual_input("nanosynth")
        else:
            self._handle = _midi.open_input(
                _resolve_port(port, _midi.list_input_ports()), "nanosynth"
            )

        _midi.set_callback(
            self._handle, self._raw_callback, ignore_timing=not receive_clock
        )

    def _raw_callback(self, data: bytes) -> None:
        """Dispatch raw MIDI bytes to registered handlers."""
        msg = _parse(data)
        if msg is None:
            return
        for callback in self._handlers.get(type(msg), ()):
            callback(msg)

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

    def on(self, msg_type: type[M], callback: Callable[[M], None]) -> None:
        """Register a handler for one message type, e.g. ``on(ProgramChange, f)``."""
        with self._lock:
            current = self._handlers.get(msg_type, [])
            self._handlers[msg_type] = [*current, callback]

    def off(self, msg_type: type[M], callback: Callable[[M], None]) -> None:
        """Remove a handler registered with :meth:`on`. Unknown handlers are ignored."""
        with self._lock:
            current = self._handlers.get(msg_type, [])
            if callback in current:
                updated = list(current)
                updated.remove(callback)
                self._handlers[msg_type] = updated

    def on_note_on(self, callback: Callable[[NoteOn], None]) -> None:
        """Register a handler for Note On messages."""
        self.on(NoteOn, callback)

    def on_note_off(self, callback: Callable[[NoteOff], None]) -> None:
        """Register a handler for Note Off messages."""
        self.on(NoteOff, callback)

    def on_cc(self, callback: Callable[[ControlChange], None]) -> None:
        """Register a handler for Control Change messages."""
        self.on(ControlChange, callback)

    def on_pitch_bend(self, callback: Callable[[PitchBend], None]) -> None:
        """Register a handler for Pitch Bend messages."""
        self.on(PitchBend, callback)

    def off_note_on(self, callback: Callable[[NoteOn], None]) -> None:
        """Remove a Note On handler."""
        self.off(NoteOn, callback)

    def off_note_off(self, callback: Callable[[NoteOff], None]) -> None:
        """Remove a Note Off handler."""
        self.off(NoteOff, callback)

    def off_cc(self, callback: Callable[[ControlChange], None]) -> None:
        """Remove a Control Change handler."""
        self.off(ControlChange, callback)

    def off_pitch_bend(self, callback: Callable[[PitchBend], None]) -> None:
        """Remove a Pitch Bend handler."""
        self.off(PitchBend, callback)

    # -- Static methods --------------------------------------------------------

    @staticmethod
    def list_ports() -> list[str]:
        """Return a list of available MIDI input port names."""
        return list(_midi.list_input_ports())


def _resolve_port(port: int | str, names: list[str]) -> int:
    """Map an index or a name substring to a port index."""
    if isinstance(port, bool) or not isinstance(port, (int, str)):
        raise TypeError(f"port must be int, str, or None, got {type(port)}")
    if isinstance(port, int):
        return port
    for i, name in enumerate(names):
        if port in name:
            return i
    raise MidiError(f"No MIDI port matching {port!r}")


# ---------------------------------------------------------------------------
# MidiOut class
# ---------------------------------------------------------------------------


class MidiOut:
    """MIDI output port.

    Args:
        port: Port to open.  ``None`` opens a virtual port,
            ``int`` opens by index, ``str`` matches by name.

    Example::

        with MidiOut("Synth") as out:
            out.send(ProgramChange(channel=0, program=5))
            out.send(NoteOn(channel=0, note=60, velocity=100))
    """

    def __init__(self, port: int | str | None = None) -> None:
        self._handle: Any = None
        if port is None:
            self._handle = _midi.open_virtual_output("nanosynth")
        else:
            self._handle = _midi.open_output(
                _resolve_port(port, _midi.list_output_ports()), "nanosynth"
            )

    def send(self, msg: MidiMessage) -> None:
        """Encode and send one message."""
        self.send_bytes(_encode(msg))

    def send_bytes(self, data: bytes) -> None:
        """Send one raw MIDI message (e.g. SysEx) unvalidated."""
        if self._handle is None:
            raise MidiError("MIDI output is closed")
        _midi.send_message(self._handle, bytes(data))

    def close(self) -> None:
        """Close the MIDI output port."""
        if self._handle is not None:
            _midi.close_output(self._handle)
            self._handle = None

    def __enter__(self) -> MidiOut:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @staticmethod
    def list_ports() -> list[str]:
        """Return a list of available MIDI output port names."""
        return list(_midi.list_output_ports())


# ---------------------------------------------------------------------------
# MIDI clock bridge
# ---------------------------------------------------------------------------

#: MIDI Timing Clock resolution, in ticks per quarter note.
PPQN = 24


class MidiClockOut:
    """Send MIDI Timing Clock and transport, following a pattern ``Clock``.

    Ticks run on a daemon thread at ``PPQN`` per beat of ``clock.bpm``; tempo
    changes apply from the next tick. :meth:`start` sends ``Start`` and
    begins ticking on the clock's next beat; :meth:`stop` sends ``Stop``.

    Args:
        midi_out: Destination port.
        clock: Tempo source.
    """

    def __init__(self, midi_out: MidiOut, clock: Clock) -> None:
        self._out = midi_out
        self._clock = clock
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        """Whether the tick thread is active."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Send ``Start`` and begin ticking on the clock's next beat."""
        if self.running:
            return
        self._stop_event.clear()
        first_tick = self._clock.next_boundary(1.0)
        self._thread = threading.Thread(
            target=self._run, args=(first_tick,), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop ticking and send ``Stop``."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self._out.send(Stop())

    def _run(self, next_tick: float) -> None:
        tick = _encode(TimingClock())
        self._stop_event.wait(max(0.0, next_tick - time.monotonic()))
        if self._stop_event.is_set():
            return
        self._out.send(Start())
        while not self._stop_event.is_set():
            self._out.send_bytes(tick)
            # Advance from the previous deadline, not the wake time, so OS
            # jitter does not accumulate as tempo drift.
            next_tick += self._clock.beat_duration / PPQN
            # time.sleep, not Event.wait: on Windows (CPython >= 3.11) it uses a
            # high-resolution timer; Event.wait rounds to the ~15.6 ms tick.
            time.sleep(max(0.0, next_tick - time.monotonic()))


class MidiClockIn:
    """Slave a pattern ``Clock`` to incoming MIDI Timing Clock.

    Sets ``clock.bpm`` from the mean tick interval over the last beat, and
    re-anchors the clock's beat grid on each received beat so quantized
    players stay in phase with the master. ``Start`` resets the grid to beat
    0; ``SongPosition`` moves it.

    The ``MidiIn`` must be opened with ``receive_clock=True``.

    Args:
        midi_in: Source port.
        clock: Clock to drive.
    """

    def __init__(self, midi_in: MidiIn, clock: Clock) -> None:
        self._in = midi_in
        self._clock = clock
        self._ticks = 0
        self._last: float | None = None
        self._intervals: deque[float] = deque(maxlen=PPQN)
        self._handlers: list[tuple[type, Callable[[Any], None]]] = [
            (TimingClock, self._on_tick),
            (Start, self._on_start),
            (SongPosition, self._on_song_position),
        ]
        for msg_type, handler in self._handlers:
            midi_in.on(msg_type, handler)

    @property
    def beats(self) -> float:
        """Beats received since the last ``Start`` or ``SongPosition``."""
        return self._ticks / PPQN

    def close(self) -> None:
        """Stop following the incoming clock."""
        for msg_type, handler in self._handlers:
            self._in.off(msg_type, handler)

    def _on_start(self, _msg: Start) -> None:
        self._ticks = 0
        self._last = None
        self._clock.set_beat(0.0)

    def _on_song_position(self, msg: SongPosition) -> None:
        # One MIDI beat (sixteenth note) is 6 clock ticks.
        self._ticks = msg.position * 6
        self._last = None
        self._clock.set_beat(self.beats)

    def _on_tick(self, _msg: TimingClock) -> None:
        now = time.monotonic()
        if self._last is not None:
            self._intervals.append(now - self._last)
        self._last = now
        self._ticks += 1
        if self._ticks % PPQN == 0 and self._intervals:
            mean = sum(self._intervals) / len(self._intervals)
            if mean > 0:
                self._clock.bpm = 60.0 / (mean * PPQN)
            self._clock.set_beat(self.beats)


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
        synth = call(server.synth, synthdef_name, params, SYNTH_PARAMS)
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
            call(server.set, synth, {param_name: scaled}, SET_PARAMS)

    midi_in.on_cc(on_cc)

    def cleanup() -> None:
        midi_in.off_cc(on_cc)

    return cleanup
