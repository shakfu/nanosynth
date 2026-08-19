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

import itertools
import logging
import math
import random
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence
from collections.abc import Sequence as SequenceABC
from collections.abc import Set as SetABC
from typing import Any, Generic, TypeVar, Union

from .exceptions import EngineError

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Default scheduling latency in seconds. Events are sent as OSC bundles
#: stamped this far ahead of the wall clock, giving the engine slack to
#: schedule them sample-accurately rather than firing them on arrival.
DEFAULT_LATENCY = 0.1


def _monotonic_to_unix(when: float) -> float:
    """Convert a ``time.monotonic()`` instant to the ``time.time()`` domain.

    Clock scheduling uses ``time.monotonic()`` (immune to wall-clock jumps),
    but OSC bundle timestamps are Unix epoch seconds, so deadlines must be
    translated at send time.
    """
    return time.time() + (when - time.monotonic())


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

    def play(
        self,
        clock: Clock,
        server: Any,
        latency: float | None = None,
        quant: float | None = None,
        offset: float = 0.0,
    ) -> Player:
        """Start playing this pattern on the given clock and server.

        Defined here rather than on :class:`EventPattern` so that the generic
        wrappers -- ``Pn(Pbind(...))``, ``Pseq([...])``, ``Pfin(...)`` -- stay
        playable.  Only patterns that yield events are meaningful to play; a
        value pattern will produce nonsense.

        Args:
            clock: The Clock providing tempo.
            server: A Server instance for synth creation.
            latency: Scheduling latency override in seconds; defaults to the
                clock's latency.
            quant: Quantization in beats.  Playback starts on the next
                ``quant``-beat boundary of the clock's grid instead of
                immediately, so patterns launched at different moments stay
                phase-aligned.  ``None`` (the default) starts at once.
            offset: Beats past the quantization boundary at which to start.

        Returns:
            A Player that can be stopped.
        """
        player = Player(self, clock, server, latency=latency)  # type: ignore[arg-type]
        return player.play(quant=quant, offset=offset)


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
        seed: Optional RNG seed. When given, each iteration restarts from this
            seed, so the pattern is reproducible (e.g. for NRT rendering). When
            ``None`` (default) a fresh per-instance RNG is used -- still
            independent of the global ``random`` state, so unrelated ``random``
            calls elsewhere cannot perturb the sequence.
    """

    def __init__(
        self,
        sequence: Sequence[T],
        repeats: int | float = float("inf"),
        seed: int | None = None,
    ) -> None:
        self._sequence = sequence
        self._repeats = repeats
        self._seed = seed

    def __iter__(self) -> Iterator[T]:
        rng = random.Random(self._seed)
        count = 0
        while count < self._repeats:
            yield rng.choice(self._sequence)
            count += 1


class Pwhite(Pattern[float]):
    """Uniform random float between *lo* and *hi*.

    Args:
        lo: Lower bound (inclusive).
        hi: Upper bound (inclusive).
        repeats: Number of values to produce.
        seed: Optional RNG seed (see :class:`Prand` for the seeding semantics).
    """

    def __init__(
        self,
        lo: float = 0.0,
        hi: float = 1.0,
        repeats: int | float = float("inf"),
        seed: int | None = None,
    ) -> None:
        self._lo = lo
        self._hi = hi
        self._repeats = repeats
        self._seed = seed

    def __iter__(self) -> Iterator[float]:
        rng = random.Random(self._seed)
        count = 0
        while count < self._repeats:
            yield rng.uniform(self._lo, self._hi)
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
        seed: Optional RNG seed (see :class:`Prand` for the seeding semantics).
    """

    def __init__(
        self,
        items: Sequence[T],
        weights: Sequence[float],
        repeats: int | float = float("inf"),
        seed: int | None = None,
    ) -> None:
        if len(items) != len(weights):
            raise ValueError("items and weights must have the same length")
        self._items = items
        self._weights = weights
        self._repeats = repeats
        self._seed = seed

    def __iter__(self) -> Iterator[T]:
        rng = random.Random(self._seed)
        count = 0
        while count < self._repeats:
            yield rng.choices(self._items, weights=self._weights, k=1)[0]
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


#: Named scales as semitone offsets within an octave.  Used by the ``degree``
#: key of an event; pass a name or an explicit list as ``scale``.
SCALES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor": (0, 2, 3, 5, 7, 9, 11),
    "ionian": (0, 2, 4, 5, 7, 9, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    "major_pentatonic": (0, 2, 4, 7, 9),
    "minor_pentatonic": (0, 3, 5, 7, 10),
    "blues": (0, 3, 5, 6, 7, 10),
    "whole_tone": (0, 2, 4, 6, 8, 10),
    "chromatic": (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
}

# Event keys that are metadata or inputs to the derivation chain below, never
# passed to the synth as control parameters.
_META_KEYS = frozenset(
    {
        "instrument",
        "dur",
        "delta",
        "sustain",
        "legato",
        "stretch",
        "degree",
        "note",
        "midinote",
        "octave",
        "root",
        "scale",
        "db",
        "_mono",
    }
)


def _resolve_scale(value: Any) -> Sequence[int]:
    """Coerce a ``scale`` event value to a sequence of semitone offsets."""
    if isinstance(value, str):
        try:
            return SCALES[value]
        except KeyError:
            raise ValueError(
                f"unknown scale {value!r}; choose from {sorted(SCALES)}"
            ) from None
    if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes)):
        steps = [int(x) for x in value]
        if not steps:
            raise ValueError("scale must not be empty")
        return steps
    raise ValueError(f"scale must be a name or a sequence of semitones, got {value!r}")


def _degree_to_note(degree: float, scale: Sequence[int]) -> float:
    """Map a scale degree to a semitone offset, wrapping across octaves.

    Degrees outside the scale length wrap into higher/lower octaves, so degree
    7 of a 7-note scale is the octave above degree 0.  Fractional degrees
    interpolate between adjacent scale steps.
    """
    steps = len(scale)
    index = math.floor(degree)
    frac = degree - index
    octave, position = divmod(index, steps)
    note = float(scale[position]) + 12.0 * octave
    if frac:
        # Interpolate toward the next degree (which may be the octave above).
        next_octave, next_position = divmod(index + 1, steps)
        next_note = float(scale[next_position]) + 12.0 * next_octave
        note += frac * (next_note - note)
    return note


def _derive_event(event: Event, explicit: SetABC[str]) -> None:
    """Fill in derived event keys in place.

    Implements the SuperCollider derivation chain -- ``degree`` -> ``note`` ->
    ``midinote`` -> ``freq``, plus ``db`` -> ``amp`` and the
    ``dur``/``legato``/``stretch`` -> ``sustain``/``delta`` timing keys.  Each
    step is skipped when the user bound that key explicitly, so binding
    ``freq`` directly bypasses the pitch chain entirely.
    """
    # -- Pitch: degree -> note -> midinote -> freq --------------------------
    if "degree" in event and "note" not in explicit:
        degree = event["degree"]
        if isinstance(degree, (int, float)):
            scale = _resolve_scale(event.get("scale", "major"))
            event["note"] = _degree_to_note(float(degree), scale)

    if "note" in event and "midinote" not in explicit:
        note = event["note"]
        if isinstance(note, (int, float)):
            root = event.get("root", 0.0)
            octave = event.get("octave", 5.0)
            root_f = float(root) if isinstance(root, (int, float)) else 0.0
            octave_f = float(octave) if isinstance(octave, (int, float)) else 5.0
            # octave 5 puts note 0 at MIDI 60 (middle C), as in sclang.
            event["midinote"] = float(note) + root_f + 12.0 * octave_f

    if "midinote" in event and "freq" not in explicit:
        midinote = event["midinote"]
        if isinstance(midinote, (int, float)):
            event["freq"] = _midinote_to_freq(float(midinote))

    # -- Amplitude: db -> amp ----------------------------------------------
    if "db" in event and "amp" not in explicit:
        db = event["db"]
        if isinstance(db, (int, float)):
            event["amp"] = 10.0 ** (float(db) / 20.0)

    # -- Timing: dur/legato/stretch -> sustain, delta -----------------------
    dur = event.get("dur", 1.0)
    dur_beats = dur.dur if isinstance(dur, Rest) else dur
    if not isinstance(dur_beats, (int, float)):
        dur_beats = 1.0
    stretch = event.get("stretch", 1.0)
    stretch_f = float(stretch) if isinstance(stretch, (int, float)) else 1.0

    if "sustain" not in event:
        legato = event.get("legato", 0.8)
        legato_f = float(legato) if isinstance(legato, (int, float)) else 0.8
        event["sustain"] = float(dur_beats) * legato_f * stretch_f

    if "delta" not in event:
        event["delta"] = float(dur_beats) * stretch_f


def _event_delta(event: Event) -> float:
    """Beats to advance after *event* -- its ``delta``, falling back to ``dur``."""
    delta = event.get("delta")
    if isinstance(delta, (int, float)):
        return float(delta)
    dur = event.get("dur", 1.0)
    if isinstance(dur, Rest):
        return float(dur.dur)
    if isinstance(dur, (int, float)):
        return float(dur)
    return 1.0


# Keys that feed the derivation chain. A Pkey bound to one of these is
# resolved *before* derivation runs (so it can supply a degree or a dur);
# any other Pkey is resolved *after* (so it can read a derived freq or amp).
_CHAIN_INPUT_KEYS = frozenset(
    {
        "degree",
        "note",
        "midinote",
        "scale",
        "root",
        "octave",
        "db",
        "dur",
        "legato",
        "stretch",
    }
)


class Pkey(Pattern[Any]):
    """Reference another key of the event currently being built.

    Resolved by :class:`Pbind` alongside its other bindings, so it sees their
    values for this event::

        Pbind(freq=Pseq([440, 660]), amp=Pkey("freq", lambda f: 100.0 / f))

    Ordering follows from what the bound key is. A ``Pkey`` bound to an input
    of the derivation chain (``degree``, ``dur``, ``db``, ...) resolves before
    the chain runs, so it can drive it. A ``Pkey`` bound to anything else
    resolves after, so it can read the chain's output::

        # amp follows the derived freq, not the raw degree
        Pbind(degree=Pseq([0, 4]), amp=Pkey("freq", lambda f: 40.0 / f))

    Args:
        key: Name of the event key to read.
        transform: Optional callable applied to the referenced value.
        default: Value used when the referenced key is absent.

    Note that patterns do not overload arithmetic operators, so combine values
    with *transform* rather than writing ``Pkey("freq") * 2``.
    """

    def __init__(
        self,
        key: str,
        transform: Callable[[Any], Any] | None = None,
        default: Any = 0.0,
    ) -> None:
        self._key = key
        self._transform = transform
        self._default = default

    def __iter__(self) -> Iterator[Any]:
        raise TypeError(
            "Pkey is only meaningful inside a Pbind, where it reads a sibling "
            "key of the event being built; it has no standalone value stream"
        )

    def _resolve(self, event: Event) -> Any:
        value = event.get(self._key, self._default)
        return self._transform(value) if self._transform is not None else value


class EventPattern(Pattern[Event]):
    """Base class for patterns that yield events rather than bare values.

    A marker for the event layer -- ``Pbind`` and the composites built on it.
    :meth:`Pattern.play` lives on the base class, so generic wrappers such as
    ``Pn(Pbind(...))`` are playable too.
    """


class Pbind(EventPattern):
    """Bind keys to patterns/values to produce a stream of events.

    Stops when any bound pattern is exhausted.  Scalar values repeat
    forever.  Events are merged with ``_EVENT_DEFAULTS``.

    Args:
        **bindings: Key-value pairs where values can be floats,
            strings, Rest instances, or Pattern instances.
    """

    def __init__(self, **bindings: float | str | Rest | Pattern[Any] | Pkey) -> None:
        self._bindings = bindings

    def __iter__(self) -> Iterator[Event]:
        # Split bindings by kind. Pkey bindings are deferred to the end of each
        # event because they read the values the other bindings produced.
        iters: dict[str, Iterator[Any]] = {}
        scalars: dict[str, Any] = {}
        keyrefs: dict[str, Pkey] = {}
        for key, val in self._bindings.items():
            if isinstance(val, Pkey):
                keyrefs[key] = val
            elif isinstance(val, Pattern):
                iters[key] = iter(val)
            else:
                scalars[key] = val
        explicit = frozenset(self._bindings)

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

            # Pkeys feeding the derivation chain resolve first, in binding
            # order, so one may reference an earlier one.
            for key, ref in keyrefs.items():
                if key in _CHAIN_INPUT_KEYS:
                    event[key] = ref._resolve(event)

            _derive_event(event, explicit)

            # The rest resolve against the finished event, so they can read
            # derived values such as freq, amp, sustain and delta.
            for key, ref in keyrefs.items():
                if key not in _CHAIN_INPUT_KEYS:
                    event[key] = ref._resolve(event)

            yield event


# ---------------------------------------------------------------------------
# Composite event patterns
# ---------------------------------------------------------------------------


class Ppar(EventPattern):
    """Play several event patterns in parallel, merged into one stream.

    Events from all sub-patterns are interleaved in time order.  Each yielded
    event's ``delta`` is rewritten to the gap until the next event in the
    merged stream, while its ``sustain`` (and every other key) is left alone,
    so each voice keeps its own note lengths.  Simultaneous events land in the
    same bundle timestamp and therefore start on the same sample.

    The merged stream ends when every sub-pattern is exhausted.

    Args:
        patterns: Event patterns to run concurrently.
    """

    def __init__(self, patterns: Sequence[Pattern[Event]]) -> None:
        self._patterns = list(patterns)

    def _entries(self) -> list[tuple[float, Pattern[Event]]]:
        return [(0.0, pattern) for pattern in self._patterns]

    def __iter__(self) -> Iterator[Event]:
        # Each entry tracks a stream's next onset (in beats from the start of
        # the merged stream), a tiebreak index, its iterator, and the event
        # waiting to be emitted.
        entries: list[list[Any]] = []
        for index, (offset, pattern) in enumerate(self._entries()):
            iterator = iter(pattern)
            first = next(iterator, None)
            if first is not None:
                entries.append([offset, index, iterator, first])

        # Preserve a nonzero leading offset (all voices delayed, e.g. a Ptpar
        # whose smallest offset is > 0). Only inter-event gaps are encoded as
        # `delta` below, so without this the initial silence is dropped and the
        # stream starts early. Emit a leading rest that advances by min_onset.
        if entries:
            min_onset = min(entry[0] for entry in entries)
            if min_onset > 0:
                yield {"dur": Rest(min_onset), "delta": min_onset}

        while entries:
            entries.sort(key=lambda entry: (entry[0], entry[1]))
            onset, _, iterator, event = entries[0]
            advance = _event_delta(event)

            following = next(iterator, None)
            if following is None:
                entries.pop(0)
            else:
                entries[0][0] = onset + advance
                entries[0][3] = following

            if entries:
                next_onset = min(entry[0] for entry in entries)
                merged = max(0.0, next_onset - onset)
            else:
                merged = advance

            merged_event = dict(event)
            merged_event["delta"] = merged
            yield merged_event


class Ptpar(Ppar):
    """Like :class:`Ppar`, but each pattern starts at its own beat offset.

    Args:
        pairs: ``(offset_in_beats, pattern)`` tuples.
    """

    def __init__(self, pairs: Sequence[tuple[float, Pattern[Event]]]) -> None:
        self._pairs = [(float(offset), pattern) for offset, pattern in pairs]
        super().__init__([pattern for _, pattern in self._pairs])

    def _entries(self) -> list[tuple[float, Pattern[Event]]]:
        return list(self._pairs)


# Distinguishes the synth belonging to one Pmono stream from any other.
_mono_ids = itertools.count(1)


class Pmono(EventPattern):
    """One persistent synth whose parameters are updated per event.

    Where :class:`Pbind` creates a synth per event, ``Pmono`` creates a single
    synth on its first event and sends ``/n_set`` for every event after that,
    releasing it when the pattern ends.  This is how sclang models a
    monophonic, continuously-gliding line (portamento, filter sweeps) that a
    stream of separate synths cannot produce.

    Accepts the same bindings as :class:`Pbind`, including the pitch chain.
    ``sustain`` is ignored: the synth is held for the whole pattern rather than
    released per note.

    Args:
        instrument: SynthDef name for the persistent synth.
        **bindings: As :class:`Pbind`.
    """

    def __init__(
        self,
        instrument: str = "default",
        **bindings: float | str | Rest | Pattern[Any] | Pkey,
    ) -> None:
        bindings.setdefault("instrument", instrument)
        self._source = Pbind(**bindings)

    def __iter__(self) -> Iterator[Event]:
        # A fresh id per iteration keeps two concurrent plays of the same
        # Pmono (e.g. inside a Ppar) on separate synths.
        mono_id = f"mono-{next(_mono_ids)}"
        for event in self._source:
            tagged = dict(event)
            tagged["_mono"] = mono_id
            yield tagged


class Pdef(EventPattern):
    """A named, hot-swappable event pattern.

    ``Pdef(name, pattern)`` registers or replaces the pattern stored under
    *name*; ``Pdef(name)`` looks up the existing one.  A player iterating a
    ``Pdef`` picks up a replacement at the next event boundary, so a running
    part can be redefined without stopping playback -- the pattern analogue of
    :class:`~nanosynth.proxy.Ndef`.

    The stream ends when the current source is exhausted; wrap the source in
    :class:`Pn` to loop it.

    Args:
        name: Registry key.
        pattern: New source pattern, or ``None`` to look up an existing entry.
    """

    _registry: dict[str, Pdef] = {}
    _registry_lock = threading.Lock()
    # Established in __new__, since a lookup must not reset an existing entry.
    _name: str
    _pattern: Pattern[Event] | None

    def __new__(cls, name: str, pattern: Pattern[Event] | None = None) -> Pdef:
        with cls._registry_lock:
            existing = cls._registry.get(name)
            if existing is None:
                existing = super().__new__(cls)
                existing._name = name
                existing._pattern = None
                cls._registry[name] = existing
            if pattern is not None:
                existing._pattern = pattern
            return existing

    def __init__(self, name: str, pattern: Pattern[Event] | None = None) -> None:
        # State is established in __new__ so that looking up an existing Pdef
        # does not reset it; __init__ still runs on the returned instance.
        pass

    @property
    def name(self) -> str:
        """The registry key this Pdef is stored under."""
        return self._name

    @property
    def source(self) -> Pattern[Event] | None:
        """The current source pattern, or ``None`` if never assigned."""
        return self._pattern

    @source.setter
    def source(self, pattern: Pattern[Event] | None) -> None:
        self._pattern = pattern

    @classmethod
    def clear(cls) -> None:
        """Forget every registered Pdef.  Does not stop running players."""
        with cls._registry_lock:
            cls._registry.clear()

    def __repr__(self) -> str:
        return f"Pdef({self._name!r})"

    def __iter__(self) -> Iterator[Event]:
        while True:
            source = self._pattern
            if source is None:
                return
            iterator = iter(source)
            while True:
                # Re-read the source each event so a swap takes effect at the
                # next event rather than only on the next full iteration.
                if self._pattern is not source:
                    break  # restart from the replacement
                try:
                    yield next(iterator)
                except StopIteration:
                    return


class Pfin(Pattern[T]):
    """Yield at most *count* values from a pattern.

    Args:
        count: Maximum number of values.
        pattern: Source pattern.
    """

    def __init__(self, count: int, pattern: Pattern[T]) -> None:
        self._count = count
        self._pattern = pattern

    def __iter__(self) -> Iterator[T]:
        # islice pulls exactly `count` items from the source. The previous
        # enumerate/return pulled one extra (index == count) before stopping,
        # which matters for a shared or side-effecting source iterator.
        yield from itertools.islice(self._pattern, max(self._count, 0))


class Pfindur(EventPattern):
    """Yield events until their accumulated duration reaches *duration*.

    The final event's ``delta`` is clipped so the total is exact, which is what
    makes a bounded pattern line up with a bar boundary.

    Args:
        duration: Total duration in beats.
        pattern: Source event pattern.
    """

    def __init__(self, duration: float, pattern: Pattern[Event]) -> None:
        self._duration = duration
        self._pattern = pattern

    def __iter__(self) -> Iterator[Event]:
        elapsed = 0.0
        for event in self._pattern:
            remaining = self._duration - elapsed
            if remaining <= 0:
                return
            delta = _event_delta(event)
            if delta >= remaining:
                clipped = dict(event)
                clipped["delta"] = remaining
                yield clipped
                return
            yield event
            elapsed += delta


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------


class Clock:
    """Tempo clock that drives pattern playback.

    Runs a background daemon thread.  Uses ``time.monotonic()`` for
    drift-free absolute scheduling.  Multiple players share one clock
    for synchronized timing.

    Call :meth:`stop` when done: the running thread holds a reference back to
    the clock (and its players), so a clock that is never stopped lives -- with
    its thread -- for the rest of the process. The thread is a daemon, so this
    does not block interpreter exit, but it is a leak within a long-running
    process.

    Args:
        bpm: Beats per minute (default 120).
        latency: Scheduling latency in seconds (default
            :data:`DEFAULT_LATENCY`).  Events are sent as OSC bundles stamped
            this far ahead, so onset accuracy is set by the engine rather than
            by when the Python thread woke.  Raise it if playback stutters
            under load; lower it for tighter response to live input.
    """

    def __init__(self, bpm: float = 120.0, latency: float = DEFAULT_LATENCY) -> None:
        self._bpm = bpm
        self._latency = latency
        # Beat 0 of this clock's grid, in the time.monotonic() domain. All
        # quantization is measured from here, so players started at different
        # moments share one bar line.
        self._origin = time.monotonic()
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
    def latency(self) -> float:
        """Scheduling latency in seconds.  Settable; applies to later events."""
        return self._latency

    @latency.setter
    def latency(self, value: float) -> None:
        self._latency = value

    @property
    def beat_duration(self) -> float:
        """Duration of one beat in seconds (read-only: ``60 / bpm``)."""
        return 60.0 / self._bpm

    @property
    def elapsed_beats(self) -> float:
        """Beats since this clock's grid origin.

        Measured from the origin at the *current* tempo, so changing ``bpm``
        mid-session redefines where past beats fall.  Set the tempo before
        starting quantized players if you need the grid to be stable.
        """
        return (time.monotonic() - self._origin) / self.beat_duration

    def next_boundary(self, quant: float, offset: float = 0.0) -> float:
        """Monotonic time of the next ``quant``-beat boundary.

        With ``quant=4`` this is the downbeat of the next bar in 4/4.  A
        non-positive *quant* means "no quantization" and returns now.

        Args:
            quant: Grid size in beats.
            offset: Beats past the boundary to return.
        """
        now = time.monotonic()
        if quant <= 0:
            return now
        beat_dur = self.beat_duration
        elapsed = (now - self._origin) / beat_dur
        boundary = (math.floor(elapsed / quant) + 1) * quant + offset
        return self._origin + boundary * beat_dur

    def reset_grid(self) -> None:
        """Move the quantization grid origin to now (beat 0 starts here)."""
        self._origin = time.monotonic()

    def _add_player(self, player: Player) -> None:
        with self._lock:
            # Idempotent: calling play() on an already-playing player must not
            # register it twice (which would double every tick and time advance).
            if player not in self._players:
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
                    try:
                        player._tick(now)
                    except Exception:  # noqa: BLE001 -- one bad player must
                        # not take down the clock thread and silence every
                        # other player sharing it.
                        logger.exception("Player tick failed; stopping player")
                        player._stopped = True
                        self._remove_player(player)
                        continue
                if not player._stopped and player._next_time < earliest_next:
                    earliest_next = player._next_time

            sleep_time = max(0.0, earliest_next - time.monotonic())
            self._stop_event.wait(timeout=sleep_time)

    def stop(self) -> None:
        """Stop the clock and all its players.

        Mirrors :meth:`Player.stop` for every player: held Pmono synths are
        gated off, not just marked stopped. Without this a live Pmono voice
        (held with ``gate=1``) would ring until the server quits, since only
        per-event Pbind synths have their gate-release bundles already queued
        in the engine.
        """
        self._stop_event.set()
        with self._lock:
            players = list(self._players)
            for player in players:
                player._stopped = True
            self._players.clear()
        # Release outside the lock: _release_mono sends OSC to the server, and
        # holding the clock lock across engine I/O is unnecessary.
        for player in players:
            player._release_mono()


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------


class Player:
    """Drives event playback from a pattern on a clock.

    Created by ``Pbind.play()`` or directly.

    Args:
        pattern: An event pattern to play.
        clock: The tempo clock.
        server: A Server instance for synth creation.
        latency: Scheduling latency override in seconds.  Defaults to the
            clock's latency, so players sharing a clock stay phase-aligned.
    """

    def __init__(
        self,
        pattern: Pattern[Event],
        clock: Clock,
        server: Any,
        latency: float | None = None,
    ) -> None:
        self._pattern = pattern
        self._clock = clock
        self._server = server
        self._latency = latency
        self._iter: Iterator[Event] | None = None
        self._stopped = True
        self._next_time = 0.0
        # Live Pmono synths, keyed by the stream id their events carry.
        self._mono_synths: dict[str, Any] = {}
        # Guards _mono_synths against the stop()-vs-_tick() race: stop() (user
        # thread) clears it while _tick() (clock thread) may be creating a mono
        # synth, which could otherwise leave a voice held after stop.
        self._mono_lock = threading.Lock()

    @property
    def latency(self) -> float:
        """Effective scheduling latency: this player's override, or the clock's."""
        return self._clock.latency if self._latency is None else self._latency

    def play(self, quant: float | None = None, offset: float = 0.0) -> Player:
        """Start playback.  Returns self for chaining.

        Args:
            quant: Quantization in beats -- start on the next ``quant``-beat
                boundary of the clock's grid rather than immediately.  ``None``
                starts at once.
            offset: Beats past the quantization boundary at which to start.
        """
        self._iter = iter(self._pattern)
        self._mono_synths.clear()
        self._stopped = False
        self._next_time = (
            time.monotonic()
            if quant is None
            else self._clock.next_boundary(quant, offset)
        )
        self._clock._add_player(self)
        return self

    def stop(self) -> None:
        """Stop playback and release any held Pmono synths."""
        self._stopped = True
        self._clock._remove_player(self)
        self._release_mono()

    def _release_mono(self) -> None:
        """Gate off every held Pmono synth, ignoring a dead server."""
        with self._mono_lock:
            if not self._mono_synths:
                return
            synths = list(self._mono_synths.values())
            self._mono_synths.clear()
        try:
            for synth in synths:
                self._server.set(synth, gate=0.0)
        except (EngineError, OSError):
            pass  # Server already gone; the synths died with it.

    def _tick(self, now: float) -> None:
        """Called by the clock thread.  Pull next event and schedule synth."""
        if self._iter is None or self._stopped:
            return

        try:
            event = next(self._iter)
        except StopIteration:
            self._stopped = True
            self._clock._remove_player(self)
            self._release_mono()
            return

        dur_val = event.get("dur", 1.0)
        # Time advance comes from `delta` (which honours `stretch`, and which
        # Ppar rewrites to the gap in the merged stream), falling back to `dur`.
        dur_beats = _event_delta(event)

        beat_dur = self._clock.beat_duration
        # The deadline for *this* event, captured before advancing.
        scheduled = self._next_time
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

        # Onset in the OSC timestamp domain: the event's own deadline plus the
        # latency window, so the engine -- not this thread's wake time --
        # decides the exact sample the synth starts on.
        onset = _monotonic_to_unix(scheduled) + self.latency

        mono_id = event.get("_mono")

        try:
            if isinstance(mono_id, str):
                # Pmono: one persistent synth per stream. Create it on the
                # first event, then retune it in place -- no per-event gate
                # release, so the envelope and any portamento carry across.
                # Hold _mono_lock and re-check _stopped so a concurrent stop()
                # cannot clear the dict between the create and the insert and
                # leave the new voice held (item 14).
                with self._mono_lock:
                    if self._stopped:
                        return
                    held = self._mono_synths.get(mono_id)
                    with self._server.at(onset):
                        if held is None:
                            self._mono_synths[mono_id] = self._server.synth(
                                instrument, **params
                            )
                        elif params:
                            self._server.set(held, **params)
                return

            with self._server.at(onset):
                synth = self._server.synth(instrument, **params)

            # Schedule gate release for gated envelopes. Sent now as a
            # timestamped bundle rather than deferred to a threading.Timer:
            # the engine holds it, so release timing is immune to GIL jitter,
            # no thread is leaked per note, and a release can never fire from
            # Python against an already-quit server.
            sustain_val = event.get("sustain")
            if isinstance(sustain_val, (int, float)):
                sustain_secs = float(sustain_val) * beat_dur
                with self._server.at(onset + sustain_secs):
                    self._server.set(synth, gate=0.0)
        except (EngineError, OSError):
            # Server quit or the connection dropped mid-event; end playback
            # rather than raising on every subsequent tick.
            self._stopped = True
            self._clock._remove_player(self)
            self._mono_synths.clear()
