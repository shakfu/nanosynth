# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1]

### Fixed

- **OSC blob length integer overflow -> heap over-read** (`_osc.cpp`): `decode_blob` rounded the wire-supplied 32-bit blob length up to a 4-byte boundary *before* the bounds check, so a length near `UINT32_MAX` (e.g. `0xFFFFFFFF`) wrapped to a tiny padded size and slipped past the guard, after which the ~4 GB blob was scanned/copied past the end of the datagram. Reachable from any incoming packet (engine replies are decoded through the same path). The length is now validated against the remaining bytes before the rounding, matching the overflow-safe form already used for bundle elements

- **`audioSignal * 0` and `audioSignal ** 0` crashed the engine** (`synthdef.py`): the compiler folded `x * 0 -> 0` and `x ** 0 -> 1` to a scalar constant unconditionally, even when the surviving operand was an audio/control-rate UGen. Feeding that scalar wire into a signal-rate input (e.g. `Out.ar(bus, SinOsc.ar() * 0)`) made scsynth's SIMD `Out_next_a_nova_64` read a single 4-byte scalar as an aligned 64-sample block -- an out-of-bounds, often misaligned load that segfaults (and, depending on heap layout, can read garbage instead of crashing). The two rate-downgrading folds now apply only when the surviving operand is itself scalar-rate; otherwise the `BinaryOpUGen` is kept so the result is a proper rate-matched silence/ones signal. This was the true cause of the real-boot smoke-test crash previously misattributed to the headless audio environment

- **Unbounded C++ recursion in OSC encoding** (`_osc.cpp`): `encode_value` recursed into nested lists/tuples with no depth limit (unlike the decoder), so a deeply nested or self-referential Python sequence overflowed the C++ stack and crashed the process uncatchably. Encoding now bounds nesting depth and raises `ValueError` past the limit

- **Quit-timeout force-cleanup re-introduced a double-free** (`scsynth.py`, `supernova.py`): when the engine failed to acknowledge shutdown within 5s, the timeout path freed the native `World`/`nova_server` even though the wait thread was still inside `World_WaitForQuit`/`supernova_run` on it -- the exact teardown race the normal path guards against. Shutdown now joins the thread first and, only if it has provably exited, deletes the native object; if the thread is wedged it deliberately leaks rather than free-under-a-live-thread (memory-safe). `supernova_cleanup` was split into `supernova_stop` (deactivate audio) and `supernova_delete` so teardown can order stop -> join -> delete

- **Synchronous requests hung when issued inside an `at()` block** (`server.py`): `send_msg_sync` (and everything built on it -- `sync`, `status`, `version`, `query_tree`, `enable_notifications`, the `send_synthdef` confirmation) registered a reply waiter and then sent the request, but inside `with server.at(...)` the request was captured into the pending bundle instead of being sent, so no reply could ever arrive and the call blocked for the full timeout before reporting a spurious failure on a healthy engine. These now raise a clear `EngineError` telling the caller to move the synchronous call outside the `at()` block

- **Comparison operators did not fold and could crash on cross-scope use** (`synthdef.py`): `>`, `<`, `.equal()`, and `.not_equal()` (unlike `>=`/`<=`) passed no float operator, so two-constant comparisons emitted a stray scalar UGen instead of folding, and one computed outside a builder then used inside raised `SynthDefError: UGen input in different scope`. All six comparisons now fold consistently to `1.0`/`0.0`

- **`Dwhite` upper bound defaulted to 0.0** (`ugens/demand.py`): a copy-paste made `Dwhite`'s `maximum` default `0.0` instead of `1.0`, so `Dwhite()` with defaults degenerated to a constant-zero stream. Corrected to `1.0` (its `Dbrown`/`Diwhite` siblings were already correct) and the language-neutral spec regenerated

- **`Clock.stop()` left held `Pmono` voices ringing** (`patterns.py`): stopping a clock marked its players stopped but, unlike `Player.stop()`, never gated off their held `Pmono` synths, so a mono voice rang until the server quit. `Clock.stop()` now releases every player's held voices

- **`Score.render()` / `to_binary()` did not sort by timestamp** (`score.py`): the NRT command stream is consumed sequentially, so an out-of-order entry (e.g. `score.add(2.0, ...)` before `score.add(1.0, ...)`) was rendered at the wrong time with no error. Both now serialize a stable-sorted copy, and the teardown guard bundle is appended after the sort so it still runs last

- **Option-string use-after-free on abnormal teardown** (`_scsynth.cpp`): the capsule held the `World`'s option strings (`mPassword`, `mRestrictedPath`, ...) which scsynth dereferences on every packet/command, but freed them in its destructor without regard to whether the `World` had been cleaned up. If the capsule was garbage-collected while a `World` was still live (an abandoned boot with a port open), the running engine read freed memory. The strings are now freed only after an explicit `world_cleanup`/`world_wait_for_quit`; otherwise they are leaked deliberately rather than freed under a live engine

- **`enable_notifications` first-use race** (`server.py`): two threads enabling node notifications concurrently could both install the dispatch handlers and both send `/notify 1`, so every `/n_go`/`/n_end`/... fired user callbacks twice. The enable/install transition is now serialized by a dedicated lock

- **`send_packet` handle race on panic** (`scsynth.py`, `supernova.py`): the status check and the native-handle dereference read `self._world`/`self._server` separately, so the wait/run thread nulling it on a panic in between could pass a null handle to the native call. The handle is now snapshotted once and re-checked

- **Explicit buffer-id reservation could corrupt the allocator** (`server.py`): `_BlockAllocator.reserve` did not bounds- or overlap-check the requested id, so reserving an out-of-range or already-allocated id populated the size table without matching a free interval, and a later `free` then injected a bad interval that `allocate` could hand out. `reserve` now validates the range and rejects overlap with an `EngineError`

- **Concurrent `boot()` on one instance could clobber its state** (`scsynth.py`, `supernova.py`): the OFFLINE->BOOTING check-and-set was unsynchronized, so two threads booting the same instance could both proceed and leave `is_running` reporting the wrong state. A per-instance lock now serializes that transition

- **MIDI handler lists were mutated across threads without synchronization** (`midi.py`): the RtMidi callback thread iterated the handler lists while `on_*`/`off_*` mutated them from the user thread, risking `RuntimeError: list changed size during iteration` or missed/double dispatch during live coding. Dispatch now iterates over a snapshot

- **`midi_note_map` leaked voices on retrigger and cleanup** (`midi.py`): a second Note-On for a still-held key overwrote the entry and dropped the previous synth un-gated (a stuck voice), and `cleanup()` left held voices ringing. The map now gates the previous voice off before retriggering and releases all held voices on cleanup

- **Constant folding aborted the whole build on math-domain inputs** (`synthdef.py`): folding `ConstantProxy(-1.0).sqrt_()`, `log(0)`, `(-8) ** (1/3)`, etc. raised `ValueError`/`TypeError` out of graph construction, where scsynth would produce NaN/inf. Such folds now defer to a runtime UGen instead of failing the build

- **Malformed envelope `curves` corrupted or emptied the envelope** (`envelopes.py`): a `curves` list longer than the segment count inflated the compiled segment count (cycling amplitudes/durations), and `curves=None`/`[]` produced a zero-segment envelope that silently dropped every breakpoint. Curves are now normalized to exactly `len(durations)` -- cycled if short, truncated if long, defaulting to LINEAR when empty

- **Failed supernova boot leaked the process engine claim** (`_supernova.cpp`, `_scsynth.cpp`): a boot that failed before the SuperCollider core globals were initialized left the cross-engine coordination env var claimed, wrongly rejecting a later boot of the other engine kind. A scope guard now releases the claim on such pre-init failures (and keeps it once the core exists, since the process is then genuinely tainted), and the supernova RT memory pool is guarded against re-initialization on retry

- **A self-freeing `LFGauss` was silently optimized away** (`synthdef.py`): `LFGauss` is marked pure, so an `LFGauss(done_action=FREE_SYNTH)` whose signal output is unused (used purely to self-free the synth) was dead-code-eliminated by graph optimization, dropping the `DoneAction` -- the synth would never free. Dead-code elimination now keeps any pure UGen that carries an active (nonzero) `DoneAction`; a `DoneAction.NOTHING` UGen is still eliminated, so the optimization is otherwise unchanged

- **Invalid SynthDef/parameter names raised opaque low-level errors** (`compiler.py`): a name longer than 255 bytes raised `struct.error` and a non-ASCII name raised `UnicodeEncodeError` deep in the binary encoder. SCgf string encoding now validates ASCII and the 255-byte limit and raises a clear `SynthDefError`

- **`Pfin` over-consumed its source, and `Ptpar` dropped a leading offset** (`patterns.py`): `Pfin(count, p)` pulled one extra element from the source before stopping (it now consumes exactly `count`, which matters for a shared/side-effecting iterator), and `Ppar`/`Ptpar` discarded a nonzero minimum start offset so an all-delayed parallel group started early (it now emits a leading rest for that offset)

- **`alloc_buffer_from_array` wrote engine memory after a failed sync** (`server.py`): the `sync()` return was ignored, so on a sync timeout the direct buffer write proceeded against a possibly-unallocated buffer. It now raises `EngineError` on a failed sync instead of writing blindly

### Changed

- **`Server.send_synthdef` confirmation timeout is now a parameter** (`server.py`): `/d_recv` completion is asynchronous and a large SynthDef or a busy engine can take well over the previous hard-coded 100 ms, after which the def was marked loaded anyway and a following `/s_new` could fail with "SynthDef not found". The timeout now defaults to 5s (matching the other synchronous calls) and is exposed as a `timeout` argument; the wait still returns the instant `/done` arrives, so a healthy engine is not slowed

- **Stochastic patterns accept a `seed`** (`patterns.py`): `Prand`, `Pwhite`, and `Pchoose` take an optional `seed` and use a per-instance RNG instead of the module-global `random`. A seeded pattern replays identically on every iteration (reproducible NRT renders), and even unseeded patterns are now independent of unrelated `random` use elsewhere in the process

- **`Ndef` registry keyed on the server object** (`proxy.py`): the named-proxy registry was keyed on `id(server)` (an int that can be reused after a server is collected) and is now a `WeakKeyDictionary` keyed on the server itself, so a collected server's entry is dropped automatically and identity can never be aliased

- **In-code documentation of two accepted limitations**: the direct in-process buffer transfer (`_scsynth.cpp` `world_buffer_get`/`set`) now states its safety contract explicitly -- a get/set racing a `/b_free` or `/b_alloc` on the same buffer id is a use-after-free, not a benign glitch, so callers must not run buffer commands for that id during the transfer -- and the cross-engine guard (`_scsynth.cpp`, `_supernova.cpp`) documents that its coordination env var is inherited across `fork()` and is not atomic against concurrent claims (the two extension modules share no symbols, so a process-local static cannot replace it)

### Added

- **Real-boot CI job** (`.github/workflows/build.yml`): a `test-realtime` job provisions a virtual ALSA sound card and runs `tests/test_realtime_smoke.py` against a genuinely booted scsynth `World` (the live `/sync` round-trip, reclaiming allocators, node-free notifications, reboot, and the send/reply deadlock regression), closing the gap where the largest module was previously exercised only by opt-in local runs. Supernova real-boot is intentionally excluded pending a separate teardown/reboot fix

- **Golden-fixture render test** (`test_integration.py`): a new NRT integration test loads each committed `.scsyndef` golden fixture verbatim and asserts it renders non-silent audio -- the correctness link the golden-byte test's docstring claimed but did not previously exercise (the byte test only checks `compile() == fixture`)

- **Independent UGen-default oracle** (`test_ugen_spec.py`): a hand-verified test of well-known UGen argument defaults (the demand-random UGens plus anchor shapes), transcribed from the SuperCollider class library rather than generated from the same Python classes the spec introspects, so a wrong default like the `Dwhite` regression is caught instead of being mirrored into the committed spec

## [0.3.0]

### Added

- **Timestamped OSC bundle scheduling** (`server.py`): `Server.send_bundle(contents, timestamp)` sends an explicit bundle, and `Server.at(timestamp)` is a context manager that captures every message sent inside the block into a single timestamped bundle. Because it hooks `send_msg` -- which all OSC-sending `Server` methods already route through -- the ordinary high-level API works unchanged inside the block (`with server.at(t): server.synth(...)`), rather than needing a bundle-aware variant of each method. Node ids are allocated eagerly, so returned proxies are usable before the bundle is sent. Timestamps are Unix epoch seconds; a past timestamp executes on arrival. The capture stack is thread-local (a block open on one thread never captures another's sends), blocks nest into nested OSC bundles, an empty block sends nothing, and a block that raises sends nothing rather than emitting a half-built bundle

- **Pattern latency scheduling** (`patterns.py`): `Clock(bpm, latency=...)` and `Player(..., latency=...)` (defaulting to the clock's value, so players sharing a clock stay phase-aligned) schedule each event as a bundle stamped `target + latency` instead of an immediate `/s_new` at Python wake time. `DEFAULT_LATENCY` is 0.1s. Onset accuracy is now set by the engine rather than by when the clock thread woke, so playback holds steady under Python-side load. Verified against a live engine via `/n_go` notifications: a bundle stamped 750ms ahead created its node 734ms later, versus 11ms for the unbundled path

- **Pattern quantization** (`patterns.py`): `Clock` now maintains a beat grid, and `play(quant=...)` starts playback on the next `quant`-beat boundary instead of immediately, so parts launched by hand at arbitrary moments still begin together. `offset` starts a given number of beats past the boundary (for backbeats and swung entries). `Clock.elapsed_beats`, `Clock.next_boundary(quant, offset)`, and `Clock.reset_grid()` expose the grid. All players on a clock share one grid, so quantized starts are mutually aligned

- **Pitch and event derivation chain** (`patterns.py`): `Pbind` now implements the sclang derivation chain -- `degree` -> `note` -> `midinote` -> `freq`, plus `db` -> `amp` and `dur`/`legato`/`stretch` -> `sustain`/`delta` -- so patterns can be written in scale degrees rather than precomputed frequencies. `degree` indexes a `scale` (a name from the new `SCALES` table or an explicit semitone list), wrapping across octaves, with fractional degrees interpolating between steps; `root` transposes and `octave` (default 5) places note 0 at MIDI 60. Every step is skipped when the key is bound explicitly, so binding `freq` bypasses the chain entirely. Derivation inputs are treated as metadata and never sent to the synth as controls

- **`Ppar` / `Ptpar`** (`patterns.py`): run event patterns in parallel, merged into one time-ordered stream. Each voice keeps its own `sustain`; only `delta` is rewritten to the gap in the merged stream. Simultaneous events receive a delta of 0 and therefore land in the same bundle timestamp -- verified against a live engine, where coincident events started 0.04ms apart. `Ptpar` adds a per-pattern beat offset

- **`Pmono`** (`patterns.py`): holds a single synth for the lifetime of the pattern and sends `/n_set` per event rather than creating a node per note, releasing it when the pattern ends or the player stops. This is what produces a monophonic gliding line (portamento, continuous filter sweeps) that a stream of separate synths cannot. Verified live: five events created one node and ended one

- **`Pdef`** (`patterns.py`): a named, hot-swappable event pattern registry -- the pattern analogue of `Ndef`. `Pdef(name, pattern)` registers or replaces, `Pdef(name)` looks up, and a running player picks up a replacement at the next event boundary, so a part can be rewritten without stopping playback

- **`Pkey`** (`patterns.py`): references another key of the event being built, with an optional transform callable. A `Pkey` bound to a derivation-chain input (`degree`, `dur`, `db`, ...) resolves before the chain runs so it can drive it; bound to any other key it resolves after, so it can read derived values such as `freq`. Patterns do not overload arithmetic operators, so the transform callable replaces sclang's `Pkey(\freq) * 2`

- **`Pfin` / `Pfindur`** (`patterns.py`): bound a pattern by event count or by total duration. `Pfindur` clips the final `delta` so the total is exact and the pattern lands on a bar line

- **`EventPattern` base class** (`patterns.py`): `play()` moved here from `Pbind`, so every event pattern (`Ppar`, `Pmono`, `Pdef`, `Pfindur`) is directly playable. `Pbind` remains a `Pattern` subclass, so existing type checks are unaffected

- **Demos for the scheduling and pattern features** (`demos/scsynth/`, run via `make demos`): `22_bundle_scheduling.py` plays the same 16-click rhythm twice under deliberate GIL load -- once as immediate messages (audibly uneven) and once as `server.at()` bundles (rigid) -- then uses `send_bundle()` for an atomic chord change and a scheduled synchronised release. `23_pitch_chain.py` plays one degree sequence through four scales, then varies `root`/`octave`/`db`/`legato`/`stretch`, and drives filter cutoff and pan from the derived `freq` via `Pkey`. `24_parallel_quant.py` layers bass/lead/hats through `Ppar`, staggers entries with `Ptpar`, and launches parts at deliberately awkward mid-bar moments to show `quant` snapping them to the downbeat. `25_pmono_pdef.py` plays a line as `Pbind` then `Pmono` so the portamento difference is audible, hot-swaps a running `Pdef` twice without a gap, and bounds patterns with `Pfin`/`Pfindur`

- **Patterns guide** (`docs/patterns.md`): documents the event model, the pitch chain, latency and quantization, and the composite patterns, including an explicit list of what is not implemented (array-valued chord keys, pattern arithmetic operators, `Score.from_pattern`)

- **Native Rust port** ([synthdef](https://github.com/shakfu/synthdef)): a companion project reimplements the SynthDef compiler in Rust, driven by this package's language-neutral UGen spec (`spec/nanosynth-ugens.json`) and validated **byte-for-byte** against nanosynth's compiler via shared golden fixtures, so the two cannot silently diverge. On top of the compiler it adds a nanosynth-style `Server` and SuperCollider-style pattern sequencing over the pure-Rust [`plyphon`](https://crates.io/crates/plyphon) engine (native and `wasm32`), targeting environments a Python runtime cannot reach -- other languages via a C ABI, the browser via WASM, or a DAW plugin. Consuming the shared spec is the reason it was decoupled from the release version (below)

- **Performance benchmark suite** (`benchmarks/`): `pytest-benchmark` benchmarks for the compile hot path (`SynthDefBuilder.build()` and `SynthDef.compile()` on a representative subtractive-synth reference graph) and OSC message/bundle encode/decode. Kept out of `tests/` so the coverage-gated `make test` run does not time them. `make bench` runs them, `make bench-baseline` regenerates the committed `benchmarks/baseline.json`, and `make bench-check` fails if any benchmark regresses more than 25% (median) versus the baseline on the same machine. A manual (`workflow_dispatch`-only) `benchmarks` CI job gates gross regressions by benchmarking HEAD and the previous commit on one runner (same-machine, apples-to-apples) at a looser 50% threshold that tolerates shared-runner noise

### Fixed

- **GIL/mutex lock-order inversion deadlocked the process** (`_scsynth.cpp`, `_supernova.cpp`, `_midi.cpp`): the engine's print, reply and MIDI callbacks took their C++ mutex and *then* acquired the GIL, while the Python-side entry points that share those mutexes (`set_print_func`, `set_reply_func`, `set_callback`, the MIDI capsule destructor, and critically `world_send_packet`) are entered with the GIL already held and then take the mutex. Any interleaving of an outgoing packet with an incoming reply could therefore deadlock: the reply thread held the mutex waiting for the GIL while a Python thread held the GIL waiting for the mutex, and every remaining thread then blocked behind the GIL with the process hung at zero CPU. All five callbacks now acquire the GIL first, copy the callable under the mutex, release it, and invoke the handler outside the lock -- one consistent GIL-then-mutex order. Dispatching outside the lock also means a slow reply or MIDI handler no longer blocks every concurrent `send_packet`, and the MIDI callback now holds its own reference so a handler cleared mid-dispatch cannot be torn down under it. `SetPrintFunc` was additionally moved out of the print-mutex scope, where a log line emitted during registration would have re-entered the same non-recursive mutex

  Found when a full `make demos` run hung; diagnosed from a `sample(1)` trace showing a Python thread blocked in `std::mutex::lock()` inside `_scsynth` while an scsynth thread sat in `PyGILState_Ensure`. A new opt-in regression test (`test_realtime_smoke.py::test_concurrent_send_and_reply_does_not_deadlock`, gated by `NANOSYNTH_TEST_REALTIME=scsynth`) drives six sender threads against four reply threads with node notifications enabled; it deadlocks the pre-fix build within seconds and passes on the fix. Verified by rebuilding both ways: pre-fix wedged 4/4 runs, post-fix survived 5/5 at ~140k reply events per 30s run. The test runs the stress in a subprocess so a future regression surfaces as a timeout rather than wedging the pytest session

### Changed

- **`Pattern.play()` moved to the base class** (`patterns.py`): `play()` was initially added to the new `EventPattern` base, which left the generic wrappers unplayable -- `Pn(Pbind(...))`, the idiomatic way to loop a part, raised `AttributeError`, as did `Pseq([...])`, `Pfin(...)` and `p1 | p2` over events. Since those are generic in their element type they cannot subclass `EventPattern`, so `play()` now lives on `Pattern` itself. `EventPattern` remains as the marker for the event layer. Found while writing the demos

- **Player advances by `delta`, not `dur`** (`patterns.py`): the time advance after an event now comes from its `delta` key (which honours `stretch`, and which `Ppar` rewrites to the gap in the merged stream), falling back to `dur` when absent. For a plain `Pbind` with no `stretch` the two are identical, so existing patterns are unaffected

- **Gate release is now engine-scheduled** (`patterns.py`): `Player` previously spawned a `threading.Timer` per note to send `gate=0.0` after the sustain duration. The release is now sent during the same tick as the note itself, stamped `onset + sustain`, so the engine holds it. This leaks no thread at high event density, cannot drift independently of the clock, and can never fire from Python against an already-quit server (a queued release simply dies with the engine)

- **Clock isolates failing players** (`patterns.py`): an exception in `Player._tick()` previously propagated into the clock's run loop and killed the clock thread, silencing every other player sharing it. A failing player is now logged and dropped while the clock keeps ticking; a `Player` whose server has quit (`EngineError`/`OSError`) ends its own playback cleanly instead of raising on every subsequent tick

- **UGen spec now records output arity**: each entry in `spec/nanosynth-ugens.json` gains an `outputs` field -- `{"kind": "fixed", "count": N}` for most UGens (0 for `Out`, 2 for `Pan2`, ...) or `{"kind": "variable", "default": N}` for multichannel UGens. The `@ugen` decorator stores the declaration on the class (`_declared_channel_count` / `_declared_is_multichannel`) for introspection without affecting the runtime channel count. Needed by non-Python frontends to emit multi-output UGens.

- **Decoupled the UGen spec from the release version**: `spec/nanosynth-ugens.json` no longer carries a `generator_version` field, so a version bump no longer trips the `tests/test_ugen_spec.py` drift guard. The spec now regenerates only when the UGen metadata or enum tables actually change

## [0.2.1]

### Added

- **`nanosynth compile` CLI command**: compiles Python-defined SynthDefs to `.scsyndef` binaries for use with a standalone `scsynth`/`supernova`, `/d_load`, or deploy-time precompilation. Loads a `.py` file, discovers every module-level `SynthDef` (both `@synthdef`-decorated functions and `SynthDefBuilder.build()` results), and writes one `<name>.scsyndef` per def (`-o DIR`) or a single bundled SCgf file holding all defs (`-b FILE`). `-n/--name` selects specific defs (repeatable); `--anonymous` emits MD5-hash names. Reports actionable errors (missing/non-`.py` input, import failure, no SynthDefs found, unknown name, missing output dir, duplicate names that would overwrite) on stderr with a non-zero exit

- **Property-based tests** (`test_properties.py`, hypothesis): randomized invariants over the graph frontend -- algebraic identity laws (`sig + 0`/`0 + sig`/`sig - 0`/`sig * 1`/`1 * sig`/`sig / 1`/`sig ** 1` return the original signal; `sig * 0` and `sig ** 0` fold to the constants 0 and 1), constant folding equivalence with Python float arithmetic, multichannel expansion arity (a width-n input expands to n channels; combining widths m and n yields max(m, n)), and compilation determinism (byte-identical SCgf and stable topological order across rebuilds, independent of the declared name). Recipes generate graphs up to 14 UGens deep

- **CLI documentation** (`docs/cli.md`): documents both the `info` and `compile` subcommands, how SynthDefs are discovered, the option matrix, per-def vs bundled output, and exit-status behavior

- **Deployment guide** (`docs/deployment.md`): the precompiled-artifact workflow for non-Python consumers -- compile SynthDefs to `.scsyndef` offline with `nanosynth compile`, then load them at runtime via `/d_load` / `/d_loadDir` / `/d_recv` from nanosynth, `sclang`, or any OSC client. Clarifies that the runtime identifier is the SynthDef name embedded in the binary, not the filename

- **Language-neutral UGen spec** (`spec/nanosynth-ugens.json`, `scripts/generate_ugen_spec.py`): a versioned, machine-readable table of all 341 UGens (names, calculation rates, parameter defaults, and `unexpanded`/pure/output/width-first flags), the operator/rate/done-action enum tables, and an `operator_ugens` block naming `BinaryOpUGen`/`UnaryOpUGen` and the enum table their `special_index` selects, so a non-Python implementation of the SynthDef frontend shares the drift-prone metadata rather than transcribing it by hand. `tests/test_ugen_spec.py` fails if the committed spec drifts from the code (regenerate with `python scripts/generate_ugen_spec.py`); included in sdists

- **SCgf format specification** (`docs/scgf-format.md`): documents the SCgf version-2 binary byte layout (header, constant pool, parameter tables, UGen records, input specs) and the UGen spec schema, for writing loaders, validators, or independent compilers in other languages

- **Source-tree CI test matrix**: a `test-source` job runs `pytest` against the source tree (not built wheels) across CPython 3.10--3.14 on Linux, building the C extension from source via `uv sync`. Closes the gap where `make test` was previously only exercised against cibuildwheel-built wheels

## [0.2.0]

### Added

- **Node lifecycle notifications** (`server.py`): `Server.enable_notifications()` registers for the engine's node events (`/notify`); once on, `/n_go`/`/n_end`/`/n_off`/`/n_on`/`/n_move` are parsed into `NodeEvent` objects. `on_node(callback)` receives every event; `wait_for_node_free(node_id, timeout)` blocks until a node ends (including a self-freeing `DoneAction` synth, which the client otherwise has no way to observe); and `Synth.wait_free()` / `Synth.on_free(callback)` are per-node conveniences (the latter is one-shot and self-unregisters). `enable_notifications()` waits for the `/done /notify` confirmation so registration is in effect before any node is created -- otherwise the first node's `/n_go` can be missed. `NodeEvent` is exported from the top-level package

- **Server introspection & control** (`server.py`): `Server.status()` returns a `ServerStatus` (CPU load, sample rate, and ugen/synth/group/synthdef counts from `/status.reply`); `version()` returns a `ServerVersion` (`/version.reply`); `query_tree(group, controls=...)` returns the live node graph as a nested `NodeInfo` tree (groups, synths, and their current control values, parsed from `/g_queryTree.reply`); `dump_tree()` prints it to the engine log; and `reset()` is the "panic" equivalent -- frees all nodes (`/g_freeAll`), clears the scheduler (`/clearSched`), recreates the default group, and resets the node-id allocator (leaving loaded SynthDefs, buffers, and buses intact). `ServerStatus`/`ServerVersion`/`NodeInfo` are exported from the top-level package

- **Direct numpy buffer data exchange** (`server.py`, `_scsynth.cpp`): `Server.get_buffer_data(buffer_id)` and `set_buffer_data(buffer_id, array)` copy samples directly between a numpy array and a buffer's in-process float storage via `memcpy` -- no OSC round-trip and none of the `/b_getn`/`/b_setn` datagram-size limits, which is the core advantage of the embedded engine. `get` returns a `(frames, channels)` float32 array (owning a copy, so it stays valid across buffer reallocation); `set` accepts 1-D (mono) or 2-D input, coerced to contiguous float32 and shape-checked against the buffer. `buffer_info(buffer_id)` returns `(frames, channels, sample_rate)`, and `alloc_buffer_from_array(array)` allocates a correctly-sized buffer and fills it in one call (handy for loading wavetables/samples). scsynth-only (raises `EngineError` for supernova); numpy is an optional dependency (`pip install nanosynth[numpy]`), imported lazily with a clear error if missing. The C++ accessors (`world_buffer_get/set/info`) read the live buffer, so concurrent synth access during a transfer may tear/glitch (documented, never crashes)

- **`Server.sync()` round-trip barrier**: sends `/sync` with a unique id and blocks until the matching `/synced` reply, the canonical scsynth flush primitive. Returns `True` once synced or `False` on timeout. Concurrent `sync()` calls are matched by id

- **Reply matchers**: `Server.wait_for_reply()` and `send_msg_sync()` accept an optional `match` predicate so a waiter accepts only a reply satisfying it (e.g. a `/done` whose first argument is the originating command). Non-matching replies leave the waiter registered instead of resolving it

- **Reclaiming id allocators** (`server.py`): node ids, buffers, audio buses, and control buses are now managed by allocators that reclaim freed ids. Buffers/buses use a coalescing free-list block allocator (`_BlockAllocator`) that hands out the lowest available contiguous block, reuses freed blocks, supports explicit-id reservation, and raises `EngineError` on exhaustion. Node ids use a wrapping allocator (`_NodeIdAllocator`) bounded within scsynth's id space (not reclaimed on free, since self-freeing `DoneAction` synths are not reported to the client)

- **Cross-engine process guard** (`_scsynth.cpp`, `_supernova.cpp`): scsynth and supernova each statically embed the full SuperCollider core and share process-global state (the dlopen'd UGen plugin registry, FFT init), so creating one kind after the other has run in the same process segfaults -- in either order, even after a clean quit, and even via NRT (which also creates a scsynth World). A guard in each extension's engine-creation entry point (coordinated through an environment variable, since the two modules share no symbols) now raises `ServerCannotBoot` with a clear message instead of letting the process crash. Same-kind reuse (scsynth reboot, repeated NRT renders) is unaffected

- **Test hardening**: golden SCgf byte fixtures (`tests/fixtures/scgf/`, regenerable via `python tests/test_golden_scgf.py`) that freeze proven-correct compiler output and catch silent format regressions; unit tests for the allocators (reclaim, coalescing, capacity, reservation, thread-safety), `sync()`, and reply matchers; forced cross-path OSC parity tests (`test_osc_parity.py`) asserting byte-identical encode, identical decode, and identical exception types across the native and pure-Python codecs; and opt-in realtime smoke tests (`test_realtime_smoke.py`, gated by `NANOSYNTH_TEST_REALTIME=scsynth|supernova`) that boot a real engine and exercise `sync()`, buffer reclaim, and clean quit. A `--cov-fail-under`-style coverage floor (90%) is enforced via `[tool.coverage.report]`

### Fixed

- **OSC codec C++/Python parity** (`_osc.cpp`, `osc.py`, `exceptions.py`): the two codecs violated their "must stay compatible" contract. They now agree on (a) **exception type** -- both raise `OscError` on malformed input (the C++ path via a nanobind exception translator scoped to a dedicated `OscDecodeError` C++ type, so it does not affect `std::runtime_error`s from the `_scsynth`/`_supernova` extensions -- nanobind translators are process-global; the Python path by wrapping `struct.error`/`IndexError`/`ValueError`), and `OscError` now also subclasses `ValueError` so `except ValueError` keeps working; (b) **string encoding** -- both use UTF-8 (Python previously used ASCII and raised on non-ASCII); and (c) **unterminated strings** -- the C++ decoder now rejects a string with no null terminator instead of silently accepting it, matching Python

- **Reply waiter leak on timeout** (`server.py`): a timed-out `wait_for_reply`/`send_msg_sync` waiter was never removed from `_pending_replies`, so it lingered and could be spuriously resolved by a later unrelated reply. Timed-out waiters are now unregistered

- **atexit cleanup leak** (`scsynth.py`, `supernova.py`): `atexit.register(self.quit)` ran in `__init__` and was never unregistered, so every protocol object (booted or not) leaked an atexit callback holding a strong reference. Registration now happens on `boot()` and is removed on `quit()`, so never-booted objects accumulate nothing

- **OSC bundle decoder out-of-bounds read** (`_osc.cpp`): the native bundle decoders (`decode_bundle_from_raw`, `decode_bundle_bytes`) read each element's length as a signed `int32_t` and bounds-checked it with `offset + (size_t)length > len`. A malformed datagram with a negative length cast to `size_t` could wrap that addition and pass the check, then hand a negative/huge size to `nb::bytes`, causing an out-of-bounds read or oversized allocation. Lengths are now read as `uint32_t` and validated with the overflow-safe `element_len > len - offset` (`offset <= len` is guaranteed at that point)

- **Engine boot/quit thread coordination** (`scsynth.py`, `supernova.py`): `_shutdown()` previously did a blind `thread.join(timeout=5)` followed by an unconditional forced `world_cleanup`/`supernova_cleanup`, which could tear the engine down concurrently with a wait/run thread still inside `World_WaitForQuit`/`supernova_run` (a double-free / use-after-free race on the engine handle). It now gates on the existing `exit_future` -- resolved by the wait/run thread only after the engine has been torn down internally -- while that thread is alive, with forced cleanup retained only as a logged last resort on a 5s timeout

- **Boot is now exception-safe** (`scsynth.py`, `supernova.py`): if the on-boot callback or the wait/run-thread start raised, the engine handle was created and the process-global `_active_world`/`_active` flag was left set, permanently wedging every subsequent boot with `ServerCannotBoot`. The go-online sequence is now wrapped; on failure a new `_abort_partial_boot()` tears down the engine and clears the global flag. The thread is started and `boot_future` resolved last, so rollback never races a running loop

- **Pattern clock timing drift** (`patterns.py`): `Player._tick` advanced the next event deadline from the wall-clock wake time (`now + dur * beat_dur`), baking every late wake-up into the following event and accumulating drift over a session. It now advances from the previous scheduled target (`self._next_time + dur * beat_dur`); if the clock falls behind, successive events fire back-to-back until it catches up, with no accumulated error

- **Release and docs CI workflows** (`.github/workflows/`): `release.yml` had its `push: tags` and `workflow_dispatch` inputs commented out while the publish steps gated on the resulting always-undefined `inputs.target` and a never-true `github.event_name == 'push'`, so no PyPI publish could ever run. Triggers are restored and the PyPI gate now keys on `startsWith(github.ref, 'refs/tags/v')`. `docs.yml` ran `uv sync --group docs` against a non-existent dependency group (mkdocs deps live in `dev`); it now runs `uv sync` and its `push: branches: [main]` trigger is restored

### Changed

- **Synchronous SynthDef load matches the sub-command** (`server.py`): `send_synthdef()` now waits for a `/done` whose first argument is `/d_recv`, so a `/done` from an unrelated async command cannot resolve the wait early (still falls back to fire-and-forget on timeout for mock servers)

- **Recording uses `sync()` instead of `time.sleep`** (`server.py`): `record()` and `stop_recording()` replaced their fixed `time.sleep(0.1)` pauses with `self.sync()` barriers, so the disk buffer is provably open before `DiskOut` starts and final samples are flushed before the file is closed

- **Single-sourced package version**: the version was hard-coded in both `pyproject.toml` and `src/nanosynth/__init__.py` and could drift. `pyproject.toml` now declares `dynamic = ["version"]` and reads `__version__` from `src/nanosynth/__init__.py` via scikit-build-core's regex metadata provider, making `__init__.py` the single source of truth

## [0.1.6]

### Added

- **`nanosynth info` CLI command**: shows version, Python version/platform/architecture, audio backend (CoreAudio/PortAudio), UGen plugin path and count, and whether the scsynth and supernova C extensions loaded successfully (with error reason if not). `--list` / `-l` flag lists all available UGen classes alphabetically (341 UGens). Entry point registered via `[project.scripts]` in `pyproject.toml`. Uses `argparse` subparsers for future extensibility

- **MIDI usage guide** (`docs/midi.md`): covers port opening (by index, name substring, or virtual port), MIDI message types (`NoteOn`, `NoteOff`, `ControlChange`, `PitchBend`), handler registration and removal, `midi_note_map()` for note-to-synth mapping with frequency/velocity conversion, `midi_cc_map()` for CC-to-parameter mapping with linear scaling, and thread safety considerations for callbacks running on RtMidi's polling thread

- **Threading model documentation** (`docs/threading.md`): documents all background threads (engine daemon, reply callback, Clock, Timer, MIDI), the engine lifecycle state machine (`OFFLINE -> BOOTING -> ONLINE -> QUITTING`), OSC reply dispatch with locking, thread-local `SynthDefBuilder` stacks with UUID scope checking, Clock/Player scheduling with adaptive sleep, and a reference table of thread-safe vs thread-unsafe operations

- **Integration tests** (`test_integration.py`): 19 tests verifying the full compilation-to-audio pipeline (SynthDefBuilder -> SynthDef -> SCgf binary -> engine load -> audio synthesis -> WAV output) via NRT rendering. Covers sine wave synthesis (non-silence, amplitude scaling, frequency differentiation), parameter control, diverse UGens (WhiteNoise, Saw, LPF, RLPF, Pan2), envelopes (percussive decay verification), Mix, stereo panning, `@synthdef` decorator, complex graphs (subtractive, additive, multi-SynthDef scores), and compilation roundtrip (determinism, anonymous names, optimization equivalence). No audio hardware required

- **Basic UGen tests** (`test_basic_ugens.py`): 37 tests covering `MulAdd`, `Sum3`, `Sum4`, and `Mix` -- all algebraic simplification paths, rate computation and validation, zero-elision, input swapping for rate validity, multichannel expansion, recursive Mix grouping (Sum3/Sum4 tree), and SCgf compilation. Coverage of `basic.py` raised from 26% to 86%

- **Adversarial compiler tests** (`test_adversarial.py`): 32 tests for edge cases -- deep UGen chains (100-deep filter cascades, 200-deep arithmetic chains), large graphs (500 parallel UGens, 100 parameters, 200+ constants), name encoding boundaries (empty, 1-char, 255-char, 256-char overflow, non-ASCII rejection), scope isolation (nested/sequential/cross-scope errors), degenerate graphs (constant-only, parameter-only, all-dead-code), topological sort edge cases (diamond dependencies, wide fan-out/fan-in, disconnected subgraphs), compilation determinism, and custom UGen type name encoding

- **OSC edge case tests** (`test_osc_edge_cases.py`): 48+ tests (parametrized across native C++ and pure-Python backends) covering NTP timestamp edge cases (zero, fractional, large, immediate, non-realtime), deeply nested bundles (3-level, 5-level, mixed message/bundle), special characters in addresses (underscores, digits, dots, long, minimal, OSC wildcards), equality edge cases, `format_datagram`/`str`/`repr`, `to_list`/`to_osc`, `find_free_port`, unsupported type encoding, and empty/no-arg messages

- **Concurrency stress tests** (`test_concurrency.py`): 10 tests covering SynthDefBuilder thread isolation (50 concurrent builds with unique frequencies, barrier-synchronized stack checks, nested builder isolation, cross-thread UGen rejection, 30 concurrent complex graphs with Mix/LPF/params, deterministic output under concurrency) and Server reply dispatch (20 concurrent waiters resolved via raw datagram dispatch, concurrent handler registration/unregistration, 100 concurrent dispatches, waiter timeout)

- **Low-coverage UGen module tests** (`test_ugen_coverage.py`): 30 tests covering LocalIn (single/multi-channel, default cycling, scalar defaults, feedback loops with LocalOut, control rate), BiPanB2 (audio/control rate, 3-channel output), DecodeB2 (4/8 channel counts), Splay (single/multiple sources, normalize/no-normalize, spread/center, control rate), Klank (basic, explicit amplitudes, decay times, default fill, empty frequencies rejection, frequency scale/offset/decay scale), LinLin (ar/kr mapping, identity), and Silence (mono/stereo/8-channel)

- **Typed exception hierarchy** (`exceptions.py`): All exceptions defined in a single module importable via `from nanosynth.exceptions import ...`. `NanosynthError` base class with `OscError` (OSC encode/decode), `EngineError` (engine lifecycle), `ServerCannotBoot` (boot failures, subclass of `EngineError`), `MidiError` (MIDI port/callback), and `SynthDefError` (graph construction) subclasses. All six exception classes exported from the top-level package

- **Supernova demos** (`demos/supernova/`): 5 new demos -- demand-rate sequencing with parallel voices (`07_demand_sequencer.py`), pattern sequencing via Pbind/Clock (`08_patterns.py`), FFT spectral processing (`09_spectral.py`), managed ParGroup context manager with chord progression (`10_managed_pargroup.py`), and NodeProxy/Ndef live coding (`11_nodeproxy.py`)

### Fixed

- **Synchronous SynthDef loading** (`server.py`): `send_synthdef()` now waits for the engine's `/done /d_recv` reply before returning (0.1s timeout), ensuring the SynthDef is ready for immediate use. Previously the fire-and-forget `/d_recv` caused race conditions on supernova where `/s_new` could arrive before the SynthDef was loaded (e.g. NodeProxy source swaps failing with "Cannot create synth"). Falls back gracefully to fire-and-forget on timeout, so mock servers in tests are unaffected

- **NRT render crash with persistent delay synths** (`score.py`): `Score.render()` would segfault during World cleanup when persistent synths (no `DoneAction.FREE_SYNTH` or explicit `/n_free`) containing delay UGens (DelayN, CombC, etc.) reading from private buses via `In.ar` were still running at end-of-score. The engine freed delay line buffers while they were still referenced. Fixed by sending `/g_freeAll 0` (free all nodes in the default group) before the end-of-score marker, ensuring clean synth teardown before World cleanup

### Changed

- **Consolidated exceptions into `nanosynth.exceptions`**: `ServerCannotBoot` moved from `scsynth.py` and `SynthDefError` moved from `synthdef.py` into the new `exceptions.py` module. Both are re-exported from their original modules for internal use but the canonical import path is now `nanosynth.exceptions`

- **Narrowed broad `except Exception` catches**: `server.py:_dispatch_reply` OSC decode catch narrowed to specific decode-failure types (`ValueError`, `IndexError`, `struct.error`, `OscError`, `RuntimeError`). `patterns.py:_release_synth` narrowed to `(EngineError, OSError)`. Handler callback catch retained as `except Exception` with explicit annotation for intentional user-callback isolation

- **Replaced generic `RuntimeError` with typed exceptions**: `scsynth.py` and `supernova.py` `send_packet` raise `EngineError` instead of `RuntimeError` when the server is not running. `server.py` raises `EngineError` for bus/recording state errors. `proxy.py` raises `EngineError` for missing source synth. `midi.py` raises `MidiError` for port-not-found. `osc.py` raises `OscError` for unparseable type tags

## [0.1.5]

### Added

- **Embedded supernova**: `EmbeddedSupernovaProtocol` runs SuperCollider's parallel DSP engine (supernova) in-process via nanobind (`_supernova.cpp`), as a drop-in replacement for `EmbeddedProcessProtocol`. Same `Server` API -- just pass `protocol=EmbeddedSupernovaProtocol()`. Supernova schedules independent nodes across CPU cores when placed in `ParGroup`s, providing parallel DSP execution that scsynth cannot. C++ wrapper (`_supernova.cpp`, ~400 lines) wraps supernova's C++ classes directly (no C API exists), synthesizing `server_arguments` from Python kwargs, implementing a custom reply endpoint for in-process OSC responses, and managing the event loop on a daemon thread. Supernova plugins (24 `_supernova` variants) are compiled with `SUPERNOVA` defined and bundled alongside scsynth plugins. Build gated by `NANOSYNTH_EMBED_SUPERNOVA=ON` CMake option

- **ParGroup support**: `ParGroup` proxy class (subclass of `Group`) and `Server.par_group()` / `Server.managed_par_group()` for creating parallel groups via `/p_new`. ParGroups evaluate their child nodes in parallel across CPU cores (supernova only; scsynth treats them as regular groups)

- **SynthDef disk I/O**: `SynthDef.save(path)` writes compiled SCgf bytes to a `.scsyndef` file (with optional `use_anonymous_name` flag). `Server.load_synthdef(path)` loads a `.scsyndef` file into the engine via `/d_load`, resolving to an absolute path for the engine

- Demo scripts reorganized into `demos/scsynth/` (21 demos) and `demos/supernova/` (6 demos). Supernova demos: `01_sine.py` (basic sine wave), `02_parallel_voices.py` (24 voices in ParGroup), `03_fx_chain.py` (delay + reverb effect chain), `04_parallel_fx.py` (three independent effect chains on private buses in a ParGroup), `05_nested_pargroups.py` (nested ParGroups with left/right voice banks and sequential fx group), `06_dense_polyphony.py` (64 simultaneous voices stress test)

## [0.1.4]

### Added

- **Patterns / sequencing**: `Pattern[T]` abstract base class with `__iter__`, `take(n)`, and `|` (chain) operator. Eight value patterns: `Pseq` (sequential with nested pattern flattening), `Prand` (random selection), `Pwhite` (uniform random float), `Pseries` (arithmetic series), `Pgeom` (geometric series), `Pchoose` (weighted random), `Pn` (repeat a pattern N times), `Pconst` (yield until sum reaches total). `Pbind` binds keys to patterns/scalars to produce `Event` dicts, stops on shortest pattern, merges with configurable defaults, auto-derives `sustain` from `dur` and `freq` from `midinote`. `Clock` (background daemon thread with `time.monotonic()` scheduling, settable `bpm`) and `Player` (pulls events, creates synths, schedules gate release via `threading.Timer`). `Rest` sentinel class for silent beats

- **MIDI input**: C++ nanobind extension (`_midi.cpp`) wrapping RtMidiIn from vendored rtmidi 6.0.0 (CoreMIDI on macOS, ALSA on Linux, WinMM on Windows; JACK disabled). Python layer (`midi.py`): frozen dataclass message types (`NoteOn`, `NoteOff`, `ControlChange`, `PitchBend`), `MidiIn` class with handler registration (`on_note_on`/`off_note_on`, `on_cc`/`off_cc`, etc.), pure-Python `_parse()` for raw MIDI bytes (velocity-0 note-on treated as note-off), context manager support, port opening by index/name/virtual. High-level helpers: `midi_note_map()` (note-on creates synth with freq/amp, note-off sends gate=0) and `midi_cc_map()` (CC values scaled to parameter range). Build integration: `NANOSYNTH_EMBED_MIDI` CMake option, rtmidi built as static library via `add_subdirectory`

- **NodeProxy / Ndef**: `NodeProxy` owns a private audio bus, a source synth (with ASR envelope for clean crossfade on swap), and a monitor synth (reads from private bus, writes to hardware output). Source can be a callable (auto-wrapped in `SynthDefBuilder` with envelope) or a `SynthDef`. Hot-swap sends gate=0 to old source (10ms release) and creates new source (10ms attack) for overlap crossfade. `play()` / `stop()` control monitoring, `clear()` frees all resources, `set()` updates source synth params. `Ndef` is a global named proxy registry: `Ndef(server, "name", source)` creates or retrieves a `NodeProxy`, `Ndef.clear_all(server)` frees all proxies for a server. Registry keyed by `(id(server), name)` to support multiple servers

- **Bus allocation**: `Bus` proxy class with `Server.audio_bus()`, `Server.control_bus()`, `free_bus()`, `managed_audio_bus()`, `managed_control_bus()`. Audio buses allocate from the private range (after hardware I/O); control buses from 0. `Bus` supports `int()` conversion, `set()` for control buses, equality/hashing, and `free()`. `Server.options` property exposes the `Options` configuration

- **Server recording**: `Server.record(path)` captures real-time audio output to WAV/AIFF via DiskOut. `stop_recording()` finalizes the file. `is_recording` property for state inspection. Configurable channel count, bus, header/sample format. Recorder SynthDef built and cached on first use per channel count. `write_buffer()` gains a `leave_open` parameter for disk-streaming buffers

- **NRT (non-real-time) rendering**: `Score` class for offline audio rendering without real-time audio hardware. `Score.add()`, `add_synthdef()`, `add_synth()` build a timestamped sequence of OSC commands; `to_binary()` serializes to SC's binary command file format; `render()` invokes the embedded scsynth NRT engine to produce WAV/AIFF files. C++ binding `world_nrt_render()` wraps `World_NonRealTimeSynthesis` with configurable sample rate, format, channels, and engine options

- **SynthDef graph introspection**: `SynthDef.graph()` returns a `SynthDefGraph` NamedTuple containing `UGenNode` and `UGenInput` structures for programmatic DAG walking. `SynthDef.to_dot()` exports the graph as a Graphviz DOT string for visualization. Handles BinaryOpUGen/UnaryOpUGen operator names, Control parameter names, multi-output UGens, and constant inputs

- Demo script `19_nrt_render.py`: offline rendering of a C major arpeggio to WAV and AIFF files

- Demo script `20_patterns.py`: pattern-based sequencing with Pseq, Prand, Pwhite, Pbind, Clock, and Rest

- Demo script `21_nodeproxy.py`: NodeProxy hot-swapping (sine/saw/noise) and Ndef named proxy registry

- **Concepts documentation page** (`docs/concepts.md`): explains 8 non-obvious internal concepts -- calculation rates, multichannel expansion, the `unexpanded` flag, parameter rates, the builder scope, graph optimization (constant folding and dead code elimination), width-first ordering, and the `Default` sentinel. Each section includes code examples and practical implications

### Changed

- Demos 01--11 converted from low-level `_scsynth` API to high-level `Server` API (`server.synth()`, `server.group()`, `server.free()`, `node.set()`, context manager lifecycle)

- README restructured: Quick Start now leads with the `Server`-based workflow (define, boot, play), followed by managed nodes, effect chains with `AddAction`, and NRT rendering. Synthesis technique examples moved to a dedicated section. SynthDef compilation without engine, graph introspection, and OSC codec moved to Advanced Features

### Fixed

- **Windows NRT render crash** (`score.py`): `Score.render()` used `tempfile.NamedTemporaryFile(delete=True)` for the binary command file, which on Windows holds an exclusive file lock preventing the C++ engine from opening it -- causing an access violation (0xC0000005) in `World_New`. Replaced with `tempfile.mkstemp()` so the file is closed before `world_nrt_render` reads it, with manual cleanup in a `finally` block

## [0.1.3]

### Added

- **`Synth` / `Group` proxy objects**: `Server.synth()` and `Server.group()` now return lightweight `Synth` and `Group` proxy objects instead of raw ints. Proxies support `.set(**params)`, `.free()`, context manager usage (`with server.synth(...) as node:`), and are fully int-compatible via `__int__()`, `__index__()`, `__eq__()`, and `__hash__()`. `managed_synth()` and `managed_group()` also yield proxies. Existing code comparing against ints continues to work unchanged

- **`control()` function**: convenience constructor for SynthDef parameters with rate and lag metadata -- `control(440.0, rate="ar")` is equivalent to `Parameter(value=440.0, rate=ParameterRate.AUDIO)`. Accepts string rate tokens (`"ar"`, `"kr"`, `"ir"`, `"tr"`) or `ParameterRate` enum values

- **Tuple syntax for `SynthDefBuilder`**: parameters can be specified as tuples -- `SynthDefBuilder(freq=("ar", 440.0))` for `(rate, value)` or `SynthDefBuilder(amp=("kr", 0.5, 0.1))` for `(rate, value, lag)`. Works alongside `float`, `Parameter`, and `control()` styles

- **Trimmed `__all__` exports**: `from nanosynth import *` now exports ~60 names (core API + 29 common UGens) instead of 340+. The full UGen set remains available via `from nanosynth.ugens import *` or qualified imports

- **Extended operators**: `BinaryOperator` expanded from 7 to 43 entries, `UnaryOperator` from 2 to 34, covering SC's full practical operator set (power, integer division, comparisons, bitwise ops, trig, pitch conversion, clipping, ring modulation, etc.)

- **Operator methods on UGenOperable**: 16 new dunder methods (`__pow__`, `__floordiv__`, `__le__`, `__ge__`, `__and__`, `__or__`, `__xor__`, `__lshift__`, `__rshift__` and their reverse variants), `equal()`/`not_equal()` explicit comparison methods, 25 named binary methods (`min_`, `max_`, `clip2`, `fold2`, `wrap2`, `ring1`--`ring4`, `atan2`, `hypot`, etc.), and 32 named unary methods (`midicps`, `cpsmidi`, `dbamp`, `ampdb`, `tanh_`, `softclip`, `distort`, `squared`, `sqrt_`, `exp_`, `log_`, `sin_`, `cos_`, etc.)

- **Constant folding** for new operators: `POWER`, `INTEGER_DIVISION`, `MINIMUM`, `MAXIMUM`, comparison ops, and all math-stdlib unary ops fold `float op float` at compile time

- **POWER optimizations** in `BinaryOpUGen._new_single`: `x ** 0` folds to `1`, `x ** 1` folds to `x`

- **Buffer management** on `Server`: `alloc_buffer()`, `read_buffer()`, `write_buffer()`, `free_buffer()`, `zero_buffer()`, `close_buffer()`, `next_buffer_id()`, plus `managed_buffer()` and `managed_read_buffer()` context managers. Buffer IDs are auto-allocated (monotonically from 0) or explicitly specified; allocated buffers tracked in `_allocated_buffers` set

- **Reply handling**: C++ reply callback (`set_reply_func` in `_scsynth.cpp`) routes OSC responses from the engine back to Python; `EmbeddedProcessProtocol.set_reply_callback()` wires it at boot; `Server` gains `_dispatch_reply()` router, `on()`/`off()` for persistent handlers, `wait_for_reply()` for blocking one-shot waits, and `send_msg_sync()` for send-and-wait patterns -- all thread-safe

- Demo script `18_operators_buffers.py`: extended operators (`midicps`, `tanh_`, `clip2`, `dbamp`, `softclip`, `distort`), managed buffer allocation, and synchronous reply handling (`send_msg_sync`)

- **Documentation site** (mkdocs-material + mkdocstrings): auto-generated API reference from docstrings, organized by core modules and 28 UGen categories, with Getting Started guide and changelog. Served locally via `make docs-serve`, deployed to GitHub Pages via `make docs-deploy`. New `docs` dependency group in `pyproject.toml`, GitHub Actions workflow (`.github/workflows/docs.yml`) for auto-deploy on push to main

- **Comprehensive docstrings** across all core modules:
  - `enums.py`: all 6 enum classes (`CalculationRate`, `ParameterRate`, `BinaryOperator`, `UnaryOperator`, `DoneAction`, `EnvelopeShape`) with member descriptions and `from_expr()` methods
  - `synthdef.py`: `SynthDef`, `SynthDefBuilder`, `UGen`, `UGenOperable`, `UnaryOpUGen`, `BinaryOpUGen`, `Parameter`, `Control`, `SynthDefError`, `UGenSerializable`; 25 named binary methods with formulas (`ring1`--`ring4`, `clip2`, `fold2`, `wrap2`, `difsqr`, `sumsqr`, etc.); 8 pitch/amplitude conversion methods with examples (`midicps`, `cpsmidi`, `dbamp`, `ampdb`); waveshaping methods (`distort`, `softclip`)
  - `envelopes.py`: `Envelope` class with full Args section, all 5 factory methods (`adsr`, `asr`, `linen`, `percussive`, `triangle`), `EnvGen` with parameter descriptions
  - `osc.py`: `OscMessage`, `OscBundle` with public method docstrings (`to_datagram`, `from_datagram`, `to_list`), `find_free_port()`
  - `scsynth.py`: `Options` with commonly adjusted fields, `BootStatus`, `ServerCannotBoot`, `EmbeddedProcessProtocol.boot()` and `.quit()`
  - `compiler.py`: `compile_synthdefs()` with Args/Returns documenting the SCgf binary format

- **`AddAction` enum** (`enums.py`): `ADD_TO_HEAD`, `ADD_TO_TAIL`, `ADD_BEFORE`, `ADD_AFTER`, `REPLACE` -- replaces opaque raw ints in `Server.synth()`, `Server.group()`, and their managed variants. Raw int values still accepted for backwards compatibility

- **`ServerProtocol`** structural type (`synthdef.py`): `SynthDef.send()` and `SynthDef.play()` now accept any object satisfying `ServerProtocol` instead of `Any`, restoring type safety without circular imports

### Fixed

- **Gendy1/2/3 parameter wire order** (`gendyn.py`): all three Gendy UGens had incorrect parameter ordering and counts vs the C++ plugin (`GendynUGens.cpp`). Gendy1/2 had a single `frequency` where SC expects `min_frequency`/`max_frequency`, and had four distribution parameters (`amplitude_parameter_one/two`, `duration_parameter_one/two`) where SC expects two (`amplitude_parameter`, `duration_parameter`). Wire positions 2--10 were all wrong, causing silence or garbage output. Gendy3's parameter order was also incorrect (it has a different layout from Gendy1/2 in the C++ -- single `frequency`, no min/max). All three now match their `ZIN0()` indices exactly

- **Klank audio rate** (`ffsinosc.py`): `Klank.ar()` passed `calculation_rate=None` to `_new_expanded`, which resolved to `CalculationRate.SCALAR` -- the filter bank was computed once at init instead of processing audio samples per block. Changed to `CalculationRate.AUDIO`

- **`ParameterRate.from_expr("tr")`**: the `"tr"` token for trigger rate was missing from the string-to-enum mapping, causing `KeyError` when using `control(rate="tr")`. Added alongside `"ar"`, `"kr"`, `"ir"`

- `help(nanosynth)` crash: dynamically generated rate methods (`.ar`, `.kr`, `.ir`) created via `exec` in `_create_fn` had `__module__ = None`, causing `pydoc` to raise `TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'` when rendering help text. Now sets `__module__` from the owning class before applying decorators.

- **`__bool__` trap on `UGenOperable`**: `UGenOperable.__bool__` now raises `TypeError` instead of silently returning `True`. Catches the common footgun where `if sig > 0:` always takes the truthy branch because comparison operators return `UGenOperable` objects, not booleans

- **`Server.quit()` decoupled from protocol internals**: `Server.quit()` now delegates to `EmbeddedProcessProtocol.quit()` instead of reaching into the private `_shutdown()` method, properly setting the `QUITTING` state for clean shutdown callbacks

- **Thread-local builder guard centralized**: replaced three inconsistent `hasattr(_local, "_active_builders")` guard patterns in `SynthDefBuilder.__init__`, `__enter__`, and `UGen.__init__` with a single `_get_active_builders()` function

- **Topological sort descendant ordering**: `_initiate_topological_sort` had `key=lambda x: ugens.index(ugen)` which captured the loop variable, making the sort a no-op. Fixed to `key=lambda x: ugens.index(x)` to sort descendants by their position in the UGen list

## [0.1.2]

### Added

- **~80 new UGen classes** (290 -> 346 total), achieving full parity with supriya's UGen surface:
  - **Phase vocoder** (`pv.py`): `FFT`, `IFFT`, `PV_ChainUGen`, and 34 `PV_*` analysis/resynthesis UGens, plus `RunningSum`
  - **Machine listening** (`ml.py`): `BeatTrack`, `BeatTrack2`, `KeyTrack`, `Loudness`, `MFCC`, `Onsets`, `Pitch`, `SpecCentroid`, `SpecFlatness`, `SpecPcile`
  - **Stochastic synthesis** (`gendyn.py`): `Gendy1`, `Gendy2`, `Gendy3`
  - **Hilbert transforms** (`hilbert.py`): `FreqShift`, `Hilbert`, `HilbertFIR`
  - **Mouse/keyboard** (`mac.py`): `KeyState`, `MouseButton`, `MouseX`, `MouseY`
  - **Disk I/O** (`diskio.py`): `DiskIn`, `DiskOut`, `VDiskIn`
  - **Utility** (`basic.py`): `MulAdd`, `Sum3`, `Sum4`, `Mix` (signal mixer with Sum3/Sum4 tree optimization)
  - **Additions to existing modules**: `LocalBuf`, `ScopeOut2` (bufio); `Demand`, `Dwrand` (demand); `Poll`, `SendReply`, `SendPeakRMS` (triggers); `LocalIn` (inout); `Klank` (ffsinosc); `LinLin`, `Silence` (lines); `Changed` (filters); `CompanderD` (dynamics); `Splay` (panning)

- `Default` sentinel class in `synthdef.py` for parameters whose defaults are computed from other parameters at construction time (used by `FFT`, `Gendy1-3`, `ScopeOut2`)

- `PseudoUGen` base class for virtual UGens that compose other UGens (`Mix`, `Changed`, `CompanderD`, `LinLin`, `Silence`, `Splay`)

- `_postprocess_kwargs` hook on `UGen.__init__` for transforming parameters at construction time (dynamic channel counts, Default resolution, rate forcing)

- `GREATER_THAN` and `LESS_THAN` binary operators with corresponding `__gt__`/`__lt__` on `UGenOperable`

- Demo scripts: `14_spectral.py` (FFT/PV spectral processing), `15_gendy.py` (stochastic synthesis), `16_klank_splay.py` (resonant filter banks), `17_freqshift.py` (Bode frequency shifting)

### Fixed

- `LocalBuf` crash: `SynthDefBuilder.build()` now runs a `_cleanup_local_bufs` pass that automatically inserts a `MaxLocalBufs` UGen when `LocalBuf` instances are present in the graph (e.g. from `FFT`'s auto-allocated buffer). Without this, scsynth would crash with `LocalBuf tried to allocate too many local buffers`

## [0.1.1]

### Added

- `Server` class (`nanosynth.server`) -- high-level wrapper around the embedded scsynth engine with boot/quit lifecycle, node ID allocation, SynthDef dispatch, and convenience methods (`synth`, `group`, `free`, `set`). Supports context manager usage

- `Server.managed_synth()` and `Server.managed_group()` context managers -- create a synth or group and automatically free it on context exit (including on exceptions); guard against freeing if the server has already stopped

- `SynthDef.send(server)` and `SynthDef.play(server, **params)` convenience methods for sending SynthDefs and creating synths in one call

- `SynthDef.dump_ugens()` pretty-printer -- returns a human-readable UGen graph representation (modeled on SuperCollider's `SynthDef.dumpUGens`), showing UGen types, rates, input wiring, operator names, and multi-output counts

- `Envelope.compile()` -- dedicated serialization path producing `tuple[float, ...]` directly, bypassing UGenVector/ConstantProxy; raises `TypeError` on UGen inputs. `serialize()` retained for UGen graph wiring

- Demo scripts `12_server_sine.py` (sine wave via Server API) and `13_server_pad.py` (gated pad chord progression with `managed_synth`, `managed_group`, and `server.set()`)

- `EmbeddedProcessProtocol.send_packet()` and `send_msg()` convenience methods for sending OSC to the engine without importing `_scsynth` directly

- Auto-generated docstrings for all `@ugen`-decorated classes (e.g. `SinOsc -- ar, kr\n\nParameters:\n    frequency (default: 440.0)`)

- `__slots__` on core graph classes (`UGen`, `OutputProxy`, `ConstantProxy`, `UGenVector`, `UGenOperable`, `UGenScalar`, `UGenSerializable`) for lower memory usage

- OSC test suite now runs all 24 tests against both the C++ and pure-Python backends (48 total)

- `EmbeddedProcessProtocol` state machine tests: initial state, quit no-op, send errors when offline, callback storage, boot-when-active guard

- Test coverage for `SynthDefBuilder` cross-scope errors, graph optimization (`_optimize`/`_eliminate`), `Envelope.linen`/`.triangle`/`.asr` factory methods, multi-channel UGens (`In`, `PanAz`, `DecodeB2`), `compile_synthdefs` with multiple SynthDefs, demand-rate UGens (`Dseq`, `Drand`, `Duty`, etc.), and `@synthdef` decorator (trigger/audio/lag rates, complex graphs) -- 54 new tests (322 -> 376)

- `qa` CI job: runs ruff lint, ruff format check, mypy --strict, and pytest against the source tree on every push/PR

- Release workflow (`release.yml`): tag-triggered publish to PyPI via trusted publisher, `workflow_dispatch` for TestPyPI, auto-generated GitHub Release

- Docstrings on `SynthDefBuilder.build()`, `.add_parameter()`, and `.__getitem__()`

- Plugin loading validation: `_options_to_world_kwargs()` logs a warning when no UGen plugins path is found

### Fixed

- macOS CoreAudio teardown crash: registered a C-level `atexit` guard in `_scsynth.cpp` (after `World_New`) that calls `_exit(0)` before CoreAudio's static destructors run; removed `os._exit(0)` from all 11 demo scripts

- `WorldStrings` memory leak in `_scsynth.cpp`: capsule destructor now frees the heap-allocated strings object

- Windows CI build failure caused by Strawberry Perl's incompatible ccache crashing MSVC (`STATUS_ENTRYPOINT_NOT_FOUND`); disabled SC's ccache integration on Windows

- nanobind 2.11 compatibility: replaced capturing lambda in `_scsynth.cpp` capsule constructor with `WorldHandle` struct and non-capturing cleanup function

- Removed 11 `type: ignore[arg-type]` suppressions from `EnvGen` by widening `UGen.__init__`, `_new_single`, and `_new_expanded` kwargs to `UGenRecursiveInput | None`

- OSC decoder unbounded recursion: `_osc.cpp` blob/bundle recursive parsing now enforces a maximum nesting depth of 16 levels; beyond the limit, blobs are returned as raw bytes

- OSC decoder aggregate bounds checking: `decode_message_clean` pre-validates that the payload has enough bytes for all type tags before entering the decode loop

- `world_send_packet` `const_cast` removal: OSC packet data is now copied into a `std::vector<char>` before passing to `World_SendPacket`, eliminating undefined behavior from casting away const on Python bytes

- `scsynth_print_func` buffer overflow: replaced fixed 4096-byte stack buffer with a two-pass approach that dynamically allocates when the formatted message exceeds the stack buffer

### Changed

- Protected `EmbeddedProcessProtocol._active_world` with `threading.Lock` to prevent race conditions on concurrent `boot()` calls

- Cleaned up `Envelope.serialize()` and `UGenSerializable.serialize()` signatures: removed unused `**kwargs` parameter, added docstring documenting the wire format

- Extracted 6 enum classes (`CalculationRate`, `ParameterRate`, `BinaryOperator`, `UnaryOperator`, `DoneAction`, `EnvelopeShape`) from `synthdef.py` into `enums.py`

- Extracted SCgf binary compiler (`_compile_*`, `_encode_*`, `compile_synthdefs`) from `synthdef.py` into `compiler.py`

- Pinned `nanobind>=2.11,<3` in both `[build-system]` and `[dependency-groups]`

- All `ValueError` raises in `synthdef.py` (10) and `envelopes.py` (2) now include descriptive messages

- Narrowed bare `except Exception` in `osc.py` to `except (ValueError, IndexError, struct.error)`

- Refactored all 11 demo scripts to use `_options_to_world_kwargs()` instead of duplicated 25-line `_options_kwargs()` functions

## [0.1.0]

Initial release.

### Added

- **SynthDef compiler** -- `SynthDefBuilder` context manager and `@synthdef` decorator for defining UGen graphs in Python, compiled to SuperCollider's SCgf binary format

- **290+ UGen definitions** across 18 categories: oscillators, filters, BEQ filters, noise, delays, envelopes, panning, demand, dynamics, chaos, granular, buffer I/O, physical modeling, reverb, convolution, I/O, lines, and triggers

- **Envelope system** -- `Envelope` class with `adsr`, `asr`, `linen`, `percussive`, and `triangle` factory methods, plus the `EnvGen` UGen

- **OSC codec** -- `OscMessage` and `OscBundle` encode/decode with pure-Python implementation and C++ accelerated path via nanobind (`_osc.cpp`)

- **Embedded libscsynth** -- in-process SuperCollider engine via nanobind (`_scsynth.cpp`), with `EmbeddedProcessProtocol` for lifecycle management and `Options` frozen dataclass for server configuration

- **Vendored dependencies** -- SuperCollider 3.14.1, libsndfile, and PortAudio built from source via `add_subdirectory`; SC trimmed to 27MB (from 132MB) with only libscsynth, UGen plugins, and required boost headers; libsndfile tailored for WAV/AIFF only (no external codec deps). Audio backend: CoreAudio on macOS, vendored PortAudio on Linux/Windows

- **Incremental builds** -- `make build` uses `--wheel --no-build-isolation` with persistent cmake build cache in `build/`; incremental rebuilds in ~3s

- **Wheel repair** -- platform-conditional wheel repair via delocate (macOS), auditwheel (Linux), delvewheel (Windows); SC's macOS `POST_BUILD` bundle-copy commands disabled to prevent duplicate plugins leaking into the wheel

- **Demos** -- three example scripts: sine wave (`01_sine.py`), subtractive synthesis (`02_subtractive.py`), and FM synthesis with melody (`03_fm.py`)

- **Test suite** -- 291 tests covering OSC round-trip encoding, SynthDef compilation, UGen instantiation and calculation rates, and server options/lifecycle

- **Full `mypy --strict` compliance** with complete type annotations

- **CI workflow** -- GitHub Actions with cibuildwheel building wheels for CPython 3.10--3.13 across macOS ARM64, Linux x86_64, and Windows x86_64; sdist built separately; all artifacts aggregated into a single download

- **Development tooling** -- Makefile with `dev`, `build`, `sdist`, `test`, `lint`, `format`, `typecheck`, `qa`, `clean`, and `reset` targets
