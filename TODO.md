# TODO

Remaining improvement tasks, grouped by category.

---

## Architecture / Usability

- [ ] **High-level `Server` / `Engine` class.** Wrap the full boot-send-quit lifecycle so users don't need to understand OSC encoding, world lifecycle, or `_scsynth` imports. Subsumes `EmbeddedProcessProtocol` + `_options_to_world_kwargs`.
- [ ] **`SynthDef.send()` / `SynthDef.load()` convenience methods.** After compiling a SynthDef, users must manually encode a `/d_recv` OSC message. A convenience method to send to a running engine would be natural.

- [ ] **SynthDef graph pretty-printer.** `synthdef.dump()` or `synthdef.graph()` to print the UGen graph (like SC's `SynthDef.dumpUGens`). Data is already in `synthdef._ugens`.

- [ ] **Async engine protocol.** An `asyncio`-based alternative to the thread-based `EmbeddedProcessProtocol`. Could coexist with the current implementation.

- [ ] **`Envelope` as a first-class serializable type.** Give `Envelope` a dedicated serialization path rather than the generic `UGenSerializable` interface.

---

## Code Generation

- [ ] **Replace `exec`-based code generation with `__init_subclass__`.** The `_create_fn` / `_add_init` / `_add_rate_fn` machinery uses string-template `exec` (same approach as `dataclasses`). A metaclass or `__init_subclass__` hook would make generated methods debuggable and introspectable. Tradeoff: more metaclass complexity.

---

## Test Coverage Gaps

- [ ] **`SynthDefBuilder` scope errors.** No tests verify that using a UGen from one builder scope inside another raises `SynthDefError`.
- [ ] **Graph optimization in isolation.** `_optimize` and `_eliminate` are only tested indirectly via `build(optimize=True)`.
- [ ] **Envelope factory methods.** No tests for `Envelope.linen`, `Envelope.triangle`, `Envelope.asr`. Only `adsr` and `percussive` are exercised.
- [ ] **Multi-channel expansion.** No tests for UGens with `is_multichannel=True` (e.g., `In`, `PanAz`, `DecodeB2`).
- [ ] **`compile_synthdefs` with multiple SynthDefs.** `compile_synthdefs` accepts `*synthdefs` but tests only ever compile a single SynthDef.
- [ ] **Demand-rate UGens.** No tests for demand-rate (`dr`) calculation rate UGens (e.g., `Dseq`, `Duty`).
- [ ] **`@synthdef` decorator coverage.** Limited test coverage compared to the `SynthDefBuilder` context manager.
- [ ] **Integration tests.** No tests verify that a compiled SynthDef produces audio when loaded into the embedded engine. Audio hardware in CI is tricky, but worth noting.

---

## CI / Build

- [ ] **Add `make qa` CI job.** CI only runs `pytest` via cibuildwheel. A separate job running `make qa` would catch lint/type regressions.
- [ ] **Python 3.14 classifier mismatch.** `CIBW_BUILD` includes 3.14 but `pyproject.toml` classifiers list up to 3.13. Reconcile.
- [ ] **Source-tree test matrix.** No CI job runs `make test` against the source tree across Python versions (only via cibuildwheel against built wheels).
- [ ] **Release workflow.** No automation for publishing to PyPI. Add a tag-triggered or `workflow_dispatch` job.

---

## C++ Safety

- [ ] **OSC decoder: unbounded recursion.** `_osc.cpp` blob parsing recursively tries to parse as bundle/message with no depth limit. Enforce a reasonable limit (e.g., 16 levels).
- [ ] **OSC decoder: aggregate bounds checking.** Type tag loop can advance offset past buffer if many tags but undersized payload. Pre-validate aggregate data size.
- [ ] **Remove `const_cast` in `world_send_packet`.** `const_cast<char*>(data.c_str())` is safe today but fragile. A defensive copy into `std::vector<char>` would be safer.
- [ ] **C++ print buffer overflow.** `scsynth_print_func` uses a fixed 4096-byte stack buffer. SC can produce longer messages during verbose plugin loading. Consider dynamic allocation.

---

## Documentation

- [ ] **Auto-generated API reference docs.** No Sphinx/mkdocs/pdoc setup. For 290+ UGens, auto-generated docs would be valuable.
- [ ] **Docstrings on `SynthDefBuilder` methods.** `build()`, `add_parameter()`, `__getitem__()` have no docstrings.

---

## Concurrency

- [ ] **Lock `_active_world` class variable.** `EmbeddedProcessProtocol._active_world` is unprotected global mutable state. Concurrent `boot()` calls could race.

---

## Misc

- [ ] **`SynthDefBuilder.__getitem__` return type.** Returns `OutputProxy | Parameter` depending on parameter shape. Dual return type is inconvenient for type checkers and users.
- [ ] **Plugin loading validation.** If `find_ugen_plugins_path()` returns `None`, the engine boots with no UGen plugins, producing silent failure. Validate and warn.
