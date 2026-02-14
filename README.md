# nanosynth

A Python package that embeds SuperCollider's [libscsynth](https://github.com/supercollider/supercollider) synthesis engine in-process using [nanobind](https://github.com/wjakob/nanobind). Define SynthDefs in Python, compile them to SuperCollider's SCgf binary format, boot the embedded audio engine, and control it via OSC -- all without leaving Python.

## Features

- **Embedded synthesis engine** -- libscsynth runs in-process as a Python extension (vendored and built from source), no separate scsynth process required
- **High-level `Server` class** -- boot/quit lifecycle, node ID allocation, SynthDef dispatch, and convenience methods (`synth`, `group`, `free`, `set`). Context manager support and `managed_synth()`/`managed_group()` for automatic node cleanup
- **Pythonic SynthDef builder** -- define UGen graphs using a context manager and operator overloading, compiled to SuperCollider's SCgf binary format
- **290+ UGens** -- oscillators, filters, delays, noise, chaos, granular, demand, dynamics, panning, physical modeling, reverb, and more
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

### Defining and Compiling a SynthDef

No embedded engine required -- you can define UGen graphs and compile them to SCgf bytes for use with any SuperCollider server:

```python
from nanosynth import SynthDefBuilder, DoneAction, compile_synthdefs
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.ugens import Out, Pan2, SinOsc

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
scgf_bytes = synthdef.compile()
```

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

### Booting the Embedded Engine and Playing Sound

The `Server` class wraps the embedded engine lifecycle. Use it as a context manager to boot on entry and shut down on exit:

```python
import time
from nanosynth import Server, Options

with Server(Options(verbosity=0)) as server:
    # Send the SynthDef we defined above
    synthdef.send(server)
    time.sleep(0.1)

    # Create a synth -- returns a node ID
    node = server.synth("sine", frequency=440.0, amplitude=0.3)
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
| **Oscillators** | `SinOsc`, `Saw`, `Pulse`, `Blip`, `LFSaw`, `LFPulse`, `LFTri`, `LFCub`, `LFPar`, `VarSaw`, `SyncSaw`, `Impulse`, `FSinOsc`, `LFGauss`, `Vibrato`, `Osc`, `OscN`, `COsc`, `VOsc`, `VOsc3` |
| **Filters** | `LPF`, `HPF`, `BPF`, `BRF`, `RLPF`, `RHPF`, `MoogFF`, `Lag`, `Lag2`, `Lag3`, `Decay`, `Decay2`, `Ringz`, `Formlet`, `Median`, `LeakDC`, `OnePole`, `OneZero`, `TwoPole`, `TwoZero`, `FOS`, `SOS`, `MidEQ`, `Slew`, `Slope` |
| **BEQ Filters** | `BLowPass`, `BHiPass`, `BBandPass`, `BBandStop`, `BAllPass`, `BLowShelf`, `BHiShelf`, `BPeakEQ`, `BLowCut`, `BHiCut` |
| **Noise** | `WhiteNoise`, `PinkNoise`, `BrownNoise`, `GrayNoise`, `ClipNoise`, `Dust`, `Dust2`, `Crackle`, `LFNoise0`, `LFNoise1`, `LFNoise2`, `LFDNoise0`, `LFDNoise1`, `LFDNoise3`, `Logistic` |
| **Delays** | `DelayN`, `DelayL`, `DelayC`, `CombN`, `CombL`, `CombC`, `AllpassN`, `AllpassL`, `AllpassC`, `BufDelayN`, `BufDelayL`, `BufDelayC`, `BufCombN`, `BufCombL`, `BufCombC`, `BufAllpassN`, `BufAllpassL`, `BufAllpassC` |
| **Envelopes** | `EnvGen`, `Linen`, `Done`, `Free`, `FreeSelf`, `FreeSelfWhenDone`, `Pause`, `PauseSelf`, `PauseSelfWhenDone` |
| **Panning** | `Pan2`, `Pan4`, `PanAz`, `PanB`, `PanB2`, `BiPanB2`, `Balance2`, `Rotate2`, `DecodeB2`, `XFade2` |
| **Demand** | `Dseq`, `Dser`, `Dseries`, `Drand`, `Dxrand`, `Dshuf`, `Dwhite`, `Dbrown`, `Diwhite`, `Dibrown`, `Dgeom`, `Duty`, `DemandEnvGen`, `Dbufrd`, `Dbufwr`, `Dstutter`, `Dreset`, `Dswitch`, `Dswitch1`, `Dunique` |
| **Dynamics** | `Compander`, `Limiter`, `Normalizer`, `Amplitude` |
| **Chaos** | `LorenzL`, `HenonN/L/C`, `GbmanN/L`, `LatoocarfianN/L/C`, `LinCongN/L/C`, `CuspN/L`, `QuadN/L/C`, `StandardN/L`, `FBSineN/L/C` |
| **Granular** | `GrainBuf`, `GrainIn`, `PitchShift`, `Warp1` |
| **Buffer I/O** | `PlayBuf`, `RecordBuf`, `BufRd`, `BufWr`, `ClearBuf`, `MaxLocalBufs`, `ScopeOut` |
| **Physical Modeling** | `Pluck`, `Ball`, `TBall`, `Spring` |
| **Reverb** | `FreeVerb` |
| **Convolution** | `Convolution`, `Convolution2`, `Convolution2L`, `Convolution3` |
| **I/O** | `In`, `Out`, `InFeedback`, `OffsetOut`, `ReplaceOut`, `XOut`, `LocalOut` |
| **Lines** | `Line`, `XLine`, `LinExp`, `DC`, `K2A`, `A2K`, `AmpComp`, `AmpCompA` |
| **Triggers** | `Trig`, `Trig1`, `Latch`, `Gate`, `Schmidt`, `Sweep`, `Phasor`, `Peak`, `SendTrig`, `ToggleFF`, `TDelay`, `ZeroCrossing`, `Clip`, `Fold`, `Wrap` |
| **Info** | `SampleRate`, `BlockSize`, `ControlRate`, `BufFrames`, `BufSampleRate`, `BufChannels`, `BufDur`, `NumOutputBuses`, `NumInputBuses`, `NumAudioBuses`, `NumBuffers`, `NodeID` |
| **Random** | `Rand`, `IRand`, `ExpRand`, `LinRand`, `NRand`, `TRand`, `TIRand`, `TExpRand`, `CoinGate`, `TWindex`, `RandID`, `RandSeed`, `Hasher`, `MantissaMask` |
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

The GitHub Actions workflow (`.github/workflows/build.yml`) builds wheels for CPython 3.10--3.14 on macOS ARM64, Linux x86_64, and Windows x86_64 using [cibuildwheel](https://cibuildwheel.pypa.io). A `qa` job runs lint, format check, typecheck, and tests on every push. An sdist is built separately and all artifacts are aggregated into a single downloadable archive.

A separate release workflow (`.github/workflows/release.yml`) publishes to PyPI on tag push via trusted publisher, with manual dispatch for TestPyPI.

## Attributions

- [SuperCollider](https://supercollider.github.io) -- the audio synthesis engine and programming language that nanosynth embeds.
- [supriya](https://github.com/supriya-project/supriya) -- the inspiration for nanosynth; its UGen system and SynthDef compiler were the basis for this project's graph compilation pipeline.
- [TidalCycles](https://tidalcycles.org) -- live coding pattern language for music, built on SuperCollider.
- [Strudel](https://strudel.cc) -- JavaScript port of TidalCycles for browser-based live coding.
- [Sonic Pi](https://sonic-pi.net) -- live coding music synth built on SuperCollider.
- [nanobind](https://github.com/wjakob/nanobind) -- the C++/Python binding library used to embed libscsynth and the OSC codec.

## License

MIT
