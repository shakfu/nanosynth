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

- [x] **NRT rendering.** `Score` class with `add()`, `add_synthdef()`, `add_synth()`, `to_binary()`, `render()`. C++ `world_nrt_render()` binding calls `World_NonRealTimeSynthesis`. Supports WAV/AIFF output with configurable sample rate, format, and channel count.

- [x] **SynthDef graph introspection.** `SynthDef.graph()` returns a `SynthDefGraph` with `UGenNode` / `UGenInput` NamedTuples for structured DAG walking. `SynthDef.to_dot()` exports to Graphviz DOT format. Handles BinaryOpUGen/UnaryOpUGen operator names, Control parameter names, multi-output UGens, and constant inputs.

- [ ] **Lazy / deferred graph compilation.** `SynthDefBuilder.build()` eagerly deep-copies, sorts, optimizes, and compiles. A lazy mode compiling only on first `send()` / `compile()` could benefit live-coding scenarios. Priority: **low**, effort: **low**.

- [ ] **Supernova (parallel DSP engine).** SuperCollider's alternative server that distributes node graph evaluation across multiple DSP threads via "parallel groups". Supernova source was stripped during thirdparty trimming and would need to be restored from SC 3.14.1. Key blocker: supernova has no C API equivalent to scsynth's (`World_New`, `World_SendPacket`, etc.) -- its interface is a C++ class hierarchy (`nova_server`), so a new nanobind wrapper (`_supernova.cpp`) would need to be written from scratch. Trimmed boost headers (thread, lockfree, atomic) likely sufficient but need verification. Alternative: support supernova as an external process via UDP/TCP OSC (avoids the C++ wrapper problem but loses in-process zero-latency). Priority: **low**, effort: **high**.

---

## Code Generation

- [ ] **Replace `exec`-based code generation with `__init_subclass__`.** The `_create_fn` / `_add_init` / `_add_rate_fn` machinery uses string-template `exec` (same approach as `dataclasses`). A closure-based approach would make generated methods debuggable and introspectable. Tradeoff: lose nice `inspect.signature()` (recoverable with `__signature__` overrides). Priority: **low**, effort: **medium**.

---

## Code Quality

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

- [x] **"Concepts" documentation.** Non-obvious concepts that need explanation: multichannel expansion, calculation rates (SCALAR/CONTROL/AUDIO/DEMAND), the scope system, parameter rate system, `unexpanded` flag, `is_width_first`, optimization pass, and the `Default` sentinel. Priority: **medium**, effort: **medium**.

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

## CLI

- [ ] **`nanosynth render` command.** CLI entry point for offline (NRT) rendering. Takes a Python script that defines a `Score` object, renders it to an audio file. Usage: `nanosynth render script.py -o output.wav --sr 48000 --format WAV --sample-format int16`. Useful for batch processing, CI pipelines, and generative music workflows. Register via `[project.scripts]` in `pyproject.toml`. Priority: **medium**, effort: **low**.

---

## Feature Gaps (relative to sclang)

Not necessarily all worth implementing, but represents the gap between "compile SynthDefs" and "replace sclang for synthesis work". Ordered by priority:

- [x] **Bus allocation** (`Bus.audio`, `Bus.control`). `Bus` proxy class with `Server.audio_bus()`, `Server.control_bus()`, `free_bus()`, `managed_audio_bus()`, `managed_control_bus()`. Audio buses start at `first_private_bus_id`, control buses at 0. `Bus.set()` for control buses, `int()` compatibility, context managers.

- [x] **Recording** (`Server.record`). `Server.record(path)` / `Server.stop_recording()` / `Server.is_recording` for capturing real-time audio output to WAV/AIFF. Uses DiskOut + 65536-frame streaming buffer. Configurable channel count, bus, format. Recorder SynthDef cached by channel count.

- [x] **Patterns / sequencing** (`Pbind`, `Pseq`, `Prand`). `Pattern[T]` ABC with `__iter__` + `take()` + `|` chaining. Value patterns: `Pseq`, `Prand`, `Pwhite`, `Pseries`, `Pgeom`, `Pchoose`, `Pn`, `Pconst`. `Pbind` binds keys to patterns/scalars, producing `Event` dicts merged with defaults. `Clock` (daemon thread, `time.monotonic()` scheduling) and `Player` drive real-time playback. `Rest` sentinel skips synth creation. Gate release via `threading.Timer`. `midinote`-to-`freq` conversion, auto-derived `sustain`.

- [x] **MIDI input** (`MidiIn`). C++ nanobind wrapper (`_midi.cpp`) around RtMidiIn with vendored rtmidi 6.0.0 (CoreMIDI/ALSA/WinMM, JACK disabled). Python layer (`midi.py`): frozen dataclass message types (`NoteOn`, `NoteOff`, `ControlChange`, `PitchBend`), `MidiIn` class with handler registration (`on_note_on`, `on_cc`, etc.), pure-Python `_parse()` for raw MIDI bytes, context manager support. High-level helpers: `midi_note_map()` (note-on -> synth, note-off -> gate=0) and `midi_cc_map()` (CC -> scaled param).

- [x] **Node proxies / live coding** (`NodeProxy`, `Ndef`). `NodeProxy` owns a private audio bus, source synth (with ASR envelope for crossfade), and monitor synth. Source swap: gate=0 on old (10ms release), create new (10ms attack). Accepts callables (auto-wrapped in SynthDefBuilder) or SynthDef objects. `Ndef` is a global named proxy registry (`__new__` returns `NodeProxy`) keyed by `(id(server), name)`. `clear_all(server)` frees all proxies for a server.

- [ ] **Scope / metering** (`Stethoscope`, `ServerMeter`). Useful feedback but requires a UI story (matplotlib? terminal?). Priority: **low**, effort: **medium**.
- [x] **ParGroup support** (groups work, no ParGroup). Multi-core DSP optimization. Nobody is blocked by its absence. Priority: **low**, effort: **low**.
- [ ] **SynthDef variants**. Niche even in SC, rarely used. Priority: **low**, effort: **low**.

---

## Misc

- [x] **`SynthDefBuilder.__getitem__` return type.** Won't fix -- the `OutputProxy | Parameter` union is correct.

- [x] **Plugin loading validation.** Logs a warning when no UGen plugins path is found.
