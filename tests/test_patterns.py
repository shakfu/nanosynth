"""Tests for the pattern-based sequencing system."""

from __future__ import annotations

import math
import time
from unittest.mock import MagicMock

import pytest

from nanosynth.patterns import (
    Clock,
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
