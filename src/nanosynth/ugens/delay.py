"""Delay line UGens."""

from typing import Any

from ..enums import CalculationRate
from ..synthdef import Default, UGen, UGenRecursiveInput, param, ugen


def _initial_state(
    calculation_rate: CalculationRate, kwargs: dict[str, Any], *names: str
) -> dict[str, Any]:
    """Resolve Default() delay state like sclang: 0 at audio rate, else the input."""
    for name in names:
        if isinstance(kwargs.get(name), Default):
            audio = calculation_rate == CalculationRate.AUDIO
            kwargs[name] = 0.0 if audio else kwargs.get("source")
    return kwargs


@ugen(ar=True, kr=True, is_pure=True)
class AllpassC(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class AllpassL(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class AllpassN(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufAllpassC(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufAllpassL(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufAllpassN(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufCombC(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufCombL(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufCombN(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufDelayC(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class BufDelayL(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class BufDelayN(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class CombC(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class CombL(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class CombN(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class DelTapRd(UGen):
    buffer_id = param()
    phase = param()
    delay_time = param(0.0)
    interpolation = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class DelTapWr(UGen):
    buffer_id = param()
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class DelayC(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class DelayL(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class DelayN(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class Delay1(UGen):
    """One-sample delay. ``x1`` is the initial previous sample."""

    source = param()
    x1 = param(Default())

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        return calculation_rate, _initial_state(calculation_rate, kwargs, "x1")


@ugen(ar=True, kr=True, is_pure=True)
class Delay2(UGen):
    """Two-sample delay. ``x1``/``x2`` are the initial previous samples."""

    source = param()
    x1 = param(Default())
    x2 = param(Default())

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        return calculation_rate, _initial_state(calculation_rate, kwargs, "x1", "x2")
