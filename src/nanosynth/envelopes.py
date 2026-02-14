"""
Envelope class and EnvGen UGen for nanosynth.

Ported from supriya's ugens/envelopes.py.
"""

import itertools
from collections.abc import Iterator, Sequence
from typing import Any, SupportsFloat, cast

from .enums import CalculationRate, EnvelopeShape
from .synthdef import (
    OutputProxy,
    UGen,
    UGenOperable,
    UGenRecursiveInput,
    UGenSerializable,
    UGenVector,
)


# ---------------------------------------------------------------------------
# Utility helpers (inlined from supriya.utils)
# ---------------------------------------------------------------------------


def _zip_cycled(
    *args: Sequence[Any],
) -> Iterator[tuple[Any, ...]]:
    maximum_i = max(len(a) for a in args) - 1
    cycles = [itertools.cycle(a) for a in args]
    for i, result in enumerate(zip(*cycles)):
        yield result
        if i == maximum_i:
            break


def _expand_deep(item: list[Any]) -> list[list[Any]]:
    size = 1
    for x in item:
        if isinstance(x, Sequence) and not isinstance(x, str):
            size = max(len(x), size)
    should_recurse = False
    sequences: list[list[Any]] = [[] for _ in range(size)]
    for x in item:
        for i in range(size):
            if isinstance(x, Sequence) and not isinstance(x, str):
                v = x[i % len(x)]
                if isinstance(v, Sequence) and not isinstance(v, str):
                    if len(v) > 1:
                        should_recurse = True
                    else:
                        v = v[0]
            else:
                v = x
            sequences[i].append(v)
    if should_recurse:
        for j in reversed(range(size)):
            sequences[j : j + 1] = _expand_deep(sequences[j])
    return sequences


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


class Envelope(UGenSerializable):
    """An envelope specification for use with EnvGen."""

    def __init__(
        self,
        amplitudes: Sequence[UGenOperable | float] = (0, 1, 0),
        durations: Sequence[UGenOperable | float] = (1, 1),
        curves: Sequence[EnvelopeShape | UGenOperable | float | str | None] = (
            EnvelopeShape.LINEAR,
            EnvelopeShape.LINEAR,
        ),
        release_node: int | None = None,
        loop_node: int | None = None,
        offset: UGenOperable | float = 0.0,
    ) -> None:
        if len(amplitudes) <= 1:
            raise ValueError(
                f"amplitudes must have at least 2 values, got {len(amplitudes)}"
            )
        if not (len(durations) == (len(amplitudes) - 1)):
            raise ValueError(
                f"durations length ({len(durations)}) must equal amplitudes length - 1 ({len(amplitudes) - 1})"
            )
        if isinstance(curves, (int, float, str, EnvelopeShape, UGenOperable)):
            curves = [curves]
        elif curves is None:
            curves = []
        self._release_node = release_node
        self._loop_node = loop_node
        self._offset = offset
        self._initial_amplitude: UGenOperable | float = self._flatten(
            float(amplitudes[0])
            if not isinstance(amplitudes[0], UGenOperable)
            else amplitudes[0]
        )
        self._amplitudes: tuple[UGenOperable | float, ...] = tuple(
            self._flatten(
                float(amplitude)
                if not isinstance(amplitude, UGenOperable)
                else amplitude
            )
            for amplitude in amplitudes[1:]
        )
        self._durations: tuple[UGenOperable | float, ...] = tuple(
            self._flatten(
                float(duration) if not isinstance(duration, UGenOperable) else duration
            )
            for duration in durations
        )
        curves_: list[EnvelopeShape | UGenOperable | float] = []
        for x in curves:
            if isinstance(x, (EnvelopeShape, UGenOperable)):
                curves_.append(self._flatten(x))
            elif isinstance(x, str) or x is None:
                curves_.append(EnvelopeShape.from_expr(x))
            else:
                curves_.append(float(x))
        self._curves: tuple[EnvelopeShape | UGenOperable | float, ...] = tuple(curves_)
        self._envelope_segments = tuple(
            _zip_cycled(self._amplitudes, self._durations, self._curves)
        )

    @staticmethod
    def _flatten(item: UGenOperable | float) -> UGenOperable | float:
        if isinstance(item, (float, int)):
            return item
        elif isinstance(item, OutputProxy):
            return item
        elif isinstance(item, UGen) and len(item) == 1:
            return item[0]
        return item

    @classmethod
    def adsr(
        cls,
        attack_time: float = 0.01,
        decay_time: float = 0.3,
        sustain: float = 0.5,
        release_time: float = 1.0,
        peak: float = 1.0,
        curve: float = -4.0,
        bias: float = 0.0,
    ) -> "Envelope":
        amplitudes = [x + bias for x in [0, peak, peak * sustain, 0]]
        durations = [attack_time, decay_time, release_time]
        curves = [curve]
        release_node = 2
        return Envelope(
            amplitudes=amplitudes,
            durations=durations,
            curves=curves,
            release_node=release_node,
        )

    @classmethod
    def asr(
        cls,
        attack_time: float = 0.01,
        sustain: float = 1.0,
        release_time: float = 1.0,
        curve: float = -4.0,
    ) -> "Envelope":
        amplitudes = [0, sustain, 0]
        durations = [attack_time, release_time]
        curves = [curve]
        release_node = 1
        return Envelope(
            amplitudes=amplitudes,
            durations=durations,
            curves=curves,
            release_node=release_node,
        )

    @classmethod
    def linen(
        cls,
        attack_time: float = 0.01,
        sustain_time: float = 1.0,
        release_time: float = 1.0,
        level: float = 1.0,
        curve: float | int = 1,
    ) -> "Envelope":
        amplitudes = [0, level, level, 0]
        durations = [attack_time, sustain_time, release_time]
        curves: list[float | int] = [curve]
        return Envelope(amplitudes=amplitudes, durations=durations, curves=curves)

    @classmethod
    def percussive(
        cls,
        attack_time: UGenOperable | float = 0.01,
        release_time: UGenOperable | float = 1.0,
        amplitude: UGenOperable | float = 1.0,
        curve: EnvelopeShape | UGenOperable | float | str = -4.0,
    ) -> "Envelope":
        amplitudes = [0, amplitude, 0]
        durations = [attack_time, release_time]
        curves = [curve]
        return Envelope(amplitudes=amplitudes, durations=durations, curves=curves)

    @classmethod
    def triangle(
        cls,
        duration: float = 1.0,
        amplitude: float = 1.0,
    ) -> "Envelope":
        amplitudes = [0, amplitude, 0]
        duration = duration / 2.0
        durations = [duration, duration]
        return Envelope(amplitudes=amplitudes, durations=durations)

    def serialize(self, **kwargs: Any) -> UGenVector:
        result: list[UGenOperable | float] = []
        result.append(self.initial_amplitude)
        result.append(len(self.envelope_segments))
        result.append(-99 if self.release_node is None else self.release_node)
        result.append(-99 if self.loop_node is None else self.loop_node)
        for amplitude, duration, curve in self._envelope_segments:
            result.append(amplitude)
            result.append(duration)
            if isinstance(curve, EnvelopeShape):
                shape = int(curve)
                curve = 0.0
            else:
                shape = int(EnvelopeShape.CUSTOM)
            result.append(shape)
            result.append(curve)
        expanded = [
            UGenVector(*cast(Sequence[SupportsFloat | UGenOperable], x))
            for x in _expand_deep(result)
        ]
        if len(expanded) == 1:
            return expanded[0]
        return UGenVector(*expanded)

    @property
    def amplitudes(self) -> tuple[UGenOperable | float, ...]:
        return (self.initial_amplitude,) + tuple(s[0] for s in self.envelope_segments)

    @property
    def curves(self) -> tuple[EnvelopeShape | UGenOperable | float, ...]:
        return tuple(s[2] for s in self.envelope_segments)

    @property
    def duration(self) -> UGenOperable | float:
        return sum(self.durations)

    @property
    def durations(self) -> tuple[UGenOperable | float, ...]:
        return tuple(s[1] for s in self.envelope_segments)

    @property
    def envelope_segments(
        self,
    ) -> tuple[tuple[Any, ...], ...]:
        return self._envelope_segments

    @property
    def initial_amplitude(self) -> UGenOperable | float:
        return self._initial_amplitude

    @property
    def loop_node(self) -> int | None:
        return self._loop_node

    @property
    def offset(self) -> UGenOperable | float:
        return self._offset

    @property
    def release_node(self) -> int | None:
        return self._release_node


# ---------------------------------------------------------------------------
# EnvGen UGen
# ---------------------------------------------------------------------------


class EnvGen(UGen):
    _ordered_keys = (
        "gate",
        "level_scale",
        "level_bias",
        "time_scale",
        "done_action",
        "envelope",
    )
    _unexpanded_keys = frozenset(["envelope"])
    _has_done_flag = True

    def __init__(
        self,
        *,
        calculation_rate: CalculationRate,
        gate: UGenRecursiveInput = 1.0,
        level_scale: UGenRecursiveInput = 1.0,
        level_bias: UGenRecursiveInput = 0.0,
        time_scale: UGenRecursiveInput = 1.0,
        done_action: UGenRecursiveInput = 0.0,
        envelope: UGenRecursiveInput | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            calculation_rate=calculation_rate,
            gate=gate,
            level_scale=level_scale,
            level_bias=level_bias,
            time_scale=time_scale,
            done_action=done_action,
            envelope=envelope,
            **kwargs,
        )

    @classmethod
    def _new_expanded(  # type: ignore[override]
        cls,
        *,
        calculation_rate: CalculationRate | None = None,
        done_action: UGenRecursiveInput | None = None,
        envelope: UGenRecursiveInput | None = None,
        gate: UGenRecursiveInput = 1.0,
        level_bias: UGenRecursiveInput = 0.0,
        level_scale: UGenRecursiveInput = 1.0,
        time_scale: UGenRecursiveInput = 1.0,
    ) -> UGenOperable:
        return super()._new_expanded(
            calculation_rate=calculation_rate,
            done_action=done_action,
            envelope=envelope,
            gate=gate,
            level_bias=level_bias,
            level_scale=level_scale,
            time_scale=time_scale,
        )

    @classmethod
    def ar(
        cls,
        *,
        gate: UGenRecursiveInput = 1.0,
        level_scale: UGenRecursiveInput = 1.0,
        level_bias: UGenRecursiveInput = 0.0,
        time_scale: UGenRecursiveInput = 1.0,
        done_action: UGenRecursiveInput = 0,
        envelope: UGenRecursiveInput | None = None,
    ) -> UGenOperable:
        return cls._new_expanded(
            calculation_rate=CalculationRate.AUDIO,
            gate=gate,
            level_scale=level_scale,
            level_bias=level_bias,
            time_scale=time_scale,
            done_action=done_action,
            envelope=envelope,
        )

    @classmethod
    def kr(
        cls,
        *,
        gate: UGenRecursiveInput = 1.0,
        level_scale: UGenRecursiveInput = 1.0,
        level_bias: UGenRecursiveInput = 0.0,
        time_scale: UGenRecursiveInput = 1.0,
        done_action: UGenRecursiveInput = 0,
        envelope: UGenRecursiveInput | None = None,
    ) -> UGenOperable:
        return cls._new_expanded(
            calculation_rate=CalculationRate.CONTROL,
            gate=gate,
            level_scale=level_scale,
            level_bias=level_bias,
            time_scale=time_scale,
            done_action=done_action,
            envelope=envelope,
        )
