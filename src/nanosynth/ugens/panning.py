"""Panning UGens."""

import math
from typing import Any, cast
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


# Four outputs (W, X, Y, Z: first-order 3D B-format), as PanB_next writes.
@ugen(ar=True, kr=True, channel_count=4, fixed_channel_count=True)
class PanB(UGen):
    """First-order 3D B-format panner. Outputs W, X, Y, Z.

    ``azimuth`` is in units of pi (-1 to 1) and ``elevation`` in units of
    pi/2 (-1 to 1), as ``PanB_next`` scales them; neither is in radians.
    """

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


@ugen(ar=True, kr=True)
class LinXFade2(UGen):
    """Linear crossfade. As in sclang, ``level`` scales the output; it is not an input."""

    in_a = param()
    in_b = param(0)
    pan = param(0)

    @classmethod
    def ar(
        cls,
        *,
        in_a: UGenRecursiveInput,
        in_b: UGenRecursiveInput = 0,
        pan: UGenRecursiveInput = 0,
        level: UGenRecursiveInput = 1,
    ) -> UGenOperable:
        signal = cls._new_expanded(
            calculation_rate=CalculationRate.AUDIO, in_a=in_a, in_b=in_b, pan=pan
        )
        return signal * level

    @classmethod
    def kr(
        cls,
        *,
        in_a: UGenRecursiveInput,
        in_b: UGenRecursiveInput = 0,
        pan: UGenRecursiveInput = 0,
        level: UGenRecursiveInput = 1,
    ) -> UGenOperable:
        signal = cls._new_expanded(
            calculation_rate=CalculationRate.CONTROL, in_a=in_a, in_b=in_b, pan=pan
        )
        return signal * level


class SplayAz(PseudoUGen):
    """Spread an array of signals across ``channel_count`` outputs with ``PanAz``."""

    @staticmethod
    def _build(
        rate: CalculationRate,
        channel_count: int,
        source: Sequence[UGenRecursiveInput] | UGenRecursiveInput,
        spread: UGenRecursiveInput,
        level: UGenRecursiveInput,
        width: UGenRecursiveInput,
        center: UGenRecursiveInput,
        orientation: UGenRecursiveInput,
        level_comp: bool | UGenRecursiveInput,
    ) -> UGenOperable:
        from .basic import Mix

        sources = list(source) if isinstance(source, Sequence) else [source]
        n = max(1, len(sources))
        norm_spread = (n - 1) / n * spread  # type: ignore[operator]
        if n == 1:
            position: UGenRecursiveInput = center
        else:
            # sclang [center - s, center + s].resamp1(n)
            lo, hi = center - norm_spread, center + norm_spread  # type: ignore[operator]
            position = [lo + (hi - lo) * (i / (n - 1)) for i in range(n)]
        comp: Any
        if level_comp is True:
            comp = math.sqrt(1 / n) if rate == CalculationRate.AUDIO else 1 / n
        elif level_comp is False:
            comp = 1
        elif isinstance(level_comp, UGenOperable):
            comp = (1 / n) ** level_comp.clip(0.0, 1.0)
        else:  # LevelComp: n.reciprocal ** levelComp.clip(0, 1)
            comp = (1 / n) ** min(max(float(cast(float, level_comp)), 0.0), 1.0)
        method = PanAz.ar if rate == CalculationRate.AUDIO else PanAz.kr  # type: ignore[attr-defined]
        panners = method(
            channel_count=channel_count,
            source=sources,
            position=position,
            amplitude=level * comp,
            width=width,
            orientation=orientation,
        )
        # .flop.collect(Mix(_)): one Mix per output channel, over all sources.
        per_source = [list(p) for p in (panners if n > 1 else [panners])]
        return UGenVector(*(Mix.new(list(ch)) for ch in zip(*per_source)))

    @classmethod
    def ar(
        cls,
        *,
        channel_count: int = 4,
        source: Sequence[UGenRecursiveInput] | UGenRecursiveInput,
        spread: UGenRecursiveInput = 1,
        level: UGenRecursiveInput = 1,
        width: UGenRecursiveInput = 2,
        center: UGenRecursiveInput = 0.0,
        orientation: UGenRecursiveInput = 0.5,
        level_comp: bool | UGenRecursiveInput = True,
    ) -> UGenOperable:
        return cls._build(
            CalculationRate.AUDIO,
            channel_count,
            source,
            spread,
            level,
            width,
            center,
            orientation,
            level_comp,
        )

    @classmethod
    def kr(
        cls,
        *,
        channel_count: int = 4,
        source: Sequence[UGenRecursiveInput] | UGenRecursiveInput,
        spread: UGenRecursiveInput = 1,
        level: UGenRecursiveInput = 1,
        width: UGenRecursiveInput = 2,
        center: UGenRecursiveInput = 0.0,
        orientation: UGenRecursiveInput = 0.5,
        level_comp: bool | UGenRecursiveInput = True,
    ) -> UGenOperable:
        return cls._build(
            CalculationRate.CONTROL,
            channel_count,
            source,
            spread,
            level,
            width,
            center,
            orientation,
            level_comp,
        )
