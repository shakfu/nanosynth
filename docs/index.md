# nanosynth

nanosynth is a Python package that embeds SuperCollider's [libscsynth](https://github.com/supercollider/supercollider) synthesis engine in-process using [nanobind](https://github.com/wjakob/nanobind). It makes it possible to define SynthDefs in Python, compile them to SuperCollider's SCgf binary format, boot the embedded audio engine, and control it via OSC -- all without leaving Python.

## Features

- **Embedded synthesis engine** -- libscsynth runs in-process as a Python extension (vendored and built from source), no separate scsynth process required
- **High-level `Server` class** -- boot/quit lifecycle, node ID allocation, SynthDef dispatch, buffer management, OSC reply handling, and convenience methods (`synth`, `group`, `free`, `set`). Context manager support and `managed_synth()`/`managed_group()`/`managed_buffer()` for automatic resource cleanup
- **Pythonic SynthDef builder** -- define UGen graphs using a context manager and operator overloading, compiled to SuperCollider's SCgf binary format
- **340+ UGens** -- oscillators, filters, delays, noise, chaos, granular, demand, dynamics, panning, physical modeling, reverb, phase vocoder, machine listening, stochastic synthesis, and more
- **Rich operator algebra** -- 43 binary and 34 unary operators on all UGen signals, including arithmetic, comparison, bitwise, power, trig, pitch conversion (`midicps`/`cpsmidi`), clipping (`clip2`/`fold2`/`wrap2`), and more
- **Buffer management** -- `alloc_buffer`, `read_buffer`, `write_buffer`, `free_buffer`, `zero_buffer`, `close_buffer`, and context managers for automatic cleanup
- **Reply handling** -- bidirectional OSC communication with the engine: persistent handlers (`on`/`off`), blocking one-shot waits (`wait_for_reply`), and send-and-wait (`send_msg_sync`)
- **Envelope system** -- `Envelope` class with factory methods (`adsr`, `asr`, `linen`, `percussive`, `triangle`) and the `EnvGen` UGen
- **OSC codec** -- pure-Python `OscMessage`/`OscBundle` encode/decode with optional C++ acceleration via nanobind
- **`@synthdef` decorator** -- shorthand for defining SynthDefs as plain functions with parameter rate/lag annotations
- **Full type safety** -- passes `mypy --strict`, complete type annotations throughout

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (package manager)

## Installation

```sh
pip install nanosynth
```

Or build from source:

```sh
uv pip install -e .
make build    # incremental wheel build
```
