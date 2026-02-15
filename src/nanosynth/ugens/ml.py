"""Machine listening and analysis UGens."""

from typing import Any

from ..enums import CalculationRate
from ..synthdef import UGen, UGenRecursiveInput, param, ugen


@ugen(kr=True, channel_count=4, fixed_channel_count=True)
class BeatTrack(UGen):
    pv_chain = param()
    lock = param(0.0)


@ugen(kr=True, channel_count=6, fixed_channel_count=True)
class BeatTrack2(UGen):
    bus_index = param(0.0)
    feature_count = param()
    window_size = param(2)
    phase_accuracy = param(0.02)
    lock = param(0.0)
    weighting_scheme = param(-2.1)


@ugen(kr=True)
class KeyTrack(UGen):
    pv_chain = param()
    key_decay = param(2)
    chroma_leak = param(0.5)


@ugen(kr=True)
class Loudness(UGen):
    pv_chain = param()
    smask = param(0.25)
    tmask = param(1)


@ugen(kr=True, fixed_channel_count=True)
class MFCC(UGen):
    pv_chain = param()
    coeff_count = param(13)

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        self._channel_count = int(kwargs["coeff_count"])  # type: ignore[call-overload]
        return calculation_rate, kwargs


@ugen(kr=True)
class Onsets(UGen):
    pv_chain = param()
    threshold = param(0.5)
    odftype = param(3)
    relaxtime = param(1)
    floor_ = param(0.1)  # type: ignore[assignment]
    mingap = param(10)
    medianspan = param(11)
    whtype = param(1)
    rawodf = param(0)


@ugen(kr=True, channel_count=2, fixed_channel_count=True)
class Pitch(UGen):
    source = param()
    initial_frequency = param(440)
    min_frequency = param(60)
    max_frequency = param(4000)
    exec_frequency = param(100)
    max_bins_per_octave = param(16)
    median = param(1)
    amplitude_threshold = param(0.01)
    peak_threshold = param(0.5)
    down_sample_factor = param(1)
    clarity = param(0)


@ugen(kr=True)
class SpecCentroid(UGen):
    pv_chain = param()


@ugen(kr=True)
class SpecFlatness(UGen):
    pv_chain = param()


@ugen(kr=True)
class SpecPcile(UGen):
    pv_chain = param()
    fraction = param(0.5)
    interpolate = param(0)
