# Command-Line Interface

nanosynth installs a `nanosynth` console script with two subcommands: `info` for build and environment diagnostics, and `compile` for turning Python-defined SynthDefs into `.scsyndef` binaries.

Run `nanosynth --help` to see the available subcommands, or `nanosynth <command> --help` for the options of a single command.

## `nanosynth info`

Prints the installed version, Python and platform details, the active audio backend, the UGen plugin path and count, and whether the scsynth and supernova C extensions are embedded in the wheel.

```bash
nanosynth info
```

Pass `-l` / `--list` to print every available UGen class instead:

```bash
nanosynth info --list
```

## `nanosynth compile`

Loads a Python file, finds the SynthDefs it defines, and compiles each one to SuperCollider's SCgf binary format. The resulting `.scsyndef` files can be loaded by a standalone `scsynth` or `supernova` server, sent over OSC with `/d_load`, or precompiled as part of a deployment step so that graph construction does not happen at runtime.

```bash
nanosynth compile defs.py
```

### How SynthDefs are discovered

The command imports the target file as a module and collects every `SynthDef` object bound at module level, in definition order. Both construction styles are picked up:

- Functions decorated with `@synthdef`, which bind a `SynthDef` to the function name.

- SynthDefs assigned from a `SynthDefBuilder.build(name=...)` call.

A minimal input file:

```python
from nanosynth import synthdef
from nanosynth.ugens import Out, SinOsc


@synthdef()
def bleep(freq=440, amp=0.2):
    Out.ar(bus=0, source=SinOsc.ar(frequency=freq) * amp)
```

!!! note
    Importing the file executes it, the same way `sclang` runs a `.scd` file to compile it. Only compile files you trust.

### Options

| Option | Description |
|--------|-------------|
| `FILE.py` | Python file defining one or more SynthDef objects (required). |
| `-o`, `--output DIR` | Directory for per-SynthDef files. Defaults to the current directory. |
| `-b`, `--bundle FILE` | Write all SynthDefs into a single file instead of one file per def. |
| `-n`, `--name NAME` | Compile only the named SynthDef. Repeat the flag to select several. Defaults to all. |
| `--anonymous` | Use each SynthDef's MD5-hash name in the binary instead of its declared name. |

### Per-SynthDef output

By default each SynthDef is written to its own file named after the SynthDef, as `<name>.scsyndef`, in the output directory:

```bash
nanosynth compile defs.py -o build/synthdefs
# Wrote build/synthdefs/bleep.scsyndef
```

If two SynthDefs share the same effective name they would overwrite each other, so the command stops with an error and suggests `--bundle` instead.

### Bundled output

An SCgf file can hold multiple SynthDefs. Pass `--bundle` to write them all into one file:

```bash
nanosynth compile defs.py --bundle build/all.scsyndef
# Wrote 2 SynthDef(s) to build/all.scsyndef (bleep, noise)
```

### Selecting and renaming

Use `--name` to compile a subset, and `--anonymous` to emit hash-based names (useful when a def has no declared name or when you want content-addressed binaries):

```bash
nanosynth compile defs.py -n bleep -o build/
nanosynth compile defs.py --bundle build/all.scsyndef --anonymous
```

### Exit status

The command exits non-zero and reports the reason on standard error when the input file is missing or is not a `.py` file, the file fails to import, no SynthDefs are found, a requested `--name` does not match, or the output directory does not exist.
