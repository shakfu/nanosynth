"""Oscillator UGens."""

import math
from typing import Any

from ..enums import CalculationRate
from ..synthdef import PseudoUGen, UGen, UGenOperable, UGenRecursiveInput, param, ugen


@ugen(ar=True, kr=True, is_pure=True)
class COsc(UGen):
    buffer_id = param()
    frequency = param(440.0)
    beats = param(0.5)


@ugen(ar=True, kr=True, is_pure=True)
class DegreeToKey(UGen):
    buffer_id = param()
    source = param()
    octave = param(12)


@ugen(ar=True, kr=True, is_pure=True, unipolar=True)
class Impulse(UGen):
    frequency = param(440.0)
    phase = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class Index(UGen):
    buffer_id = param()
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class LFCub(UGen):
    frequency = param(440.0)
    initial_phase = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class LFGauss(UGen):
    duration = param(1)
    width = param(0.1)
    initial_phase = param(0)
    loop = param(1)
    done_action = param(0)

    @staticmethod
    def _range(
        output: UGenOperable, lo: UGenRecursiveInput, hi: UGenRecursiveInput
    ) -> UGenOperable:
        """sclang's LFGauss.range: map from the curve's minimum, exp(-1 / (2 width^2)), to 1."""
        width = output.ugen._inputs[1]  # type: ignore[attr-defined]
        if isinstance(width, (int, float)):
            minval: Any = math.exp(1.0 / (-2.0 * width * width))
        else:
            minval = (1.0 / (-2.0 * width.squared())).exp_()
        return output.linlin(minval, 1, lo, hi)


@ugen(ar=True, kr=True, is_pure=True)
class LFPar(UGen):
    frequency = param(440.0)
    initial_phase = param(0.0)


@ugen(ar=True, kr=True, is_pure=True, unipolar=True)
class LFPulse(UGen):
    frequency = param(440.0)
    initial_phase = param(0.0)
    width = param(0.5)


@ugen(ar=True, kr=True, is_pure=True)
class LFSaw(UGen):
    frequency = param(440.0)
    initial_phase = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class LFTri(UGen):
    frequency = param(440.0)
    initial_phase = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class Osc(UGen):
    buffer_id = param()
    frequency = param(440.0)
    initial_phase = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class OscN(UGen):
    buffer_id = param()
    frequency = param(440.0)
    initial_phase = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class Select(UGen):
    selector = param()
    sources = param(unexpanded=True)


class SelectX(PseudoUGen):
    """Crossfade between neighbouring elements of ``sources`` (``XFade2``), as sclang."""

    @staticmethod
    def _build(
        rate: CalculationRate, which: UGenRecursiveInput, sources: UGenRecursiveInput
    ) -> UGenOperable:
        from ..synthdef import ConstantProxy
        from .panning import XFade2

        w = which if isinstance(which, UGenOperable) else ConstantProxy(which)  # type: ignore[arg-type]
        audio = rate == CalculationRate.AUDIO
        select = Select.ar if audio else Select.kr  # type: ignore[attr-defined]
        fade = XFade2.ar if audio else XFade2.kr  # type: ignore[attr-defined]
        return fade(  # type: ignore[no-any-return]
            in_a=select(selector=w.round_(2), sources=sources),
            in_b=select(selector=w.trunc(2) + 1, sources=sources),
            pan=(w * 2 - 1).fold2(1),
        )

    @classmethod
    def ar(
        cls, *, which: UGenRecursiveInput, sources: UGenRecursiveInput
    ) -> UGenOperable:
        return cls._build(CalculationRate.AUDIO, which, sources)

    @classmethod
    def kr(
        cls, *, which: UGenRecursiveInput, sources: UGenRecursiveInput
    ) -> UGenOperable:
        return cls._build(CalculationRate.CONTROL, which, sources)


@ugen(ar=True, kr=True, is_pure=True)
class SinOsc(UGen):
    frequency = param(440.0)
    phase = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class SinOscFB(UGen):
    frequency = param(440.0)
    feedback = param(0.0)


class PMOsc(PseudoUGen):
    """Phase modulation: a ``SinOsc`` whose phase is another ``SinOsc``."""

    @classmethod
    def ar(
        cls,
        *,
        carrier_frequency: UGenRecursiveInput,
        modulator_frequency: UGenRecursiveInput,
        pm_index: UGenRecursiveInput = 0.0,
        modulator_phase: UGenRecursiveInput = 0.0,
    ) -> UGenOperable:
        modulator = SinOsc.ar(frequency=modulator_frequency, phase=modulator_phase)  # type: ignore[attr-defined]
        return SinOsc.ar(frequency=carrier_frequency, phase=modulator * pm_index)  # type: ignore[attr-defined,no-any-return]

    @classmethod
    def kr(
        cls,
        *,
        carrier_frequency: UGenRecursiveInput,
        modulator_frequency: UGenRecursiveInput,
        pm_index: UGenRecursiveInput = 0.0,
        modulator_phase: UGenRecursiveInput = 0.0,
    ) -> UGenOperable:
        modulator = SinOsc.kr(frequency=modulator_frequency, phase=modulator_phase)  # type: ignore[attr-defined]
        return SinOsc.kr(frequency=carrier_frequency, phase=modulator * pm_index)  # type: ignore[attr-defined,no-any-return]


@ugen(ar=True, kr=True, is_pure=True)
class SyncSaw(UGen):
    sync_frequency = param(440.0)
    saw_frequency = param(440.0)


@ugen(ar=True, kr=True, is_pure=True)
class VOsc(UGen):
    buffer_id = param()
    frequency = param(440.0)
    phase = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class VOsc3(UGen):
    buffer_id = param()
    freq_1 = param(110.0)
    freq_2 = param(220.0)
    freq_3 = param(440.0)


@ugen(ar=True, kr=True, is_pure=True)
class VarSaw(UGen):
    frequency = param(440.0)
    initial_phase = param(0.0)
    width = param(0.5)


@ugen(ar=True, kr=True, is_pure=True)
class Vibrato(UGen):
    frequency = param(440)
    rate = param(6)
    depth = param(0.02)
    delay = param(0)
    onset = param(0)
    rate_variation = param(0.04)
    depth_variation = param(0.1)
    initial_phase = param(0)
    trigger = param(0)


@ugen(ar=True, kr=True, is_pure=True)
class WrapIndex(UGen):
    buffer_id = param()
    source = param()
