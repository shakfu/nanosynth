# Compatibility and correctness position

Assessed 2026-10-04 against SuperCollider 3.14.1, the version vendored in `thirdparty/supercollider`. Method and tooling: `docs/dev/ugen-metadata-audit.md`.

## Summary

| Area | Result |
|-|-|
| Graph compilation (28-case corpus vs sclang, by rendered audio) | 24 match exactly. The 4 that differ are listed below; all are explained |
| Unary operators (34) | All special indices match the engine |
| Binary operators (44) | **32 have the wrong special index**: every operator from `min` on |
| UGen input order (339 UGens present in sclang) | **16 UGens send inputs in the wrong order** |
| Engine load and render (341 UGens, 530 rate cases) | 508 ok. 8 not installed, 5 crash, 6 non-finite, 3 build errors; triage below |
| Input-rate rules sclang enforces | None enforced. 87 rules across 80 UGens; 6 are violated by nanosynth's own defaults |
| Coverage | 51 plugin units and 9 sclang pseudo-UGens have no nanosynth class |

The two critical classes, wrong operator indices and wrong input order, produce wrong audio with no error. A user writing `x.min(y)`, `x ** 2`, `x.clip2(1)`, `Dwhite(...)` or `Duty(...)` gets a different signal from what the same code produces in SuperCollider.

## Critical: wrong audio, no error

### Binary operator special indices

`BinaryOperator` in `src/nanosynth/enums.py` reserves indices 12 and 13 for `opIdentical`/`opNotIdentical`. These are commented out of the engine's enum (`server/plugins/BinaryOpUGens.cpp`), so every operator from `MINIMUM` on is 2 higher than the engine expects. sclang emits `min=12`, `max=13`, `round=19`, `hypot=23`, `wrap2=45`, matching the engine.

Each affected operator runs a different engine operation. `min` (sent as 14) runs bitwise AND; `max` runs bitwise OR. Affected: `min`, `max`, bit ops, `lcm`, `gcd`, `round`, `round_up`, `trunc`, `atan2`, `hypot`, `hypotx`, `**` (power), shifts, `ring1`-`ring4`, `difsqr`, `sumsqr`, `sqrsum`, `sqrdif`, `absdif`, `thresh`, `amclip`, `scaleneg`, `clip2`, `excess`, `fold2`, `wrap2`. 18 were confirmed by rendering against sclang; all 32 by enum comparison. Correct: `+ - * /`, integer division, `%`, and the six comparisons.

### Input order

nanosynth sends a UGen's inputs in its parameter declaration order; the plugin reads them by slot. Confirmed by C++ and by rendering against sclang:

| UGens | nanosynth sends | Engine reads | Rendered result |
|-|-|-|-|
| `BufCombN/L/C`, `BufAllpassN/L/C` | buf, in, `maximum_delay_time`, delay, decay | buf, in, delay, decay | delay = `maximum_delay_time`, decay = `delay_time` |
| `BufDelayN/L/C` | buf, in, `maximum_delay_time`, delay | buf, in, delay | delay = `maximum_delay_time` |
| `Dwhite`, `Diwhite` | lo, hi, length | length, lo, hi | `Dwhite`: inf; `Diwhite`: ~1e8 |
| `Dbrown`, `Dibrown` | lo, hi, step, length | length, lo, hi, step | wrong range |
| `Dgeom` | start, grow, length | length, start, grow | silence |
| `Duty` | dur, reset, level, doneAction | dur, reset, doneAction, level | silence |
| `Dbufwr` | input, buf, phase, loop | buf, phase, input, loop | writes the wrong buffer/position |

`Dseries`, `Dseq`, `Drand` and the other list demand UGens are correct.

## High

**Input rates are not validated.** sclang's `checkInputs` rejects graphs where an audio-rate UGen gets a scalar or control-rate signal in a slot it reads as audio. nanosynth has no equivalent. The plugin then reads 64 samples from a 1-sample wire.
- 6 rules are violated by nanosynth's own defaults, so omitting the argument is enough: `AmpComp.frequency`, `AmpCompA.frequency`, `BufRd.phase`, `BufWr.phase`, `Demand.trigger`, `XFade2.in_b`. Observed effects: `BufWr` crash, `AmpCompA` and `XFade2` NaN/inf.
- 81 more are violated when a user passes a non-audio signal, for example `LPF.ar(source=Saw.kr(...))`.

**Engine cannot load 8 UGens** ("UGen not installed"):
- `Dunique` and `HilbertFIR` are pseudo-UGens in sclang, but nanosynth emits them as units.
- `BHiCut` and `BLowCut` exist in neither sclang 3.14.1 nor the plugins.
- `MouseX`, `MouseY`, `MouseButton` and `KeyState`: their plugin (UIUGens) is not shipped.

**Wrong defaults that break output:**
- `AmpComp`: `root=0` and `frequency=1000`; sclang uses `60.midicps` for both. Division by zero.
- `ExpRand`: `minimum=0`; sclang uses 0.01. Output is -inf.

**`Envelope.linen` is not linear by default.** Its default `curve=1` is encoded as curvature 1 (shape `CUSTOM`), not as the linear shape. sclang's default is `\lin`.

**`Mix` flattens to mono.** sclang's `Mix` sums the outer array, so `Mix(Pan2.ar([a, b], ...))` stays stereo; nanosynth's sums all channels into one. The class docstring says "down-to-mono", so this may be intentional. It still breaks a common sclang idiom.

## Medium

**Defaults differing from sclang:**
- `NRand.n`: 1 vs 0.
- `RandID.rand_id`: 1 vs 0.
- `Dibrown.hi`/`step`: 12 and 1 vs 1 and 0.01 (sclang inherits them from `Dbrown`).
- `Gendy1`, `Gendy2`, `LeakDC`: sclang uses different defaults at control rate; nanosynth uses the audio-rate ones at both rates.

**Rates sclang does not offer:** `Buf*` delays at kr, `InFeedback` at kr, and `PV_HainsworthFoote`/`PV_JensenAndersen` at kr only, where sclang has ar only.

**api gaps:** `SendPeakRMS` rejects a single signal, which sclang accepts. `SendTrig` declares 1 output; sclang declares 0 and the plugin writes none. That one is harmless.

## Low

**Coverage:** 51 plugin units have no class. 7 are Bela hardware I/O; `OutputProxy` is not a UGen. Musical gaps include:
- `Klang`, `Formant`, `Shaper`, `SinOscFB`, `IndexL`;
- `Stepper`, `Timer`, `PulseCount`, `PulseDivider`, `SetResetFF`, `TDuty`;
- `GVerb`, `FreeVerb2`, `Resonz`, `TGrains`, `GrainSin`, `GrainFM`, `PartConv`;
- `LinPan2`, `LinXFade2`, `IEnvGen`, `T2A`, `T2K`.

Missing sclang pseudo-UGens: `Splay`, `SplayAz`, `DynKlank`, `DynKlang`, `VarLag`, `Changed`, `CompanderD`, `Tap`, `UnpackFFT`.

**Stricter than sclang:** 199 arguments across 101 UGens are required in nanosynth but have a default in sclang, typically `in = 0.0`.

## Not nanosynth defects

| Case | Finding |
|-|-|
| `DelTapRd`, `ScopeOut2` crash | sclang's build of the same graph crashes identically. They need a `DelTapWr` phase or a scope buffer |
| `Saw.kr`, `Pulse.kr` at 440 Hz non-finite | Same in sclang's build: frequency above control-rate Nyquist |
| `NumRunningSynths` | Its Ctor calls `INRATE(0)` with 0 inputs, in sclang's build too. Upstream bug |
| `MaxLocalBufs` build error | Internal UGen, created by the graph |

## Not verified

- **Supernova.** All renders used scsynth.
- **Arguments that are symbols, strings or arrays.** The extractor does not track them. Their UGens (`Onsets`, `Poll`, `SendReply`, `SendPeakRMS`, `Klank`) were checked by hand.
- **Renames.** Synonyms in `scripts/ugen_position.py`; 2 remain unexplained and were reviewed by hand.
- **Behaviour beyond 0.1-0.25 s renders with default or recipe inputs.** Effects that need specific input ranges, long run time or buffers holding data were not exercised.
- **The pattern, server and MIDI layers.** They are compared to nothing here.

## Reproduce

```bash
# sclang 3.14.1, headless (no Qt, no JACK)
git clone --depth 1 --branch Version-3.14.1 --recurse-submodules --shallow-submodules \
    https://github.com/supercollider/supercollider.git sc
cmake -S sc -B scbuild -G Ninja -DCMAKE_BUILD_TYPE=Release -DSC_QT=OFF -DSC_IDE=OFF \
    -DSUPERNOVA=OFF -DSC_EL=OFF -DSC_VIM=OFF -DSC_ED=OFF -DSC_HIDAPI=OFF \
    -DSC_ABLETON_LINK=OFF -DNO_X11=ON -DINSTALL_HELP=OFF -DFFT_GREEN=ON \
    -DAUDIOAPI=portaudio -DSYSTEM_PORTAUDIO=OFF
ninja -C scbuild sclang
# sclang_conf.yaml: includePaths: [sc/SCClassLibrary], excludeDefaultPaths: true

sclang -l sclang_conf.yaml scripts/sclang_reference.scd raw.json
python scripts/ugen_position.py import-reference raw.json   # -> spec/sclang-reference.json
python scripts/ugen_sweep.py                                # -> build/ugen-sweep.json
python scripts/ugen_position.py report                      # -> build/ugen-position.json
sclang -l sclang_conf.yaml scripts/compile_corpus.scd corpus/
python scripts/compile_corpus.py corpus/                    # -> build/compile-corpus.json
```
