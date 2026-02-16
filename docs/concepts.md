# Concepts

This page explains internal concepts that become relevant when building non-trivial SynthDefs. Each section covers what the concept is, why it matters, and how to use it.

## Calculation Rates

Every UGen runs at one of four rates, which determines how often it computes new output values:

| Rate | Token | Meaning |
|------|-------|---------|
| `SCALAR` | `.ir()` | Computed once at synth creation |
| `CONTROL` | `.kr()` | Computed once per control block (typically every 64 samples) |
| `AUDIO` | `.ar()` | Computed every sample |
| `DEMAND` | `.dr()` | Computed only when another UGen requests a value |

Use the lowest rate that gives acceptable results. A filter cutoff that changes slowly can run at `.kr()`, saving CPU compared to `.ar()`. Constant values like a bus index should use `.ir()`.

**Rate promotion**: when you combine UGens at different rates with arithmetic, the result runs at the highest rate among its inputs:

```python
from nanosynth import SynthDefBuilder
from nanosynth.ugens import SinOsc, LFNoise1, Out

with SynthDefBuilder(amplitude=0.3) as builder:
    # LFNoise1 runs at control rate, SinOsc at audio rate.
    # The multiplication produces an audio-rate signal.
    sig = SinOsc.ar(frequency=440.0) * LFNoise1.kr(frequency=4.0)
    Out.ar(bus=0, source=sig)
```

## Multichannel Expansion

Passing a list to any UGen parameter creates parallel instances, one per list element. The result is a `UGenVector` rather than a single UGen:

```python
from nanosynth import SynthDefBuilder
from nanosynth.ugens import Out, SinOsc

with SynthDefBuilder() as builder:
    # Creates two SinOsc UGens: one at 440 Hz, one at 443 Hz.
    # The result is a UGenVector with two elements -- stereo output.
    sig = SinOsc.ar(frequency=[440, 443])
    Out.ar(bus=0, source=sig)
```

When multiple parameters receive lists of different lengths, shorter lists cycle. This is useful for creating detuned unison voices:

```python
from nanosynth import SynthDefBuilder
from nanosynth.ugens import Out, SinOsc

with SynthDefBuilder() as builder:
    # 4 oscillators: frequencies cycle, phases alternate
    sig = SinOsc.ar(
        frequency=[440, 443, 437, 445],
        phase=[0, 0.5],  # cycles: 0, 0.5, 0, 0.5
    )
    Out.ar(bus=0, source=sig)
```

## The `unexpanded` Flag

Some parameters should accept a list as a single input rather than triggering multichannel expansion. The `param(unexpanded=True)` flag prevents expansion for that parameter.

This is used by demand-rate UGens where the list *is* the data (a sequence of values to step through), not a request for parallel UGens:

```python
from nanosynth import SynthDefBuilder, DoneAction
from nanosynth.ugens import Demand, Dseq, Impulse, Out, SinOsc

with SynthDefBuilder() as builder:
    # Dseq.sequence is unexpanded -- the list [60, 62, 64, 65, 67]
    # is a single sequence, not 5 parallel Dseq instances.
    freq = Demand.ar(
        trigger=Impulse.ar(frequency=4),
        source=Dseq.dr(
            repeats=2,
            sequence=[60, 62, 64, 65, 67],
        ).midicps(),
    )
    Out.ar(bus=0, source=SinOsc.ar(frequency=freq) * 0.2)
```

Without `unexpanded=True`, passing `[60, 62, 64, 65, 67]` to `sequence` would create five separate Dseq UGens -- not the intended behavior.

`EnvGen.envelope` and `LagControl.lags` also use this flag, since their list inputs represent structured data rather than parallel channels.

## Parameter Rates

`ParameterRate` is distinct from `CalculationRate`. It controls which Control UGen type is generated for a SynthDef parameter -- how the parameter is *exposed to the server*, not how fast a UGen computes.

| ParameterRate | Generated Control UGen | Use case |
|---------------|----------------------|----------|
| `kr` (default) | `Control` | Standard continuously-settable parameter |
| `ar` | `AudioControl` | Audio-rate modulation input |
| `tr` | `TrigControl` | Re-triggers on every `.set()` call |
| `kr` + lag | `LagControl` | Smoothed parameter (avoids zipper noise) |
| `ir` | `Control.ir` | Set once at synth creation, never changes |

Specify parameter rates using the `control()` function or tuple syntax:

```python
from nanosynth import SynthDefBuilder, control

with SynthDefBuilder(
    freq=control(440.0, rate="ar"),          # audio-rate input
    amp=control(0.3, lag=0.1),               # smoothed control
    bus=control(0, rate="ir"),               # fixed at creation
    trig=control(0.0, rate="tr"),            # trigger parameter
    cutoff=("kr", 1200.0),                   # tuple shorthand
    pan=("kr", 0.0, 0.05),                   # tuple with lag
) as builder:
    pass
```

## The Builder Scope

`SynthDefBuilder` is a context manager that pushes itself onto a thread-local stack. UGens created inside the `with` block automatically register with the topmost builder:

```python
from nanosynth import SynthDefBuilder
from nanosynth.ugens import Out, SinOsc

with SynthDefBuilder() as builder:
    # SinOsc and Out register with `builder` automatically --
    # no explicit wiring needed.
    Out.ar(bus=0, source=SinOsc.ar(frequency=440.0))

synthdef = builder.build(name="sine")
```

Each builder gets a UUID on creation. Every UGen stamped with that UUID belongs to that builder's scope. Cross-scope wiring (using a UGen from one builder as input to another) raises `SynthDefError`:

```python
from nanosynth import SynthDefBuilder
from nanosynth.ugens import Out, SinOsc

with SynthDefBuilder() as a:
    sig = SinOsc.ar(frequency=440.0)

with SynthDefBuilder() as b:
    Out.ar(bus=0, source=sig)  # raises SynthDefError: UGen input in different scope
```

The thread-local stack means multiple threads can build SynthDefs concurrently without interference -- each thread has its own builder stack.

## Graph Optimization

`SynthDefBuilder.build()` runs an optimization pass before producing the final SynthDef. Two optimizations are applied:

**Constant folding** -- arithmetic on constants is evaluated at compile time rather than generating UGens:

```python
from nanosynth import SynthDefBuilder
from nanosynth.ugens import Out, SinOsc

with SynthDefBuilder() as builder:
    # 440.0 + 10.0 becomes the constant 450.0 at compile time.
    # No BinaryOpUGen is generated.
    Out.ar(bus=0, source=SinOsc.ar(frequency=440.0 + 10.0))
```

This extends to operations like `sig * 1` (identity multiplication) and `sig + 0` (identity addition), which are reduced to `sig` without generating operator UGens.

**Dead code elimination** -- pure UGens (`_is_pure = True`) with no descendants are removed from the graph. A UGen is "pure" if it has no side effects (most oscillators and filters). Output UGens like `Out` are never pure, so they anchor the graph:

```python
from nanosynth import SynthDefBuilder
from nanosynth.ugens import Out, SinOsc

with SynthDefBuilder() as builder:
    unused = SinOsc.ar(frequency=300.0)  # pure, no descendants -> eliminated
    sig = SinOsc.ar(frequency=440.0)
    Out.ar(bus=0, source=sig)            # not pure (is_output) -> kept
```

## Width-First Ordering

Some UGens must execute before all subsequent UGens in the graph, regardless of explicit signal connections. The `is_width_first=True` flag forces a UGen to be a topological antecedent of every UGen that appears after it.

This is used by FFT and other spectral UGens. `FFT` must complete its spectral analysis before any PV (phase vocoder) operation reads the buffer:

```python
from nanosynth import SynthDefBuilder
from nanosynth.ugens import IFFT, Out, WhiteNoise
from nanosynth.ugens.pv import FFT, PV_BrickWall

with SynthDefBuilder() as builder:
    # FFT is width-first: it becomes an antecedent of PV_BrickWall
    # and IFFT in the topological sort, even though the dependency
    # is implicit (they share a buffer, not a signal connection).
    chain = FFT.kr(source=WhiteNoise.ar())
    chain = PV_BrickWall.kr(pv_chain=chain, wipe=0.5)
    Out.ar(bus=0, source=IFFT.ar(pv_chain=chain))
```

Without width-first ordering, the topological sort might place PV operations before the FFT that fills their buffer, producing silence or garbage.

## The `Default` Sentinel

`Default()` marks UGen parameters whose default values depend on other parameters. The sentinel is resolved in the UGen's `_postprocess_kwargs` method before construction.

For example, `FFT.buffer_id` defaults to `Default()`. When left unset, `_postprocess_kwargs` creates a `LocalBuf` sized to the `window_size` parameter:

```python
from nanosynth import SynthDefBuilder
from nanosynth.ugens import IFFT, Out, WhiteNoise
from nanosynth.ugens.pv import FFT

with SynthDefBuilder() as builder:
    # buffer_id defaults to Default() -> a LocalBuf is created
    # automatically, sized to window_size (or 2048 if unset).
    chain = FFT.kr(source=WhiteNoise.ar())
    Out.ar(bus=0, source=IFFT.ar(pv_chain=chain))
```

Similarly, `Gendy1.knum` defaults to `Default()` and resolves to the value of `init_cps` when not explicitly provided.

A `Default` parameter is distinct from a simple default value -- it cannot be a fixed constant because its value is computed from sibling parameters at construction time.
