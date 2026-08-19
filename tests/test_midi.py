"""Tests for MIDI message parsing and handler dispatch.

These tests are pure Python -- no MIDI hardware or _midi C extension needed
for the parsing tests.  MidiIn/handler tests use mocks.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nanosynth.exceptions import MidiError
from nanosynth.midi import (
    ControlChange,
    MidiIn,
    NoteOff,
    NoteOn,
    PitchBend,
    _parse,
    midi_cc_map,
    midi_note_map,
)


# ---------------------------------------------------------------------------
# _parse -- raw byte decoding
# ---------------------------------------------------------------------------


class TestParse:
    def test_note_on_channel_0(self) -> None:
        msg = _parse(bytes([0x90, 60, 100]))
        assert msg == NoteOn(channel=0, note=60, velocity=100)

    def test_note_on_channel_9(self) -> None:
        msg = _parse(bytes([0x99, 42, 80]))
        assert msg == NoteOn(channel=9, note=42, velocity=80)

    def test_note_on_velocity_zero_is_note_off(self) -> None:
        msg = _parse(bytes([0x90, 60, 0]))
        assert msg == NoteOff(channel=0, note=60, velocity=0)

    def test_note_off(self) -> None:
        msg = _parse(bytes([0x80, 60, 64]))
        assert msg == NoteOff(channel=0, note=60, velocity=64)

    def test_note_off_channel_5(self) -> None:
        msg = _parse(bytes([0x85, 72, 0]))
        assert msg == NoteOff(channel=5, note=72, velocity=0)

    def test_control_change(self) -> None:
        msg = _parse(bytes([0xB0, 1, 127]))
        assert msg == ControlChange(channel=0, control=1, value=127)

    def test_cc_channel_3(self) -> None:
        msg = _parse(bytes([0xB3, 74, 64]))
        assert msg == ControlChange(channel=3, control=74, value=64)

    def test_pitch_bend_center(self) -> None:
        # Center = 8192 = 0x2000. LSB=0, MSB=64
        msg = _parse(bytes([0xE0, 0x00, 0x40]))
        assert msg == PitchBend(channel=0, value=8192)

    def test_pitch_bend_min(self) -> None:
        msg = _parse(bytes([0xE0, 0x00, 0x00]))
        assert msg == PitchBend(channel=0, value=0)

    def test_pitch_bend_max(self) -> None:
        msg = _parse(bytes([0xE0, 0x7F, 0x7F]))
        assert msg == PitchBend(channel=0, value=16383)

    def test_empty_data(self) -> None:
        assert _parse(b"") is None

    def test_incomplete_note_on(self) -> None:
        assert _parse(bytes([0x90, 60])) is None

    def test_unknown_status(self) -> None:
        # System exclusive (0xF0) not supported
        assert _parse(bytes([0xF0, 0x7E, 0xF7])) is None

    def test_incomplete_cc(self) -> None:
        assert _parse(bytes([0xB0, 1])) is None


# ---------------------------------------------------------------------------
# MidiIn handler dispatch (mocked _midi backend)
# ---------------------------------------------------------------------------


class TestMidiInDispatch:
    """Test handler registration and dispatch using a mock MidiIn."""

    def _make_midi_in(self) -> MidiIn:
        """Create a MidiIn with a mocked _midi backend."""
        with patch("nanosynth.midi._midi") as mock_backend:
            mock_backend.open_virtual_input.return_value = MagicMock()
            midi = MidiIn(port=None)
        return midi

    def test_note_on_dispatch(self) -> None:
        midi = self._make_midi_in()
        handler = MagicMock()
        midi.on_note_on(handler)
        midi._raw_callback(bytes([0x90, 60, 100]))
        handler.assert_called_once_with(NoteOn(channel=0, note=60, velocity=100))

    def test_note_off_dispatch(self) -> None:
        midi = self._make_midi_in()
        handler = MagicMock()
        midi.on_note_off(handler)
        midi._raw_callback(bytes([0x80, 60, 64]))
        handler.assert_called_once_with(NoteOff(channel=0, note=60, velocity=64))

    def test_cc_dispatch(self) -> None:
        midi = self._make_midi_in()
        handler = MagicMock()
        midi.on_cc(handler)
        midi._raw_callback(bytes([0xB0, 1, 127]))
        handler.assert_called_once_with(ControlChange(channel=0, control=1, value=127))

    def test_pitch_bend_dispatch(self) -> None:
        midi = self._make_midi_in()
        handler = MagicMock()
        midi.on_pitch_bend(handler)
        midi._raw_callback(bytes([0xE0, 0x00, 0x40]))
        handler.assert_called_once_with(PitchBend(channel=0, value=8192))

    def test_multiple_handlers(self) -> None:
        midi = self._make_midi_in()
        h1 = MagicMock()
        h2 = MagicMock()
        midi.on_note_on(h1)
        midi.on_note_on(h2)
        midi._raw_callback(bytes([0x90, 60, 100]))
        h1.assert_called_once()
        h2.assert_called_once()

    def test_off_removes_handler(self) -> None:
        midi = self._make_midi_in()
        handler = MagicMock()
        midi.on_note_on(handler)
        midi.off_note_on(handler)
        midi._raw_callback(bytes([0x90, 60, 100]))
        handler.assert_not_called()

    def test_off_nonexistent_handler_is_noop(self) -> None:
        midi = self._make_midi_in()
        handler = MagicMock()
        midi.off_note_on(handler)  # should not raise

    def test_velocity_zero_dispatches_note_off(self) -> None:
        midi = self._make_midi_in()
        on_handler = MagicMock()
        off_handler = MagicMock()
        midi.on_note_on(on_handler)
        midi.on_note_off(off_handler)
        midi._raw_callback(bytes([0x90, 60, 0]))
        on_handler.assert_not_called()
        off_handler.assert_called_once()

    def test_unknown_message_no_dispatch(self) -> None:
        midi = self._make_midi_in()
        handler = MagicMock()
        midi.on_note_on(handler)
        midi._raw_callback(bytes([0xF0, 0x7E, 0xF7]))
        handler.assert_not_called()


# ---------------------------------------------------------------------------
# MidiIn construction (mocked _midi backend)
# ---------------------------------------------------------------------------


class TestMidiInConstruction:
    def test_open_virtual(self) -> None:
        with patch("nanosynth.midi._midi") as mock:
            mock.open_virtual_input.return_value = MagicMock()
            midi = MidiIn(port=None)
            mock.open_virtual_input.assert_called_once_with("nanosynth")
            midi.close()

    def test_open_by_index(self) -> None:
        with patch("nanosynth.midi._midi") as mock:
            mock.open_input.return_value = MagicMock()
            midi = MidiIn(port=0)
            mock.open_input.assert_called_once_with(0, "nanosynth")
            midi.close()

    def test_open_by_name(self) -> None:
        with patch("nanosynth.midi._midi") as mock:
            mock.list_input_ports.return_value = ["Port A", "My Controller"]
            mock.open_input.return_value = MagicMock()
            midi = MidiIn(port="Controller")
            mock.open_input.assert_called_once_with(1, "nanosynth")
            midi.close()

    def test_open_by_name_not_found(self) -> None:
        with patch("nanosynth.midi._midi") as mock:
            mock.list_input_ports.return_value = ["Port A"]
            with pytest.raises(MidiError, match="No MIDI port matching"):
                MidiIn(port="Nonexistent")

    def test_context_manager(self) -> None:
        with patch("nanosynth.midi._midi") as mock:
            mock.open_virtual_input.return_value = MagicMock()
            with MidiIn(port=None):
                pass
            mock.close_input.assert_called_once()


# ---------------------------------------------------------------------------
# High-level helpers (mocked server)
# ---------------------------------------------------------------------------


class TestMidiNoteMap:
    def test_note_on_creates_synth(self) -> None:
        with patch("nanosynth.midi._midi") as mock:
            mock.open_virtual_input.return_value = MagicMock()
            midi = MidiIn(port=None)

        server = MagicMock()
        synth_mock = MagicMock()
        server.synth.return_value = synth_mock

        cleanup = midi_note_map(midi, server, "pad", pan=0.0)

        # Simulate note on
        midi._raw_callback(bytes([0x90, 69, 100]))
        server.synth.assert_called_once()
        args, kwargs = server.synth.call_args
        assert args[0] == "pad"
        assert kwargs["freq"] == pytest.approx(440.0)
        assert kwargs["pan"] == 0.0

        # Simulate note off
        midi._raw_callback(bytes([0x80, 69, 0]))
        server.set.assert_called_once_with(synth_mock, gate=0.0)

        cleanup()

    def test_retrigger_gates_previous_voice(self) -> None:
        """A second Note-On for a held key gates the first synth off (M8)."""
        with patch("nanosynth.midi._midi") as mock:
            mock.open_virtual_input.return_value = MagicMock()
            midi = MidiIn(port=None)

        server = MagicMock()
        first, second = MagicMock(name="first"), MagicMock(name="second")
        server.synth.side_effect = [first, second]

        cleanup = midi_note_map(midi, server, "pad")
        midi._raw_callback(bytes([0x90, 69, 100]))  # note on
        midi._raw_callback(bytes([0x90, 69, 110]))  # retrigger, no note-off
        # The first voice must have been gated off, not leaked.
        server.set.assert_any_call(first, gate=0.0)
        assert server.synth.call_count == 2
        cleanup()

    def test_cleanup_removes_handlers(self) -> None:
        with patch("nanosynth.midi._midi") as mock:
            mock.open_virtual_input.return_value = MagicMock()
            midi = MidiIn(port=None)

        server = MagicMock()
        cleanup = midi_note_map(midi, server, "pad")
        cleanup()

        # After cleanup, note on should not create a synth
        midi._raw_callback(bytes([0x90, 60, 100]))
        server.synth.assert_not_called()

    def test_cleanup_gates_held_voices(self) -> None:
        """cleanup() releases any voices still held (M8)."""
        with patch("nanosynth.midi._midi") as mock:
            mock.open_virtual_input.return_value = MagicMock()
            midi = MidiIn(port=None)

        server = MagicMock()
        held = MagicMock(name="held")
        server.synth.return_value = held

        cleanup = midi_note_map(midi, server, "pad")
        midi._raw_callback(bytes([0x90, 64, 100]))  # note on, never released
        cleanup()
        server.set.assert_any_call(held, gate=0.0)


class TestMidiCcMap:
    def test_cc_sets_param(self) -> None:
        with patch("nanosynth.midi._midi") as mock:
            mock.open_virtual_input.return_value = MagicMock()
            midi = MidiIn(port=None)

        server = MagicMock()
        synth_mock = MagicMock()

        cleanup = midi_cc_map(
            midi,
            server,
            synth_mock,
            cc_map={1: "frequency"},
            range_min=100.0,
            range_max=1000.0,
        )

        # CC 1 at value 127 -> max of range
        midi._raw_callback(bytes([0xB0, 1, 127]))
        server.set.assert_called_once()
        _, kwargs = server.set.call_args
        assert kwargs["frequency"] == pytest.approx(1000.0)

        server.set.reset_mock()

        # CC 1 at value 0 -> min of range
        midi._raw_callback(bytes([0xB0, 1, 0]))
        _, kwargs = server.set.call_args
        assert kwargs["frequency"] == pytest.approx(100.0)

        # Unmapped CC should not trigger set
        server.set.reset_mock()
        midi._raw_callback(bytes([0xB0, 99, 64]))
        server.set.assert_not_called()

        cleanup()


# ---------------------------------------------------------------------------
# Message dataclass properties
# ---------------------------------------------------------------------------


class TestMessageDataclasses:
    def test_note_on_frozen(self) -> None:
        msg = NoteOn(channel=0, note=60, velocity=100)
        with pytest.raises(AttributeError):
            msg.note = 61  # type: ignore[misc]

    def test_note_off_equality(self) -> None:
        assert NoteOff(0, 60, 64) == NoteOff(0, 60, 64)
        assert NoteOff(0, 60, 64) != NoteOff(0, 61, 64)

    def test_cc_repr(self) -> None:
        msg = ControlChange(channel=0, control=1, value=127)
        assert "control=1" in repr(msg)

    def test_pitch_bend_hash(self) -> None:
        s = {PitchBend(0, 8192), PitchBend(0, 8192), PitchBend(1, 8192)}
        assert len(s) == 2
