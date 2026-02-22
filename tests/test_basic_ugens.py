"""Tests for basic utility UGens: MulAdd, Sum3, Sum4, Mix."""

from nanosynth.enums import CalculationRate
from nanosynth.synthdef import (
    BinaryOpUGen,
    ConstantProxy,
    OutputProxy,
    SynthDefBuilder,
    UGenVector,
    UnaryOpUGen,
)
from nanosynth.ugens import Out, SinOsc
from nanosynth.ugens.basic import Mix, MulAdd, Sum3, Sum4


# ---------------------------------------------------------------------------
# MulAdd
# ---------------------------------------------------------------------------


class TestMulAdd:
    def test_identity(self):
        """MulAdd(source, 1, 0) returns the source unchanged."""
        with SynthDefBuilder():
            sig = SinOsc.ar()
            result = MulAdd.new(source=sig, multiplier=1, addend=0)
            assert result is sig

    def test_mul_zero_returns_addend(self):
        """MulAdd(source, 0, addend) returns the addend."""
        with SynthDefBuilder():
            sig = SinOsc.ar()
            result = MulAdd.new(source=sig, multiplier=0.0, addend=5.0)
            assert isinstance(result, (float, ConstantProxy))
            assert float(result) == 5.0

    def test_negate_source(self):
        """MulAdd(source, -1, 0) returns -source."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            result = MulAdd.new(source=sig, multiplier=-1, addend=0)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        unary_ops = [u for u in sd.ugens if isinstance(u, UnaryOpUGen)]
        assert len(unary_ops) == 1

    def test_mul_only(self):
        """MulAdd(source, m, 0) with m != 1 returns source * m."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            result = MulAdd.new(source=sig, multiplier=0.5, addend=0)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        binary_ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) == 1

    def test_sub_source(self):
        """MulAdd(source, -1, addend) returns addend - source."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            result = MulAdd.new(source=sig, multiplier=-1, addend=1.0)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        binary_ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) == 1

    def test_add_only(self):
        """MulAdd(source, 1, addend) returns source + addend."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            result = MulAdd.new(source=sig, multiplier=1, addend=0.5)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        binary_ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) == 1

    def test_full_muladd_audio_rate(self):
        """MulAdd with audio-rate source creates a MulAdd UGen."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            result = MulAdd.new(source=sig, multiplier=0.5, addend=0.1)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        muladds = [u for u in sd.ugens if isinstance(u, MulAdd)]
        assert len(muladds) == 1
        assert muladds[0].calculation_rate == CalculationRate.AUDIO

    def test_full_muladd_control_rate(self):
        """MulAdd with control-rate source and scalar args creates MulAdd."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.kr()
            result = MulAdd.new(source=sig, multiplier=0.5, addend=0.1)
            Out.kr(bus=0, source=result)
        sd = builder.build(name="test")
        muladds = [u for u in sd.ugens if isinstance(u, MulAdd)]
        assert len(muladds) == 1
        assert muladds[0].calculation_rate == CalculationRate.CONTROL

    def test_rate_swapped_inputs(self):
        """When source is invalid but multiplier is valid as source, inputs swap."""
        with SynthDefBuilder() as builder:
            # control-rate source with audio-rate multiplier -- should swap
            kr_sig = SinOsc.kr()
            ar_sig = SinOsc.ar()
            result = MulAdd.new(source=kr_sig, multiplier=ar_sig, addend=0.1)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        muladds = [u for u in sd.ugens if isinstance(u, MulAdd)]
        assert len(muladds) == 1
        # The MulAdd should be audio rate (max of inputs)
        assert muladds[0].calculation_rate == CalculationRate.AUDIO

    def test_fallback_scalar_source_swaps_to_muladd(self):
        """Scalar source with audio multiplier swaps inputs to produce MulAdd."""
        with SynthDefBuilder() as builder:
            # scalar source, audio multiplier -- swap makes multiplier the source
            result = MulAdd.new(source=1.0, multiplier=SinOsc.ar(), addend=SinOsc.ar())
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        muladds = [u for u in sd.ugens if isinstance(u, MulAdd)]
        assert len(muladds) == 1
        assert muladds[0].calculation_rate == CalculationRate.AUDIO

    def test_muladd_compiles(self):
        """A SynthDef containing MulAdd compiles to valid SCgf."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            result = MulAdd.new(source=sig, multiplier=0.5, addend=0.1)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test_muladd")
        data = sd.compile()
        assert data[:4] == b"SCgf"


# ---------------------------------------------------------------------------
# Sum3
# ---------------------------------------------------------------------------


class TestSum3:
    def test_three_nonzero_creates_sum3(self):
        """Sum3 with three nonzero inputs creates a Sum3 UGen."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=550)
            c = SinOsc.ar(frequency=660)
            result = Sum3.new(input_one=a, input_two=b, input_three=c)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum3s) == 1

    def test_third_zero_returns_sum(self):
        """Sum3(a, b, 0) returns a + b."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=550)
            result = Sum3.new(input_one=a, input_two=b, input_three=0)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum3s) == 0
        binary_ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) >= 1

    def test_second_zero_returns_sum(self):
        """Sum3(a, 0, c) returns a + c."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            c = SinOsc.ar(frequency=660)
            result = Sum3.new(input_one=a, input_two=0, input_three=c)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum3s) == 0

    def test_first_zero_returns_sum(self):
        """Sum3(0, b, c) returns b + c."""
        with SynthDefBuilder() as builder:
            b = SinOsc.ar(frequency=550)
            c = SinOsc.ar(frequency=660)
            result = Sum3.new(input_one=0, input_two=b, input_three=c)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum3s) == 0

    def test_rate_sorting(self):
        """Sum3 sorts inputs by rate, highest first."""
        with SynthDefBuilder() as builder:
            ar = SinOsc.ar()
            kr = SinOsc.kr()
            result = Sum3.new(input_one=kr, input_two=1.0, input_three=ar)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum3s) == 1
        # Rate should be audio (max of inputs)
        assert sum3s[0].calculation_rate == CalculationRate.AUDIO
        # First input should be the audio-rate UGen
        first_input = sum3s[0].inputs[0]
        assert isinstance(first_input, OutputProxy)
        assert first_input.ugen.calculation_rate == CalculationRate.AUDIO

    def test_sum3_compiles(self):
        """A SynthDef containing Sum3 compiles to valid SCgf."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=550)
            c = SinOsc.ar(frequency=660)
            result = Sum3.new(input_one=a, input_two=b, input_three=c)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test_sum3")
        data = sd.compile()
        assert data[:4] == b"SCgf"


# ---------------------------------------------------------------------------
# Sum4
# ---------------------------------------------------------------------------


class TestSum4:
    def test_four_nonzero_creates_sum4(self):
        """Sum4 with four nonzero inputs creates a Sum4 UGen."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=550)
            c = SinOsc.ar(frequency=660)
            d = SinOsc.ar(frequency=770)
            result = Sum4.new(input_one=a, input_two=b, input_three=c, input_four=d)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        assert len(sum4s) == 1

    def test_first_zero_delegates_to_sum3(self):
        """Sum4(0, b, c, d) delegates to Sum3(b, c, d)."""
        with SynthDefBuilder() as builder:
            b = SinOsc.ar(frequency=550)
            c = SinOsc.ar(frequency=660)
            d = SinOsc.ar(frequency=770)
            result = Sum4.new(input_one=0, input_two=b, input_three=c, input_four=d)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum4s) == 0
        assert len(sum3s) == 1

    def test_second_zero_delegates_to_sum3(self):
        """Sum4(a, 0, c, d) delegates to Sum3(a, c, d)."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            c = SinOsc.ar(frequency=660)
            d = SinOsc.ar(frequency=770)
            result = Sum4.new(input_one=a, input_two=0, input_three=c, input_four=d)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum4s) == 0
        assert len(sum3s) == 1

    def test_third_zero_delegates_to_sum3(self):
        """Sum4(a, b, 0, d) delegates to Sum3(a, b, d)."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=550)
            d = SinOsc.ar(frequency=770)
            result = Sum4.new(input_one=a, input_two=b, input_three=0, input_four=d)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum4s) == 0
        assert len(sum3s) == 1

    def test_fourth_zero_delegates_to_sum3(self):
        """Sum4(a, b, c, 0) delegates to Sum3(a, b, c)."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=550)
            c = SinOsc.ar(frequency=660)
            result = Sum4.new(input_one=a, input_two=b, input_three=c, input_four=0)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum4s) == 0
        assert len(sum3s) == 1

    def test_two_zeros_becomes_binary_add(self):
        """Sum4 with two zero inputs collapses through Sum3 to binary add."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=550)
            result = Sum4.new(input_one=a, input_two=0, input_three=b, input_four=0)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum4s) == 0
        assert len(sum3s) == 0
        binary_ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) >= 1

    def test_rate_sorting(self):
        """Sum4 sorts inputs by rate, highest first."""
        with SynthDefBuilder() as builder:
            ar = SinOsc.ar()
            kr = SinOsc.kr()
            result = Sum4.new(
                input_one=1.0, input_two=kr, input_three=2.0, input_four=ar
            )
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        assert len(sum4s) == 1
        assert sum4s[0].calculation_rate == CalculationRate.AUDIO
        first_input = sum4s[0].inputs[0]
        assert isinstance(first_input, OutputProxy)
        assert first_input.ugen.calculation_rate == CalculationRate.AUDIO

    def test_sum4_compiles(self):
        """A SynthDef containing Sum4 compiles to valid SCgf."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=550)
            c = SinOsc.ar(frequency=660)
            d = SinOsc.ar(frequency=770)
            result = Sum4.new(input_one=a, input_two=b, input_three=c, input_four=d)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test_sum4")
        data = sd.compile()
        assert data[:4] == b"SCgf"


# ---------------------------------------------------------------------------
# Mix
# ---------------------------------------------------------------------------


class TestMix:
    def test_single_source_passthrough(self):
        """Mix of a single source returns that source directly."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            result = Mix.new([sig])
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        # No Sum3/Sum4/BinaryOp needed for a single input
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        assert len(sum3s) == 0
        assert len(sum4s) == 0

    def test_two_sources_binary_add(self):
        """Mix of two sources produces a BinaryOpUGen addition."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=550)
            result = Mix.new([a, b])
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        binary_ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) >= 1

    def test_three_sources_sum3(self):
        """Mix of three sources produces a Sum3 UGen."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=f) for f in [440, 550, 660]]
            result = Mix.new(sources)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum3s) == 1

    def test_four_sources_sum4(self):
        """Mix of four sources produces a Sum4 UGen."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=f) for f in [440, 550, 660, 770]]
            result = Mix.new(sources)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        assert len(sum4s) == 1

    def test_five_sources_recursive(self):
        """Mix of five sources groups into Sum4 + remainder, then sums."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=f) for f in [440, 550, 660, 770, 880]]
            result = Mix.new(sources)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        # First pass: Sum4(4 sources) + 1 remainder = 2 intermediate results
        # Second pass: binary add of 2 results
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        assert len(sum4s) == 1

    def test_eight_sources(self):
        """Mix of eight sources produces two Sum4 UGens."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=440 + i * 50) for i in range(8)]
            result = Mix.new(sources)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        # First pass: 2 x Sum4 = 2 results, second pass: binary add
        assert len(sum4s) == 2

    def test_nested_sources_flattened(self):
        """Mix flattens nested lists of sources."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar(frequency=440)
            b = SinOsc.ar(frequency=550)
            c = SinOsc.ar(frequency=660)
            result = Mix.new([[a, b], c])
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        assert len(sum3s) == 1

    def test_non_sequence_wrapped(self):
        """Mix.new(single_ugen) wraps non-sequence in list and passes through."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            result = Mix.new(sig)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        sinoscs = [u for u in sd.ugens if isinstance(u, SinOsc)]
        assert len(sinoscs) == 1
        # No summing UGens needed for a single input
        sum3s = [u for u in sd.ugens if isinstance(u, Sum3)]
        sum4s = [u for u in sd.ugens if isinstance(u, Sum4)]
        assert len(sum3s) == 0
        assert len(sum4s) == 0

    def test_multichannel_basic(self):
        """Mix.multichannel splits sources into columns and mixes each."""
        with SynthDefBuilder() as builder:
            # 4 sources, 2 channels -> 2 columns of 2, each mixed
            sources = [SinOsc.ar(frequency=f) for f in [440, 550, 660, 770]]
            result = Mix.multichannel(sources, channel_count=2)
            assert isinstance(result, UGenVector)
            assert len(result) == 2
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_mix_compiles(self):
        """A SynthDef using Mix compiles to valid SCgf."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=f) for f in [440, 550, 660, 770]]
            Out.ar(bus=0, source=Mix.new(sources))
        sd = builder.build(name="test_mix")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_mix_multichannel_expansion(self):
        """Mix of multichannel-expanded UGens (UGenVector) flattens correctly."""
        with SynthDefBuilder() as builder:
            # SinOsc.ar with list produces UGenVector
            stereo = SinOsc.ar(frequency=[440, 550])
            result = Mix.new(stereo)
            Out.ar(bus=0, source=result)
        sd = builder.build(name="test")
        # Two SinOsc UGens mixed down to mono via binary add
        binary_ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) >= 1

    def test_mix_deterministic(self):
        """Two identical Mix graphs produce byte-identical SCgf."""

        def build_mix():
            with SynthDefBuilder() as builder:
                sources = [SinOsc.ar(frequency=f) for f in [440, 550, 660]]
                Out.ar(bus=0, source=Mix.new(sources))
            return builder.build(name="det").compile()

        assert build_mix() == build_mix()
