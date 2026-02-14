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

- [x] **`qa` CI job.** Runs lint, format check, typecheck, and pytest against the source tree on every push/PR.
- [x] **Python 3.14 classifier.** Both `CIBW_BUILD` and `pyproject.toml` classifiers include 3.14.
- [ ] **Source-tree test matrix.** No CI job runs `make test` against the source tree across Python versions (only via cibuildwheel against built wheels).
- [x] **Release workflow.** Tag-triggered publish to PyPI via trusted publisher (`gh-action-pypi-publish`), with `workflow_dispatch` for TestPyPI. Creates GitHub Release with auto-generated notes.

---

## C++ Safety

- [x] **OSC decoder: unbounded recursion.** `_osc.cpp` blob parsing recursively tries to parse as bundle/message with no depth limit. Enforce a reasonable limit (e.g., 16 levels).
- [x] **OSC decoder: aggregate bounds checking.** Type tag loop can advance offset past buffer if many tags but undersized payload. Pre-validate aggregate data size.
- [x] **Remove `const_cast` in `world_send_packet`.** `const_cast<char*>(data.c_str())` is safe today but fragile. A defensive copy into `std::vector<char>` would be safer.
- [x] **C++ print buffer overflow.** `scsynth_print_func` uses a fixed 4096-byte stack buffer. SC can produce longer messages during verbose plugin loading. Consider dynamic allocation.

---

## Documentation

- [ ] **Auto-generated API reference docs.** No Sphinx/mkdocs/pdoc setup. For 290+ UGens, auto-generated docs would be valuable.
- [x] **Docstrings on `SynthDefBuilder` methods.** `build()`, `add_parameter()`, `__getitem__()` now have docstrings.

---

## Concurrency

- [x] **Lock `_active_world` class variable.** Protected with `threading.Lock`; all reads/writes go through the lock.

---

## Misc

- [x] **`SynthDefBuilder.__getitem__` return type.** Won't fix -- the `OutputProxy | Parameter` union is correct and both types satisfy `UGenRecursiveInput`/`UGenOperable`, so arithmetic and UGen constructor usage work without type errors. Narrowing to `UGenOperable` would lose type information needed by compiler internals.
- [x] **Plugin loading validation.** Logs a warning when no UGen plugins path is found.
