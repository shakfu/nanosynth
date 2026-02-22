# TODO

Remaining improvement tasks, grouped by category and ordered by priority within each section.

---

## Test Coverage

- [x] **Integration tests.** 19 tests in `test_integration.py` verify the full pipeline (SynthDefBuilder -> SynthDef -> SCgf binary -> engine load -> audio synthesis -> WAV output) via NRT rendering. Covers: sine wave synthesis (non-silence, amplitude scaling, frequency differentiation), parameter control (frequency, amplitude), diverse UGens (WhiteNoise, Saw, LPF, RLPF, Pan2), envelopes (percussive decay), Mix, stereo panning, @synthdef decorator, complex graphs (subtractive, additive, multi-SynthDef), compilation roundtrip (determinism, anonymous names, optimization equivalence). No audio hardware required.

- [x] **`basic.py` UGen coverage.** `MulAdd`, `Sum3`, `Sum4`, `Mix` coverage raised from 26% to 86%. 37 tests in `test_basic_ugens.py` covering algebraic simplifications, rate computation, zero-elision, multichannel expansion, recursive mixing, and SCgf compilation.

- [x] **Negative / adversarial compiler tests.** 32 tests in `test_adversarial.py` covering deep UGen chains (100-200 deep), large graphs (500 parallel UGens, 100 parameters, 200 constants), name encoding boundaries (empty/1-char/255-char/256-char/non-ASCII), scope isolation, degenerate graphs, topological sort edge cases (diamond, fan-out, fan-in, disconnected subgraphs), compilation determinism, and custom UGen type names.

- [x] **OSC edge case tests.** 48+ tests (with parametrization across native/Python backends) in `test_osc_edge_cases.py` covering NTP timestamp edge cases (zero, fractional, large, immediate, non-realtime), deeply nested bundles (3-level, 5-level, mixed), special characters in addresses (underscores, digits, dots, long, minimal, wildcards), equality edge cases, format_datagram/str/repr, to_list/to_osc, find_free_port, unsupported type encoding, empty/no-arg messages.

- [x] **Concurrency stress tests.** 10 tests in `test_concurrency.py` covering SynthDefBuilder thread isolation (50 concurrent builds, barrier-synchronized stack checks, nested builder isolation, cross-thread UGen rejection, 30 concurrent complex graphs, deterministic output under concurrency) and Server reply dispatch (20 concurrent waiters, concurrent handler registration/unregistration, 100 concurrent dispatches, waiter timeout).

- [x] **Low-coverage UGen modules.** 30 tests in `test_ugen_coverage.py` covering LocalIn (single/multi-channel, default cycling, scalar defaults, feedback loops, control rate), BiPanB2 (audio/control rate, 3-channel output), DecodeB2 (4/8 channels), Splay (single/multiple sources, normalize, spread/center, control rate), Klank (basic, amplitudes, decay times, defaults, empty frequencies, scale params), LinLin (ar/kr, identity), Silence (mono/stereo/8-channel).

- [ ] **Property-based tests (hypothesis).** Algebraic properties: `sig + 0 == sig`, `sig * 1 == sig`, `compile(a + b)` deterministic, multichannel expansion correctness, topological sort determinism. Priority: **low**, effort: **medium**.

- [ ] **Source-tree test matrix.** No CI job runs `make test` against the source tree across Python versions (only via cibuildwheel against built wheels). Priority: **low**, effort: **low**.

---

## CI / Build

- [ ] **Coverage reporting.** No codecov or equivalent integration. Coverage regressions can creep in silently. Upload coverage from the QA job and gate PRs on coverage delta. Priority: **medium**, effort: **low**.

- [ ] **Performance regression benchmarks.** No tracking of graph compilation speed or OSC encode/decode throughput. A simple `pytest-benchmark` suite for `SynthDefBuilder.build()` on a reference graph would catch regressions early. Priority: **low**, effort: **low**.

---

## CLI

- [ ] **`nanosynth render` command.** CLI entry point for offline (NRT) rendering. Takes a Python script that defines a `Score` object, renders it to an audio file. Usage: `nanosynth render script.py -o output.wav --sr 48000 --format WAV --sample-format int16`. Useful for batch processing, CI pipelines, and generative music workflows. Register via `[project.scripts]` in `pyproject.toml`. Priority: **medium**, effort: **low**.

---

## Code Quality

- [x] **Narrow broad `except Exception` catches.** `server.py:_dispatch_reply` OSC decode catch narrowed to `(ValueError, IndexError, struct.error, OscError, RuntimeError)`. Handler callback catch retained as `except Exception` (intentional isolation of user callbacks, annotated with `noqa: BLE001`). `patterns.py:_release_synth` narrowed to `(EngineError, OSError)`.

- [x] **Typed exceptions for protocol/engine errors.** New `exceptions.py` module with hierarchy: `NanosynthError` base, `OscError`, `EngineError`, `MidiError`. `ServerCannotBoot` now inherits from `EngineError`. `SynthDefError` now inherits from `NanosynthError`. Replaced `RuntimeError` with typed exceptions in `scsynth.py`, `supernova.py`, `server.py`, `proxy.py`, `midi.py`, and `osc.py`. All 4 new exception classes exported from `__init__.py`.

---

## Documentation

- [ ] **MIDI usage guide.** `midi.py` has no dedicated documentation beyond docstrings. Need examples covering `MidiIn` setup, handler registration, `midi_note_map()`, and `midi_cc_map()` with a live server. Priority: **medium**, effort: **low**.

- [ ] **Cookbook / examples page.** Beyond the getting-started guide, there's no "recipes" page showing common patterns: effect chains, multichannel routing, recording workflows, NRT rendering, pattern sequencing. Priority: **medium**, effort: **medium**.

- [ ] **Threading model documentation.** The interaction between `EmbeddedProcessProtocol`'s daemon thread, OSC callbacks, `SynthDefBuilder` thread-local scopes, and `Clock`/`Player` threads is non-obvious. A short architecture section would prevent misuse. Priority: **low**, effort: **low**.

---

## Architecture

- [ ] **Async engine protocol.** An `asyncio`-based alternative to the thread-based `EmbeddedProcessProtocol`. Would enable `await server.synth(...)` and integrate cleanly with async web frameworks. Priority: **low**, effort: **medium**.

- [ ] **Lazy / deferred graph compilation.** `SynthDefBuilder.build()` eagerly deep-copies, sorts, optimizes, and compiles. A lazy mode compiling only on first `send()` / `compile()` could benefit live-coding scenarios. Priority: **low**, effort: **low**.

---

## Code Generation

- [ ] **Replace `exec`-based code generation with `__init_subclass__`.** The `_create_fn` / `_add_init` / `_add_rate_fn` machinery uses string-template `exec` (same approach as `dataclasses`). A closure-based approach would make generated methods debuggable and introspectable. Tradeoff: lose nice `inspect.signature()` (recoverable with `__signature__` overrides). Priority: **low**, effort: **medium**.

---

## Feature Gaps (relative to sclang)

- [ ] **Scope / metering** (`Stethoscope`, `ServerMeter`). Useful feedback but requires a UI story (matplotlib? terminal?). Priority: **low**, effort: **medium**.

- [ ] **SynthDef variants**. Niche even in SC, rarely used. Priority: **low**, effort: **low**.
