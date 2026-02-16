"""Tests for Score NRT rendering."""

import struct
import tempfile
from pathlib import Path


from nanosynth.osc import OscBundle, OscMessage
from nanosynth.score import Score
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


class TestScoreSerialization:
    def test_to_binary_empty(self):
        """An empty score produces empty bytes."""
        s = Score()
        assert s.to_binary() == b""

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
        # Total length should be exactly 4 + size
        assert len(data) == 4 + size

    def test_to_binary_multiple_entries(self):
        """Multiple entries produce concatenated size+datagram pairs."""
        s = Score()
        s.add(0.0, OscMessage("/first"))
        s.add(1.0, OscMessage("/second"))
        data = s.to_binary()

        # Parse first entry
        size1 = struct.unpack(">i", data[:4])[0]
        remainder = data[4 + size1 :]
        # Parse second entry
        size2 = struct.unpack(">i", remainder[:4])[0]
        assert size2 > 0
        # Total length matches
        assert len(data) == 4 + size1 + 4 + size2

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

        score.render(output_path, sample_rate=44100)
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
        from nanosynth.scsynth import Options

        with SynthDefBuilder() as builder:
            Out.ar(bus=0, source=SinOsc.ar() * 0.1)
        sd = builder.build(name="test_opts")

        score = Score()
        score.add_synthdef(0.0, sd)
        score.add_synth(0.0, "test_opts")
        score.add(0.2, OscMessage("/c_set", 0, 0))

        opts = Options(verbosity=0, block_size=64)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            output_path = f.name

        score.render(output_path, sample_rate=48000, options=opts)
        p = Path(output_path)
        try:
            assert p.exists()
            assert p.stat().st_size > 44
        finally:
            p.unlink(missing_ok=True)
