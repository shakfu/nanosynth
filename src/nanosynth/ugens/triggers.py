"""Trigger and signal routing UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, kr=True, ir=True)
class Clip(UGen):
    source = param()
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True, ir=True)
class Fold(UGen):
    source = param()
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True)
class Gate(UGen):
    source = param()
    trigger = param(0)


@ugen(ar=True, kr=True, ir=True)
class InRange(UGen):
    source = param()
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True)
class Latch(UGen):
    source = param()
    trigger = param(0)


@ugen(ar=True, kr=True)
class LeastChange(UGen):
    a = param(0)
    b = param(0)


@ugen(ar=True, kr=True)
class MostChange(UGen):
    a = param(0)
    b = param(0)


@ugen(ar=True, kr=True)
class Peak(UGen):
    source = param()
    trigger = param(0)


@ugen(ar=True, kr=True)
class PeakFollower(UGen):
    source = param()
    decay = param(0.999)


@ugen(ar=True, kr=True)
class Phasor(UGen):
    trigger = param(0)
    rate = param(1.0)
    start = param(0.0)
    stop = param(1.0)
    reset_pos = param(0.0)


@ugen(ar=True, kr=True)
class RunningMax(UGen):
    source = param()
    trigger = param(0)


@ugen(ar=True, kr=True)
class RunningMin(UGen):
    source = param()
    trigger = param(0)


@ugen(ar=True, kr=True)
class Schmidt(UGen):
    source = param()
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True)
class SendTrig(UGen):
    trigger = param()
    id_ = param(0)
    value = param(0.0)


@ugen(ar=True, kr=True)
class Sweep(UGen):
    trigger = param(0)
    rate = param(1.0)


@ugen(ar=True, kr=True)
class TDelay(UGen):
    source = param()
    duration = param(0.1)


@ugen(ar=True, kr=True)
class ToggleFF(UGen):
    trigger = param(0)


@ugen(ar=True, kr=True)
class Trig1(UGen):
    source = param()
    duration = param(0.1)


@ugen(ar=True, kr=True)
class Trig(UGen):
    source = param()
    duration = param(0.1)


@ugen(ar=True, kr=True, ir=True)
class Wrap(UGen):
    source = param()
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True)
class ZeroCrossing(UGen):
    source = param()
