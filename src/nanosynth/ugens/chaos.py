"""Chaotic generator UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True)
class CuspL(UGen):
    frequency = param(22050)
    a = param(1.0)
    b = param(1.9)
    xi = param(0.0)


@ugen(ar=True)
class CuspN(UGen):
    frequency = param(22050)
    a = param(1.0)
    b = param(1.9)
    xi = param(0.0)


@ugen(ar=True)
class FBSineC(UGen):
    frequency = param(22050)
    im = param(1.0)
    fb = param(0.1)
    a = param(1.1)
    c = param(0.5)
    xi = param(0.1)
    yi = param(0.1)


@ugen(ar=True)
class FBSineL(UGen):
    frequency = param(22050)
    im = param(1.0)
    fb = param(0.1)
    a = param(1.1)
    c = param(0.5)
    xi = param(0.1)
    yi = param(0.1)


@ugen(ar=True)
class FBSineN(UGen):
    frequency = param(22050)
    im = param(1.0)
    fb = param(0.1)
    a = param(1.1)
    c = param(0.5)
    xi = param(0.1)
    yi = param(0.1)


@ugen(ar=True)
class GbmanL(UGen):
    frequency = param(22050)
    xi = param(1.2)
    yi = param(2.1)


@ugen(ar=True)
class GbmanN(UGen):
    frequency = param(22050)
    xi = param(1.2)
    yi = param(2.1)


@ugen(ar=True)
class HenonC(UGen):
    frequency = param(22050)
    a = param(1.4)
    b = param(0.3)
    x_0 = param(0)
    x_1 = param(0)


@ugen(ar=True)
class HenonL(UGen):
    frequency = param(22050)
    a = param(1.4)
    b = param(0.3)
    x_0 = param(0)
    x_1 = param(0)


@ugen(ar=True)
class HenonN(UGen):
    frequency = param(22050)
    a = param(1.4)
    b = param(0.3)
    x_0 = param(0)
    x_1 = param(0)


@ugen(ar=True)
class LatoocarfianC(UGen):
    frequency = param(22050)
    a = param(1)
    b = param(3)
    c = param(0.5)
    d = param(0.5)
    xi = param(0.5)
    yi = param(0.5)


@ugen(ar=True)
class LatoocarfianL(UGen):
    frequency = param(22050)
    a = param(1)
    b = param(3)
    c = param(0.5)
    d = param(0.5)
    xi = param(0.5)
    yi = param(0.5)


@ugen(ar=True)
class LatoocarfianN(UGen):
    frequency = param(22050)
    a = param(1)
    b = param(3)
    c = param(0.5)
    d = param(0.5)
    xi = param(0.5)
    yi = param(0.5)


@ugen(ar=True)
class LinCongC(UGen):
    frequency = param(22050)
    a = param(1.1)
    c = param(0.13)
    m = param(1)
    xi = param(0)


@ugen(ar=True)
class LinCongL(UGen):
    frequency = param(22050)
    a = param(1.1)
    c = param(0.13)
    m = param(1)
    xi = param(0)


@ugen(ar=True)
class LinCongN(UGen):
    frequency = param(22050)
    a = param(1.1)
    c = param(0.13)
    m = param(1)
    xi = param(0)


@ugen(ar=True)
class LorenzL(UGen):
    frequency = param(22050)
    s = param(10)
    r = param(28)
    b = param(2.667)
    h = param(0.05)
    xi = param(0.1)
    yi = param(0)
    zi = param(0)


@ugen(ar=True)
class QuadC(UGen):
    frequency = param(22050)
    a = param(1)
    b = param(-1)
    c = param(-0.75)
    xi = param(0)


@ugen(ar=True)
class QuadL(UGen):
    frequency = param(22050)
    a = param(1)
    b = param(-1)
    c = param(-0.75)
    xi = param(0)


@ugen(ar=True)
class QuadN(UGen):
    frequency = param(22050)
    a = param(1)
    b = param(-1)
    c = param(-0.75)
    xi = param(0)


@ugen(ar=True)
class StandardL(UGen):
    frequency = param(22050)
    k = param(1)
    xi = param(0.5)
    yi = param(0)


@ugen(ar=True)
class StandardN(UGen):
    frequency = param(22050)
    k = param(1)
    xi = param(0.5)
    yi = param(0)
