"""Band-limited oscillator UGens."""

from ..synthdef import UGen, param, ugen


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


@ugen(ar=True, kr=True, is_pure=True)
class Saw(UGen):
    frequency = param(440.0)
