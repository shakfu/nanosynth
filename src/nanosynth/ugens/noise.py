"""Noise and random UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, kr=True)
class BrownNoise(UGen):
    pass


@ugen(ar=True, kr=True)
class ClipNoise(UGen):
    pass


@ugen(ar=True, kr=True)
class CoinGate(UGen):
    probability = param(0.5)
    trigger = param()


@ugen(ar=True, kr=True)
class Crackle(UGen):
    chaos_parameter = param(1.5)


@ugen(ar=True, kr=True)
class Dust(UGen):
    density = param(0.0)


@ugen(ar=True, kr=True)
class Dust2(UGen):
    density = param(0.0)


@ugen(ir=True)
class ExpRand(UGen):
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True)
class GrayNoise(UGen):
    pass


@ugen(ar=True, kr=True)
class Hasher(UGen):
    source = param()


@ugen(ir=True)
class IRand(UGen):
    minimum = param(0)
    maximum = param(127)


@ugen(ar=True, kr=True)
class LFClipNoise(UGen):
    frequency = param(500.0)


@ugen(ar=True, kr=True)
class LFDClipNoise(UGen):
    frequency = param(500.0)


@ugen(ar=True, kr=True)
class LFDNoise0(UGen):
    frequency = param(500.0)


@ugen(ar=True, kr=True)
class LFDNoise1(UGen):
    frequency = param(500.0)


@ugen(ar=True, kr=True)
class LFDNoise3(UGen):
    frequency = param(500.0)


@ugen(ar=True, kr=True)
class LFNoise0(UGen):
    frequency = param(500.0)


@ugen(ar=True, kr=True)
class LFNoise1(UGen):
    frequency = param(500.0)


@ugen(ar=True, kr=True)
class LFNoise2(UGen):
    frequency = param(500.0)


@ugen(ir=True)
class LinRand(UGen):
    minimum = param(0.0)
    maximum = param(1.0)
    skew = param(0)


@ugen(ar=True, kr=True)
class Logistic(UGen):
    chaos_parameter = param(3)
    frequency = param(1000)
    initial_y = param(0.5)


@ugen(ar=True, kr=True)
class MantissaMask(UGen):
    source = param(0)
    bits = param(3)


@ugen(ir=True)
class NRand(UGen):
    minimum = param(0.0)
    maximum = param(1.0)
    n = param(1)


@ugen(ar=True, kr=True)
class PinkNoise(UGen):
    pass


@ugen(ir=True)
class Rand(UGen):
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(kr=True, ir=True, is_width_first=True)
class RandID(UGen):
    rand_id = param(1)


@ugen(ar=True, kr=True, ir=True, is_width_first=True)
class RandSeed(UGen):
    trigger = param(0)
    seed = param(56789)


@ugen(ar=True, kr=True)
class TExpRand(UGen):
    minimum = param(0.01)
    maximum = param(1.0)
    trigger = param(0)


@ugen(ar=True, kr=True)
class TIRand(UGen):
    minimum = param(0)
    maximum = param(127)
    trigger = param(0)


@ugen(ar=True, kr=True)
class TRand(UGen):
    minimum = param(0.0)
    maximum = param(1.0)
    trigger = param(0)


@ugen(ar=True, kr=True)
class TWindex(UGen):
    trigger = param()
    normalize = param(0)
    array = param(unexpanded=True)


@ugen(ar=True, kr=True)
class WhiteNoise(UGen):
    pass
