"""Stochastic synthesis UGens (Gendy family)."""

from typing import Any

from ..enums import CalculationRate
from ..synthdef import (
    Default,
    UGen,
    UGenRecursiveInput,
    param,
    ugen,
)


@ugen(ar=True, kr=True)
class Gendy1(UGen):
    amplitude_distribution = param(1)
    duration_distribution = param(1)
    amplitude_scale = param(0.5)
    duration_scale = param(0.5)
    frequency = param(440.0)
    amplitude_parameter_one = param(0.5)
    amplitude_parameter_two = param(0.5)
    duration_parameter_one = param(0.5)
    duration_parameter_two = param(0.5)
    init_cps = param(12)
    knum = param(Default())

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        if isinstance(kwargs.get("knum"), Default):
            kwargs["knum"] = kwargs.get("init_cps")
        return calculation_rate, kwargs


@ugen(ar=True, kr=True)
class Gendy2(UGen):
    amplitude_distribution = param(1)
    duration_distribution = param(1)
    amplitude_scale = param(0.5)
    duration_scale = param(0.5)
    frequency = param(440.0)
    amplitude_parameter_one = param(0.5)
    amplitude_parameter_two = param(0.5)
    duration_parameter_one = param(0.5)
    duration_parameter_two = param(0.5)
    init_cps = param(12)
    knum = param(Default())
    a = param(1.17)
    c = param(0.31)

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        if isinstance(kwargs.get("knum"), Default):
            kwargs["knum"] = kwargs.get("init_cps")
        return calculation_rate, kwargs


@ugen(ar=True, kr=True)
class Gendy3(UGen):
    amplitude_distribution = param(1)
    duration_distribution = param(1)
    amplitude_scale = param(0.5)
    duration_scale = param(0.5)
    frequency = param(440.0)
    amplitude_parameter_one = param(0.5)
    amplitude_parameter_two = param(0.5)
    duration_parameter_one = param(0.5)
    duration_parameter_two = param(0.5)
    init_cps = param(12)
    knum = param(Default())

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        if isinstance(kwargs.get("knum"), Default):
            kwargs["knum"] = kwargs.get("init_cps")
        return calculation_rate, kwargs
