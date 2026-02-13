"""Buffer I/O UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, kr=True, is_multichannel=True)
class BufRd(UGen):
    buffer_id = param()
    phase = param(0.0)
    loop = param(1)
    interpolation = param(2)


@ugen(ar=True, kr=True, has_done_flag=True)
class BufWr(UGen):
    buffer_id = param()
    phase = param(0.0)
    loop = param(1.0)
    source = param(unexpanded=True)


@ugen(ir=True, is_width_first=True)
class ClearBuf(UGen):
    buffer_id = param()


@ugen(ir=True)
class MaxLocalBufs(UGen):
    maximum = param(0)


@ugen(ar=True, kr=True, is_multichannel=True)
class PlayBuf(UGen):
    buffer_id = param()
    rate = param(1)
    trigger = param(1)
    start_position = param(0)
    loop = param(0)
    done_action = param(0)


@ugen(ar=True, kr=True, has_done_flag=True)
class RecordBuf(UGen):
    buffer_id = param()
    offset = param(0.0)
    record_level = param(1.0)
    preexisting_level = param(0.0)
    run = param(1.0)
    loop = param(1.0)
    trigger = param(1.0)
    done_action = param(0)
    source = param(unexpanded=True)


@ugen(ar=True, kr=True)
class ScopeOut(UGen):
    buffer_id = param()
    source = param(unexpanded=True)
