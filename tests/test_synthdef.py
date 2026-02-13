"""Tests for SynthDef compilation, UGen graphs, parameters, and envelopes."""

import struct

import pytest

from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import (
    BinaryOpUGen,
    BinaryOperator,
    CalculationRate,
    ConstantProxy,
    Control,
    DoneAction,
    EnvelopeShape,
    OutputProxy,
    Parameter,
    ParameterRate,
    SynthDef,
    SynthDefBuilder,
    SynthDefError,
    UGen,
    UGenVector,
    UnaryOpUGen,
    compile_synthdefs,
    param,
    synthdef,
    ugen,
)
from nanosynth.ugens import (
    LPF,
    Line,
    Out,
    Pan2,
    RLPF,
    Saw,
    SinOsc,
    WhiteNoise,
    XLine,
)


# ---------------------------------------------------------------------------
# SCgf compilation tests
# ---------------------------------------------------------------------------


class TestCompilation:
    def test_scgf_header(self):
        """Compiled output starts with SCgf magic, version 2, synthdef count 1."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        synthdef = builder.build(name="test")
        data = synthdef.compile()
        assert data[:4] == b"SCgf"
        version = struct.unpack(">I", data[4:8])[0]
        assert version == 2
        count = struct.unpack(">H", data[8:10])[0]
        assert count == 1

    def test_synthdef_name_encoded(self):
        """The synthdef name appears in the compiled bytes."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        synthdef = builder.build(name="my_synth")
        data = synthdef.compile()
        # After the 10-byte header, we should find the name
        name_len = data[10]
        name = data[11 : 11 + name_len].decode("ascii")
        assert name == "my_synth"

    def test_anonymous_name_is_md5(self):
        """A SynthDef without a name gets an MD5 hash as anonymous_name."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        synthdef = builder.build()
        assert len(synthdef.anonymous_name) == 32
        assert synthdef.name is None
        assert synthdef.effective_name == synthdef.anonymous_name

    def test_constants_collected(self):
        """Constants used in UGen inputs are collected in the SynthDef."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=880.0, phase=0.5))
        synthdef = builder.build(name="test")
        # 440.0 default is overridden, so constants should include 880.0, 0.5, 0.0
        assert 880.0 in synthdef.constants
        assert 0.5 in synthdef.constants
        assert 0.0 in synthdef.constants

    def test_parameters_encoded(self):
        """Named parameters appear in the SynthDef."""
        with SynthDefBuilder(frequency=440.0, amplitude=0.5) as builder:
            sig = SinOsc.ar(frequency=builder["frequency"])
            Out.ar(bus=0, source=sig * builder["amplitude"])
        synthdef = builder.build(name="test")
        assert "frequency" in synthdef.parameters
        assert "amplitude" in synthdef.parameters

    def test_ugen_count(self):
        """The number of UGens matches expected count."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        synthdef = builder.build(name="test")
        # SinOsc + Out = 2
        assert len(synthdef.ugens) == 2

    def test_compile_multiple_synthdefs(self):
        """compile_synthdefs handles multiple SynthDefs."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar())
        sd1 = b1.build(name="a")
        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=SinOsc.ar(frequency=880.0))
        sd2 = b2.build(name="b")
        data = compile_synthdefs(sd1, sd2)
        assert data[:4] == b"SCgf"
        count = struct.unpack(">H", data[8:10])[0]
        assert count == 2

    def test_round_trip_deterministic(self):
        """Compiling the same SynthDef twice yields identical bytes."""
        with SynthDefBuilder(freq=440.0) as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=builder["freq"]))
        sd1 = builder.build(name="det")
        with SynthDefBuilder(freq=440.0) as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=builder["freq"]))
        sd2 = builder.build(name="det")
        assert sd1.compile() == sd2.compile()


# ---------------------------------------------------------------------------
# UGen graph tests
# ---------------------------------------------------------------------------


class TestUGenGraph:
    def test_multichannel_expansion(self):
        """SinOsc.ar(frequency=[440, 443]) produces a UGenVector of two proxies."""
        with SynthDefBuilder():
            result = SinOsc.ar(frequency=[440, 443])
            Out.ar(bus=0, source=result)
        assert isinstance(result, UGenVector)
        assert len(result) == 2

    def test_multichannel_expansion_synthdef(self):
        """Multichannel expansion produces correct UGen count."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=[440, 443]))
        synthdef = builder.build(name="test")
        # 2 SinOsc + 1 Out = 3
        assert len(synthdef.ugens) == 3

    def test_arithmetic_produces_binary_op(self):
        """SinOsc.ar() * 0.5 produces a BinaryOpUGen(MULTIPLICATION)."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() * 0.5
            Out.ar(bus=0, source=sig)
        synthdef = builder.build(name="test")
        binary_ops = [u for u in synthdef.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) == 1
        assert binary_ops[0].operator == BinaryOperator.MULTIPLICATION

    def test_short_circuit_mul_by_one(self):
        """SinOsc.ar() * 1 returns the SinOsc directly (no BinaryOpUGen)."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() * 1
            Out.ar(bus=0, source=sig)
        synthdef = builder.build(name="test")
        binary_ops = [u for u in synthdef.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) == 0

    def test_short_circuit_add_zero(self):
        """SinOsc.ar() + 0 returns the SinOsc directly."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() + 0
            Out.ar(bus=0, source=sig)
        synthdef = builder.build(name="test")
        binary_ops = [u for u in synthdef.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) == 0

    def test_short_circuit_mul_by_zero(self):
        """SinOsc.ar() * 0 returns a ConstantProxy(0)."""
        with SynthDefBuilder():
            sig = SinOsc.ar() * 0
            # sig should be ConstantProxy(0)
            assert isinstance(sig, ConstantProxy)
            assert float(sig) == 0.0

    def test_negation(self):
        """Negation produces UnaryOpUGen(NEGATIVE)."""
        with SynthDefBuilder() as builder:
            sig = -SinOsc.ar()
            Out.ar(bus=0, source=sig)
        synthdef = builder.build(name="test")
        unary_ops = [u for u in synthdef.ugens if isinstance(u, UnaryOpUGen)]
        assert len(unary_ops) == 1

    def test_pan2_has_two_outputs(self):
        """Pan2 produces a UGen with 2 outputs."""
        with SynthDefBuilder() as builder:
            panned = Pan2.ar(source=SinOsc.ar())
            Out.ar(bus=0, source=panned)
        synthdef = builder.build(name="test")
        pan2s = [u for u in synthdef.ugens if isinstance(u, Pan2)]
        assert len(pan2s) == 1
        assert len(pan2s[0]) == 2

    def test_out_has_zero_outputs(self):
        """Out has 0 output channels (it's an output-only UGen)."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        synthdef = builder.build(name="test")
        outs = [u for u in synthdef.ugens if isinstance(u, Out)]
        assert len(outs) == 1
        assert len(outs[0]) == 0


# ---------------------------------------------------------------------------
# Parameter / Control tests
# ---------------------------------------------------------------------------


class TestParameters:
    def test_builder_creates_parameters(self):
        """SynthDefBuilder with keyword args produces Control UGens."""
        with SynthDefBuilder(frequency=440.0, amplitude=0.5) as builder:
            Out.ar(
                bus=0,
                source=SinOsc.ar(frequency=builder["frequency"]) * builder["amplitude"],
            )
        synthdef = builder.build(name="test")
        controls = [u for u in synthdef.ugens if isinstance(u, Control)]
        assert len(controls) >= 1

    def test_parameter_names_sorted(self):
        """Parameters in the SynthDef are sorted alphabetically."""
        with SynthDefBuilder(zebra=1.0, alpha=2.0, middle=3.0) as builder:
            sig = SinOsc.ar(frequency=builder["alpha"])
            sig = sig * builder["middle"] + builder["zebra"]
            Out.ar(bus=0, source=sig)
        synthdef = builder.build(name="test")
        param_names = list(synthdef.parameters.keys())
        assert param_names == sorted(param_names)

    def test_getitem_returns_output_proxy(self):
        """builder['name'] returns an OutputProxy for scalar parameters."""
        with SynthDefBuilder(freq=440.0) as builder:
            proxy = builder["freq"]
            assert isinstance(proxy, OutputProxy)
            Out.ar(bus=0, source=SinOsc.ar(frequency=proxy))

    def test_multi_value_parameter(self):
        """Parameters with sequence values produce multi-output Parameters."""
        with SynthDefBuilder(frequency=[440, 443]) as builder:
            result = builder["frequency"]
            # Should be a Parameter (multi-output)
            assert isinstance(result, Parameter)
            assert len(result) == 2
            Out.ar(bus=0, source=SinOsc.ar(frequency=result))

    def test_duplicate_parameter_raises(self):
        """Adding a duplicate parameter name raises ValueError."""
        builder = SynthDefBuilder(freq=440.0)
        with pytest.raises(ValueError):
            builder.add_parameter(name="freq", value=880.0)


# ---------------------------------------------------------------------------
# Topological sort tests
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    def test_inputs_before_outputs(self):
        """UGens are ordered so inputs come before outputs."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        synthdef = builder.build(name="test")
        ugens = synthdef.ugens
        # SinOsc must come before Out
        sin_idx = next(i for i, u in enumerate(ugens) if isinstance(u, SinOsc))
        out_idx = next(i for i, u in enumerate(ugens) if isinstance(u, Out))
        assert sin_idx < out_idx

    def test_control_before_ugens(self):
        """Control UGens come before the UGens that use their outputs."""
        with SynthDefBuilder(freq=440.0) as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=builder["freq"]))
        synthdef = builder.build(name="test")
        ugens = synthdef.ugens
        ctrl_idx = next(i for i, u in enumerate(ugens) if isinstance(u, Control))
        sin_idx = next(i for i, u in enumerate(ugens) if isinstance(u, SinOsc))
        assert ctrl_idx < sin_idx

    def test_chain_ordering(self):
        """A chain of UGens is correctly ordered."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            sig = LPF.ar(source=sig, frequency=1000.0)
            Out.ar(bus=0, source=sig)
        synthdef = builder.build(name="test")
        ugens = synthdef.ugens
        sin_idx = next(i for i, u in enumerate(ugens) if isinstance(u, SinOsc))
        lpf_idx = next(i for i, u in enumerate(ugens) if isinstance(u, LPF))
        out_idx = next(i for i, u in enumerate(ugens) if isinstance(u, Out))
        assert sin_idx < lpf_idx < out_idx


# ---------------------------------------------------------------------------
# Envelope tests
# ---------------------------------------------------------------------------


class TestEnvelope:
    def test_adsr_serialize(self):
        """Envelope.adsr().serialize() returns expected float sequence."""
        env = Envelope.adsr()
        serialized = env.serialize()
        # Should be a UGenVector of ConstantProxy values
        assert isinstance(serialized, UGenVector)
        values = [float(x) for x in serialized]
        # initial_amplitude=0, 3 segments, release_node=2, loop_node=-99
        assert values[0] == 0.0  # initial amplitude
        assert values[1] == 3.0  # number of segments
        assert values[2] == 2.0  # release node
        assert values[3] == -99.0  # loop node

    def test_linen_serialize(self):
        """Envelope.linen().serialize() returns expected structure."""
        env = Envelope.linen()
        serialized = env.serialize()
        values = [float(x) for x in serialized]
        assert values[0] == 0.0  # initial amplitude
        assert values[1] == 3.0  # 3 segments (attack, sustain, release)
        assert values[2] == -99.0  # no release node
        assert values[3] == -99.0  # no loop node

    def test_percussive_serialize(self):
        """Envelope.percussive().serialize() returns expected structure."""
        env = Envelope.percussive()
        serialized = env.serialize()
        values = [float(x) for x in serialized]
        assert values[0] == 0.0  # initial amplitude
        assert values[1] == 2.0  # 2 segments

    def test_triangle_serialize(self):
        """Envelope.triangle().serialize() returns expected structure."""
        env = Envelope.triangle()
        serialized = env.serialize()
        values = [float(x) for x in serialized]
        assert values[0] == 0.0  # initial amplitude
        assert values[1] == 2.0  # 2 segments

    def test_envelope_validation(self):
        """Envelope raises on bad input."""
        with pytest.raises(ValueError):
            Envelope(amplitudes=[0])  # need at least 2
        with pytest.raises(ValueError):
            Envelope(amplitudes=[0, 1, 0], durations=[1])  # mismatch

    def test_envgen_wires_envelope(self):
        """EnvGen correctly wires an Envelope as unexpanded input."""
        with SynthDefBuilder() as builder:
            env = EnvGen.kr(
                envelope=Envelope.percussive(),
                done_action=DoneAction.FREE_SYNTH,
            )
            Out.ar(bus=0, source=SinOsc.ar() * env)
        synthdef = builder.build(name="test")
        # Should compile without error
        data = synthdef.compile()
        assert len(data) > 0

    def test_envgen_in_synthdef(self):
        """A SynthDef with EnvGen compiles and has correct UGen types."""
        with SynthDefBuilder(gate=1.0) as builder:
            env = EnvGen.kr(
                envelope=Envelope.adsr(),
                gate=builder["gate"],
                done_action=DoneAction.FREE_SYNTH,
            )
            Out.ar(bus=0, source=SinOsc.ar() * env)
        synthdef = builder.build(name="test")
        ugen_types = {type(u).__name__ for u in synthdef.ugens}
        assert "EnvGen" in ugen_types
        assert "SinOsc" in ugen_types
        assert "Out" in ugen_types
        assert "Control" in ugen_types


# ---------------------------------------------------------------------------
# Concrete UGen tests
# ---------------------------------------------------------------------------


class TestConcreteUGens:
    def test_sinusc_ar(self):
        """SinOsc.ar() returns an OutputProxy at audio rate."""
        with SynthDefBuilder():
            sig = SinOsc.ar()
            assert isinstance(sig, OutputProxy)
            assert sig.calculation_rate == CalculationRate.AUDIO
            Out.ar(bus=0, source=sig)

    def test_saw_ar(self):
        """Saw.ar() returns an OutputProxy at audio rate."""
        with SynthDefBuilder():
            sig = Saw.ar()
            assert isinstance(sig, OutputProxy)
            assert sig.calculation_rate == CalculationRate.AUDIO
            Out.ar(bus=0, source=sig)

    def test_whitenoise_ar(self):
        """WhiteNoise.ar() returns an OutputProxy at audio rate."""
        with SynthDefBuilder():
            sig = WhiteNoise.ar()
            assert isinstance(sig, OutputProxy)
            assert sig.calculation_rate == CalculationRate.AUDIO
            Out.ar(bus=0, source=sig)

    def test_lpf_ar(self):
        """LPF.ar() wires correctly."""
        with SynthDefBuilder() as builder:
            sig = LPF.ar(source=SinOsc.ar(), frequency=1000.0)
            Out.ar(bus=0, source=sig)
        synthdef = builder.build(name="test")
        lpfs = [u for u in synthdef.ugens if isinstance(u, LPF)]
        assert len(lpfs) == 1

    def test_rlpf_ar(self):
        """RLPF.ar() wires correctly."""
        with SynthDefBuilder() as builder:
            sig = RLPF.ar(source=WhiteNoise.ar(), frequency=800.0, reciprocal_of_q=0.3)
            Out.ar(bus=0, source=sig)
        synthdef = builder.build(name="test")
        rlpfs = [u for u in synthdef.ugens if isinstance(u, RLPF)]
        assert len(rlpfs) == 1

    def test_line_kr(self):
        """Line.kr() has done_flag."""
        with SynthDefBuilder() as builder:
            line = Line.kr(start=0.0, stop=1.0, duration=1.0)
            Out.ar(bus=0, source=SinOsc.ar() * line)
        synthdef = builder.build(name="test")
        lines = [u for u in synthdef.ugens if isinstance(u, Line)]
        assert len(lines) == 1
        assert lines[0].has_done_flag

    def test_xline_kr(self):
        """XLine.kr() compiles correctly."""
        with SynthDefBuilder() as builder:
            xl = XLine.kr(start=1.0, stop=0.001, duration=2.0, done_action=2)
            Out.ar(bus=0, source=SinOsc.ar() * xl)
        synthdef = builder.build(name="test")
        xlines = [u for u in synthdef.ugens if isinstance(u, XLine)]
        assert len(xlines) == 1


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_calculation_rate_from_expr(self):
        assert CalculationRate.from_expr(None) == CalculationRate.SCALAR
        assert CalculationRate.from_expr(0) == CalculationRate.SCALAR
        assert CalculationRate.from_expr(1.5) == CalculationRate.SCALAR
        assert CalculationRate.from_expr("audio") == CalculationRate.AUDIO

    def test_calculation_rate_token(self):
        assert CalculationRate.SCALAR.token == "ir"
        assert CalculationRate.CONTROL.token == "kr"
        assert CalculationRate.AUDIO.token == "ar"
        assert CalculationRate.DEMAND.token == "dr"

    def test_parameter_rate_from_expr(self):
        assert ParameterRate.from_expr(None) == ParameterRate.CONTROL
        assert ParameterRate.from_expr("trigger") == ParameterRate.TRIGGER

    def test_envelope_shape_from_expr(self):
        assert EnvelopeShape.from_expr(None) == EnvelopeShape.LINEAR
        assert EnvelopeShape.from_expr("exponential") == EnvelopeShape.EXPONENTIAL


# ---------------------------------------------------------------------------
# SynthDef equality / hashing
# ---------------------------------------------------------------------------


class TestSynthDefEquality:
    def test_equal_synthdefs(self):
        """Two SynthDefs with the same graph and name are equal."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar())
        sd1 = b1.build(name="eq")
        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=SinOsc.ar())
        sd2 = b2.build(name="eq")
        assert sd1 == sd2
        assert hash(sd1) == hash(sd2)

    def test_different_names_not_equal(self):
        """SynthDefs with different names are not equal."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar())
        sd1 = b1.build(name="a")
        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=SinOsc.ar())
        sd2 = b2.build(name="b")
        assert sd1 != sd2

    def test_synthdef_repr(self):
        """SynthDef has a useful repr."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        synthdef = builder.build(name="my_synth")
        assert "SynthDef" in repr(synthdef)
        assert "my_synth" in repr(synthdef)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_empty_synthdef_raises(self):
        """SynthDef with no UGens raises SynthDefError."""
        with pytest.raises(SynthDefError):
            SynthDef([], name="empty")

    def test_cross_scope_raises(self):
        """Using an OutputProxy from a different builder scope raises."""
        with SynthDefBuilder():
            sig1 = SinOsc.ar()
        with pytest.raises(SynthDefError):
            with SynthDefBuilder():
                Out.ar(bus=0, source=sig1)


# ---------------------------------------------------------------------------
# @synthdef decorator tests
# ---------------------------------------------------------------------------


class TestSynthdefDecorator:
    def test_basic_synthdef(self):
        """@synthdef() produces a SynthDef with correct name."""

        @synthdef()
        def sine(freq=440, amp=0.1):
            sig = SinOsc.ar(frequency=freq) * amp
            Out.ar(bus=0, source=sig)

        assert isinstance(sine, SynthDef)
        assert sine.name == "sine"

    def test_synthdef_compiles(self):
        """@synthdef() output compiles to valid SCgf."""

        @synthdef()
        def test_sd(freq=440):
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq))

        data = test_sd.compile()
        assert data[:4] == b"SCgf"

    def test_synthdef_byte_identical(self):
        """@synthdef() output is byte-identical to equivalent SynthDefBuilder usage."""

        @synthdef()
        def test_sd(freq=440, amp=0.5):
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq) * amp)

        with SynthDefBuilder(freq=440.0, amp=0.5) as builder:
            Out.ar(
                bus=0,
                source=SinOsc.ar(frequency=builder["freq"]) * builder["amp"],
            )
        sd_manual = builder.build(name="test_sd")

        assert test_sd.compile() == sd_manual.compile()

    def test_synthdef_with_rates(self):
        """@synthdef('ar', ('kr', 0.5)) sets parameter rates and lags."""

        @synthdef("ar", ("kr", 0.5))
        def rated(freq=440, amp=0.1):
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq) * amp)

        assert isinstance(rated, SynthDef)
        # Check that AudioControl and LagControl are present
        ugen_types = {type(u).__name__ for u in rated.ugens}
        assert "AudioControl" in ugen_types
        assert "LagControl" in ugen_types

    def test_synthdef_with_envelope(self):
        """@synthdef() works with EnvGen and Envelope."""

        @synthdef()
        def env_test(freq=440, gate=1):
            sig = SinOsc.ar(frequency=freq)
            env = EnvGen.kr(
                envelope=Envelope.adsr(),
                gate=gate,
                done_action=DoneAction.FREE_SYNTH,
            )
            Out.ar(bus=0, source=sig * env)

        assert isinstance(env_test, SynthDef)
        data = env_test.compile()
        assert data[:4] == b"SCgf"

    def test_synthdef_default_value(self):
        """Parameters without defaults get value 0.0."""

        @synthdef()
        def test_sd(x):
            Out.ar(bus=0, source=SinOsc.ar(frequency=x))

        assert "x" in test_sd.parameters
        param_obj, _ = test_sd.parameters["x"]
        assert param_obj.value == (0.0,)


# ---------------------------------------------------------------------------
# @ugen decorator tests
# ---------------------------------------------------------------------------


class TestUgenDecorator:
    def test_ugen_creates_rate_methods(self):
        """@ugen(ar=True, kr=True) creates .ar() and .kr() classmethods."""

        @ugen(ar=True, kr=True)
        class TestOsc(UGen):
            frequency = param(440.0)

        assert hasattr(TestOsc, "ar")
        assert hasattr(TestOsc, "kr")

    def test_ugen_sets_ordered_keys(self):
        """@ugen sets _ordered_keys from param declarations."""

        @ugen(ar=True)
        class TestOsc(UGen):
            frequency = param(440.0)
            phase = param(0.0)

        assert TestOsc._ordered_keys == ("frequency", "phase")

    def test_ugen_flags(self):
        """@ugen sets _has_done_flag, _is_pure, _is_output."""

        @ugen(ar=True, has_done_flag=True, is_pure=True)
        class TestUG(UGen):
            source = param()

        assert TestUG._has_done_flag is True
        assert TestUG._is_pure is True

    def test_ugen_compiles(self):
        """A decorator-defined UGen compiles to valid SCgf."""

        @ugen(ar=True, kr=True)
        class MyOsc(UGen):
            frequency = param(440.0)

        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=MyOsc.ar(frequency=880.0))
        sd = builder.build(name="test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        assert b"MyOsc" in data
