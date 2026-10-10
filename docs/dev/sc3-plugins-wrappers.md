# sc3-plugins wrappers

`nanosynth.ugens.sc3` wraps 458 of the 483 UGen classes in sc3-plugins 3.14.1. A SynthDef that uses them needs a server with sc3-plugins installed.

```python
from nanosynth.ugens.sc3 import DFM1
DFM1.ar(source=Saw.ar(), freq=800, res=0.5)
```

## Files

| File | Role | Edited by |
|-|-|-|
| `scripts/sclang_reference.scd` | Builds a SynthDef for every UGen class and rate in sclang; records arguments, inputs, outputs, rates and superclasses | hand |
| `scripts/sc3_plugins_reference.py` | Runs the `.scd` with the sc3-plugins class files added; keeps sc3-plugins' classes; marks each with its library and whether its name appears in the C/C++ sources (`has_unit`) | hand |
| `spec/sc3-plugins-reference.json` | sclang's wire contract for sc3-plugins | `sc3_plugins_reference.py` |
| `scripts/generate_sc3_ugens.py` | Writes `sc3.py` and the skipped list; holds `WIRE_ORDER` | hand |
| `scripts/ugen_probe.py` | Builds a nanosynth UGen as the `.scd` builds the sclang one, and compares them; shared with `tests/test_ugen_reference.py` | hand |
| `src/nanosynth/ugens/sc3.py` | The wrappers | `generate_sc3_ugens.py` |
| `src/nanosynth/ugens/sc3_custom.py` | 6 classes whose sclang methods compute inputs | hand |
| `spec/sc3-plugins-skipped.json` | Classes not wrapped, with the reason | `generate_sc3_ugens.py` |
| `tests/fixtures/sc3_reference_allowlist.json` | Accepted differences from sclang, with the reason | hand |
| `tests/test_sc3_ugens.py` | The checks below | hand |

## How a class is wrapped

The reference comes from sclang, not from parsing `.sc` files, so any argument handling inside a sclang method shows in it.

For each class in the reference, `generate_sc3_ugens.py`:

1. Skips it if `has_unit` is false. The class is sclang-only: a server has no unit to run.
2. Skips it if sclang could not build it, or if it builds only other UGens (a pseudo-UGen).
3. Writes a class whose parameters are the sclang method's arguments. `mul` and `add` are dropped. camelCase becomes snake_case, `in` becomes `source`, and a name that is a keyword or a `UGen` attribute gets a trailing `_`. A `numChannels` or `numChans` argument that sclang does not send becomes `channel_count`.
4. Takes the parameter order from `WIRE_ORDER` instead, when the class has an entry there.
5. Builds the class and compares it with sclang input by input, at every rate. Rates that differ are dropped. A class that still differs is skipped, unless its differences match its allowlist entry exactly.

Classes in `sc3_custom.__all__` are not generated. `sc3.py` imports and re-exports them.

## Hand-maintained parts

| Part | Holds | When to edit |
|-|-|-|
| `WIRE_ORDER` | For 18 classes, the arguments in the order sclang sends them. `*name` is an array sent as its elements; `*name?` one that may be empty | A class is skipped as "differs from sclang" and its sclang method sends its arguments reordered, drops one, sends `mul`/`add` as inputs, or appends an array |
| `sc3_custom.py` | FeatureSave, MatchingPResynth, Getenv, NovaDiskOut, TextVU, SOMRd | The sclang method computes inputs: a count, a string as character codes, an output count taken from an argument |
| Allowlist | NovaDiskOut, StkInst, TextVU | The difference is a probe artifact or deliberate. Give the reason |

Read the sclang method in the sc3-plugins `.sc` file before editing any of these. Where sclang and the C++ disagree, check the C++: BMoog's `saturation` is never sent, and its read in the C++ is commented out.

## Checks

`tests/test_sc3_ugens.py`:

- The reference was made by sclang and sc3-plugins at the vendored SuperCollider version.
- `sc3.py` and the skipped list are what the generator writes now.
- Every reference class is wrapped or skipped with a reason.
- Every wrapped class matches sclang, apart from its allowlist entry.
- Classes that compute inputs build the expected inputs from real arguments; the probe passes only placeholders.

With `NANOSYNTH_SC3_PLUGINS` set to a directory of built sc3-plugins:

- Every wrapped name is registered by some plugin. NovaDiskOut is exempt: NovaDiskIO is off in a default build.
- DFM1 renders through the plugin.

## Skipped classes (25)

| Reason | Count |
|-|-|
| sclang-only: no unit in the C/C++ sources | 14 |
| sclang cannot build it | 10 |
| Pseudo-UGen | 1 |

## Building sclang without Qt

The reference scripts need sclang at the vendored SuperCollider version. A distribution's sclang is often older. sclang builds in about 20 s from the release source tarball, `SuperCollider-<version>-Source.tar.bz2`. Dependencies: readline, ALSA headers and libsndfile.

```
cmake -S SuperCollider-3.14.1-Source -B build/sclang -DCMAKE_BUILD_TYPE=Release \
    -DSC_QT=OFF -DSC_IDE=OFF -DSUPERNOVA=OFF -DSC_HIDAPI=OFF -DNO_AVAHI=ON \
    -DSC_ABLETON_LINK=OFF -DENABLE_TESTSUITE=OFF -DINSTALL_HELP=OFF -DFFT_GREEN=ON \
    -DNO_X11=ON -DAUDIOAPI=portaudio -DSYSTEM_PORTAUDIO=OFF -DSC_EL=OFF -DSC_VIM=OFF \
    -DSC_ED=OFF -DUSE_CCACHE=OFF
cmake --build build/sclang --target sclang -j
```

Without JACK, FFTW, libudev or Avahi installed, the options above select PortAudio, the Green FFT, no HID and no Avahi. They affect the servers, which this build does not use. Add `-DSNDFILE_INCLUDE_DIR=... -DSNDFILE_LIBRARY=...` if libsndfile is not installed.

The scripts find the class library at `../share/SuperCollider/SCClassLibrary` from the binary:

```
mkdir -p build/sclang/install/bin build/sclang/install/share/SuperCollider
cp build/sclang/lang/sclang build/sclang/install/bin/
ln -s "$PWD/SuperCollider-3.14.1-Source/SCClassLibrary" build/sclang/install/share/SuperCollider/
```

This build reproduces `spec/sclang-reference.json` exactly.

## Regenerating the reference

```
export SCLANG=build/sclang/install/bin/sclang
uv run python scripts/sc3_plugins_reference.py /path/to/sc3-plugins-3.14.1-Source
uv run python scripts/generate_sc3_ugens.py
uv run pytest tests/test_sc3_ugens.py
```

The script refuses an sclang or an sc3-plugins source at another version. Use the release tarball, `sc3-plugins-<version>-Source.tar.bz2`: its directory name gives the version.

## A new SuperCollider or sc3-plugins release

sc3-plugins is released with SuperCollider's version number, and its plugins must be built against the same SuperCollider headers: scsynth checks `api_version` when it loads one.

1. Update the vendored SuperCollider in `thirdparty/supercollider`. The reference test then fails until step 2.
2. Build sclang at the new version, as above, and run `make sclang-reference`. Fix the core UGens it flags, or allowlist them in `tests/fixtures/ugen_reference_allowlist.json`.
3. Regenerate the sc3-plugins reference and wrappers against the new sc3-plugins source, as above.
4. Read the changes to `spec/sc3-plugins-skipped.json`:
   - A class newly skipped as "differs from sclang" changed its sclang method. Give it a `WIRE_ORDER` entry, or write it in `sc3_custom.py`.
   - A `WIRE_ORDER` entry or `sc3_custom` class that fails names a method that changed. Read the new `.sc` and update it.
   - A new class with no unit, or one sclang cannot build, needs nothing.
5. Run `make test` with `NANOSYNTH_SC3_PLUGINS` set to the new plugins, built against the new headers.

Renamed sclang arguments rename the Python parameters. Note that in the CHANGELOG under Upgrading: it breaks callers.

The SSP repo builds the same versions for the device; its steps are in its `docs/dev/scsynth-module.md`.
