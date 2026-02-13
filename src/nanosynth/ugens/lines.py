"""Line and level UGens."""

from ..synthdef import UGen, param, ugen


@ugen(kr=True, is_pure=True)
class A2K(UGen):
    source = param()


@ugen(ar=True, ir=True, kr=True, is_pure=True)
class AmpComp(UGen):
    frequency = param(1000.0)
    root = param(0.0)
    exp = param(0.3333)


@ugen(ar=True, ir=True, kr=True, is_pure=True)
class AmpCompA(UGen):
    frequency = param(1000.0)
    root = param(0.0)
    min_amp = param(0.32)
    root_amp = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class DC(UGen):
    source = param()


@ugen(ar=True, is_pure=True)
class K2A(UGen):
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class LinExp(UGen):
    source = param()
    input_minimum = param(0)
    input_maximum = param(1)
    output_minimum = param(1)
    output_maximum = param(2)


@ugen(ar=True, kr=True, has_done_flag=True)
class Line(UGen):
    start = param(0.0)
    stop = param(1.0)
    duration = param(1.0)
    done_action = param(0)


@ugen(ar=True, kr=True, has_done_flag=True)
class XLine(UGen):
    start = param(1.0)
    stop = param(2.0)
    duration = param(1.0)
    done_action = param(0)
