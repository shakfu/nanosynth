#!/usr/bin/env python3
"""Generate the language-neutral nanosynth UGen spec.

Introspects every UGen class and emits a machine-readable JSON description of
the UGen metadata table (names, calculation rates, parameter defaults, flags)
plus the enum tables (calculation rates, binary/unary operators, done actions)
that a non-Python implementation of the SynthDef frontend needs.

This is the shared, drift-prone data referenced by the cross-language
compilation tasks: the algorithm (multichannel expansion, rate inference,
constant folding) is reimplemented natively per language, but this table and
the SCgf byte layout are shared so they cannot be transcribed by hand and
diverge. ``tests/test_ugen_spec.py`` asserts the committed spec matches what
this script produces, so it is regenerated in lockstep with the code.

Usage::

    python scripts/generate_ugen_spec.py            # write spec/nanosynth-ugens.json
    python scripts/generate_ugen_spec.py --check    # exit 1 if the file is stale
"""

from __future__ import annotations

import inspect
import json
import math
import sys
from pathlib import Path
from typing import Any

from nanosynth.enums import (
    BinaryOperator,
    CalculationRate,
    DoneAction,
    UnaryOperator,
)
from nanosynth.envelopes import EnvGen
from nanosynth.synthdef import BinaryOpUGen, Default, UGen, UnaryOpUGen
from nanosynth import ugens as ugens_module

SPEC_VERSION = "1.0"
SUPERCOLLIDER_VERSION = "3.14.1"
SCGF_VERSION = 2

SPEC_PATH = Path(__file__).resolve().parent.parent / "spec" / "nanosynth-ugens.json"


def _default_to_json(default: Any) -> Any:
    """Encode a parameter default as a JSON-safe value.

    Numbers stay numbers; ``None`` stays null; the required and computed
    sentinels become the strings ``"required"`` and ``"computed"``; the
    non-finite floats become their string spellings so JSON stays valid.
    """
    if default is inspect.Parameter.empty:
        return "required"
    if isinstance(default, Default):
        return "computed"
    if default is None:
        return None
    value = float(default)
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    if math.isnan(value):
        return "nan"
    return value


def _ugen_classes() -> list[type[UGen]]:
    """Every instantiable UGen class, sorted by name (excludes PseudoUGens)."""
    found: dict[str, type[UGen]] = {}
    for name in dir(ugens_module):
        obj = getattr(ugens_module, name)
        if isinstance(obj, type) and issubclass(obj, UGen) and obj is not UGen:
            found[obj.__name__] = obj
    # EnvGen lives outside the ugens package.
    found[EnvGen.__name__] = EnvGen
    return [found[name] for name in sorted(found)]


def _ugen_spec(cls: type[UGen]) -> dict[str, Any]:
    signature = inspect.signature(cls.__init__)
    ordered_keys = getattr(cls, "_ordered_keys", ())
    unexpanded_keys = getattr(cls, "_unexpanded_keys", frozenset())
    parameters = []
    for name in ordered_keys:
        param = signature.parameters.get(name)
        default = param.default if param is not None else inspect.Parameter.empty
        parameters.append(
            {
                "name": name,
                "default": _default_to_json(default),
                "unexpanded": name in unexpanded_keys,
            }
        )
    return {
        "name": cls.__name__,
        "rates": [rate.token for rate in getattr(cls, "_valid_calculation_rates", ())],
        "flags": {
            "pure": bool(getattr(cls, "_is_pure", False)),
            "output": bool(getattr(cls, "_is_output", False)),
            "width_first": bool(getattr(cls, "_is_width_first", False)),
            "has_done_flag": bool(getattr(cls, "_has_done_flag", False)),
        },
        "parameters": parameters,
    }


def _operator_ugen_spec(cls: type[UGen], special_index_enum: str) -> dict[str, Any]:
    """Describe an operator UGen (``BinaryOpUGen`` / ``UnaryOpUGen``).

    These differ from ordinary UGens: they carry no rate constructors (the
    calculation rate is inferred from the inputs), and their ``special_index``
    is not zero but selects the operator from one of the enum tables. They are
    single-output and always pure.
    """
    return {
        "name": cls.__name__,
        "inputs": list(getattr(cls, "_ordered_keys", ())),
        "output_count": 1,
        "special_index_enum": special_index_enum,
        "flags": {"pure": bool(getattr(cls, "_is_pure", False))},
    }


def build_spec() -> dict[str, Any]:
    """Build the full spec dictionary from live introspection."""
    return {
        "spec_version": SPEC_VERSION,
        "supercollider_version": SUPERCOLLIDER_VERSION,
        "scgf_version": SCGF_VERSION,
        "enums": {
            "calculation_rates": {rate.token: int(rate) for rate in CalculationRate},
            "binary_operators": {op.name: int(op) for op in BinaryOperator},
            "unary_operators": {op.name: int(op) for op in UnaryOperator},
            "done_actions": {action.name: int(action) for action in DoneAction},
        },
        "operator_ugens": [
            _operator_ugen_spec(BinaryOpUGen, "binary_operators"),
            _operator_ugen_spec(UnaryOpUGen, "unary_operators"),
        ],
        "ugens": [_ugen_spec(cls) for cls in _ugen_classes()],
    }


def render(spec: dict[str, Any]) -> str:
    """Deterministic JSON text (trailing newline) for stable diffs."""
    return json.dumps(spec, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = render(build_spec())
    if "--check" in argv:
        if not SPEC_PATH.exists() or SPEC_PATH.read_text() != text:
            print(
                f"{SPEC_PATH} is stale. Run: python scripts/generate_ugen_spec.py",
                file=sys.stderr,
            )
            return 1
        print(f"{SPEC_PATH} is up to date.")
        return 0
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(text)
    print(f"Wrote {SPEC_PATH} ({len(build_spec()['ugens'])} UGens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
