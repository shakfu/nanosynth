#!/usr/bin/env python3
"""Compilation corpus: compare nanosynth graphs with sclang by rendered audio.

Each case builds the same graph as the case of the same name in
``scripts/compile_corpus.scd``, with every argument explicit. Both SynthDefs
render through the embedded engine (NRT, 32-bit float) and the samples are
compared. Comparing audio rather than SCgf bytes tolerates legitimate
differences in graph optimization.

Usage::

    sclang -l sclang_conf.yaml scripts/compile_corpus.scd SCLANG_DIR/
    python scripts/compile_corpus.py SCLANG_DIR/

Writes ``build/compile-corpus.json``. ``duty_positive_control`` uses a UGen
whose input order is known to be wrong, so it must report DIFFERENT; if it
does not, the comparison is broken. See ``docs/dev/ugen-metadata-audit.md``.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from nanosynth import ugens as U
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import SynthDefBuilder

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "compile-corpus.json"
TOLERANCE = 1e-4
SECONDS = 0.25


def sin(f: float, phase: float = 0.0):  # noqa: ANN201
    return U.SinOsc.ar(frequency=f, phase=phase)


def env(e: Envelope, gate=1, scale=1, bias=0, time=1):  # noqa: ANN001, ANN201
    return EnvGen.ar(
        envelope=e,
        gate=gate,
        level_scale=scale,
        level_bias=bias,
        time_scale=time,
        done_action=0,
    )


def case_arith() -> None:
    s = sin(220)
    U.Out.ar(
        bus=0, source=[s * 0.5 + 0.1, (s - 0.2) / 2 * U.SinOsc.kr(frequency=3, phase=0)]
    )


def case_unary() -> None:
    s = sin(220)
    U.Out.ar(
        bus=0,
        source=[
            abs(s) * 0.3 + (-s) * 0.2 + s.squared() * 0.1 + s.cubed() * 0.1,
            abs(s).sqrt_() * 0.2
            + (s * 3).tanh_() * 0.2
            + s.distort() * 0.2
            + (s * 2).softclip() * 0.2
            + (s + 2).reciprocal() * 0.1
            + s.sign() * 0.05,
        ],
    )


def case_binary() -> None:
    s, t = sin(220), sin(3.7) * 0.8
    U.Out.ar(
        bus=0,
        source=[
            s.min_(t) * 0.2
            + s.max_(t) * 0.2
            + (abs(s) ** 1.5) * 0.2
            + (s % 0.3)
            + s.round_(0.25) * 0.2
            + s.trunc(0.25) * 0.1,
            s.atan2(t) * 0.1
            + s.hypot(t) * 0.2
            + s.thresh(0.3) * 0.2
            + s.clip2(0.5) * 0.2
            + (s * 2).fold2(0.7) * 0.2
            + (s * 2).wrap2(0.6) * 0.1
            + s.ring1(t) * 0.1
            + s.amclip(t) * 0.1
            + s.scaleneg(0.5) * 0.1
            + s.absdif(t) * 0.1
            + s.sqrsum(t) * 0.05
            + s.difsqr(t) * 0.05
            + s.excess(0.3) * 0.1,
        ],
    )


def case_compare() -> None:
    s, t = sin(220), sin(3.7) * 0.8
    U.Out.ar(
        bus=0,
        source=[(s > t) * 0.2 + (s < 0.1) * 0.2, (s >= t) * 0.1 + (s <= 0.0) * 0.1],
    )


def case_folding() -> None:
    s, t = sin(2 * 110), sin(3.7)
    U.Out.ar(bus=0, source=[s * 1 + 0, s * (2 + 3) * 0.1 + (s * 0) + t * 0.1])


def case_conversions() -> None:
    f = (U.SinOsc.kr(frequency=1, phase=0) * 12 + 60).midicps()
    a = (U.SinOsc.kr(frequency=2, phase=0) * -10 - 10).dbamp()
    db6 = 10 ** (-6 / 20)
    U.Out.ar(
        bus=0, source=[U.SinOsc.ar(frequency=f, phase=0) * 0.2, sin(330) * a * db6]
    )


def case_multichannel() -> None:
    panned = U.Pan2.ar(
        source=U.SinOsc.ar(frequency=[220, 330], phase=0),
        position=[-0.5, 0.5],
        level=0.3,
    )
    U.Out.ar(bus=0, source=U.Mix.new(sources=panned))


def case_mix_sizes() -> None:
    def mix(freqs: list[float]):  # noqa: ANN202
        return U.Mix.new(sources=U.SinOsc.ar(frequency=freqs, phase=0))

    U.Out.ar(
        bus=0,
        source=[
            mix([100, 200, 300]) * 0.1 + mix([110, 220, 330, 440]) * 0.1,
            mix([i * 100 for i in range(1, 10)]) * 0.05
            + mix([150, 250, 350, 450, 550]) * 0.05,
        ],
    )


def case_env_perc() -> None:
    e = Envelope.percussive(attack_time=0.01, release_time=0.1, amplitude=1, curve=-4)
    U.Out.ar(bus=0, source=env(e) * sin(440))


def case_env_adsr_release() -> None:
    gate = U.Line.kr(start=1, stop=-1, duration=0.2, done_action=0) > 0
    e = Envelope.adsr(
        attack_time=0.01,
        decay_time=0.03,
        sustain=0.5,
        release_time=0.05,
        peak=1,
        curve=-4,
        bias=0,
    )
    U.Out.ar(bus=0, source=env(e, gate=gate) * sin(440))


def case_env_curves() -> None:
    e1 = Envelope(
        [0, 1, 0.3, 0.8, 0], [0.03, 0.04, 0.05, 0.06], ["sine", "welch", -3, "step"]
    )
    e2 = Envelope([0.01, 1, 0.01], [0.05, 0.1], ["exponential", "exponential"])
    U.Out.ar(bus=0, source=[env(e1), env(e2)])


def case_env_scaled() -> None:
    e1 = Envelope.linen(
        attack_time=0.02, sustain_time=0.05, release_time=0.03, level=0.8, curve=1
    )
    e2 = Envelope.triangle(duration=0.1, amplitude=0.9)
    U.Out.ar(bus=0, source=[env(e1, scale=0.5, bias=0.1, time=1.5), env(e2, time=0.5)])


def case_controls(b: SynthDefBuilder) -> None:
    U.Out.ar(bus=0, source=U.SinOsc.ar(frequency=b["freq"], phase=0) * b["amp"])


def case_demand() -> None:
    trig = U.Impulse.ar(frequency=100, phase=0)
    inner = U.Dseq.dr(sequence=[0.3, 0.4], repeats=2)
    U.Out.ar(
        bus=0,
        source=[
            U.Demand.ar(
                trigger=trig,
                reset=0,
                source=U.Dseq.dr(sequence=[0.1, 0.2, inner], repeats=float("inf")),
            ),
            U.Demand.ar(
                trigger=trig,
                reset=0,
                source=U.Dseries.dr(start=0, step=0.01, length=float("inf")),
            ),
        ],
    )


def case_duty_positive_control() -> None:
    seq = U.Dseq.dr(sequence=[0.1, 0.2, 0.3], repeats=float("inf"))
    U.Out.ar(bus=0, source=U.Duty.ar(duration=0.005, reset=0, level=seq, done_action=0))


def case_fft() -> None:
    chain = U.FFT.kr(
        buffer_id=U.LocalBuf.ir(frame_count=2048, channel_count=1),
        source=sin(440) + sin(3000),
        hop=0.5,
        window_type=0,
        active=1,
        window_size=0,
    )
    walled = U.PV_BrickWall.kr(pv_chain=chain, wipe=0.2)
    U.Out.ar(
        bus=0, source=U.IFFT.ar(pv_chain=walled, window_type=0, window_size=0) * 0.3
    )


def case_feedback() -> None:
    sig = sin(220) * 0.1 + U.LocalIn.ar(channel_count=1, default=0) * 0.5
    U.LocalOut.ar(source=sig)
    U.Out.ar(bus=0, source=sig)


def case_delays() -> None:
    imp = U.Impulse.ar(frequency=20, phase=0)
    U.Out.ar(
        bus=0,
        source=[
            U.CombN.ar(
                source=imp, maximum_delay_time=0.05, delay_time=0.013, decay_time=0.2
            )
            + U.AllpassN.ar(
                source=imp, maximum_delay_time=0.05, delay_time=0.007, decay_time=0.1
            ),
            U.DelayL.ar(source=sin(330), maximum_delay_time=0.05, delay_time=0.0123),
        ],
    )


def case_filters() -> None:
    cutoff = U.SinOsc.kr(frequency=2, phase=0) * 400 + 800
    U.Out.ar(
        bus=0,
        source=[
            U.RLPF.ar(
                source=U.Pulse.ar(frequency=110, width=0.3),
                frequency=cutoff,
                reciprocal_of_q=0.3,
            )
            * 0.3,
            U.MoogFF.ar(
                source=U.LFSaw.ar(frequency=110, initial_phase=0),
                frequency=1200,
                gain=2,
                reset=0,
            )
            * 0.3
            + U.BLowPass.ar(
                source=U.LFTri.ar(frequency=220, initial_phase=0),
                frequency=900,
                reciprocal_of_q=0.7,
            )
            * 0.3,
        ],
    )


def case_panners() -> None:
    s, t = sin(300), sin(450)
    pan = U.Pan2.ar(source=s, position=U.SinOsc.kr(frequency=1, phase=0), level=0.5)
    bal = U.Balance2.ar(left=s, right=t, position=0.3, level=0.5)
    az = U.PanAz.ar(
        channel_count=4, source=t, position=0.2, amplitude=0.5, width=2, orientation=0.5
    )
    U.Out.ar(bus=0, source=[pan[0] + bal[0] + az[0], pan[1] + bal[1] + az[1]])


def case_select_clip() -> None:
    s = sin(220) * 2
    which = U.LFSaw.kr(frequency=2, initial_phase=0) * 1.5 + 1.5
    choices = [
        sin(220),
        U.LFTri.ar(frequency=330, initial_phase=0),
        U.Pulse.ar(frequency=440, width=0.5),
    ]
    U.Out.ar(
        bus=0,
        source=[
            U.Select.ar(selector=which, sources=choices) * 0.3,
            U.Clip.ar(source=s, minimum=-0.5, maximum=0.5) * 0.3
            + U.Wrap.ar(source=s, minimum=-0.4, maximum=0.4) * 0.3
            + U.Fold.ar(source=s, minimum=-0.6, maximum=0.6) * 0.3,
        ],
    )


def case_triggers() -> None:
    def imp(f: float):  # noqa: ANN202
        return U.Impulse.ar(frequency=f, phase=0)

    pulse = U.Pulse.ar(frequency=30, width=0.5)
    U.Out.ar(
        bus=0,
        source=[
            U.Trig1.ar(source=imp(10), duration=0.01) * 0.2
            + U.Latch.ar(source=sin(3), trigger=imp(50)) * 0.2
            + U.Phasor.ar(trigger=imp(4), rate=0.001, start=0, stop=1, reset_pos=0)
            * 0.2,
            U.Sweep.ar(trigger=imp(4), rate=2) * 0.2
            + U.ToggleFF.ar(trigger=imp(20)) * 0.2
            + U.Decay2.ar(source=imp(8), attack_time=0.001, decay_time=0.05) * 0.2
            + U.Lag.ar(source=pulse, lag_time=0.01) * 0.1
            + U.Ramp.ar(source=pulse, lag_time=0.01) * 0.1,
        ],
    )


def case_rates() -> None:
    U.Out.ar(
        bus=0,
        source=[
            U.K2A.ar(source=U.SinOsc.kr(frequency=5, phase=0)),
            U.K2A.ar(source=U.A2K.kr(source=sin(5))),
        ],
    )


def case_seeded_noise() -> None:
    U.RandSeed.ir(trigger=1, seed=42)
    U.Out.ar(
        bus=0, source=[U.WhiteNoise.ar() * 0.1, U.LFNoise1.ar(frequency=500) * 0.1]
    )


def case_linmap() -> None:
    s = sin(2)
    lin = U.LinLin.ar(
        source=s,
        input_minimum=-1,
        input_maximum=1,
        output_minimum=200,
        output_maximum=400,
    )
    exp = U.LinExp.ar(
        source=s,
        input_minimum=-1,
        input_maximum=1,
        output_minimum=200,
        output_maximum=800,
    )
    U.Out.ar(
        bus=0,
        source=[
            U.SinOsc.ar(frequency=lin, phase=0) * 0.2,
            U.SinOsc.ar(frequency=exp, phase=0) * 0.2,
        ],
    )


def case_klank() -> None:
    U.Out.ar(
        bus=0,
        source=U.Klank.ar(
            source=U.Impulse.ar(frequency=8, phase=0),
            frequencies=[400, 800, 1200],
            amplitudes=[0.3, 0.2, 0.1],
            decay_times=[0.2, 0.3, 0.4],
            frequency_scale=1,
            frequency_offset=0,
            decay_scale=1,
        ),
    )


def case_buses() -> None:
    U.Out.ar(bus=10, source=sin(330))
    U.Out.ar(bus=0, source=U.In.ar(bus=10, channel_count=1) * 0.5)


def case_lines() -> None:
    U.Out.ar(
        bus=0,
        source=[
            U.Line.ar(start=0, stop=1, duration=0.2, done_action=0),
            U.XLine.ar(start=0.01, stop=1, duration=0.2, done_action=0),
        ],
    )


CASES: dict[str, Callable[..., None]] = {
    name.removeprefix("case_"): fn
    for name, fn in globals().items()
    if name.startswith("case_")
}
CONTROLS = {"controls": {"freq": 330.0, "amp": 0.25}}


def compile_case(name: str) -> bytes:
    with SynthDefBuilder(**CONTROLS.get(name, {})) as b:
        fn = CASES[name]
        fn(b) if fn.__code__.co_argcount else fn()
    return b.build(name="corpus").compile()


def render(def_bytes: bytes, tmp: Path, tag: str) -> list[float]:
    path = tmp / f"{tag}.scsyndef"
    path.write_bytes(def_bytes)
    code = (
        "import sys; from nanosynth.osc import OscMessage; from nanosynth.score import Score;"
        "from nanosynth.scsynth import Options; from pathlib import Path;"
        "s = Score(); s.add(0.0, OscMessage('/d_recv', Path(sys.argv[1]).read_bytes()));"
        "s.add(0.0, OscMessage('/s_new', 'corpus', 1000, 0, 0));"
        f"s.add({SECONDS}, OscMessage('/c_set', 0, 0));"
        "s.render(sys.argv[1] + '.wav', sample_format='float', output_channels=2,"
        " options=Options(verbosity=-1))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(path)], capture_output=True, timeout=60
    )
    if proc.returncode != 0:
        raise RuntimeError(f"render failed (exit {proc.returncode})")
    raw = Path(str(path) + ".wav").read_bytes()
    i = raw.find(b"data")
    n = struct.unpack("<I", raw[i + 4 : i + 8])[0]
    return list(struct.unpack(f"<{n // 4}f", raw[i + 8 : i + 8 + n - n % 4]))


def main(sclang_dir: str) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="corpus-"))
    results = []
    for name in CASES:
        row: dict[str, object] = {"case": name}
        ref_path = Path(sclang_dir) / f"{name}.scsyndef"
        try:
            ref = render(ref_path.read_bytes(), tmp, f"{name}.sc")
            got = render(compile_case(name), tmp, f"{name}.ns")
            finite = [abs(a - b) for a, b in zip(ref, got) if a == a and b == b]
            diff = max(finite, default=0.0)
            peak = max((abs(a) for a in ref if a == a), default=0.0)
            row.update(
                max_diff=diff,
                peak=peak,
                status="MATCH" if diff <= TOLERANCE else "DIFFERENT",
            )
        except Exception as exc:  # noqa: BLE001 -- report and continue
            row.update(status="ERROR", detail=f"{type(exc).__name__}: {exc}")
        results.append(row)
        detail = (
            row.get("detail")
            or f"max|diff|={row['max_diff']:.3g} peak={row['peak']:.3g}"
        )
        print(f"{name:24} {row['status']:9} {detail}")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
