# UGen metadata audit

Status: step 1 done, steps 2-4 proposed, 2026-10-04. Tracked in `TODO.md` (High, "UGen metadata has no independent reference").

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

### 2. Static plugin scan as a test

Turn the scan into `tests/test_ugen_plugin_scan.py`:

- Fail when C++ writes `OUT(n)` with `n >= declared outputs`, or reads `IN(n)` with `n >= declared inputs` without an `mNumInputs` guard.
- Keep an allowlist, `tests/fixtures/ugen_scan_allowlist.json`, with a reason per entry for verified false positives.

It needs no SuperCollider install and runs in under a second. It catches the `DiskOut`/`PanB` class only, so it is a tripwire, not the oracle.

### 3. sclang reference (the oracle)

sclang defines the SynthDef wire contract: input order, defaults, output count, rate and special index. Use it as the reference.

- `scripts/sclang_reference.scd`: for every `UGen.allSubclasses` and each rate method, build a SynthDef calling the method with its `prototypeFrame` defaults. From the resulting graph, record per UGen:
  - argument names and defaults;
  - input count;
  - output count and output rates;
  - special index;
  - supported rates.

  Write the results to `spec/sclang-reference.json`.
- Run it with sclang at the vendored version, as a manual `workflow_dispatch` job. Regenerate only when `SCVersion.txt` changes, and commit the JSON.
- `tests/test_ugen_reference.py` compares each nanosynth UGen's structural tuple against the reference. Deviations go in an allowlist with reasons: Python renames, nanosynth-only pseudo-UGens, UGens whose defaults sclang cannot instantiate.

The comparison is per UGen, not byte-for-byte on compiled SCgf. sclang and nanosynth optimize graphs differently (`MulAdd`, `Sum3`/`Sum4`, constant folding), so byte equality would fail on correct graphs.

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
