# Scope rules

What belongs in nanosynth. Stated 2026-11-11.

## In scope

nanosynth embeds and wraps the SuperCollider audio engines.

- The engines: scsynth and supernova, in-process.

- What the engines need: libsndfile, the UGen plugins, sc3-plugins (without HOA), and the audio backends.

- The Python API over the engines:
  - SynthDef and UGen graph construction and compilation;
  - server control;
  - NRT scores;
  - patterns and NodeProxy;
  - MIDI;
  - the CLI.

## Out of scope

- Native libraries that the engines do not need. Vendor them in the package that uses them. Example: QuickJS for headless Strudel is in nanodirt.

- Front-end and protocol code: the Dirt event model, and Strudel, Tidal or vortex support. This lives in nanodirt.

- Code under GPL or AGPL. nanosynth is MIT.

## Dependencies

- No third-party runtime dependencies from PyPI. Vendor the library in `thirdparty/` and wrap it with nanobind, behind a `NANOSYNTH_EMBED_*` option.

- Dev and test tools are exempt.

## Test for a new addition

1. Does an engine need it, or does it wrap an engine? If not, it belongs elsewhere.

2. Is it MIT-compatible? If not, it belongs elsewhere.

3. Is it a runtime dependency? If so, vendor it instead.
