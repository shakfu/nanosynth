# TODO

Remaining improvement tasks, grouped by category and ordered by priority within each section.

---

## Critical

## High

### Correctness & API Gaps

- [x] **UGen metadata has no independent reference.** Steps 1-3 of `docs/dev/ugen-metadata-audit.md` done 2026-10-05: `tests/test_ugen_plugin_scan.py` and `tests/test_ugen_reference.py` check all UGens against the plugin C++ and sclang 3.14.1. They found errors in 34 more UGens, all fixed in 0.4.0 (see CHANGELOG). Step 4 is tracked under Medium. Priority: **high**, effort: **medium**.

### Packaging / CI

- [ ] **Tests are biased toward mocks; realtime coverage is opt-in.** Three crash or data-loss bugs (`DiskOut` outputs, recording silence and finalization, `MidiIn.close()` deadlock) passed ~1200 tests, because recording and MIDI teardown were only exercised against mocks. `tests/test_realtime_smoke.py` runs only with `NANOSYNTH_TEST_REALTIME` set, and CI runs it for scsynth on Linux alone. Every engine-touching feature should have at least one test against a live engine or an NRT render, and the realtime job should run on every push. Priority: **high**, effort: **medium**.

## Medium

### Correctness & API Gaps

- [ ] **Supernova reboot/teardown crash; print redirection is a no-op.** Booting supernova a second time in one process segfaults in `_run_loop` (`test_reboot_in_same_process[supernova]`), so the realtime file must run one test per process for that engine and CI does not run supernova realtime at all (see `build.yml`). Separately, `_supernova.cpp` defines a `SetPrintFunc` shim that stores the function in a static nothing reads, so `set_print_func` has no effect on supernova output. Priority: **medium**, effort: **medium**.

- [ ] **UGen overruns with computed indices are unchecked.** The plugin scan sees only literal `IN(n)`/`OUT(n)`; sclang checks only the wire contract. Step 4 of `docs/dev/ugen-metadata-audit.md`: build the plugins with AddressSanitizer and NRT-render every UGen with default inputs. Priority: **medium**, effort: **medium**.

- [ ] **The sclang comparison cannot see swapped inputs with equal defaults.** `Dbufwr` sent `[value, buffer, phase, loop]` against the plugin's `[buffer, phase, value, loop]` and passed, because the first three defaults are all 0. Perturb one argument at a time in `scripts/sclang_reference.scd`, record which input slot changes, and compare the slot-to-argument map per UGen. Needs an sclang-to-nanosynth argument name table. Priority: **medium**, effort: **medium**.

- [ ] **`Dwrand` rejects UGens in `sequence` and `weights`.** `Dwrand.dr` calls `float()` on every element, so `Dwrand.dr(sequence=[Dseq.dr(...), 1])` raises. sclang accepts any input there. Priority: **medium**, effort: **low**.

### Packaging / CI

- [ ] **macOS and Windows are tested only inside wheel builds.** `qa`, `test-source` and `test-realtime` run on Linux only; macOS/Windows run the suite once per wheel under cibuildwheel, with no realtime engine boot and no MIDI ports. Timing-sensitive code (`MidiClockOut` tick jitter under Windows' ~15.6 ms wait granularity, `Clock` scheduling) is unmeasured there. Add a non-wheel test job per OS, including a realtime boot where a virtual audio device is available. Overlaps the mock-bias item under High. Priority: **medium**, effort: **medium**.

### Feature Gaps (engine & composition)

## Low

### Correctness & API Gaps

- [ ] **Single-World constraint is implicit.** A process-global live World is enforced via a class-level `_active_world` flag plus process-global print/reply callbacks in `_scsynth.cpp`. It leaks into behaviour: quitting one server clears the print callback process-wide, and TCP transport and `maximum_logins > 1` are wired in C++ but unreachable from Python. Document the singleton constraint explicitly; longer term, key the callbacks by World handle. Note (2026-10-04): the constraint is still absent from the `Server` and `Options` docstrings and from `docs/`, and `set_print_func`/`set_reply_func` remain process-global. Priority: **low**, effort: **medium**.

### Packaging / CI

- [ ] **cibuildwheel runs the full suite in every wheel.** `CIBW_TEST_COMMAND: pytest {project}/tests/` across 5 Pythons x 3 OSes means 15 complete runs, including the slow NRT tests. Add a smoke marker for the in-wheel run. Priority: **low**, effort: **low**. Measured 2026-10-04: the suite takes ~5 s of test time and the NRT tests ~0.13 s, so a smoke subset saves ~1 min across 15 wheels while dropping Windows/macOS coverage (wheel builds are the only CI on those OSes). Not worth doing unless the suite grows.

### Architecture

- [ ] **(c) Rust core with multi-target bindings.** Only if a consumer genuinely needs *runtime* SynthDef construction in a compiled environment. A Rust arena with algebraic UGen types, driven by the spec from (b), exposed via `cbindgen` (C ABI), `wasm-bindgen` (JS/WASM), and PyO3 -- with PyO3 replacing the Python frontend so there stays exactly one implementation rather than a parallel port. This is a from-scratch reimplementation; the effort is dominated by porting the frontend and its UGen metadata, not the trivial (~150-line) SCgf backend. Priority: **low**, effort: **high**.

- [ ] **Async engine protocol.** An `asyncio`-based alternative to the thread-based `EmbeddedProcessProtocol`. Would enable `await server.synth(...)` and integrate cleanly with async web frameworks. Priority: **low**, effort: **medium**.

- [ ] **Lazy / deferred graph compilation.** `SynthDefBuilder.build()` eagerly deep-copies, sorts, optimizes, and compiles. A lazy mode compiling only on first `send()` / `compile()` could benefit live-coding scenarios. Priority: **low**, effort: **low**.

### Code Generation

- [ ] **Replace `exec`-based code generation with `__init_subclass__`.** The `_create_fn` / `_add_init` / `_add_rate_fn` machinery uses string-template `exec` (same approach as `dataclasses`). A closure-based approach would make generated methods debuggable and introspectable. Tradeoff: lose nice `inspect.signature()` (recoverable with `__signature__` overrides). Priority: **low**, effort: **medium**.

### Feature Gaps (relative to sclang)

- [ ] **Scope / metering** (`Stethoscope`, `ServerMeter`). Useful feedback but requires a UI story (matplotlib? terminal?). Priority: **low**, effort: **medium**.

- [ ] **SynthDef variants**. Niche even in SC, rarely used. Priority: **low**, effort: **low**.
