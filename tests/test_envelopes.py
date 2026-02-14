"""Tests for Envelope.compile() dedicated serialization path."""

import pytest

from nanosynth.envelopes import Envelope
from nanosynth.synthdef import SynthDefBuilder, UGenVector
from nanosynth.ugens import SinOsc, Out


class TestEnvelopeCompile:
    def test_adsr_compile_matches_serialize(self) -> None:
        """compile() produces the same float values as serialize()."""
        env = Envelope.adsr()
        compiled = env.compile()
        serialized_values = tuple(float(x) for x in env.serialize())
        assert compiled == serialized_values

    def test_linen_compile_matches_serialize(self) -> None:
        env = Envelope.linen()
        compiled = env.compile()
        serialized_values = tuple(float(x) for x in env.serialize())
        assert compiled == serialized_values

    def test_percussive_compile_matches_serialize(self) -> None:
        env = Envelope.percussive()
        compiled = env.compile()
        serialized_values = tuple(float(x) for x in env.serialize())
        assert compiled == serialized_values

    def test_triangle_compile_matches_serialize(self) -> None:
        env = Envelope.triangle()
        compiled = env.compile()
        serialized_values = tuple(float(x) for x in env.serialize())
        assert compiled == serialized_values

    def test_asr_compile_matches_serialize(self) -> None:
        env = Envelope.asr()
        compiled = env.compile()
        serialized_values = tuple(float(x) for x in env.serialize())
        assert compiled == serialized_values

    def test_returns_tuple_of_floats(self) -> None:
        env = Envelope.adsr()
        result = env.compile()
        assert isinstance(result, tuple)
        assert all(isinstance(x, float) for x in result)

    def test_adsr_structure(self) -> None:
        """compile() output has correct structure for ADSR."""
        env = Envelope.adsr()
        values = env.compile()
        assert values[0] == 0.0  # initial amplitude
        assert values[1] == 3.0  # 3 segments
        assert values[2] == 2.0  # release node
        assert values[3] == -99.0  # no loop node

    def test_percussive_structure(self) -> None:
        env = Envelope.percussive(attack_time=0.01, release_time=1.0, amplitude=0.8)
        values = env.compile()
        assert values[0] == 0.0  # initial amplitude
        assert values[1] == 2.0  # 2 segments
        assert values[4] == 0.8  # peak amplitude

    def test_ugen_input_raises_type_error(self) -> None:
        """compile() raises TypeError when envelope has UGen inputs."""
        with SynthDefBuilder():
            sig = SinOsc.ar()
            env = Envelope.percussive(amplitude=sig)
            with pytest.raises(TypeError, match="Cannot compile envelope with UGen"):
                env.compile()
            Out.ar(bus=0, source=sig)

    def test_custom_envelope_compile(self) -> None:
        """compile() works with custom amplitude/duration/curve values."""
        env = Envelope(
            amplitudes=[0.0, 1.0, 0.5, 0.0],
            durations=[0.1, 0.5, 0.4],
            curves=[-4.0, 0.0, -4.0],
        )
        values = env.compile()
        assert values[0] == 0.0  # initial
        assert values[1] == 3.0  # 3 segments
        assert len(values) == 4 + 3 * 4  # header + 3 segments * 4 values each

    def test_compile_with_release_and_loop_nodes(self) -> None:
        """compile() correctly encodes release_node and loop_node."""
        env = Envelope(
            amplitudes=[0.0, 1.0, 0.0],
            durations=[0.5, 0.5],
            release_node=1,
            loop_node=0,
        )
        values = env.compile()
        assert values[2] == 1.0  # release_node
        assert values[3] == 0.0  # loop_node


class TestSerializeCleanup:
    def test_serialize_no_kwargs(self) -> None:
        """serialize() works without keyword arguments (signature cleaned up)."""
        env = Envelope.adsr()
        result = env.serialize()
        assert isinstance(result, UGenVector)

    def test_serialize_still_works_in_synthdef(self) -> None:
        """serialize() still works correctly within SynthDef wiring."""
        from nanosynth.envelopes import EnvGen
        from nanosynth.enums import DoneAction

        with SynthDefBuilder() as builder:
            env = EnvGen.kr(
                envelope=Envelope.adsr(),
                done_action=DoneAction.FREE_SYNTH,
            )
            Out.ar(bus=0, source=SinOsc.ar() * env)
        sd = builder.build(name="test")
        assert sd.compile()[:4] == b"SCgf"
