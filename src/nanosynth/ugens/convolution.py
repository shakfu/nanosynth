"""Convolution UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True)
class Convolution(UGen):
    source = param()
    kernel = param()
    framesize = param(512)


@ugen(ar=True)
class Convolution2(UGen):
    source = param()
    kernel = param()
    trigger = param(0.0)
    framesize = param(2048)


@ugen(ar=True)
class Convolution2L(UGen):
    source = param()
    kernel = param()
    trigger = param(0.0)
    framesize = param(2048)
    crossfade = param(1.0)


@ugen(ar=True)
class Convolution3(UGen):
    source = param()
    kernel = param()
    trigger = param(0.0)
    framesize = param(2048)
