# TODO

Remaining improvement tasks, grouped by category and ordered by priority within each section.

---

## CI / Build

- [ ] **Performance regression benchmarks.** No tracking of graph compilation speed or OSC encode/decode throughput. A simple `pytest-benchmark` suite for `SynthDefBuilder.build()` on a reference graph would catch regressions early. Priority: **low**, effort: **low**.

---

## Architecture

- [ ] **C/C++ SynthDef graph construction library.** A shared library exposing a C API for the SynthDef frontend -- multichannel expansion, rate inference, constant folding -- that any language can FFI into. This is the part worth sharing across languages (Python, Rust, JS/WASM, DAW plugins). Not an IR compiler: the backend (topological sort, constant deduplication, SCgf binary encoding) is trivial (~300 lines); the frontend is where the complexity lives (~1500 lines of non-trivial logic in the Python implementation). Only worth pursuing if there's a concrete non-Python consumer that needs SynthDef compilation without a Python runtime. Priority: **low**, effort: **high**.

- [ ] **Async engine protocol.** An `asyncio`-based alternative to the thread-based `EmbeddedProcessProtocol`. Would enable `await server.synth(...)` and integrate cleanly with async web frameworks. Priority: **low**, effort: **medium**.

- [ ] **Lazy / deferred graph compilation.** `SynthDefBuilder.build()` eagerly deep-copies, sorts, optimizes, and compiles. A lazy mode compiling only on first `send()` / `compile()` could benefit live-coding scenarios. Priority: **low**, effort: **low**.

---

## Code Generation

- [ ] **Replace `exec`-based code generation with `__init_subclass__`.** The `_create_fn` / `_add_init` / `_add_rate_fn` machinery uses string-template `exec` (same approach as `dataclasses`). A closure-based approach would make generated methods debuggable and introspectable. Tradeoff: lose nice `inspect.signature()` (recoverable with `__signature__` overrides). Priority: **low**, effort: **medium**.

---

## Feature Gaps (relative to sclang)

- [ ] **Scope / metering** (`Stethoscope`, `ServerMeter`). Useful feedback but requires a UI story (matplotlib? terminal?). Priority: **low**, effort: **medium**.

- [ ] **SynthDef variants**. Niche even in SC, rarely used. Priority: **low**, effort: **low**.
