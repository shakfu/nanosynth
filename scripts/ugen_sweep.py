#!/usr/bin/env python3
"""Load and render every nanosynth UGen in the embedded engine (NRT).

For each UGen and each rate it supports, build a SynthDef with default inputs
(required inputs get a recipe keyed by parameter name), then NRT-render it in
its own subprocess so a crash only loses that case. Each case is classified:

    build_error    nanosynth could not construct or compile it
    not_installed  scsynth rejected the SynthDef ("UGen 'X' not installed")
    engine_error   scsynth printed another error during the render
    crash          the render process died on a signal
    timeout        the render did not finish
    nonfinite      the output contains NaN or inf
    ok             none of the above

Writes ``build/ugen-sweep.json``. Part of the UGen audit; see
``docs/dev/ugen-metadata-audit.md``.

Usage::

    python scripts/ugen_sweep.py                 # all UGens
    python scripts/ugen_sweep.py SinOsc PanB     # selected UGens
    python scripts/ugen_sweep.py --render CASE   # (internal) render one case
"""

from __future__ import annotations

import inspect
import json
import struct
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "ugen-sweep.json"
RATES = ("ar", "kr", "ir", "dr")
RENDER_SECONDS = 0.1
# Optional text arguments (labels, OSC addresses); None means "generate one".
TEXT_PARAMS = frozenset({"label", "command_name"})
TIMEOUT = 30


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def _signal(rate: str) -> Any:
    from nanosynth.ugens import DC, Dseq, SinOsc

    if rate == "ar":
        return SinOsc.ar(frequency=220.0) * 0.1
    if rate == "kr":
        return SinOsc.kr(frequency=1.0) * 0.1
    if rate == "dr":
        return Dseq.dr(sequence=[1, 2, 3], repeats=float("inf"))
    return DC.ir(source=0.5) if hasattr(DC, "ir") else 0.5


def _recipe(name: str, rate: str) -> Any:
    """A plausible value for a required parameter, keyed by its name."""
    from nanosynth.ugens import FFT, Impulse, LocalBuf, WhiteNoise

    if name == "envelope":
        from nanosynth.envelopes import Envelope

        return Envelope.percussive()
    if name.startswith("pv_chain"):
        return FFT.kr(buffer_id=LocalBuf.ir(frame_count=2048), source=WhiteNoise.ar())
    if name == "kernel" and rate == "ar":  # Convolution: an audio-rate kernel signal
        return _signal(rate)
    if name in {"buffer_id", "kernel"}:
        return LocalBuf.ir(frame_count=2048)
    if name in {"trigger", "gate", "reset"}:
        return (
            Impulse.kr(frequency=10.0) if rate != "ar" else Impulse.ar(frequency=10.0)
        )
    if name in {"frequencies", "amplitudes", "decay_times"}:  # Klank, DynKlank, ...
        return [400.0, 800.0]
    if name in {"sequence", "array", "weights", "character", "sources"}:
        return [1.0, 2.0, 3.0]
    if name in {"node_id"}:
        return 99999.0
    if name in {
        "source",
        "in_a",
        "in_b",
        "left",
        "right",
        "x",
        "y",
        "w",
    } or name.startswith("input_"):
        return _signal(rate)
    return 1.0


def _wrap(sig: Any, rate: str) -> None:
    from nanosynth.ugens import K2A, Duty, Out

    if rate == "dr":
        Out.ar(bus=0, source=Duty.ar(duration=0.01, level=sig))
    elif rate == "ar":
        Out.ar(bus=0, source=sig)
    else:
        Out.ar(bus=0, source=K2A.ar(source=sig))


def ugen_classes() -> dict[str, type]:
    from nanosynth import envelopes, ugens

    spec = json.loads((ROOT / "spec" / "nanosynth-ugens.json").read_text())
    found = {}
    for entry in spec["ugens"]:
        cls = getattr(ugens, entry["name"], None) or getattr(
            envelopes, entry["name"], None
        )
        if cls is not None:
            found[entry["name"]] = cls
    return found


def build_case(name: str, cls: type, rate: str) -> bytes:
    """Compile a SynthDef exercising *cls* at *rate*. Raises on failure."""
    from nanosynth.synthdef import SynthDefBuilder

    method = getattr(cls, rate)
    with SynthDefBuilder() as builder:
        kwargs = {}
        for pname, p in inspect.signature(method).parameters.items():
            required = p.default is inspect.Parameter.empty or (
                p.default is None and pname not in TEXT_PARAMS
            )
            if p.kind is inspect.Parameter.KEYWORD_ONLY and required:
                kwargs[pname] = _recipe(pname, rate)
            elif pname == "channel_count" and p.default is not inspect.Parameter.empty:
                kwargs[pname] = 1
        sig = method(**kwargs)
        has_outputs = not getattr(cls, "_is_output", False) and sig is not None
        try:
            has_outputs = has_outputs and len(sig) > 0  # type: ignore[arg-type]
        except TypeError:
            pass
        if has_outputs:
            _wrap(sig, rate)
    return builder.build(name="sweep").compile()


# ---------------------------------------------------------------------------
# Rendering (child process)
# ---------------------------------------------------------------------------


def render_case(def_path: str) -> None:
    from nanosynth.osc import OscMessage
    from nanosynth.score import Score
    from nanosynth.scsynth import Options

    data = Path(def_path).read_bytes()
    wav = def_path + ".wav"
    score = Score()
    score.add(0.0, OscMessage("/d_recv", data))
    score.add(0.0, OscMessage("/s_new", "sweep", 1000, 0, 0))
    score.add(RENDER_SECONDS, OscMessage("/c_set", 0, 0))
    score.render(
        wav, sample_format="float", output_channels=2, options=Options(verbosity=0)
    )
    print(f"RENDERED {wav}", flush=True)


def _nonfinite(wav: Path) -> bool:
    raw = wav.read_bytes()
    i = raw.find(b"data")
    if i < 0:
        return False
    size = struct.unpack("<I", raw[i + 4 : i + 8])[0]
    floats = struct.unpack(f"<{size // 4}f", raw[i + 8 : i + 8 + size - size % 4])
    return any(f != f or f in (float("inf"), float("-inf")) for f in floats)


def classify(def_path: Path) -> tuple[str, str]:
    try:
        proc = subprocess.run(
            [sys.executable, __file__, "--render", str(def_path)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return "timeout", ""
    out = proc.stdout + proc.stderr
    if proc.returncode < 0:
        return "crash", f"signal {-proc.returncode}"
    if "not installed" in out:
        line = next(ln for ln in out.splitlines() if "not installed" in ln)
        return "not_installed", line.strip()
    errors = [
        ln.strip()
        for ln in out.splitlines()
        if ("ERROR" in ln or "FAILURE" in ln or "exception" in ln.lower())
        and "open directory failed" not in ln
    ]
    if proc.returncode != 0 or "RENDERED" not in out:
        return "engine_error", (errors or out.strip().splitlines()[-1:] or [""])[0]
    if errors:
        return "engine_error", errors[0]
    if _nonfinite(Path(str(def_path) + ".wav")):
        return "nonfinite", ""
    return "ok", ""


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main(names: list[str]) -> None:
    classes = ugen_classes()
    if names:
        classes = {n: classes[n] for n in names}
    tmp = Path(tempfile.mkdtemp(prefix="ugen-sweep-"))
    cases: list[dict[str, Any]] = []
    for name, cls in sorted(classes.items()):
        for rate in RATES:
            if not hasattr(cls, rate):
                continue
            case: dict[str, Any] = {"ugen": name, "rate": rate}
            try:
                path = tmp / f"{name}.{rate}.scsyndef"
                path.write_bytes(build_case(name, cls, rate))
                case["path"] = path
            except Exception as exc:  # noqa: BLE001 -- record any build failure
                case["status"], case["detail"] = (
                    "build_error",
                    f"{type(exc).__name__}: {exc}",
                )
            cases.append(case)

    todo = [c for c in cases if "path" in c]
    with ThreadPoolExecutor(max_workers=16) as pool:
        for case, (status, detail) in zip(
            todo, pool.map(lambda c: classify(c["path"]), todo)
        ):
            case["status"], case["detail"] = status, detail
    for case in cases:
        case.pop("path", None)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(cases, indent=1) + "\n")
    counts: dict[str, int] = {}
    for case in cases:
        counts[case["status"]] = counts.get(case["status"], 0) + 1
    print(f"{len(classes)} UGens, {len(cases)} cases -> {OUT}")
    for status, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {status:14} {n}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--render":
        render_case(sys.argv[2])
    else:
        main(sys.argv[1:])
