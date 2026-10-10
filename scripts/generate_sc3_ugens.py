#!/usr/bin/env python3
"""Generate src/nanosynth/ugens/sc3.py from spec/sc3-plugins-reference.json.

Each sc3-plugins UGen becomes a class whose parameters follow the sclang method's
arguments: camelCase becomes snake_case and ``in`` becomes ``source``. A class
is written only if scripts/ugen_probe.py finds it identical to sclang, input
by input, at every rate it keeps. The rest are listed with a reason in
spec/sc3-plugins-skipped.json.

Usage::

    python scripts/generate_sc3_ugens.py          # write both files
    python scripts/generate_sc3_ugens.py --check  # exit 1 if either is out of date
"""

from __future__ import annotations

import importlib.util
import json
import keyword
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

from nanosynth.synthdef import UGen
from nanosynth.ugens import sc3_custom

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_PATH = ROOT / "spec" / "sc3-plugins-reference.json"
MODULE_PATH = ROOT / "src" / "nanosynth" / "ugens" / "sc3.py"
SKIPPED_PATH = ROOT / "spec" / "sc3-plugins-skipped.json"
# differences from sclang that are probe artifacts or deliberate, each with a reason
ALLOWLIST: dict[str, dict[str, Any]] = json.loads(
    (ROOT / "tests" / "fixtures" / "sc3_reference_allowlist.json").read_text()
)
HAND_WRITTEN = set(sc3_custom.__all__)

_spec = importlib.util.spec_from_file_location(
    "_ugen_probe", ROOT / "scripts" / "ugen_probe.py"
)
assert _spec is not None and _spec.loader is not None
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

RATE_ORDER = ["ar", "kr", "ir", "dr"]
# an argument with one of these names that sclang does not send is the number of outputs
CHANNEL_ARGS = {"numChannels", "numChans"}
# names the generated __init__ and rate methods use, UGen attributes a parameter would hide,
# and `l`, which ruff rejects as ambiguous (E741)
RESERVED = {"self", "cls", "calculation_rate", "channel_count", "kwargs", "l"} | set(
    dir(UGen)
)
# Classes whose sclang method sends its arguments in another order, drops one, or sends
# mul and add as inputs: the arguments in the order sent. `*name` is an array sent as its
# elements; `*name?` is one that may be empty, as sclang's `nil.asArray` is.
WIRE_ORDER = {
    "BMoog": [
        "in",
        "freq",
        "q",
        "mode",
    ],  # sclang takes `saturation` and never sends it
    "BufGrainBBF": [
        "trigger",
        "dur",
        "sndbuf",
        "rate",
        "pos",
        "interp",
        "envbuf",
        "azimuth",
        "elevation",
        "rho",
        "wComp",
    ],
    "BufGrainBF": [
        "trigger",
        "dur",
        "sndbuf",
        "rate",
        "pos",
        "interp",
        "azimuth",
        "elevation",
        "rho",
        "wComp",
    ],
    "BufGrainI": [
        "trigger",
        "dur",
        "sndbuf",
        "rate",
        "pos",
        "interp",
        "envbuf1",
        "envbuf2",
        "ifac",
    ],
    "BufGrainIBF": [
        "trigger",
        "dur",
        "sndbuf",
        "rate",
        "pos",
        "interp",
        "envbuf1",
        "envbuf2",
        "ifac",
        "azimuth",
        "elevation",
        "rho",
        "wComp",
    ],
    "Dbrown2": ["length", "lo", "hi", "step", "dist"],
    "Dgauss": ["length", "lo", "hi"],
    "GrainBufJ": [
        "trigger",
        "dur",
        "sndbuf",
        "rate",
        "pos",
        "interp",
        "pan",
        "envbufnum",
        "maxGrains",
        "grainAmp",
        "loop",
    ],
    "GrainFMJ": [
        "trigger",
        "dur",
        "carfreq",
        "modfreq",
        "index",
        "pan",
        "envbufnum",
        "maxGrains",
        "grainAmp",
    ],
    "GrainInJ": ["trigger", "dur", "in", "pan", "envbufnum", "maxGrains", "grainAmp"],
    "GrainSinJ": [
        "trigger",
        "dur",
        "freq",
        "pan",
        "envbufnum",
        "maxGrains",
        "grainAmp",
    ],
    "KMeansRT": ["bufnum", "k", "gate", "reset", "learn", "*inputdata"],
    "PV_BinPlayBuf": [
        "buffer",
        "playbuf",
        "rate",
        "offset",
        "loop",
        "binStart",
        "binSkip",
        "numBins",
        "clear",
    ],
    "PV_MagMulAdd": ["buffer", "mul", "add"],
    "PermModArray": ["in", "freq", "*pattern"],
    "SOMAreaWr": [
        "bufnum",
        "netsize",
        "numdims",
        "nhood",
        "gate",
        "*inputdata",
        "*coords",
    ],
    "SOMTrain": [
        "bufnum",
        "netsize",
        "numdims",
        "traindur",
        "nhood",
        "gate",
        "initweight",
        "*inputdata",
    ],
    "StkInst": ["freq", "gate", "onamp", "offamp", "instNumber", "*args?"],
}


def py_name(arg: str) -> str:
    if arg == "in":
        return "source"
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", arg).lower()
    return name + "_" if keyword.iskeyword(name) or name in RESERVED else name


def literal(x: Any) -> str:
    if x in ("inf", "-inf", "nan"):
        return f'float("{x}")'
    return repr(x)


def by_rate(entry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Rate token -> the sclang record that builds the UGen at that rate."""
    out: dict[str, dict[str, Any]] = {}
    for record in entry["methods"].values():
        if "rate" in record:
            out.setdefault(probe.RATE_TOKENS[record["rate"]], record)
    return out


def channel_arg(record: dict[str, Any]) -> str | None:
    """The argument that sets the output count rather than being sent, if there is one."""
    args = [a["name"] for a in record["args"] if a["name"] not in ("mul", "add")]
    found = [a for a in args if a in CHANNEL_ARGS]
    return (
        found[0] if len(found) == 1 and len(record["inputs"]) == len(args) - 1 else None
    )


def array_default(text: Any) -> Any:
    """An sclang array literal such as `[1,0]` as a tuple, else None."""
    if not isinstance(text, str) or not text.strip().startswith("["):
        return None
    try:
        return tuple(json.loads(text))
    except ValueError:
        return None


def arguments(name: str, record: dict[str, Any]) -> list[tuple[str, Any, bool]]:
    """(sclang name, default or None, is an array) per input, in the order sent."""
    if name in WIRE_ORDER:
        declared = {a["name"]: a.get("default") for a in record["args"]}
        out = []
        for item in WIRE_ORDER[name]:
            arg = item.strip("*?")
            default = declared[arg]
            if item.startswith("*"):
                default = () if item.endswith("?") else array_default(default)
            elif isinstance(default, str) and default not in ("inf", "-inf", "nan"):
                default = None
            out.append((arg, default, item.startswith("*")))
        return out
    skip = {"mul", "add", channel_arg(record)}
    args = [a for a in record["args"] if a["name"] not in skip]
    inputs = record["inputs"]
    out = []
    for i, a in enumerate(args):
        default = a.get("default")
        # A default sclang computes, such as `SampleRate.ir`, is kept only if it came out a number.
        if isinstance(default, str) and default not in ("inf", "-inf", "nan"):
            number = len(inputs) == len(args) and not isinstance(inputs[i], str)
            default = inputs[i] if number else None
        out.append((a["name"], default, False))
    return out


def class_source(name: str, entry: dict[str, Any], tokens: list[str]) -> str:
    record = by_rate(entry)[tokens[0]]
    chain = entry.get("superclasses", [])
    flags = [f"{t}=True" for t in tokens]
    outputs = record["outputs"]
    if channel_arg(record):
        flags += ["is_multichannel=True", f"channel_count={outputs}"]
    elif outputs == 0:
        flags += ["is_output=True", "channel_count=0", "fixed_channel_count=True"]
    elif outputs > 1:
        flags += [f"channel_count={outputs}", "fixed_channel_count=True"]
    if "WidthFirstUGen" in chain:
        flags.append("is_width_first=True")
    if "PureUGen" in chain or "PureMultiOutUGen" in chain:
        flags.append("is_pure=True")
    base = "PV_ChainUGen" if "PV_ChainUGen" in chain else "UGen"
    lines = [f"@ugen({', '.join(flags)})", f"class {name}({base}):"]
    for arg, default, array in arguments(name, record):
        value = "" if default is None else literal(default)
        if array:
            value += ", unexpanded=True" if value else "unexpanded=True"
        lines.append(f"    {py_name(arg)} = param({value})")
    if len(lines) == 2:
        lines.append("    pass")
    return "\n".join(lines) + "\n"


def candidate(name: str, entry: dict[str, Any]) -> tuple[list[str], str]:
    """The rates whose sclang arguments and outputs match the first rate's, or a reason."""
    records = by_rate(entry)
    if not entry["has_unit"]:
        return [], "no unit in sc3-plugins' C++ sources: the class is sclang only"
    if not records:
        errors = sorted({m["error"] for m in entry["methods"].values() if "error" in m})
        if errors:
            return [], "sclang could not build it: " + errors[0].splitlines()[0]
        emits = sorted(
            {e for m in entry["methods"].values() for e in m.get("emits", [])}
        )
        return (
            [],
            f"pseudo-UGen: sclang code that builds {', '.join(emits) or 'nothing'}",
        )
    tokens = [t for t in RATE_ORDER if t in records]
    first = records[tokens[0]]
    shape = ([a for a, _, _ in arguments(name, first)], first["outputs"])
    tokens = [
        t
        for t in tokens
        if ([a for a, _, _ in arguments(name, records[t])], records[t]["outputs"])
        == shape
    ]
    names = [py_name(a) for a in shape[0]]
    if len(set(names)) != len(names):
        return [], "two arguments map to one Python name"
    return tokens, ""


def check(
    name: str, entry: dict[str, Any], tokens: list[str], namespace: dict[str, Any]
) -> list[str]:
    exec(class_source(name, entry, tokens), namespace)
    cls = namespace[name]
    try:
        found = probe.problems(
            cls, {**entry, "methods": {t: by_rate(entry)[t] for t in tokens}}
        )
    except Exception as exc:  # the probe's arguments do not suit this class
        return [f"nanosynth cannot build it: {type(exc).__name__}: {exc}"]
    return list(found)


def generate() -> tuple[str, str]:
    reference = json.loads(REFERENCE_PATH.read_text())
    module = types.ModuleType("nanosynth.ugens._sc3_candidates")
    module.__package__ = "nanosynth.ugens"
    namespace = module.__dict__
    exec(
        "from ..synthdef import UGen, param, ugen\nfrom .pv import PV_ChainUGen\n",
        namespace,
    )
    kept: dict[str, list[tuple[str, str]]] = {}
    skipped: dict[str, str] = {}
    for name, entry in sorted(reference["ugens"].items()):
        if name in HAND_WRITTEN:
            continue
        tokens, reason = candidate(name, entry)
        if tokens:
            found = check(name, entry, tokens, namespace)
            # drop the rates that differ and try once more with the rest
            bad = {p.split(":")[0] for p in found if p.split(":")[0] in tokens}
            if found and bad and len(bad) < len(tokens):
                tokens = [t for t in tokens if t not in bad]
                found = check(name, entry, tokens, namespace)
            if found and sorted(found) != sorted(
                ALLOWLIST.get(name, {}).get("problems", [])
            ):
                tokens, reason = [], "differs from sclang: " + "; ".join(found)
        if tokens:
            kept.setdefault(entry["library"], []).append(
                (name, class_source(name, entry, tokens))
            )
        else:
            skipped[name] = reason
    count = sum(len(v) for v in kept.values())
    header = f'''"""sc3-plugins UGens, generated by scripts/generate_sc3_ugens.py. Do not edit.

Generated from spec/sc3-plugins-reference.json (sc3-plugins {reference["sc3_plugins_version"]},
sclang {reference["sclang_version"]}). {count + len(HAND_WRITTEN)} UGens, {len(HAND_WRITTEN)} of them hand-written in ``sc3_custom``;
the classes left out, and why, are in
spec/sc3-plugins-skipped.json. Parameters follow the sclang arguments: camelCase becomes
snake_case and ``in`` becomes ``source``.

A SynthDef using these needs a server with sc3-plugins installed.
"""

from ..synthdef import UGen, param, ugen
from .pv import PV_ChainUGen
from .sc3_custom import {", ".join(sorted(HAND_WRITTEN))}

'''
    body = []
    for library in sorted(kept):
        body.append(f"# --- {library}\n")
        body.extend(f"\n{src}\n" for _, src in kept[library])
    names = sorted(
        [n for classes in kept.values() for n, _ in classes] + list(HAND_WRITTEN)
    )
    footer = "\n__all__ = [\n" + "".join(f'    "{n}",\n' for n in names) + "]\n"
    text = header + "\n".join(body).rstrip() + "\n\n" + footer
    # formatted as `make format` would, so that it leaves the file alone
    ruff = shutil.which("ruff") or "ruff"
    text = subprocess.run(
        [ruff, "format", "--stdin-filename", str(MODULE_PATH), "-"],
        input=text,
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout
    return text, json.dumps(skipped, indent=1, sort_keys=True) + "\n"


def main() -> int:
    text, skipped = generate()
    if "--check" in sys.argv[1:]:
        current = MODULE_PATH.exists() and MODULE_PATH.read_text() == text
        current = (
            current and SKIPPED_PATH.exists() and SKIPPED_PATH.read_text() == skipped
        )
        if not current:
            print("out of date: run scripts/generate_sc3_ugens.py", file=sys.stderr)
        return 0 if current else 1
    MODULE_PATH.write_text(text)
    SKIPPED_PATH.write_text(skipped)
    print(
        f"Wrote {MODULE_PATH} and {SKIPPED_PATH} ({len(json.loads(skipped))} skipped)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
