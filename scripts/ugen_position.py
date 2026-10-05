#!/usr/bin/env python3
"""Compare nanosynth's UGen metadata with sclang and the engine.

Joins four sources per UGen and rate:

- ``spec/nanosynth-ugens.json``: nanosynth's own metadata.
- ``spec/sclang-reference.json``: sclang 3.14.1 metadata, extracted by
  ``scripts/sclang_reference.scd`` and normalized by ``import-reference``.
- ``build/ugen-sweep.json``: engine load/render results from
  ``scripts/ugen_sweep.py``.
- A comment-aware scan of the vendored plugin C++ for output writes and
  input reads beyond the declared counts.

Writes ``build/ugen-position.json``. See ``docs/dev/ugen-metadata-audit.md``.

Usage::

    python scripts/ugen_position.py import-reference RAW.json
    python scripts/ugen_position.py report
"""

from __future__ import annotations

import collections
import glob
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "spec" / "sclang-reference.json"
SPEC = ROOT / "spec" / "nanosynth-ugens.json"
SWEEP = ROOT / "build" / "ugen-sweep.json"
OUT = ROOT / "build" / "ugen-position.json"
PLUGINS = ROOT / "thirdparty" / "supercollider" / "server" / "plugins"

RATE_OF = {"audio": "ar", "control": "kr", "scalar": "ir", "demand": "dr"}

# Findings verified by hand as artifacts of the extraction, by UGen. The
# extractor tracks numeric and UGen arguments only, so a symbol, string or
# array argument leaves no tagged input slot and shifts the comparison.
ALLOWED: dict[str, tuple[set[str], str]] = {
    "Onsets": (
        {"order", "default", "input_count"},
        "odftype is a symbol in sclang (\\rcomplex -> 3); order matches",
    ),
    "Poll": (
        {"input_count"},
        "label is a string; trig, in, trigid, label-size, chars as in sclang",
    ),
    "SendReply": (
        {"order", "input_count"},
        "cmdName is a string; order matches sclang",
    ),
    "SendPeakRMS": (
        {"order", "input_count"},
        "cmdName is a string; order matches sclang",
    ),
    "Klank": ({"input_count"}, "specifications are a Ref array; order matches sclang"),
    "LocalBuf": (
        {"input_count", "name"},
        "numChannels is held at its default; order (channels, frames) matches",
    ),
    "DecodeB2": (
        {"input_count"},
        "orientation arrives as a constant; C++ reads it as IN(3), as nanosynth sends",
    ),
    "MaxLocalBufs": ({"input_count"}, "internal; created by the graph, not by users"),
    "LinRand": ({"name"}, "minmax renamed skew; same slot"),
    "EnvGen": (
        {"missing_rate"},
        "nanosynth's EnvGen.ar/kr are custom class methods the spec does not list",
    ),
    "Dstutter": (
        {"extra_rate"},
        "sclang *new maps to kr in this report; demand rate in both",
    ),
    "Dunique": (
        {"extra_rate"},
        "sclang *new maps to kr in this report; demand rate in both",
    ),
    "Dwrand": (
        {"extra_rate"},
        "sclang *new maps to kr in this report; demand rate in both",
    ),
    "Sum3": ({"missing_rate"}, "optimizer output, not user-constructed"),
    "Sum4": ({"missing_rate"}, "optimizer output, not user-constructed"),
    "PV_ChainUGen": ({"not_in_sclang"}, "abstract base class, never emitted"),
}
SKIP_ARGS = {"mul", "add"}


# ---------------------------------------------------------------------------
# import-reference: resolve expression defaults from the .sc source
# ---------------------------------------------------------------------------


def _arg_declaration(source: str, pos: int) -> str:
    """The text of a method's argument declaration (``arg ...;`` or ``|...|``)."""
    body = source.index("{", pos) + 1
    rest = re.sub(r"^(\s|//[^\n]*\n)*", "", source[body:])
    if rest.startswith("arg"):
        return rest[3 : rest.index(";")]
    if rest.startswith("|"):
        return rest[1 : rest.index("|", 1)]
    return ""


def _split_top(text: str) -> list[str]:
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _resolve(expr: str, names: set[str]) -> Any:
    """A numeric value for simple sclang default expressions, else the text."""
    e = expr.strip()
    while e.startswith("(") and e.endswith(")") and e[1:-1].strip() not in names:
        e = e[1:-1].strip()
    if e.startswith("(") and e.endswith(")"):
        e = e[1:-1].strip()
    if e in names:
        return {"ref": e}
    table = {"inf": math.inf, "-inf": -math.inf, "pi": math.pi, "-pi": -math.pi}
    if e in table:
        return table[e]
    m = re.fullmatch(r"(-?[\d.]+)\s*\.midicps", e)
    if m:
        return 440.0 * 2 ** ((float(m.group(1)) - 69) / 12)
    m = re.fullmatch(r"(-?[\d.]*)pi", e)
    if m:
        return float(m.group(1) or 1) * math.pi
    try:
        return float(e)
    except ValueError:
        return {"expr": e}


def import_reference(raw_path: str) -> None:
    raw = json.loads(Path(raw_path).read_text())
    sources: dict[str, str] = {}
    for rec in raw["records"]:
        path = rec.pop("file", "")
        pos = rec.pop("char_pos", None)
        rel = path.split("SCClassLibrary/", 1)[-1]
        rec["source"] = f"SCClassLibrary/{rel}"
        if pos is None or not path:
            continue
        if path not in sources:
            sources[path] = Path(path).read_text(errors="replace")
        decl = _arg_declaration(sources[path], pos)
        exprs: dict[str, str] = {}
        for part in _split_top(decl):
            name, _, expr = part.lstrip(".").partition("=")
            exprs[name.strip()] = expr.strip()
        names = {a["name"] for a in rec["args"]}
        for arg in rec["args"]:
            expr = exprs.get(arg["name"], "")
            if expr and arg.get("default") is None:
                arg["default"] = _resolve(expr, names)
            if expr:
                arg["default_source"] = expr
    REFERENCE.write_text(json.dumps(raw, indent=1, sort_keys=True) + "\n")
    print(f"Wrote {REFERENCE} ({len(raw['records'])} records)")


# ---------------------------------------------------------------------------
# Static scan of plugin C++ (comments stripped)
# ---------------------------------------------------------------------------

_FN = re.compile(
    r"^(?:static\s+|FLATTEN\s+|inline\s+)*void\s+([A-Z]\w*?)_(?:next|Ctor)\w*\s*\([^)]*\)\s*\{",
    re.M,
)
_OUT = re.compile(r"\b(?:Z?OUT0?|OUTRATE)\((\d+)\)")
_IN = re.compile(r"\b(?:Z?IN0?|INRATE|IN_AT|INBUFLENGTH)\((\d+)\)")


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def plugin_scan() -> dict[str, dict[str, int]]:
    found: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"out": -1, "in": -1}
    )
    for path in glob.glob(str(PLUGINS / "*.cpp")):
        src = _strip_comments(Path(path).read_text(errors="replace"))
        for m in _FN.finditer(src):
            depth, i = 1, m.end()
            while depth and i < len(src):
                depth += {"{": 1, "}": -1}.get(src[i], 0)
                i += 1
            body = src[m.end() : i]
            rec = found[m.group(1)]
            rec["out"] = max([rec["out"], *map(int, _OUT.findall(body))])
            rec["in"] = max([rec["in"], *map(int, _IN.findall(body))])
            if "mNumInputs" in body:
                rec["guarded"] = 1
    return dict(found)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _norm(name: str) -> str:
    n = name.lower().replace("_", "")
    for a, b in (
        ("frequency", "freq"),
        ("bufferid", "buf"),
        ("bufnum", "buf"),
        ("buffer", "buf"),
        ("trigger", "trig"),
        ("source", "in"),
        ("input", "in"),
        ("channelcount", "numchannels"),
        ("interpolation", "interp"),
        ("maximum", "max"),
        ("minimum", "min"),
        ("delaytime", "deltime"),
        ("decaytime", "decaytime"),
    ):
        n = n.replace(a, b)
    return n


# sclang argument name -> nanosynth parameter names it may be renamed to.
# Built from the renames in nanosynth's UGen classes; each was checked against
# the class definition. Matching is after _norm on both sides.
SYNONYMS: dict[str, set[str]] = {
    "lo": {"minimum"},
    "hi": {"maximum"},
    "minval": {"minimum"},
    "maxval": {"maximum"},
    "buffer": {"pvchain", "bufferid"},
    "chain": {"pvchain"},
    "buffera": {"pvchaina"},
    "bufferb": {"pvchainb"},
    "dur": {"duration"},
    "iphase": {"initialphase"},
    "phase": {"initialphase", "phase"},
    "rq": {"reciprocalofq"},
    "rs": {"reciprocalofs"},
    "channelsarray": {"source"},
    "inputarray": {"source"},
    "src": {"source"},
    "demandugens": {"source"},
    "list": {"sequence"},
    "array": {"sources", "sequence"},
    "pos": {"position"},
    "pan": {"position"},
    "coef": {"coefficient"},
    "damp": {"damping"},
    "ampdist": {"amplitudedistribution"},
    "durdist": {"durationdistribution"},
    "adparam": {"amplitudeparameter"},
    "ddparam": {"durationparameter"},
    "ampscale": {"amplitudescale"},
    "durscale": {"durationscale"},
    "lagtimeu": {"lagtimeup"},
    "lagtimed": {"lagtimedown"},
    "end": {"stop"},
    "g": {"gravity"},
    "chaosparam": {"chaosparameter"},
    "bufpos": {"bufferid"},
    "sndbuf": {"bufferid"},
    "db": {"gain"},
    "wintype": {"windowtype"},
    "winsize": {"windowsize"},
    "envbufnum": {"envelopebufferid"},
    "bw": {"bandwidth"},
    "numharm": {"harmoniccount"},
    "id": {"ugenid", "nodeid", "randid"},
    "post": {"postmode"},
    "prob": {"probability"},
    "interp": {"interpolate", "interpolation"},
    "maxgrains": {"maximumoverlap"},
    "srclo": {"inputminimum"},
    "srchi": {"inputmaximum"},
    "dstlo": {"outputminimum"},
    "dsthi": {"outputmaximum"},
    "init": {"initialy"},
    "xpos": {"xposition"},
    "ypos": {"yposition"},
    "level": {"gain", "amplitude", "level"},
    "startpos": {"startposition"},
    "reclevel": {"recordlevel"},
    "prelevel": {"preexistinglevel"},
    "numsamp": {"samplecount"},
    "scopenum": {"scopeid"},
    "which": {"selector"},
    "dn": {"down"},
    "xfade": {"crossfade"},
    "numfeatures": {"featurecount"},
    "thresh": {"threshold"},
    "amp": {"threshold", "amplitude"},
    "room": {"roomsize"},
    "suslevel": {"sustainlevel"},
    "initfreq": {"initialfrequency"},
    "ampthreshold": {"amplitudethreshold"},
    "downsample": {"downsamplefactor"},
    "clar": {"clarity"},
    "freqscale": {"frequencyscaling", "frequencyscale"},
    "in": {"source", "trigger"},
    "gate": {"trigger", "gate"},
    "floor": {"floor"},
    "values": {"source"},
    "sig": {"source"},
}


def _equivalent(sc_name: str, nano_name: str) -> bool:
    a, b = _norm(sc_name), _norm(nano_name)
    return a == b or b in {_norm(x) for x in SYNONYMS.get(sc_name.lower(), ())}


def _input_args(rec: dict[str, Any]) -> list[str]:
    """sclang argument names in input-slot order, collapsing array runs."""
    seq: list[str] = []
    for slot in rec.get("inputs", []):
        name = slot.get("arg")
        if name and (not seq or seq[-1] != name):
            seq.append(name)
    return seq


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-4, abs_tol=1e-6) or (
            math.isinf(a) and a == b
        )
    return a == b


def report() -> None:
    spec = {u["name"]: u for u in json.loads(SPEC.read_text())["ugens"]}
    ref_records = json.loads(REFERENCE.read_text())["records"]
    sweep = json.loads(SWEEP.read_text()) if SWEEP.exists() else []
    scan = plugin_scan()

    ref: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    for rec in ref_records:
        if rec["status"] == "ok":
            rate = RATE_OF.get(rec.get("rate", ""), rec["selector"])
        else:
            rate = {"new": "kr"}.get(rec["selector"], rec["selector"])
        ref[rec["class"]].setdefault(rate, rec)
    sweep_by = {(c["ugen"], c["rate"]): c for c in sweep}

    findings: list[dict[str, Any]] = []

    def add(ugen: str, rate: str | None, kind: str, detail: str) -> None:
        findings.append({"ugen": ugen, "rate": rate, "kind": kind, "detail": detail})

    for name, u in sorted(spec.items()):
        if name not in ref:
            add(name, None, "not_in_sclang", "no sclang 3.14.1 class of this name")
            continue
        sc_rates = set(ref[name])
        for rate in sorted(set(u["rates"]) - sc_rates):
            add(name, rate, "extra_rate", f"sclang has {sorted(sc_rates)}")
        for rate in sorted(sc_rates - set(u["rates"])):
            if ref[name][rate]["status"] == "ok":
                add(name, rate, "missing_rate", f"nanosynth has {u['rates']}")
        for rate in u["rates"]:
            rec = ref[name].get(rate)
            if rec is None:
                continue
            if rec["status"] == "pseudo":
                add(
                    name,
                    rate,
                    "pseudo_in_sclang",
                    f"sclang expands to {rec.get('expands_to')}",
                )
                continue
            if rec["status"] != "ok":
                continue
            # Outputs.
            out = u["outputs"]
            if out["kind"] == "fixed" and out["count"] != rec["num_outputs"]:
                add(
                    name,
                    rate,
                    "outputs",
                    f"nanosynth {out['count']}, sclang {rec['num_outputs']}",
                )
            # Input order, names and defaults.
            sc_args = {a["name"]: a for a in rec["args"]}
            sc_order = [a for a in _input_args(rec) if a not in SKIP_ARGS]
            nano = u["parameters"]
            if len(sc_order) != len(nano):
                add(
                    name,
                    rate,
                    "input_count",
                    f"nanosynth {[p['name'] for p in nano]} vs sclang {sc_order}",
                )
            for i, (p, sc_name) in enumerate(zip(nano, sc_order)):
                elsewhere = [
                    k
                    for k, q in enumerate(nano)
                    if k != i and _equivalent(sc_name, q["name"])
                ]
                if _equivalent(sc_name, p["name"]):
                    pass
                elif elsewhere:
                    add(
                        name,
                        rate,
                        "order",
                        f"slot {i}: sclang {sc_name!r} is nanosynth "
                        f"{nano[elsewhere[0]]['name']!r} at slot {elsewhere[0]}; "
                        f"nanosynth sends {p['name']!r} there",
                    )
                else:
                    add(
                        name,
                        rate,
                        "name",
                        f"slot {i}: nanosynth {p['name']!r}, sclang {sc_name!r}",
                    )
                if not _equivalent(sc_name, p["name"]):
                    continue  # defaults of different arguments are not comparable
                sd = sc_args[sc_name].get("default")
                nd = p["default"]
                if (
                    isinstance(sd, (int, float))
                    and isinstance(nd, (int, float))
                    and not _same(sd, nd)
                ):
                    add(
                        name,
                        rate,
                        "default",
                        f"{p['name']}: nanosynth {nd}, sclang {sd}",
                    )
                elif isinstance(sd, (int, float)) and nd == "required":
                    add(
                        name,
                        rate,
                        "default_missing",
                        f"{p['name']}: sclang default {sd}",
                    )
            # Rate rules nanosynth does not enforce.
            for sc_name in rec.get("requires_audio") or []:
                if sc_name in sc_order:
                    i = sc_order.index(sc_name)
                    pname = nano[i]["name"] if i < len(nano) else sc_name
                    add(name, rate, "unenforced_audio_input", pname)
        # Engine sweep.
        for rate in u["rates"]:
            case = sweep_by.get((name, rate))
            if case and case["status"] != "ok":
                add(name, rate, f"engine_{case['status']}", case["detail"])
        # Static scan.
        s = scan.get(name)
        if (
            s
            and u["outputs"]["kind"] == "fixed"
            and s["out"] + 1 > u["outputs"]["count"]
        ):
            add(
                name,
                None,
                "scan_outputs",
                f"C++ writes OUT({s['out']}), declared {u['outputs']['count']}",
            )
        if (
            s
            and not any(p["unexpanded"] for p in u["parameters"])
            and not s.get("guarded")
        ):
            if s["in"] + 1 > len(u["parameters"]):
                add(
                    name,
                    None,
                    "scan_inputs",
                    f"C++ reads IN({s['in']}), declared {len(u['parameters'])}",
                )

    for cls in sorted(set(ref) - set(spec)):
        statuses = {r["status"] for r in ref[cls].values()}
        add(cls, None, "missing_ugen", "pseudo" if statuses == {"pseudo"} else "unit")

    for f in findings:
        kinds, reason = ALLOWED.get(f["ugen"], (set(), ""))
        if f["kind"] in kinds:
            f["allowed"] = reason
    allowed = [f for f in findings if "allowed" in f]
    findings = [f for f in findings if "allowed" not in f]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps({"findings": findings, "allowed": allowed}, indent=1) + "\n"
    )
    print(f"{len(allowed)} findings allowlisted as extraction artifacts")
    counts = collections.Counter(f["kind"] for f in findings)
    ugens = collections.defaultdict(set)
    for f in findings:
        ugens[f["kind"]].add(f["ugen"])
    print(f"{len(findings)} findings -> {OUT}")
    for kind, n in counts.most_common():
        print(f"  {kind:26} {n:4} findings, {len(ugens[kind]):3} UGens")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "import-reference":
        import_reference(sys.argv[2])
    elif sys.argv[1:] == ["report"]:
        report()
    else:
        sys.exit(__doc__)
