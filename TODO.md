# TODO

Remaining improvement tasks, grouped by category.

---

## Architecture / Usability

- [x] **High-level `Server` class.** Wraps boot-send-quit lifecycle, node ID allocation, SynthDef dispatch, and common OSC commands (`synth`, `group`, `free`, `set`).
- [x] **`SynthDef.send()` / `SynthDef.play()` convenience methods.** Send a compiled SynthDef to a running server, or send and create a synth in one call.

- [x] **SynthDef graph pretty-printer.** `SynthDef.dump_ugens()` prints the UGen graph (like SC's `SynthDef.dumpUGens`), showing UGen types, rates, inputs, operator names, and multi-output counts.

- [ ] **Async engine protocol.** An `asyncio`-based alternative to the thread-based `EmbeddedProcessProtocol`. Could coexist with the current implementation. Deferred until bidirectional OSC is implemented.

- [x] **`Envelope.compile()` dedicated serialization path.** Produces `tuple[float, ...]` directly, bypassing UGenVector/ConstantProxy. `serialize()` retained for UGen graph wiring.

---

## Code Generation

- [ ] **Replace `exec`-based code generation with `__init_subclass__`.** The `_create_fn` / `_add_init` / `_add_rate_fn` machinery uses string-template `exec` (same approach as `dataclasses`). A metaclass or `__init_subclass__` hook would make generated methods debuggable and introspectable. Tradeoff: more metaclass complexity.

---

## Test Coverage Gaps

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
