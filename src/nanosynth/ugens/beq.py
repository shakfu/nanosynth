"""BEQ (BiQuad EQ) filter UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, is_pure=True)
class BAllPass(UGen):
    source = param()
    frequency = param(1200.0)
    reciprocal_of_q = param(1.0)


@ugen(ar=True, is_pure=True)
class BBandPass(UGen):
    source = param()
    frequency = param(1200.0)
    bandwidth = param(1.0)


@ugen(ar=True, is_pure=True)
class BBandStop(UGen):
    source = param()
    frequency = param(1200.0)
    bandwidth = param(1.0)


@ugen(ar=True, is_pure=True)
class BHiCut(UGen):
    source = param()
    frequency = param(1200.0)
    order = param(2.0)
    max_order = param(5.0)


@ugen(ar=True, is_pure=True)
class BHiPass(UGen):
    source = param()
    frequency = param(1200.0)
    reciprocal_of_q = param(1.0)


@ugen(ar=True, is_pure=True)
class BHiShelf(UGen):
    source = param()
    frequency = param(1200.0)
    reciprocal_of_s = param(1.0)
    gain = param(0.0)


@ugen(ar=True, is_pure=True)
class BLowCut(UGen):
    source = param()
    frequency = param(1200.0)
    order = param(2.0)
    max_order = param(5.0)


@ugen(ar=True, is_pure=True)
class BLowPass(UGen):
    source = param()
    frequency = param(1200.0)
    reciprocal_of_q = param(1.0)


@ugen(ar=True, is_pure=True)
class BLowShelf(UGen):
    source = param()
    frequency = param(1200.0)
    reciprocal_of_s = param(1.0)
    gain = param(0.0)


@ugen(ar=True, is_pure=True)
class BPeakEQ(UGen):
    source = param()
    frequency = param(1200.0)
    reciprocal_of_q = param(1.0)
    gain = param(0.0)
