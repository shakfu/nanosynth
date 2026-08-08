"""Tests for the pattern-based sequencing system."""

from __future__ import annotations

import math
import threading
import time
from unittest.mock import ANY, MagicMock, call

import pytest

from nanosynth.exceptions import EngineError
from nanosynth.patterns import (
    DEFAULT_LATENCY,
    SCALES,
    Clock,
    Pdef,
    Pfin,
    Pfindur,
    Pkey,
    Pmono,
    Ppar,
    Ptpar,
    Pbind,
    Pchoose,
    Pconst,
    Pgeom,
    Player,
    Pn,
    Prand,
    Pseq,
    Pseries,
    Pwhite,
    Rest,
    _META_KEYS,
    _degree_to_note,
    _event_delta,
    _midinote_to_freq,
)


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.01) -> bool:
    """Poll ``predicate`` until true or timeout. Returns the final value.

    Used instead of fixed sleeps so the Player tests don't flake on slow CI.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------------------------------------------------------------------------
# Rest
# ---------------------------------------------------------------------------


class TestRest:
    def test_default_dur(self) -> None:
        r = Rest()
        assert r.dur == 1.0

    def test_custom_dur(self) -> None:
        r = Rest(0.5)
        assert r.dur == 0.5

    def test_repr(self) -> None:
        assert repr(Rest(0.25)) == "Rest(0.25)"

    def test_equality(self) -> None:
        assert Rest(1.0) == Rest(1.0)
        assert Rest(0.5) != Rest(1.0)

    def test_hash(self) -> None:
        assert hash(Rest(1.0)) == hash(Rest(1.0))
        s = {Rest(1.0), Rest(1.0), Rest(0.5)}
        assert len(s) == 2


# ---------------------------------------------------------------------------
# Pseq
# ---------------------------------------------------------------------------


class TestPseq:
    def test_single_repeat(self) -> None:
        assert Pseq([1, 2, 3]).take(10) == [1, 2, 3]

    def test_multiple_repeats(self) -> None:
        assert Pseq([1, 2, 3], repeats=2).take(10) == [1, 2, 3, 1, 2, 3]

    def test_zero_repeats(self) -> None:
        assert Pseq([1, 2, 3], repeats=0).take(10) == []

    def test_infinite_repeats(self) -> None:
        p = Pseq([1, 2], repeats=float("inf"))
        assert p.take(6) == [1, 2, 1, 2, 1, 2]

    def test_nested_pattern_flattening(self) -> None:
        inner = Pseq([10, 20])
        outer = Pseq([1, inner, 3])
        assert outer.take(10) == [1, 10, 20, 3]

    def test_reusable(self) -> None:
        """Patterns produce fresh iterators each time."""
        p = Pseq([1, 2, 3])
        assert list(p) == [1, 2, 3]
        assert list(p) == [1, 2, 3]

    def test_empty_sequence(self) -> None:
        assert Pseq([], repeats=3).take(10) == []


# ---------------------------------------------------------------------------
# Prand
# ---------------------------------------------------------------------------


class TestPrand:
    def test_finite_count(self) -> None:
        p = Prand([1, 2, 3], repeats=5)
        result = p.take(10)
        assert len(result) == 5
        assert all(x in [1, 2, 3] for x in result)

    def test_infinite_default(self) -> None:
        p = Prand([1, 2])
        result = p.take(20)
        assert len(result) == 20


# ---------------------------------------------------------------------------
# Pwhite
# ---------------------------------------------------------------------------


class TestPwhite:
    def test_range(self) -> None:
        p = Pwhite(0.0, 1.0, repeats=100)
        values = list(p)
        assert len(values) == 100
        assert all(0.0 <= v <= 1.0 for v in values)

    def test_custom_range(self) -> None:
        p = Pwhite(10.0, 20.0, repeats=50)
        values = list(p)
        assert all(10.0 <= v <= 20.0 for v in values)


# ---------------------------------------------------------------------------
# Pseries
# ---------------------------------------------------------------------------


class TestPseries:
    def test_default(self) -> None:
        assert Pseries(repeats=5).take(10) == [0.0, 1.0, 2.0, 3.0, 4.0]

    def test_custom_start_step(self) -> None:
        assert Pseries(start=10, step=3, repeats=4).take(10) == [10, 13, 16, 19]

    def test_negative_step(self) -> None:
        assert Pseries(start=5, step=-1, repeats=4).take(10) == [5, 4, 3, 2]


# ---------------------------------------------------------------------------
# Pgeom
# ---------------------------------------------------------------------------


class TestPgeom:
    def test_default(self) -> None:
        assert Pgeom(repeats=4).take(10) == [1.0, 2.0, 4.0, 8.0]

    def test_custom(self) -> None:
        result = Pgeom(start=100, grow=0.5, repeats=4).take(10)
        assert result == [100.0, 50.0, 25.0, 12.5]


# ---------------------------------------------------------------------------
# Pchoose
# ---------------------------------------------------------------------------


class TestPchoose:
    def test_weighted(self) -> None:
        # With extreme weights, one item dominates
        p = Pchoose([1, 2], [1000, 0], repeats=10)
        assert p.take(10) == [1] * 10

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            Pchoose([1, 2], [0.5])


# ---------------------------------------------------------------------------
# Pn
# ---------------------------------------------------------------------------


class TestPn:
    def test_repeat_pattern(self) -> None:
        inner = Pseq([1, 2])
        p = Pn(inner, repeats=3)
        assert p.take(10) == [1, 2, 1, 2, 1, 2]

    def test_single_repeat(self) -> None:
        p = Pn(Pseq([10, 20]), repeats=1)
        assert list(p) == [10, 20]


# ---------------------------------------------------------------------------
# Pconst
# ---------------------------------------------------------------------------


class TestPconst:
    def test_exact_sum(self) -> None:
        p = Pconst(1.0, Pseq([0.25, 0.25, 0.25, 0.25], repeats=float("inf")))
        result = list(p)
        assert result == [0.25, 0.25, 0.25, 0.25]
        assert math.isclose(sum(result), 1.0)

    def test_clip_last(self) -> None:
        p = Pconst(1.0, Pseq([0.3, 0.3, 0.3, 0.3], repeats=float("inf")))
        result = list(p)
        assert math.isclose(sum(result), 1.0)
        assert len(result) == 4
        assert result[-1] == pytest.approx(0.1)

    def test_single_large_value(self) -> None:
        p = Pconst(0.5, Pseq([1.0], repeats=float("inf")))
        result = list(p)
        assert result == [0.5]

    def test_source_exhausted_before_total(self) -> None:
        p = Pconst(10.0, Pseq([1.0, 2.0]))
        result = list(p)
        assert result == [1.0, 2.0]


# ---------------------------------------------------------------------------
# Pattern chaining (|)
# ---------------------------------------------------------------------------


class TestPatternChaining:
    def test_chain_two(self) -> None:
        p = Pseq([1, 2]) | Pseq([3, 4])
        assert list(p) == [1, 2, 3, 4]

    def test_chain_three(self) -> None:
        p = Pseq([1]) | Pseq([2]) | Pseq([3])
        assert list(p) == [1, 2, 3]


# ---------------------------------------------------------------------------
# Pattern.take
# ---------------------------------------------------------------------------


class TestTake:
    def test_take_fewer_than_available(self) -> None:
        assert Pseq([1, 2, 3, 4, 5]).take(3) == [1, 2, 3]

    def test_take_more_than_available(self) -> None:
        assert Pseq([1, 2]).take(10) == [1, 2]

    def test_take_zero(self) -> None:
        assert Pseq([1, 2]).take(0) == []


# ---------------------------------------------------------------------------
# midinote_to_freq
# ---------------------------------------------------------------------------


class TestMidinoteToFreq:
    def test_a440(self) -> None:
        assert _midinote_to_freq(69) == pytest.approx(440.0)

    def test_middle_c(self) -> None:
        assert _midinote_to_freq(60) == pytest.approx(261.6256, rel=1e-4)

    def test_octave(self) -> None:
        assert _midinote_to_freq(81) == pytest.approx(880.0)


# ---------------------------------------------------------------------------
# Pbind
# ---------------------------------------------------------------------------


class TestPbind:
    def test_scalar_only_is_infinite(self) -> None:
        """Scalar-only Pbind produces infinite events; verify with take-like logic."""
        p = Pbind(freq=440.0, dur=0.5)
        it = iter(p)
        events = [next(it) for _ in range(3)]
        assert len(events) == 3
        assert all(e["freq"] == 440.0 for e in events)

    def test_finite_pattern(self) -> None:
        events = list(Pbind(freq=Pseq([440, 550, 660])))
        assert len(events) == 3
        assert events[0]["freq"] == 440
        assert events[1]["freq"] == 550
        assert events[2]["freq"] == 660

    def test_defaults_applied(self) -> None:
        events = list(Pbind(freq=Pseq([440])))
        assert len(events) == 1
        assert events[0]["instrument"] == "default"
        assert events[0]["dur"] == 1.0
        assert events[0]["amp"] == 0.1
        assert events[0]["pan"] == 0.0

    def test_override_defaults(self) -> None:
        events = list(Pbind(freq=Pseq([440]), dur=0.25, amp=0.5))
        assert events[0]["dur"] == 0.25
        assert events[0]["amp"] == 0.5

    def test_stops_on_shortest_pattern(self) -> None:
        events = list(
            Pbind(
                freq=Pseq([440, 550, 660]),
                amp=Pseq([0.1, 0.2]),
            )
        )
        assert len(events) == 2

    def test_midinote_to_freq_conversion(self) -> None:
        events = list(Pbind(midinote=Pseq([69])))
        assert events[0]["freq"] == pytest.approx(440.0)

    def test_explicit_freq_overrides_midinote(self) -> None:
        """If freq is explicitly bound, midinote conversion is skipped."""
        events = list(Pbind(midinote=Pseq([69]), freq=Pseq([100.0])))
        assert events[0]["freq"] == 100.0

    def test_sustain_derived_from_dur(self) -> None:
        events = list(Pbind(freq=Pseq([440]), dur=1.0))
        assert events[0]["sustain"] == pytest.approx(0.8)

    def test_rest_in_dur(self) -> None:
        events = list(Pbind(freq=Pseq([440]), dur=Pseq([Rest(0.5)])))
        assert isinstance(events[0]["dur"], Rest)

    def test_reusable(self) -> None:
        p = Pbind(freq=Pseq([440, 550]))
        assert len(list(p)) == 2
        assert len(list(p)) == 2

    def test_instrument_binding(self) -> None:
        events = list(Pbind(instrument="pad", freq=Pseq([440])))
        assert events[0]["instrument"] == "pad"


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


class TestClock:
    def test_default_bpm(self) -> None:
        clock = Clock()
        try:
            assert clock.bpm == 120.0
        finally:
            clock.stop()

    def test_beat_duration(self) -> None:
        clock = Clock(bpm=60)
        try:
            assert clock.beat_duration == pytest.approx(1.0)
        finally:
            clock.stop()

    def test_set_bpm(self) -> None:
        clock = Clock(bpm=120)
        try:
            clock.bpm = 60
            assert clock.bpm == 60
            assert clock.beat_duration == pytest.approx(1.0)
        finally:
            clock.stop()

    def test_stop_is_idempotent(self) -> None:
        clock = Clock()
        clock.stop()
        clock.stop()  # should not raise


# ---------------------------------------------------------------------------
# Player (with mock server)
# ---------------------------------------------------------------------------


class TestPlayer:
    @pytest.fixture()
    def mock_server(self) -> MagicMock:
        server = MagicMock()
        server.synth.return_value = MagicMock()
        return server

    def test_play_creates_synths(self, mock_server: MagicMock) -> None:
        clock = Clock(bpm=600)  # fast clock for test speed
        try:
            pattern = Pbind(
                instrument="test",
                freq=Pseq([440, 550]),
                dur=0.1,
            )
            player = Player(pattern, clock, mock_server)
            player.play()
            # Two finite events; wait for both synths rather than a fixed sleep.
            _wait_until(lambda: mock_server.synth.call_count >= 2)
            player.stop()
        finally:
            clock.stop()

        assert mock_server.synth.call_count == 2
        # Verify instrument name
        for c in mock_server.synth.call_args_list:
            assert c[0][0] == "test"

    def test_rest_skips_synth_creation(self, mock_server: MagicMock) -> None:
        clock = Clock(bpm=600)
        try:
            pattern = Pbind(
                freq=Pseq([440]),
                dur=Pseq([Rest(0.1)]),
            )
            player = Player(pattern, clock, mock_server)
            player.play()
            # The single rest event ends the (finite) pattern; wait for that.
            _wait_until(lambda: player._stopped)
            player.stop()
        finally:
            clock.stop()

        assert mock_server.synth.call_count == 0

    def test_player_stops_at_pattern_end(self, mock_server: MagicMock) -> None:
        clock = Clock(bpm=600)
        try:
            pattern = Pbind(freq=Pseq([440]), dur=0.1)
            player = Player(pattern, clock, mock_server)
            player.play()
            # Poll instead of fixed sleep -- CI runners may be slow
            deadline = time.monotonic() + 2.0
            while not player._stopped and time.monotonic() < deadline:
                time.sleep(0.05)
            assert player._stopped is True
        finally:
            clock.stop()

    def test_gate_release_scheduled(self, mock_server: MagicMock) -> None:
        clock = Clock(bpm=6000)  # very fast
        synth_mock = MagicMock()
        mock_server.synth.return_value = synth_mock
        try:
            pattern = Pbind(freq=Pseq([440]), dur=0.5, sustain=0.1)
            player = Player(pattern, clock, mock_server)
            player.play()
            # Wait for the scheduled gate-release rather than a fixed sleep.
            _wait_until(lambda: mock_server.set.called)
        finally:
            clock.stop()

        # gate=0 should have been sent
        mock_server.set.assert_called_with(synth_mock, gate=0.0)

    def test_pbind_play_returns_player(self, mock_server: MagicMock) -> None:
        clock = Clock(bpm=120)
        try:
            pattern = Pbind(freq=Pseq([440]))
            player = pattern.play(clock, mock_server)
            assert isinstance(player, Player)
            player.stop()
        finally:
            clock.stop()

    def test_synth_params_passed(self, mock_server: MagicMock) -> None:
        clock = Clock(bpm=600)
        try:
            pattern = Pbind(
                freq=Pseq([440.0]),
                amp=Pseq([0.3]),
                dur=0.1,
            )
            player = Player(pattern, clock, mock_server)
            player.play()
            _wait_until(lambda: mock_server.synth.call_count >= 1)
            player.stop()
        finally:
            clock.stop()

        assert mock_server.synth.call_count == 1
        _, kwargs = mock_server.synth.call_args
        assert kwargs["freq"] == 440.0
        assert kwargs["amp"] == 0.3


class TestLatencyScheduling:
    """Events are dispatched as timestamped bundles, not immediate messages."""

    @pytest.fixture()
    def mock_server(self) -> MagicMock:
        server = MagicMock()
        server.synth.return_value = MagicMock()
        return server

    def test_clock_default_latency(self) -> None:
        clock = Clock(bpm=120)
        try:
            assert clock.latency == DEFAULT_LATENCY
        finally:
            clock.stop()

    def test_clock_latency_settable(self) -> None:
        clock = Clock(bpm=120, latency=0.25)
        try:
            assert clock.latency == 0.25
            clock.latency = 0.05
            assert clock.latency == 0.05
        finally:
            clock.stop()

    def test_player_inherits_clock_latency(self, mock_server: MagicMock) -> None:
        clock = Clock(bpm=120, latency=0.3)
        try:
            player = Player(Pbind(freq=Pseq([440])), clock, mock_server)
            assert player.latency == 0.3
            # An explicit override wins over the clock's value.
            override = Player(Pbind(freq=Pseq([440])), clock, mock_server, latency=0.01)
            assert override.latency == 0.01
        finally:
            clock.stop()

    def test_synth_created_inside_at_block(self, mock_server: MagicMock) -> None:
        """/s_new must be captured by server.at(), not sent bare."""
        clock = Clock(bpm=600, latency=0.05)
        try:
            pattern = Pbind(instrument="test", freq=Pseq([440]), dur=0.1)
            Player(pattern, clock, mock_server).play()
            _wait_until(lambda: mock_server.synth.call_count >= 1)
        finally:
            clock.stop()

        assert mock_server.at.called
        # at() opened before synth() was called.
        assert mock_server.mock_calls.index(
            call.at(ANY)
        ) < mock_server.mock_calls.index(
            call.synth("test", freq=440.0, amp=0.1, pan=0.0)
        )

    def test_onset_timestamp_is_ahead_of_now(self, mock_server: MagicMock) -> None:
        """The bundle timestamp leads wall-clock by roughly the latency."""
        latency = 0.5
        clock = Clock(bpm=600, latency=latency)
        try:
            pattern = Pbind(freq=Pseq([440]), dur=0.1)
            Player(pattern, clock, mock_server).play()
            _wait_until(lambda: mock_server.at.called)
            sent_at = time.time()
        finally:
            clock.stop()

        onset = mock_server.at.call_args_list[0][0][0]
        # Unix-epoch domain, and scheduled into the future by ~latency.
        assert onset > sent_at
        assert onset - sent_at <= latency + 0.2

    def test_gate_release_uses_bundle_not_timer(self, mock_server: MagicMock) -> None:
        """Release is stamped sustain seconds after onset, sent immediately."""
        clock = Clock(bpm=60, latency=0.05)  # 1 beat == 1 second
        try:
            pattern = Pbind(freq=Pseq([440]), dur=2.0, sustain=1.0)
            Player(pattern, clock, mock_server).play()
            # Both at() blocks open during the same tick -- no waiting a full
            # sustain period, which is the point of bundling the release.
            assert _wait_until(lambda: mock_server.at.call_count >= 2, timeout=1.0)
        finally:
            clock.stop()

        onset, release = (c[0][0] for c in mock_server.at.call_args_list[:2])
        assert release - onset == pytest.approx(1.0, abs=1e-6)
        mock_server.set.assert_called_with(mock_server.synth.return_value, gate=0.0)

    def test_no_timer_threads_per_note(self, mock_server: MagicMock) -> None:
        """High event density must not spawn a thread per note."""
        before = threading.active_count()
        clock = Clock(bpm=6000, latency=0.01)
        try:
            pattern = Pbind(freq=Pseq([440] * 40), dur=0.05, sustain=10.0)
            Player(pattern, clock, mock_server).play()
            _wait_until(lambda: mock_server.synth.call_count >= 40, timeout=3.0)
            # Long sustains would each hold a live threading.Timer.
            assert threading.active_count() <= before + 2
        finally:
            clock.stop()

    def test_engine_error_stops_player(self, mock_server: MagicMock) -> None:
        """A quit server ends playback instead of raising every tick."""
        mock_server.at.side_effect = EngineError("server gone")
        clock = Clock(bpm=600)
        try:
            player = Player(Pbind(freq=Pseq([440] * 10), dur=0.1), clock, mock_server)
            player.play()
            assert _wait_until(lambda: player._stopped, timeout=2.0)
        finally:
            clock.stop()

    def test_clock_survives_failing_player(self, mock_server: MagicMock) -> None:
        """One player raising must not silence others on the same clock."""
        bad_server = MagicMock()
        bad_server.at.side_effect = RuntimeError("unexpected")
        clock = Clock(bpm=600)
        try:
            bad = Player(Pbind(freq=Pseq([440] * 10), dur=0.1), clock, bad_server)
            # Non-exhausting, so a stop can only come from the clock dying.
            good = Player(Pbind(freq=Pn(Pseq([550])), dur=0.1), clock, mock_server)
            bad.play()
            good.play()
            assert _wait_until(lambda: bad._stopped, timeout=2.0)
            # The good player keeps ticking after the bad one was culled.
            assert _wait_until(lambda: mock_server.synth.call_count >= 3, timeout=2.0)
            after_cull = mock_server.synth.call_count
            assert _wait_until(
                lambda: mock_server.synth.call_count > after_cull, timeout=2.0
            )
            assert good._stopped is False
        finally:
            clock.stop()


class TestPitchChain:
    """degree -> note -> midinote -> freq, plus db -> amp."""

    def test_degree_to_midinote_major(self) -> None:
        events = Pbind(degree=Pseq([0, 1, 2, 3, 4, 5, 6, 7])).take(8)
        # Major scale from middle C.
        assert [e["midinote"] for e in events] == [
            60.0,
            62.0,
            64.0,
            65.0,
            67.0,
            69.0,
            71.0,
            72.0,
        ]

    def test_degree_zero_is_middle_c(self) -> None:
        event = Pbind(degree=0).take(1)[0]
        assert event["midinote"] == 60.0
        assert event["freq"] == pytest.approx(261.6255653, abs=1e-6)

    def test_negative_degree_wraps_octave_down(self) -> None:
        # Degree -1 in C major is the B below middle C.
        assert Pbind(degree=-1).take(1)[0]["midinote"] == 59.0

    def test_fractional_degree_interpolates(self) -> None:
        # Halfway between degree 0 (0 semitones) and degree 1 (2 semitones).
        assert _degree_to_note(0.5, (0, 2, 4, 5, 7, 9, 11)) == 1.0

    def test_named_scale_root_and_octave(self) -> None:
        events = Pbind(degree=Pseq([0, 2, 4]), scale="minor", root=3, octave=4).take(3)
        assert [e["midinote"] for e in events] == [51.0, 54.0, 58.0]

    def test_explicit_scale_sequence(self) -> None:
        event = Pbind(degree=1, scale=[0, 7]).take(1)[0]
        assert event["midinote"] == 67.0

    def test_unknown_scale_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown scale"):
            Pbind(degree=0, scale="klingon").take(1)

    def test_empty_scale_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            Pbind(degree=0, scale=[]).take(1)

    def test_explicit_freq_bypasses_chain(self) -> None:
        """Binding a downstream key must win over deriving it."""
        assert Pbind(degree=5, freq=100.0).take(1)[0]["freq"] == 100.0

    def test_explicit_midinote_bypasses_degree(self) -> None:
        event = Pbind(degree=5, midinote=69.0).take(1)[0]
        assert event["freq"] == pytest.approx(440.0)

    def test_db_to_amp(self) -> None:
        assert Pbind(db=-6.0).take(1)[0]["amp"] == pytest.approx(0.5011872, abs=1e-6)

    def test_explicit_amp_beats_db(self) -> None:
        assert Pbind(db=-6.0, amp=0.9).take(1)[0]["amp"] == 0.9

    def test_scale_names_are_valid(self) -> None:
        for name in SCALES:
            event = Pbind(degree=0, scale=name).take(1)[0]
            assert isinstance(event["midinote"], float)

    def test_pitch_keys_not_sent_as_params(self) -> None:
        """Derivation inputs are metadata, not synth controls."""
        for key in ("degree", "note", "midinote", "octave", "root", "scale", "db"):
            assert key in _META_KEYS


class TestEventTiming:
    """legato / stretch / delta."""

    def test_default_sustain_is_legato_times_dur(self) -> None:
        event = Pbind(dur=2.0).take(1)[0]
        assert event["sustain"] == pytest.approx(1.6)  # 2.0 * 0.8
        assert event["delta"] == pytest.approx(2.0)

    def test_legato_and_stretch(self) -> None:
        event = Pbind(dur=2.0, legato=0.5, stretch=2.0).take(1)[0]
        assert event["sustain"] == pytest.approx(2.0)  # 2 * 0.5 * 2
        assert event["delta"] == pytest.approx(4.0)  # 2 * 2

    def test_explicit_sustain_and_delta_win(self) -> None:
        event = Pbind(dur=1.0, sustain=5.0, delta=7.0).take(1)[0]
        assert event["sustain"] == 5.0
        assert event["delta"] == 7.0

    def test_rest_delta_uses_rest_duration(self) -> None:
        assert _event_delta(Pbind(dur=Rest(0.25)).take(1)[0]) == pytest.approx(0.25)


class TestPkey:
    def test_reads_sibling_key(self) -> None:
        event = Pbind(freq=Pseq([440.0]), amp=Pkey("freq", lambda f: 100.0 / f)).take(
            1
        )[0]
        assert event["amp"] == pytest.approx(100.0 / 440.0)

    def test_without_transform(self) -> None:
        assert Pbind(freq=330.0, detune=Pkey("freq")).take(1)[0]["detune"] == 330.0

    def test_default_for_missing_key(self) -> None:
        assert Pbind(x=Pkey("nope", default=7.0)).take(1)[0]["x"] == 7.0

    def test_sees_derived_keys(self) -> None:
        """Pkey resolves after the pitch chain, so it can read freq."""
        event = Pbind(degree=0, harmonic=Pkey("freq", lambda f: f * 2)).take(1)[0]
        assert event["harmonic"] == pytest.approx(261.6255653 * 2, abs=1e-4)

    def test_standalone_iteration_raises(self) -> None:
        with pytest.raises(TypeError, match="only meaningful inside a Pbind"):
            iter(Pkey("freq"))


class TestPpar:
    def test_merges_streams_in_time_order(self) -> None:
        a = Pbind(instrument="a", dur=1.0)
        b = Pbind(instrument="b", dur=0.5)
        events = Ppar([a, b]).take(6)
        onsets: list[tuple[float, str]] = []
        t = 0.0
        for event in events:
            onsets.append((t, str(event["instrument"])))
            t += float(event["delta"])
        assert onsets == [
            (0.0, "a"),
            (0.0, "b"),
            (0.5, "b"),
            (1.0, "a"),
            (1.0, "b"),
            (1.5, "b"),
        ]

    def test_simultaneous_events_get_zero_delta(self) -> None:
        """Zero delta is what makes co-incident events share a bundle onset."""
        events = Ppar([Pbind(dur=1.0), Pbind(dur=1.0)]).take(2)
        assert float(events[0]["delta"]) == 0.0

    def test_preserves_per_voice_sustain(self) -> None:
        a = Pbind(instrument="a", dur=4.0)
        b = Pbind(instrument="b", dur=0.5)
        events = Ppar([a, b]).take(2)
        by_name = {str(e["instrument"]): e for e in events}
        assert by_name["a"]["sustain"] == pytest.approx(3.2)
        assert by_name["b"]["sustain"] == pytest.approx(0.4)

    def test_ends_when_all_exhausted(self) -> None:
        a = Pbind(freq=Pseq([1, 2]), dur=1.0)
        b = Pbind(freq=Pseq([3]), dur=1.0)
        assert len(Ppar([a, b]).take(99)) == 3

    def test_empty_pattern_list(self) -> None:
        assert Ppar([]).take(5) == []

    def test_total_duration_matches_longest(self) -> None:
        a = Pbind(freq=Pseq([1, 2, 3]), dur=1.0)
        b = Pbind(freq=Pseq([1] * 6), dur=0.5)
        total = sum(float(e["delta"]) for e in Ppar([a, b]).take(99))
        assert total == pytest.approx(3.0)


class TestPtpar:
    def test_offsets_delay_streams(self) -> None:
        a = Pbind(instrument="a", freq=Pseq([1]), dur=1.0)
        b = Pbind(instrument="b", freq=Pseq([2]), dur=1.0)
        events = Ptpar([(0.0, a), (2.0, b)]).take(4)
        assert [str(e["instrument"]) for e in events] == ["a", "b"]
        # 'a' is followed by a 2-beat gap before 'b'.
        assert float(events[0]["delta"]) == pytest.approx(2.0)


class TestPmono:
    def test_events_share_one_stream_id(self) -> None:
        events = Pmono("bass", freq=Pseq([100, 200, 300])).take(3)
        ids = {str(e["_mono"]) for e in events}
        assert len(ids) == 1

    def test_separate_iterations_get_separate_ids(self) -> None:
        pattern = Pmono("bass", freq=Pseq([100]))
        assert pattern.take(1)[0]["_mono"] != pattern.take(1)[0]["_mono"]

    def test_instrument_defaults_to_argument(self) -> None:
        assert Pmono("bass").take(1)[0]["instrument"] == "bass"

    def test_supports_pitch_chain(self) -> None:
        assert Pmono("bass", degree=0).take(1)[0]["midinote"] == 60.0

    def test_player_creates_one_synth_then_sets(self) -> None:
        server = MagicMock()
        server.synth.return_value = MagicMock()
        clock = Clock(bpm=6000, latency=0.01)
        try:
            player = Player(
                Pmono("bass", freq=Pseq([100, 200, 300]), dur=0.5), clock, server
            )
            player.play()
            _wait_until(lambda: player._stopped, timeout=3.0)
        finally:
            clock.stop()

        # One synth for three events; the rest are /n_set.
        assert server.synth.call_count == 1
        freqs = [
            c.kwargs["freq"] for c in server.set.call_args_list if "freq" in c.kwargs
        ]
        assert freqs == [200.0, 300.0]

    def test_player_releases_mono_synth_at_end(self) -> None:
        server = MagicMock()
        held = MagicMock()
        server.synth.return_value = held
        clock = Clock(bpm=6000, latency=0.01)
        try:
            player = Player(Pmono("bass", freq=Pseq([100]), dur=0.5), clock, server)
            player.play()
            _wait_until(lambda: player._stopped, timeout=3.0)
        finally:
            clock.stop()
        server.set.assert_called_with(held, gate=0.0)

    def test_stop_releases_mono_synth(self) -> None:
        server = MagicMock()
        held = MagicMock()
        server.synth.return_value = held
        clock = Clock(bpm=600, latency=0.01)
        try:
            player = Player(Pmono("bass", freq=Pn(Pseq([100])), dur=1.0), clock, server)
            player.play()
            _wait_until(lambda: server.synth.called, timeout=2.0)
            player.stop()
        finally:
            clock.stop()
        server.set.assert_called_with(held, gate=0.0)


class TestPdef:
    @pytest.fixture(autouse=True)
    def _clear_registry(self):
        Pdef.clear()
        yield
        Pdef.clear()

    def test_lookup_returns_same_instance(self) -> None:
        Pdef("lead", Pbind(freq=440.0))
        assert Pdef("lead") is Pdef("lead")

    def test_lookup_does_not_clear_source(self) -> None:
        Pdef("lead", Pbind(freq=440.0))
        assert Pdef("lead").source is not None

    def test_swap_takes_effect_at_next_event(self) -> None:
        Pdef("lead", Pn(Pbind(freq=440.0)))
        stream = iter(Pdef("lead"))
        assert next(stream)["freq"] == 440.0
        Pdef("lead", Pn(Pbind(freq=880.0)))
        assert next(stream)["freq"] == 880.0

    def test_unassigned_pdef_yields_nothing(self) -> None:
        assert Pdef("empty").take(3) == []

    def test_finite_source_ends_stream(self) -> None:
        Pdef("lead", Pbind(freq=Pseq([1, 2])))
        assert len(Pdef("lead").take(99)) == 2

    def test_source_settable(self) -> None:
        pdef = Pdef("lead", Pbind(freq=440.0))
        pdef.source = Pbind(freq=880.0)
        assert pdef.take(1)[0]["freq"] == 880.0

    def test_repr_and_name(self) -> None:
        assert repr(Pdef("lead")) == "Pdef('lead')"
        assert Pdef("lead").name == "lead"


class TestPfinPfindur:
    def test_pfin_limits_count(self) -> None:
        assert [e["freq"] for e in Pfin(2, Pbind(freq=Pseq([1, 2, 3, 4]))).take(9)] == [
            1,
            2,
        ]

    def test_pfin_shorter_source_unaffected(self) -> None:
        assert len(Pfin(10, Pbind(freq=Pseq([1, 2]))).take(9)) == 2

    def test_pfindur_clips_final_delta(self) -> None:
        events = Pfindur(2.5, Pbind(freq=Pseq([1, 2, 3, 4]), dur=1.0)).take(9)
        deltas = [float(e["delta"]) for e in events]
        assert deltas == [1.0, 1.0, 0.5]
        assert sum(deltas) == pytest.approx(2.5)

    def test_pfindur_exact_fit(self) -> None:
        events = Pfindur(2.0, Pbind(freq=Pseq([1, 2, 3]), dur=1.0)).take(9)
        assert sum(float(e["delta"]) for e in events) == pytest.approx(2.0)


class TestQuantization:
    def test_next_boundary_lands_on_grid(self) -> None:
        clock = Clock(bpm=120)  # 0.5s per beat
        try:
            clock.reset_grid()
            boundary = clock.next_boundary(4.0)
            elapsed_at_boundary = (boundary - clock._origin) / clock.beat_duration
            assert elapsed_at_boundary == pytest.approx(4.0, abs=1e-6)
        finally:
            clock.stop()

    def test_boundary_is_in_the_future(self) -> None:
        clock = Clock(bpm=120)
        try:
            assert clock.next_boundary(1.0) > time.monotonic()
        finally:
            clock.stop()

    def test_offset_shifts_past_boundary(self) -> None:
        clock = Clock(bpm=120)
        try:
            base = clock.next_boundary(4.0)
            shifted = clock.next_boundary(4.0, offset=0.5)
            assert shifted - base == pytest.approx(0.25, abs=1e-6)  # half a beat
        finally:
            clock.stop()

    def test_non_positive_quant_is_immediate(self) -> None:
        clock = Clock(bpm=120)
        try:
            assert clock.next_boundary(0.0) == pytest.approx(time.monotonic(), abs=0.05)
        finally:
            clock.stop()

    def test_players_quantized_to_same_grid_align(self) -> None:
        """Two players started at different moments share a start time."""
        clock = Clock(bpm=600)
        server_a, server_b = MagicMock(), MagicMock()
        try:
            first = Player(Pbind(dur=1.0), clock, server_a).play(quant=4.0)
            time.sleep(0.02)
            second = Player(Pbind(dur=1.0), clock, server_b).play(quant=4.0)
            assert first._next_time == pytest.approx(second._next_time, abs=1e-6)
            first.stop()
            second.stop()
        finally:
            clock.stop()

    def test_unquantized_play_starts_now(self) -> None:
        clock = Clock(bpm=600)
        try:
            player = Player(Pbind(dur=1.0), clock, MagicMock()).play()
            assert player._next_time == pytest.approx(time.monotonic(), abs=0.05)
            player.stop()
        finally:
            clock.stop()

    def test_pattern_play_accepts_quant(self) -> None:
        clock = Clock(bpm=600)
        try:
            player = Pbind(dur=1.0).play(clock, MagicMock(), quant=4.0)
            assert player._next_time > time.monotonic()
            player.stop()
        finally:
            clock.stop()

    def test_chain_input_pkey_resolves_before_derivation(self) -> None:
        """A Pkey bound to a chain input drives the chain rather than reading it."""
        event = Pbind(base=4.0, degree=Pkey("base"), dur=1.0).take(1)[0]
        assert event["midinote"] == 67.0  # degree 4 of C major


class TestGenericWrappersArePlayable:
    """Pn(Pbind(...)) is the idiomatic loop; it must be directly playable."""

    @pytest.mark.parametrize(
        "wrap",
        [
            lambda p: Pn(p, 2),
            lambda p: Pseq([p], repeats=2),
            lambda p: Pfin(3, p),
            lambda p: p | p,
        ],
        ids=["Pn", "Pseq", "Pfin", "chain"],
    )
    def test_wrapped_event_pattern_plays(self, wrap) -> None:
        server = MagicMock()
        server.synth.return_value = MagicMock()
        clock = Clock(bpm=6000, latency=0.01)
        try:
            player = wrap(Pbind(instrument="x", freq=Pseq([440]), dur=0.5)).play(
                clock, server
            )
            assert _wait_until(lambda: server.synth.called, timeout=2.0)
            player.stop()
        finally:
            clock.stop()

    def test_wrapped_pattern_accepts_quant(self) -> None:
        clock = Clock(bpm=600)
        try:
            player = Pn(Pbind(dur=1.0), 2).play(clock, MagicMock(), quant=4.0)
            assert player._next_time > time.monotonic()
            player.stop()
        finally:
            clock.stop()
