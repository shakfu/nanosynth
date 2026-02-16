# Supernova Guide

Supernova is SuperCollider's parallel DSP engine. Where scsynth processes all audio on a single thread, supernova distributes independent synth nodes across multiple CPU cores. nanosynth embeds both engines in-process -- you choose which one to use at boot time.

## When to use supernova

Supernova provides a benefit when your synthesis graph has **independent signal paths** that can run concurrently. Typical cases:

- **Dense polyphony** -- 32+ simultaneous voices, each with its own filter/envelope/panning chain

- **Parallel effect chains** -- multiple self-contained source-to-output paths (e.g., three instruments each with their own delay and reverb)

- **Nested hierarchies** -- left/right channel voice banks processed independently, mixed at the end

If your graph is a single linear chain (source -> filter -> reverb -> output), supernova and scsynth will perform identically -- there is nothing to parallelize.

## Quick start

The `Server` API is identical for both engines. The only difference is passing `protocol=EmbeddedSupernovaProtocol()`:

```python
import time
from nanosynth import EmbeddedSupernovaProtocol, Options, Server
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import DoneAction, SynthDefBuilder
from nanosynth.ugens import Out, Pan2, SinOsc

with SynthDefBuilder(frequency=440.0, amplitude=0.3) as builder:
    sig = SinOsc.ar(frequency=builder["frequency"]) * builder["amplitude"]
    env = EnvGen.kr(
        envelope=Envelope.linen(attack_time=0.1, sustain_time=1.8, release_time=0.1),
        done_action=DoneAction.FREE_SYNTH,
    )
    Out.ar(bus=0, source=Pan2.ar(source=sig * env))

synthdef = builder.build(name="sine")

with Server(
    Options(verbosity=0, load_synthdefs=False),
    protocol=EmbeddedSupernovaProtocol(),
) as server:
    synthdef.send(server)
    time.sleep(0.1)

    node = server.synth("sine", frequency=440.0, amplitude=0.3)
    time.sleep(2.0)
```

All SynthDefs, UGens, `AddAction`, buses, buffers, patterns, recording, and reply handling work identically with both engines. The same compiled SynthDef binary (SCgf format) is used by both.

## ParGroup: enabling parallel execution

The key to getting parallel execution from supernova is `ParGroup`. A regular `Group` executes its children sequentially (top to bottom). A `ParGroup` tells supernova's scheduler that its children have **no data dependencies** and can run on separate CPU cores.

```python
from nanosynth import AddAction

# Regular group -- children execute sequentially
group = server.group(target=1, action=AddAction.ADD_TO_HEAD)

# Parallel group -- children execute across cores
par = server.par_group(target=1, action=AddAction.ADD_TO_HEAD)
```

### Basic parallel voices

Place independent voices in a ParGroup so they can compute in parallel:

```python
par = server.par_group(target=1, action=AddAction.ADD_TO_HEAD)

# These four voices can execute on separate cores
for freq in [261.63, 329.63, 392.00, 523.25]:
    server.synth("voice", target=par, frequency=freq, amplitude=0.15)
```

### Parallel effect chains on private buses

For maximum parallelism, give each chain its own private bus so there are zero data dependencies between chains:

```python
# Three buses for three independent chains
BUSES = [16, 18, 20]  # stereo pairs: 16-17, 18-19, 20-21

par = server.par_group(target=1, action=AddAction.ADD_TO_HEAD)

for bus, freq in zip(BUSES, [110.0, 220.0, 330.0]):
    # Each chain is a sequential Group inside the ParGroup
    chain = server.group(target=par)

    # Source writes to private bus
    server.synth("source", target=chain, out_bus=bus, frequency=freq)

    # Effect reads from private bus, writes to main output
    server.synth(
        "reverb",
        target=chain,
        action=AddAction.ADD_TO_TAIL,
        in_bus=bus,
    )
```

supernova runs all three chain groups in parallel because they are children of the ParGroup and use separate buses.

### Nested ParGroups

ParGroups can nest. A top-level ParGroup can contain sub-ParGroups for finer-grained control over what runs in parallel vs. sequentially:

```python
# Top-level parallel group
top = server.par_group(target=1, action=AddAction.ADD_TO_HEAD)

# Left and right voice banks -- parallel with each other
left_par = server.par_group(target=top)
right_par = server.par_group(target=top)

# Sequential effects group -- must run after voices
fx_group = server.group(target=top, action=AddAction.ADD_TO_TAIL)

# Voices within each side also run in parallel
for freq in [300.0, 500.0, 800.0]:
    server.synth("voice", target=left_par, pan=-0.6, frequency=freq)
for freq in [350.0, 600.0, 950.0]:
    server.synth("voice", target=right_par, pan=0.6, frequency=freq)

# Reverb runs after all voices
server.synth("reverb", target=fx_group)
```

The resulting node tree:

```
ParGroup (top)
  |-- ParGroup (left_par)    -- voices compute in parallel
  |-- ParGroup (right_par)   -- voices compute in parallel
  |-- Group (fx_group)       -- reverb runs after both sides
```

Both sides compute in parallel with each other, and voices within each side also compute in parallel. The fx group runs sequentially after everything above it.

### Managed ParGroups

Like `managed_group()`, `managed_par_group()` frees the group automatically on context exit:

```python
with server.managed_par_group(target=1) as par:
    server.synth("voice", target=par, frequency=440.0)
    server.synth("voice", target=par, frequency=660.0)
    time.sleep(3.0)
# par freed here -- all children freed too
```

## SynthDef compatibility

scsynth and supernova share the same SynthDef binary format and UGen plugin ABI. A SynthDef compiled with nanosynth works with both engines without modification. UGen plugins are compiled in two variants at build time -- one for scsynth and one for supernova -- but the SynthDef format is identical.

This means you can develop and test with scsynth, then switch to supernova for production workloads that benefit from parallelism, with no changes to your SynthDef definitions.

## Limitations

**One instance per process.** Supernova uses a global singleton (`nova_server`). Only one `EmbeddedSupernovaProtocol` can be active at a time. Attempting to boot a second one raises `ServerCannotBoot`.

**Cannot run alongside scsynth.** scsynth and supernova cannot both be active simultaneously in the same process due to audio device contention and shared global state. Quit one before booting the other.

**ParGroup on scsynth.** The `par_group()` API works with scsynth too, but scsynth treats ParGroups as regular Groups -- there is no parallel execution. This is useful for writing engine-agnostic code that benefits from parallelism on supernova without breaking on scsynth.

**Thread count.** By default, supernova uses all available CPU cores for DSP threads. This is configured internally and is not currently exposed as a user-facing option.

## Building

Supernova is built by default alongside scsynth. To disable it:

```sh
# Build without supernova
uv pip install -e . -C cmake.define.NANOSYNTH_EMBED_SUPERNOVA=OFF
```

To check whether supernova is available at runtime:

```python
try:
    from nanosynth import EmbeddedSupernovaProtocol
    print("supernova available")
except ImportError:
    print("supernova not available")
```

## Demo scripts

Six demo scripts are provided in `demos/supernova/`:

| Script | Description |
|--------|-------------|
| `01_sine.py` | Basic sine wave -- same as the scsynth version, verifying the engine works |
| `02_parallel_voices.py` | 24 voices in a ParGroup with per-voice filtering and panning |
| `03_fx_chain.py` | Delay and reverb effect chain with execution order via groups |
| `04_parallel_fx.py` | Three independent effect chains on private buses in a ParGroup |
| `05_nested_pargroups.py` | Two-level ParGroup hierarchy with left/right voice banks |
| `06_dense_polyphony.py` | 64 simultaneous voices -- stress test for parallel DSP scheduling |

Run them with:

```sh
make demos-supernova
```
