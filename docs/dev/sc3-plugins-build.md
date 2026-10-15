# Building sc3-plugins into the wheel

Status: feasibility checked 2026-10-15 on macOS arm64 only. Nothing in the repo was changed. Wrappers for these UGens: `sc3-plugins-wrappers.md`. Motivation: SuperDirt's `super*` synths (`livecoding.md`).

## Source

sc3-plugins tag `Version-3.14.1` (`fa926d6`, 2026-08-26). It has 2 submodules: `external_libraries/nova-simd` and `external_libraries/stk`. The checkout is 32 MB, of which `source/` is 18 MB.

## Result on macOS arm64

- It configures against `thirdparty/supercollider` (`SC_PATH`) with no missing Boost headers.

- 172 scsynth and 172 supernova targets. HOA accounts for 96 of each. No target name clashes with the core plugins.

- One compile error: `source/NCAnalysisUGens/SMS.cpp:442`, `if(0<=bufnum<= world->mNumSndBufs)`. Clang 21 makes `-Wparentheses` an error here. The condition is always true, so it is also a real bug. Patch it to `0 <= bufnum && bufnum < world->mNumSndBufs`.

- A clean build of all 344 targets takes 86 s (Ninja, 8 cores).

- The embedded scsynth loaded all 172 scsynth plugins. NRT renders gave non-zero peaks for `MdaPiano`, `MembraneHexagon`, `AY`, `BMoog`, `SawDPW` and `SwitchDelay`. `FM7` was not rendered because it has no wrapper.

- `api_version` matches, since the plugins compile against the vendored headers (`sc_api_version = 3`, `SC_InterfaceTable.h:26`).

## Size

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

Plan, in-wheel:

1. Vendor a trimmed copy at `thirdparty/sc3-plugins/`. Drop `website/`, `quarks/`, `osx_package/`, `NovaDiskIO/`, `HOAUGens/` and each `sc/HelpSource`. HOA (higher-order ambisonics: 96 of the 172 plugins, about 2.8 MB of the 7.1 MB) is excluded because no SuperDirt synth uses it (decided 2026-10-15).

2. Write a nanosynth CMake fragment that builds each plugin directory as an `EXCLUDE_FROM_ALL` target. Install the targets next to the core plugins, as `SCSYNTH_PLUGIN_TARGETS` and `SUPERNOVA_PLUGIN_TARGETS` already are. A subdirectory such as `plugins/sc3/` keeps them apart. `find_ugen_plugins_path` then returns both directories; scsynth accepts a colon-separated path (tested).

3. Apply the `SMS.cpp` patch, and record it next to the trim script.

4. Build `PitchDetection` on macOS only, unless FFTW is added to the Linux and Windows builds.

5. Add hand wrappers for `FM7` (skipped in `spec/sc3-plugins-skipped.json:12`) and `PulseDPW`. `PulseDPW` is a sclang composite of two `SawDPW` (`MCLDOscUGens.sc:12`), so it becomes a `PseudoUGen`.

Build cost: cibuildwheel rebuilds the plugins for each CPython version, adding about 86 s per wheel on macOS. The plugins do not use the Python ABI. A separate `py3-none-<platform>` wheel would be built once per platform. That is the alternative if CI time or size becomes a problem; it is not needed to start.

## Licence

sc3-plugins is GPLv2-or-later overall (`license.txt`). ATK is GPLv3+ (`AtkUGens.cpp:18`). HOA, DEIND/Faust and nova-simd are GPL. STK is permissive. `mdaPiano_sc3.h:2` refers to a `readme.license` that is not in the tree. No GPL-incompatible code was found, but the scan was not exhaustive; GPLv2-only files were not audited.

`pyproject.toml` declares MIT, but the wheel already bundles GPLv3 SuperCollider. sc3-plugins does not change that, but the metadata should say so.

## Open

- Linux (manylinux GCC) and Windows (MSVC) builds are untested. Next step: a CI dry run on all three platforms.

- Supernova plugins double the size. Ship them only if supernova users need sc3-plugins.
