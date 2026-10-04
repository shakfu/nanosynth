"""Tests for Score NRT rendering."""

import struct
import tempfile
from pathlib import Path


import pytest

from nanosynth.enums import AddAction
from nanosynth.osc import OscBundle, OscMessage
from nanosynth.score import _GUARD_EPSILON, Score
from nanosynth.scsynth import Options
from nanosynth.synthdef import SynthDefBuilder
from nanosynth.ugens import Out, SinOsc


# ---------------------------------------------------------------------------
# Score construction tests
# ---------------------------------------------------------------------------


class TestScoreConstruction:
    def test_empty_score(self):
        """A new Score has no entries and zero duration."""
        s = Score()
        assert s.duration() == 0.0

    def test_add_single_message(self):
        """add() accepts a single OscMessage."""
        s = Score()
        s.add(0.5, OscMessage("/test", 1))
        assert s.duration() == 0.5

    def test_add_message_list(self):
        """add() accepts a list of OscMessages."""
        s = Score()
        s.add(1.0, [OscMessage("/a"), OscMessage("/b")])
        assert s.duration() == 1.0

    def test_add_synthdef(self):
        """add_synthdef() adds a /d_recv message."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="test")
        s = Score()
        s.add_synthdef(0.0, sd)
        # Check that we have an entry
        assert len(s._entries) == 1
        msgs = s._entries[0][1]
        assert msgs[0].address == "/d_recv"

    def test_add_synth(self):
        """add_synth() adds a /s_new message with params."""
        s = Score()
        s.add_synth(0.0, "sine", node_id=1000, freq=440.0)
        msgs = s._entries[0][1]
        assert msgs[0].address == "/s_new"
        contents = msgs[0].contents
        assert contents[0] == "sine"
        assert contents[1] == 1000
        # Should contain freq param
        assert "freq" in contents
        assert 440.0 in contents

    def test_add_synth_allocates_node_ids(self):
        """add_synth() allocates unique node IDs and returns them."""
        s = Score()
        a = s.add_synth(0.0, "sine", node_id=None)
        b = s.add_synth(0.5, "sine", node_id=None)
        assert (a, b) == (1000, 1001)
        assert s._entries[1][1][0].contents[1] == b

    def test_auto_ids_skip_explicit_ids(self):
        """An explicit node_id is never handed out again by allocation."""
        s = Score()
        s.add_synth(0.0, "sine", node_id=1001)
        s.add_synth(0.0, "sine", node_id=-1)  # server-assigned; not reserved
        assert [s.add_synth(0.0, "sine", None) for _ in range(2)] == [1000, 1002]

    def test_add_synth_controls_mapping(self):
        """Controls named like add_synth's own parameters stay controls."""
        s = Score()
        s.add_synth(0.0, "sine", controls={"target": 2.0, "node_id": 3.0})
        contents = tuple(s._entries[0][1][0].contents)
        assert contents == ("sine", -1, 0, 0, "target", 2.0, "node_id", 3.0)

    def test_add_synth_add_action(self):
        """add_synth() accepts an AddAction in its original positional slot."""
        s = Score()
        s.add_synth(0.0, "sine", -1, AddAction.ADD_AFTER, 7)
        contents = s._entries[0][1][0].contents
        assert tuple(contents[1:4]) == (-1, int(AddAction.ADD_AFTER), 7)

    def test_add_synth_default_node_id_is_engine_assigned(self):
        """The default stays -1, as before allocation existed."""
        s = Score()
        assert s.add_synth(0.0, "sine") == -1
        assert s._entries[0][1][0].contents[1] == -1

    def test_add_synth_original_keywords(self):
        """The pre-0.4 keyword form still works unchanged."""
        s = Score()
        node = s.add_synth(0.0, "sine", node_id=5, add_action=1, target=0, freq=2.0)
        assert node == 5
        assert tuple(s._entries[0][1][0].contents) == ("sine", 5, 1, 0, "freq", 2.0)

    def test_sort(self):
        """sort() orders entries by time."""
        s = Score()
        s.add(2.0, OscMessage("/late"))
        s.add(0.5, OscMessage("/early"))
        s.add(1.0, OscMessage("/mid"))
        s.sort()
        times = [t for t, _ in s._entries]
        assert times == [0.5, 1.0, 2.0]

    def test_duration(self):
        """duration() returns the max timestamp."""
        s = Score()
        s.add(0.0, OscMessage("/a"))
        s.add(3.5, OscMessage("/b"))
        s.add(1.0, OscMessage("/c"))
        assert s.duration() == 3.5


# ---------------------------------------------------------------------------
# Binary serialization tests
# ---------------------------------------------------------------------------


def _decode(data: bytes) -> list[OscBundle]:
    """Split a binary command file into its bundles."""
    bundles = []
    while data:
        size = struct.unpack(">i", data[:4])[0]
        bundles.append(OscBundle.from_datagram(data[4 : 4 + size]))
        data = data[4 + size :]
    return bundles


def _nrt_times(data: bytes) -> list[float]:
    """Raw NRT bundle timestamps (seconds, no NTP epoch) of a command file."""
    times = []
    while data:
        size = struct.unpack(">i", data[:4])[0]
        times.append(struct.unpack(">Q", data[12:20])[0] / 2**32)
        data = data[4 + size :]
    return times


class TestScoreSerialization:
    def test_to_binary_empty(self):
        """An empty score produces empty bytes."""
        s = Score()
        assert s.to_binary() == b""

    def test_to_binary_appends_guard(self):
        """to_binary() ends with /g_freeAll + /c_set just after the last event."""
        s = Score()
        s.add(0.0, OscMessage("/a"))
        s.add(2.0, OscMessage("/b"))
        data = s.to_binary()
        last = _decode(data)[-1]
        assert [m.address for m in last.contents] == ["/g_freeAll", "/c_set"]
        assert _nrt_times(data)[-1] == pytest.approx(2.0 + _GUARD_EPSILON, abs=1e-6)

    def test_to_binary_format(self):
        """to_binary() produces int32 size + bundle datagram pairs."""
        s = Score()
        s.add(0.0, OscMessage("/test", 1))
        data = s.to_binary()
        # First 4 bytes are int32 size
        size = struct.unpack(">i", data[:4])[0]
        assert size > 0
        # The bundle datagram follows
        bundle_data = data[4 : 4 + size]
        assert len(bundle_data) == size
        # Should be a valid bundle
        assert bundle_data[:8] == b"#bundle\x00"
        # Event bundle, then the guard bundle
        assert len(_decode(data)) == 2

    def test_to_binary_multiple_entries(self):
        """Multiple entries produce concatenated size+datagram pairs."""
        s = Score()
        s.add(0.0, OscMessage("/first"))
        s.add(1.0, OscMessage("/second"))
        data = s.to_binary()

        addresses = [b.contents[0].address for b in _decode(data)]
        assert addresses == ["/first", "/second", "/g_freeAll"]

    def test_to_binary_nrt_timestamp(self):
        """Bundle timestamps use raw seconds (no NTP epoch offset)."""
        s = Score()
        s.add(1.0, OscMessage("/test"))
        data = s.to_binary()
        # Skip int32 size prefix + "#bundle\0" (8 bytes)
        size = struct.unpack(">i", data[:4])[0]
        bundle_data = data[4 : 4 + size]
        # Timestamp is at bytes 8-16 of the bundle
        ts_bytes = bundle_data[8:16]
        ts_ntp = struct.unpack(">Q", ts_bytes)[0]
        # 1.0 second in NTP fixed point: integer part = 1, fractional = 0
        # Should be approximately 2^32 (1 second * 2^32)
        ts_seconds = ts_ntp / (2**32)
        assert abs(ts_seconds - 1.0) < 0.001

    def test_to_binary_roundtrip_bundle(self):
        """Bundle datagrams in binary can be decoded back."""
        s = Score()
        msg = OscMessage("/s_new", "sine", 1000, 0, 0)
        s.add(0.5, msg)
        data = s.to_binary()
        size = struct.unpack(">i", data[:4])[0]
        bundle_data = data[4 : 4 + size]
        bundle = OscBundle.from_datagram(bundle_data)
        assert len(bundle.contents) == 1
        decoded_msg = bundle.contents[0]
        assert isinstance(decoded_msg, OscMessage)
        assert decoded_msg.address == "/s_new"


# ---------------------------------------------------------------------------
# NRT render integration test
# ---------------------------------------------------------------------------


class TestScoreRender:
    def test_render_produces_wav(self):
        """Score.render() produces a WAV file with audio data."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar(frequency=440.0) * 0.3)
        sd = builder.build(name="test_nrt")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "test_nrt")
        score.add(0.5, OscMessage("/c_set", 0, 0))

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            output_path = f.name

        score.render(output_path, sample_rate=44100, options=Options(verbosity=-1))
        p = Path(output_path)
        try:
            assert p.exists(), "WAV file was not created"
            assert p.stat().st_size > 44, "WAV file is too small (header only?)"
            # Check WAV header
            with open(output_path, "rb") as fh:
                header = fh.read(4)
                assert header == b"RIFF", f"Not a WAV file: {header!r}"
        finally:
            p.unlink(missing_ok=True)

    def test_render_with_options(self):
        """Score.render() respects Options overrides."""
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar() * 0.1)
        sd = builder.build(name="test_opts")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "test_opts")
        score.add(0.2, OscMessage("/c_set", 0, 0))

        opts = Options(verbosity=-1, block_size=64)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            output_path = f.name

        score.render(output_path, sample_rate=48000, options=opts)
        p = Path(output_path)
        try:
            assert p.exists()
            assert p.stat().st_size > 44
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Score.from_pattern
# ---------------------------------------------------------------------------

from nanosynth.patterns import Pbind, Pmono, Pseq, Rest  # noqa: E402


def _commands(score: Score) -> list[tuple[float, str, tuple]]:
    score.sort()
    return [(t, m.address, tuple(m.contents)) for t, ms in score._entries for m in ms]


class TestFromPattern:
    def test_onsets_and_releases_follow_tempo(self):
        pattern = Pbind(instrument="beep", freq=Pseq([100.0, 200.0]), dur=1.0)
        cmds = _commands(Score.from_pattern(pattern, 10.0, bpm=120.0))
        news = [(t, c[0], c[c.index("freq") + 1]) for t, a, c in cmds if a == "/s_new"]
        assert news == [(0.0, "beep", 100.0), (0.5, "beep", 200.0)]
        # sustain = 0.8 beats = 0.4 s at 120 bpm
        releases = [t for t, a, c in cmds if a == "/n_set" and c[1:] == ("gate", 0.0)]
        assert releases == pytest.approx([0.4, 0.9])

    def test_synthdefs_precede_events(self):
        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar())
        sd = builder.build(name="fp")
        score = Score.from_pattern(Pbind(instrument="fp", dur=1.0), 1.0, synthdefs=[sd])
        assert [a for _, a, _ in _commands(score)][:2] == ["/d_recv", "/s_new"]

    def test_duration_bounds_infinite_pattern(self):
        score = Score.from_pattern(Pbind(dur=0.5), 2.0, bpm=60.0)
        onsets = [t for t, a, _ in _commands(score) if a == "/s_new"]
        assert onsets == [0.0, 0.5, 1.0, 1.5]

    def test_rest_advances_without_synth(self):
        score = Score.from_pattern(Pbind(dur=Pseq([1.0, Rest(1.0), 1.0])), 10.0, bpm=60)
        onsets = [t for t, a, _ in _commands(score) if a == "/s_new"]
        assert onsets == [0.0, 2.0]

    def test_chord_creates_unique_nodes(self):
        score = Score.from_pattern(Pbind(midinote=Pseq([[60, 64, 67]])), 4.0)
        ids = [c[1] for _, a, c in _commands(score) if a == "/s_new"]
        assert len(set(ids)) == 3

    def test_pmono_released_at_stream_end(self):
        score = Score.from_pattern(
            Pmono("m", freq=Pseq([1.0, 2.0]), dur=1.0), 10.0, bpm=60
        )
        cmds = _commands(score)
        assert [a for _, a, _ in cmds].count("/s_new") == 1
        assert cmds[-1][0] == 2.0 and cmds[-1][2][1:] == ("gate", 0.0)

    def test_param_named_target_stays_a_control(self):
        score = Score.from_pattern(Pbind(target=7.0, dur=Pseq([1.0])), 1.0)
        contents = [c for _, a, c in _commands(score) if a == "/s_new"][0]
        assert contents[2:4] == (0, 0)
        assert contents[contents.index("target") + 1] == 7.0

    def test_renders_audio_where_notes_are(self):
        """End to end: a two-note pattern sounds at its onsets, silent between."""
        np = pytest.importorskip("numpy")
        import wave

        from nanosynth.envelopes import EnvGen, Envelope

        with SynthDefBuilder(freq=440.0, gate=1.0) as b:
            env = EnvGen.kr(envelope=Envelope.asr(0.005, 1.0, 0.005), gate=b["gate"])
            Out.ar(bus=0, source=SinOsc.ar(frequency=b["freq"]) * env * 0.3)
        sd = b.build(name="fp_gated")
        # bpm 60: notes at 0 s and 1 s, each sustained 0.4 s.
        score = Score.from_pattern(
            Pbind(instrument="fp_gated", dur=Pseq([1.0, 1.0]), legato=0.4),
            4.0,
            bpm=60.0,
            synthdefs=[sd],
        )
        score.add(1.6, OscMessage("/c_set", 0, 0))  # end marker
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = Path(f.name)
        try:
            score.render(path, output_channels=1, options=Options(verbosity=-1))
            with wave.open(str(path)) as w:
                sr = w.getframerate()
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        finally:
            path.unlink(missing_ok=True)

        def peak(t0: float, t1: float) -> float:
            return float(np.abs(pcm[int(t0 * sr) : int(t1 * sr)]).max()) / 32767

        assert peak(0.1, 0.3) > 0.2
        assert peak(0.5, 0.9) < 0.01
        assert peak(1.1, 1.3) > 0.2
