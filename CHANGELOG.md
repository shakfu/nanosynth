# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`Synth` / `Group` proxy objects**: `Server.synth()` and `Server.group()` now return lightweight `Synth` and `Group` proxy objects instead of raw ints. Proxies support `.set(**params)`, `.free()`, context manager usage (`with server.synth(...) as node:`), and are fully int-compatible via `__int__()`, `__index__()`, `__eq__()`, and `__hash__()`. `managed_synth()` and `managed_group()` also yield proxies. Existing code comparing against ints continues to work unchanged
- **`control()` function**: convenience constructor for SynthDef parameters with rate and lag metadata -- `control(440.0, rate="ar")` is equivalent to `Parameter(value=440.0, rate=ParameterRate.AUDIO)`. Accepts string rate tokens (`"ar"`, `"kr"`, `"ir"`, `"tr"`) or `ParameterRate` enum values
- **Tuple syntax for `SynthDefBuilder`**: parameters can be specified as tuples -- `SynthDefBuilder(freq=("ar", 440.0))` for `(rate, value)` or `SynthDefBuilder(amp=("kr", 0.5, 0.1))` for `(rate, value, lag)`. Works alongside `float`, `Parameter`, and `control()` styles
- **Trimmed `__all__` exports**: `from nanosynth import *` now exports ~60 names (core API + 29 common UGens) instead of 340+. The full UGen set remains available via `from nanosynth.ugens import *` or qualified imports

- **Extended operators**: `BinaryOperator` expanded from 7 to 43 entries, `UnaryOperator` from 2 to 34, covering SC's full practical operator set (power, integer division, comparisons, bitwise ops, trig, pitch conversion, clipping, ring modulation, etc.)
- **Operator methods on UGenOperable**: 16 new dunder methods (`__pow__`, `__floordiv__`, `__le__`, `__ge__`, `__and__`, `__or__`, `__xor__`, `__lshift__`, `__rshift__` and their reverse variants), `equal()`/`not_equal()` explicit comparison methods, 25 named binary methods (`min_`, `max_`, `clip2`, `fold2`, `wrap2`, `ring1`--`ring4`, `atan2`, `hypot`, etc.), and 32 named unary methods (`midicps`, `cpsmidi`, `dbamp`, `ampdb`, `tanh_`, `softclip`, `distort`, `squared`, `sqrt_`, `exp_`, `log_`, `sin_`, `cos_`, etc.)
- **Constant folding** for new operators: `POWER`, `INTEGER_DIVISION`, `MINIMUM`, `MAXIMUM`, comparison ops, and all math-stdlib unary ops fold `float op float` at compile time
- **POWER optimizations** in `BinaryOpUGen._new_single`: `x ** 0` folds to `1`, `x ** 1` folds to `x`
- **Buffer management** on `Server`: `alloc_buffer()`, `read_buffer()`, `write_buffer()`, `free_buffer()`, `zero_buffer()`, `close_buffer()`, `next_buffer_id()`, plus `managed_buffer()` and `managed_read_buffer()` context managers. Buffer IDs are auto-allocated (monotonically from 0) or explicitly specified; allocated buffers tracked in `_allocated_buffers` set
- **Reply handling**: C++ reply callback (`set_reply_func` in `_scsynth.cpp`) routes OSC responses from the engine back to Python; `EmbeddedProcessProtocol.set_reply_callback()` wires it at boot; `Server` gains `_dispatch_reply()` router, `on()`/`off()` for persistent handlers, `wait_for_reply()` for blocking one-shot waits, and `send_msg_sync()` for send-and-wait patterns -- all thread-safe
- Demo script `18_operators_buffers.py`: extended operators (`midicps`, `tanh_`, `clip2`, `dbamp`, `softclip`, `distort`), managed buffer allocation, and synchronous reply handling (`send_msg_sync`)
- **Documentation site** (mkdocs-material + mkdocstrings): auto-generated API reference from docstrings, organized by core modules and 28 UGen categories, with Getting Started guide and changelog. Served locally via `make docs-serve`, deployed to GitHub Pages via `make docs-deploy`. New `docs` dependency group in `pyproject.toml`, GitHub Actions workflow (`.github/workflows/docs.yml`) for auto-deploy on push to main
- **Comprehensive docstrings** across all core modules:
  - `enums.py`: all 6 enum classes (`CalculationRate`, `ParameterRate`, `BinaryOperator`, `UnaryOperator`, `DoneAction`, `EnvelopeShape`) with member descriptions and `from_expr()` methods
  - `synthdef.py`: `SynthDef`, `SynthDefBuilder`, `UGen`, `UGenOperable`, `UnaryOpUGen`, `BinaryOpUGen`, `Parameter`, `Control`, `SynthDefError`, `UGenSerializable`; 25 named binary methods with formulas (`ring1`--`ring4`, `clip2`, `fold2`, `wrap2`, `difsqr`, `sumsqr`, etc.); 8 pitch/amplitude conversion methods with examples (`midicps`, `cpsmidi`, `dbamp`, `ampdb`); waveshaping methods (`distort`, `softclip`)
  - `envelopes.py`: `Envelope` class with full Args section, all 5 factory methods (`adsr`, `asr`, `linen`, `percussive`, `triangle`), `EnvGen` with parameter descriptions
  - `osc.py`: `OscMessage`, `OscBundle` with public method docstrings (`to_datagram`, `from_datagram`, `to_list`), `find_free_port()`
  - `scsynth.py`: `Options` with commonly adjusted fields, `BootStatus`, `ServerCannotBoot`, `EmbeddedProcessProtocol.boot()` and `.quit()`
  - `compiler.py`: `compile_synthdefs()` with Args/Returns documenting the SCgf binary format
- **`AddAction` enum** (`enums.py`): `ADD_TO_HEAD`, `ADD_TO_TAIL`, `ADD_BEFORE`, `ADD_AFTER`, `REPLACE` -- replaces opaque raw ints in `Server.synth()`, `Server.group()`, and their managed variants. Raw int values still accepted for backwards compatibility
- **`ServerProtocol`** structural type (`synthdef.py`): `SynthDef.send()` and `SynthDef.play()` now accept any object satisfying `ServerProtocol` instead of `Any`, restoring type safety without circular imports

### Fixed

- **Gendy1/2/3 parameter wire order** (`gendyn.py`): all three Gendy UGens had incorrect parameter ordering and counts vs the C++ plugin (`GendynUGens.cpp`). Gendy1/2 had a single `frequency` where SC expects `min_frequency`/`max_frequency`, and had four distribution parameters (`amplitude_parameter_one/two`, `duration_parameter_one/two`) where SC expects two (`amplitude_parameter`, `duration_parameter`). Wire positions 2--10 were all wrong, causing silence or garbage output. Gendy3's parameter order was also incorrect (it has a different layout from Gendy1/2 in the C++ -- single `frequency`, no min/max). All three now match their `ZIN0()` indices exactly
- **Klank audio rate** (`ffsinosc.py`): `Klank.ar()` passed `calculation_rate=None` to `_new_expanded`, which resolved to `CalculationRate.SCALAR` -- the filter bank was computed once at init instead of processing audio samples per block. Changed to `CalculationRate.AUDIO`
- **`ParameterRate.from_expr("tr")`**: the `"tr"` token for trigger rate was missing from the string-to-enum mapping, causing `KeyError` when using `control(rate="tr")`. Added alongside `"ar"`, `"kr"`, `"ir"`
- `help(nanosynth)` crash: dynamically generated rate methods (`.ar`, `.kr`, `.ir`) created via `exec` in `_create_fn` had `__module__ = None`, causing `pydoc` to raise `TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'` when rendering help text. Now sets `__module__` from the owning class before applying decorators.
- **`__bool__` trap on `UGenOperable`**: `UGenOperable.__bool__` now raises `TypeError` instead of silently returning `True`. Catches the common footgun where `if sig > 0:` always takes the truthy branch because comparison operators return `UGenOperable` objects, not booleans
- **`Server.quit()` decoupled from protocol internals**: `Server.quit()` now delegates to `EmbeddedProcessProtocol.quit()` instead of reaching into the private `_shutdown()` method, properly setting the `QUITTING` state for clean shutdown callbacks
- **Thread-local builder guard centralized**: replaced three inconsistent `hasattr(_local, "_active_builders")` guard patterns in `SynthDefBuilder.__init__`, `__enter__`, and `UGen.__init__` with a single `_get_active_builders()` function
- **Topological sort descendant ordering**: `_initiate_topological_sort` had `key=lambda x: ugens.index(ugen)` which captured the loop variable, making the sort a no-op. Fixed to `key=lambda x: ugens.index(x)` to sort descendants by their position in the UGen list

## [0.1.2]

### Added

- **~80 new UGen classes** (290 -> 346 total), achieving full parity with supriya's UGen surface:
  - **Phase vocoder** (`pv.py`): `FFT`, `IFFT`, `PV_ChainUGen`, and 34 `PV_*` analysis/resynthesis UGens, plus `RunningSum`
  - **Machine listening** (`ml.py`): `BeatTrack`, `BeatTrack2`, `KeyTrack`, `Loudness`, `MFCC`, `Onsets`, `Pitch`, `SpecCentroid`, `SpecFlatness`, `SpecPcile`
  - **Stochastic synthesis** (`gendyn.py`): `Gendy1`, `Gendy2`, `Gendy3`
  - **Hilbert transforms** (`hilbert.py`): `FreqShift`, `Hilbert`, `HilbertFIR`
  - **Mouse/keyboard** (`mac.py`): `KeyState`, `MouseButton`, `MouseX`, `MouseY`
  - **Disk I/O** (`diskio.py`): `DiskIn`, `DiskOut`, `VDiskIn`
  - **Utility** (`basic.py`): `MulAdd`, `Sum3`, `Sum4`, `Mix` (signal mixer with Sum3/Sum4 tree optimization)
  - **Additions to existing modules**: `LocalBuf`, `ScopeOut2` (bufio); `Demand`, `Dwrand` (demand); `Poll`, `SendReply`, `SendPeakRMS` (triggers); `LocalIn` (inout); `Klank` (ffsinosc); `LinLin`, `Silence` (lines); `Changed` (filters); `CompanderD` (dynamics); `Splay` (panning)
- `Default` sentinel class in `synthdef.py` for parameters whose defaults are computed from other parameters at construction time (used by `FFT`, `Gendy1-3`, `ScopeOut2`)
- `PseudoUGen` base class for virtual UGens that compose other UGens (`Mix`, `Changed`, `CompanderD`, `LinLin`, `Silence`, `Splay`)
- `_postprocess_kwargs` hook on `UGen.__init__` for transforming parameters at construction time (dynamic channel counts, Default resolution, rate forcing)
- `GREATER_THAN` and `LESS_THAN` binary operators with corresponding `__gt__`/`__lt__` on `UGenOperable`
- Demo scripts: `14_spectral.py` (FFT/PV spectral processing), `15_gendy.py` (stochastic synthesis), `16_klank_splay.py` (resonant filter banks), `17_freqshift.py` (Bode frequency shifting)

### Fixed

- `LocalBuf` crash: `SynthDefBuilder.build()` now runs a `_cleanup_local_bufs` pass that automatically inserts a `MaxLocalBufs` UGen when `LocalBuf` instances are present in the graph (e.g. from `FFT`'s auto-allocated buffer). Without this, scsynth would crash with `LocalBuf tried to allocate too many local buffers`

## [0.1.1]

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
- `qa` CI job: runs ruff lint, ruff format check, mypy --strict, and pytest against the source tree on every push/PR
- Release workflow (`release.yml`): tag-triggered publish to PyPI via trusted publisher, `workflow_dispatch` for TestPyPI, auto-generated GitHub Release
- Docstrings on `SynthDefBuilder.build()`, `.add_parameter()`, and `.__getitem__()`
- Plugin loading validation: `_options_to_world_kwargs()` logs a warning when no UGen plugins path is found

### Fixed

- macOS CoreAudio teardown crash: registered a C-level `atexit` guard in `_scsynth.cpp` (after `World_New`) that calls `_exit(0)` before CoreAudio's static destructors run; removed `os._exit(0)` from all 11 demo scripts
- `WorldStrings` memory leak in `_scsynth.cpp`: capsule destructor now frees the heap-allocated strings object
- Windows CI build failure caused by Strawberry Perl's incompatible ccache crashing MSVC (`STATUS_ENTRYPOINT_NOT_FOUND`); disabled SC's ccache integration on Windows
- nanobind 2.11 compatibility: replaced capturing lambda in `_scsynth.cpp` capsule constructor with `WorldHandle` struct and non-capturing cleanup function
- Removed 11 `type: ignore[arg-type]` suppressions from `EnvGen` by widening `UGen.__init__`, `_new_single`, and `_new_expanded` kwargs to `UGenRecursiveInput | None`
- OSC decoder unbounded recursion: `_osc.cpp` blob/bundle recursive parsing now enforces a maximum nesting depth of 16 levels; beyond the limit, blobs are returned as raw bytes
- OSC decoder aggregate bounds checking: `decode_message_clean` pre-validates that the payload has enough bytes for all type tags before entering the decode loop
- `world_send_packet` `const_cast` removal: OSC packet data is now copied into a `std::vector<char>` before passing to `World_SendPacket`, eliminating undefined behavior from casting away const on Python bytes
- `scsynth_print_func` buffer overflow: replaced fixed 4096-byte stack buffer with a two-pass approach that dynamically allocates when the formatted message exceeds the stack buffer

### Changed

- Protected `EmbeddedProcessProtocol._active_world` with `threading.Lock` to prevent race conditions on concurrent `boot()` calls
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
