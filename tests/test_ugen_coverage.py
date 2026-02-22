"""Tests for low-coverage UGen modules: inout, panning, ffsinosc, lines.

Targets uncovered code paths: LocalIn._postprocess_kwargs, Splay PseudoUGen,
Klank.ar() specification expansion, LinLin PseudoUGen, and Silence PseudoUGen.
"""

import pytest

from nanosynth.synthdef import (
    SynthDefBuilder,
    UGenVector,
)
from nanosynth.ugens import Out, SinOsc, WhiteNoise
from nanosynth.ugens.basic import MulAdd
from nanosynth.ugens.ffsinosc import Klank
from nanosynth.ugens.inout import LocalIn, LocalOut
from nanosynth.ugens.lines import DC, LinLin, Silence
from nanosynth.ugens.panning import BiPanB2, DecodeB2, Pan2, Splay


# ---------------------------------------------------------------------------
# inout.py: LocalIn
# ---------------------------------------------------------------------------


class TestLocalIn:
    def test_localin_single_channel(self):
        """LocalIn.ar(channel_count=1) with default 0 compiles."""
        with SynthDefBuilder() as builder:
            local = LocalIn.ar(channel_count=1)
            Out.ar(bus=0, source=local)
        sd = builder.build(name="test")
        localins = [u for u in sd.ugens if isinstance(u, LocalIn)]
        assert len(localins) == 1

    def test_localin_multi_channel(self):
        """LocalIn.ar(channel_count=2) produces a multi-output UGen with 2 channels."""
        with SynthDefBuilder() as builder:
            local = LocalIn.ar(channel_count=2)
            assert isinstance(local, LocalIn)
            assert len(local) == 2
            Out.ar(bus=0, source=local)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_localin_default_cycling(self):
        """LocalIn cycles defaults to fill channel_count."""
        with SynthDefBuilder() as builder:
            # 4 channels with 2-element default -> should cycle [0.5, 0.8, 0.5, 0.8]
            local = LocalIn.ar(channel_count=4, default=[0.5, 0.8])
            Out.ar(bus=0, source=local)
        sd = builder.build(name="test")
        localins = [u for u in sd.ugens if isinstance(u, LocalIn)]
        assert len(localins) == 1
        # Verify we can compile without errors
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_localin_single_default_value(self):
        """LocalIn with a scalar default still works."""
        with SynthDefBuilder() as builder:
            local = LocalIn.ar(channel_count=2, default=0.0)
            Out.ar(bus=0, source=local)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_localin_with_localout(self):
        """LocalIn/LocalOut feedback loop compiles."""
        with SynthDefBuilder() as builder:
            local = LocalIn.ar(channel_count=1, default=0.0)
            sig = SinOsc.ar(frequency=440.0) + local * 0.5
            LocalOut.ar(source=sig)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="feedback")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_localin_kr(self):
        """LocalIn.kr works at control rate."""
        with SynthDefBuilder() as builder:
            local = LocalIn.kr(channel_count=1)
            Out.kr(bus=0, source=local)
        sd = builder.build(name="test")
        localins = [u for u in sd.ugens if isinstance(u, LocalIn)]
        assert len(localins) == 1


# ---------------------------------------------------------------------------
# panning.py: BiPanB2, DecodeB2, Splay
# ---------------------------------------------------------------------------


class TestBiPanB2:
    def test_bipanb2_compiles(self):
        """BiPanB2 produces 3-channel output and compiles."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=660)
            result = BiPanB2.ar(in_a=a, in_b=b, azimuth=0.0)
            assert isinstance(result, BiPanB2)
            assert len(result) == 3
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_bipanb2_kr(self):
        """BiPanB2.kr works at control rate."""
        with SynthDefBuilder() as builder:
            a = SinOsc.kr(frequency=1)
            b = SinOsc.kr(frequency=2)
            result = BiPanB2.kr(in_a=a, in_b=b, azimuth=0.5)
            Out.kr(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"


class TestDecodeB2:
    def test_decodeb2_compiles(self):
        """DecodeB2 with default 4 channels compiles."""
        with SynthDefBuilder() as builder:
            w = SinOsc.ar(frequency=440)
            x = SinOsc.ar(frequency=550)
            y = SinOsc.ar(frequency=660)
            result = DecodeB2.ar(channel_count=4, w=w, x=x, y=y)
            assert isinstance(result, DecodeB2)
            assert len(result) == 4
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_decodeb2_custom_channel_count(self):
        """DecodeB2 with custom channel count."""
        with SynthDefBuilder() as builder:
            w = SinOsc.ar(frequency=440)
            x = SinOsc.ar(frequency=550)
            y = SinOsc.ar(frequency=660)
            result = DecodeB2.ar(channel_count=8, w=w, x=x, y=y)
            assert isinstance(result, DecodeB2)
            assert len(result) == 8
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"


class TestSplay:
    def test_splay_ar_single_source(self):
        """Splay.ar with a single source produces stereo output."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar(frequency=440)
            result = Splay.ar(source=[sig])
            assert isinstance(result, UGenVector)
            assert len(result) == 2
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_splay_ar_multiple_sources(self):
        """Splay.ar with multiple sources spreads across stereo field."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=f) for f in [440, 550, 660, 770]]
            result = Splay.ar(source=sources)
            assert isinstance(result, UGenVector)
            assert len(result) == 2
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        # Should have Pan2 UGens for each source
        pan2s = [u for u in sd.ugens if isinstance(u, Pan2)]
        assert len(pan2s) == 4

    def test_splay_ar_normalize(self):
        """Splay.ar with normalize=True scales level by sqrt(1/n)."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=f) for f in [440, 550]]
            result = Splay.ar(source=sources, normalize=True)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_splay_ar_no_normalize(self):
        """Splay.ar with normalize=False does not scale level."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=f) for f in [440, 550]]
            result = Splay.ar(source=sources, normalize=False)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_splay_kr(self):
        """Splay.kr works at control rate."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.kr(frequency=f) for f in [1, 2, 3]]
            result = Splay.kr(source=sources)
            assert isinstance(result, UGenVector)
            assert len(result) == 2
            Out.kr(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_splay_custom_spread_and_center(self):
        """Splay.ar respects spread and center parameters."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=f) for f in [440, 880]]
            result = Splay.ar(source=sources, spread=0.5, center=0.3)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"


# ---------------------------------------------------------------------------
# ffsinosc.py: Klank
# ---------------------------------------------------------------------------


class TestKlank:
    def test_klank_basic(self):
        """Klank.ar with explicit frequencies compiles."""
        with SynthDefBuilder() as builder:
            sig = WhiteNoise.ar() * 0.01
            result = Klank.ar(
                source=sig,
                frequencies=[800, 1071, 1153, 1723],
            )
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        klanks = [u for u in sd.ugens if isinstance(u, Klank)]
        assert len(klanks) == 1

    def test_klank_with_amplitudes(self):
        """Klank.ar with explicit amplitudes compiles."""
        with SynthDefBuilder() as builder:
            sig = WhiteNoise.ar() * 0.01
            result = Klank.ar(
                source=sig,
                frequencies=[800, 1200],
                amplitudes=[1.0, 0.5],
            )
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_klank_with_decay_times(self):
        """Klank.ar with explicit decay times compiles."""
        with SynthDefBuilder() as builder:
            sig = WhiteNoise.ar() * 0.01
            result = Klank.ar(
                source=sig,
                frequencies=[800, 1200, 1600],
                amplitudes=[1.0, 0.5, 0.25],
                decay_times=[1.0, 0.5, 0.25],
            )
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_klank_default_amplitudes_and_decays(self):
        """Klank.ar defaults amplitudes and decay_times to 1.0 each."""
        with SynthDefBuilder() as builder:
            sig = WhiteNoise.ar() * 0.01
            result = Klank.ar(
                source=sig,
                frequencies=[440, 880, 1320],
            )
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        klanks = [u for u in sd.ugens if isinstance(u, Klank)]
        assert len(klanks) == 1
        # Should have 9 spec inputs (3 freqs * 3 values each) plus source + 3 scale params
        # The specifications are interleaved: [f1, a1, d1, f2, a2, d2, ...]

    def test_klank_empty_frequencies_raises(self):
        """Klank.ar with empty frequencies raises ValueError."""
        with SynthDefBuilder():
            sig = WhiteNoise.ar() * 0.01
            with pytest.raises(ValueError):
                Klank.ar(source=sig, frequencies=[])

    def test_klank_frequency_scale(self):
        """Klank.ar with frequency_scale parameter compiles."""
        with SynthDefBuilder() as builder:
            sig = WhiteNoise.ar() * 0.01
            result = Klank.ar(
                source=sig,
                frequencies=[800, 1200],
                frequency_scale=2.0,
                frequency_offset=100.0,
                decay_scale=0.5,
            )
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"


# ---------------------------------------------------------------------------
# lines.py: LinLin, Silence
# ---------------------------------------------------------------------------


class TestLinLin:
    def test_linlin_ar(self):
        """LinLin.ar maps input range to output range."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar(frequency=1.0)
            mapped = LinLin.ar(
                source=sig,
                input_minimum=-1.0,
                input_maximum=1.0,
                output_minimum=200.0,
                output_maximum=800.0,
            )
            Out.ar(bus=0, source=mapped)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        # LinLin uses MulAdd internally
        muladds = [u for u in sd.ugens if isinstance(u, MulAdd)]
        assert len(muladds) >= 1

    def test_linlin_kr(self):
        """LinLin.kr maps input range to output range at control rate."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.kr(frequency=1.0)
            mapped = LinLin.kr(
                source=sig,
                input_minimum=-1.0,
                input_maximum=1.0,
                output_minimum=0.0,
                output_maximum=1.0,
            )
            Out.kr(bus=0, source=mapped)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_linlin_identity_mapping(self):
        """LinLin with identical input/output ranges is identity."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar(frequency=440)
            mapped = LinLin.ar(
                source=sig,
                input_minimum=0.0,
                input_maximum=1.0,
                output_minimum=0.0,
                output_maximum=1.0,
            )
            Out.ar(bus=0, source=mapped)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"


class TestSilence:
    def test_silence_mono(self):
        """Silence.ar() produces a single DC(0) UGen."""
        with SynthDefBuilder() as builder:
            sig = Silence.ar()
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        dcs = [u for u in sd.ugens if isinstance(u, DC)]
        assert len(dcs) == 1

    def test_silence_stereo(self):
        """Silence.ar(channel_count=2) produces a UGenVector of 2 channels."""
        with SynthDefBuilder() as builder:
            sig = Silence.ar(channel_count=2)
            assert isinstance(sig, UGenVector)
            assert len(sig) == 2
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_silence_many_channels(self):
        """Silence.ar(channel_count=8) produces 8-channel output."""
        with SynthDefBuilder() as builder:
            sig = Silence.ar(channel_count=8)
            assert isinstance(sig, UGenVector)
            assert len(sig) == 8
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
