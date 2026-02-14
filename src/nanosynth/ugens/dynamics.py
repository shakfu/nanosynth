"""Dynamics processing UGens."""

from ..enums import CalculationRate
from ..synthdef import (
    PseudoUGen,
    UGen,
    UGenOperable,
    UGenRecursiveInput,
    param,
    ugen,
)


@ugen(ar=True, kr=True)
class Amplitude(UGen):
    source = param()
    attack_time = param(0.01)
    release_time = param(0.01)


@ugen(ar=True)
class Compander(UGen):
    source = param()
    control = param(0.0)
    threshold = param(0.5)
    slope_below = param(1.0)
    slope_above = param(1.0)
    clamp_time = param(0.01)
    relax_time = param(0.1)


class CompanderD(PseudoUGen):
    """Convenience constructor for Compander with delayed source."""

    @classmethod
    def ar(
        cls,
        *,
        source: UGenRecursiveInput,
        threshold: UGenRecursiveInput = 0.5,
        clamp_time: UGenRecursiveInput = 0.01,
        relax_time: UGenRecursiveInput = 0.1,
        slope_above: UGenRecursiveInput = 1.0,
        slope_below: UGenRecursiveInput = 1.0,
    ) -> UGenOperable:
        from .delay import DelayN

        return Compander._new_expanded(
            calculation_rate=CalculationRate.AUDIO,
            clamp_time=clamp_time,
            control=source,
            relax_time=relax_time,
            slope_above=slope_above,
            slope_below=slope_below,
            source=DelayN.ar(  # type: ignore[attr-defined]
                source=source,
                maximum_delay_time=clamp_time,
                delay_time=clamp_time,
            ),
            threshold=threshold,
        )


@ugen(ar=True)
class Limiter(UGen):
    source = param()
    level = param(1.0)
    duration = param(0.01)


@ugen(ar=True)
class Normalizer(UGen):
    source = param()
    level = param(1.0)
    duration = param(0.01)
