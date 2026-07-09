# Deploying Precompiled SynthDefs

The nanosynth SynthDef frontend -- the Python API that turns a UGen graph into SuperCollider's SCgf binary format -- is a build-time tool. It runs once, in Python, and emits `.scsyndef` files. Those files are language-neutral: any SuperCollider-compatible engine (`scsynth`, `supernova`, or nanosynth's embedded engine) can load them, from any host language, with no Python runtime present.

This is the recommended path for non-Python consumers. A DAW plugin, a Rust or JavaScript audio app, or a WASM player that needs to *use* a synth almost never needs to *construct* it at runtime -- it needs the compiled definition. Compile the SynthDefs offline with Python, ship the binaries as assets, and load them at runtime over OSC.

## Step 1: compile

Define your SynthDefs in a Python file and compile them with the CLI (see [Command-Line Interface](cli.md) for the full option matrix):

```bash
# One <name>.scsyndef file per SynthDef, into an assets directory
nanosynth compile defs.py -o build/synthdefs

# Or a single bundle file holding every SynthDef
nanosynth compile defs.py --bundle build/synthdefs/all.scsyndef
```

## Step 2: understand the artifact

An SCgf file is self-describing and holds one or more SynthDefs. The exact byte layout is documented in [The SCgf Binary Format](scgf-format.md).

The key deployment fact: the name you reference at runtime is the **SynthDef name embedded in the binary**, not the filename. Per-def output happens to name the file after the SynthDef (`bleep.scsyndef` for a SynthDef named `bleep`), but a bundle groups many names into one file, and `--anonymous` bakes content-hash names into the binary. Load a file, then create synths by the embedded name.

## Step 3: load into an engine

Loading is a standard SuperCollider server command. Three mechanisms cover every host:

- **`/d_load <path>`** -- tell the engine to read one `.scsyndef` file from disk. `/d_loadDir <dir>` loads every `.scsyndef` in a directory. The path must be reachable by the engine process.

- **`/d_recv <bytes>`** -- send the file contents directly as an OSC blob, no filesystem involved. This is the right choice when the engine cannot see your disk (sandboxed plugin, remote server, WASM).

- Both reply with `/done` when the definition is ready. Wait for it before creating synths.

From nanosynth itself:

```python
server.load_synthdef("build/synthdefs/bleep.scsyndef")   # sends /d_load, waits for /done
```

From `sclang`:

```supercollider
s.sendMsg("/d_load", "build/synthdefs/bleep.scsyndef".standardizePath);
```

From any language with an OSC client (Rust, C, JavaScript, ...), send the same messages you would to any `scsynth`: a `/d_load` message with the absolute path string, or a `/d_recv` message with the file bytes as a blob argument, then await the `/done` reply.

You can also point the engine at a synthdefs directory at boot so definitions load automatically -- see the engine's `load_synthdefs` option -- but explicit `/d_load` / `/d_recv` is the portable, predictable choice.

## Step 4: use the SynthDef

Once loaded, create synths by the embedded name with `/s_new`, exactly as if the definition had been authored in `sclang`:

```supercollider
s.sendMsg("/s_new", "bleep", 1000, 0, 0, "freq", 330, "amp", 0.2);
```

## Format compatibility

nanosynth emits SCgf **version 2**, the format used by SuperCollider 3.x. Files compile once and remain loadable by any 3.x-compatible engine. If you need the format details -- to write a loader, validator, or a compiler in another language -- see [The SCgf Binary Format](scgf-format.md) and the machine-readable UGen spec described there.
