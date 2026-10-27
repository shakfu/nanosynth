# Roadmap: Dirt-protocol backend

Status as of 2026-10-18, end of day. Claims marked "inference" were not checked against source.

Related documents:

| Document | Content |
|-|-|
| `livecoding.md` | Options considered and why nanodirt |
| `compatibility-position.md` | UGen correctness record against sclang 3.14.1 |
| nanodirt `docs/dev/status.md` | nanodirt progress and next steps |
| nanodirt `docs/dev/integration.md` | Front-end design: adapters, ports, CLI |
| nanodirt `docs/dev/superdirt-parameter-mapping.md` | SuperDirt event pipeline mapped to nanosynth |
| nanodirt `docs/dev/spike-results.md` | End-to-end spike with Tidal, vortex, Strudel |

nanodirt lives at `~/projects/nanodirt`.

## Objective

Let TidalCycles, Strudel and vortex play through `pip install nanodirt` with no SuperCollider install. The stack to replace:

| SC component | Role for the front ends | Replacement |
|-|-|-|
| scsynth | Audio engine, OSC on UDP 57110 | nanosynth embedded engine |
| sc3-plugins | UGens for 7 `super*` synths | nanosynth wheel |
| sclang | Compiles SuperDirt's classes and SynthDefs, runs its event loop | nanosynth DSL, nanodirt |
| SuperDirt + Vowel quark | `/dirt/play`, event model, orbits, effects, samples, instruments | nanodirt |
| Node bridge (Strudel) | WebSocket 8080 to UDP 57120 | nanodirt WebSocket adapter |

nanodirt is GPL-3.0-or-later and depends on MIT nanosynth. A translation of SuperDirt (GPL-2.0-or-later) is a derivative work under the GPL, so it cannot ship inside MIT nanosynth. Packaging options: `nanodirt-integration.md`.

## Division of work

- **nanosynth:** engine, UGens, sclang-compatible DSL semantics, realtime reliability. Nothing Dirt-specific.
- **nanodirt:** receivers, event model, SynthDefs, samples, clock for vortex, CLI.

A nanosynth item belongs on this roadmap only if nanodirt needs it.

## Milestones

Order follows nanodirt `integration.md`, "Order of work".

| | Milestone | Delivers | Owner | Status |
|-|-|-|-|-|
| S | Spike | Tidal handshake, vortex in-process, Strudel over WS, all recorded and checked | nanodirt | Done 2026-10-15 (`spike/`, uncommitted, throwaway) |
| P | Package setup | `pyproject.toml`, Makefile, CI, Python 3.10-3.14 | nanodirt | Done; CI green on Linux and macOS, Python 3.10-3.14 (run 40504664337) |
| M1 | Core phase 1 + UDP adapter | Samples, event model, basic fields, `lpf`/`hpf`/`bpf`, handshake. Tidal works | nanodirt | Done: 34 events match SuperDirt bundle for bundle; audio envelope correlation 0.9997 |
| M2 | WebSocket adapter + Strudel sample maps | Strudel works with default banks, no Node | nanodirt | Done; browsers other than Chrome untested |
| M3 | `nanodirt vortex` | Replacement `vortex.boot`, Link clock, no OSC | nanodirt | Done, headless; GUI not driven |
| M4 | Orbits, global effects, modules, `super*` synths | `room`, `delay*`, `vowel`, 11 default and 32 extra synths | nanodirt | Done: 25 core, 43 instrument and 20 effect SynthDefs checked against sclang |
| M5 | superdough-only controls | 167 Strudel controls that SuperDirt ignores | nanodirt | Not started; needs decision 1 below |
| O | SuperDirt on nanosynth's engine | Parity oracle; full parity with sclang still installed | nanosynth N1, N2, N7 | Done 2026-10-18: `scripts/superdirt_oracle.py` |

## Requirements and status

### R1. Engine

| Item | Status | Evidence |
|-|-|-|
| UDP port 57110 | Done | `scsynth.py:22`; `world_open_udp`, `scsynth.py:290` |
| Tidal `/c_set` and `"cN"` bus strings | Done | Spike: `cutoff: "c1"` mapped via handshake index (`spike-results.md`) |
| Concurrent senders from Qt/IPython threads | Done | `world_send_packet` releases the GIL (nanodirt `integration.md`, "vortex") |
| sc3-plugins built on all wheel platforms | Released in 0.5.0 | Build run 38678335191 for `7a212da`: Linux, Windows, macOS wheels passed with `NANOSYNTH_SC3_PLUGINS` on by default (`CMakeLists.txt:103`) |
| Second client on the engine (oracle O) | Done | `Options.client_id`; SuperDirt confirmed as client 1 with `maxLogins` 4 |

nanodirt runs in-process and allocates through nanosynth, so it needs neither N1 nor N2. Only oracle O does.

### R2. UGen coverage

| Item | Status | Evidence |
|-|-|-|
| UGens in SuperDirt core SynthDefs | Done except `IEnvGen` | nanodirt `superdirt-parameter-mapping.md`, "nanosynth coverage". Only `DirtEnvGen` uses `IEnvGen`, and no core SynthDef uses `DirtEnvGen` |
| sc3-plugins wrappers for the 7 extra synths | Done | `MdaPiano`, `MembraneHexagon`, `AY`, `BMoog`, `SawDPW`, `PulseDPW`, `FM7` |
| UGen classes in all 198 SuperDirt SynthDefs | Done | Dumped from the oracle (`ORACLE_DUMP_UGENS`); all 122 classes exist. Added `GVerb`, `LinXFade2`, `Resonz`, `SinOscFB`; pseudo `DynKlank`, `PMOsc`, `SelectX`, `Silent`, `SoundIn`, `SplayAz`. `IEnvGen` only for unused `DirtEnvGen` |

### R3. Translation fidelity

nanodirt rewrites SuperDirt's sclang SynthDefs in the nanosynth DSL. Where the two languages differ, the rewrite gives wrong audio or needs boilerplate.

| Item | Status | Evidence |
|-|-|-|
| Operator indices, input order, defaults | Fixed in 0.4.0 | CHANGELOG `[0.4.0]` |
| `range`, `exprange`, `linlin`, `linexp`, `expexp`, `clip`, `fold`, `wrap`, `lag` | Done | Corpus case `mapping` matches sclang |
| `Mix` keeps the outer array | Done | Corpus case `multichannel` now matches |
| Input-rate validation (`checkInputs`) | Done | Probed from sclang: 147 slot rules over 93 core classes, 2831 over 129 sc3-plugins classes |
| `Envelope.linen` linear by default | Done | SuperDirt's default synths call `Env.linen` with `\lin` |
| `LocalIn` first block in NRT | Fixed in engine | Read uninitialized memory at block 0; mattered for in-process NRT parity tests |
| Arguments sclang defaults but nanosynth requires | Open, not blocking | 199 arguments in 101 UGens (`compatibility-position.md`, "Low") |

### R4. Realtime reliability

nanodirt uses only the realtime path: timetagged bundles 0.1-0.25 s ahead, buffer reads while running.

| Item | Status | Evidence |
|-|-|-|
| Realtime tests in CI on every push | Done for scsynth | `test (realtime, scsynth)` runs on push; supernova excluded (TODO, Medium) |
| Onset accuracy for future timetags | Done | `test_future_bundles_play_on_time`: 1-sample error at 0.3 s lookahead |
| Buffer read without blocking the sender | Done | Header parsed on first use; `/b_allocRead` sent without waiting |
| UDP after a reboot in one process | Fixed in engine | `patches/sc-asio-restart.patch`; a second World read no UDP packets |
| Supernova reboot in one process | Broken | Segfault in `_run_loop` (TODO, Medium). Not blocking: nanodirt uses scsynth |
| macOS realtime | Done 2026-10-27 | `test_realtime_smoke.py` passes for scsynth on macOS 26.7 (18 tests); nanodirt over UDP plays samples, synths and global effects with no late drops. Windows is not a target |

### R5. Dirt protocol (nanodirt)

Spec: nanodirt `superdirt-parameter-mapping.md`. Pinned SuperDirt revision: `650a1d6`. Done for M1-M4; nanodirt `status.md` lists what each test checks and what remains (M5, `IEnvGen`, `metatune`, RMS replies).

### R6. Front ends

| Front end | Path | Verified |
|-|-|-|
| Tidal 1.10.3, stock `BootTidal.hs` | UDP 57120 | Spike, macOS; nanodirt on Linux 2026-10-18 |
| vortex `aefea84` | in-process via `vortex.boot` replacement | Spike, headless; GUI and REPL not driven interactively |
| vortex | UDP 57120 | Not tested (inference: same as Tidal) |
| Strudel web, Chrome | WS 8080 | Spike, after the Local Network Access prompt |
| Strudel web, Safari | WS 8080 | Fails; error not captured |
| Strudel web, Firefox | WS 8080 | Not tested |
| Strudel desktop / Node bridge | UDP 57120 | Not tested; `sustain` clash needs `--strudel` |

### R7. Distribution

| Item | Status |
|-|-|
| sc3-plugins in the nanosynth wheel | Released in 0.5.0; nanodirt 0.1.0 requires it |
| Dirt-Samples | Done: `nanodirt samples fetch`, cache at `~/.cache/nanodirt` |
| Strudel default banks | Done: the maps `prebake.mjs` loads, downloaded on first use; MP3 needs ffmpeg (TODO) |
| vortex | git install only; Python 3.11-3.13 |

## Pending work

All pending work, in nanosynth and nanodirt, is in `TODO.md`, section "Dirt-protocol backend".

Decided 2026-10-18: build oracle O; change `Mix` to sclang's semantics; raise on input-rate violations.

## Risks

- **Silent translation errors.** Mitigated: every translated SynthDef is rendered against sclang's binary, and events against stock SuperDirt.
- **Parity drift.** SuperDirt changes upstream. nanodirt follows by hand from `650a1d6`.
- **Safari.** Strudel in Safari did not connect. If Safari blocks `ws://localhost` from https, Safari users need the desktop app or the Node bridge.
- **Port 8080.** Strudel hardcodes it and llama.cpp uses it by default. An upstream Strudel change is the only fix.
- **vortex packaging.** No current PyPI release; `nanodirt[vortex]` cannot depend on a git URL.
