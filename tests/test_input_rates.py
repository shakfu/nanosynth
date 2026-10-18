"""Input-rate checks at SynthDef build, as sclang's checkInputs (src/nanosynth/_input_rates.py)."""

import pytest

from nanosynth.exceptions import SynthDefError
from nanosynth.synthdef import SynthDefBuilder
from nanosynth.ugens import (
    LPF,
    BufRd,
    BufWr,
    DC,
    Demand,
    Dseq,
    Impulse,
    K2A,
    Out,
    Saw,
    SinOsc,
    XFade2,
)


def _build(fn, **controls):  # type: ignore[no-untyped-def]
    with SynthDefBuilder(**controls) as b:
        fn(b)
    return b.build(name="t")


class TestRejected:
    @pytest.mark.parametrize(
        "fn, match",
        [
            (
                lambda b: Out.ar(bus=0, source=0.5),
                r"Out\.ar input 1 \('source'\) must be audio",
            ),
            (lambda b: Out.ar(bus=0, source=SinOsc.kr()), "got control rate"),
            (lambda b: Out.ar(bus=0, source=b["amp"]), "got control rate"),
            (
                lambda b: Out.ar(bus=0, source=LPF.ar(source=Saw.kr())),
                r"LPF\.ar input 0",
            ),
            # Every element of an array parameter is checked.
            (lambda b: Out.ar(bus=0, source=[SinOsc.ar(), 0.1]), "input 2"),
            # Defaults that sclang rejects too.
            (
                lambda b: Out.ar(bus=0, source=BufRd.ar(buffer_id=0)),
                r"BufRd\.ar input 1 \('phase'\)",
            ),
            (
                lambda b: BufWr.ar(buffer_id=0, source=SinOsc.ar()),
                r"BufWr\.ar input 1 \('phase'\)",
            ),
            (
                lambda b: Out.ar(bus=0, source=XFade2.ar(in_a=SinOsc.ar())),
                r"XFade2\.ar input 1",
            ),
            (
                lambda b: Out.ar(
                    bus=0,
                    source=Demand.ar(trigger=1, reset=0, source=Dseq.dr(sequence=[1])),
                ),
                r"Demand\.ar input 0",
            ),
        ],
    )
    def test_rejected(self, fn, match) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(SynthDefError, match=match):
            _build(fn, amp=0.5)


class TestAccepted:
    @pytest.mark.parametrize(
        "fn",
        [
            lambda b: Out.ar(bus=0, source=DC.ar(source=0.5)),
            lambda b: Out.ar(bus=0, source=K2A.ar(source=b["amp"])),
            lambda b: Out.kr(bus=0, source=0.5),
            lambda b: Out.ar(
                bus=0, source=LPF.ar(source=Saw.ar(), frequency=SinOsc.kr())
            ),
            lambda b: Out.ar(
                bus=0,
                source=Demand.ar(
                    trigger=Impulse.ar(frequency=4),
                    reset=0,
                    source=Dseq.dr(sequence=[1]),
                ),
            ),
        ],
    )
    def test_accepted(self, fn) -> None:  # type: ignore[no-untyped-def]
        assert _build(fn, amp=0.5).compile()[:4] == b"SCgf"

    def test_audio_rate_control_is_audio(self) -> None:
        from nanosynth.synthdef import control

        sd = _build(
            lambda b: Out.ar(bus=0, source=b["sig"]), sig=control(0.0, rate="ar")
        )
        assert sd.compile()[:4] == b"SCgf"
