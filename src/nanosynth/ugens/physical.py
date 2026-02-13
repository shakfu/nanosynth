"""Physical modeling UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, kr=True)
class Ball(UGen):
    source = param()
    gravity = param(1.0)
    damping = param(0.0)
    friction = param(0.01)


@ugen(ar=True)
class Pluck(UGen):
    source = param()
    trigger = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1)
    coefficient = param(0.5)


@ugen(ar=True, kr=True)
class Spring(UGen):
    source = param()
    spring = param(1.0)
    damping = param(0.0)


@ugen(ar=True, kr=True)
class TBall(UGen):
    source = param()
    gravity = param(10.0)
    damping = param(0.0)
    friction = param(0.01)
