"""Mouse and keyboard input UGens."""

from ..synthdef import UGen, param, ugen


@ugen(kr=True)
class KeyState(UGen):
    keycode = param(0)
    minimum = param(0.0)
    maximum = param(1.0)
    lag = param(0.2)


@ugen(kr=True)
class MouseButton(UGen):
    minimum = param(0.0)
    maximum = param(1.0)
    lag = param(0.2)


@ugen(kr=True)
class MouseX(UGen):
    minimum = param(0.0)
    maximum = param(1.0)
    warp = param(0)
    lag = param(0.2)


@ugen(kr=True)
class MouseY(UGen):
    minimum = param(0.0)
    maximum = param(1.0)
    warp = param(0)
    lag = param(0.2)
