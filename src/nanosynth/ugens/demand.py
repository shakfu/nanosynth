"""Demand-rate UGens."""

from collections.abc import Sequence
from typing import Any

from ..enums import CalculationRate
from ..synthdef import (
    UGen,
    UGenOperable,
    UGenRecursiveInput,
    UGenScalarInput,
    UGenSerializable,
    UGenVector,
    param,
    ugen,
)
from .bufio import ClearBuf, LocalBuf


@ugen(dr=True)
class Dbrown(UGen):
    length = param(float("inf"))
    minimum = param(0.0)
    maximum = param(1.0)
    step = param(0.01)


@ugen(dr=True)
class Dbufrd(UGen):
    buffer_id = param(0)
    phase = param(0)
    loop = param(1)


@ugen(dr=True)
class Dbufwr(UGen):
    buffer_id = param(0.0)
    phase = param(0.0)
    source = param(0.0)
    loop = param(1.0)


@ugen(ar=True, kr=True)
class Demand(UGen):
    trigger = param(0)
    reset = param(0)
    source = param(unexpanded=True)

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        source = kwargs["source"]
        if not isinstance(source, Sequence):
            kwargs["source"] = [source]  # type: ignore[list-item]
        self._channel_count = len(kwargs["source"])  # type: ignore[arg-type]
        return calculation_rate, kwargs


@ugen(ar=True, kr=True)
class DemandEnvGen(UGen):
    level = param()
    duration = param()
    shape = param(1)
    curve = param(0)
    gate = param(1)
    reset = param(1)
    level_scale = param(1)
    level_bias = param(0)
    time_scale = param(1)
    done_action = param(0)


@ugen(dr=True)
class Dgeom(UGen):
    length = param(float("inf"))
    start = param(1)
    grow = param(2)


@ugen(dr=True)
class Dibrown(UGen):
    length = param(float("inf"))
    minimum = param(0)
    maximum = param(12)
    step = param(1)


@ugen(dr=True)
class Diwhite(UGen):
    length = param(float("inf"))
    minimum = param(0)
    maximum = param(1)


@ugen(dr=True)
class Drand(UGen):
    repeats = param(1)
    sequence = param(unexpanded=True)


@ugen(dr=True)
class Dreset(UGen):
    source = param()
    reset = param(0)


@ugen(dr=True)
class Dseq(UGen):
    repeats = param(1)
    sequence = param(unexpanded=True)


@ugen(dr=True)
class Dser(UGen):
    repeats = param(1)
    sequence = param(unexpanded=True)


@ugen(dr=True)
class Dseries(UGen):
    length = param(float("inf"))
    start = param(1)
    step = param(1)


@ugen(dr=True)
class Dshuf(UGen):
    repeats = param(1)
    sequence = param(unexpanded=True)


@ugen(dr=True)
class Dstutter(UGen):
    n = param(2)
    source = param()


@ugen(dr=True)
class Dswitch(UGen):
    index_ = param()
    sequence = param(unexpanded=True)


@ugen(dr=True)
class Dswitch1(UGen):
    index_ = param()
    sequence = param(unexpanded=True)


class Dunique(UGenSerializable):
    """Share one demand stream among several readers, as sclang's ``Dunique``.

    Each use as a UGen input creates a reader. Every reader returns the values
    ``source`` produces, in order, each once. With ``protected``, a reader that
    falls ``max_buffer_size`` values behind ends instead of reading overwritten
    values.
    """

    __slots__ = ("_buffer", "_frames", "_protected", "_write_index", "_writer")

    def __init__(
        self,
        *,
        source: UGenRecursiveInput,
        max_buffer_size: int = 1024,
        protected: bool = True,
    ) -> None:
        self._frames = max_buffer_size
        self._protected = protected
        self._buffer = _cleared_buffer(max_buffer_size)
        self._write_index: UGenOperable | None = None
        if protected:
            self._write_index = _cleared_buffer(1)
            # 2 ** 24: the largest integer a float32 phase can address exactly.
            phase: UGenRecursiveInput = Dbufwr.dr(  # type: ignore[attr-defined]
                source=Dseries.dr(start=0, step=1, length=2**24),  # type: ignore[attr-defined]
                buffer_id=self._write_index,
            )
        else:
            phase = Dseq.dr(  # type: ignore[attr-defined]
                repeats=float("inf"),
                sequence=[Dseries.dr(start=0, step=1, length=max_buffer_size)],  # type: ignore[attr-defined]
            )
        self._writer = Dbufwr.dr(  # type: ignore[attr-defined]
            source=source, buffer_id=self._buffer, phase=phase, loop=int(protected)
        )

    def serialize(self) -> UGenVector:
        """Create a reader. Each read pulls the writer first (``first_arg``)."""
        buffer = self._buffer.first_arg(self._writer)
        if self._write_index is not None:
            read_index = _cleared_buffer(1)
            index = Dbufwr.dr(  # type: ignore[attr-defined]
                source=Dseries.dr(start=0, step=1, length=float("inf")),  # type: ignore[attr-defined]
                buffer_id=read_index,
            )
            written = Dbufrd.dr(buffer_id=self._write_index)  # type: ignore[attr-defined]
            read = Dbufrd.dr(buffer_id=read_index)  # type: ignore[attr-defined]
            overrun = (written - read) > self._frames
            # On overrun, switch to an empty series, which ends the stream.
            buffer = Dswitch1.dr(  # type: ignore[attr-defined]
                index_=overrun,
                sequence=[buffer, Dseries.dr(length=0)],  # type: ignore[attr-defined]
            )
        else:
            index = Dseq.dr(  # type: ignore[attr-defined]
                repeats=float("inf"),
                sequence=[Dseries.dr(start=0, step=1, length=self._frames)],  # type: ignore[attr-defined]
            )
        return UGenVector(Dbufrd.dr(buffer_id=buffer, phase=index, loop=1))  # type: ignore[attr-defined]


def _cleared_buffer(frames: int) -> UGenOperable:
    buffer: UGenOperable = LocalBuf.ir(frame_count=frames)  # type: ignore[attr-defined]
    ClearBuf.ir(buffer_id=buffer)  # type: ignore[attr-defined]
    return buffer


@ugen(ar=True, kr=True)
class Duty(UGen):
    duration = param(1.0)
    reset = param(0.0)
    done_action = param(0.0)
    level = param(1.0)


@ugen(dr=True)
class Dwhite(UGen):
    length = param(float("inf"))
    minimum = param(0.0)
    maximum = param(1.0)


@ugen(dr=True)
class Dwrand(UGen):
    repeats = param(1)
    length = param()
    weights = param(unexpanded=True)
    sequence = param(unexpanded=True)

    @classmethod
    def dr(
        cls,
        *,
        repeats: UGenScalarInput = 1,
        sequence: Sequence[UGenScalarInput],
        weights: Sequence[UGenScalarInput],
    ) -> UGenOperable:
        if not isinstance(sequence, Sequence):
            sequence = [sequence]
        seq = tuple(float(x) for x in sequence)  # type: ignore[arg-type]
        if not isinstance(weights, Sequence):
            weights = [weights]
        wts = tuple(float(x) for x in weights)  # type: ignore[arg-type]
        wts = wts[: len(seq)]
        wts += (0.0,) * (len(seq) - len(wts))
        return cls._new_expanded(
            calculation_rate=CalculationRate.DEMAND,
            repeats=repeats,
            length=len(seq),
            sequence=seq,
            weights=wts,
        )


@ugen(dr=True)
class Dxrand(UGen):
    repeats = param(1)
    sequence = param(unexpanded=True)
