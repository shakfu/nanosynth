"""Trigger and signal routing UGens."""

from ..enums import CalculationRate
from ..synthdef import (
    OutputProxy,
    UGen,
    UGenOperable,
    UGenRecursiveInput,
    UGenScalarInput,
    param,
    ugen,
)


@ugen(ar=True, kr=True, ir=True)
class Clip(UGen):
    source = param()
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True, ir=True)
class Fold(UGen):
    source = param()
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True)
class Gate(UGen):
    source = param()
    trigger = param(0)


@ugen(ar=True, kr=True, ir=True)
class InRange(UGen):
    source = param()
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True)
class Latch(UGen):
    source = param()
    trigger = param(0)


@ugen(ar=True, kr=True)
class LeastChange(UGen):
    a = param(0)
    b = param(0)


@ugen(ar=True, kr=True)
class MostChange(UGen):
    a = param(0)
    b = param(0)


@ugen(ar=True, kr=True)
class Peak(UGen):
    source = param()
    trigger = param(0)


@ugen(ar=True, kr=True)
class PeakFollower(UGen):
    source = param()
    decay = param(0.999)


@ugen(ar=True, kr=True)
class Phasor(UGen):
    trigger = param(0)
    rate = param(1.0)
    start = param(0.0)
    stop = param(1.0)
    reset_pos = param(0.0)


@ugen(ar=True, kr=True)
class RunningMax(UGen):
    source = param()
    trigger = param(0)


@ugen(ar=True, kr=True)
class RunningMin(UGen):
    source = param()
    trigger = param(0)


@ugen(ar=True, kr=True)
class Schmidt(UGen):
    source = param()
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True)
class SendTrig(UGen):
    trigger = param()
    id_ = param(0)
    value = param(0.0)


@ugen(ar=True, kr=True)
class Sweep(UGen):
    trigger = param(0)
    rate = param(1.0)


@ugen(ar=True, kr=True)
class TDelay(UGen):
    source = param()
    duration = param(0.1)


@ugen(ar=True, kr=True)
class ToggleFF(UGen):
    trigger = param(0)


@ugen(ar=True, kr=True)
class Trig1(UGen):
    source = param()
    duration = param(0.1)


@ugen(ar=True, kr=True)
class Trig(UGen):
    source = param()
    duration = param(0.1)


@ugen(ar=True, kr=True, ir=True)
class Wrap(UGen):
    source = param()
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(ar=True, kr=True)
class ZeroCrossing(UGen):
    source = param()


@ugen(ar=True, kr=True)
class Poll(UGen):
    trigger = param()
    source = param()
    trigger_id = param(-1)
    label = param(unexpanded=True)

    def __init__(
        self,
        *,
        calculation_rate: CalculationRate = CalculationRate.SCALAR,
        label: UGenRecursiveInput | None = None,
        source: UGenScalarInput | None = None,
        trigger: UGenScalarInput | None = None,
        trigger_id: UGenScalarInput = -1,
        **kwargs: UGenRecursiveInput | None,
    ) -> None:
        if label is None:
            if isinstance(source, UGen):
                label_str = type(source).__name__
            elif isinstance(source, OutputProxy):
                label_str = type(source.ugen).__name__
            else:
                label_str = "UGen"
        else:
            label_str = str(label)
        UGen.__init__(
            self,
            calculation_rate=calculation_rate,
            label=[len(label_str), *(ord(c) for c in label_str)],
            source=source,
            trigger=trigger,
            trigger_id=trigger_id,
        )

    @classmethod
    def ar(
        cls,
        *,
        label: str | None = None,
        source: UGenRecursiveInput | None = None,
        trigger: UGenRecursiveInput | None = None,
        trigger_id: UGenRecursiveInput = -1,
    ) -> UGenOperable:
        return cls._new_expanded(
            calculation_rate=CalculationRate.AUDIO,
            label=label,
            source=source,
            trigger=trigger,
            trigger_id=trigger_id,
        )

    @classmethod
    def kr(
        cls,
        *,
        label: str | None = None,
        source: UGenRecursiveInput | None = None,
        trigger: UGenRecursiveInput | None = None,
        trigger_id: UGenRecursiveInput = -1,
    ) -> UGenOperable:
        return cls._new_expanded(
            calculation_rate=CalculationRate.CONTROL,
            label=label,
            source=source,
            trigger=trigger,
            trigger_id=trigger_id,
        )


@ugen(ar=True, kr=True, channel_count=0, fixed_channel_count=True)
class SendPeakRMS(UGen):
    reply_rate = param(20)
    peak_lag = param(3)
    reply_id = param(-1)
    source_size = param()
    source = param(unexpanded=True)
    character_count = param()
    character = param(unexpanded=True)

    @classmethod
    def ar(
        cls,
        *,
        command_name: str = "/reply",
        peak_lag: UGenScalarInput = 3,
        reply_id: UGenScalarInput = -1,
        reply_rate: UGenScalarInput = 20,
        source: UGenRecursiveInput,
    ) -> UGenOperable:
        command = str(command_name)
        return cls._new_single(
            calculation_rate=CalculationRate.AUDIO,
            peak_lag=peak_lag,
            reply_id=reply_id,
            reply_rate=reply_rate,
            source=source,
            source_size=len(source),  # type: ignore[arg-type]
            character_count=len(command),
            character=[ord(x) for x in command],
        )

    @classmethod
    def kr(
        cls,
        *,
        command_name: str = "/reply",
        peak_lag: UGenScalarInput = 3,
        reply_id: UGenScalarInput = -1,
        reply_rate: UGenScalarInput = 20,
        source: UGenRecursiveInput,
    ) -> UGenOperable:
        command = str(command_name)
        return cls._new_single(
            calculation_rate=CalculationRate.CONTROL,
            peak_lag=peak_lag,
            reply_id=reply_id,
            reply_rate=reply_rate,
            source=source,
            source_size=len(source),  # type: ignore[arg-type]
            character_count=len(command),
            character=[ord(x) for x in command],
        )


@ugen(ar=True, kr=True, channel_count=0, fixed_channel_count=True)
class SendReply(UGen):
    trigger = param()
    reply_id = param(-1)
    character_count = param()
    character = param(unexpanded=True)
    source = param(unexpanded=True)

    @classmethod
    def ar(
        cls,
        *,
        command_name: str = "/reply",
        reply_id: UGenScalarInput = -1,
        source: UGenRecursiveInput,
        trigger: UGenRecursiveInput,
    ) -> UGenOperable:
        command = str(command_name)
        return cls._new_single(
            calculation_rate=CalculationRate.AUDIO,
            trigger=trigger,
            reply_id=reply_id,
            character_count=len(command),
            character=[ord(x) for x in command],
            source=source,
        )

    @classmethod
    def kr(
        cls,
        *,
        command_name: str = "/reply",
        reply_id: UGenScalarInput = -1,
        source: UGenRecursiveInput,
        trigger: UGenRecursiveInput,
    ) -> UGenOperable:
        command = str(command_name)
        return cls._new_single(
            calculation_rate=CalculationRate.CONTROL,
            trigger=trigger,
            reply_id=reply_id,
            character_count=len(command),
            character=[ord(x) for x in command],
            source=source,
        )
