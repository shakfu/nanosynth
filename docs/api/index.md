# API Reference

## Core Modules

| Module | Description |
|---|---|
| [SynthDef Builder](synthdef.md) | `SynthDefBuilder`, `SynthDef`, `UGen` base class, `@synthdef` decorator |
| [Server](server.md) | `Server` class -- boot/quit lifecycle, node control, buffer management & numpy data exchange, `sync()`, introspection (`status`/`query_tree`/`reset`), and node notifications. See the [Server Control](../server-control.md) guide |
| [Envelopes](envelopes.md) | `Envelope` class and `EnvGen` UGen |
| [OSC Codec](osc.md) | `OscMessage` and `OscBundle` encode/decode |
| [Enums](enums.md) | `CalculationRate`, `DoneAction`, `BinaryOperator`, `UnaryOperator`, etc. |
| [Options](scsynth.md) | `Options` dataclass and `EmbeddedProcessProtocol` |
| [Compiler](compiler.md) | SCgf binary serialization and `compile_synthdefs()` |
| [Exceptions](exceptions.md) | `NanosynthError` hierarchy |

## Composition

| Module | Description |
|---|---|
| [Patterns](patterns.md) | `Pseq`/`Prand`/`Pwhite` value patterns, `Pbind` events, `Clock` and `Player` |
| [Node Proxies](proxy.md) | `NodeProxy` and `Ndef` -- hot-swappable sources for live coding |
| [Score (NRT)](score.md) | Offline rendering to an audio file without an audio device |

## Engines & I/O

| Module | Description |
|---|---|
| [Supernova](supernova.md) | Parallel-DSP engine lifecycle. See the [Supernova Guide](../supernova.md) |
| [MIDI](midi.md) | `MidiIn` and parsed message types. See the [MIDI Guide](../midi.md) |

## UGens

340+ UGen classes organized by category. See the [UGen index](ugens/index.md) for an overview.
