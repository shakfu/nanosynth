"""Granular synthesis UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, is_multichannel=True)
class GrainBuf(UGen):
    trigger = param(0)
    duration = param(1)
    buffer_id = param()
    rate = param(1)
    position = param(0)
    interpolate = param(2)
    pan = param(0)
    envelope_buffer_id = param(-1)
    maximum_overlap = param(512)


@ugen(ar=True, is_multichannel=True)
class GrainIn(UGen):
    trigger = param(0)
    duration = param(1)
    source = param()
    position = param(0)
    envelope_buffer_id = param(-1)
    maximum_overlap = param(512)


@ugen(ar=True)
class PitchShift(UGen):
    source = param()
    window_size = param(0.2)
    pitch_ratio = param(1.0)
    pitch_dispersion = param(0.0)
    time_dispersion = param(0.0)


@ugen(ar=True, is_multichannel=True)
class Warp1(UGen):
    buffer_id = param(0)
    pointer = param(0)
    frequency_scaling = param(1)
    window_size = param(0.2)
    envelope_buffer_id = param(-1)
    overlaps = param(8)
    window_rand_ratio = param(0)
    interpolation = param(1)
