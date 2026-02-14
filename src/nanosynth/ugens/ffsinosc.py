"""Band-limited oscillator UGens."""

import itertools
from collections.abc import Sequence
from typing import Any

from ..synthdef import (
    UGen,
    UGenOperable,
    UGenRecursiveInput,
    UGenScalarInput,
    param,
    ugen,
)


@ugen(ar=True, kr=True)
class Blip(UGen):
    frequency = param(440.0)
    harmonic_count = param(200.0)


@ugen(ar=True, kr=True)
class FSinOsc(UGen):
    frequency = param(440.0)
    initial_phase = param(0.0)


@ugen(ar=True, kr=True)
class Pulse(UGen):
    frequency = param(440.0)
    width = param(0.5)


@ugen(ar=True)
class Klank(UGen):
    source = param()
    frequency_scale = param(1)
    frequency_offset = param(0)
    decay_scale = param(1)
    specifications = param(unexpanded=True)

    @classmethod
    def ar(
        cls,
        *,
        source: UGenRecursiveInput,
        frequencies: Sequence[UGenScalarInput],
        amplitudes: Sequence[UGenScalarInput] | None = None,
        decay_times: Sequence[UGenScalarInput] | None = None,
        frequency_scale: UGenRecursiveInput = 1,
        frequency_offset: UGenRecursiveInput = 0,
        decay_scale: UGenRecursiveInput = 1,
    ) -> UGenOperable:
        if not frequencies:
            raise ValueError(frequencies)
        if not amplitudes:
            amplitudes = [1.0] * len(frequencies)
        if not decay_times:
            decay_times = [1.0] * len(frequencies)
        max_len = max(len(frequencies), len(amplitudes), len(decay_times))
        cycles = [itertools.cycle(s) for s in (frequencies, amplitudes, decay_times)]
        specs: list[Any] = []
        for i, (f, a, d) in enumerate(zip(*cycles)):
            specs.extend([f, a, d])
            if i >= max_len - 1:
                break
        return cls._new_expanded(
            calculation_rate=None,
            decay_scale=decay_scale,
            frequency_offset=frequency_offset,
            frequency_scale=frequency_scale,
            source=source,
            specifications=specs,
        )


@ugen(ar=True, kr=True, is_pure=True)
class Saw(UGen):
    frequency = param(440.0)
