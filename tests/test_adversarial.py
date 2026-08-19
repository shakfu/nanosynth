"""Adversarial and negative tests for the SynthDef compiler.

Tests edge cases: deep UGen chains, large graphs, invalid inputs,
name encoding boundaries, and topological sort robustness.
"""

import struct

import pytest

from nanosynth.exceptions import SynthDefError
from nanosynth.synthdef import (
    BinaryOpUGen,
    SynthDef,
    SynthDefBuilder,
    UGen,
    compile_synthdefs,
    param,
    ugen,
)
from nanosynth.ugens import LPF, Out, SinOsc, WhiteNoise
from nanosynth.ugens.basic import Mix


# ---------------------------------------------------------------------------
# Deep UGen chains
# ---------------------------------------------------------------------------


class TestDeepChains:
    def test_deep_filter_chain(self):
        """A chain of 100 cascaded LPFs compiles without error."""
        with SynthDefBuilder() as builder:
            sig = WhiteNoise.ar()
            for _ in range(100):
                sig = LPF.ar(source=sig, frequency=1000.0)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="deep")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        lpfs = [u for u in sd.ugens if isinstance(u, LPF)]
        assert len(lpfs) == 100

    def test_deep_arithmetic_chain(self):
        """A chain of 200 additions compiles without error."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            for i in range(200):
                sig = sig + 0.001
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="arith_deep")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        binary_ops = [u for u in sd.ugens if isinstance(u, BinaryOpUGen)]
        assert len(binary_ops) == 200

    def test_deep_chain_topological_order(self):
        """Topological sort preserves dependency order in deep chains."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            for _ in range(50):
                sig = LPF.ar(source=sig, frequency=1000.0)
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="topo_deep")
        ugen_types = [type(u).__name__ for u in sd.ugens]
        # SinOsc must come before all LPFs, LPFs before Out
        sin_idx = ugen_types.index("SinOsc")
        out_idx = ugen_types.index("Out")
        lpf_indices = [i for i, t in enumerate(ugen_types) if t == "LPF"]
        assert all(sin_idx < i for i in lpf_indices)
        assert all(i < out_idx for i in lpf_indices)


# ---------------------------------------------------------------------------
# Large graphs
# ---------------------------------------------------------------------------


class TestLargeGraphs:
    def test_many_parallel_ugens(self):
        """A graph with 500 parallel SinOscs mixed down compiles."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=440 + i) for i in range(500)]
            Out.ar(bus=0, source=Mix.new(sources))
        sd = builder.build(name="large")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        sinoscs = [u for u in sd.ugens if isinstance(u, SinOsc)]
        assert len(sinoscs) == 500

    def test_many_constants(self):
        """A graph with many distinct constants collects them all."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar()
            for i in range(200):
                sig = sig + float(i) * 0.0001
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="consts")
        # Each distinct float becomes a constant
        assert len(sd.constants) >= 200

    def test_many_parameters(self):
        """A SynthDef with 100 parameters compiles."""
        kwargs = {f"p{i}": float(i) for i in range(100)}
        with SynthDefBuilder(**kwargs) as builder:
            sig = SinOsc.ar(frequency=builder["p0"])
            for i in range(1, 100):
                sig = sig + builder[f"p{i}"]
            Out.ar(bus=0, source=sig)
        sd = builder.build(name="many_params")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        assert len(sd.parameters) == 100


# ---------------------------------------------------------------------------
# Name encoding edge cases
# ---------------------------------------------------------------------------


class TestNameEdgeCases:
    def test_empty_name_uses_anonymous(self):
        """An empty-string name falls back to anonymous MD5 hash."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="")
        data = sd.compile()
        # Empty name means compile uses anonymous_name (32 hex chars)
        name_len = data[10]
        assert name_len == 32

    def test_max_length_name(self):
        """A 255-character name (max for 1-byte length encoding) compiles."""
        long_name = "a" * 255
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name=long_name)
        data = sd.compile()
        name_len = data[10]
        assert name_len == 255
        name = data[11 : 11 + 255].decode("ascii")
        assert name == long_name

    def test_name_with_underscores_and_digits(self):
        """Names with underscores and digits compile correctly."""
        name = "my_synth_v2_final_3"
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name=name)
        data = sd.compile()
        name_len = data[10]
        assert data[11 : 11 + name_len].decode("ascii") == name

    def test_single_char_name(self):
        """A single-character name compiles."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="x")
        data = sd.compile()
        assert data[10] == 1
        assert data[11:12] == b"x"

    def test_name_over_255_raises(self):
        """A name longer than 255 characters raises a clear SynthDefError."""
        long_name = "b" * 256
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name=long_name)
        with pytest.raises(SynthDefError, match="255-byte limit"):
            sd.compile()

    def test_non_ascii_name_raises(self):
        """A name with non-ASCII characters raises a clear SynthDefError."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="synth_\xff\xfe")
        with pytest.raises(SynthDefError, match="ASCII"):
            sd.compile()


# ---------------------------------------------------------------------------
# Invalid SCgf binary parsing
# ---------------------------------------------------------------------------


class TestInvalidBinary:
    def test_compile_multiple_synthdefs(self):
        """compile_synthdefs with multiple SynthDefs produces correct count."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar())
        sd1 = b1.build(name="sd1")

        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=WhiteNoise.ar())
        sd2 = b2.build(name="sd2")

        data = compile_synthdefs(sd1, sd2)
        assert data[:4] == b"SCgf"
        count = struct.unpack(">H", data[8:10])[0]
        assert count == 2

    def test_anonymous_names_are_deterministic(self):
        """The same graph always produces the same anonymous name."""

        def make_sd():
            with SynthDefBuilder() as builder:
                Out.ar(bus=0, source=SinOsc.ar(frequency=440))
            return builder.build()

        sd1 = make_sd()
        sd2 = make_sd()
        assert sd1.anonymous_name == sd2.anonymous_name

    def test_different_graphs_different_anonymous_names(self):
        """Different graphs produce different anonymous names."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar(frequency=440))
        sd1 = b1.build()

        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=SinOsc.ar(frequency=880))
        sd2 = b2.build()

        assert sd1.anonymous_name != sd2.anonymous_name


# ---------------------------------------------------------------------------
# Scope isolation
# ---------------------------------------------------------------------------


class TestScopeIsolation:
    def test_nested_builders_inner_cannot_use_outer(self):
        """A UGen from an outer builder cannot be used inside an inner builder."""
        with SynthDefBuilder():
            outer_sig = SinOsc.ar()
            with pytest.raises(SynthDefError):
                with SynthDefBuilder():
                    Out.ar(bus=0, source=outer_sig)

    def test_sequential_builders_independent(self):
        """Two sequential builders produce independent SynthDefs."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar(frequency=440))
        sd1 = b1.build(name="sd1")

        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=SinOsc.ar(frequency=880))
        sd2 = b2.build(name="sd2")

        assert sd1.compile() != sd2.compile()

    def test_cross_scope_parameter_raises(self):
        """Using a parameter from one builder in another raises."""
        with SynthDefBuilder(freq=440) as b1:
            freq = b1["freq"]
        with pytest.raises(SynthDefError):
            with SynthDefBuilder():
                Out.ar(bus=0, source=SinOsc.ar(frequency=freq))

    def test_cross_scope_arithmetic_raises(self):
        """Arithmetic between UGens from different scopes raises."""
        with SynthDefBuilder():
            sig_a = SinOsc.ar()
        with pytest.raises(SynthDefError):
            with SynthDefBuilder():
                sig_b = SinOsc.ar()
                Out.ar(bus=0, source=sig_a + sig_b)


# ---------------------------------------------------------------------------
# Empty and degenerate graphs
# ---------------------------------------------------------------------------


class TestDegenerateGraphs:
    def test_empty_ugens_raises(self):
        """SynthDef with empty UGen list raises SynthDefError."""
        with pytest.raises(SynthDefError):
            SynthDef([], name="empty")

    def test_constants_only_graph(self):
        """A graph that outputs only a constant compiles."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=0.5)
        sd = builder.build(name="const_only")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_parameter_only_graph(self):
        """A graph that outputs only a parameter compiles."""
        with SynthDefBuilder(amp=0.5) as builder:
            Out.ar(bus=0, source=builder["amp"])
        sd = builder.build(name="param_only")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_all_dead_code_with_out(self):
        """Dead code is eliminated but Out and its dependencies survive."""
        with SynthDefBuilder() as builder:
            # 10 dead UGens
            for _ in range(10):
                SinOsc.ar()
            Out.ar(bus=0, source=WhiteNoise.ar())
        sd = builder.build(name="dead_code", optimize=True)
        sinoscs = [u for u in sd.ugens if isinstance(u, SinOsc)]
        assert len(sinoscs) == 0
        assert any(isinstance(u, WhiteNoise) for u in sd.ugens)
        assert any(isinstance(u, Out) for u in sd.ugens)


# ---------------------------------------------------------------------------
# Topological sort edge cases
# ---------------------------------------------------------------------------


class TestTopologicalSortEdgeCases:
    def test_diamond_dependency(self):
        """Diamond dependency: A -> B, A -> C, B -> D, C -> D."""
        with SynthDefBuilder() as builder:
            a = SinOsc.ar()
            b = LPF.ar(source=a, frequency=1000)
            c = LPF.ar(source=a, frequency=2000)
            d = b + c
            Out.ar(bus=0, source=d)
        sd = builder.build(name="diamond")
        ugen_list = sd.ugens
        # Find indices
        sin_idx = next(i for i, u in enumerate(ugen_list) if isinstance(u, SinOsc))
        lpf_indices = [i for i, u in enumerate(ugen_list) if isinstance(u, LPF)]
        out_idx = next(i for i, u in enumerate(ugen_list) if isinstance(u, Out))
        # SinOsc before both LPFs, both LPFs before Out
        assert all(sin_idx < lpf_i for lpf_i in lpf_indices)
        assert all(lpf_i < out_idx for lpf_i in lpf_indices)

    def test_wide_fan_out(self):
        """One source feeding 50 parallel consumers."""
        with SynthDefBuilder() as builder:
            source = SinOsc.ar()
            sigs = [source * float(i + 1) * 0.01 for i in range(50)]
            Out.ar(bus=0, source=Mix.new(sigs))
        sd = builder.build(name="fanout")
        data = sd.compile()
        assert data[:4] == b"SCgf"
        # Source should appear exactly once
        sinoscs = [u for u in sd.ugens if isinstance(u, SinOsc)]
        assert len(sinoscs) == 1

    def test_wide_fan_in(self):
        """50 independent sources all feeding a single Mix."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=200 + i * 10) for i in range(50)]
            Out.ar(bus=0, source=Mix.new(sources))
        sd = builder.build(name="fanin")
        data = sd.compile()
        assert data[:4] == b"SCgf"

    def test_disconnected_subgraphs_impure(self):
        """Impure UGens in disconnected subgraphs survive optimization."""
        with SynthDefBuilder() as builder:
            # Subgraph 1: actually used
            Out.ar(bus=0, source=SinOsc.ar())
            # Subgraph 2: impure, not connected to Out
            WhiteNoise.ar()
        sd = builder.build(name="disconn", optimize=True)
        # WhiteNoise is impure so survives
        assert any(isinstance(u, WhiteNoise) for u in sd.ugens)

    def test_optimize_preserves_correctness(self):
        """Optimized and non-optimized builds produce identical audio graphs
        when there is no dead code."""
        with SynthDefBuilder() as b1:
            sig = SinOsc.ar() * 0.5
            Out.ar(bus=0, source=sig)
        sd_opt = b1.build(name="test", optimize=True)

        with SynthDefBuilder() as b2:
            sig = SinOsc.ar() * 0.5
            Out.ar(bus=0, source=sig)
        sd_noopt = b2.build(name="test", optimize=False)

        assert sd_opt.compile() == sd_noopt.compile()


# ---------------------------------------------------------------------------
# Compilation determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_identical_graphs_byte_identical(self):
        """Building the same graph twice produces byte-identical SCgf."""

        def build():
            with SynthDefBuilder() as builder:
                sig = SinOsc.ar(frequency=440) * 0.5
                Out.ar(bus=0, source=sig)
            return builder.build(name="det").compile()

        assert build() == build()

    def test_parameter_order_deterministic(self):
        """Parameters are sorted deterministically regardless of insertion order."""
        with SynthDefBuilder(z_param=1.0, a_param=2.0, m_param=3.0) as b1:
            sig = SinOsc.ar(frequency=b1["a_param"]) * b1["m_param"] + b1["z_param"]
            Out.ar(bus=0, source=sig)
        sd1 = b1.build(name="det")

        with SynthDefBuilder(a_param=2.0, m_param=3.0, z_param=1.0) as b2:
            sig = SinOsc.ar(frequency=b2["a_param"]) * b2["m_param"] + b2["z_param"]
            Out.ar(bus=0, source=sig)
        sd2 = b2.build(name="det")

        assert sd1.compile() == sd2.compile()


# ---------------------------------------------------------------------------
# UGen type name encoding
# ---------------------------------------------------------------------------


class TestUGenTypeNames:
    def test_custom_ugen_name_in_binary(self):
        """A custom @ugen class name appears in the compiled binary."""

        @ugen(ar=True, is_pure=True)
        class MyCustomOsc(UGen):
            frequency = param(440.0)

        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=MyCustomOsc.ar())
        sd = builder.build(name="custom")
        data = sd.compile()
        assert b"MyCustomOsc" in data

    def test_ugen_with_long_name(self):
        """UGen class names up to 255 chars work in SCgf encoding."""
        # Dynamically create a UGen class with a very long name
        long_name = "X" * 200
        attrs = {"frequency": param(440.0)}
        LongNameUGen = type(long_name, (UGen,), attrs)
        # Apply the @ugen decorator
        LongNameUGen = ugen(ar=True, is_pure=True)(LongNameUGen)

        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=LongNameUGen.ar())
        sd = builder.build(name="long_ugen")
        data = sd.compile()
        assert long_name.encode("ascii") in data
