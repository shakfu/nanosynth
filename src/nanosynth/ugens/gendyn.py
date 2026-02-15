"""Stochastic synthesis UGens (Gendy family).

Iannis Xenakis' Dynamic Stochastic Synthesis. Waveforms are generated
by random walks on breakpoint amplitudes and durations.

Wire orders verified against ``GendynUGens.cpp`` ``ZIN0()`` indices:

- **Gendy1** (10 inputs): whichamp, whichdur, adparam, ddparam,
  minfreq, maxfreq, ampscale, durscale, initCPs, knum
- **Gendy2** (12 inputs): same as Gendy1 + a, c (Lehmer parameters)
- **Gendy3** (9 inputs): whichamp, whichdur, adparam, ddparam,
  freq, ampscale, durscale, initCPs, knum (single freq, no min/max)
"""

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
    """Gendy1 -- ZIN0 order: whichamp(0), whichdur(1), adparam(2),
    ddparam(3), minfreq(4), maxfreq(5), ampscale(6), durscale(7),
    initCPs(8), knum(9)."""

    amplitude_distribution = param(1)
    duration_distribution = param(1)
    amplitude_parameter = param(1.0)
    duration_parameter = param(1.0)
    min_frequency = param(440.0)
    max_frequency = param(660.0)
    amplitude_scale = param(0.5)
    duration_scale = param(0.5)
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
    """Gendy2 -- ZIN0 order: whichamp(0), whichdur(1), adparam(2),
    ddparam(3), minfreq(4), maxfreq(5), ampscale(6), durscale(7),
    initCPs(8), knum(9), a(10), c(11)."""

    amplitude_distribution = param(1)
    duration_distribution = param(1)
    amplitude_parameter = param(1.0)
    duration_parameter = param(1.0)
    min_frequency = param(440.0)
    max_frequency = param(660.0)
    amplitude_scale = param(0.5)
    duration_scale = param(0.5)
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
    """Gendy3 -- ZIN0 order: whichamp(0), whichdur(1), adparam(2),
    ddparam(3), freq(4), ampscale(5), durscale(6), initCPs(7), knum(8).

    Note: Gendy3 has a single frequency (not min/max), and the C++ reads
    initCPs from ZIN0(7) and knum from ZIN0(8).
    """

    amplitude_distribution = param(1)
    duration_distribution = param(1)
    amplitude_parameter = param(1.0)
    duration_parameter = param(1.0)
    frequency = param(440.0)
    amplitude_scale = param(0.5)
    duration_scale = param(0.5)
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
