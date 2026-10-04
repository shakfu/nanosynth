"""Static scan of the plugin C++ against declared UGen input and output counts.

For each ``<UGen>_next*`` and ``<UGen>_Ctor`` function in
``thirdparty/supercollider/server/plugins``, the highest literal ``OUT(n)`` or
``IN(n)`` index must be below the counts in ``spec/nanosynth-ugens.json``.
Functions that read ``mNumInputs``/``mNumOutputs`` compute their bounds, so
they are skipped. This catches the ``DiskOut``/``PanB`` class of error (a
write past the declared outputs); ``test_ugen_reference.py`` checks the rest.
The operator enums are checked against the plugin enums the same way.
See ``docs/dev/ugen-metadata-audit.md``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "thirdparty" / "supercollider" / "server" / "plugins"
SPEC = {
    u["name"]: u
    for u in json.loads((ROOT / "spec" / "nanosynth-ugens.json").read_text())["ugens"]
}

COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
FUNCTION = re.compile(r"\bvoid\s+(\w+?)_(next\w*|Ctor)\s*\([^)]*\)\s*\{")
ACCESS = re.compile(r"\b(Z?OUT0?|Z?IN0?|INRATE)\s*\(\s*(\d+)\s*\)")

# Verified false positives: function -> reason.
ALLOWED = {
    "NumRunningSynths_Ctor": "INRATE(0) with no inputs; sclang also sends none. Upstream bug.",
}

# Implemented as C++ structs or never sent to the server.
UNSCANNED = {"DC", "K2A", "MulAdd", "PV_ChainUGen", "Sum3", "Sum4"}


def _functions() -> Iterator[tuple[str, str, str]]:
    """Yield (ugen name, function name, body) per plugin function, comments removed."""
    for path in sorted(PLUGINS.glob("*.cpp")):
        text = COMMENT.sub("", path.read_text(errors="replace"))
        for match in FUNCTION.finditer(text):
            depth, i = 1, match.end()
            while depth:
                depth += {"{": 1, "}": -1}.get(text[i], 0)
                i += 1
            name = match.group(1)
            yield name, f"{name}_{match.group(2)}", text[match.end() : i]


def scan(spec: dict[str, dict[str, Any]]) -> tuple[list[str], set[str]]:
    """Return (violations, names of spec UGens with at least one function)."""
    violations: list[str] = []
    seen: set[str] = set()
    for name, function, body in _functions():
        ugen = spec.get(name)
        if ugen is None or function in ALLOWED:
            continue
        seen.add(name)
        params = ugen["parameters"]
        fixed_inputs = not any(p["unexpanded"] for p in params)
        outputs = ugen["outputs"]
        for kind, index in ((k, int(i)) for k, i in ACCESS.findall(body)):
            if "OUT" in kind:
                if (
                    outputs["kind"] == "fixed"
                    and index >= outputs["count"]
                    and "mNumOutputs" not in body
                ):
                    violations.append(
                        f"{function}: {kind}({index}), declares {outputs['count']} outputs"
                    )
            elif fixed_inputs and index >= len(params) and "mNumInputs" not in body:
                violations.append(
                    f"{function}: {kind}({index}), declares {len(params)} inputs"
                )
    return sorted(set(violations)), seen


def test_plugins_stay_within_declared_counts() -> None:
    violations, _ = scan(SPEC)
    assert violations == []


def test_scan_covers_every_ugen() -> None:
    _, seen = scan(SPEC)
    assert set(SPEC) - seen == UNSCANNED


def test_scan_catches_past_metadata_errors() -> None:
    """The DiskOut and PanB declarations that crashed the engine must fail the scan."""
    spec = json.loads(json.dumps(SPEC))
    spec["DiskOut"]["outputs"]["count"] = 0
    spec["PanB"]["outputs"]["count"] = 3
    spec["Vibrato"]["parameters"].pop()
    violations, _ = scan(spec)
    assert any(v.startswith("DiskOut_next") for v in violations)
    assert any(v.startswith("PanB_next") and "OUT(3)" in v for v in violations)
    assert any(v.startswith("Vibrato_") for v in violations)


# nanosynth operator name -> plugin enum name (BinaryOpUGens.cpp, UnaryOpUGens.cpp).
BINARY_NAMES = {
    "ADDITION": "opAdd",
    "SUBTRACTION": "opSub",
    "MULTIPLICATION": "opMul",
    "INTEGER_DIVISION": "opIDiv",
    "FLOAT_DIVISION": "opFDiv",
    "MODULO": "opMod",
    "EQUAL": "opEQ",
    "NOT_EQUAL": "opNE",
    "LESS_THAN": "opLT",
    "GREATER_THAN": "opGT",
    "LESS_THAN_OR_EQUAL": "opLE",
    "GREATER_THAN_OR_EQUAL": "opGE",
    "MINIMUM": "opMin",
    "MAXIMUM": "opMax",
    "BITWISE_AND": "opBitAnd",
    "BITWISE_OR": "opBitOr",
    "BITWISE_XOR": "opBitXor",
    "LCM": "opLCM",
    "GCD": "opGCD",
    "ROUND": "opRound",
    "ROUND_UP": "opRoundUp",
    "TRUNCATION": "opTrunc",
    "ATAN2": "opAtan2",
    "HYPOT": "opHypot",
    "HYPOTX": "opHypotx",
    "POWER": "opPow",
    "SHIFT_LEFT": "opShiftLeft",
    "SHIFT_RIGHT": "opShiftRight",
    "RING1": "opRing1",
    "RING2": "opRing2",
    "RING3": "opRing3",
    "RING4": "opRing4",
    "DIFFERENCE_OF_SQUARES": "opDifSqr",
    "SUM_OF_SQUARES": "opSumSqr",
    "SQUARE_OF_SUM": "opSqrSum",
    "SQUARE_OF_DIFFERENCE": "opSqrDif",
    "ABSOLUTE_DIFFERENCE": "opAbsDif",
    "THRESHOLD": "opThresh",
    "AMPLITUDE_CLIPPING": "opAMClip",
    "SCALE_NEGATIVE": "opScaleNeg",
    "CLIP2": "opClip2",
    "EXCESS": "opExcess",
    "FOLD2": "opFold2",
    "WRAP2": "opWrap2",
    "FIRST_ARG": "opFirstArg",
}

UNARY_NAMES = {
    "NEGATIVE": "opNeg",
    "BIT_NOT": "opBitNot",
    "ABSOLUTE_VALUE": "opAbs",
    "CEILING": "opCeil",
    "FLOOR": "opFloor",
    "FRACTIONAL_PART": "opFrac",
    "SIGN": "opSign",
    "SQUARED": "opSquared",
    "CUBED": "opCubed",
    "SQUARE_ROOT": "opSqrt",
    "EXPONENTIAL": "opExp",
    "RECIPROCAL": "opRecip",
    "MIDICPS": "opMIDICPS",
    "CPSMIDI": "opCPSMIDI",
    "MIDIRATIO": "opMIDIRatio",
    "RATIOMIDI": "opRatioMIDI",
    "DBAMP": "opDbAmp",
    "AMPDB": "opAmpDb",
    "OCTCPS": "opOctCPS",
    "CPSOCT": "opCPSOct",
    "LOG": "opLog",
    "LOG2": "opLog2",
    "LOG10": "opLog10",
    "SIN": "opSin",
    "COS": "opCos",
    "TAN": "opTan",
    "ARCSIN": "opArcSin",
    "ARCCOS": "opArcCos",
    "ARCTAN": "opArcTan",
    "SINH": "opSinH",
    "COSH": "opCosH",
    "TANH": "opTanH",
    "DISTORT": "opDistort",
    "SOFTCLIP": "opSoftClip",
}


def _plugin_enum(filename: str) -> dict[str, int]:
    """Indices of the first anonymous enum in a plugin file, comments removed."""
    text = COMMENT.sub("", (PLUGINS / filename).read_text())
    body = text[
        text.index("enum {") + len("enum {") : text.index("};", text.index("enum {"))
    ]
    return {
        name.strip(): i
        for i, name in enumerate(n for n in body.split(",") if n.strip())
    }


def test_binary_operator_indices_match_plugin() -> None:
    from nanosynth.enums import BinaryOperator

    plugin = _plugin_enum("BinaryOpUGens.cpp")
    assert {op.name: int(op) for op in BinaryOperator} == {
        name: plugin[cpp] for name, cpp in BINARY_NAMES.items()
    }


def test_unary_operator_indices_match_plugin() -> None:
    from nanosynth.enums import UnaryOperator

    plugin = _plugin_enum("UnaryOpUGens.cpp")
    assert {op.name: int(op) for op in UnaryOperator} == {
        name: plugin[cpp] for name, cpp in UNARY_NAMES.items()
    }
