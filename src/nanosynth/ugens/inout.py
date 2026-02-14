"""Bus input/output UGens."""

import itertools
from collections.abc import Sequence
from typing import Any

from ..enums import CalculationRate
from ..synthdef import UGen, UGenRecursiveInput, param, ugen


@ugen(ar=True, kr=True, is_multichannel=True)
class In(UGen):
    bus = param(0.0)


@ugen(ar=True, kr=True, is_multichannel=True)
class InFeedback(UGen):
    bus = param(0.0)


@ugen(ar=True, kr=True, is_multichannel=True)
class LocalIn(UGen):
    default = param(0.0, unexpanded=True)

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        default = kwargs["default"]
        if not isinstance(default, Sequence):
            default = [default]  # type: ignore[list-item]
        defaults = [float(x) for x in default]  # type: ignore[arg-type]
        # Repeat defaults to fill channel_count
        result: list[float] = []
        cycle = itertools.cycle(defaults)
        for i, x in enumerate(cycle):
            if i >= self._channel_count:
                break
            result.append(x)
        kwargs["default"] = result
        return calculation_rate, kwargs


@ugen(ar=True, kr=True, channel_count=0, fixed_channel_count=True)
class LocalOut(UGen):
    source = param(unexpanded=True)


@ugen(ar=True, kr=True, is_output=True, channel_count=0, fixed_channel_count=True)
class OffsetOut(UGen):
    bus = param(0)
    source = param(unexpanded=True)


@ugen(ar=True, kr=True, is_output=True, channel_count=0, fixed_channel_count=True)
class Out(UGen):
    bus = param(0)
    source = param(unexpanded=True)


@ugen(ar=True, kr=True, is_output=True, channel_count=0, fixed_channel_count=True)
class ReplaceOut(UGen):
    bus = param(0)
    source = param(unexpanded=True)


@ugen(ar=True, kr=True, is_output=True, channel_count=0, fixed_channel_count=True)
class XOut(UGen):
    bus = param(0)
    crossfade = param(0.0)
    source = param(unexpanded=True)
