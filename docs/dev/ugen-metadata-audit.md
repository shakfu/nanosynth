# UGen metadata audit

Status: steps 1-3 done 2026-10-05; step 4 open. Tracked in `TODO.md` (High, "UGen metadata has no independent reference").

## Problem

Each UGen's metadata (rates, input names, order and defaults, output count) is hand-written in `src/nanosynth/ugens/*.py`. Nothing checks it against an independent source:

- `spec/nanosynth-ugens.json` is generated from those classes.
- `tests/fixtures/scgf/` holds nanosynth's own compiled output.

Both agree with any metadata error. Wrong metadata fails in three ways:

| Error | Effect |
|-|-|
| Too few outputs | Plugin writes past its output buffers: crash or memory corruption |
| Too few inputs | Plugin reads past its input array: garbage values or crash |
| Wrong input order or default | Wrong audio, no error |

## Evidence

- `DiskOut` declared 0 outputs and writes `OUT(0)`. Every `Server.record()` crashed the engine (fixed).
- A static scan of `thirdparty/supercollider/server/plugins/*.cpp` compares the highest literal `OUT(n)`/`IN(n)` index per `<UGen>_next*`/`_Ctor` function with the declared counts. It found:
  - `PanB`: declares 3 outputs, writes 4 (W, X, Y, Z). Confirmed.
  - 8 UGens whose C++ reads more inputs than nanosynth declares, with no `mNumInputs` guard: `Delay1`, `Delay2`, `KeyTrack`, `NumRunningSynths`, `PV_HainsworthFoote`, `PV_JensenAndersen`, `SpecPcile`, `Vibrato`. Unverified.
- The scan cannot see 10 UGens with no matching plugin function, indices computed in loops or macros, input order, or defaults.

## Proposal

Four steps, cheapest first. Each step's check runs in CI.

### 1. Fix the confirmed and triage the candidates (done 2026-10-04)

Checked against the class library at tag `Version-3.14.1`, matching `thirdparty/supercollider/SCVersion.txt`.

| UGen | Finding | Action |
|-|-|-|
| `PanB` | 4 outputs in sclang and C++; nanosynth declared 3. Rendering it segfaulted | `channel_count=4` |
| `Delay1` | sclang has `x1` | Added; `Default()` resolves to 0 (ar) or the input (kr), as sclang |
| `Delay2` | sclang has `x1`, `x2` | Added, same rule |
| `Vibrato` | sclang has `trig` | Added as `trigger` |
| `SpecPcile` | sclang has `binout` | Added as `bin_out` |
| `KeyTrack` | `ZIN0(3)` is inside a comment | False positive |
| `PV_HainsworthFoote`, `PV_JensenAndersen` | `ZIN0(7)` is inside a commented `printf` | False positives |
| `NumRunningSynths` | Ctor calls `INRATE(0)` with 0 inputs; sclang also sends 0 | Upstream bug, likely meant `mCalcRate`. Not a metadata error |

`tests/test_ugen_sclang_parity.py` checks each fix's arity and renders `PanB`, `Delay1` and `Delay2` through NRT. Each test fails, or crashes, on the old metadata.

The step 2 scan must skip comments; three of the four false positives came from commented code.

### 2. Static plugin scan as a test (done 2026-10-05)

`tests/test_ugen_plugin_scan.py` fails when a `<UGen>_next*`/`_Ctor` function writes `OUT(n)` or reads `IN(n)` beyond the counts in `spec/nanosynth-ugens.json`. It strips comments first and skips functions that read `mNumInputs`/`mNumOutputs`.

- The allowlist is a dict in the test: `NumRunningSynths_Ctor` only.

- A coverage test pins the 6 UGens with no matching function (`DC`, `K2A`, `MulAdd`, `Sum3`, `Sum4` are C++ structs; `PV_ChainUGen` is abstract).

- A self-test reintroduces the `DiskOut`, `PanB` and `Vibrato` errors and checks the scan reports them.

### 3. sclang reference (done 2026-10-05)

`scripts/sclang_reference.scd` calls every rate method of every `UGen` subclass with its defaults, and records the args, inputs, outputs, output rates and special index of the last instance in the graph. `make sclang-reference` (`scripts/sclang_reference.py`) runs it with default class-library paths excluded, checks the version against `SCVersion.txt`, and writes `spec/sclang-reference.json`.

- Run it with the official 3.14.1 release, e.g. sclang from `SuperCollider-3.14.1-macOS-universal.dmg`. sclang 3.13 cannot parse the 3.14 library.

- Arguments with no default get `DC` at the method's rate. Seven named arguments get structured values (`envelope`, `numChannels`, Klank specs).

- sclang 3.14 stores non-literal defaults (`root = 60.midicps`, `x1 = (in)`) as nil in `prototypeFrame`, and evaluates them when the argument is nil. The script reads the argument list from the method source, passes nil for those arguments, and records the expression text.

- The probe reads the graph before `finishBuild`. sclang 3.14 drops unused pure UGens there.

- If the class is missing from the graph, the probe retries with a UGen as the first argument (`Lag.ar(0)` returns 0).

`tests/test_ugen_reference.py` probes each nanosynth UGen the same way and compares rates, output count, special index, input count and each constant input. A slot where either side has a UGen is skipped: that is a required argument on one side, not an order error. Deviations live in `tests/fixtures/ugen_reference_allowlist.json` with reasons; a stale entry fails.

The first run found errors in 34 UGens. `tests/test_ugen_sclang_parity.py` renders the `Duty`/`Dwhite` and `BufDelayN` fixes.

| Class | UGens | Action |
|-|-|-|
| `length` sent last; plugin reads `IN(0)` | `Dwhite`, `Dbrown`, `Diwhite`, `Dibrown`, `Dgeom` | Reordered |
| `level`/`done_action` swapped | `Duty` | Reordered |
| Extra `maximum_delay_time` read as the delay time | `BufDelay{N,L,C}`, `BufComb{N,L,C}`, `BufAllpass{N,L,C}` | Removed |
| No plugin | `BHiCut`, `BLowCut` | Removed |
| No plugin; sclang pseudo-UGen | `HilbertFIR`, `Dunique` | Pseudo-UGen, as sclang. `Dunique`'s graph matches sclang's UGen for UGen |
| `kr` with no control-rate calc function | `InFeedback`, `OffsetOut`, `BufComb*`, `BufAllpass*` | `kr` removed |
| Rate missing | `PV_HainsworthFoote`, `PV_JensenAndersen` (`ar`), `Convolution3` (`kr`), `Schmidt` (`ir`) | Added |
| Output never written | `SendTrig` | 0 outputs |
| Required inputs silently dropped | `Poll` | `source` required, `trigger` defaults to 10 |
| Default differs | `AmpComp`, `ExpRand`, `NRand`, `RandID`, `LeakDC.kr`, `Gendy1.kr`, `Gendy2.kr` | sclang's default |

Implementing `Dunique` found two more errors the comparison could not see:

- `BinaryOperator` was 2 high from `MINIMUM` on. The probe compares UGen classes only, not operator indices. `test_ugen_plugin_scan.py` now checks both operator enums against the plugin enums.

- `Dbufwr` sent its value first. sclang's defaults are 0, 0, 0, 1 and so are nanosynth's, so the swapped slots compared equal. Any UGen whose swapped inputs share a default passes the same way. Probing each argument with a distinct value would close this; see `TODO.md`.

Kept against sclang (allowlisted): `Dibrown` defaults, because sclang's `step = 0.01` truncates to 0 in `Dibrown_next`; `kr` on the two PV detectors, because their plugin fills any block size.

### 4. Optional: dynamic sweep under AddressSanitizer

- Build the plugins with `-fsanitize=address`.
- NRT-render every UGen with default inputs, one subprocess each.

This catches overruns with computed indices, which steps 2 and 3 miss. Run it nightly or on demand; the ASan build is slow.

## Alternatives considered

- **Compare against supriya's UGen definitions.** No sclang needed. But nanosynth was ported from supriya, so shared errors would pass. Weak independence.
- **Parse the `.sc` class files directly.** Output counts are set in `init` methods (`initOutputs(n)`, `^0.0`, computed counts), so a parser would be brittle. Running sclang avoids parsing it.

## Effort (estimates)

| Step | Estimate |
|-|-|
| 1 | half a day, plus a test per fixed UGen |
| 2 | half a day |
| 3 | 2-3 days, mostly triaging the first mismatch list (size unknown) |
| 4 | 1-2 days for the ASan build and sweep harness |
