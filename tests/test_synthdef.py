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
    control,
    param,
    synthdef,
    ugen,
)
from nanosynth.ugens import (
    LPF,
    DecodeB2,
    Drand,
    Dseq,
    Dser,
    Dseries,
    Dshuf,
    Dwhite,
    Duty,
    In,
    InFeedback,
    Line,
    Out,
    Pan2,
    PanAz,
    PanB2,
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


# ---------------------------------------------------------------------------
# SynthDefBuilder scope error tests
# ---------------------------------------------------------------------------


class TestScopeErrors:
    def test_cross_scope_output_proxy_raises(self):
        """Using an OutputProxy from builder A as input in builder B raises."""
        with SynthDefBuilder():
            sig = SinOsc.ar()
        with pytest.raises(SynthDefError, match="different scope"):
            with SynthDefBuilder():
                Out.ar(bus=0, source=sig)

    def test_cross_scope_arithmetic_raises(self):
        """Arithmetic between UGens from different scopes raises."""
        with SynthDefBuilder():
            sig = SinOsc.ar()
        with pytest.raises(SynthDefError, match="different scope"):
            with SynthDefBuilder():
                Out.ar(bus=0, source=sig * 0.5)

    def test_cross_scope_parameter_raises(self):
        """Using a parameter proxy from one builder inside another raises."""
        with SynthDefBuilder(freq=440.0) as b1:
            freq_proxy = b1["freq"]
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq_proxy))
        with pytest.raises(SynthDefError, match="different scope"):
            with SynthDefBuilder():
                Out.ar(bus=0, source=SinOsc.ar(frequency=freq_proxy))

    def test_cross_scope_chained_raises(self):
        """A chain of UGens from scope A used in scope B raises."""
        with SynthDefBuilder():
            sig = LPF.ar(source=SinOsc.ar(), frequency=1000.0)
        with pytest.raises(SynthDefError, match="different scope"):
            with SynthDefBuilder():
                Out.ar(bus=0, source=sig)

    def test_same_scope_ok(self):
        """Using UGens within the same scope works fine."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            sig = LPF.ar(source=sig, frequency=1000.0)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="same_scope")
        assert sd.compile()[:4] == b"SCgf"

    def test_nested_scope_inner_to_outer_raises(self):
        """UGen created in an inner scope cannot be used after exiting it."""
        with SynthDefBuilder():
            with SynthDefBuilder():
                inner_sig = SinOsc.ar()
            with pytest.raises(SynthDefError, match="different scope"):
                Out.ar(bus=0, source=inner_sig)


# ---------------------------------------------------------------------------
# Graph optimization tests
# ---------------------------------------------------------------------------


class TestGraphOptimization:
    def test_optimize_eliminates_unused_pure_ugen(self):
        """A pure UGen with no dependents is removed by optimization."""
        with SynthDefBuilder() as builder:
            SinOsc.ar()  # unused pure UGen
            Out.ar(bus=0, source=WhiteNoise.ar())
        sd_opt = builder.build(name="opt", optimize=True)
        # SinOsc should be eliminated -- only WhiteNoise + Out remain
        ugen_types = [type(u).__name__ for u in sd_opt.ugens]
        assert "SinOsc" not in ugen_types
        assert "WhiteNoise" in ugen_types
        assert "Out" in ugen_types

    def test_no_optimize_keeps_unused_pure_ugen(self):
        """Without optimization, unused pure UGens are retained."""
        with SynthDefBuilder() as builder:
            SinOsc.ar()  # unused pure UGen
            Out.ar(bus=0, source=WhiteNoise.ar())
        sd_no_opt = builder.build(name="noopt", optimize=False)
        ugen_types = [type(u).__name__ for u in sd_no_opt.ugens]
        assert "SinOsc" in ugen_types

    def test_optimize_keeps_used_pure_ugen(self):
        """A pure UGen that feeds into another UGen is NOT eliminated."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()  # used -- feeds into Out
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="used", optimize=True)
        ugen_types = [type(u).__name__ for u in sd.ugens]
        assert "SinOsc" in ugen_types

    def test_optimize_cascade_eliminates_chain(self):
        """Optimization cascades: if A feeds only B, and B is unused, both go."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            LPF.ar(source=sig, frequency=1000.0)  # unused chain
            Out.ar(bus=0, source=WhiteNoise.ar())
        sd = builder.build(name="cascade", optimize=True)
        ugen_types = [type(u).__name__ for u in sd.ugens]
        assert "SinOsc" not in ugen_types
        assert "LPF" not in ugen_types

    def test_optimize_keeps_impure_ugen(self):
        """Impure UGens (is_pure=False) are never eliminated, even if unused."""
        with SynthDefBuilder() as builder:
            WhiteNoise.ar()  # impure, unused
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="impure", optimize=True)
        ugen_types = [type(u).__name__ for u in sd.ugens]
        # WhiteNoise is not pure, so optimization should not remove it
        assert "WhiteNoise" in ugen_types

    def test_optimize_partial_chain(self):
        """If A feeds B and C, but only B is used, A and B survive, C is eliminated."""
        with SynthDefBuilder() as builder:
            osc = SinOsc.ar()
            LPF.ar(source=osc, frequency=500.0)  # unused
            Out.ar(bus=0, source=osc)  # osc is used via Out
        sd = builder.build(name="partial", optimize=True)
        ugen_types = [type(u).__name__ for u in sd.ugens]
        assert "SinOsc" in ugen_types
        assert "LPF" not in ugen_types
        assert "Out" in ugen_types

    def test_optimize_vs_no_optimize_ugen_count(self):
        """Optimized build has fewer UGens than non-optimized when dead code exists."""
        with SynthDefBuilder() as b1:
            SinOsc.ar()  # dead
            SinOsc.ar(frequency=880.0)  # dead
            Out.ar(bus=0, source=WhiteNoise.ar())
        sd_opt = b1.build(name="opt", optimize=True)

        with SynthDefBuilder() as b2:
            SinOsc.ar()
            SinOsc.ar(frequency=880.0)
            Out.ar(bus=0, source=WhiteNoise.ar())
        sd_noopt = b2.build(name="noopt", optimize=False)

        assert len(sd_opt.ugens) < len(sd_noopt.ugens)


# ---------------------------------------------------------------------------
# Envelope factory method tests
# ---------------------------------------------------------------------------


class TestEnvelopeFactories:
    def test_linen_structure(self):
        """Envelope.linen() has 3 segments, no release node."""
        env = Envelope.linen(
            attack_time=0.1, sustain_time=2.0, release_time=0.5, level=0.8
        )
        assert len(env.envelope_segments) == 3
        assert env.release_node is None
        assert env.initial_amplitude == 0

    def test_linen_amplitudes(self):
        """Envelope.linen() amplitudes: 0 -> level -> level -> 0."""
        env = Envelope.linen(level=0.7)
        values = [float(x) for x in env.serialize()]
        assert values[0] == 0.0  # initial
        # Segment amplitudes: level, level, 0
        # Serialization: [init, n_seg, rel_node, loop_node, amp, dur, shape, curve, ...]
        assert values[4] == 0.7  # first target (attack -> level)
        assert values[8] == 0.7  # second target (sustain at level)
        assert values[12] == 0.0  # third target (release -> 0)

    def test_linen_custom_curve(self):
        """Envelope.linen() respects the curve parameter."""
        env = Envelope.linen(curve=5)
        values = [float(x) for x in env.serialize()]
        # curve values at positions 7, 11, 15 (shape=5 means custom curve)
        assert values[6] == 5.0  # shape for segment 1
        assert values[10] == 5.0  # shape for segment 2

    def test_linen_compiles_with_envgen(self):
        """Envelope.linen() works inside EnvGen in a SynthDef."""
        with SynthDefBuilder() as builder:
            env = EnvGen.kr(
                envelope=Envelope.linen(
                    attack_time=0.1, sustain_time=1.0, release_time=0.2
                ),
                done_action=DoneAction.FREE_SYNTH,
            )
            Out.ar(bus=0, source=SinOsc.ar() * env)
        sd = builder.build(name="linen_test")
        assert sd.compile()[:4] == b"SCgf"

    def test_triangle_structure(self):
        """Envelope.triangle() has 2 segments, no release node."""
        env = Envelope.triangle(duration=2.0, amplitude=0.5)
        assert len(env.envelope_segments) == 2
        assert env.release_node is None
        assert env.initial_amplitude == 0

    def test_triangle_symmetry(self):
        """Envelope.triangle() splits duration equally."""
        env = Envelope.triangle(duration=4.0, amplitude=1.0)
        values = [float(x) for x in env.serialize()]
        # Segment durations at positions 5 and 9
        assert values[5] == 2.0  # rise duration = total/2
        assert values[9] == 2.0  # fall duration = total/2

    def test_triangle_amplitudes(self):
        """Envelope.triangle() amplitudes: 0 -> amplitude -> 0."""
        env = Envelope.triangle(amplitude=0.6)
        values = [float(x) for x in env.serialize()]
        assert values[0] == 0.0  # initial
        assert values[4] == 0.6  # peak
        assert values[8] == 0.0  # end

    def test_triangle_compiles_with_envgen(self):
        """Envelope.triangle() works inside EnvGen in a SynthDef."""
        with SynthDefBuilder() as builder:
            env = EnvGen.kr(
                envelope=Envelope.triangle(duration=1.0),
                done_action=DoneAction.FREE_SYNTH,
            )
            Out.ar(bus=0, source=SinOsc.ar() * env)
        sd = builder.build(name="tri_test")
        assert sd.compile()[:4] == b"SCgf"

    def test_asr_structure(self):
        """Envelope.asr() has 2 segments with release_node=1."""
        env = Envelope.asr(attack_time=0.05, sustain=0.8, release_time=1.5)
        assert len(env.envelope_segments) == 2
        assert env.release_node == 1
        assert env.initial_amplitude == 0

    def test_asr_amplitudes(self):
        """Envelope.asr() amplitudes: 0 -> sustain -> 0."""
        env = Envelope.asr(sustain=0.9)
        values = [float(x) for x in env.serialize()]
        assert values[0] == 0.0  # initial
        assert values[2] == 1.0  # release_node = 1
        assert values[4] == 0.9  # sustain level
        assert values[8] == 0.0  # release to 0

    def test_asr_compiles_with_envgen(self):
        """Envelope.asr() works with gate inside EnvGen."""
        with SynthDefBuilder(gate=1.0) as builder:
            env = EnvGen.kr(
                envelope=Envelope.asr(attack_time=0.01, sustain=1.0, release_time=0.5),
                gate=builder["gate"],
                done_action=DoneAction.FREE_SYNTH,
            )
            Out.ar(bus=0, source=SinOsc.ar() * env)
        sd = builder.build(name="asr_test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        ugen_types = {type(u).__name__ for u in sd.ugens}
        assert "EnvGen" in ugen_types


# ---------------------------------------------------------------------------
# Multi-channel expansion tests (is_multichannel UGens)
# ---------------------------------------------------------------------------


class TestMultiChannelUGens:
    def test_in_ar_channel_count(self):
        """In.ar with channel_count=2 produces a UGen with 2 outputs."""
        with SynthDefBuilder() as builder:
            sig = In.ar(bus=0, channel_count=2)
            assert isinstance(sig, In)
            assert len(sig) == 2
            Out.ar(bus=0, source=[sig[0], sig[1]])
        sd = builder.build(name="in_test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_in_ar_single_channel(self):
        """In.ar with channel_count=1 produces a single OutputProxy."""
        with SynthDefBuilder() as builder:
            sig = In.ar(bus=8, channel_count=1)
            assert isinstance(sig, OutputProxy)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="in_mono")
        assert sd.compile()[:4] == b"SCgf"

    def test_in_kr(self):
        """In.kr with channel_count=4 produces a UGen with 4 outputs."""
        with SynthDefBuilder() as builder:
            sig = In.kr(bus=0, channel_count=4)
            assert isinstance(sig, In)
            assert len(sig) == 4
            Out.kr(bus=0, source=[sig[0], sig[1], sig[2], sig[3]])
        sd = builder.build(name="in_kr4")
        assert sd.compile()[:4] == b"SCgf"

    def test_infeedback_multichannel(self):
        """InFeedback.ar with channel_count=2 produces 2 outputs."""
        with SynthDefBuilder() as builder:
            sig = InFeedback.ar(bus=0, channel_count=2)
            assert isinstance(sig, InFeedback)
            assert len(sig) == 2
            Out.ar(bus=0, source=[sig[0], sig[1]])
        sd = builder.build(name="infb_test")
        assert sd.compile()[:4] == b"SCgf"

    def test_panaz_multichannel(self):
        """PanAz.ar with channel_count=4 produces a 4-output UGen."""
        with SynthDefBuilder() as builder:
            sig = PanAz.ar(source=SinOsc.ar(), channel_count=4)
            assert isinstance(sig, PanAz)
            assert len(sig) == 4
            Out.ar(bus=0, source=[sig[0], sig[1], sig[2], sig[3]])
        sd = builder.build(name="panaz_test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        assert b"PanAz" in data

    def test_panaz_channel_count_3(self):
        """PanAz with non-default channel_count works."""
        with SynthDefBuilder() as builder:
            sig = PanAz.ar(source=SinOsc.ar(), channel_count=3)
            assert len(sig) == 3
            Out.ar(bus=0, source=[sig[0], sig[1], sig[2]])
        sd = builder.build(name="panaz3")
        assert sd.compile()[:4] == b"SCgf"

    def test_decodeb2_default_channels(self):
        """DecodeB2 defaults to channel_count=4."""
        with SynthDefBuilder() as builder:
            # PanB2 produces 3 outputs (w, x, y)
            encoded = PanB2.ar(source=SinOsc.ar(), azimuth=0.0)
            decoded = DecodeB2.ar(w=encoded[0], x=encoded[1], y=encoded[2])
            assert isinstance(decoded, DecodeB2)
            assert len(decoded) == 4
            Out.ar(bus=0, source=[decoded[0], decoded[1], decoded[2], decoded[3]])
        sd = builder.build(name="decodeb2_test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        assert b"DecodeB2" in data

    def test_decodeb2_custom_channels(self):
        """DecodeB2 with custom channel_count overrides the default."""
        with SynthDefBuilder() as builder:
            encoded = PanB2.ar(source=SinOsc.ar(), azimuth=0.0)
            decoded = DecodeB2.ar(
                w=encoded[0], x=encoded[1], y=encoded[2], channel_count=6
            )
            assert len(decoded) == 6
            Out.ar(
                bus=0,
                source=[decoded[i] for i in range(6)],
            )
        sd = builder.build(name="decodeb2_6ch")
        assert sd.compile()[:4] == b"SCgf"

    def test_multichannel_indexing(self):
        """Multi-channel UGens support integer and slice indexing."""
        with SynthDefBuilder() as builder:
            sig = In.ar(bus=0, channel_count=4)
            # Integer index
            assert isinstance(sig[0], OutputProxy)
            # Slice
            sliced = sig[1:3]
            assert isinstance(sliced, UGenVector)
            assert len(sliced) == 2
            Out.ar(bus=0, source=[sig[0], sig[1], sig[2], sig[3]])
        builder.build(name="idx_test")


# ---------------------------------------------------------------------------
# compile_synthdefs with multiple SynthDefs
# ---------------------------------------------------------------------------


class TestCompileSynthdefs:
    def test_three_synthdefs(self):
        """compile_synthdefs handles three SynthDefs."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar())
        sd1 = b1.build(name="alpha")

        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=Saw.ar())
        sd2 = b2.build(name="beta")

        with SynthDefBuilder() as b3:
            Out.ar(bus=0, source=WhiteNoise.ar())
        sd3 = b3.build(name="gamma")

        data = compile_synthdefs(sd1, sd2, sd3)
        assert data[:4] == b"SCgf"
        count = struct.unpack(">H", data[8:10])[0]
        assert count == 3

    def test_names_present_in_compiled_output(self):
        """All SynthDef names appear in the compiled binary."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar())
        sd1 = b1.build(name="first")

        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=Saw.ar())
        sd2 = b2.build(name="second")

        data = compile_synthdefs(sd1, sd2)
        assert b"first" in data
        assert b"second" in data

    def test_anonymous_names(self):
        """compile_synthdefs with use_anonymous_names=True uses MD5 hashes."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar())
        sd1 = b1.build(name="named")

        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=Saw.ar())
        sd2 = b2.build(name="also_named")

        data = compile_synthdefs(sd1, sd2, use_anonymous_names=True)
        assert b"named" not in data
        # Anonymous names are 32-char MD5 hashes
        assert sd1.anonymous_name.encode() in data
        assert sd2.anonymous_name.encode() in data

    def test_single_synthdef_matches_compile(self):
        """compile_synthdefs(sd) produces the same bytes as sd.compile()."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=440.0))
        sd = builder.build(name="solo")
        assert compile_synthdefs(sd) == sd.compile()

    def test_different_graphs_produce_different_output(self):
        """Two SynthDefs with different UGen graphs produce different bytes."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar())
        sd1 = b1.build(name="x")

        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=LPF.ar(source=Saw.ar(), frequency=800.0))
        sd2 = b2.build(name="x")

        # Same name, different graph
        assert sd1.compile() != sd2.compile()


# ---------------------------------------------------------------------------
# Demand-rate UGen tests
# ---------------------------------------------------------------------------


class TestDemandUGens:
    def test_dseq_compiles(self):
        """Dseq.dr inside Duty.kr compiles to valid SCgf."""
        with SynthDefBuilder() as builder:
            freq = Duty.kr(
                duration=0.5,
                level=Dseq.dr(repeats=2, sequence=[440.0, 550.0, 660.0]),
            )
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq))
        sd = builder.build(name="dseq_test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        ugen_types = {type(u).__name__ for u in sd.ugens}
        assert "Dseq" in ugen_types
        assert "Duty" in ugen_types

    def test_drand_compiles(self):
        """Drand.dr inside Duty.kr compiles to valid SCgf."""
        with SynthDefBuilder() as builder:
            freq = Duty.kr(
                duration=0.25,
                level=Drand.dr(repeats=8, sequence=[440.0, 550.0, 660.0, 880.0]),
            )
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq))
        sd = builder.build(name="drand_test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        ugen_types = {type(u).__name__ for u in sd.ugens}
        assert "Drand" in ugen_types

    def test_dseries_compiles(self):
        """Dseries.dr compiles correctly."""
        with SynthDefBuilder() as builder:
            freq = Duty.kr(
                duration=0.5,
                level=Dseries.dr(start=200.0, step=100.0, length=5),
            )
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq))
        sd = builder.build(name="dseries_test")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        assert b"Dseries" in data

    def test_dwhite_compiles(self):
        """Dwhite.dr compiles correctly."""
        with SynthDefBuilder() as builder:
            freq = Duty.kr(
                duration=0.25,
                level=Dwhite.dr(minimum=200.0, maximum=800.0, length=10),
            )
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq))
        sd = builder.build(name="dwhite_test")
        assert sd.compile()[:4] == b"SCgf"

    def test_dser_compiles(self):
        """Dser.dr (like Dseq but truncates) compiles correctly."""
        with SynthDefBuilder() as builder:
            freq = Duty.kr(
                duration=0.5,
                level=Dser.dr(repeats=3, sequence=[440.0, 550.0]),
            )
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq))
        sd = builder.build(name="dser_test")
        assert sd.compile()[:4] == b"SCgf"

    def test_dshuf_compiles(self):
        """Dshuf.dr (shuffled sequence) compiles correctly."""
        with SynthDefBuilder() as builder:
            freq = Duty.kr(
                duration=0.25,
                level=Dshuf.dr(repeats=2, sequence=[440.0, 550.0, 660.0]),
            )
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq))
        sd = builder.build(name="dshuf_test")
        assert sd.compile()[:4] == b"SCgf"

    def test_duty_ar(self):
        """Duty.ar (audio-rate demand reading) compiles correctly."""
        with SynthDefBuilder() as builder:
            sig = Duty.ar(
                duration=0.01,
                level=Dseq.dr(repeats=1, sequence=[0.5, -0.5, 0.3, -0.3]),
            )
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="duty_ar_test")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_demand_rate_is_demand(self):
        """Dseq.dr() has calculation_rate == DEMAND."""
        with SynthDefBuilder() as builder:
            d = Dseq.dr(repeats=1, sequence=[1.0, 2.0])
            assert d.ugen.calculation_rate == CalculationRate.DEMAND
            freq = Duty.kr(duration=0.5, level=d)
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq))
        builder.build(name="rate_test")

    def test_nested_demand_ugens(self):
        """Demand UGens can be nested (Dseq reading from Drand)."""
        with SynthDefBuilder() as builder:
            # Use Drand to select durations, Dseq for pitches
            dur = Drand.dr(repeats=16, sequence=[0.125, 0.25, 0.5])
            freq = Dseq.dr(repeats=4, sequence=[440.0, 550.0, 660.0, 880.0])
            sig = Duty.ar(duration=dur, level=freq)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="nested_demand")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        ugen_types = {type(u).__name__ for u in sd.ugens}
        assert "Drand" in ugen_types
        assert "Dseq" in ugen_types


# ---------------------------------------------------------------------------
# @synthdef decorator extended coverage
# ---------------------------------------------------------------------------


class TestSynthdefDecoratorExtended:
    def test_trigger_rate_parameter(self):
        """@synthdef('trigger') produces a TrigControl."""

        @synthdef("trigger")
        def trig_test(trig=0):
            Out.ar(bus=0, source=SinOsc.ar() * trig)

        ugen_types = {type(u).__name__ for u in trig_test.ugens}
        assert "TrigControl" in ugen_types

    def test_multiple_rates(self):
        """@synthdef with mixed rates produces corresponding control types."""

        @synthdef("ar", "kr", "trigger")
        def multi_rate(audio_in=0, ctrl_in=440, trig_in=0):
            Out.ar(bus=0, source=SinOsc.ar(frequency=ctrl_in) * audio_in * trig_in)

        ugen_types = {type(u).__name__ for u in multi_rate.ugens}
        assert "AudioControl" in ugen_types
        assert "TrigControl" in ugen_types
        # ctrl_in is kr without lag, so it's a regular Control
        assert "Control" in ugen_types

    def test_lag_parameter(self):
        """@synthdef(('kr', 0.1)) produces a LagControl."""

        @synthdef(("kr", 0.1))
        def lag_test(freq=440):
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq))

        ugen_types = {type(u).__name__ for u in lag_test.ugens}
        assert "LagControl" in ugen_types

    def test_no_default_gets_zero(self):
        """Parameters without defaults get value 0.0."""

        @synthdef()
        def zero_default(a, b):
            Out.ar(bus=0, source=SinOsc.ar(frequency=a) * b)

        for name in ("a", "b"):
            param_obj, _ = zero_default.parameters[name]
            assert param_obj.value == (0.0,)

    def test_complex_synthdef(self):
        """@synthdef with envelope, filter, and multiple parameters."""

        @synthdef()
        def complex_sd(freq=440, cutoff=2000, amp=0.3, gate=1):
            sig = Saw.ar(frequency=freq)
            sig = LPF.ar(source=sig, frequency=cutoff)
            env = EnvGen.kr(
                envelope=Envelope.adsr(),
                gate=gate,
                done_action=DoneAction.FREE_SYNTH,
            )
            Out.ar(bus=0, source=Pan2.ar(source=sig * env * amp))

        assert isinstance(complex_sd, SynthDef)
        data = complex_sd.compile()
        assert data[:4] == b"SCgf"
        assert b"complex_sd" in data
        ugen_types = {type(u).__name__ for u in complex_sd.ugens}
        assert "Saw" in ugen_types
        assert "LPF" in ugen_types
        assert "EnvGen" in ugen_types
        assert "Pan2" in ugen_types

    def test_decorator_name_matches_function(self):
        """The SynthDef name always matches the function name."""

        @synthdef()
        def my_custom_name(x=1):
            Out.ar(bus=0, source=SinOsc.ar(frequency=x))

        assert my_custom_name.name == "my_custom_name"

    def test_excess_rate_args_ignored(self):
        """Extra rate args beyond the parameter count are silently ignored."""

        @synthdef("ar", "kr", "trigger", "kr")  # 4 rate args, only 2 params
        def two_params(a=0, b=0):
            Out.ar(bus=0, source=SinOsc.ar(frequency=a) * b)

        assert isinstance(two_params, SynthDef)
        ugen_types = {type(u).__name__ for u in two_params.ugens}
        assert "AudioControl" in ugen_types


# ---------------------------------------------------------------------------
# dump_ugens tests
# ---------------------------------------------------------------------------


class TestDumpUgens:
    def test_basic_output(self):
        """dump_ugens() returns a string with SynthDef name header."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="test")
        output = sd.dump_ugens()
        assert output.startswith("SynthDef: test")

    def test_contains_ugen_names(self):
        """dump_ugens() output contains all UGen type names."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="test")
        output = sd.dump_ugens()
        assert "SinOsc" in output
        assert "Out" in output

    def test_contains_rate_tokens(self):
        """dump_ugens() output shows rate tokens (ar, kr)."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="test")
        output = sd.dump_ugens()
        assert ".ar" in output

    def test_control_shows_parameter_names(self):
        """dump_ugens() shows parameter names for Control UGens."""
        with SynthDefBuilder(frequency=440.0, amplitude=0.5) as builder:
            Out.ar(
                bus=0,
                source=SinOsc.ar(frequency=builder["frequency"]) * builder["amplitude"],
            )
        sd = builder.build(name="test")
        output = sd.dump_ugens()
        assert "amplitude" in output
        assert "frequency" in output

    def test_binary_op_shows_operator(self):
        """dump_ugens() shows operator name for BinaryOpUGen."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar() * 0.5)
        sd = builder.build(name="test")
        output = sd.dump_ugens()
        assert "MULTIPLICATION" in output

    def test_multichannel_shows_output_count(self):
        """dump_ugens() shows output count for multi-output UGens."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=Pan2.ar(source=SinOsc.ar()))
        sd = builder.build(name="test")
        output = sd.dump_ugens()
        assert "2 outputs" in output

    def test_complex_graph(self):
        """dump_ugens() works on a complex graph with envelope."""
        with SynthDefBuilder(freq=440.0, gate=1.0) as builder:
            sig = SinOsc.ar(frequency=builder["freq"])
            env = EnvGen.kr(
                envelope=Envelope.adsr(),
                gate=builder["gate"],
                done_action=DoneAction.FREE_SYNTH,
            )
            Out.ar(bus=0, source=Pan2.ar(source=sig * env))
        sd = builder.build(name="complex")
        output = sd.dump_ugens()
        assert "SynthDef: complex" in output
        assert "Control" in output
        assert "SinOsc" in output
        assert "EnvGen" in output
        assert "Pan2" in output
        # Should have numbered lines
        assert "  0:" in output

    def test_anonymous_synthdef_name(self):
        """dump_ugens() shows MD5 hash for anonymous SynthDef."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build()
        output = sd.dump_ugens()
        assert f"SynthDef: {sd.anonymous_name}" in output


# ---------------------------------------------------------------------------
# SynthDef.send() / .play() tests
# ---------------------------------------------------------------------------


class TestSynthDefSendPlay:
    def test_send_calls_server(self):
        """send() calls server.send_synthdef()."""
        from unittest.mock import MagicMock

        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="test")
        server = MagicMock()
        sd.send(server)
        server.send_synthdef.assert_called_once_with(sd)

    def test_play_returns_node_id(self):
        """play() sends the SynthDef and returns a node ID."""
        from unittest.mock import MagicMock

        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="test")
        server = MagicMock()
        server.synth.return_value = 1000
        node_id = sd.play(server, frequency=440.0)
        assert node_id == 1000
        server.send_synthdef.assert_called_once_with(sd)
        server.synth.assert_called_once_with(
            "test", target=1, action=0, frequency=440.0
        )

    def test_play_custom_target_action(self):
        """play() forwards target and action to server.synth()."""
        from unittest.mock import MagicMock

        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="test")
        server = MagicMock()
        server.synth.return_value = 1001
        sd.play(server, target=2, action=1)
        server.synth.assert_called_once_with("test", target=2, action=1)


# ---------------------------------------------------------------------------
# Extended operator tests
# ---------------------------------------------------------------------------


from nanosynth.synthdef import UnaryOperator  # noqa: E402


class TestExtendedOperators:
    """Tests for extended BinaryOperator/UnaryOperator enum values and methods."""

    # -- Dunder methods produce correct BinaryOpUGen ---------------------------

    def test_pow_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() ** 2
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.POWER for o in ops)

    def test_rpow_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = 2 ** SinOsc.ar()
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.POWER for o in ops)

    def test_floordiv_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() // 2
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.INTEGER_DIVISION for o in ops)

    def test_rfloordiv_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = 10 // SinOsc.ar()
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.INTEGER_DIVISION for o in ops)

    def test_le_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() <= 0.5
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.LESS_THAN_OR_EQUAL for o in ops)

    def test_ge_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() >= 0.5
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.GREATER_THAN_OR_EQUAL for o in ops)

    def test_and_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() & SinOsc.ar(frequency=880)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.BITWISE_AND for o in ops)

    def test_or_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() | SinOsc.ar(frequency=880)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.BITWISE_OR for o in ops)

    def test_xor_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() ^ SinOsc.ar(frequency=880)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.BITWISE_XOR for o in ops)

    def test_lshift_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() << 2
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.SHIFT_LEFT for o in ops)

    def test_rshift_produces_binary_op(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar() >> 2
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.SHIFT_RIGHT for o in ops)

    # -- POWER optimizations ---------------------------------------------------

    def test_pow_zero_returns_one(self):
        with SynthDefBuilder():
            sig = SinOsc.ar() ** 0
            assert isinstance(sig, ConstantProxy)
            assert float(sig) == 1.0

    def test_pow_one_returns_self(self):
        with SynthDefBuilder() as builder:
            osc = SinOsc.ar()
            sig = osc**1
            assert isinstance(sig, OutputProxy)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert not any(o.operator == BinaryOperator.POWER for o in ops)

    # -- Named binary methods --------------------------------------------------

    def test_min(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar().min_(0.5)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.MINIMUM for o in ops)

    def test_max(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar().max_(0.0)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.MAXIMUM for o in ops)

    def test_clip2(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar().clip2(0.5)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.CLIP2 for o in ops)

    # -- Named unary methods ---------------------------------------------------

    def test_midicps(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar().midicps()
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, UnaryOpUGen)]
        assert any(o.operator == UnaryOperator.MIDICPS for o in ops)

    def test_tanh(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar().tanh_()
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, UnaryOpUGen)]
        assert any(o.operator == UnaryOperator.TANH for o in ops)

    def test_softclip(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar().softclip()
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, UnaryOpUGen)]
        assert any(o.operator == UnaryOperator.SOFTCLIP for o in ops)

    def test_squared(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar().squared()
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, UnaryOpUGen)]
        assert any(o.operator == UnaryOperator.SQUARED for o in ops)

    def test_distort(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar().distort()
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, UnaryOpUGen)]
        assert any(o.operator == UnaryOperator.DISTORT for o in ops)

    # -- Constant folding for new operators ------------------------------------

    def test_pow_constant_folding(self):
        with SynthDefBuilder():
            result = ConstantProxy(2.0) ** ConstantProxy(3.0)
            assert isinstance(result, ConstantProxy)
            assert float(result) == 8.0

    def test_floordiv_constant_folding(self):
        with SynthDefBuilder():
            result = ConstantProxy(7.0) // ConstantProxy(2.0)
            assert isinstance(result, ConstantProxy)
            assert float(result) == 3.0

    def test_min_constant_folding(self):
        result = ConstantProxy(3.0).min_(ConstantProxy(5.0))
        assert isinstance(result, ConstantProxy)
        assert float(result) == 3.0

    def test_max_constant_folding(self):
        result = ConstantProxy(3.0).max_(ConstantProxy(5.0))
        assert isinstance(result, ConstantProxy)
        assert float(result) == 5.0

    def test_sqrt_constant_folding(self):

        result = ConstantProxy(9.0).sqrt_()
        assert isinstance(result, ConstantProxy)
        assert abs(float(result) - 3.0) < 1e-10

    def test_sin_constant_folding(self):

        result = ConstantProxy(0.0).sin_()
        assert isinstance(result, ConstantProxy)
        assert abs(float(result)) < 1e-10

    def test_le_constant_folding(self):
        result = ConstantProxy(3.0) <= ConstantProxy(5.0)
        assert isinstance(result, ConstantProxy)
        assert float(result) == 1.0  # True -> 1.0

    def test_ge_constant_folding(self):
        result = ConstantProxy(3.0) >= ConstantProxy(5.0)
        assert isinstance(result, ConstantProxy)
        assert float(result) == 0.0  # False -> 0.0

    # -- equal / not_equal methods ---------------------------------------------

    def test_equal_method(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar().equal(0.0)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.EQUAL for o in ops)

    def test_not_equal_method(self):
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar().not_equal(0.0)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="test")
        ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert any(o.operator == BinaryOperator.NOT_EQUAL for o in ops)


class TestUGenOperableBoolTrap:
    """Test that UGenOperable raises TypeError in boolean context."""

    def test_output_proxy_bool_raises(self):
        with SynthDefBuilder():
            sig = SinOsc.ar()
            with pytest.raises(
                TypeError, match="Cannot use UGen expressions in boolean context"
            ):
                if sig:
                    pass

    def test_constant_proxy_bool_raises(self):
        cp = ConstantProxy(1.0)
        with pytest.raises(
            TypeError, match="Cannot use UGen expressions in boolean context"
        ):
            if cp:
                pass

    def test_ugen_vector_bool_raises(self):
        with SynthDefBuilder():
            sig = SinOsc.ar(frequency=[440, 880])
            with pytest.raises(
                TypeError, match="Cannot use UGen expressions in boolean context"
            ):
                if sig:
                    pass

    def test_comparison_result_bool_raises(self):
        with SynthDefBuilder():
            sig = SinOsc.ar()
            comparison = sig > 0
            with pytest.raises(
                TypeError, match="Cannot use UGen expressions in boolean context"
            ):
                if comparison:
                    pass

    def test_constant_proxy_eq_still_returns_bool(self):
        """ConstantProxy.__eq__ should still return a plain bool."""
        cp1 = ConstantProxy(1.0)
        cp2 = ConstantProxy(1.0)
        assert cp1 == cp2  # Should work fine, returns bool
        assert not (cp1 == ConstantProxy(2.0))


class TestThreadLocalGuard:
    """Test that the centralized _get_active_builders works across threads."""

    def test_builders_isolated_across_threads(self):
        import threading

        from nanosynth.synthdef import _get_active_builders

        results: list[int] = []

        def thread_fn() -> None:
            builders = _get_active_builders()
            results.append(len(builders))

        t = threading.Thread(target=thread_fn)
        t.start()
        t.join()
        assert results == [0]

    def test_builders_accessible_in_main_thread(self):
        from nanosynth.synthdef import _get_active_builders

        builders = _get_active_builders()
        assert isinstance(builders, list)


class TestTopologicalSortDescendantOrdering:
    """Test that descendants are sorted by their position in the UGen list."""

    def test_sort_produces_valid_order(self):
        """A graph with branching should sort correctly."""
        with SynthDefBuilder(freq=440.0) as builder:
            sig = SinOsc.ar(frequency=builder["freq"])
            filtered = LPF.ar(source=sig, frequency=1000)
            Out.ar(bus=0, source=filtered)
        sd = builder.build(name="test")
        # The topological sort should place Control before SinOsc,
        # SinOsc before LPF, and LPF before Out
        ugen_types = [type(u).__name__ for u in sd.ugens]
        assert ugen_types.index("Control") < ugen_types.index("SinOsc")
        assert ugen_types.index("SinOsc") < ugen_types.index("LPF")
        assert ugen_types.index("LPF") < ugen_types.index("Out")

    def test_fan_out_graph_sorts_correctly(self):
        """A single source feeding multiple consumers should sort correctly."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar(frequency=440)
            # Two independent consumers of the same signal
            left = sig * 0.5
            right = sig * 0.3
            Out.ar(bus=0, source=left)
            Out.ar(bus=1, source=right)
        sd = builder.build(name="test", optimize=False)
        # SinOsc should come before both BinaryOpUGens
        ugen_types = [type(u).__name__ for u in sd.ugens]
        sin_idx = ugen_types.index("SinOsc")
        for i, u in enumerate(sd.ugens):
            if isinstance(u, BinaryOpUGen):
                assert i > sin_idx


class TestServerProtocol:
    """Test that ServerProtocol structural typing works."""

    def test_protocol_isinstance_check(self):
        from nanosynth.synthdef import ServerProtocol

        class FakeServer:
            def send_synthdef(self, synthdef: SynthDef) -> None:
                pass

            def synth(
                self, name: str, target: int = 1, action: int = 0, **params: float
            ) -> int:
                return 0

        assert isinstance(FakeServer(), ServerProtocol)

    def test_synthdef_send_with_protocol(self):
        from unittest.mock import MagicMock

        mock_server = MagicMock(spec=["send_synthdef", "synth"])
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="test")
        sd.send(mock_server)
        mock_server.send_synthdef.assert_called_once_with(sd)


# ---------------------------------------------------------------------------
# control() function tests
# ---------------------------------------------------------------------------


class TestControlFunction:
    def test_control_returns_parameter(self):
        p = control(440.0)
        assert isinstance(p, Parameter)
        assert p.value == (440.0,)

    def test_control_default_rate_is_control(self):
        p = control(440.0)
        assert p.rate == ParameterRate.CONTROL

    def test_control_audio_rate_string(self):
        p = control(440.0, rate="ar")
        assert p.rate == ParameterRate.AUDIO

    def test_control_scalar_rate_string(self):
        p = control(0, rate="ir")
        assert p.rate == ParameterRate.SCALAR

    def test_control_trigger_rate_string(self):
        p = control(1.0, rate="tr")
        assert p.rate == ParameterRate.TRIGGER

    def test_control_rate_enum(self):
        p = control(440.0, rate=ParameterRate.AUDIO)
        assert p.rate == ParameterRate.AUDIO

    def test_control_with_lag(self):
        p = control(0.3, lag=0.1)
        assert p.lag == 0.1

    def test_control_sequence_value(self):
        p = control([1.0, 2.0, 3.0])
        assert p.value == (1.0, 2.0, 3.0)

    def test_control_in_synthdefbuilder(self):
        """control() works as a SynthDefBuilder kwarg."""
        with SynthDefBuilder(
            freq=control(440.0, rate="ar"),
            amp=control(0.3, lag=0.1),
        ) as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=builder["freq"]) * builder["amp"])
        sd = builder.build(name="test_control")
        params = sd.parameters
        assert "freq" in params
        assert "amp" in params
        freq_param, _ = params["freq"]
        amp_param, _ = params["amp"]
        assert freq_param.rate == ParameterRate.AUDIO
        assert amp_param.lag == 0.1


# ---------------------------------------------------------------------------
# Tuple syntax tests
# ---------------------------------------------------------------------------


class TestTupleSyntax:
    def test_two_element_tuple(self):
        """(rate, value) tuple creates parameter with correct rate."""
        with SynthDefBuilder(freq=("ar", 440.0)) as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=builder["freq"]))
        sd = builder.build(name="test_tuple2")
        freq_param, _ = sd.parameters["freq"]
        assert freq_param.rate == ParameterRate.AUDIO
        assert freq_param.value == (440.0,)

    def test_three_element_tuple(self):
        """(rate, value, lag) tuple creates parameter with rate and lag."""
        with SynthDefBuilder(amp=("kr", 0.5, 0.1)) as builder:
            Out.ar(bus=0, source=SinOsc.ar() * builder["amp"])
        sd = builder.build(name="test_tuple3")
        amp_param, _ = sd.parameters["amp"]
        assert amp_param.rate == ParameterRate.CONTROL
        assert amp_param.value == (0.5,)
        assert amp_param.lag == 0.1

    def test_invalid_tuple_length(self):
        """Tuple with wrong number of elements raises ValueError."""
        with pytest.raises(ValueError, match="2 or 3 elements"):
            SynthDefBuilder(freq=("ar", 440.0, 0.1, "extra"))  # type: ignore[arg-type]

    def test_scalar_rate_tuple(self):
        """(ir, value) tuple for scalar rate."""
        with SynthDefBuilder(bus=("ir", 0.0)) as builder:
            Out.ar(bus=builder["bus"], source=SinOsc.ar())
        sd = builder.build(name="test_ir")
        bus_param, _ = sd.parameters["bus"]
        assert bus_param.rate == ParameterRate.SCALAR

    def test_mixed_kwarg_styles(self):
        """Different kwarg styles can be mixed in one builder."""
        with SynthDefBuilder(
            freq=control(440.0, rate="ar"),
            amp=("kr", 0.3, 0.1),
            bus=0.0,
        ) as builder:
            Out.ar(
                bus=builder["bus"],
                source=SinOsc.ar(frequency=builder["freq"]) * builder["amp"],
            )
        sd = builder.build(name="test_mixed")
        assert "freq" in sd.parameters
        assert "amp" in sd.parameters
        assert "bus" in sd.parameters
