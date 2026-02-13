"""Delay line UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, kr=True, is_pure=True)
class AllpassC(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class AllpassL(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class AllpassN(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufAllpassC(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufAllpassL(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufAllpassN(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufCombC(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufCombL(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufCombN(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BufDelayC(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class BufDelayL(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class BufDelayN(UGen):
    buffer_id = param()
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class CombC(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class CombL(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class CombN(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class DelTapRd(UGen):
    buffer_id = param()
    phase = param()
    delay_time = param(0.0)
    interpolation = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class DelTapWr(UGen):
    buffer_id = param()
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class DelayC(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class DelayL(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class DelayN(UGen):
    source = param()
    maximum_delay_time = param(0.2)
    delay_time = param(0.2)


@ugen(ar=True, kr=True, is_pure=True)
class Delay1(UGen):
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class Delay2(UGen):
    source = param()
