"""Hilbert transform and frequency shifting UGens."""

from ..synthdef import (
    PseudoUGen,
    UGen,
    UGenRecursiveInput,
    UGenVector,
    param,
    ugen,
)
from .delay import DelayN
from .info import BufDur
from .pv import FFT, IFFT, PV_PhaseShift90


@ugen(ar=True)
class FreqShift(UGen):
    source = param()
    frequency = param(0.0)
    phase = param(0.0)


@ugen(ar=True, channel_count=2, fixed_channel_count=True)
class Hilbert(UGen):
    source = param()


class HilbertFIR(PseudoUGen):
    """FFT-based Hilbert transform, as sclang's: ``[source delayed, source shifted 90 degrees]``.

    The source is delayed by one buffer duration to align with the FFT output.
    """

    @classmethod
    def ar(
        cls, *, source: UGenRecursiveInput, buffer_id: UGenRecursiveInput
    ) -> UGenVector:
        chain = PV_PhaseShift90.kr(pv_chain=FFT.kr(buffer_id=buffer_id, source=source))  # type: ignore[attr-defined]
        delay = BufDur.kr(buffer_id=buffer_id)  # type: ignore[attr-defined]
        return UGenVector(
            DelayN.ar(source=source, maximum_delay_time=delay, delay_time=delay),  # type: ignore[attr-defined]
            IFFT.ar(pv_chain=chain),  # type: ignore[attr-defined]
        )
