"""Performance benchmarks for the compile and OSC hot paths.

Run via ``make bench`` (writes a JSON) or ``make bench-check`` (compares against
the committed baseline and fails on regression). These are deliberately kept out
of the ``tests/`` tree so the coverage-gated ``make test`` run neither collects
nor times them.

The reference graph is a small but representative subtractive-synth voice: three
detuned oscillators (multichannel expansion), a mix-down (Sum tree), a resonant
filter, an envelope, operator UGens, and four control-rate parameters. It
exercises every stage of ``SynthDefBuilder.build()`` -- expansion, topological
sort, optimization, and SCgf encoding.
"""

from __future__ import annotations

from typing import Any

import pytest

from nanosynth import SynthDefBuilder
from nanosynth.enums import DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.osc import OscBundle, OscMessage
from nanosynth.synthdef import SynthDef
from nanosynth.ugens import RLPF, Mix, Out, Pan2, Saw


def build_reference() -> SynthDef:
    """Construct and compile the reference SynthDef from scratch."""
    with SynthDefBuilder(freq=440.0, amp=0.2, cutoff=2000.0, gate=1.0) as builder:
        env = EnvGen.kr(
            envelope=Envelope.adsr(),
            gate=builder["gate"],
            done_action=DoneAction.FREE_SYNTH,
        )
        osc = Saw.ar(
            frequency=[builder["freq"], builder["freq"] * 1.01, builder["freq"] * 0.99]
        )
        mixed = Mix.new(osc)
        filtered = RLPF.ar(
            source=mixed, frequency=builder["cutoff"], reciprocal_of_q=0.5
        )
        signal = filtered * env * builder["amp"]
        Out.ar(bus=0, source=Pan2.ar(source=signal, position=0.0))
    return builder.build(name="reference")


def _reference_message() -> OscMessage:
    return OscMessage("/s_new", "reference", 1000, 0, 0, "freq", 330.0, "amp", 0.2)


def _reference_bundle() -> OscBundle:
    return OscBundle(
        contents=[_reference_message() for _ in range(8)],
        timestamp=1.0,
    )


@pytest.mark.benchmark(group="compile")
def test_build_reference_graph(benchmark: Any) -> None:
    """Full define + build + compile of the reference SynthDef."""
    result = benchmark(build_reference)
    assert result.compile()[:4] == b"SCgf"


@pytest.mark.benchmark(group="compile")
def test_compile_prebuilt_graph(benchmark: Any) -> None:
    """SCgf backend encoding of an already-built SynthDef."""
    synthdef = build_reference()
    result = benchmark(synthdef.compile)
    assert result[:4] == b"SCgf"


@pytest.mark.benchmark(group="osc")
def test_osc_message_encode(benchmark: Any) -> None:
    message = _reference_message()
    result = benchmark(message.to_datagram)
    assert isinstance(result, bytes)


@pytest.mark.benchmark(group="osc")
def test_osc_message_decode(benchmark: Any) -> None:
    datagram = _reference_message().to_datagram()
    result = benchmark(OscMessage.from_datagram, datagram)
    assert result.address == "/s_new"


@pytest.mark.benchmark(group="osc")
def test_osc_bundle_encode(benchmark: Any) -> None:
    bundle = _reference_bundle()
    result = benchmark(bundle.to_datagram)
    assert isinstance(result, bytes)


@pytest.mark.benchmark(group="osc")
def test_osc_bundle_decode(benchmark: Any) -> None:
    datagram = _reference_bundle().to_datagram()
    result = benchmark(OscBundle.from_datagram, datagram)
    assert len(result.contents) == 8
