"""Band-limited oscillator UGens."""

import itertools
from collections.abc import Sequence
from typing import Any

from ..enums import CalculationRate
from ..synthdef import (
    PseudoUGen,
    UGen,
    UGenOperable,
    UGenRecursiveInput,
    UGenScalarInput,
    UGenVector,
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
            calculation_rate=CalculationRate.AUDIO,
            decay_scale=decay_scale,
            frequency_offset=frequency_offset,
            frequency_scale=frequency_scale,
            source=source,
            specifications=specs,
        )


class DynKlank(PseudoUGen):
    """A bank of ``Ringz`` resonators whose parameters may be signals, as sclang."""

    @staticmethod
    def _build(
        rate: CalculationRate,
        source: UGenRecursiveInput,
        frequencies: Sequence[UGenRecursiveInput] | None,
        amplitudes: Sequence[UGenRecursiveInput] | None,
        decay_times: Sequence[UGenRecursiveInput] | None,
        frequency_scale: UGenRecursiveInput,
        frequency_offset: UGenRecursiveInput,
        decay_scale: UGenRecursiveInput,
    ) -> UGenOperable:
        from .filters import Ringz

        # sclang's multiNew expands over every argument but the spec: one bank
        # of resonators per channel of a multichannel source or scale.
        expanding = [source, frequency_scale, frequency_offset, decay_scale]
        widths = [len(x) for x in expanding if isinstance(x, (list, tuple, UGenVector))]
        if widths:

            def at(x: Any, i: int) -> Any:
                if isinstance(x, (list, tuple, UGenVector)):
                    return x[i % len(x)]
                return x

            return UGenVector(
                *(
                    DynKlank._build(
                        rate,
                        at(source, i),
                        frequencies,
                        amplitudes,
                        decay_times,
                        at(frequency_scale, i),
                        at(frequency_offset, i),
                        at(decay_scale, i),
                    )
                    for i in range(max(widths))
                )
            )

        def vector(values: Sequence[Any] | None, default: float) -> UGenVector:
            return UGenVector(*(values or [default]))

        freqs = vector(frequencies, 440.0) * frequency_scale + frequency_offset
        decays = vector(decay_times, 1.0) * decay_scale
        amps = vector(amplitudes, 1.0)
        method = Ringz.ar if rate == CalculationRate.AUDIO else Ringz.kr  # type: ignore[attr-defined]
        rings = method(source=source, frequency=freqs, decay_time=decays) * amps
        # sclang Array.sum: a left-to-right chain of +, not Sum3/Sum4.
        total: UGenOperable = rings[0]
        for ring in list(rings)[1:]:
            total = total + ring
        return total

    @classmethod
    def ar(
        cls,
        *,
        source: UGenRecursiveInput,
        frequencies: Sequence[UGenRecursiveInput] | None = None,
        amplitudes: Sequence[UGenRecursiveInput] | None = None,
        decay_times: Sequence[UGenRecursiveInput] | None = None,
        frequency_scale: UGenRecursiveInput = 1.0,
        frequency_offset: UGenRecursiveInput = 0.0,
        decay_scale: UGenRecursiveInput = 1.0,
    ) -> UGenOperable:
        return cls._build(
            CalculationRate.AUDIO,
            source,
            frequencies,
            amplitudes,
            decay_times,
            frequency_scale,
            frequency_offset,
            decay_scale,
        )

    @classmethod
    def kr(
        cls,
        *,
        source: UGenRecursiveInput,
        frequencies: Sequence[UGenRecursiveInput] | None = None,
        amplitudes: Sequence[UGenRecursiveInput] | None = None,
        decay_times: Sequence[UGenRecursiveInput] | None = None,
        frequency_scale: UGenRecursiveInput = 1.0,
        frequency_offset: UGenRecursiveInput = 0.0,
        decay_scale: UGenRecursiveInput = 1.0,
    ) -> UGenOperable:
        return cls._build(
            CalculationRate.CONTROL,
            source,
            frequencies,
            amplitudes,
            decay_times,
            frequency_scale,
            frequency_offset,
            decay_scale,
        )


@ugen(ar=True, kr=True, is_pure=True)
class Saw(UGen):
    frequency = param(440.0)
