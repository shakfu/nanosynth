# The SCgf Binary Format

This document specifies the SCgf **version 2** binary layout that nanosynth emits (via `SynthDef.compile()`, `compile_synthdefs()`, and `nanosynth compile`), plus the machine-readable UGen spec that accompanies it. Together they are the shared, language-neutral contract for anyone writing a loader, validator, or an independent SynthDef compiler in another language.

The goal is that the frontend *algorithm* (multichannel expansion, rate inference, constant folding) is reimplemented natively per language, while the *data* -- the UGen metadata table and this byte layout -- is shared, so the two cannot be transcribed by hand and drift apart. The golden SCgf fixtures under `tests/fixtures/scgf/` freeze proven-correct output and serve as the byte-level cross-implementation contract.

## Conventions

- All multi-byte integers and floats are **big-endian**.

- `pstring` is a Pascal-style string: a single `uint8` length followed by that many ASCII bytes (no null terminator). Names are therefore limited to 255 bytes.

- Type shorthand below: `u8`, `u16`, `u32` are unsigned big-endian integers; `f32` is an IEEE-754 big-endian float.

## File layout

```
"SCgf"                       4 bytes, ASCII magic
u32   version                always 2
u16   synthdef_count
synthdef_count x SynthDef
```

### SynthDef

```
pstring   name
Constants
Parameters
UGens
u16       variant_count       nanosynth always emits 0
```

The `name` is the identifier used with `/s_new`; it is independent of any filename. With `--anonymous` (or for an unnamed SynthDef) it is the 32-character lowercase MD5 hash of the compiled graph.

### Constants

```
u32   constant_count
constant_count x f32          the constant pool
```

UGen inputs that are literal numbers reference this pool by index (see below).

### Parameters

Two back-to-back tables: the flat vector of initial control values, then the named index into it.

```
u32   value_count             sum of all control widths
value_count x f32             initial parameter values
u32   name_count
name_count x (pstring name, u32 index)
```

Each named parameter maps a name to its starting offset (`index`) in the control-value vector. Multi-channel parameters occupy several consecutive slots.

### UGens

```
u32   ugen_count
ugen_count x UGen             in topologically sorted order
```

### UGen

```
pstring   class_name          e.g. "SinOsc", "BinaryOpUGen"
u8        calculation_rate    see the calculation_rates enum
u32       input_count
u32       output_count
u16       special_index       operator selector, else 0
input_count x InputSpec
output_count x u8             per-output calculation rate
```

`special_index` selects the operator for `BinaryOpUGen` / `UnaryOpUGen` (indexing the `binary_operators` / `unary_operators` enum) and is `0` for ordinary UGens.

### InputSpec

Each input is a pair of `u32`. The first value distinguishes the two cases:

```
constant input:   u32 = 0xFFFFFFFF,  u32 = index into the constant pool
ugen input:       u32 = source ugen index,  u32 = output index on that ugen
```

That is the complete format. The backend that writes it is about 150 lines; the complexity of a SynthDef compiler lives entirely in the frontend that produces the sorted UGen list, the constant pool, and the control tables.

## The UGen spec

`spec/nanosynth-ugens.json` is the language-neutral UGen metadata table, generated from the code by `scripts/generate_ugen_spec.py` and kept in sync by `tests/test_ugen_spec.py`. Regenerate it with:

```bash
python scripts/generate_ugen_spec.py
```

### Top-level fields

- `spec_version` -- schema version of this file. Bumped only when the spec's shape changes, so it is independent of the nanosynth release version.

- `supercollider_version` -- the SuperCollider release whose UGens and format these match.

- `scgf_version` -- the binary format version documented above (2).

- `enums` -- the wire-level integer tables: `calculation_rates` (token to `u8`), `binary_operators` and `unary_operators` (name to `special_index`), and `done_actions` (name to value).

- `operator_ugens` -- the two operator UGens (see below), listed separately because their `special_index` is not zero.

- `ugens` -- the metadata table, one entry per instantiable UGen.

### UGen entry

```json
{
  "name": "SinOsc",
  "rates": ["ar", "kr"],
  "flags": { "pure": true, "output": false, "width_first": false, "has_done_flag": false },
  "parameters": [
    { "name": "frequency", "default": 440.0, "unexpanded": false },
    { "name": "phase", "default": 0.0, "unexpanded": false }
  ]
}
```

- `name` -- the `class_name` written into the SCgf UGen record.

- `rates` -- the calculation rates the UGen can be instantiated at, as tokens keyed in `enums.calculation_rates`.

- `flags`:

    - `pure` -- side-effect-free, so it may be constant-folded or eliminated as dead code when its outputs are unused.

    - `output` -- writes to a bus and produces no outputs (e.g. `Out`); never dead-code-eliminated.

    - `width_first` -- must be ordered ahead of its width-first peers during the topological sort (e.g. `LocalBuf`, FFT-chain setup).

    - `has_done_flag` -- exposes a done action / done flag.

- `parameters` -- ordered input parameters. `unexpanded` marks a variadic tail (a parameter that consumes all remaining channels rather than expanding, e.g. an array argument). `default` is one of:

    - a number -- the numeric default;

    - `null` -- an explicit `None` default;

    - `"required"` -- no default, the caller must supply a value;

    - `"computed"` -- derived from other parameters at construction time;

    - `"inf"` / `"-inf"` / `"nan"` -- the corresponding non-finite float.

### Operator UGens

Arithmetic operators do not each get their own UGen class. Instead, two UGens carry an operator selector in their `special_index` field:

```json
{
  "name": "BinaryOpUGen",
  "inputs": ["left", "right"],
  "output_count": 1,
  "special_index_enum": "binary_operators",
  "flags": { "pure": true }
}
```

- `name` -- the `class_name` in the SCgf record (`BinaryOpUGen` or `UnaryOpUGen`).

- `inputs` -- the fixed positional inputs (`left`/`right` for binary, `source` for unary).

- `output_count` -- always 1.

- `special_index_enum` -- names the enum table (`binary_operators` or `unary_operators`) whose value the record's `special_index` holds. This is the one case where `special_index` is meaningful for a non-operator decoder: a `class_name` of `BinaryOpUGen` with `special_index` 2 is a multiplication.

Unlike the entries in `ugens`, operator UGens have no rate constructors -- their calculation rate is inferred from the inputs (the maximum of the input rates) -- so they carry no `rates` list. They are always pure.

See [Deploying Precompiled SynthDefs](deployment.md) for how to load the compiled binaries from any host language.
