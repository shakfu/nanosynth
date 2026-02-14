"""Line and level UGens."""

from ..synthdef import (
    PseudoUGen,
    UGen,
    UGenOperable,
    UGenRecursiveInput,
    UGenVector,
    param,
    ugen,
)


@ugen(kr=True, is_pure=True)
class A2K(UGen):
    source = param()


@ugen(ar=True, ir=True, kr=True, is_pure=True)
class AmpComp(UGen):
    frequency = param(1000.0)
    root = param(0.0)
    exp = param(0.3333)


@ugen(ar=True, ir=True, kr=True, is_pure=True)
class AmpCompA(UGen):
    frequency = param(1000.0)
    root = param(0.0)
    min_amp = param(0.32)
    root_amp = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class DC(UGen):
    source = param()


@ugen(ar=True, is_pure=True)
class K2A(UGen):
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class LinExp(UGen):
    source = param()
    input_minimum = param(0)
    input_maximum = param(1)
    output_minimum = param(1)
    output_maximum = param(2)


class LinLin(PseudoUGen):
    """Linear-to-linear mapping pseudo-UGen."""

    @staticmethod
    def ar(
        *,
        source: UGenRecursiveInput,
        input_minimum: UGenRecursiveInput = 0.0,
        input_maximum: UGenRecursiveInput = 1.0,
        output_minimum: UGenRecursiveInput = 1.0,
        output_maximum: UGenRecursiveInput = 2.0,
    ) -> UGenOperable:
        from .basic import MulAdd

        scale = (output_maximum - output_minimum) / (input_maximum - input_minimum)  # type: ignore[operator]
        offset = output_minimum - (scale * input_minimum)
        return MulAdd.new(source=source, multiplier=scale, addend=offset)  # type: ignore[attr-defined,no-any-return]

    @staticmethod
    def kr(
        *,
        source: UGenRecursiveInput,
        input_minimum: UGenRecursiveInput = 0.0,
        input_maximum: UGenRecursiveInput = 1.0,
        output_minimum: UGenRecursiveInput = 1.0,
        output_maximum: UGenRecursiveInput = 2.0,
    ) -> UGenOperable:
        from .basic import MulAdd

        scale = (output_maximum - output_minimum) / (input_maximum - input_minimum)  # type: ignore[operator]
        offset = output_minimum - (scale * input_minimum)
        return MulAdd.new(source=source, multiplier=scale, addend=offset)  # type: ignore[attr-defined,no-any-return]


@ugen(ar=True, kr=True, has_done_flag=True)
class Line(UGen):
    start = param(0.0)
    stop = param(1.0)
    duration = param(1.0)
    done_action = param(0)


class Silence(PseudoUGen):
    """Audio-rate silence pseudo-UGen."""

    @classmethod
    def ar(cls, channel_count: int = 1) -> UGenOperable:
        silence = DC.ar(source=0)  # type: ignore[attr-defined]
        if channel_count == 1:
            return silence  # type: ignore[no-any-return]
        return UGenVector(*([silence] * channel_count))


@ugen(ar=True, kr=True, has_done_flag=True)
class XLine(UGen):
    start = param(1.0)
    stop = param(2.0)
    duration = param(1.0)
    done_action = param(0)
