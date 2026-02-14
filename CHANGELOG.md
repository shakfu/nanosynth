# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Server` class (`nanosynth.server`) -- high-level wrapper around the embedded scsynth engine with boot/quit lifecycle, node ID allocation, SynthDef dispatch, and convenience methods (`synth`, `group`, `free`, `set`). Supports context manager usage
- `Server.managed_synth()` and `Server.managed_group()` context managers -- create a synth or group and automatically free it on context exit (including on exceptions); guard against freeing if the server has already stopped
- `SynthDef.send(server)` and `SynthDef.play(server, **params)` convenience methods for sending SynthDefs and creating synths in one call
- `SynthDef.dump_ugens()` pretty-printer -- returns a human-readable UGen graph representation (modeled on SuperCollider's `SynthDef.dumpUGens`), showing UGen types, rates, input wiring, operator names, and multi-output counts
- `Envelope.compile()` -- dedicated serialization path producing `tuple[float, ...]` directly, bypassing UGenVector/ConstantProxy; raises `TypeError` on UGen inputs. `serialize()` retained for UGen graph wiring
- Demo scripts `12_server_sine.py` (sine wave via Server API) and `13_server_pad.py` (gated pad chord progression with `managed_synth`, `managed_group`, and `server.set()`)
- `EmbeddedProcessProtocol.send_packet()` and `send_msg()` convenience methods for sending OSC to the engine without importing `_scsynth` directly
- Auto-generated docstrings for all `@ugen`-decorated classes (e.g. `SinOsc -- ar, kr\n\nParameters:\n    frequency (default: 440.0)`)
- `__slots__` on core graph classes (`UGen`, `OutputProxy`, `ConstantProxy`, `UGenVector`, `UGenOperable`, `UGenScalar`, `UGenSerializable`) for lower memory usage
- OSC test suite now runs all 24 tests against both the C++ and pure-Python backends (48 total)
- `EmbeddedProcessProtocol` state machine tests: initial state, quit no-op, send errors when offline, callback storage, boot-when-active guard
- Test coverage for `SynthDefBuilder` cross-scope errors, graph optimization (`_optimize`/`_eliminate`), `Envelope.linen`/`.triangle`/`.asr` factory methods, multi-channel UGens (`In`, `PanAz`, `DecodeB2`), `compile_synthdefs` with multiple SynthDefs, demand-rate UGens (`Dseq`, `Drand`, `Duty`, etc.), and `@synthdef` decorator (trigger/audio/lag rates, complex graphs) -- 54 new tests (322 -> 376)

### Fixed

- macOS CoreAudio teardown crash: registered a C-level `atexit` guard in `_scsynth.cpp` (after `World_New`) that calls `_exit(0)` before CoreAudio's static destructors run; removed `os._exit(0)` from all 11 demo scripts
- `WorldStrings` memory leak in `_scsynth.cpp`: capsule destructor now frees the heap-allocated strings object
- Windows CI build failure caused by Strawberry Perl's incompatible ccache crashing MSVC (`STATUS_ENTRYPOINT_NOT_FOUND`); disabled SC's ccache integration on Windows
- nanobind 2.11 compatibility: replaced capturing lambda in `_scsynth.cpp` capsule constructor with `WorldHandle` struct and non-capturing cleanup function
- Removed 11 `type: ignore[arg-type]` suppressions from `EnvGen` by widening `UGen.__init__`, `_new_single`, and `_new_expanded` kwargs to `UGenRecursiveInput | None`

### Changed

- Cleaned up `Envelope.serialize()` and `UGenSerializable.serialize()` signatures: removed unused `**kwargs` parameter, added docstring documenting the wire format
- Extracted 6 enum classes (`CalculationRate`, `ParameterRate`, `BinaryOperator`, `UnaryOperator`, `DoneAction`, `EnvelopeShape`) from `synthdef.py` into `enums.py`
- Extracted SCgf binary compiler (`_compile_*`, `_encode_*`, `compile_synthdefs`) from `synthdef.py` into `compiler.py`
- Pinned `nanobind>=2.11,<3` in both `[build-system]` and `[dependency-groups]`
- All `ValueError` raises in `synthdef.py` (10) and `envelopes.py` (2) now include descriptive messages
- Narrowed bare `except Exception` in `osc.py` to `except (ValueError, IndexError, struct.error)`
- Refactored all 11 demo scripts to use `_options_to_world_kwargs()` instead of duplicated 25-line `_options_kwargs()` functions

## [0.1.0]

Initial release.

### Added

- **SynthDef compiler** -- `SynthDefBuilder` context manager and `@synthdef` decorator for defining UGen graphs in Python, compiled to SuperCollider's SCgf binary format
- **290+ UGen definitions** across 18 categories: oscillators, filters, BEQ filters, noise, delays, envelopes, panning, demand, dynamics, chaos, granular, buffer I/O, physical modeling, reverb, convolution, I/O, lines, and triggers
- **Envelope system** -- `Envelope` class with `adsr`, `asr`, `linen`, `percussive`, and `triangle` factory methods, plus the `EnvGen` UGen
- **OSC codec** -- `OscMessage` and `OscBundle` encode/decode with pure-Python implementation and C++ accelerated path via nanobind (`_osc.cpp`)
- **Embedded libscsynth** -- in-process SuperCollider engine via nanobind (`_scsynth.cpp`), with `EmbeddedProcessProtocol` for lifecycle management and `Options` frozen dataclass for server configuration
- **Vendored dependencies** -- SuperCollider 3.14.1, libsndfile, and PortAudio built from source via `add_subdirectory`; SC trimmed to 27MB (from 132MB) with only libscsynth, UGen plugins, and required boost headers; libsndfile tailored for WAV/AIFF only (no external codec deps). Audio backend: CoreAudio on macOS, vendored PortAudio on Linux/Windows
- **Incremental builds** -- `make build` uses `--wheel --no-build-isolation` with persistent cmake build cache in `build/`; incremental rebuilds in ~3s
- **Wheel repair** -- platform-conditional wheel repair via delocate (macOS), auditwheel (Linux), delvewheel (Windows); SC's macOS `POST_BUILD` bundle-copy commands disabled to prevent duplicate plugins leaking into the wheel
- **Demos** -- three example scripts: sine wave (`01_sine.py`), subtractive synthesis (`02_subtractive.py`), and FM synthesis with melody (`03_fm.py`)
- **Test suite** -- 291 tests covering OSC round-trip encoding, SynthDef compilation, UGen instantiation and calculation rates, and server options/lifecycle
- **Full `mypy --strict` compliance** with complete type annotations
- **CI workflow** -- GitHub Actions with cibuildwheel building wheels for CPython 3.10--3.13 across macOS ARM64, Linux x86_64, and Windows x86_64; sdist built separately; all artifacts aggregated into a single download
- **Development tooling** -- Makefile with `dev`, `build`, `sdist`, `test`, `lint`, `format`, `typecheck`, `qa`, `clean`, and `reset` targets
