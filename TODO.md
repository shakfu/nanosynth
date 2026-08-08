# TODO

Remaining improvement tasks, grouped by category and ordered by priority within each section.

The sections from **Correctness & API Gaps** onward were migrated here from `REVIEW.md` (a full architecture/code review of 0.1.6) when that file was retired; everything it recorded as done or resolved was dropped, and only open items were carried over. `REVIEW.md` was gitignored and untracked, so the only copy in history is the pre-`13525fb` one, which predates the fixes tracked against it -- treat this file as the sole live record of that review's open items.

---

## Correctness & API Gaps

Ordered by likelihood of biting a user.

- [ ] **`Score.to_binary()` emits an unguarded score.** The `/g_freeAll` + `/c_set` safety bundle that `render()` documents as necessary to avoid engine crashes is appended inside `render()` (`score.py:126-127`), not in the public `to_binary()`. Anyone writing a score file themselves gets the unguarded version. Fold the guard into `to_binary()` and have `render()` call it. Priority: **high**, effort: **low**.

- [ ] **Terminal `/g_freeAll` truncates the final event.** It is appended at exactly `end_time` (`score.py:126`), so the last event can be cut off. Use `end_time + epsilon`. Priority: **medium**, effort: **low**.

- [ ] **`Score.add_synth` ergonomics.** Takes raw ints -- no node-id allocation, no `AddAction` -- unlike `Server.synth`. Also `preferred_hardware_buffer_size=8192` is hard-coded at `score.py:167`, ignoring the passed `options`. Priority: **medium**, effort: **low**.

- [ ] **MIDI handler lists are mutated without a lock.** `midi.py:203-241` appends to and removes from the handler lists from the user thread while the RtMidi thread iterates them. (Distinct from the GIL/mutex ordering bug fixed in `_midi.cpp` -- this is the Python side.) Priority: **medium**, effort: **low**.

- [ ] **MIDI C++ handler exceptions vanish.** `_midi.cpp:69` swallows them with `catch (...)`, so a broken handler fails invisibly during live performance. Route to `PyErr_WriteUnraisable`. Priority: **medium**, effort: **low**.

- [ ] **`record()` has no `is_running` guard** and remains single-stream (one recording at a time). The sleep-based sequencing it used to rely on is already replaced by `sync()`. Priority: **low**, effort: **low**.

- [ ] **`Options.maximum_logins` default disagrees with the engine.** Python defaults to 1 (`scsynth.py:60`), the C++ default is 64. Harmless but confusing; align them. Priority: **low**, effort: **low**.

- [ ] **`set_print_func(None)` installs a no-op rather than restoring the default.** Output is silently dropped instead of reverting to scsynth's own printer. Priority: **low**, effort: **low**.

- [ ] **Single-World constraint is implicit.** A process-global live World is enforced via a class-level `_active_world` flag plus process-global print/reply callbacks in `_scsynth.cpp`. It leaks into behaviour: quitting one server clears the print callback process-wide, and TCP transport and `maximum_logins > 1` are wired in C++ but unreachable from Python. Document the singleton constraint explicitly; longer term, key the callbacks by World handle. Priority: **low**, effort: **medium**.

---

## Packaging / CI

- [ ] **Version is hard-coded in two places.** `pyproject.toml:3` and `src/nanosynth/__init__.py:3` both carry the version with nothing asserting they match, so they will drift. Single-source it via scikit-build-core metadata and add a drift test. Priority: **high**, effort: **low**.

- [ ] **No `concurrency: cancel-in-progress` in `build.yml`.** Rapid pushes queue redundant, expensive wheel builds. Priority: **medium**, effort: **low**.

- [ ] **cibuildwheel runs the full suite in every wheel.** `CIBW_TEST_COMMAND: pytest {project}/tests/` across 5 Pythons x 3 OSes means 15 complete runs, including the slow NRT tests. Add a smoke marker for the in-wheel run. Priority: **low**, effort: **low**.

---

## Feature Gaps (engine & composition)

- [ ] **MIDI output and clock.** `MidiOut`, plus MIDI clock/transport send and receive (slaving a `Clock` to incoming clock). Also missing: Program Change and Aftertouch message types. Priority: **medium**, effort: **medium**.

- [ ] **CLI beyond `info` and `compile`.** `nanosynth render score.py -o out.wav`, `nanosynth midi-ports`, a boot self-test, and a top-level `--version`. Priority: **medium**, effort: **low**.

- [ ] **Buffer introspection and generators.** `/b_query`, and `/b_gen` wavetable helpers (`sine1`/`sine2`/`sine3`, `cheby`). The direct numpy buffer path already covers bulk data exchange; these cover the rest. Also missing: control-bus `get()`. Priority: **medium**, effort: **low**.

- [ ] **Pattern gaps.** `Pbindef` (per-key updates to a running `Pbind`), `PmonoArtic`, array-valued event keys for chords (one event expanding to several synths), and `Score.from_pattern(pattern, duration)` -- the realtime pattern engine and NRT scoring currently share no code path. These are the deliberate exclusions listed under "Not yet implemented" in `docs/patterns.md`. Priority: **medium**, effort: **medium**.

---

## Architecture

### Cross-language SynthDef compilation

These supersede the earlier "C/C++ SynthDef graph construction library" idea. All are gated on a concrete non-Python consumer, and the first question for any such consumer is whether it can use pre-compiled `.scsyndef` artifacts (task a) rather than needing the frontend at all. Do not hand-write a C frontend or maintain a second parallel implementation of the frontend logic (multichannel expansion / rate inference / constant folding) -- that reintroduces the dual-implementation drift the OSC codec already suffered. Ordered cheapest-first.

- [x] **(a) Precompiled `.scsyndef` artifact workflow.** `docs/deployment.md` documents the build-time compile step (`nanosynth compile`), artifact layout (name-in-binary vs filename, per-def vs bundle), and loading via `/d_load` / `/d_loadDir` / `/d_recv` from nanosynth, sclang, and any OSC client -- no new engine code.

- [x] **(b) Language-neutral UGen spec + SCgf format doc.** `spec/nanosynth-ugens.json` (generated by `scripts/generate_ugen_spec.py`, kept in sync by `tests/test_ugen_spec.py`) is the shared UGen metadata table (341 UGens: names, rates, parameter defaults, `unexpanded`/pure/output/width-first flags) plus the operator/rate/done-action enum tables. `docs/scgf-format.md` specifies the SCgf version-2 byte layout and the spec schema. Golden SCgf fixtures remain the byte-level cross-implementation contract.

- [ ] **(c) Rust core with multi-target bindings.** Only if a consumer genuinely needs *runtime* SynthDef construction in a compiled environment. A Rust arena with algebraic UGen types, driven by the spec from (b), exposed via `cbindgen` (C ABI), `wasm-bindgen` (JS/WASM), and PyO3 -- with PyO3 replacing the Python frontend so there stays exactly one implementation rather than a parallel port. This is a from-scratch reimplementation; the effort is dominated by porting the frontend and its UGen metadata, not the trivial (~150-line) SCgf backend. Priority: **low**, effort: **high**.

- [ ] **Async engine protocol.** An `asyncio`-based alternative to the thread-based `EmbeddedProcessProtocol`. Would enable `await server.synth(...)` and integrate cleanly with async web frameworks. Priority: **low**, effort: **medium**.

- [ ] **Lazy / deferred graph compilation.** `SynthDefBuilder.build()` eagerly deep-copies, sorts, optimizes, and compiles. A lazy mode compiling only on first `send()` / `compile()` could benefit live-coding scenarios. Priority: **low**, effort: **low**.

---

## Code Generation

- [ ] **Replace `exec`-based code generation with `__init_subclass__`.** The `_create_fn` / `_add_init` / `_add_rate_fn` machinery uses string-template `exec` (same approach as `dataclasses`). A closure-based approach would make generated methods debuggable and introspectable. Tradeoff: lose nice `inspect.signature()` (recoverable with `__signature__` overrides). Priority: **low**, effort: **medium**.

---

## Feature Gaps (relative to sclang)

- [ ] **Scope / metering** (`Stethoscope`, `ServerMeter`). Useful feedback but requires a UI story (matplotlib? terminal?). Priority: **low**, effort: **medium**.

- [ ] **SynthDef variants**. Niche even in SC, rarely used. Priority: **low**, effort: **low**.
