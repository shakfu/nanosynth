"""Panning UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, kr=True, channel_count=2, fixed_channel_count=True)
class Balance2(UGen):
    left = param()
    right = param()
    position = param(0.0)
    level = param(1.0)


@ugen(ar=True, kr=True, channel_count=3, fixed_channel_count=True)
class BiPanB2(UGen):
    in_a = param()
    in_b = param()
    azimuth = param()
    gain = param(1.0)


@ugen(ar=True, kr=True, is_multichannel=True, channel_count=4)
class DecodeB2(UGen):
    w = param()
    x = param()
    y = param()
    orientation = param(0.5)


@ugen(ar=True, kr=True, channel_count=2, fixed_channel_count=True)
class Pan2(UGen):
    source = param()
    position = param(0.0)
    level = param(1.0)


@ugen(ar=True, kr=True, channel_count=4, fixed_channel_count=True)
class Pan4(UGen):
    source = param()
    x_position = param(0)
    y_position = param(0)
    gain = param(1)


@ugen(ar=True, kr=True, is_multichannel=True)
class PanAz(UGen):
    source = param()
    position = param(0)
    amplitude = param(1)
    width = param(2)
    orientation = param(0.5)


@ugen(ar=True, kr=True, channel_count=3, fixed_channel_count=True)
class PanB(UGen):
    source = param()
    azimuth = param(0)
    elevation = param(0)
    gain = param(1)


@ugen(ar=True, kr=True, channel_count=3, fixed_channel_count=True)
class PanB2(UGen):
    source = param()
    azimuth = param(0)
    gain = param(1)


@ugen(ar=True, kr=True, channel_count=2, fixed_channel_count=True)
class Rotate2(UGen):
    x = param()
    y = param()
    position = param(0)


@ugen(ar=True, kr=True)
class XFade2(UGen):
    in_a = param()
    in_b = param(0)
    pan = param(0)
    level = param(1)
