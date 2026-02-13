"""Server info UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ir=True)
class BlockSize(UGen):
    pass


@ugen(kr=True, ir=True)
class BufChannels(UGen):
    buffer_id = param()


@ugen(kr=True, ir=True)
class BufDur(UGen):
    buffer_id = param()


@ugen(kr=True, ir=True)
class BufFrames(UGen):
    buffer_id = param()


@ugen(kr=True, ir=True)
class BufRateScale(UGen):
    buffer_id = param()


@ugen(kr=True, ir=True)
class BufSampleRate(UGen):
    buffer_id = param()


@ugen(kr=True, ir=True)
class BufSamples(UGen):
    buffer_id = param()


@ugen(ir=True)
class ControlDur(UGen):
    pass


@ugen(ir=True)
class ControlRate(UGen):
    pass


@ugen(ir=True)
class NodeID(UGen):
    pass


@ugen(ir=True)
class NumAudioBuses(UGen):
    pass


@ugen(ir=True)
class NumBuffers(UGen):
    pass


@ugen(ir=True)
class NumControlBuses(UGen):
    pass


@ugen(ir=True)
class NumInputBuses(UGen):
    pass


@ugen(ir=True)
class NumOutputBuses(UGen):
    pass


@ugen(kr=True, ir=True)
class NumRunningSynths(UGen):
    pass


@ugen(ir=True)
class RadiansPerSample(UGen):
    pass


@ugen(ir=True)
class SampleDur(UGen):
    pass


@ugen(ir=True)
class SampleRate(UGen):
    pass


@ugen(ir=True)
class SubsampleOffset(UGen):
    pass
