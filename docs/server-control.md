# Server Control

Beyond creating synths and groups, the `Server` exposes runtime facilities that
take advantage of the engine running *in-process*: a synchronization barrier,
direct numpy buffer exchange, introspection of the live node graph, and node
lifecycle notifications. See the [Server API reference](api/server.md) for the
full signatures.

## Synchronization

Most commands (creating synths, allocating buffers, loading SynthDefs) are
asynchronous -- the call returns before the engine has processed them.
`sync()` sends `/sync` and blocks until the engine acknowledges with `/synced`,
guaranteeing every prior command has been applied:

```python
from nanosynth import Server

with Server() as server:
    synthdef.send(server)
    buffer_id = server.alloc_buffer(44100)
    server.sync()                 # buffer + synthdef are now ready to use
    node = server.synth("player", buffer=buffer_id)
```

`sync()` returns `True` once synced, or `False` on timeout. It is the canonical
way to order work that depends on a prior asynchronous command having completed.

## Buffer Data Exchange (numpy)

Because the engine shares the process, sample data moves between a numpy array
and a buffer's memory with a direct `memcpy` -- no OSC `/b_setn`/`/b_getn`
round-trip and no datagram-size limits. Install the optional dependency with
`pip install nanosynth[numpy]`.

```python
import numpy as np
from nanosynth import Server

with Server() as server:
    # Load a numpy array straight into a new buffer (allocates + fills).
    wavetable = np.sin(np.linspace(0, 2 * np.pi, 1024, endpoint=False)).astype("float32")
    buffer_id = server.alloc_buffer_from_array(wavetable)

    # Inspect: (frames, channels, sample_rate)
    frames, channels, sample_rate = server.buffer_info(buffer_id)

    # Read samples back into numpy -- shape (frames, channels), float32.
    data = server.get_buffer_data(buffer_id)

    # Process in numpy and write back (shape must match the buffer).
    server.set_buffer_data(buffer_id, np.tanh(data * 2.0))
```

`get_buffer_data` always returns a 2-D `(frames, channels)` array (mono is
`(frames, 1)`); `set_buffer_data` accepts 1-D (mono) or 2-D input and coerces it
to contiguous `float32`. These read and write the *live* buffer, so for clean
results the buffer should not be in active use by a synth during the transfer (a
concurrent read/write may tear or glitch -- it never crashes). Direct buffer
access is available on the embedded scsynth engine only (not supernova).

## Introspection

Query the running engine and inspect or reset its node graph:

```python
from nanosynth import Server

with Server() as server:
    status = server.status()      # CPU load, sample rate, node/synth/ugen counts
    print(status.num_synths, status.actual_sample_rate)

    version = server.version()    # program name and version

    # The live node tree as a nested NodeInfo (groups, synths, control values).
    tree = server.query_tree(controls=True)
    for child in tree.children:
        print(child.node_id, "group" if child.is_group else child.synthdef)

    # "Panic": free all nodes, clear the scheduler, recreate the default group.
    server.reset()
```

`status()`, `version()`, and `query_tree()` block for a reply and raise
`EngineError` on timeout. `reset()` frees all nodes and resets node-id
allocation but leaves loaded SynthDefs, buffers, and buses intact.

## Node Lifecycle Notifications

Register for node events to observe nodes being created, freed, paused,
resumed, or moved. This is the only way to know when a synth that frees
*itself* (via a `DoneAction` envelope) has actually finished:

```python
from nanosynth import Server

with Server() as server:
    synthdef.send(server)
    server.enable_notifications()

    # Observe every node event.
    server.on_node(lambda e: print(e.action, e.node_id))

    # ...or wait for one specific node to free itself.
    node = server.synth("ping", frequency=440.0)  # a self-freeing percussive synth
    if node.wait_free(timeout=3.0):
        print("the synth finished and freed itself")
```

Each callback receives a `NodeEvent` with `action` (`"go"`, `"end"`, `"off"`,
`"on"`, `"move"`), `node_id`, `parent_group_id`, `is_group`, and (for groups)
`head_node_id`/`tail_node_id`. `Synth.on_free(callback)` is a one-shot
convenience that fires when that specific node ends.

Notifications are off by default. `enable_notifications()` waits for the engine
to confirm registration so the first node's `/n_go` is not missed; callbacks run
on the reply thread, so they must be non-blocking (see the
[Threading Model](threading.md)).
