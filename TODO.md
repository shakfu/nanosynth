# TODO

Remaining improvement tasks, grouped by category. Priority and effort estimates included where known.

---

## Quick Fixes

- [ ] **`AddAction` enum.** The `action` parameter on `synth()` and `group()` accepts raw ints (0-4). Add an `AddAction` IntEnum (`addToHead`, `addToTail`, `addBefore`, `addAfter`, `addReplace`) and accept it in the API. Keep raw int support for backwards compat. Priority: **low**, effort: **trivial**.

- [ ] **`__bool__` trap on `UGenOperable`.** `UGenOperable.__gt__` and `__lt__` return `UGenOperable` objects (always truthy), so `if sig > 0:` silently takes the truthy branch. Add `__bool__` that raises `TypeError("Cannot use UGen expressions in boolean context; use .gt() / .lt() for signal-rate comparison")`. Priority: **medium**, effort: **trivial**.

- [ ] **`Server.quit()` calls `_shutdown()` directly.** `Server.quit()` reaches into `self._protocol._shutdown()`, coupling it to `EmbeddedProcessProtocol` internals. `EmbeddedProcessProtocol.quit()` should handle the full shutdown sequence. Priority: **low**, effort: **trivial**.

- [ ] **Centralize thread-local guard.** `synthdef.py` has inconsistent `hasattr(_local, "_active_builders")` guard patterns across `SynthDefBuilder.__init__`, `__enter__`, and `UGen.__init__`. Extract into a single `_get_active_builders() -> list[SynthDefBuilder]` function. Priority: **low**, effort: **trivial**.

- [ ] **Fix `_initiate_topological_sort` key lambda.** The `key=lambda x: ugens.index(ugen)` captures the loop variable `ugen`, making the sort a no-op (all elements get the same key). Should be `key=lambda x: ugens.index(x)` if the intent is to sort descendants by position. Priority: **medium**, effort: **trivial**.

- [ ] **`ServerProtocol` typing.** `SynthDef.send()` and `play()` type their `server` parameter as `Any` to avoid circular imports. A `Protocol` class would restore type safety without import issues. Priority: **low**, effort: **trivial**.

---

## API Design

- [ ] **`Synth` / `Group` proxy objects.** `Server.synth()` returns a raw node ID int. Return a lightweight `Synth` proxy with `.set(**params)`, `.free()`, and context manager support for a more Pythonic API. Same for `Group`. Priority: **medium**, effort: **low**.

- [ ] **`SynthDefBuilder` kwarg API for parameter metadata.** Currently requires verbose `Parameter(value=440.0, rate=ParameterRate.AUDIO, lag=0.1)` for non-default params. Consider a `param()` helper or tuple syntax for the builder context. Note: `param()` already exists for the `@ugen` decorator -- naming collision needs resolution. Priority: **medium**, effort: **low**.

- [ ] **Flat namespace pollution.** `__init__.py` does `from .ugens import *`, exporting 340+ names. Consider exporting only the most common UGens at the top level, keeping the rest in `nanosynth.ugens`. Counter-argument: flat namespace is convenient for REPL/notebook use. Priority: **low**, effort: **trivial**.

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
