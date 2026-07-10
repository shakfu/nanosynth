# Related Projects

## synthdef -- a native Rust port

[synthdef](https://github.com/shakfu/synthdef) is a native Rust port of nanosynth.

It reimplements the SynthDef compiler in Rust, driven by this package's language-neutral UGen spec (`spec/nanosynth-ugens.json`) and validated **byte-for-byte** against nanosynth's compiler via shared golden fixtures, so the two implementations cannot silently diverge.

On top of the compiler it builds a full stack:

- A nanosynth-style `Server` -- load SynthDefs, play synths and groups, set controls by name, buses, buffers, node notifications, and offline / real-time rendering.

- SuperCollider-style pattern sequencing (Pbind/Pseq/Pwhite/Pwrand/...) with per-event timing, polyphony, gate-release, and a background clock.

Both run over the pure-Rust [`plyphon`](https://crates.io/crates/plyphon) synthesis engine (which has no process-global state and also compiles to `wasm32`).

The goal is a portable core that runs where a Python runtime cannot -- other languages via a C ABI, the browser via WASM, or a DAW plugin. The [`nanosynth compile`](cli.md) CLI and the [SCgf format spec](scgf-format.md) document the same binary format both projects emit.
