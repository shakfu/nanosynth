"""Probe a nanosynth UGen class as scripts/sclang_reference.scd probes sclang, and compare.

Shared by tests/test_ugen_reference.py and scripts/generate_sc3_ugens.py.
"""

from __future__ import annotations

import inspect
import math
from typing import Any

from nanosynth.envelopes import Envelope
from nanosynth.synthdef import OutputProxy, SynthDefBuilder, UGen
from nanosynth.ugens import DC

RATE_TOKENS = {"audio": "ar", "control": "kr", "scalar": "ir", "demand": "dr"}

# Structured arguments, mirroring `overrides` in sclang_reference.scd.
OVERRIDES: dict[str, Any] = {
    "envelope": Envelope(amplitudes=[0, 1, 0], durations=[1, 1]),
    "frequencies": [100],  # Klank, Klang: sclang gets `[[100], [1], [1]]
    "label": "x",
}


def _substitute(rate: str) -> Any:
    if rate == "ar":
        return DC.ar(source=0.5)
    if rate == "kr":
        return DC.kr(source=0.5)
    return 0.5


def _encode(x: Any) -> Any:
    if isinstance(x, OutputProxy):
        return "ugen:" + type(x.ugen).__name__
    x = float(x)
    return "inf" if x == math.inf else "-inf" if x == -math.inf else x


def _same(ours: Any, theirs: Any) -> bool:
    if isinstance(ours, str) or isinstance(theirs, str):
        return bool(ours == theirs)
    # The reference stores 9 significant digits; SCgf stores float32.
    return math.isclose(ours, theirs, rel_tol=1e-6, abs_tol=1e-6)


def _probe(
    cls: type[UGen], token: str, record: dict[str, Any]
) -> tuple[UGen, set[str]]:
    """Build *cls* at *token* like the sclang probe; return it and substituted keys."""
    method = getattr(cls, token)
    params = [
        p
        for p in inspect.signature(method).parameters.values()
        if p.kind in (p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    sub_rate = (
        record["substitute_rate"]
        if record["substitute_rate"] in ("ar", "kr")
        else token
    )
    unexpanded = getattr(cls, "_unexpanded_keys", frozenset())
    with SynthDefBuilder() as builder:
        kwargs: dict[str, Any] = {}
        substituted: set[str] = set()
        for i, p in enumerate(params):
            if p.name in OVERRIDES:
                kwargs[p.name] = OVERRIDES[p.name]
            elif p.name == "channel_count":
                kwargs[p.name] = record["outputs"]
            elif p.default is inspect.Parameter.empty or (
                record.get("substitute_first") and i == 0
            ):
                value = _substitute(sub_rate)
                kwargs[p.name] = [value] if p.name in unexpanded else value
                substituted.add(p.name)
        method(**kwargs)
        ugen = [u for u in builder._ugens if type(u) is cls][-1]
    return ugen, substituted


def problems(cls: type[UGen], entry: dict[str, Any] | None) -> list[str]:
    """How *cls* differs from its sclang reference *entry*; empty if it matches."""
    if entry is None:
        return ["absent from sclang"]
    by_rate = {
        RATE_TOKENS[m["rate"]]: m for m in entry["methods"].values() if "rate" in m
    }
    if not by_rate:
        emits = sorted(
            {e for m in entry["methods"].values() for e in m.get("emits", [])}
        )
        return [f"pseudo-UGen in sclang, emits {emits}"]
    ours = {r.token for r in getattr(cls, "_valid_calculation_rates", ())} or {
        t for t in RATE_TOKENS.values() if hasattr(cls, t)
    }
    problems = []
    if ours != set(by_rate):
        problems.append(f"rates ours={sorted(ours)} sclang={sorted(by_rate)}")
    for token in sorted(ours & set(by_rate)):
        record = by_rate[token]
        ugen, substituted = _probe(cls, token, record)
        if len(ugen) != record["outputs"]:
            problems.append(
                f"{token}: outputs ours={len(ugen)} sclang={record['outputs']}"
            )
        if ugen._special_index != record["special_index"]:
            problems.append(
                f"{token}: special_index ours={ugen._special_index} "
                f"sclang={record['special_index']}"
            )
        inputs = [_encode(x) for x in ugen._inputs]
        theirs = record["inputs"]
        if len(inputs) != len(theirs):
            problems.append(f"{token}: inputs ours={inputs} sclang={theirs}")
            continue
        for i, (x, y) in enumerate(zip(inputs, theirs)):
            key = ugen._input_keys[i]
            name = key if isinstance(key, str) else key[0]
            # A UGen on either side is a required argument with no default
            # there; a default on the other side is not a contract error.
            if name in substituted or isinstance(y, str) and y.startswith("ugen:"):
                continue
            if not _same(x, y):
                problems.append(f"{token}: input {i} ({name}) ours={x} sclang={y}")
    return problems
