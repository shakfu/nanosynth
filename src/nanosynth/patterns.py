"""Pattern-based sequencing system for musical event scheduling.

Patterns are reusable templates that produce fresh iterators each time
(standard Python ``Iterable[T]`` protocol).  This mirrors SuperCollider's
Pattern/Stream split mapped to Python idioms: ``Pattern.__iter__()``
returns a generator.

Basic usage::

    from nanosynth.patterns import Pseq, Pbind, Clock

    pattern = Pbind(
        instrument="default",
        freq=Pseq([440, 550, 660], repeats=2),
        dur=0.5,
        amp=0.3,
    )

    clock = Clock(bpm=120)
    player = pattern.play(clock, server)
    # ... later ...
    player.stop()
    clock.stop()
"""

from __future__ import annotations

import random
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from typing import Any, Generic, TypeVar, Union

from .exceptions import EngineError

T = TypeVar("T")

# Type alias for events -- string keys mapping to float, str, or Rest values.
Event = dict[str, Union[float, str, "Rest"]]

_EVENT_DEFAULTS: Event = {
    "instrument": "default",
    "dur": 1.0,
    "amp": 0.1,
    "pan": 0.0,
}


class Rest:
    """Silence marker.

    When ``dur`` in an event is a ``Rest`` instance, the Player advances
    time by ``rest.dur`` beats but does not create a synth.
    """

    __slots__ = ("dur",)

    def __init__(self, dur: float = 1.0) -> None:
        self.dur = dur

    def __repr__(self) -> str:
        return f"Rest({self.dur})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Rest):
            return self.dur == other.dur
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("Rest", self.dur))


# ---------------------------------------------------------------------------
# Pattern ABC
# ---------------------------------------------------------------------------


class Pattern(ABC, Generic[T]):
    """Abstract base class for all patterns.

    Subclasses must implement ``__iter__`` which returns a fresh iterator
    each time it is called.
    """

    @abstractmethod
    def __iter__(self) -> Iterator[T]: ...

    def take(self, n: int) -> list[T]:
        """Consume and return the first *n* values from this pattern."""
        result: list[T] = []
        for i, val in enumerate(self):
            if i >= n:
                break
            result.append(val)
        return result

    def __or__(self, other: Pattern[T]) -> _Chain[T]:
        """Chain two patterns: ``p1 | p2`` yields p1 then p2."""
        return _Chain(self, other)


class _Chain(Pattern[T]):
    """Internal: concatenation of two patterns via ``|``."""

    def __init__(self, left: Pattern[T], right: Pattern[T]) -> None:
        self._left = left
        self._right = right

    def __iter__(self) -> Iterator[T]:
        yield from self._left
        yield from self._right


# ---------------------------------------------------------------------------
# Value Patterns
# ---------------------------------------------------------------------------


class Pseq(Pattern[T]):
    """Sequential playback of a sequence.

    If an element is itself a ``Pattern``, it is flattened (yielded from).

    Args:
        sequence: Items to yield.
        repeats: Number of times to cycle through the sequence.
    """

    def __init__(
        self, sequence: Sequence[T | Pattern[T]], repeats: int | float = 1
    ) -> None:
        self._sequence = sequence
        self._repeats = repeats

    def __iter__(self) -> Iterator[T]:
        count = 0
        while count < self._repeats:
            for item in self._sequence:
                if isinstance(item, Pattern):
                    yield from item
                else:
                    yield item
            count += 1


class Prand(Pattern[T]):
    """Random selection from a sequence.

    Args:
        sequence: Pool of items to choose from.
        repeats: Number of values to produce.
    """

    def __init__(
        self, sequence: Sequence[T], repeats: int | float = float("inf")
    ) -> None:
        self._sequence = sequence
        self._repeats = repeats

    def __iter__(self) -> Iterator[T]:
        count = 0
        while count < self._repeats:
            yield random.choice(self._sequence)
            count += 1


class Pwhite(Pattern[float]):
    """Uniform random float between *lo* and *hi*.

    Args:
        lo: Lower bound (inclusive).
        hi: Upper bound (inclusive).
        repeats: Number of values to produce.
    """

    def __init__(
        self, lo: float = 0.0, hi: float = 1.0, repeats: int | float = float("inf")
    ) -> None:
        self._lo = lo
        self._hi = hi
        self._repeats = repeats

    def __iter__(self) -> Iterator[float]:
        count = 0
        while count < self._repeats:
            yield random.uniform(self._lo, self._hi)
            count += 1


class Pseries(Pattern[float]):
    """Arithmetic series: ``start, start+step, start+2*step, ...``

    Args:
        start: Initial value.
        step: Increment per step.
        repeats: Number of values to produce.
    """

    def __init__(
        self, start: float = 0.0, step: float = 1.0, repeats: int | float = float("inf")
    ) -> None:
        self._start = start
        self._step = step
        self._repeats = repeats

    def __iter__(self) -> Iterator[float]:
        value = self._start
        count = 0
        while count < self._repeats:
            yield value
            value += self._step
            count += 1


class Pgeom(Pattern[float]):
    """Geometric series: ``start, start*grow, start*grow^2, ...``

    Args:
        start: Initial value.
        grow: Multiplier per step.
        repeats: Number of values to produce.
    """

    def __init__(
        self, start: float = 1.0, grow: float = 2.0, repeats: int | float = float("inf")
    ) -> None:
        self._start = start
        self._grow = grow
        self._repeats = repeats

    def __iter__(self) -> Iterator[float]:
        value = self._start
        count = 0
        while count < self._repeats:
            yield value
            value *= self._grow
            count += 1


class Pchoose(Pattern[T]):
    """Weighted random selection from items.

    Args:
        items: Pool of items to choose from.
        weights: Relative weights for each item (must sum to > 0).
        repeats: Number of values to produce.
    """

    def __init__(
        self,
        items: Sequence[T],
        weights: Sequence[float],
        repeats: int | float = float("inf"),
    ) -> None:
        if len(items) != len(weights):
            raise ValueError("items and weights must have the same length")
        self._items = items
        self._weights = weights
        self._repeats = repeats

    def __iter__(self) -> Iterator[T]:
        count = 0
        while count < self._repeats:
            yield random.choices(self._items, weights=self._weights, k=1)[0]
            count += 1


class Pn(Pattern[T]):
    """Repeat a pattern N times.

    Each repetition creates a fresh iterator from the wrapped pattern.

    Args:
        pattern: The pattern to repeat.
        repeats: Number of full repetitions.
    """

    def __init__(
        self, pattern: Pattern[T], repeats: int | float = float("inf")
    ) -> None:
        self._pattern = pattern
        self._repeats = repeats

    def __iter__(self) -> Iterator[T]:
        count = 0
        while count < self._repeats:
            yield from self._pattern
            count += 1


class Pconst(Pattern[float]):
    """Yield values from *pattern* until their sum reaches *total*.

    The last value is clipped so the sum equals *total* exactly.

    Args:
        total: Target sum.
        pattern: Source pattern for values.
    """

    def __init__(self, total: float, pattern: Pattern[float]) -> None:
        self._total = total
        self._pattern = pattern

    def __iter__(self) -> Iterator[float]:
        remaining = self._total
        for value in self._pattern:
            if remaining <= 0:
                break
            if value >= remaining:
                yield remaining
                break
            yield value
            remaining -= value


# ---------------------------------------------------------------------------
# Pbind -- event pattern
# ---------------------------------------------------------------------------


def _midinote_to_freq(midinote: float) -> float:
    """Convert MIDI note number to frequency in Hz."""
    result: float = 440.0 * (2.0 ** ((midinote - 69.0) / 12.0))
    return result


class Pbind(Pattern[Event]):
    """Bind keys to patterns/values to produce a stream of events.

    Stops when any bound pattern is exhausted.  Scalar values repeat
    forever.  Events are merged with ``_EVENT_DEFAULTS``.

    Args:
        **bindings: Key-value pairs where values can be floats,
            strings, Rest instances, or Pattern instances.
    """

    def __init__(self, **bindings: float | str | Rest | Pattern[Any]) -> None:
        self._bindings = bindings

    def __iter__(self) -> Iterator[Event]:
        # Create iterators for pattern bindings; scalars stay as-is
        iters: dict[str, Iterator[Any]] = {}
        scalars: dict[str, float | str | Rest] = {}
        for key, val in self._bindings.items():
            if isinstance(val, Pattern):
                iters[key] = iter(val)
            else:
                scalars[key] = val

        while True:
            event: Event = dict(_EVENT_DEFAULTS)
            event.update(scalars)

            # Pull from pattern iterators -- stop if any is exhausted
            exhausted = False
            for key, it in iters.items():
                try:
                    event[key] = next(it)
                except StopIteration:
                    exhausted = True
                    break
            if exhausted:
                break

            # Derive freq from midinote if present and freq not explicitly bound
            if "midinote" in event and "freq" not in self._bindings:
                mn = event["midinote"]
                if isinstance(mn, (int, float)):
                    event["freq"] = _midinote_to_freq(float(mn))

            # Derive sustain from dur if not explicitly set
            if "sustain" not in event:
                dur = event.get("dur", 1.0)
                if isinstance(dur, Rest):
                    event["sustain"] = dur.dur * 0.8
                elif isinstance(dur, (int, float)):
                    event["sustain"] = float(dur) * 0.8

            yield event

    def play(self, clock: Clock, server: Any) -> Player:
        """Start playing this pattern on the given clock and server.

        Args:
            clock: The Clock providing tempo.
            server: A Server instance for synth creation.

        Returns:
            A Player that can be stopped.
        """
        player = Player(self, clock, server)
        return player.play()


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


class Clock:
    """Tempo clock that drives pattern playback.

    Runs a background daemon thread.  Uses ``time.monotonic()`` for
    drift-free absolute scheduling.  Multiple players share one clock
    for synchronized timing.

    Args:
        bpm: Beats per minute (default 120).
    """

    def __init__(self, bpm: float = 120.0) -> None:
        self._bpm = bpm
        self._players: list[Player] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def bpm(self) -> float:
        """Beats per minute.  Settable; takes effect on next beat."""
        return self._bpm

    @bpm.setter
    def bpm(self, value: float) -> None:
        self._bpm = value

    @property
    def beat_duration(self) -> float:
        """Duration of one beat in seconds (read-only: ``60 / bpm``)."""
        return 60.0 / self._bpm

    def _add_player(self, player: Player) -> None:
        with self._lock:
            self._players.append(player)

    def _remove_player(self, player: Player) -> None:
        with self._lock:
            try:
                self._players.remove(player)
            except ValueError:
                pass

    def _run(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                players = list(self._players)

            now = time.monotonic()
            earliest_next = now + 0.1  # default wake interval

            for player in players:
                if player._stopped:
                    continue
                if player._next_time <= now:
                    player._tick(now)
                if not player._stopped and player._next_time < earliest_next:
                    earliest_next = player._next_time

            sleep_time = max(0.0, earliest_next - time.monotonic())
            self._stop_event.wait(timeout=sleep_time)

    def stop(self) -> None:
        """Stop the clock and all its players."""
        self._stop_event.set()
        with self._lock:
            for player in self._players:
                player._stopped = True
            self._players.clear()


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

# Keys that are metadata, not synth params
_META_KEYS = frozenset({"instrument", "dur", "sustain", "midinote"})


class Player:
    """Drives event playback from a pattern on a clock.

    Created by ``Pbind.play()`` or directly.

    Args:
        pattern: An event pattern to play.
        clock: The tempo clock.
        server: A Server instance for synth creation.
    """

    def __init__(self, pattern: Pattern[Event], clock: Clock, server: Any) -> None:
        self._pattern = pattern
        self._clock = clock
        self._server = server
        self._iter: Iterator[Event] | None = None
        self._stopped = True
        self._next_time = 0.0

    def play(self) -> Player:
        """Start playback.  Returns self for chaining."""
        self._iter = iter(self._pattern)
        self._stopped = False
        self._next_time = time.monotonic()
        self._clock._add_player(self)
        return self

    def stop(self) -> None:
        """Stop playback."""
        self._stopped = True
        self._clock._remove_player(self)

    def _tick(self, now: float) -> None:
        """Called by the clock thread.  Pull next event and schedule synth."""
        if self._iter is None or self._stopped:
            return

        try:
            event = next(self._iter)
        except StopIteration:
            self._stopped = True
            self._clock._remove_player(self)
            return

        dur_val = event.get("dur", 1.0)

        # Determine beat duration for time advancement
        if isinstance(dur_val, Rest):
            dur_beats = dur_val.dur
        elif isinstance(dur_val, (int, float)):
            dur_beats = float(dur_val)
        else:
            dur_beats = 1.0

        beat_dur = self._clock.beat_duration
        # Advance from the previous scheduled target, not from the wall-clock
        # wake time `now`. Seeding from `now` would bake every late wake-up
        # into the next event's deadline, accumulating drift over a session.
        # If the clock fell behind, _next_time stays <= now and the clock's
        # run loop fires successive events back-to-back until it catches up.
        self._next_time = self._next_time + dur_beats * beat_dur

        # Rest: advance time without creating a synth
        if isinstance(dur_val, Rest):
            return

        # Extract synth params (everything except meta keys)
        instrument = str(event.get("instrument", "default"))
        params: dict[str, float] = {}
        for key, val in event.items():
            if key in _META_KEYS:
                continue
            if isinstance(val, (int, float)):
                params[key] = float(val)

        # Create the synth
        synth = self._server.synth(instrument, **params)

        # Schedule gate release for gated envelopes
        sustain_val = event.get("sustain")
        if isinstance(sustain_val, (int, float)):
            sustain_secs = float(sustain_val) * beat_dur
            timer = threading.Timer(sustain_secs, self._release_synth, args=(synth,))
            timer.daemon = True
            timer.start()

    def _release_synth(self, synth: Any) -> None:
        """Send gate=0 to release a synth's envelope."""
        try:
            self._server.set(synth, gate=0.0)
        except (EngineError, OSError):
            pass  # Server may have quit or connection lost
