# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
