"""Dynamics processing UGens."""

from ..synthdef import UGen, param, ugen


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
