# Building sc3-plugins into the wheel

Status: built into the wheel on macOS arm64 (2026-10-15). Linux and Windows are untested; CI is the first build there. Wrappers for these UGens: `sc3-plugins-wrappers.md`. Motivation: SuperDirt's `super*` synths (`livecoding.md`).

## Source

sc3-plugins tag `Version-3.14.1` (`fa926d6`, 2026-08-26). It has 2 submodules: `external_libraries/nova-simd` and `external_libraries/stk`. The checkout is 32 MB, of which `source/` is 18 MB.

## Feasibility trial on macOS arm64

A full upstream build, before vendoring.

- It configures against `thirdparty/supercollider` (`SC_PATH`) with no missing Boost headers.

- 172 scsynth and 172 supernova targets. HOA accounts for 96 of each. No target name clashes with the core plugins.

- One compile error: `source/NCAnalysisUGens/SMS.cpp:442`, `if(0<=bufnum<= world->mNumSndBufs)`. Clang 21 makes `-Wparentheses` an error here. The condition is always true, so it is also a real bug. Patch it to `0 <= bufnum && bufnum < world->mNumSndBufs`.

- A clean build of all 344 targets takes 86 s (Ninja, 8 cores).

- The embedded scsynth loaded all 172 scsynth plugins. NRT renders gave non-zero peaks for `MdaPiano`, `MembraneHexagon`, `AY`, `BMoog`, `SawDPW` and `SwitchDelay`. `FM7` was not rendered because it has no wrapper.

- `api_version` matches, since the plugins compile against the vendored headers (`sc_api_version = 3`, `SC_InterfaceTable.h:26`).

## Size (trial)

| Set | Compressed (`zip -9`) |
|-|-|
| scsynth, all 172 | 3.57 MB |
| supernova, all 172 | 3.58 MB |
| scsynth without HOA | 2.15 MB |
| The 7 SuperDirt needs | 1.16 MB |

Both servers add about 7.1 MB to each wheel, or about 4.3 MB without HOA. `MdaUGens` alone is 1.22 MB raw, mostly embedded sample data.

## Dependencies

- STK and nova-simd come with the repo. The vendored SC tree already has nova-simd.

- FFTW3f is not included. `PitchDetection` (`Tartini.h:34`) calls `fftwf_*`. On macOS, `PitchDetection` and `NCAnalysisUGens` link Accelerate instead. On Linux and Windows, drop `PitchDetection` or build FFTW. The `if (!FFTW3F_FOUND)` guard (`source/CMakeLists.txt:265`) is malformed CMake and never fires, so a missing FFTW shows up as a compile error.

- `LadspaUGen`: set `-DLADSPA=OFF`. It is already skipped on Windows.

- `NovaDiskIO` (the only heavy Boost user) is off by default. Keep it off.

The 7 plugins SuperDirt needs (`MdaUGens`, `MembraneUGens`, `AY_UGen`, `BlackrainUGens`, `MCLDOscUGens`, `FM7`, `RFWUGens`) have no external dependencies.

## Integration

Do not `add_subdirectory` the sc3-plugins top level. It changes global `CMAKE_CXX_FLAGS` (`-std=c++17`, `-stdlib=libc++`, `-msse`), adds `-fvisibility=hidden` through `add_definitions`, includes CPack again, and defines an `uninstall` target.

Done:

- `thirdparty/sc3-plugins/`: a trimmed copy (9.1 MB, 443 files), made by `scripts/vendor_sc3_plugins.py`.

- `cmake/sc3_plugins.cmake` builds each plugin as an `EXCLUDE_FROM_ALL` `MODULE` target, with a `_supernova` twin when supernova is embedded. `CMakeLists.txt` appends them to `SCSYNTH_PLUGIN_TARGETS` and `SUPERNOVA_PLUGIN_TARGETS`. They install into `nanosynth/plugins/` with the core plugins, so `find_ugen_plugins_path` is unchanged.

- CMake option `NANOSYNTH_SC3_PLUGINS`, default `ON`. The value is cached in `build/{wheel_tag}`: after one `-Ccmake.define.NANOSYNTH_SC3_PLUGINS=OFF` build, later plain builds stay off until it is set `ON` again.

- 75 plugins per server: upstream's 172 without HOA (96) and `LadspaUGen`. `PitchDetection` is macOS only (Accelerate), so Linux and Windows get 74.

- Suffix and visibility follow the core plugins: `.scx` on macOS and Windows, `.so` on Linux, no prefix, hidden symbols. nova-simd comes from `thirdparty/supercollider`; sc3-plugins' own copy is from 2013 and differs only in licence headers.

- On Windows each target gets `NOMINMAX` and `_USE_MATH_DEFINES`; supernova twins also get `BOOST_ALL_NO_LIB`, `/Zc:__cplusplus` and `ws2_32`, as `_supernova` and the core supernova plugins do.

- Wrappers: `FM7` and `PulseDPW` in `src/nanosynth/ugens/sc3_custom.py`. `FM7` is allowlisted in `tests/fixtures/sc3_reference_allowlist.json`, since sclang could not build it.

- Tests: `tests/test_sc3_ugens.py` renders `MdaPiano`, `MembraneHexagon`, `AY`, `BMoog`, `SawDPW`, `PulseDPW`, `FM7`, `SwitchDelay` and `DFM1` in NRT and checks for finite, non-silent output. They use the bundled plugins, or the `NANOSYNTH_SC3_PLUGINS` environment variable, and skip if neither exists.

- Checked by hand: the embedded supernova loads a SynthDef with `MdaPiano`, and rejects one with an unbuilt HOA UGen.

Measured on macOS arm64:

| | Without | With |
|-|-|-|
| `uv build --wheel` | 2.3 MB | 6.2 MB |
| `make build` (delocated) | 2.6 MB | 6.6 MB |
| Clean build of the sc3 targets | | about 60 s |

The sdist grows by about 2.5 MB (`thirdparty/sc3-plugins` compressed).

## Regenerating the vendored tree

```sh
git clone --recursive -b Version-3.14.1 https://github.com/supercollider/sc3-plugins /tmp/sc3-plugins
uv run python scripts/vendor_sc3_plugins.py /tmp/sc3-plugins
```

The script replaces `thirdparty/sc3-plugins/` and keeps:

- `license.txt`, `README.md` and `source/`, without `HOAUGens`, `NovaDiskIO`, `LadspaUGen` and `local`.

- From `external_libraries/stk`: `LICENSE`, `README.md`, `include/` and `src/`.

It drops `website/`, `quarks/`, `osx_package/`, packaging and Jekyll files, every upstream `CMakeLists.txt`, every `sc/` directory (sclang classes and HelpSource; licence files inside are kept, e.g. `ATK/sc/LICENSE`), nova-simd and `.git*` files. It then applies `patches/sc3-plugins-sms-bufnum.patch`, the `SMS.cpp:442` fix above.

For a new release, diff upstream `source/CMakeLists.txt` against `cmake/sc3_plugins.cmake` for new plugins or flags.

## Licence

sc3-plugins is GPLv2-or-later overall (`license.txt`). ATK is GPLv3+ (`AtkUGens.cpp:18`). HOA, DEIND/Faust and nova-simd are GPL. STK is permissive. `mdaPiano_sc3.h:2` refers to a `readme.license` that is not in the tree. No GPL-incompatible code was found, but the scan was not exhaustive; GPLv2-only files were not audited.

`pyproject.toml` declares MIT, but the wheel already bundles GPLv3 SuperCollider. sc3-plugins does not change that, but the metadata should say so.

## Risks

- Linux (manylinux GCC) and Windows (MSVC) builds have not run. The first CI run of `build-wheels` is the test; its `pytest` step runs the render tests against the installed wheel.

- MSVC: upstream builds Windows without `/std:c++17`. The supernova twins have no upstream Windows build at all.

- Each cibuildwheel Python rebuilds the plugins. A separate `py3-none-<platform>` wheel would avoid this.

- `StkInst` instruments that read STK rawwaves cannot find them: the rawwaves are not vendored, and `StkGlobals` has no wrapper.

- Supernova twins double the size. Drop them if no supernova user needs sc3-plugins.

- `pyproject.toml` declares MIT; the wheel bundles GPL code (see Licence).
