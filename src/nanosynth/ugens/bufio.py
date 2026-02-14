"""Buffer I/O UGens."""

from typing import Any

from ..enums import CalculationRate
from ..synthdef import (
    Default,
    UGen,
    UGenRecursiveInput,
    param,
    ugen,
)


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


@ugen(ir=True, is_width_first=True)
class LocalBuf(UGen):
    channel_count = param(1)
    frame_count = param(1)

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        return CalculationRate.SCALAR, kwargs


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


@ugen(ar=True, kr=True)
class ScopeOut2(UGen):
    scope_id = param()
    max_frames = param(4096)
    scope_frames = param(Default())
    source = param(unexpanded=True)

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        if isinstance(kwargs["scope_frames"], Default):
            kwargs["scope_frames"] = kwargs["max_frames"]
        return calculation_rate, kwargs
