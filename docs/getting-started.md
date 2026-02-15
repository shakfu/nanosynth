# Getting Started

## Defining and Compiling a SynthDef

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

## Using the `@synthdef` Decorator

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

## Subtractive Synthesis

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
```

## FM Synthesis

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

## Booting the Embedded Engine

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

## Managed Nodes (Automatic Cleanup)

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
```

## Debugging SynthDef Graphs

`SynthDef.dump_ugens()` prints a human-readable UGen graph:

```python
print(synthdef.dump_ugens())
# SynthDef: sine
#   0: Control.kr - frequency, amplitude
#   1: SinOsc.ar(frequency: Control[0], phase: 0.0)
#   2: BinaryOpUGen.ar(MULTIPLICATION, a: SinOsc[0], b: Control[1])
#   ...
```

## OSC Codec

The OSC module works standalone for any OSC communication needs:

```python
from nanosynth import OscMessage, OscBundle

# Encode
msg = OscMessage("/s_new", "sine", 1000, 0, 1, "frequency", 440.0)
datagram = msg.to_datagram()

# Decode
decoded = OscMessage.from_datagram(datagram)
assert decoded == msg
```

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
