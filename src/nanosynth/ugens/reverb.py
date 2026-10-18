"""Reverb UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True)
class FreeVerb(UGen):
    source = param()
    mix = param(0.33)
    room_size = param(0.5)
    damping = param(0.5)


@ugen(ar=True, channel_count=2, fixed_channel_count=True)
class GVerb(UGen):
    source = param()
    room_size = param(10.0)
    reverb_time = param(3.0)
    damping = param(0.5)
    input_bandwidth = param(0.5)
    spread = param(15.0)
    dry_level = param(1.0)
    early_reflection_level = param(0.7)
    tail_level = param(0.5)
    maximum_room_size = param(300.0)
