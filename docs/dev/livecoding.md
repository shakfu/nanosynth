# Livecoding with Dirt-protocol front ends

Status: proposal, 2026-10-15. Nothing here has been run. Claims about external code cite the revision read; claims marked "inference" were not checked.

Revisions read:

- SuperDirt `650a1d6` (2025-12-06)

- Tidal `5ae6552` (codeberg.org/uzu/tidal, 2026-07-02). The GitHub repo is stale; the protocol files are identical

- Strudel `a3302cf` (2026-10-13)

- vortex `aefea84` (2025-12-26)

- uzu/dirt `123b399` (2026-06-21)

## Goal

Let users of TidalCycles, Strudel and vortex play through nanosynth.

## What the front ends send

All three emit SuperDirt's protocol. None targets classic Dirt by default.

| | Tidal | Strudel | vortex |
|-|-|-|-|
| Language | Haskell | JavaScript (browser) | Python (GPL-3) |
| Transport | UDP | WebSocket `ws://localhost:8080` to a Node bridge (`packages/osc/server.js`), then UDP | UDP via pyliblo3 |
| Default target | `127.0.0.1:57120` (`superdirtTarget`, `Stream/Target.hs`) | `127.0.0.1:57120` | `57120` (`SuperDirtStream`, `stream.py`) |
| Message | bundle, `/dirt/play` name/value pairs | same | same |
| Latency default | 0.2 s | set by the scheduler | 0.2 s |
| Added fields | `cps`, `cycle`, `delta` | `cps`, `cycle`, `delta`; `midinote` computed from `note` (octave default 3); `size` from `roomsize` | `cps`, `cycle`, `delta` |
| Other traffic | `/dirt/handshake` every 2 s until `/dirt/handshake/reply`; `/c_set` to port 57110 for bus-mapped controls | none | none |
| Clock | Tidal clock, optional Link | browser `performance` clock | Ableton Link (`LinkClock`) |

Consequences:

- **The reference semantics are SuperDirt's.** Users write `note`, `room`, `size`, `orbit` and synth names (`superpiano`, `supersaw`). Classic Dirt ignores all of these.

- **The level scale differs.** SuperDirt's level is `amp * (min(gain, 2) + overgain)^4` with `amp = 0.4` (`core-synths.scd`, `dirt_gate`; `DirtOrbit.sc`, `makeDefaultParentEvent`). Classic Dirt uses `(gain/2)^4`. At `gain=1` the two levels are 0.4 and 0.0625.

- **The choice in `dirt-parameter-mapping.md` should be revisited.** It picked classic Dirt as the reference for a native receiver. For these users that reference is wrong. Its field analysis is still useful where Dirt and SuperDirt agree.

- **Tidal's `/c_set` messages reach nanosynth's engine directly.** Tidal sends them to port 57110 (`oBusPort`). That is nanosynth's default engine port. It uses the bus indices from the handshake reply (`Stream/Process.hs`). With no reply it keeps resending the handshake, logs "Waiting for SuperDirt", and plays anyway. Bus-mapped controls then go to raw bus numbers.

- **vortex can skip OSC.** `BaseStream.notify_event(event, timestamp, cps, cycle, delta)` is the only output hook. A subclass can call into nanosynth in the same process.

## Options

1. **SuperDirt on nanosynth's engine.** sclang runs the SuperDirt quark and treats nanosynth's embedded scsynth as a remote server.

2. **`nanodirt`.** A Python reimplementation of SuperDirt's event model on nanosynth. No sclang.

3. **uzu/dirt.** The classic C Dirt sampler, either as a separate process or with `libdirt` loaded into the engine as a plugin.

| | 1. SuperDirt | 2. nanodirt | 3a. dirt process | 3b. libdirt plugin |
|-|-|-|-|-|
| Processes | Python + sclang (+ Node for Strudel) | Python (+ Node for Strudel unless bridged) | dirt + front end | Python |
| Tidal | full | the subset implemented | samples only; ignores `note`, `room`, synths | same as 3a |
| Strudel | full | subset | same as 3a | same as 3a |
| vortex | full | subset; can run in-process | same as 3a | same as 3a |
| nanosynth changes | allocator client slice | new package | none | C++ plugin + build |
| New runtime deps | sclang, SuperDirt + Vowel quarks | none | dirt, liblo, libsamplerate, audio backend | libdirt |
| Effort (estimate) | small | large | none | medium-large |

## Option 1: SuperDirt on nanosynth's engine

### Layout

```
Tidal / Strudel bridge / vortex
        |  /dirt/play, /dirt/handshake  (UDP 57120)
        v
sclang (SuperDirt, client 1)              Tidal /c_set (UDP 57110)
        |  /s_new, /b_allocRead, /d_recv          |
        v  (UDP 57110)                            v
embedded scsynth  <--in-process--  Python (nanosynth, client 0)
        |
        v
  audio device
```

### Already in place

- The embedded engine opens a real UDP port (`src/nanosynth/scsynth.py:290`, `DEFAULT_PORT = 57110`). sclang attaches with `Server.remote`. Tidal's `/c_set` arrives on the same port.

- SuperDirt compiles its SynthDefs in sclang and sends them with `/d_recv`. nanosynth's graph compiler is not involved.

- The core SynthDefs use only UGens from shipped plugins. These are `core-synths.scd`, `core-synths-global.scd` and `default-synths.scd`. For example, `PitchShift` and `BufRd` are in `DelayUGens`, `CheckBadValues` is in `TestUGens`, `SendPeakRMS` is in `TriggerUGens`, and `PanAz` is in `PanUGens`. `SwitchDelay` (sc3-plugins) is used only when it exists; the fallback is `CombL`.

- SuperDirt reads `wav`, `aif`, `aiff` and `aifc` only (`DirtSoundLibrary.sc`, `fileExtensions`). The vendored libsndfile reads all four.

### The `super*` synths

`library/default-synths-extra.scd` defines 32 synths. They load only when sclang has the class `MembraneHexagon`, i.e. sc3-plugins is installed on the sclang side (`try-load-extra-synths.scd`).

7 of the 32 also need sc3-plugins binaries in the engine:

| Synth | sc3-plugins UGen |
|-|-|
| `superpiano` | `MdaPiano` |
| `superhex` | `MembraneHexagon` |
| `superchip` | `AY` |
| `supernoise` | `BMoog` |
| `supersaw` | `SawDPW` |
| `superpwm` | `PulseDPW` |
| `superfm` | `FM7` |

The other 25 use core UGens only. Without sc3-plugins in the engine, the 7 fail to load (`/d_recv` reports the missing UGen) and the other 25 work. sc3-plugins builds against the vendored SC tree and is planned for the wheel: `sc3-plugins-build.md`.

### Required changes

**1. Partition IDs between clients.** sclang gives each client a slice: `numBuffers div: maxNumClients` buffers, likewise for control buses, and an audio-bus offset (`Server.sc` 3.14.1, `newBufferAllocators`, `newBusAllocators`). nanosynth uses the whole range:

- buffers start at 0 (`src/nanosynth/server.py:614`);

- buses take the full private range (`server.py:617`, `server.py:622`);

- node IDs start at 1000 (`server.py:72`), the same as sclang's client 0;

- `/g_new 1` is the default group (`server.py:673`). That is also client 0's default group in sclang (inference from `makeDefaultGroups`).

Fix: add `Options.client_id` (default 0). The allocators then use slice `client_id` of `maximum_logins`, with the same arithmetic as `Server.sc`. sclang attaches as client 1. Without this, SuperDirt's sample buffers and nanosynth's buffers overwrite each other.

**2. Engine options sized for SuperDirt.** The values are from `superdirt_startup.scd`, with `maximum_logins` lowered:

```python
from nanosynth import Options, Server

options = Options(
    buffer_count=1024 * 256,    # 65536 per client with maximum_logins=4
    maximum_logins=4,           # default 64 leaves 16 buffers per client
    memory_size=8192 * 32,
    maximum_node_count=1024 * 32,
    wire_buffer_count=2048,
    input_bus_channel_count=2,
    output_bus_channel_count=2,
)
server = Server(options)
server.boot()
```

**3. sclang attaches; it does not boot.** `Server.boot` on a remote server only prints "can't boot a remote server" (`Server.sc`).

```supercollider
(
o = ServerOptions.new
    .numBuffers_(1024 * 256).maxLogins_(4).memSize_(8192 * 32)
    .maxNodes_(1024 * 32).numWireBufs_(2048)
    .numInputBusChannels_(2).numOutputBusChannels_(2);
s = Server.remote(\nano, NetAddr("127.0.0.1", 57110), o, 1);
Server.default = s;
s.doWhenBooted {
    ~dirt = SuperDirt(2, s);
    ~dirt.doNotReadYet = true;   // headers only at startup; read on first use
    ~dirt.loadSoundFiles;
    ~dirt.start(57120, 0 ! 12);
};
)
```

sclang takes `maxLogins` and `clientID` from the engine's `/notify` reply (`prHandleClientLoginInfoFromServer`). The bus and buffer counts in `ServerOptions` still have to match `Options` by hand.

### Front ends

- **Tidal:** works unchanged. The handshake reply carries SuperDirt's control-bus indices on nanosynth's engine, so `/c_set` reaches the right buses.

- **Strudel:** needs its Node bridge (`npx @strudel/osc`; `bin` in `packages/osc/package.json`) as with stock SuperDirt.

- **vortex:** works unchanged.

### Headless sclang

The cmake recipe in `compatibility-position.md` ("Reproduce") builds sclang without Qt. Add the `SuperDirt` and `Vowel` quarks, cloned into the `includePaths` of `sclang_conf.yaml`, and Dirt-Samples. On macOS, `sclang script.scd` from SuperCollider.app also works without opening a window. Memory figures for either build have not been measured.

### Risks

- nanosynth's `/notify` handling receives `/n_go` and `/n_end` for SuperDirt's nodes. `Synth` and `Group` bookkeeping must ignore node IDs it did not allocate.

- One SynthDef namespace for both clients. Avoid SuperDirt names (`dirt_*`, `imp`, `psin`, `gabor`, `super*`, ...) in nanosynth code.

- `maximum_synthdef_count=1024` may be too low with the extras loaded. Not measured.

- sclang is still a second interpreter. This option does not reduce footprint.

## Option 2: nanodirt

Chosen. nanodirt is a separate GPL-3 package (`~/projects/nanodirt`). Its front-end design (Tidal, Strudel, vortex) is in that repo: `docs/dev/integration.md`. This section keeps the scope survey.

### Layout

```
Tidal ----UDP 57120----+
Strudel --WS 8080------+--> nanodirt --in-process--> embedded scsynth
vortex ---Python call--+
```

### Scope

SuperDirt is about 2000 lines of sclang classes plus SynthDef files. Each part and what it needs:

| Part | Source | Work |
|-|-|-|
| Receiver | `SuperDirt.sc`, `connect` | `/dirt/play`; `/dirt/handshake` -> `/dirt/handshake/reply` with `&serverHostname`, `&serverPort`, `&controlBusIndices`; `/dirt/hello` -> `/dirt/hello/reply` |
| Event model | `DirtEvent.sc` (229 lines) | Duration from `sustain`, `legato`, `delta` and `unit`; fade times; sample vs synth dispatch; one bundle per event |
| Defaults and pitch | `DirtOrbit.sc`, `makeDefaultParentEvent` | `midinote = note ? n + octave*12` (octave 5), `freq = midicps(midinote)`, `amp = 0.4`, and so on |
| Orbits | `DirtOrbit.sc` (218 lines) | Per-orbit synth bus, group and global effect chain; `dry` mix |
| Per-event modules | `core-modules.scd`, `core-synths.scd` | 13 modules: `vowel`, `shape`, `hpf`, `bpf`, `crush`, `coarse`, `lpf`, `pshift`, `envelope`, `grenvelo`, `tremolo`, `phaser`, `sound` |
| Global effects | `core-synths-global.scd` | `dirt_delay`, `dirt_reverb`, `dirt_leslie`, `dirt_monitor`, `dirt_rms` |
| Sample library | `DirtSoundLibrary.sc` | folder `s`, index `n`; lazy read (`doNotReadYet`) |
| Instruments | `default-synths.scd` (11), `default-synths-extra.scd` (32) | Rewrite in the nanosynth DSL |
| Control buses | `SuperDirt.sc`, `controlBusses` | Allocate, report in the handshake, read in SynthDefs |

nanosynth lacks classes used by the 25 core-only extras: `SinOscFB`, `GVerb`, `Resonz`, `PMOsc`, `SelectX`, `SplayAz` (`compatibility-position.md`, "Coverage", plus this survey). Each is a small `@ugen` or `PseudoUGen` addition.

`vowel` needs the `Vowel` quark's formant tables. These are data, available in `Vowel.sc`.

### Front-end adapters

- **Tidal:** UDP socket on 57120. Decode with `OscBundle.from_datagram` (`osc.py:379`). Keep the timetag.

- **vortex:** a `BaseStream` subclass that calls nanodirt's `play(event, timestamp, cps, cycle, delta)` directly. No OSC, no UDP, no pyliblo3 on the output path. vortex timestamps are `liblo.time()` seconds (`stream.py`), which convert to an OSC timetag.

- **Strudel:** either keep the Node bridge and use the UDP path, or accept its WebSocket JSON (`{address, args, timestamp}`, timestamp in ms) on port 8080. The second needs a WebSocket library; the stdlib has none.

### Phases

1. Samples, event model, the `gain`/`pan`/`speed`/`begin`/`end`/`cut`/`unit` fields, and `lpf`/`hpf`/`bpf`. This covers most drum-pattern code.

2. Orbits and global effects (`room`, `size`, `dry`, `delay*`).

3. Handshake and control buses. Before this, Tidal plays but logs "Waiting for SuperDirt".

4. Remaining modules, `vowel`, and the 25 core-only `super*` synths.

5. The 7 sc3-plugins synths. This needs sc3-plugins binaries in the engine, so it may never ship by default.

### Parity testing

Option 1 is the oracle. Send the same timestamped `/dirt/play` bundle to SuperDirt-on-nanosynth and to nanodirt, record both with `Server.record`, and compare. SuperDirt has no non-real-time mode, so the comparison is real-time and needs tolerances for start-time jitter.

### Risks

- **Licence.** SuperDirt is GPL-2.0-or-later (`LICENSE`; `SuperDirt.sc` header), vortex GPL-3.0-or-later, Strudel AGPL-3, and the Vowel quark LGPL-2.1. Translating SuperDirt's SynthDefs and classes produces a derivative work under SuperDirt's GPL; nanodirt takes the "or later" option and is GPL-3.0-or-later, which vortex also requires. Put nanodirt in its own GPL-3 package that depends on nanosynth, rather than in the MIT package. Writing from behaviour alone is possible, but slower and gives worse parity.

- **Parity drift.** SuperDirt changes; nanodirt follows by hand. Pin a SuperDirt revision and record it.

- **Python on the event path.** Per event: decode, look up the sample, build the bundle, `world_send_packet`. About 100 events/s for dense Tidal code (16 events per cycle, 12 orbits, 0.5 cps). Unlikely to matter (inference; benchmark).

- **GIL contention** with vortex's `LinkClock` thread in the same process. A late send makes an event late, not early. The engine's audio is unaffected.

## Option 3: uzu/dirt

Dirt accepts `/dirt/play` on UDP 7771 and has a library form, `libdirt` (GPL-3). It covers samples with a fixed effect chain only: 32 fields (`dirt.h`, `DIRT_FIELDS`), no synths, no `note`, no orbits, no reverb.

All three front ends can reach it:

- **Tidal:** `dirtTarget` (port 7771, positional `/play`, 0.02 s latency), or `superdirtTarget` with the port changed.

- **Strudel:** the bridge takes a `port` field per message.

- **vortex:** `SuperDirtStream(port=7771)`.

The result is a different instrument from what these users' code was written for. Melodic and effect-heavy patterns lose their pitch, synths and reverb, and the level scale differs (see "What the front ends send").

### 3a. Separate process

`dirt -o portaudio -s <Dirt-Samples>`, with nanosynth running alongside.

- No code needed.

- Two audio clients on one device. CoreAudio mixes them. Linux needs JACK or PulseAudio/PipeWire.

- No shared buses and two clocks.

### 3b. libdirt as an scsynth plugin

A `DirtOut.ar(numChannels)` UGen starts libdirt with no audio backend. It calls `dirt_dequeue(now)` and `dirt_audio(out, now)` once per sample, the loop `libdirt-example.c` uses. Events arrive through libdirt's own OSC server (port 7771, liblo) or a `/cmd` plugin command.

Constraints:

- One instance per process: libdirt keeps global state.

- `sample_rate` must equal the engine's.

- `now` must come from the audio clock. A plugin sees block counts, not NTP time (inference from `SC_InterfaceTable.h`).

- `dirt_audio` takes a lock unless built `NOLOCK=1`. The sample loader's worker threads allocate memory.

### Remaining use

libdirt renders offline. It can serve as an oracle for the fields where Dirt and SuperDirt agree, but not for levels, pitch or effect order.

## Recommendation

1. **Option 1 now.** Add `Options.client_id` and document the setup. It gives full compatibility for all three front ends at small cost, and it becomes nanodirt's parity oracle.

2. **Option 2 in phases, as a separate GPL-3 package** (decided; repo `nanodirt`). Start with phase 1 and the vortex adapter. vortex users get the most from it: Python only, one process, no OSC.

3. **Drop Option 3 as a target.** Keep 3a in user docs as a zero-setup sample player.

4. **Revise `dirt-parameter-mapping.md`** to name SuperDirt as the reference, keeping its analysis of the fields Dirt and SuperDirt share.

## Open questions

- Decided 2026-10-15: nanodirt is a separate GPL-3 package; sc3-plugins go into the nanosynth wheel; front-end questions moved to nanodirt `docs/dev/integration.md`.

- Footprint: which machines are in scope? Option 1 keeps sclang; only Option 2 removes it.
