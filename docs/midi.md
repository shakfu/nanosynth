# MIDI Guide

nanosynth includes a MIDI input layer built on RtMidi (CoreMIDI on macOS, ALSA on Linux, WinMM on Windows). It provides message parsing, handler registration, and high-level helpers for mapping MIDI controllers to synth parameters.

## Listing available ports

Before connecting, check which MIDI devices are visible:

```python
from nanosynth.midi import MidiIn

for i, name in enumerate(MidiIn.list_ports()):
    print(f"  {i}: {name}")
```

## Opening a port

`MidiIn` accepts a port as an integer index, a substring match on the port name, or `None` for a virtual port:

```python
# By index
midi = MidiIn(port=0)

# By name substring (first match wins)
midi = MidiIn(port="Arturia")

# Virtual port (visible to other MIDI software as "nanosynth")
midi = MidiIn()
```

Use a context manager to ensure the port is closed on exit:

```python
with MidiIn(port=0) as midi:
    # ... register handlers, play ...
    pass
# port closed automatically
```

## Message types

Incoming MIDI data is parsed into frozen dataclasses:

| Class | Fields | Notes |
|-------|--------|-------|
| `NoteOn` | `channel`, `note`, `velocity` | Velocity-0 Note On is converted to `NoteOff` |
| `NoteOff` | `channel`, `note`, `velocity` | |
| `ControlChange` | `channel`, `control`, `value` | `value` range: 0--127 |
| `PitchBend` | `channel`, `value` | 14-bit range: 0--16383, center at 8192 |

## Registering handlers

Register one or more callbacks per message type. Handlers are invoked in registration order:

```python
from nanosynth.midi import MidiIn, NoteOn, ControlChange

def on_note(msg: NoteOn) -> None:
    print(f"Note {msg.note} vel {msg.velocity} ch {msg.channel}")

def on_cc(msg: ControlChange) -> None:
    print(f"CC {msg.control} = {msg.value}")

with MidiIn(port=0) as midi:
    midi.on_note_on(on_note)
    midi.on_cc(on_cc)

    input("Press Enter to quit...\n")
```

The full registration API:

| Register | Remove |
|----------|--------|
| `on_note_on(callback)` | `off_note_on(callback)` |
| `on_note_off(callback)` | `off_note_off(callback)` |
| `on_cc(callback)` | `off_cc(callback)` |
| `on_pitch_bend(callback)` | `off_pitch_bend(callback)` |

Multiple handlers on the same message type are all called. Removing a handler that was never registered is a silent no-op.

## Mapping notes to synths

`midi_note_map()` connects MIDI note events to synth creation and release. Note-on creates a synth with `freq` derived from the MIDI note number (A4 = 440 Hz) and `amp` from velocity (0.0--1.0). Note-off sends `gate=0.0` to release the envelope:

```python
import time
from nanosynth import Server, SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import Out, Pan2, SinOsc
from nanosynth.midi import MidiIn, midi_note_map

with SynthDefBuilder(freq=440.0, amp=0.3, gate=1.0) as builder:
    sig = SinOsc.ar(frequency=builder["freq"]) * builder["amp"]
    env = EnvGen.kr(
        envelope=Envelope.adsr(),
        gate=builder["gate"],
        done_action=DoneAction.FREE_SYNTH,
    )
    Out.ar(bus=0, source=Pan2.ar(source=sig * env))

synthdef = builder.build(name="midi_sine")

with Server() as server, MidiIn(port=0) as midi:
    synthdef.send(server)
    time.sleep(0.1)

    cleanup = midi_note_map(midi, server, "midi_sine")

    input("Playing -- press Enter to quit...\n")
    cleanup()
```

The returned cleanup function removes the note-on and note-off handlers. Active synths are tracked internally by `(channel, note)` -- pressing the same key twice releases the first synth before creating a new one.

You can pass additional fixed parameters that are sent to every synth:

```python
cleanup = midi_note_map(midi, server, "midi_sine", amp=0.5)
```

## Mapping CCs to parameters

`midi_cc_map()` maps MIDI CC numbers to synth parameter updates. CC values (0--127) are linearly scaled to a configurable range:

```python
import time
from nanosynth import Server
from nanosynth.midi import MidiIn, midi_cc_map

with Server() as server, MidiIn(port=0) as midi:
    synthdef.send(server)
    time.sleep(0.1)

    node = server.synth("midi_sine", freq=440.0)

    # CC 1 (mod wheel) controls frequency, CC 7 (volume) controls amplitude
    cleanup = midi_cc_map(
        midi, server, node,
        cc_map={1: "freq", 7: "amp"},
        range_min=100.0,
        range_max=2000.0,
    )

    input("Twisting knobs -- press Enter to quit...\n")
    cleanup()
    server.free(node)
```

Unmapped CC numbers are silently ignored. Each parameter shares the same `range_min`/`range_max` -- if you need per-parameter ranges, register separate `on_cc` handlers manually.

## Thread safety

MIDI callbacks are invoked from RtMidi's internal polling thread, not the main thread. Keep handlers fast and non-blocking. If you need to interact with shared state, use your own locking:

```python
import threading

lock = threading.Lock()
notes_held: list[int] = []

def on_note(msg):
    with lock:
        notes_held.append(msg.note)

midi.on_note_on(on_note)
```

The `midi_note_map()` and `midi_cc_map()` helpers call `server.synth()` and `node.set()` from the callback thread. This is safe because `Server.send_msg()` delegates to `EmbeddedProcessProtocol.send_packet()`, which is a synchronous C call with no Python-side locking requirements.
