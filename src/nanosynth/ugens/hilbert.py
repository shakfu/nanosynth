"""Hilbert transform and frequency shifting UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True)
class FreqShift(UGen):
    source = param()
    frequency = param(0.0)
    phase = param(0.0)


@ugen(ar=True, channel_count=2, fixed_channel_count=True)
class Hilbert(UGen):
    source = param()


@ugen(ar=True)
class HilbertFIR(UGen):
    source = param()
    buffer_id = param()
