"""Reverb UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True)
class FreeVerb(UGen):
    source = param()
    mix = param(0.33)
    room_size = param(0.5)
    damping = param(0.5)
