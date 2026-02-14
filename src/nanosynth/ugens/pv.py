"""Phase vocoder UGens."""

from typing import Any

from ..enums import CalculationRate
from ..synthdef import (
    Default,
    OutputProxy,
    UGen,
    UGenOperable,
    param,
    ugen,
)


@ugen(is_width_first=True)
class PV_ChainUGen(UGen):
    """Abstract base class for phase-vocoder-chain unit generators."""

    @property
    def fft_size(self) -> UGenOperable:
        input_ = self.inputs[0]
        if not isinstance(input_, OutputProxy):
            raise ValueError(input_)
        if not isinstance(input_.ugen, PV_ChainUGen):
            raise ValueError(input_.ugen)
        return input_.ugen.fft_size


@ugen(kr=True, is_width_first=True)
class FFT(PV_ChainUGen):
    buffer_id = param(Default())
    source = param()
    hop = param(0.5)
    window_type = param(0)
    active = param(1)
    window_size = param(0)

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: Any,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        if isinstance(kwargs["buffer_id"], Default):
            from .bufio import LocalBuf

            kwargs["buffer_id"] = LocalBuf.ir(  # type: ignore[attr-defined]
                frame_count=kwargs["window_size"] or 2048
            )
        return calculation_rate, kwargs

    @property
    def fft_size(self) -> UGenOperable:
        from .info import BufFrames

        return BufFrames.ir(buffer_id=self.buffer_id)  # type: ignore[attr-defined,no-any-return]


@ugen(ar=True, kr=True, is_width_first=True)
class IFFT(UGen):
    pv_chain = param()
    window_type = param(0)
    window_size = param(0)


@ugen(kr=True, is_width_first=True)
class PV_Add(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()


@ugen(kr=True, is_width_first=True)
class PV_BinScramble(PV_ChainUGen):
    pv_chain = param()
    wipe = param(0)
    width = param(0.2)
    trigger = param(0)


@ugen(kr=True, is_width_first=True)
class PV_BinShift(PV_ChainUGen):
    pv_chain = param()
    stretch = param(1.0)
    shift = param(0.0)
    interpolate = param(0)


@ugen(kr=True, is_width_first=True)
class PV_BinWipe(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()
    wipe = param(0)


@ugen(kr=True, is_width_first=True)
class PV_BrickWall(PV_ChainUGen):
    pv_chain = param()
    wipe = param(0)


@ugen(kr=True, is_width_first=True)
class PV_ConformalMap(PV_ChainUGen):
    pv_chain = param()
    areal = param(0)
    aimag = param(0)


@ugen(kr=True, is_width_first=True)
class PV_Conj(PV_ChainUGen):
    pv_chain = param()


@ugen(kr=True, is_width_first=True)
class PV_Copy(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()


@ugen(kr=True, is_width_first=True)
class PV_CopyPhase(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()


@ugen(kr=True, is_width_first=True)
class PV_Diffuser(PV_ChainUGen):
    pv_chain = param()
    trigger = param(0)


@ugen(kr=True, is_width_first=True)
class PV_Div(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()


@ugen(kr=True, is_width_first=True)
class PV_HainsworthFoote(PV_ChainUGen):
    pv_chain = param()
    proph = param(0)
    propf = param(0)
    threshold = param(1)
    waittime = param(0.04)


@ugen(kr=True, is_width_first=True)
class PV_JensenAndersen(PV_ChainUGen):
    pv_chain = param()
    propsc = param(0.25)
    prophfe = param(0.25)
    prophfc = param(0.25)
    propsf = param(0.25)
    threshold = param(1)
    waittime = param(0.04)


@ugen(kr=True, is_width_first=True)
class PV_LocalMax(PV_ChainUGen):
    pv_chain = param()
    threshold = param(0)


@ugen(kr=True, is_width_first=True)
class PV_MagAbove(PV_ChainUGen):
    pv_chain = param()
    threshold = param(0)


@ugen(kr=True, is_width_first=True)
class PV_MagBelow(PV_ChainUGen):
    pv_chain = param()
    threshold = param(0)


@ugen(kr=True, is_width_first=True)
class PV_MagClip(PV_ChainUGen):
    pv_chain = param()
    threshold = param(0)


@ugen(kr=True, is_width_first=True)
class PV_MagDiv(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()
    zeroed = param(0.0001)


@ugen(kr=True, is_width_first=True)
class PV_MagFreeze(PV_ChainUGen):
    pv_chain = param()
    freeze = param(0)


@ugen(kr=True, is_width_first=True)
class PV_MagMul(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()


@ugen(kr=True, is_width_first=True)
class PV_MagNoise(PV_ChainUGen):
    pv_chain = param()


@ugen(kr=True, is_width_first=True)
class PV_MagShift(PV_ChainUGen):
    pv_chain = param()
    stretch = param(1.0)
    shift = param(0.0)


@ugen(kr=True, is_width_first=True)
class PV_MagSmear(PV_ChainUGen):
    pv_chain = param()
    bins = param(0)


@ugen(kr=True, is_width_first=True)
class PV_MagSquared(PV_ChainUGen):
    pv_chain = param()


@ugen(kr=True, is_width_first=True)
class PV_Max(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()


@ugen(kr=True, is_width_first=True)
class PV_Min(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()


@ugen(kr=True, is_width_first=True)
class PV_Mul(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()


@ugen(kr=True, is_width_first=True)
class PV_PhaseShift(PV_ChainUGen):
    pv_chain = param()
    shift = param()
    integrate = param(0)


@ugen(kr=True, is_width_first=True)
class PV_PhaseShift270(PV_ChainUGen):
    pv_chain = param()


@ugen(kr=True, is_width_first=True)
class PV_PhaseShift90(PV_ChainUGen):
    pv_chain = param()


@ugen(kr=True, is_width_first=True)
class PV_RandComb(PV_ChainUGen):
    pv_chain = param()
    wipe = param(0)
    trigger = param(0)


@ugen(kr=True, is_width_first=True)
class PV_RandWipe(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()
    wipe = param(0)
    trigger = param(0)


@ugen(kr=True, is_width_first=True)
class PV_RectComb(PV_ChainUGen):
    pv_chain = param()
    num_teeth = param(0)
    phase = param(0)
    width = param(0.5)


@ugen(kr=True, is_width_first=True)
class PV_RectComb2(PV_ChainUGen):
    pv_chain_a = param()
    pv_chain_b = param()
    num_teeth = param(0)
    phase = param(0)
    width = param(0.5)


@ugen(ar=True, kr=True)
class RunningSum(UGen):
    source = param()
    sample_count = param(40)
