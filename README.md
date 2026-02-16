# nanosynth

nanosynth is a Python package that embeds SuperCollider's [libscsynth](https://github.com/supercollider/supercollider) synthesis engine in-process using [nanobind](https://github.com/wjakob/nanobind). It makes it possible to define SynthDefs in Python, compile them to SuperCollider's `SCgf` binary format, boot the embedded audio engine, and control it via OSC -- all without leaving Python.

## Features

- **Self-contained with embedded synthesis engine** -- libscsynth runs in-process as a Python extension (vendored and built from source), no separate scsynth process required

- **High-level `Server` class** -- boot/quit lifecycle, node ID allocation, SynthDef dispatch, buffer management, OSC reply handling, and convenience methods (`synth`, `group`, `free`, `set`). Context manager support and `managed_synth()`/`managed_group()`/`managed_buffer()` for automatic resource cleanup

- **Pythonic SynthDef builder** -- define UGen graphs using a context manager and operator overloading, compiled to SuperCollider's `SCgf` binary format

- **340+ UGens** -- oscillators, filters, delays, noise, chaos, granular, demand, dynamics, panning, physical modeling, reverb, phase vocoder, machine listening, stochastic synthesis, and more

- **Rich operator algebra** -- 43 binary and 34 unary operators on all UGen signals, including arithmetic, comparison, bitwise, power, trig, pitch conversion (`midicps`/`cpsmidi`), clipping (`clip2`/`fold2`/`wrap2`), and more. Compile-time constant folding and algebraic optimizations

- **Non-real-time (NRT) rendering** -- `Score` class for offline audio rendering to WAV/AIFF files without audio hardware. Timestamped OSC commands are serialized and rendered by the embedded engine

- **Bus allocation** -- `Bus` proxy class with `Server.audio_bus()`, `Server.control_bus()`, `managed_audio_bus()`, `managed_control_bus()`. Eliminates hardcoded magic bus numbers in effect chains. `int()` compatible for passing as synth parameters

- **Pattern sequencing** -- `Pbind`, `Pseq`, `Prand`, `Pwhite`, `Pseries`, `Pgeom`, `Pchoose`, `Pn`, `Pconst`, `Rest`, `Clock`, and `Player` for musical event scheduling. Patterns are reusable iterables; `Pbind` produces event streams that drive synth creation with automatic gate release. `Clock` provides tempo-driven playback with drift-free scheduling

- **MIDI input** -- `MidiIn` class for receiving MIDI from hardware controllers (via embedded RtMidi: CoreMIDI on macOS, ALSA on Linux, WinMM on Windows). Parsed message types (`NoteOn`, `NoteOff`, `ControlChange`, `PitchBend`) with handler registration. High-level helpers: `midi_note_map()` for polyphonic note-to-synth mapping, `midi_cc_map()` for CC-to-parameter control

- **NodeProxy / Ndef** -- live coding with hot-swappable synth definitions. `NodeProxy` owns a private audio bus, a source synth (with ASR envelope for crossfade), and a monitor synth. Swap the source seamlessly while audio plays. `Ndef` is a global named proxy registry for concise live-coding workflows

- **Server recording** -- `Server.record(path)` captures real-time audio output to WAV/AIFF via DiskOut. `stop_recording()` finalizes the file. Configurable channel count, bus, and format

- **Buffer management** -- `alloc_buffer`, `read_buffer`, `write_buffer`, `free_buffer`, `zero_buffer`, `close_buffer`, and context managers for automatic cleanup

- **Reply handling** -- bidirectional OSC communication with the engine: persistent handlers (`on`/`off`), blocking one-shot waits (`wait_for_reply`), and send-and-wait (`send_msg_sync`)

- **SynthDef graph introspection** -- `SynthDef.graph()` returns a structured DAG of `UGenNode`/`UGenInput` NamedTuples for programmatic traversal. `SynthDef.to_dot()` exports to Graphviz DOT format

- **Envelope system** -- `Envelope` class with factory methods (`adsr`, `asr`, `linen`, `percussive`, `triangle`) and the `EnvGen` UGen

- **OSC codec** -- pure-Python `OscMessage`/`OscBundle` encode/decode with optional C++ acceleration via nanobind

- **`@synthdef` decorator** -- shorthand for defining SynthDefs as plain functions with parameter rate/lag annotations

- **Full type safety** -- passes `mypy --strict`, complete type annotations throughout

## Requirements

- Python 3.10+

- [uv](https://github.com/astral-sh/uv) (package manager)

- For embedded scsynth: SuperCollider 3.14.1, libsndfile, and PortAudio are vendored and built from source automatically. Audio backend: CoreAudio on macOS, PortAudio (ALSA) on Linux, PortAudio (WASAPI) on Windows -- no system-level audio dependencies beyond the compiler toolchain.

## Installation

```sh
pip install nanosynth
```

Or build from source:

```sh
# Editable install with embedded libscsynth
uv pip install -e .

# Build wheel (incremental -- reuses cmake build cache in build/)
make build

# Install without the audio engine (OSC codec + SynthDef compiler only)
uv pip install -e . -C cmake.define.NANOSYNTH_EMBED_SCSYNTH=OFF
```

## Quick Start

### Run the Audio Demos

```sh
make demos
```

### Define a SynthDef and Play It

The `Server` class manages the embedded engine lifecycle. Define a SynthDef, boot the server, and play:

```python
import time
from nanosynth import Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import Out, Pan2, SinOsc

# Define a SynthDef
with SynthDefBuilder(frequency=440.0, amplitude=0.3) as builder:
    sig = SinOsc.ar(frequency=builder["frequency"])
    sig = sig * builder["amplitude"]
    env = EnvGen.kr(
        envelope=Envelope.linen(attack_time=0.1, sustain_time=1.8, release_time=0.1),
        done_action=DoneAction.FREE_SYNTH,
    )
    sig = sig * env
    Out.ar(bus=0, source=Pan2.ar(source=sig))

synthdef = builder.build(name="sine")

# Boot the server, send the SynthDef, create a synth
with Server(Options(verbosity=0)) as server:
    synthdef.send(server)
    time.sleep(0.1)

    node = server.synth("sine", frequency=440.0, amplitude=0.3)
    print(f"Playing 440 Hz sine (node {node}) for 2 seconds...")
    time.sleep(2.0)
    server.free(node)

# Engine shuts down automatically on context exit
```

Or use `SynthDef.play()` to send and create a synth in one call:

```python
with Server() as server:
    node = synthdef.play(server, frequency=880.0, amplitude=0.2)
    time.sleep(2.0)
```

### Managed Nodes (Automatic Cleanup)

`managed_synth()` and `managed_group()` create nodes that are automatically freed on context exit, even if an exception occurs:

```python
import time
from nanosynth import Server

with Server() as server:
    synthdef.send(server)
    time.sleep(0.1)

    with server.managed_synth("sine", frequency=440.0, amplitude=0.3) as node:
        print(f"Playing node {node}...")
        time.sleep(2.0)
    # node freed automatically here

    # Group multiple voices and free them together
    with server.managed_group(target=1) as group:
        server.synth("sine", target=group, frequency=261.63, amplitude=0.2)
        server.synth("sine", target=group, frequency=329.63, amplitude=0.2)
        server.synth("sine", target=group, frequency=392.00, amplitude=0.2)
        time.sleep(2.0)
    # entire group freed here
```

### Effect Chains with Bus Allocation

Use `AddAction` to control node execution order and `audio_bus()` to allocate private buses for effect routing -- no more hardcoded magic bus numbers:

```python
import time
from nanosynth import AddAction, Options, Server

with Server(Options(verbosity=0)) as server:
    src_def.send(server)
    delay_def.send(server)
    time.sleep(0.1)

    # Allocate a private bus for routing source -> effect
    with server.managed_audio_bus(2) as fx_bus:
        # Source group executes first, effect group after
        src_group = server.group(target=1, action=AddAction.ADD_TO_HEAD)
        fx_group = server.group(target=int(src_group), action=AddAction.ADD_AFTER)

        # Effect reads from the allocated bus, writes to hardware output
        server.synth("comb_delay", target=int(fx_group),
                     in_bus=float(int(fx_bus)), delay_time=0.375, mix=0.4)

        # Source writes to the allocated bus
        server.synth("perc_src", target=int(src_group),
                     out_bus=float(int(fx_bus)), frequency=440.0)
        time.sleep(2.0)
    # bus freed automatically
```

### Recording

Capture real-time audio output to a file:

```python
import time
from nanosynth import Server

with Server() as server:
    synthdef.send(server)
    time.sleep(0.1)

    # Start recording to WAV
    server.record("output.wav", header_format="wav", sample_format="int16")

    # Play some audio
    node = server.synth("sine", frequency=440.0, amplitude=0.3)
    time.sleep(2.0)
    server.free(node)

    # Stop recording -- finalizes the file
    server.stop_recording()
```

Recording options include `num_channels` (defaults to output bus count), `bus` (which bus to record from), `header_format` (`"wav"` or `"aiff"`), and `sample_format` (`"int16"`, `"int24"`, `"float"`).

### Offline (NRT) Rendering

Render audio to a file without real-time audio hardware -- useful for batch processing, testing, and CI pipelines:

```python
from nanosynth import Score, SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import Out, Pan2, SinOsc

# Define a SynthDef
with SynthDefBuilder(freq=440.0, amp=0.3) as builder:
    sig = SinOsc.ar(frequency=builder["freq"]) * builder["amp"]
    env = EnvGen.kr(
        envelope=Envelope.percussive(attack_time=0.01, release_time=0.5),
        done_action=DoneAction.FREE_SYNTH,
    )
    Out.ar(bus=0, source=Pan2.ar(source=sig * env))
sd = builder.build(name="sine")

# Build a Score -- a sequence of timestamped OSC commands
score = Score()
score.add_synthdef(0.0, sd)
score.add_synth(0.0, "sine", freq=440.0, amp=0.3)
score.add_synth(0.5, "sine", freq=554.37, amp=0.2)
score.add_synth(1.0, "sine", freq=659.26, amp=0.2)

# Render to a WAV file (no audio hardware needed)
score.render("output.wav", sample_rate=44100, header_format="WAV", sample_format="int16")
```

### Pattern Sequencing

Replace manual `time.sleep()` loops with musical patterns. `Pbind` binds keys to patterns or scalars to produce event streams; `Clock` drives playback at a given tempo:

```python
import time
from nanosynth import Options, Server
from nanosynth.patterns import Clock, Pbind, Prand, Pseq, Pwhite, Rest

with Server(Options(verbosity=0)) as server:
    # (assume a "default" SynthDef with freq, amp, gate params is loaded)
    clock = Clock(bpm=140)

    # Ascending melody
    melody = Pbind(
        instrument="default",
        freq=Pseq([261.63, 293.66, 329.63, 392.00, 440.00]),
        dur=Pseq([0.5, 0.5, 0.5, 0.5, 1.0]),
        amp=0.2,
    )
    melody.play(clock, server)
    time.sleep(3.0)

    # Randomized melody with rests and dynamic amplitude
    rand_melody = Pbind(
        instrument="default",
        freq=Prand([261.63, 329.63, 392.00, 440.00], repeats=8),
        dur=Pseq([0.25, 0.25, Rest(0.5), 0.5], repeats=2),
        amp=Pwhite(0.1, 0.25, repeats=8),
    )
    player = rand_melody.play(clock, server)
    time.sleep(4.0)

    player.stop()
    clock.stop()
```

Available patterns: `Pseq` (sequential), `Prand` (random choice), `Pwhite` (uniform random float), `Pseries` (arithmetic series), `Pgeom` (geometric series), `Pchoose` (weighted random), `Pn` (repeat N times), `Pconst` (yield until sum reaches total). Patterns support chaining with `|` and preview with `.take(n)`.

### MIDI Input

Connect hardware MIDI controllers. Requires the `_midi` C extension (built by default with `NANOSYNTH_EMBED_MIDI=ON`):

```python
import time
from nanosynth import Options, Server
from nanosynth.midi import MidiIn, midi_note_map, midi_cc_map

# List available MIDI ports
print(MidiIn.list_ports())

with Server(Options(verbosity=0)) as server:
    # (assume a gated SynthDef "synth" is loaded)

    with MidiIn(port=0) as midi:
        # Polyphonic note mapping: note-on creates synth, note-off sends gate=0
        cleanup_notes = midi_note_map(midi, server, "synth")

        # Map CC1 (mod wheel) to a parameter on an existing synth
        # cleanup_cc = midi_cc_map(midi, server, some_synth,
        #                          cc_map={1: "cutoff"}, range_min=200.0, range_max=8000.0)

        # Or register handlers directly
        midi.on_note_on(lambda msg: print(f"Note {msg.note} vel {msg.velocity}"))
        midi.on_cc(lambda msg: print(f"CC {msg.control} = {msg.value}"))

        input("Press Enter to quit...")
        cleanup_notes()
```

### NodeProxy / Ndef (Live Coding)

Hot-swap synth definitions while audio plays. `NodeProxy` manages a private audio bus, source synth, and monitor synth -- swapping replaces only the source with a crossfade:

```python
import time
from nanosynth import Options, Server
from nanosynth.proxy import Ndef, NodeProxy
from nanosynth.ugens import LFNoise1, LPF, Saw, SinOsc

with Server(Options(verbosity=0)) as server:
    # NodeProxy: manual usage
    proxy = NodeProxy(server)
    proxy.source = lambda: SinOsc.ar(frequency=440) * 0.2
    proxy.play()
    time.sleep(2.0)

    # Hot-swap to saw wave (crossfades automatically)
    proxy.source = lambda: Saw.ar(frequency=330) * 0.15
    time.sleep(2.0)

    proxy.clear()

    # Ndef: concise named proxy registry
    Ndef(server, "pad", lambda: SinOsc.ar(frequency=220) * 0.2)
    Ndef(server, "pad").play()
    time.sleep(1.5)

    # Hot-swap via Ndef
    Ndef(server, "pad", lambda: Saw.ar(frequency=165) * 0.15)
    time.sleep(1.5)

    Ndef.clear_all(server)
```

## Synthesis Techniques

The following examples show SynthDef definitions for various synthesis techniques. Each can be played using the `Server` class as shown above.

### Using the `@synthdef` Decorator

For simpler definitions, use the decorator to skip the builder boilerplate. Parameter rates and lags are specified positionally:

```python
from nanosynth import synthdef, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import Out, Pan2, SinOsc

@synthdef("kr", ("kr", 0.5))  # freq: control rate, amp: control rate with 0.5s lag
def my_sine(freq=440.0, amp=0.3):
    sig = SinOsc.ar(frequency=freq)
    env = EnvGen.kr(
        envelope=Envelope.percussive(attack_time=0.01, release_time=1.0),
        done_action=DoneAction.FREE_SYNTH,
    )
    Out.ar(bus=0, source=Pan2.ar(source=sig * amp * env))

scgf_bytes = my_sine.compile()  # my_sine is a SynthDef instance
```

### Subtractive Synthesis

```python
from nanosynth import SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import LFNoise1, LPF, Out, Pan2, RLPF, Saw, WhiteNoise, XLine

# Saw wave through a sweeping low-pass filter
with SynthDefBuilder(frequency=110.0, amplitude=0.4) as builder:
    sig = Saw.ar(frequency=builder["frequency"])
    cutoff = XLine.kr(start=8000.0, stop=200.0, duration=3.0,
                      done_action=DoneAction.FREE_SYNTH)
    sig = LPF.ar(source=sig, frequency=cutoff)
    sig = sig * builder["amplitude"]
    Out.ar(bus=0, source=Pan2.ar(source=sig))

filtered_saw = builder.build(name="filtered_saw")

# White noise through a resonant LPF with LFO-modulated cutoff
with SynthDefBuilder(amplitude=0.15) as builder:
    sig = WhiteNoise.ar()
    lfo = LFNoise1.kr(frequency=4.0)
    cutoff = lfo * 1900.0 + 2100.0  # map [-1,1] to [200, 4000]
    sig = RLPF.ar(source=sig, frequency=cutoff, reciprocal_of_q=0.1)
    env = EnvGen.kr(
        envelope=Envelope.linen(attack_time=0.5, sustain_time=2.0, release_time=0.5),
        done_action=DoneAction.FREE_SYNTH,
    )
    sig = sig * env * builder["amplitude"]
    Out.ar(bus=0, source=Pan2.ar(source=sig))

resonant_noise = builder.build(name="resonant_noise")
```

### FM Synthesis

```python
from nanosynth import SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import Out, Pan2, SinOsc

with SynthDefBuilder(
    carrier_freq=440.0, mod_ratio=2.0, mod_index=3.0,
    amplitude=0.3, gate=1.0,
) as builder:
    mod_freq = builder["carrier_freq"] * builder["mod_ratio"]
    modulator = SinOsc.ar(frequency=mod_freq) * builder["mod_index"] * mod_freq
    carrier = SinOsc.ar(frequency=builder["carrier_freq"] + modulator)
    env = EnvGen.kr(
        envelope=Envelope.adsr(
            attack_time=0.01, decay_time=0.1, sustain=0.7, release_time=0.3,
        ),
        gate=builder["gate"],
        done_action=DoneAction.FREE_SYNTH,
    )
    sig = carrier * env * builder["amplitude"]
    Out.ar(bus=0, source=Pan2.ar(source=sig))

fm_synth = builder.build(name="fm_synth")
```

### Additive Synthesis

Sum harmonics with decreasing amplitude to build a rich tone from pure sine partials:

```python
from nanosynth import SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import Out, Pan2, SinOsc

with SynthDefBuilder(frequency=200.0, amplitude=0.3) as builder:
    sig = SinOsc.ar(frequency=builder["frequency"]) * 1.0
    sig = sig + SinOsc.ar(frequency=builder["frequency"] * 2.0) * 0.5
    sig = sig + SinOsc.ar(frequency=builder["frequency"] * 3.0) * 0.33
    sig = sig + SinOsc.ar(frequency=builder["frequency"] * 4.0) * 0.25
    sig = sig + SinOsc.ar(frequency=builder["frequency"] * 5.0) * 0.2
    sig = sig * 0.3  # normalize
    env = EnvGen.kr(
        envelope=Envelope.percussive(attack_time=0.01, release_time=2.0),
        done_action=DoneAction.FREE_SYNTH,
    )
    sig = sig * env * builder["amplitude"]
    Out.ar(bus=0, source=Pan2.ar(source=sig))

additive = builder.build(name="additive")
```

### Plucked String (Physical Modeling)

Karplus-Strong style plucked string using the `Pluck` UGen:

```python
from nanosynth import SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import Dust, Out, Pan2, Pluck, WhiteNoise

with SynthDefBuilder(frequency=440.0, amplitude=0.5, decay=5.0) as builder:
    trig = Dust.ar(density=1.0)
    sig = Pluck.ar(
        source=WhiteNoise.ar(),
        trigger=trig,
        maximum_delay_time=1.0 / 100.0,
        delay_time=1.0 / builder["frequency"],
        decay_time=builder["decay"],
        coefficient=0.3,
    )
    sig = sig * builder["amplitude"]
    Out.ar(bus=0, source=Pan2.ar(source=sig))

pluck = builder.build(name="plucked_string")
```

### Delay and Reverb Effects

Process a dry signal through comb delay and FreeVerb:

```python
from nanosynth import SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import CombC, FreeVerb, Out, Pan2, Saw, LPF

with SynthDefBuilder(frequency=220.0, amplitude=0.3) as builder:
    # Dry signal: filtered saw
    dry = Saw.ar(frequency=builder["frequency"])
    dry = LPF.ar(source=dry, frequency=2000.0)
    env = EnvGen.kr(
        envelope=Envelope.percussive(attack_time=0.005, release_time=0.3),
        done_action=DoneAction.FREE_SYNTH,
    )
    dry = dry * env * builder["amplitude"]

    # Comb delay for metallic echo
    sig = CombC.ar(
        source=dry,
        maximum_delay_time=0.2,
        delay_time=0.15,
        decay_time=2.0,
    )

    # Reverb
    sig = FreeVerb.ar(source=dry + sig, mix=0.4, room_size=0.8, damping=0.3)
    Out.ar(bus=0, source=Pan2.ar(source=sig))

delay_reverb = builder.build(name="delay_reverb")
```

### Demand-Rate Sequencing

Use demand UGens to sequence pitches without host-side scheduling:

```python
from nanosynth import SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import Duty, Dseq, Out, Pan2, SinOsc

with SynthDefBuilder(amplitude=0.3) as builder:
    # Dseq loops a sequence of MIDI-note frequencies at demand rate
    freq_pattern = Dseq.dr(
        repeats=4,
        sequence=[261.63, 293.66, 329.63, 392.00, 440.00, 392.00, 329.63, 293.66],
    )
    # Duty reads from the demand pattern every 0.25 seconds
    freq = Duty.kr(duration=0.25, level=freq_pattern)
    sig = SinOsc.ar(frequency=freq) * builder["amplitude"]
    env = EnvGen.kr(
        envelope=Envelope.linen(attack_time=0.01, sustain_time=7.9, release_time=0.1),
        done_action=DoneAction.FREE_SYNTH,
    )
    sig = sig * env
    Out.ar(bus=0, source=Pan2.ar(source=sig))

sequencer = builder.build(name="sequencer")
```

### Ring Modulation

Multiply two signals together for classic ring modulation:

```python
from nanosynth import SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import LFTri, Out, Pan2, SinOsc

with SynthDefBuilder(
    carrier_freq=440.0, mod_freq=60.0, amplitude=0.3,
) as builder:
    carrier = SinOsc.ar(frequency=builder["carrier_freq"])
    modulator = LFTri.ar(frequency=builder["mod_freq"])
    sig = carrier * modulator  # ring mod = simple multiplication
    env = EnvGen.kr(
        envelope=Envelope.linen(attack_time=0.05, sustain_time=2.0, release_time=0.5),
        done_action=DoneAction.FREE_SYNTH,
    )
    sig = sig * env * builder["amplitude"]
    Out.ar(bus=0, source=Pan2.ar(source=sig))

ring_mod = builder.build(name="ring_mod")
```

### Stereo Width with Detuning

Fatten a sound by panning two slightly detuned oscillators:

```python
from nanosynth import SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import LPF, Out, Saw

with SynthDefBuilder(frequency=110.0, detune=0.5, amplitude=0.4) as builder:
    left = Saw.ar(frequency=builder["frequency"] - builder["detune"])
    right = Saw.ar(frequency=builder["frequency"] + builder["detune"])
    left = LPF.ar(source=left, frequency=3000.0)
    right = LPF.ar(source=right, frequency=3000.0)
    env = EnvGen.kr(
        envelope=Envelope.linen(attack_time=0.1, sustain_time=2.0, release_time=0.5),
        done_action=DoneAction.FREE_SYNTH,
    )
    left = left * env * builder["amplitude"]
    right = right * env * builder["amplitude"]
    Out.ar(bus=0, source=[left, right])  # direct stereo output

stereo_saw = builder.build(name="stereo_saw")
```

### Dynamics Processing

Apply compression to a signal using `Compander`:

```python
from nanosynth import SynthDefBuilder, DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import Compander, Dust, Out, Pan2, Ringz

with SynthDefBuilder(amplitude=0.5) as builder:
    # Sparse impulses through a resonant filter -- wide dynamic range
    sig = Ringz.ar(
        source=Dust.ar(density=3.0),
        frequency=2000.0,
        decay_time=0.2,
    )
    # Compress: bring quiet parts up, loud parts down
    sig = Compander.ar(
        source=sig,
        control=sig,
        threshold=0.3,
        slope_below=2.0,   # expand below threshold
        slope_above=0.5,   # compress above threshold
        clamp_time=0.01,
        relax_time=0.1,
    )
    env = EnvGen.kr(
        envelope=Envelope.linen(attack_time=0.01, sustain_time=3.0, release_time=0.5),
        done_action=DoneAction.FREE_SYNTH,
    )
    sig = sig * env * builder["amplitude"]
    Out.ar(bus=0, source=Pan2.ar(source=sig))

compressed = builder.build(name="compressed")
```

## Advanced Features

### SynthDef Compilation (No Engine Required)

SynthDef graphs can be compiled to SuperCollider's SCgf binary format without booting the audio engine -- useful for generating SynthDefs for any SuperCollider server:

```python
from nanosynth import SynthDefBuilder, compile_synthdefs
from nanosynth.ugens import Out, Pan2, SinOsc

with SynthDefBuilder(frequency=440.0) as builder:
    Out.ar(bus=0, source=Pan2.ar(source=SinOsc.ar(frequency=builder["frequency"])))

synthdef = builder.build(name="sine")
scgf_bytes = synthdef.compile()

# Or compile multiple SynthDefs into a single SCgf blob
blob = compile_synthdefs(synthdef1, synthdef2, synthdef3)
```

### Debugging SynthDef Graphs

`SynthDef.dump_ugens()` prints a human-readable UGen graph (like SuperCollider's `SynthDef.dumpUGens`):

```python
print(synthdef.dump_ugens())
# SynthDef: sine
#   0: Control.kr - frequency, amplitude
#   1: SinOsc.ar(frequency: Control[0], phase: 0.0)
#   2: BinaryOpUGen.ar(MULTIPLICATION, a: SinOsc[0], b: Control[1])
#   ...
```

### SynthDef Graph Introspection

Walk the UGen graph programmatically or export to Graphviz DOT format:

```python
# Structured graph -- returns UGenNode/UGenInput NamedTuples
graph = sd.graph()
for node in graph.nodes:
    print(f"{node.node_index}: {node.type_name}.{node.rate}")
    for inp in node.inputs:
        if inp.source is not None:
            print(f"  {inp.name} <- {inp.source.type_name}[{inp.output_index}]")
        else:
            print(f"  {inp.name} = {inp.value}")

# Export to Graphviz DOT
dot = sd.to_dot(rankdir="LR")
print(dot)  # pipe to `dot -Tpng -o graph.png`
```

### OSC Codec

The OSC module works standalone for any OSC communication needs:

```python
from nanosynth import OscMessage, OscBundle

# Encode
msg = OscMessage("/s_new", "sine", 1000, 0, 1, "frequency", 440.0)
datagram = msg.to_datagram()

# Decode
decoded = OscMessage.from_datagram(datagram)
assert decoded == msg

# Bundles
bundle = OscBundle(
    timestamp=None,  # immediately
    contents=[
        OscMessage("/s_new", "sine", 1000, 0, 1),
        OscMessage("/n_set", 1000, "frequency", 880.0),
    ],
)
bundle_bytes = bundle.to_datagram()
```

## Available UGens

Organized by category:

| Category | UGens |
|---|---|
| **Oscillators** | `SinOsc`, `Saw`, `Pulse`, `Blip`, `Klank`, `LFSaw`, `LFPulse`, `LFTri`, `LFCub`, `LFPar`, `VarSaw`, `SyncSaw`, `Impulse`, `FSinOsc`, `LFGauss`, `Vibrato`, `Osc`, `OscN`, `COsc`, `VOsc`, `VOsc3` |
| **Filters** | `LPF`, `HPF`, `BPF`, `BRF`, `RLPF`, `RHPF`, `MoogFF`, `Lag`, `Lag2`, `Lag3`, `LagUD`, `Lag2UD`, `Lag3UD`, `Ramp`, `Decay`, `Decay2`, `Ringz`, `Formlet`, `Median`, `LeakDC`, `OnePole`, `OneZero`, `TwoPole`, `TwoZero`, `APF`, `FOS`, `SOS`, `MidEQ`, `Slew`, `Slope`, `Integrator`, `DetectSilence`, `Changed` |
| **BEQ Filters** | `BLowPass`, `BHiPass`, `BBandPass`, `BBandStop`, `BAllPass`, `BLowShelf`, `BHiShelf`, `BPeakEQ`, `BLowCut`, `BHiCut` |
| **Noise** | `WhiteNoise`, `PinkNoise`, `BrownNoise`, `GrayNoise`, `ClipNoise`, `Dust`, `Dust2`, `Crackle`, `LFNoise0`, `LFNoise1`, `LFNoise2`, `LFDNoise0`, `LFDNoise1`, `LFDNoise3`, `LFClipNoise`, `LFDClipNoise`, `Logistic` |
| **Stochastic** | `Gendy1`, `Gendy2`, `Gendy3` |
| **Delays** | `DelayN`, `DelayL`, `DelayC`, `Delay1`, `Delay2`, `CombN`, `CombL`, `CombC`, `AllpassN`, `AllpassL`, `AllpassC`, `BufDelayN`, `BufDelayL`, `BufDelayC`, `BufCombN`, `BufCombL`, `BufCombC`, `BufAllpassN`, `BufAllpassL`, `BufAllpassC`, `DelTapRd`, `DelTapWr` |
| **Envelopes** | `EnvGen`, `Linen`, `Done`, `Free`, `FreeSelf`, `FreeSelfWhenDone`, `Pause`, `PauseSelf`, `PauseSelfWhenDone` |
| **Panning** | `Pan2`, `Pan4`, `PanAz`, `PanB`, `PanB2`, `BiPanB2`, `Balance2`, `Rotate2`, `DecodeB2`, `XFade2`, `Splay` |
| **Demand** | `Dseq`, `Dser`, `Dseries`, `Drand`, `Dxrand`, `Dshuf`, `Dwrand`, `Dwhite`, `Dbrown`, `Diwhite`, `Dibrown`, `Dgeom`, `Demand`, `Duty`, `DemandEnvGen`, `Dbufrd`, `Dbufwr`, `Dstutter`, `Dreset`, `Dswitch`, `Dswitch1`, `Dunique` |
| **Dynamics** | `Compander`, `CompanderD`, `Limiter`, `Normalizer`, `Amplitude` |
| **Chaos** | `LorenzL`, `HenonN/L/C`, `GbmanN/L`, `LatoocarfianN/L/C`, `LinCongN/L/C`, `CuspN/L`, `QuadN/L/C`, `StandardN/L`, `FBSineN/L/C` |
| **Granular** | `GrainBuf`, `GrainIn`, `PitchShift`, `Warp1` |
| **Buffer I/O** | `PlayBuf`, `RecordBuf`, `BufRd`, `BufWr`, `ClearBuf`, `LocalBuf`, `MaxLocalBufs`, `ScopeOut`, `ScopeOut2` |
| **Disk I/O** | `DiskIn`, `DiskOut`, `VDiskIn` |
| **Physical Modeling** | `Pluck`, `Ball`, `TBall`, `Spring` |
| **Reverb** | `FreeVerb` |
| **Convolution** | `Convolution`, `Convolution2`, `Convolution2L`, `Convolution3` |
| **Phase Vocoder** | `FFT`, `IFFT`, `PV_Add`, `PV_BinScramble`, `PV_BinShift`, `PV_BinWipe`, `PV_BrickWall`, `PV_ConformalMap`, `PV_Conj`, `PV_Copy`, `PV_CopyPhase`, `PV_Diffuser`, `PV_Div`, `PV_HainsworthFoote`, `PV_JensenAndersen`, `PV_LocalMax`, `PV_MagAbove`, `PV_MagBelow`, `PV_MagClip`, `PV_MagDiv`, `PV_MagFreeze`, `PV_MagMul`, `PV_MagNoise`, `PV_MagShift`, `PV_MagSmear`, `PV_MagSquared`, `PV_Max`, `PV_Min`, `PV_Mul`, `PV_PhaseShift`, `PV_PhaseShift90`, `PV_PhaseShift270`, `PV_RandComb`, `PV_RandWipe`, `PV_RectComb`, `PV_RectComb2`, `RunningSum` |
| **Machine Listening** | `BeatTrack`, `BeatTrack2`, `KeyTrack`, `Loudness`, `MFCC`, `Onsets`, `Pitch`, `SpecCentroid`, `SpecFlatness`, `SpecPcile` |
| **Hilbert** | `FreqShift`, `Hilbert`, `HilbertFIR` |
| **I/O** | `In`, `Out`, `InFeedback`, `LocalIn`, `LocalOut`, `OffsetOut`, `ReplaceOut`, `XOut` |
| **Lines** | `Line`, `XLine`, `LinExp`, `LinLin`, `DC`, `K2A`, `A2K`, `AmpComp`, `AmpCompA`, `Silence` |
| **Triggers** | `Trig`, `Trig1`, `Latch`, `Gate`, `Schmidt`, `Sweep`, `Phasor`, `Peak`, `PeakFollower`, `RunningMax`, `RunningMin`, `SendTrig`, `Poll`, `SendReply`, `SendPeakRMS`, `ToggleFF`, `TDelay`, `ZeroCrossing`, `LeastChange`, `MostChange`, `Clip`, `Fold`, `Wrap`, `InRange` |
| **Mouse/Keyboard** | `KeyState`, `MouseButton`, `MouseX`, `MouseY` |
| **Info** | `SampleRate`, `SampleDur`, `BlockSize`, `ControlRate`, `ControlDur`, `SubsampleOffset`, `RadiansPerSample`, `NumRunningSynths`, `BufFrames`, `BufSamples`, `BufSampleRate`, `BufRateScale`, `BufChannels`, `BufDur`, `NumOutputBuses`, `NumInputBuses`, `NumAudioBuses`, `NumControlBuses`, `NumBuffers`, `NodeID` |
| **Random** | `Rand`, `IRand`, `ExpRand`, `LinRand`, `NRand`, `TRand`, `TIRand`, `TExpRand`, `CoinGate`, `TWindex`, `RandID`, `RandSeed`, `Hasher`, `MantissaMask` |
| **Utility** | `MulAdd`, `Sum3`, `Sum4`, `Mix` |
| **Safety** | `CheckBadValues`, `Sanitize` |

## Envelope Types

```python
from nanosynth import Envelope

Envelope.adsr(attack_time=0.01, decay_time=0.3, sustain=0.5, release_time=1.0)
Envelope.asr(attack_time=0.01, sustain=1.0, release_time=1.0)
Envelope.linen(attack_time=0.01, sustain_time=1.0, release_time=1.0)
Envelope.percussive(attack_time=0.01, release_time=1.0)
Envelope.triangle(duration=1.0, amplitude=1.0)

# Custom envelope
Envelope(amplitudes=[0, 1, 0.5, 0], durations=[0.1, 0.3, 0.6], curves=[-4])
```

## Documentation

API reference docs are auto-generated from docstrings using [mkdocs-material](https://squidfunk.github.io/mkdocs-material/) and [mkdocstrings](https://mkdocstrings.github.io/).

```bash
make docs        # build static site to site/
make docs-serve  # serve locally at http://127.0.0.1:8000 with live reload
make docs-deploy # deploy to GitHub Pages
```

Browse the docs at [shakfu.github.io/nanosynth](https://shakfu.github.io/nanosynth/).

## Development

```bash
make dev         # uv sync + editable install
make build       # build wheel (incremental via build cache)
make sdist       # build source distribution
make test        # run tests
make lint        # ruff check --fix
make format      # ruff format
make typecheck   # mypy --strict
make qa          # all of the above
make clean       # remove transitory files (preserves build cache)
make reset       # clean everything including build cache
```

### CI

The GitHub Actions workflow (`.github/workflows/build.yml`) builds wheels for CPython 3.10--3.14 on macOS ARM64, Linux x86_64, and Windows x86_64 using [cibuildwheel](https://cibuildwheel.pypa.io). A `qa` job runs lint, format check, typecheck, and tests on every push. A source distribution ('sdist') is built separately and all artifacts are aggregated into a single downloadable archive.

A separate release workflow (`.github/workflows/release.yml`) publishes to PyPI on tag push via trusted publisher, with manual dispatch for TestPyPI.

## Attributions

- [SuperCollider](https://supercollider.github.io) -- the audio synthesis engine and programming language that nanosynth embeds.
- [supriya](https://github.com/supriya-project/supriya) -- the inspiration for nanosynth; its UGen system and SynthDef compiler were the basis for this project's graph compilation pipeline.
- [TidalCycles](https://tidalcycles.org) -- live coding pattern language for music, built on SuperCollider.
- [Strudel](https://strudel.cc) -- JavaScript port of TidalCycles for browser-based live coding.
- [Sonic Pi](https://sonic-pi.net) -- live coding music synth built on SuperCollider.
- [RtMidi](https://github.com/thestk/rtmidi) -- cross-platform MIDI I/O library, vendored for the `_midi` extension.
- [nanobind](https://github.com/wjakob/nanobind) -- the C++/Python binding library used to embed libscsynth, RtiMidi and the OSC codec.

## License

MIT
