"""The generated sc3-plugins wrappers (``nanosynth.ugens.sc3``) checked against sclang.

``spec/sc3-plugins-reference.json`` is sclang's wire contract for sc3-plugins'
UGens (``scripts/sc3_plugins_reference.py``); ``scripts/generate_sc3_ugens.py``
writes the module from it. Set NANOSYNTH_SC3_PLUGINS to a directory of built
sc3-plugins to also render one through the engine.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import wave
from pathlib import Path
from typing import Any

import pytest

from nanosynth.osc import OscMessage
from nanosynth.score import Score
from nanosynth.scsynth import Options, find_ugen_plugins_path
from nanosynth.synthdef import SynthDefBuilder, UGen
from nanosynth.ugens import DC, Out, Saw, sc3

ROOT = Path(__file__).resolve().parent.parent
REFERENCE: dict[str, Any] = json.loads(
    (ROOT / "spec" / "sc3-plugins-reference.json").read_text()
)
SKIPPED: dict[str, str] = json.loads(
    (ROOT / "spec" / "sc3-plugins-skipped.json").read_text()
)
ALLOWLIST: dict[str, dict[str, Any]] = json.loads(
    (ROOT / "tests" / "fixtures" / "sc3_reference_allowlist.json").read_text()
)


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_probe = _load("_ugen_probe", ROOT / "scripts" / "ugen_probe.py")
_sclang_reference = _load("_sclang_reference", ROOT / "scripts" / "sclang_reference.py")
_generator = _load("_gen_sc3", ROOT / "scripts" / "generate_sc3_ugens.py")
CLASSES: list[type[UGen]] = [getattr(sc3, name) for name in sc3.__all__]


def test_reference_matches_vendored_version() -> None:
    """sclang and sc3-plugins at the version of the vendored scsynth and its headers."""
    version = _sclang_reference.vendored_version()
    assert REFERENCE["sclang_version"] == version
    assert REFERENCE["sc3_plugins_version"] == version


@pytest.mark.skipif(shutil.which("ruff") is None, reason="generator formats with ruff")
def test_module_is_generated_from_the_reference() -> None:
    text, skipped = _generator.generate()
    assert (ROOT / "src" / "nanosynth" / "ugens" / "sc3.py").read_text() == text
    assert (ROOT / "spec" / "sc3-plugins-skipped.json").read_text() == skipped


def test_each_reference_class_is_generated_or_skipped_with_a_reason() -> None:
    generated = set(sc3.__all__)
    assert not generated & set(SKIPPED)
    assert generated | set(SKIPPED) == set(REFERENCE["ugens"])
    assert all(SKIPPED.values())


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_ugen_matches_sclang(cls: type[UGen]) -> None:
    entry = REFERENCE["ugens"][cls.__name__]
    ours = {r.token for r in cls._valid_calculation_rates}  # type: ignore[attr-defined]
    methods = {
        token: record
        for record in entry["methods"].values()
        if "rate" in record and (token := _probe.RATE_TOKENS[record["rate"]]) in ours
    }
    expected = ALLOWLIST.get(cls.__name__, {}).get("problems", [])
    assert sorted(_probe.problems(cls, {**entry, "methods": methods})) == sorted(
        expected
    )


def test_allowlist_names_wrapped_ugens_with_reasons() -> None:
    assert set(ALLOWLIST) <= set(sc3.__all__)
    assert all(entry.get("reason") for entry in ALLOWLIST.values())


def _inputs(build: Any, cls: type[UGen]) -> tuple[list[Any], int]:
    """The encoded inputs and output count of the last *cls* that *build* adds."""
    with SynthDefBuilder() as b:
        build()
    ugen = [u for u in b._ugens if type(u) is cls][-1]
    return [_probe._encode(x) for x in ugen._inputs], len(ugen)


def _codes(text: str) -> list[float]:
    return [float(ord(c)) for c in text]


# Real arguments, where the probe passes only placeholders: counts, strings and arrays.
@pytest.mark.parametrize(
    ("build", "cls", "inputs", "outputs"),
    [
        (
            lambda: sc3.FeatureSave.kr(features=[DC.kr(source=1)] * 3, trig=0),
            sc3.FeatureSave,
            [3.0, 0.0, "ugen:DC", "ugen:DC", "ugen:DC"],
            1,
        ),
        (
            lambda: sc3.MatchingPResynth.ar(
                dict_=1, trigger=0, activs=[4, 0.5, 9, 0.25]
            ),
            sc3.MatchingPResynth,
            [1.0, 0.0, 2.0, 0.0, 0.0, 4.0, 0.5, 9.0, 0.25],
            1,
        ),
        (
            lambda: sc3.Getenv.ir(key="HOME", defaultval=7),
            sc3.Getenv,
            [4.0, 7.0, *_codes("HOME")],
            1,
        ),
        (
            lambda: sc3.NovaDiskOut.ar(
                signal=[DC.ar(source=0), DC.ar(source=0)], filename="a.wav"
            ),
            sc3.NovaDiskOut,
            [2.0, "ugen:DC", "ugen:DC", 5.0, *_codes("a.wav")],
            1,
        ),
        (
            lambda: sc3.SOMRd.kr(bufnum=0, inputdata=[1, 2], numdims=3),
            sc3.SOMRd,
            [0.0, 10.0, 3.0, 1.0, 1.0, 2.0],
            3,
        ),
        (
            lambda: sc3.TextVU.kr(source=DC.kr(source=0), label="lv", width=10),
            sc3.TextVU,
            ["ugen:Impulse", "ugen:Amplitude", 10.0, 0.0, 2.0, *_codes("lv")],
            1,
        ),
        (
            lambda: sc3.StkInst.ar(inst_number=2, args=[1, 64]),
            sc3.StkInst,
            [220.0, 1.0, 1.0, 0.5, 2.0, 1.0, 64.0],
            1,
        ),
        (
            lambda: sc3.KMeansRT.kr(bufnum=0, inputdata=[0.1, 0.2, 0.3]),
            sc3.KMeansRT,
            [0.0, 5.0, 1.0, 0.0, 1.0, 0.1, 0.2, 0.3],
            1,
        ),
        (
            lambda: sc3.GrainBufJ.ar(sndbuf=3, channel_count=2),
            sc3.GrainBufJ,
            [0.0, 1.0, 3.0, 1.0, 0.0, 2.0, 0.0, -1.0, 512.0, 1.0, 0.0],
            2,
        ),
        (
            lambda: sc3.BMoog.ar(source=DC.ar(source=0)),
            sc3.BMoog,
            ["ugen:DC", 440.0, 0.2, 0.0],
            1,
        ),
    ],
    ids=lambda x: x.__name__ if isinstance(x, type) else None,
)
def test_computed_inputs(
    build: Any, cls: type[UGen], inputs: list[Any], outputs: int
) -> None:
    ours, count = _inputs(build, cls)
    assert ours == [x if isinstance(x, str) else pytest.approx(x) for x in inputs]
    assert count == outputs


def test_textvu_returns_its_source() -> None:
    with SynthDefBuilder():
        source = DC.kr(source=0)
        assert sc3.TextVU.kr(source=source) is source


@pytest.mark.skipif(
    not os.environ.get("NANOSYNTH_SC3_PLUGINS"), reason="NANOSYNTH_SC3_PLUGINS not set"
)
def test_each_wrapped_ugen_is_registered_by_a_plugin() -> None:
    """Each name is a NUL-terminated string in some plugin: what DefineUnit registers."""
    plugins = Path(os.environ["NANOSYNTH_SC3_PLUGINS"])
    blobs = [so.read_bytes() for so in plugins.glob("*.so")]
    missing = [
        n
        for n in sc3.__all__
        if n != "NovaDiskOut"  # NovaDiskIO is off in a default sc3-plugins build
        and not any(n.encode() + b"\0" in b for b in blobs)
    ]
    assert missing == []


@pytest.mark.skipif(
    not os.environ.get("NANOSYNTH_SC3_PLUGINS"), reason="NANOSYNTH_SC3_PLUGINS not set"
)
def test_dfm1_renders_through_sc3_plugins(tmp_path: Path) -> None:
    core = find_ugen_plugins_path()
    assert core is not None
    with SynthDefBuilder() as b:
        Out.ar(bus=0, source=sc3.DFM1.ar(source=Saw.ar(frequency=110), freq=800))
    sd = b.build(name="dfm1")
    path = tmp_path / "out.wav"
    score = Score()
    score.add_synthdef(0.0, sd)
    score.add_synth(0.0, sd.effective_name)
    score.add(0.2, OscMessage("/c_set", 0, 0))
    plugins = f"{core}:{os.environ['NANOSYNTH_SC3_PLUGINS']}"
    score.render(
        path,
        output_channels=1,
        options=Options(verbosity=-1, ugen_plugins_path=plugins),
    )
    with wave.open(str(path)) as w:
        raw = w.readframes(w.getnframes())
    peak = max(
        abs(int.from_bytes(raw[i : i + 2], "little", signed=True))
        for i in range(0, len(raw), 2)
    )
    assert peak / 32768 > 0.05
