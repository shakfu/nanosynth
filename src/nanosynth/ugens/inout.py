"""Bus input/output UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, kr=True, is_multichannel=True)
class In(UGen):
    bus = param(0.0)


@ugen(ar=True, kr=True, is_multichannel=True)
class InFeedback(UGen):
    bus = param(0.0)


@ugen(ar=True, kr=True, channel_count=0, fixed_channel_count=True)
class LocalOut(UGen):
    source = param(unexpanded=True)


@ugen(ar=True, kr=True, is_output=True, channel_count=0, fixed_channel_count=True)
class OffsetOut(UGen):
    bus = param(0)
    source = param(unexpanded=True)


@ugen(ar=True, kr=True, is_output=True, channel_count=0, fixed_channel_count=True)
class Out(UGen):
    bus = param(0)
    source = param(unexpanded=True)


@ugen(ar=True, kr=True, is_output=True, channel_count=0, fixed_channel_count=True)
class ReplaceOut(UGen):
    bus = param(0)
    source = param(unexpanded=True)


@ugen(ar=True, kr=True, is_output=True, channel_count=0, fixed_channel_count=True)
class XOut(UGen):
    bus = param(0)
    crossfade = param(0.0)
    source = param(unexpanded=True)
