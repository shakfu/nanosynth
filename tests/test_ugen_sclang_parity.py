"""UGen metadata checked against sclang 3.14.1 and the plugin sources.

Each case here was a mismatch found by scanning the plugin C++ for output
writes and input reads beyond nanosynth's declared counts, then confirmed in
the SuperCollider 3.14.1 class library (``SCClassLibrary/Common/Audio``). See
``docs/dev/ugen-metadata-audit.md``.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import pytest

from nanosynth.enums import CalculationRate
from nanosynth.osc import OscMessage
from nanosynth.score import Score
from nanosynth.scsynth import Options
from nanosynth.synthdef import SynthDef, SynthDefBuilder
from nanosynth.ugens import (
    DC,
    FFT,
    BufDelayN,
    Demand,
    Dseries,
    Dunique,
    Duty,
    Dwhite,
    Impulse,
    Delay1,
    Delay2,
    LocalBuf,
    Out,
    PanB,
    SinOsc,
    SpecPcile,
    Vibrato,
    WhiteNoise,
)


def _only(sd: SynthDef, cls: type) -> object:
    (ugen,) = [u for u in sd._ugens if type(u) is cls]
    return ugen


# (UGen, inputs, outputs) per sclang 3.14.1 *ar/*kr and init.
@pytest.mark.parametrize(
    ("build", "cls", "inputs", "outputs"),
    [
        (lambda: PanB.ar(source=SinOsc.ar()), PanB, 4, 4),
        (lambda: Delay1.ar(source=SinOsc.ar()), Delay1, 2, 1),
        (lambda: Delay2.ar(source=SinOsc.ar()), Delay2, 3, 1),
        (lambda: Vibrato.ar(), Vibrato, 9, 1),
        (
            lambda: SpecPcile.kr(
                pv_chain=FFT.kr(buffer_id=LocalBuf.ir(), source=WhiteNoise.ar())
            ),
            SpecPcile,
            4,
            1,
        ),
    ],
    ids=["PanB", "Delay1", "Delay2", "Vibrato", "SpecPcile"],
)
def test_arity_matches_sclang(build, cls, inputs, outputs) -> None:
    with SynthDefBuilder() as b:
        sig = build()
        Out.kr(bus=0, source=sig) if cls is SpecPcile else Out.ar(bus=0, source=sig)
    ugen = _only(b.build(name="arity"), cls)
    assert len(ugen._inputs) == inputs
    assert ugen._channel_count == outputs


def test_delay1_initial_state_defaults_follow_sclang() -> None:
    """x1 defaults to 0 at audio rate and to the input at control rate."""
    with SynthDefBuilder() as b:
        src = DC.kr(source=0.5)
        Out.ar(bus=0, source=Delay1.ar(source=SinOsc.ar()))
        Out.kr(bus=0, source=Delay1.kr(source=src))
    sd = b.build(name="d1")
    by_rate = {u.calculation_rate: u for u in sd._ugens if type(u) is Delay1}
    ar, kr = by_rate[CalculationRate.AUDIO], by_rate[CalculationRate.CONTROL]
    assert ar._inputs[1] == 0.0
    assert kr._inputs[1] is kr._inputs[0]


def _render(
    sd: SynthDef, tmp_path: Path, channels: int, seconds: float = 0.05
) -> list[list[float]]:
    """NRT-render *sd* from time 0; return per-channel samples in [-1, 1]."""
    path = tmp_path / "out.wav"
    score = Score()
    score.add_synthdef(0.0, sd)
    score.add_synth(0.0, sd.effective_name)
    score.add(seconds, OscMessage("/c_set", 0, 0))
    score.render(path, output_channels=channels, options=Options(verbosity=-1))
    with wave.open(str(path)) as w:
        raw = w.readframes(w.getnframes())
    samples = [
        int.from_bytes(raw[i : i + 2], "little", signed=True) / 32768
        for i in range(0, len(raw), 2)
    ]
    return [samples[c::channels] for c in range(channels)]


def test_panb_z_channel_is_rendered(tmp_path: Path) -> None:
    """All four B-format channels carry signal; Z was dropped with 3 outputs.

    PanB_next scales elevation by a quarter sine table, so 0.5 is pi/4.
    """
    elevation = 0.5
    with SynthDefBuilder() as b:
        Out.ar(
            bus=0,
            source=PanB.ar(source=DC.ar(source=0.5), azimuth=0.0, elevation=elevation),
        )
    w, x, y, z = _render(b.build(name="panb4"), tmp_path, channels=4)
    n = 150  # past the first block, after any level ramp
    angle = elevation * math.pi / 2
    assert w[n] == pytest.approx(0.5 / math.sqrt(2), abs=1e-3)
    assert x[n] == pytest.approx(0.5 * math.cos(angle), abs=1e-3)
    assert y[n] == pytest.approx(0.0, abs=1e-3)
    assert z[n] == pytest.approx(0.5 * math.sin(angle), abs=1e-3)


def test_delay1_starts_from_x1(tmp_path: Path) -> None:
    with SynthDefBuilder() as b:
        Out.ar(bus=0, source=Delay1.ar(source=DC.ar(source=0.5), x1=0.25))
    (out,) = _render(b.build(name="d1x"), tmp_path, channels=1)
    assert out[:3] == pytest.approx([0.25, 0.5, 0.5], abs=1e-3)


def test_delay2_starts_from_x2_then_x1(tmp_path: Path) -> None:
    with SynthDefBuilder() as b:
        Out.ar(bus=0, source=Delay2.ar(source=DC.ar(source=0.5), x1=0.25, x2=-0.25))
    (out,) = _render(b.build(name="d2x"), tmp_path, channels=1)
    assert out[:4] == pytest.approx([-0.25, 0.25, 0.5, 0.5], abs=1e-3)


def test_duty_and_dwhite_follow_plugin_input_order(tmp_path: Path) -> None:
    """Dwhite reads length from IN(0); Duty reads doneAction before level.

    With the old orders, Dwhite got length=0.25 and Duty read level from the
    done_action slot, so the output was 0.
    """
    with SynthDefBuilder() as b:
        level = Dwhite.dr(minimum=0.25, maximum=0.25)
        Out.ar(bus=0, source=Duty.ar(duration=0.001, level=level))
    (out,) = _render(b.build(name="duty"), tmp_path, channels=1)
    assert out[200:220] == pytest.approx([0.25] * 20, abs=1e-3)


def test_bufdelay_reads_delay_time(tmp_path: Path) -> None:
    """BufDelayN reads delay time from IN(2); a max-delay slot there delayed by 0.2 s."""
    with SynthDefBuilder() as b:
        buf = LocalBuf.ir(frame_count=8192)
        Out.ar(
            bus=0,
            source=BufDelayN.ar(
                buffer_id=buf, source=DC.ar(source=0.5), delay_time=0.001
            ),
        )
    (out,) = _render(b.build(name="bufdelay"), tmp_path, channels=1)
    assert out[500:520] == pytest.approx([0.5] * 20, abs=1e-3)


def test_binary_operators_render_their_operation(tmp_path: Path) -> None:
    """Indices from MINIMUM on were 2 high: min_ ran as bitwise AND (output 0)."""
    with SynthDefBuilder() as b:
        a, c = DC.ar(source=0.1), DC.ar(source=0.2)
        Out.ar(bus=0, source=[a.min_(c), a.max_(c), a**2, a.first_arg(c)])
    outs = _render(b.build(name="ops"), tmp_path, channels=4)
    assert [ch[300] for ch in outs] == pytest.approx([0.1, 0.2, 0.01, 0.1], abs=1e-3)


@pytest.mark.parametrize("protected", [True, False])
def test_dunique_readers_share_one_stream(tmp_path: Path, protected: bool) -> None:
    """Both readers get 0.01, 0.02, ...; two uses of one Dseries interleave it."""
    with SynthDefBuilder() as b:
        unique = Dunique(source=Dseries.dr(start=0.01, step=0.01), protected=protected)
        trigger = Impulse.ar(frequency=441)  # every 100 samples at 44.1 kHz
        Out.ar(
            bus=0, source=Demand.ar(trigger=trigger, reset=0, source=[unique, unique])
        )
    left, right = _render(b.build(name="dunique"), tmp_path, channels=2)
    expected = [0.01, 0.02, 0.03, 0.04]
    assert [left[i] for i in (50, 150, 250, 350)] == pytest.approx(expected, abs=1e-3)
    assert [right[i] for i in (50, 150, 250, 350)] == pytest.approx(expected, abs=1e-3)
