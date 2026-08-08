# Threading Model

nanosynth uses multiple threads internally. This page documents which threads exist, what they do, and what is safe to call from where.

## Thread overview

| Thread | Created by | Purpose | Lifetime |
|--------|-----------|---------|----------|
| Main thread | User | SynthDef construction, Server API calls, interactive use | Entire process |
| Engine thread | `EmbeddedProcessProtocol.boot()` | Runs the embedded scsynth/supernova audio engine | Boot to quit (daemon) |
| Reply callback | Engine internals | Dispatches OSC replies from the engine back to Python | While engine is running |
| Clock thread | `Clock.start()` | Drives pattern scheduling via `time.monotonic()` | Start to stop (daemon) |
| Timer threads | `Player._tick()` | One-shot threads that release synth gates after sustain duration | Short-lived (daemon) |
| MIDI thread | `MidiIn()` | RtMidi's internal polling thread for MIDI input | While port is open |

All background threads are daemon threads -- they do not prevent process exit.

## Engine lifecycle

`EmbeddedProcessProtocol` manages the audio engine on a background thread. The lifecycle is a state machine:

```
OFFLINE --> BOOTING --> ONLINE --> QUITTING --> OFFLINE
```

Only one engine instance (World) can exist per process. This is enforced by a class-level `threading.Lock` (`_active_world_lock`) that is held for the entire lifetime of the engine:

```python
from nanosynth import Server, Options

# boot() acquires the lock, starts the engine, launches the daemon thread
with Server(Options(verbosity=0)) as server:
    # engine is ONLINE, daemon thread is blocked in world_wait_for_quit()
    server.synth("sine", frequency=440.0)
# quit() signals shutdown, joins daemon thread, releases the lock
```

The daemon thread blocks in a C++ call (`world_wait_for_quit`) until the engine shuts down. When shutdown occurs -- either from `quit()` or an engine panic -- the thread cleans up, transitions to `OFFLINE`, and signals an `exit_future` that callers can await.

`EmbeddedSupernovaProtocol` follows the same pattern but runs supernova's event loop on its daemon thread instead.

## Reply dispatch

When the engine sends an OSC response (e.g., `/done`, `/n_go`, `/b_info`), it invokes a reply callback from its internal UDP processing thread. `Server._dispatch_reply()` handles this:

1. Decodes the raw OSC bytes into an `OscMessage`

2. Acquires `_reply_lock` to snapshot the handler and waiter lists

3. Releases the lock

4. Invokes all persistent handlers registered via `server.on(address, callback)`

5. Signals all one-shot waiters registered via `server.wait_for_reply(address)`

Handler exceptions are caught and logged individually -- one failing handler does not prevent others from running.

```python
# Persistent handler -- runs on every /n_go message
def on_node_created(msg):
    print(f"Node {msg.contents[0]} created")

server.on("/n_go", on_node_created)

# One-shot waiter -- blocks until a specific reply arrives
reply = server.send_msg_sync("/b_query", 0, reply_address="/b_info")
```

Handlers run on the reply callback thread, not the main thread. Keep them fast. If a handler needs to interact with shared state, use explicit locking.

## Thread-local SynthDef builders

`SynthDefBuilder` uses a `threading.local()` stack to isolate concurrent graph construction. Each thread maintains its own stack of active builders:

```python
import threading
from nanosynth import SynthDefBuilder, SinOsc, Out

def build_in_thread(freq):
    with SynthDefBuilder(frequency=freq) as b:
        # This builder is only visible to this thread.
        # Other threads have their own independent stacks.
        Out.ar(bus=0, source=SinOsc.ar(frequency=b["frequency"]))
    return b.build(name=f"sine_{freq}")

threads = []
for freq in [220, 440, 880]:
    t = threading.Thread(target=build_in_thread, args=(freq,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()
```

Each UGen is stamped with its builder's UUID at creation time. If a UGen from one builder is passed as input to a UGen in a different builder, a `SynthDefError` is raised. This prevents accidental cross-contamination between concurrent builds.

## Clock and Player scheduling

The `Clock` runs a daemon thread that drives pattern playback. Its main loop:

1. Acquires `_lock`, copies the player list

2. For each player whose scheduled time has arrived, calls `player._tick(now)`

3. Sleeps until the next scheduled event (adaptive wake time via `_stop_event.wait(timeout=...)`)

`Player._tick()` pulls the next event from its pattern and sends it as a *timestamped bundle* rather than an immediate message. Both the `/s_new` and -- for gated envelopes -- the `gate=0.0` release are dispatched during the same tick, stamped for the event's onset and for onset plus sustain respectively:

```python
import time
from nanosynth import Server, Clock, Pbind, Pseq

with Server() as server:
    synthdef.send(server)
    server.sync()

    clock = Clock(bpm=120, latency=0.1)
    # Player._tick() runs on the clock thread; the engine, not this
    # thread's wake time, decides the sample each synth starts on.
    player = Pbind(instrument="sine", dur=Pseq([0.25, 0.5], repeats=4)).play(
        clock, server
    )

    time.sleep(4.0)
    player.stop()
    clock.stop()
```

Two consequences follow from bundling. Onset accuracy no longer depends on when the Python thread woke -- only on the tick landing within the latency window, which is far weaker a requirement. And gate releases hold no Python-side state: no thread is spawned per note, and a release can never fire against a server that has since quit.

The clock thread also isolates player failures. If a `_tick()` raises -- a quit server, a pattern bug -- that player is logged and dropped rather than taking down the clock and silencing every other player sharing it.

The `Clock._lock` protects mutation of the player list (add/remove). Player state itself (`_stopped`, `_next_time`) uses simple attribute writes that are atomic under CPython's GIL. `Player.stop()` can be called from the main thread while the clock thread is ticking -- the `_stopped` flag is checked at the top of each tick.

## What is thread-safe

| Operation | Safe from any thread? | Notes |
|-----------|----------------------|-------|
| `server.synth()`, `server.free()`, `server.set()` | Yes | Delegates to `send_packet()`, a synchronous C call |
| `server.send_msg()`, `server.send_msg_sync()` | Yes | Same as above; `send_msg_sync` blocks the calling thread |
| `server.at()`, `server.send_bundle()` | Yes | The `at()` capture stack is thread-local, so a block open on one thread never swallows another thread's messages |
| `server.on()`, `server.off()` | Yes | Protected by `_reply_lock` |
| `server.wait_for_reply()` | Yes | Uses `threading.Event`, blocks calling thread |
| `SynthDefBuilder` context manager | Yes | Thread-local stacks, UUID scope checking |
| `clock.add()`, `clock.remove()` | Yes | Protected by `Clock._lock` |
| `player.stop()` | Yes | Atomic flag write |
| `node.set()`, `node.free()` | Yes | Delegates to `server.set()` / `server.free()` |
| `NodeProxy` source swap | No | No internal locking; use from one thread |
| `Ndef` registry access | No | Global dict, no locking |
| MIDI handler registration | No | Not locked; register before starting playback |
