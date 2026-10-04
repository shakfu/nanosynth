"""
27_midi_out_clock.py -- MIDI output and MIDI clock.

Opens a MIDI output (a virtual port named "nanosynth" by default, or the first
port matching the name given on the command line), then:

1. sends a program change and a short phrase of notes;
2. sends MIDI clock and transport for four bars at 120 bpm, then 90 bpm,
   following a pattern `Clock` -- a drum machine or DAW slaved to this port
   follows the tempo change.

If ALSA's "Midi Through" port exists, it also loops the clock back into a
`MidiClockIn` and prints the tempo a second `Clock` recovers from it.

Usage:
  python demos/scsynth/27_midi_out_clock.py            # virtual port
  python demos/scsynth/27_midi_out_clock.py "My Synth" # existing port

Requires:
  - nanosynth built with embedded RtMidi (NANOSYNTH_EMBED_MIDI=ON)
"""

import sys
import time

from nanosynth.midi import (
    MidiClockIn,
    MidiClockOut,
    MidiIn,
    MidiOut,
    NoteOff,
    NoteOn,
    ProgramChange,
)
from nanosynth.patterns import Clock


def play_phrase(out: MidiOut) -> None:
    out.send(ProgramChange(channel=0, program=4))
    for note in (60, 64, 67, 72, 67, 64, 60):
        out.send(NoteOn(channel=0, note=note, velocity=96))
        time.sleep(0.2)
        out.send(NoteOff(channel=0, note=note, velocity=0))


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else None
    through = next((n for n in MidiIn.list_ports() if "Midi Through" in n), None)
    if port is None and through is not None:
        port = "Midi Through"  # lets this demo hear its own clock below

    with MidiOut(port) as out:
        print("MIDI out:", port or 'virtual port "nanosynth"')
        print("Program change + phrase")
        play_phrase(out)

        master = Clock(bpm=120.0)
        follower = Clock(bpm=60.0)
        midi_in = MidiIn(through, receive_clock=True) if through else None
        clock_in = MidiClockIn(midi_in, follower) if midi_in else None

        sender = MidiClockOut(out, master)
        sender.start()
        print("MIDI clock: 120 bpm")
        for second in range(8):
            time.sleep(1.0)
            if second == 3:
                master.bpm = 90.0
                print("MIDI clock: 90 bpm")
            if clock_in is not None:
                print(f"  follower clock recovered {follower.bpm:6.2f} bpm")
        sender.stop()

        if midi_in is not None:
            midi_in.close()
        master.stop()
        follower.stop()


if __name__ == "__main__":
    main()
