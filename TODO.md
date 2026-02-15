# TODO

Remaining improvement tasks, grouped by category. Priority and effort estimates included where known.

---

## Quick Fixes

- [x] **`AddAction` enum.** `AddAction` IntEnum added to `enums.py` with `ADD_TO_HEAD`, `ADD_TO_TAIL`, `ADD_BEFORE`, `ADD_AFTER`, `REPLACE`. Accepted by `Server.synth()`, `Server.group()`, and their managed variants. Raw int still supported.

- [x] **`__bool__` trap on `UGenOperable`.** `UGenOperable.__bool__` raises `TypeError` to catch the `if sig > 0:` footgun.

- [x] **`Server.quit()` decoupled from `_shutdown()`.** Now delegates to `EmbeddedProcessProtocol.quit()` instead of calling the private `_shutdown()` method directly.

- [x] **Centralized thread-local guard.** `_get_active_builders()` function replaces three inconsistent `hasattr` guard patterns.

- [x] **Fixed `_initiate_topological_sort` key lambda.** `key=lambda x: ugens.index(x)` instead of the captured loop variable.

- [x] **`ServerProtocol` typing.** `SynthDef.send()` and `play()` accept `ServerProtocol` instead of `Any`.

---

## API Design

- [x] **`Synth` / `Group` proxy objects.** `Server.synth()` and `Server.group()` return `Synth` / `Group` proxies with `.set()`, `.free()`, context manager support, and int-compatibility via `__int__()`, `__index__()`, `__eq__()`, `__hash__()`.

- [x] **`SynthDefBuilder` kwarg API for parameter metadata.** Added `control(value, rate, lag)` function and tuple syntax `(rate, value)` / `(rate, value, lag)` for `SynthDefBuilder` kwargs. Named `control()` to avoid collision with `param()` (used by `@ugen`).

- [x] **Flat namespace pollution.** `__all__` trimmed to ~60 names (core API + 29 common UGens). Full UGen set available via `from nanosynth.ugens import *`.

---

## Architecture

- [x] **High-level `Server` class.** Wraps boot-send-quit lifecycle, node ID allocation, SynthDef dispatch, and common OSC commands (`synth`, `group`, `free`, `set`).
- [x] **`SynthDef.send()` / `SynthDef.play()` convenience methods.** Send a compiled SynthDef to a running server, or send and create a synth in one call.
- [x] **SynthDef graph pretty-printer.** `SynthDef.dump_ugens()` prints the UGen graph (like SC's `SynthDef.dumpUGens`), showing UGen types, rates, inputs, operator names, and multi-output counts.
- [x] **`Envelope.compile()` dedicated serialization path.** Produces `tuple[float, ...]` directly, bypassing UGenVector/ConstantProxy. `serialize()` retained for UGen graph wiring.

- [ ] **Async engine protocol.** An `asyncio`-based alternative to the thread-based `EmbeddedProcessProtocol`. Could coexist with the current implementation.

- [ ] **NRT rendering.** SuperCollider supports offline rendering via `World_NonRealTimeSynthesis`. Unlocks deterministic output, batch processing, and CI testing without audio hardware. Needs a C++ binding and a Python `Score` / `nrt_render()` API. Priority: **high**, effort: **medium-high**.

- [ ] **SynthDef graph introspection.** `dump_ugens()` produces strings, but there's no structured API to walk the UGen graph, query input sources, compute signal flow paths, or export to DOT/Graphviz. Add `SynthDef.graph()` returning a DAG structure and `to_dot()` for visualization. Priority: **medium**, effort: **low-medium**.

- [ ] **Lazy / deferred graph compilation.** `SynthDefBuilder.build()` eagerly deep-copies, sorts, optimizes, and compiles. A lazy mode compiling only on first `send()` / `compile()` could benefit live-coding scenarios. Priority: **low**, effort: **low**.

---

## Code Generation

- [ ] **Replace `exec`-based code generation with `__init_subclass__`.** The `_create_fn` / `_add_init` / `_add_rate_fn` machinery uses string-template `exec` (same approach as `dataclasses`). A closure-based approach would make generated methods debuggable and introspectable. Tradeoff: lose nice `inspect.signature()` (recoverable with `__signature__` overrides). Priority: **low**, effort: **medium**.

---

## Code Quality

- [ ] **Split `synthdef.py` (~2150 lines).** Contains type aliases, `@ugen` decorator system, `UGenOperable`, proxy classes, `UGen`, operator UGens, parameter/control classes, `SynthDef`, `SynthDefBuilder`, and `@synthdef` decorator. Could split into `types.py`, `ugen.py`, `operators.py`, `parameters.py`, and `synthdef.py`. Counter-argument: circular imports are likely; monolithic structure avoids that. Priority: **low**, effort: **medium**.

---

## Test Coverage

- [ ] **Integration tests.** No tests verify that a compiled SynthDef produces audio when loaded into the embedded engine.

- [ ] **Negative / adversarial compiler tests.** Test graphs with cycles, extremely deep UGen chains, thousands of UGens, invalid SCgf bytes, empty/long/special-character UGen names. Priority: **medium**, effort: **low**.

- [ ] **Concurrency tests.** `SynthDefBuilder` uses thread-local storage and UUID-based scope isolation. No tests verify two threads can build SynthDefs concurrently without interference. Priority: **medium**, effort: **low**.

- [ ] **Property-based tests (hypothesis).** Algebraic properties: `sig + 0 == sig`, `sig * 1 == sig`, `compile(a + b)` deterministic, multichannel expansion correctness, topological sort determinism. Priority: **low**, effort: **medium**.

- [ ] **Source-tree test matrix.** No CI job runs `make test` against the source tree across Python versions (only via cibuildwheel against built wheels).

---

## Documentation

- [x] **Auto-generated API reference docs.** mkdocs-material + mkdocstrings site with 6 core module pages, 28 UGen category pages, Getting Started guide, and changelog.
- [x] **Docstrings on `SynthDefBuilder` methods.** `build()`, `add_parameter()`, `__getitem__()` now have docstrings.

- [ ] **"Concepts" documentation.** Non-obvious concepts that need explanation: multichannel expansion, calculation rates (SCALAR/CONTROL/AUDIO/DEMAND), the scope system, parameter rate system, `unexpanded` flag, `is_width_first`, optimization pass, and the `Default` sentinel. Priority: **medium**, effort: **medium**.

---

## CI / Build

- [x] **`qa` CI job.** Runs lint, format check, typecheck, and pytest on every push/PR.
- [x] **Python 3.14 classifier.** Both `CIBW_BUILD` and `pyproject.toml` classifiers include 3.14.
- [x] **Release workflow.** Tag-triggered publish to PyPI via trusted publisher.

---

## C++ Safety

- [x] **OSC decoder: unbounded recursion.** Depth limit of 16 levels enforced.
- [x] **OSC decoder: aggregate bounds checking.** Pre-validates aggregate data size.
- [x] **Remove `const_cast` in `world_send_packet`.** Defensive copy into `std::vector<char>`.
- [x] **C++ print buffer overflow.** Dynamic allocation for long messages.

---

## Concurrency

- [x] **Lock `_active_world` class variable.** Protected with `threading.Lock`.

---

## Feature Gaps (relative to sclang)

Not necessarily all worth implementing, but represents the gap between "compile SynthDefs" and "replace sclang for synthesis work":

- [ ] Bus allocation (`Bus.audio`, `Bus.control`)
- [ ] ParGroup support (groups work, no ParGroup)
- [ ] Patterns / sequencing (`Pbind`, `Pseq`, `Prand` -- large design space, may be a separate package)
- [ ] MIDI input (`MIDIFunc`, `MIDIIn`)
- [ ] Recording (`Server.record`)
- [ ] Scope / metering (`Stethoscope`, `ServerMeter`)
- [ ] SynthDef variants
- [ ] Node proxies / live coding (`NodeProxy`, `Ndef`)

---

## Misc

- [x] **`SynthDefBuilder.__getitem__` return type.** Won't fix -- the `OutputProxy | Parameter` union is correct.
- [x] **Plugin loading validation.** Logs a warning when no UGen plugins path is found.
