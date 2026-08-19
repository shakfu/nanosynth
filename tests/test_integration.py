"""Integration tests verifying compiled SynthDefs produce audio.

Uses NRT (non-real-time) rendering via Score.render() to verify the
full pipeline: SynthDefBuilder -> SynthDef -> SCgf binary -> engine load
-> audio synthesis -> WAV output. No audio hardware required.
"""

import struct
import tempfile
import wave
from pathlib import Path

import pytest

from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.osc import OscMessage
from nanosynth.score import Score
from nanosynth.scsynth import Options
from nanosynth.synthdef import SynthDefBuilder, synthdef
from nanosynth.ugens import LPF, RLPF, Out, Pan2, Saw, SinOsc, WhiteNoise
from nanosynth.ugens.basic import Mix


def _render_score(score: Score, duration: float, **kwargs) -> Path:
    """Render a score to a temp WAV file and return the path.

    Caller is responsible for cleanup.
    """
    fd, path = tempfile.mkstemp(suffix=".wav")
    import os

    os.close(fd)
    # Add end-of-score marker if not already present
    score.add(duration, OscMessage("/c_set", 0, 0))
    score.render(
        path,
        sample_rate=kwargs.get("sample_rate", 44100),
        options=kwargs.get("options", Options(verbosity=-1)),
    )
    return Path(path)


def _read_wav(path: Path) -> tuple[int, int, int, bytes]:
    """Read a WAV file and return (nchannels, sampwidth, framerate, frames)."""
    with wave.open(str(path), "rb") as wf:
        return (
            wf.getnchannels(),
            wf.getsampwidth(),
            wf.getframerate(),
            wf.readframes(wf.getnframes()),
        )


def _peak_amplitude(frames: bytes, sampwidth: int) -> float:
    """Compute peak amplitude from raw PCM frames, normalized to [0, 1]."""
    if sampwidth == 2:
        # 16-bit signed PCM, little-endian
        n_samples = len(frames) // 2
        samples = struct.unpack(f"<{n_samples}h", frames)
        return max(abs(s) for s in samples) / 32767.0
    raise ValueError(f"Unsupported sample width: {sampwidth}")


def _rms_amplitude(frames: bytes, sampwidth: int) -> float:
    """Compute RMS amplitude from raw PCM frames, normalized to [0, 1]."""
    if sampwidth == 2:
        n_samples = len(frames) // 2
        samples = struct.unpack(f"<{n_samples}h", frames)
        sum_sq = sum(s * s for s in samples)
        return (sum_sq / max(n_samples, 1)) ** 0.5 / 32767.0
    raise ValueError(f"Unsupported sample width: {sampwidth}")


# ---------------------------------------------------------------------------
# Basic synthesis verification
# ---------------------------------------------------------------------------


class TestSineWaveSynthesis:
    """Verify the simplest possible SynthDef produces audible output."""

    def test_sine_produces_nonsilent_audio(self):
        """A 440Hz sine wave at 0.3 amplitude produces non-silent output."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=440.0) * 0.3)
        sd = builder.build(name="sine")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "sine")

        path = _render_score(score, 0.5)
        try:
            nch, sw, rate, frames = _read_wav(path)
            assert rate == 44100
            assert len(frames) > 0
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.1, f"Audio is near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)

    def test_sine_amplitude_scales_with_multiplier(self):
        """Doubling the amplitude multiplier roughly doubles peak output."""
        peaks = []
        for amp in (0.1, 0.2):
            with SynthDefBuilder() as builder:
                Out.ar(bus=0, source=SinOsc.ar(frequency=440.0) * amp)
            sd = builder.build(name="sine")

            score = Score()
            score.add_synthdef(0.0, sd)
            score.add_synth(0.0, "sine")

            path = _render_score(score, 0.25)
            try:
                _, sw, _, frames = _read_wav(path)
                peaks.append(_peak_amplitude(frames, sw))
            finally:
                path.unlink(missing_ok=True)

        # Peak at 0.2 should be roughly 2x the peak at 0.1 (within tolerance)
        ratio = peaks[1] / max(peaks[0], 1e-9)
        assert 1.5 < ratio < 2.5, f"Unexpected amplitude ratio: {ratio:.2f}"

    def test_different_frequencies_produce_different_waveforms(self):
        """A 440Hz and 880Hz sine produce different raw sample data."""
        outputs = []
        for freq in (440, 880):
            with SynthDefBuilder() as builder:
                Out.ar(bus=0, source=SinOsc.ar(frequency=float(freq)) * 0.3)
            sd = builder.build(name="sine")

            score = Score()
            score.add_synthdef(0.0, sd)
            score.add_synth(0.0, "sine")

            path = _render_score(score, 0.1)
            try:
                _, _, _, frames = _read_wav(path)
                outputs.append(frames)
            finally:
                path.unlink(missing_ok=True)

        assert outputs[0] != outputs[1], (
            "Different frequencies produced identical audio"
        )


# ---------------------------------------------------------------------------
# Parameter control
# ---------------------------------------------------------------------------


class TestParameterizedSynthDefs:
    """Verify SynthDef parameters are wired through to the engine."""

    def test_parameter_controls_frequency(self):
        """Passing freq=880 via /s_new produces different audio than freq=440."""
        with SynthDefBuilder(freq=440.0) as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=builder["freq"]) * 0.3)
        sd = builder.build(name="param_sine")

        outputs = []
        for freq in (440.0, 880.0):
            score = Score()
            score.add_synthdef(0.0, sd)
            score.add_synth(0.0, "param_sine", freq=freq)

            path = _render_score(score, 0.1)
            try:
                _, _, _, frames = _read_wav(path)
                outputs.append(frames)
            finally:
                path.unlink(missing_ok=True)

        assert outputs[0] != outputs[1], (
            "Different freq params produced identical audio"
        )

    def test_multiple_parameters(self):
        """A SynthDef with multiple parameters responds to all of them."""
        with SynthDefBuilder(freq=440.0, amp=0.5) as builder:
            Out.ar(
                bus=0,
                source=SinOsc.ar(frequency=builder["freq"]) * builder["amp"],
            )
        sd = builder.build(name="multi_param")

        # Render with low amplitude
        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "multi_param", freq=440.0, amp=0.1)
        path = _render_score(score, 0.25)
        try:
            _, sw, _, frames = _read_wav(path)
            peak_low = _peak_amplitude(frames, sw)
        finally:
            path.unlink(missing_ok=True)

        # Render with high amplitude
        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "multi_param", freq=440.0, amp=0.5)
        path = _render_score(score, 0.25)
        try:
            _, sw, _, frames = _read_wav(path)
            peak_high = _peak_amplitude(frames, sw)
        finally:
            path.unlink(missing_ok=True)

        assert peak_high > peak_low * 2, (
            f"amp=0.5 should be louder than amp=0.1: "
            f"peak_high={peak_high:.4f}, peak_low={peak_low:.4f}"
        )


# ---------------------------------------------------------------------------
# Diverse UGen types
# ---------------------------------------------------------------------------


class TestDiverseUGens:
    """Verify different UGen types produce audio through the full pipeline."""

    def test_white_noise(self):
        """WhiteNoise produces non-silent, non-zero audio."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=WhiteNoise.ar() * 0.3)
        sd = builder.build(name="noise")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "noise")

        path = _render_score(score, 0.25)
        try:
            _, sw, _, frames = _read_wav(path)
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.1, f"WhiteNoise is near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)

    def test_saw(self):
        """Saw oscillator produces non-silent audio."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=Saw.ar(frequency=440.0) * 0.3)
        sd = builder.build(name="saw")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "saw")

        path = _render_score(score, 0.25)
        try:
            _, sw, _, frames = _read_wav(path)
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.1, f"Saw is near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)

    def test_filtered_noise(self):
        """WhiteNoise -> LPF produces non-silent audio (filter pipeline works)."""
        with SynthDefBuilder() as builder:
            sig = WhiteNoise.ar()
            sig = LPF.ar(source=sig, frequency=1000.0)
            Out.ar(bus=0, source=sig * 0.5)
        sd = builder.build(name="filtered")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "filtered")

        path = _render_score(score, 0.25)
        try:
            _, sw, _, frames = _read_wav(path)
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.05, f"Filtered noise is near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)

    def test_filter_reduces_amplitude(self):
        """LPF at a low cutoff produces lower RMS than unfiltered noise."""
        rms_values = []
        for cutoff in (200.0, 10000.0):
            with SynthDefBuilder() as builder:
                sig = WhiteNoise.ar()
                sig = LPF.ar(source=sig, frequency=cutoff)
                Out.ar(bus=0, source=sig * 0.5)
            sd = builder.build(name="filt")

            score = Score()
            score.add_synthdef(0.0, sd)
            score.add_synth(0.0, "filt")

            path = _render_score(score, 0.5)
            try:
                _, sw, _, frames = _read_wav(path)
                rms_values.append(_rms_amplitude(frames, sw))
            finally:
                path.unlink(missing_ok=True)

        assert rms_values[0] < rms_values[1], (
            f"200Hz cutoff should be quieter than 10kHz: "
            f"rms_200={rms_values[0]:.4f}, rms_10k={rms_values[1]:.4f}"
        )


# ---------------------------------------------------------------------------
# Envelope integration
# ---------------------------------------------------------------------------


class TestEnvelopeIntegration:
    """Verify envelopes shape amplitude over time."""

    def test_percussive_envelope(self):
        """A percussive envelope starts loud and decays to near silence."""
        with SynthDefBuilder() as builder:
            env = Envelope.percussive(attack_time=0.01, release_time=0.2)
            sig = SinOsc.ar(frequency=440.0) * EnvGen.ar(envelope=env)
            Out.ar(bus=0, source=sig * 0.5)
        sd = builder.build(name="perc")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "perc")

        path = _render_score(score, 0.5)
        try:
            _, sw, rate, frames = _read_wav(path)
            # Split into first 50ms and last 200ms
            bytes_per_sample = sw * 2  # stereo
            early_end = int(0.05 * rate) * bytes_per_sample
            late_start = int(0.3 * rate) * bytes_per_sample
            early_frames = frames[:early_end]
            late_frames = frames[late_start:]
            # Assert (not silently skip) that both windows exist, so a render
            # that produced too few frames fails rather than passing vacuously.
            assert early_frames and late_frames, "render produced too few frames"
            early_rms = _rms_amplitude(early_frames, sw)
            late_rms = _rms_amplitude(late_frames, sw)
            assert early_rms > late_rms * 2, (
                f"Percussive envelope should decay: "
                f"early_rms={early_rms:.4f}, late_rms={late_rms:.4f}"
            )
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Mix / multichannel
# ---------------------------------------------------------------------------


class TestMixIntegration:
    """Verify Mix and multichannel operations produce correct output."""

    def test_mix_multiple_oscillators(self):
        """Mixing four oscillators produces non-silent audio."""
        with SynthDefBuilder() as builder:
            sources = [SinOsc.ar(frequency=float(f)) for f in [440, 550, 660, 770]]
            Out.ar(bus=0, source=Mix.new(sources) * 0.1)
        sd = builder.build(name="mix4")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "mix4")

        path = _render_score(score, 0.25)
        try:
            _, sw, _, frames = _read_wav(path)
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.05, f"Mixed oscillators near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)

    def test_stereo_panning(self):
        """Pan2 produces a stereo file with audio in both channels."""
        with SynthDefBuilder() as builder:
            sig = SinOsc.ar(frequency=440.0) * 0.3
            panned = Pan2.ar(source=sig, position=0.0)
            Out.ar(bus=0, source=panned)
        sd = builder.build(name="pan")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "pan")

        path = _render_score(score, 0.25)
        try:
            nch, sw, _, frames = _read_wav(path)
            assert nch == 2, f"Expected stereo output, got {nch} channels"
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.1, f"Panned signal near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# @synthdef decorator integration
# ---------------------------------------------------------------------------


class TestSynthdefDecoratorIntegration:
    """Verify the @synthdef convenience decorator works end-to-end."""

    def test_decorator_synthdef_produces_audio(self):
        """A @synthdef-decorated function compiles and produces audio."""

        @synthdef()
        def test_dec(freq=440, amp=0.3):
            Out.ar(bus=0, source=SinOsc.ar(frequency=freq) * amp)

        score = Score()
        score.add_synthdef(0.0, test_dec)
        score.add_synth(0.0, "test_dec")

        path = _render_score(score, 0.25)
        try:
            _, sw, _, frames = _read_wav(path)
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.1, f"Decorator SynthDef near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Complex graph integration
# ---------------------------------------------------------------------------


class TestComplexGraphIntegration:
    """Verify non-trivial synthesis graphs work end-to-end."""

    def test_subtractive_synthesis(self):
        """Saw -> RLPF with envelope produces shaped audio."""
        with SynthDefBuilder(freq=440.0, cutoff=2000.0) as builder:
            sig = Saw.ar(frequency=builder["freq"])
            sig = RLPF.ar(source=sig, frequency=builder["cutoff"], reciprocal_of_q=0.5)
            Out.ar(bus=0, source=sig * 0.3)
        sd = builder.build(name="subtractive")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "subtractive", freq=220.0, cutoff=1000.0)

        path = _render_score(score, 0.5)
        try:
            _, sw, _, frames = _read_wav(path)
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.05, f"Subtractive synth near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)

    def test_additive_synthesis(self):
        """Summing harmonic partials produces non-silent audio."""
        with SynthDefBuilder(freq=220.0) as builder:
            partials = [
                SinOsc.ar(frequency=builder["freq"] * float(i + 1)) * (1.0 / (i + 1))
                for i in range(8)
            ]
            Out.ar(bus=0, source=Mix.new(partials) * 0.1)
        sd = builder.build(name="additive")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "additive", freq=220.0)

        path = _render_score(score, 0.5)
        try:
            _, sw, _, frames = _read_wav(path)
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.05, f"Additive synth near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)

    def test_multiple_synthdefs_in_score(self):
        """Loading two SynthDefs and playing both produces audio."""
        with SynthDefBuilder() as b1:
            Out.ar(bus=0, source=SinOsc.ar(frequency=440.0) * 0.15)
        sd1 = b1.build(name="sine_a")

        with SynthDefBuilder() as b2:
            Out.ar(bus=0, source=SinOsc.ar(frequency=660.0) * 0.15)
        sd2 = b2.build(name="sine_b")

        score = Score()
        score.add_synthdef(0.0, sd1)
        score.add_synthdef(0.0, sd2)
        score.add_synth(0.0, "sine_a", node_id=1000)
        score.add_synth(0.0, "sine_b", node_id=1001)

        path = _render_score(score, 0.25)
        try:
            _, sw, _, frames = _read_wav(path)
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.1, f"Dual-synth output near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Compilation roundtrip: compile -> load -> render -> verify
# ---------------------------------------------------------------------------


class TestCompilationRoundtrip:
    """Verify the SCgf binary produced by compile() is loadable by the engine."""

    def test_compile_and_render_deterministic(self):
        """The same SynthDef compiled twice produces identical audio output."""
        outputs = []
        for _ in range(2):
            with SynthDefBuilder() as builder:
                Out.ar(bus=0, source=SinOsc.ar(frequency=440.0) * 0.3)
            sd = builder.build(name="det_test")

            score = Score()
            score.add_synthdef(0.0, sd)
            score.add_synth(0.0, "det_test")

            path = _render_score(score, 0.1)
            try:
                _, _, _, frames = _read_wav(path)
                outputs.append(frames)
            finally:
                path.unlink(missing_ok=True)

        assert outputs[0] == outputs[1], "Identical SynthDefs produced different audio"

    def test_anonymous_synthdef_renders(self):
        """A SynthDef with no explicit name (anonymous) loads and renders."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=440.0) * 0.3)
        sd = builder.build()  # no name -- uses anonymous MD5 hash

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, sd.effective_name)

        path = _render_score(score, 0.25)
        try:
            _, sw, _, frames = _read_wav(path)
            peak = _peak_amplitude(frames, sw)
            assert peak > 0.1, f"Anonymous SynthDef near-silent: peak={peak:.4f}"
        finally:
            path.unlink(missing_ok=True)

    def test_optimized_and_unoptimized_produce_same_audio(self):
        """Optimized and unoptimized builds of the same graph produce identical audio."""
        outputs = []
        for optimize in (True, False):
            with SynthDefBuilder() as builder:
                sig = SinOsc.ar(frequency=440.0) * 0.3
                # Add dead code that optimization should remove
                SinOsc.ar(frequency=880.0)
                Out.ar(bus=0, source=sig)
            sd = builder.build(name="opt_test", optimize=optimize)

            score = Score()
            score.add_synthdef(0.0, sd)
            score.add_synth(0.0, "opt_test")

            path = _render_score(score, 0.1)
            try:
                _, _, _, frames = _read_wav(path)
                outputs.append(frames)
            finally:
                path.unlink(missing_ok=True)

        assert outputs[0] == outputs[1], (
            "Optimized and unoptimized builds produced different audio"
        )


# ---------------------------------------------------------------------------
# Golden SCgf fixtures render real audio (M17)
# ---------------------------------------------------------------------------


_GOLDEN_DIR = Path(__file__).parent / "fixtures" / "scgf"
# fixture stem -> the SynthDef name compiled into it (see test_golden_scgf.py).
_GOLDEN_SYNTHS = {
    "additive_mix": "golden_additive_mix",
    "enveloped": "golden_enveloped",
    "filtered_noise": "golden_filtered_noise",
    "sine": "golden_sine",
}


class TestGoldenFixturesRenderAudio:
    """Close the loop the golden-byte test only claims: load the committed
    ``.scsyndef`` bytes into the NRT engine and prove they synthesize audio.

    ``test_golden_scgf.py`` asserts ``compile() == fixture`` -- a regression
    guard that proves nothing about correctness on its own. This renders the
    exact committed bytes and asserts non-silent output (M17).
    """

    @pytest.mark.parametrize("stem,name", sorted(_GOLDEN_SYNTHS.items()))
    def test_fixture_renders_nonsilent(self, stem: str, name: str) -> None:
        raw = (_GOLDEN_DIR / f"{stem}.scsyndef").read_bytes()
        score = Score()
        # Load the fixture bytes directly (add_synthdef would recompile a
        # SynthDef; here we send the committed bytes verbatim).
        score.add(0.0, OscMessage("/d_recv", raw))
        score.add_synth(0.0, name)

        path = _render_score(score, 0.5)
        try:
            _nch, sw, rate, frames = _read_wav(path)
            assert rate == 44100
            assert len(frames) > 0
            assert _rms_amplitude(frames, sw) > 1e-3, (
                f"golden fixture {stem!r} rendered silence -- the committed "
                f"bytes do not synthesize audio"
            )
        finally:
            path.unlink(missing_ok=True)
