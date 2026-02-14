"""Panning UGens."""

import math
from collections.abc import Sequence

from ..enums import CalculationRate
from ..synthdef import (
    PseudoUGen,
    UGen,
    UGenOperable,
    UGenRecursiveInput,
    UGenRecursiveParams,
    UGenVector,
    param,
    ugen,
)


@ugen(ar=True, kr=True, channel_count=2, fixed_channel_count=True)
class Balance2(UGen):
    left = param()
    right = param()
    position = param(0.0)
    level = param(1.0)


@ugen(ar=True, kr=True, channel_count=3, fixed_channel_count=True)
class BiPanB2(UGen):
    in_a = param()
    in_b = param()
    azimuth = param()
    gain = param(1.0)


@ugen(ar=True, kr=True, is_multichannel=True, channel_count=4)
class DecodeB2(UGen):
    w = param()
    x = param()
    y = param()
    orientation = param(0.5)


@ugen(ar=True, kr=True, channel_count=2, fixed_channel_count=True)
class Pan2(UGen):
    source = param()
    position = param(0.0)
    level = param(1.0)


@ugen(ar=True, kr=True, channel_count=4, fixed_channel_count=True)
class Pan4(UGen):
    source = param()
    x_position = param(0)
    y_position = param(0)
    gain = param(1)


@ugen(ar=True, kr=True, is_multichannel=True)
class PanAz(UGen):
    source = param()
    position = param(0)
    amplitude = param(1)
    width = param(2)
    orientation = param(0.5)


@ugen(ar=True, kr=True, channel_count=3, fixed_channel_count=True)
class PanB(UGen):
    source = param()
    azimuth = param(0)
    elevation = param(0)
    gain = param(1)


@ugen(ar=True, kr=True, channel_count=3, fixed_channel_count=True)
class PanB2(UGen):
    source = param()
    azimuth = param(0)
    gain = param(1)


@ugen(ar=True, kr=True, channel_count=2, fixed_channel_count=True)
class Rotate2(UGen):
    x = param()
    y = param()
    position = param(0)


class Splay(PseudoUGen):
    """Stereo signal spreader."""

    _ordered_keys = ("spread", "level", "center", "normalize", "source")
    _unexpanded_keys = ("source",)

    @classmethod
    def _new_expanded(
        cls,
        calculation_rate: CalculationRate | None = None,
        **kwargs: UGenRecursiveInput,
    ) -> UGenOperable:
        from .basic import Mix

        def recurse(all_expanded_params: UGenRecursiveParams) -> UGenOperable:
            if (
                not isinstance(all_expanded_params, dict)
                and len(all_expanded_params) == 1
            ):
                all_expanded_params = all_expanded_params[0]
            if isinstance(all_expanded_params, dict):
                return cls._new_single(
                    calculation_rate=calculation_rate,
                    **all_expanded_params,  # type: ignore[arg-type]
                )
            return UGenVector(*(recurse(ep) for ep in all_expanded_params))

        return Mix.multichannel(
            recurse(
                UGen._expand_params(
                    kwargs, unexpanded_keys=frozenset(cls._unexpanded_keys)
                )
            ),
            2,
        )

    @classmethod
    def _new_single(
        cls,
        *,
        calculation_rate: CalculationRate | None = None,
        center: UGenRecursiveInput = 0,
        level: UGenRecursiveInput = 1,
        normalize: bool = True,
        source: Sequence[UGenRecursiveInput] | UGenRecursiveInput,
        spread: UGenRecursiveInput = 1,
        **kwargs: UGenRecursiveInput,
    ) -> UGenOperable:
        from .basic import Mix

        if not isinstance(source, Sequence):
            source = [source]
        n = len(source)
        if n == 1:
            positions: list[UGenRecursiveInput] = [center]
        else:
            positions = [
                (i * (2 / (n - 1)) - 1) * spread + center  # type: ignore[operator]
                for i in range(n)
            ]
        if normalize:
            if calculation_rate == CalculationRate.AUDIO:
                level = level * math.sqrt(1 / n)  # type: ignore[operator]
            else:
                level = level / n  # type: ignore[operator]
        if calculation_rate == CalculationRate.AUDIO:
            panners = Pan2.ar(source=source, position=positions)  # type: ignore[attr-defined]
        else:
            panners = Pan2.kr(source=source, position=positions)  # type: ignore[attr-defined]
        return Mix.multichannel(panners, 2) * level

    @classmethod
    def ar(
        cls,
        *,
        source: UGenRecursiveInput,
        center: UGenRecursiveInput = 0,
        level: UGenRecursiveInput = 1,
        normalize: bool = True,
        spread: UGenRecursiveInput = 1,
    ) -> UGenOperable:
        return cls._new_expanded(
            calculation_rate=CalculationRate.AUDIO,
            center=center,
            level=level,
            normalize=normalize,
            source=source,
            spread=spread,
        )

    @classmethod
    def kr(
        cls,
        *,
        source: UGenRecursiveInput,
        center: UGenRecursiveInput = 0,
        level: UGenRecursiveInput = 1,
        normalize: bool = True,
        spread: UGenRecursiveInput = 1,
    ) -> UGenOperable:
        return cls._new_expanded(
            calculation_rate=CalculationRate.CONTROL,
            center=center,
            level=level,
            normalize=normalize,
            source=source,
            spread=spread,
        )


@ugen(ar=True, kr=True)
class XFade2(UGen):
    in_a = param()
    in_b = param(0)
    pan = param(0)
    level = param(1)
