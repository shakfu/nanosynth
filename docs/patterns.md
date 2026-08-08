# Patterns

Patterns are reusable templates that produce a fresh iterator each time they
are iterated, so one pattern object can drive many players. Value patterns
(`Pseq`, `Prand`, `Pwhite`, ...) yield numbers; event patterns (`Pbind` and the
composites below) yield events, which a `Player` turns into synths on a
`Clock`. See the [Patterns API reference](api/patterns.md) for full signatures.

```python
from nanosynth import Clock, Pbind, Pseq, Server

with Server() as server:
    synthdef.send(server)
    server.sync()

    clock = Clock(bpm=120)
    player = Pbind(
        instrument="sine",
        degree=Pseq([0, 2, 4, 7], repeats=4),
        dur=0.25,
    ).play(clock, server)
```

## Timing

Events are scheduled as timestamped OSC bundles rather than sent when the
Python thread happens to wake, so onset accuracy comes from the engine. The
`latency` window (default 0.1s) is how far ahead events are stamped:

```python
clock = Clock(bpm=120, latency=0.2)   # more slack under load
player = pattern.play(clock, server, latency=0.05)   # per-player override
```

Raise it if playback stutters when the machine is busy; lower it for tighter
response to live input. See the [Threading Model](threading.md) for why this
removes Python-side jitter from the audible result.

### Quantization

`quant` starts playback on the next boundary of the clock's beat grid instead
of immediately, which is what keeps parts phase-aligned when you launch them by
hand at arbitrary moments:

```python
bass.play(clock, server, quant=4)              # next bar in 4/4
hat.play(clock, server, quant=4, offset=0.5)   # half a beat after the bar
```

All players on one clock share a grid, so two patterns started seconds apart
still begin together. `clock.reset_grid()` moves beat 0 to now.

## The event model

`Pbind` merges its bindings with defaults, then fills in derived keys. Anything
you bind explicitly wins, so binding a downstream key bypasses the derivation
that would otherwise produce it.

### Pitch

The chain runs `degree` -> `note` -> `midinote` -> `freq`:

- `degree` indexes into `scale` (default `"major"`), wrapping across octaves, so
degree 7 of a 7-note scale is the octave above degree 0. Fractional degrees
interpolate between adjacent steps.

- `scale` is a name from `SCALES` or an explicit list of semitone offsets.

- `root` transposes in semitones; `octave` (default 5) places note 0 at MIDI 60,
middle C, as in sclang.

- Binding `freq` directly skips all of it.

```python
Pbind(degree=Pseq([0, 2, 4]), scale="minor", root=3, octave=4)
```

### Amplitude and timing

- `db` derives `amp` (`amp = 10 ** (db / 20)`).

- `sustain` defaults to `dur * legato * stretch` (legato default 0.8), and is
what the gate release is scheduled from.

- `delta` -- how far the player advances after the event -- defaults to
`dur * stretch`. Bind it directly to decouple note spacing from note length.

Keys that feed this machinery (`degree`, `note`, `midinote`, `octave`, `root`,
`scale`, `db`, `dur`, `delta`, `sustain`, `legato`, `stretch`, `instrument`) are
metadata and are never sent to the synth as controls. Everything else is.

### Referencing sibling keys

`Pkey` reads another key of the event being built. Patterns do not overload
arithmetic operators, so pass a transform rather than writing `Pkey("freq") * 2`:

```python
Pbind(degree=Pseq([0, 4]), amp=Pkey("freq", lambda f: 40.0 / f))
```

A `Pkey` bound to a chain *input* (`degree`, `dur`, `db`, ...) resolves before
the chain runs, so it can drive it. Bound to anything else it resolves after,
so it can read the chain's output.

## Composite patterns

- **`Ppar`** runs event patterns in parallel, merging them into one time-ordered
stream. Each voice keeps its own `sustain`; only `delta` is rewritten to the gap
in the merged stream. Simultaneous events get a delta of 0, which puts them in
the same bundle -- they start on the same sample, not merely in the same tick.

- **`Ptpar`** is `Ppar` with a beat offset per pattern, for entries that stagger.

- **`Pmono`** holds one synth for the whole pattern and sends `/n_set` per event
instead of creating a new node, then releases it at the end. This is how a
monophonic line glides -- portamento and filter sweeps that separate synths
cannot produce. `sustain` is ignored.

- **`Pdef`** is a named, hot-swappable pattern registry. `Pdef("bass", pattern)`
registers or replaces; `Pdef("bass")` looks up. A running player picks up a
replacement at the next event, so a part can be rewritten without stopping
playback -- the pattern analogue of [`Ndef`](api/proxy.md).

- **`Pfin`** bounds a pattern by event count; **`Pfindur`** bounds it by total
duration, clipping the last `delta` so the total is exact and the pattern lands
on a bar line.

```python
from nanosynth import Pdef, Pmono, Pn, Ppar, Pseq, Pbind

Pdef("bass", Pn(Pmono("acid", degree=Pseq([0, 0, 3, 5]), dur=0.25)))
Pdef("lead", Pn(Pbind(instrument="blip", degree=Pseq([7, 9, 11]), dur=0.5)))

player = Ppar([Pdef("bass"), Pdef("lead")]).play(clock, server, quant=4)

# ... later, without stopping playback:
Pdef("lead", Pn(Pbind(instrument="blip", degree=Pseq([12, 11, 9]), dur=0.25)))
```

Every pattern has `play()`, not just the event composites, so the generic
wrappers stay playable -- `Pn(Pbind(...), 4)`, `Pfin(8, part)`, `partA | partB`.
Only patterns yielding events are meaningful to play; a value pattern will
produce nonsense.

## Demos

`make demos` runs the scsynth demo scripts, four of which cover this material:

- `22_bundle_scheduling.py` -- the same rhythm sent immediately and as
timestamped bundles, under GIL load, so the timing difference is audible.

- `23_pitch_chain.py` -- one degree sequence through four scales, then `root`,
`octave`, `db`, `legato`, `stretch` and `Pkey`.

- `24_parallel_quant.py` -- `Ppar`, `Ptpar`, and parts launched mid-bar that
snap to the downbeat via `quant`.

- `25_pmono_pdef.py` -- `Pbind` versus `Pmono` on the same line, live `Pdef`
swaps, and `Pfin`/`Pfindur`.

## Not yet implemented

- Array-valued keys for chords (one event expanding to several synths).

- Arithmetic operators on patterns; use `Pkey` with a transform.

- `Score.from_pattern()` -- the realtime pattern engine and NRT scoring do not
yet share a code path, so patterns cannot be rendered offline.
