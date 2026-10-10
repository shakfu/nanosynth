"""sc3-plugins UGens whose sclang methods compute inputs: a count, a string sent as character
codes, or an output count taken from an argument. Hand-written; re-exported by ``sc3``.

Each class's wire slots are its parameters; its rate methods fill them as the sclang method
does. tests/test_sc3_ugens.py checks them against spec/sc3-plugins-reference.json.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..enums import CalculationRate
from ..synthdef import (
    UGen,
    UGenOperable,
    UGenRecursiveInput,
    UGenScalarInput,
    UGenVector,
    param,
    ugen,
)
from .dynamics import Amplitude
from .lines import A2K
from .osc import Impulse


def _as_list(x: Any) -> list[Any]:
    """An array argument as a list; one value is a list of one, as sclang's `asArray`."""
    return list(x) if isinstance(x, (list, tuple, UGenVector)) else [x]


def _codes(text: str) -> list[int]:
    return [ord(c) for c in text]


@ugen(kr=True)
class FeatureSave(UGen):
    """Writes feature values to a file (SCMIRUGens)."""

    feature_count = param()
    trig = param()
    features = param(unexpanded=True)

    @classmethod
    def kr(
        cls, *, features: UGenRecursiveInput, trig: UGenRecursiveInput
    ) -> UGenOperable:
        values = _as_list(features)
        return cls._new_single(
            calculation_rate=CalculationRate.CONTROL,
            feature_count=max(len(values), 1),
            trig=trig,
            features=values,
        )


@ugen(ar=True, kr=True)
class MatchingPResynth(UGen):
    """Resynthesises from a matching-pursuit dictionary and activations (MCLDUGens).

    ``activs`` alternates atom index and amplitude, as sclang's trailing arguments do.
    """

    dict_ = param()
    method = param(0)
    activ_count = param()
    trigger = param()
    residual = param(0)
    activs = param(unexpanded=True)

    @classmethod
    def _build(
        cls,
        rate: CalculationRate,
        dict_: UGenRecursiveInput,
        trigger: UGenRecursiveInput,
        activs: UGenRecursiveInput,
        method: UGenRecursiveInput,
        residual: UGenRecursiveInput,
    ) -> UGenOperable:
        values = _as_list(activs)
        return cls._new_single(
            calculation_rate=rate,
            dict_=dict_,
            method=method,
            activ_count=len(values) / 2,
            trigger=trigger,
            residual=residual,
            activs=values,
        )

    @classmethod
    def ar(
        cls,
        *,
        dict_: UGenRecursiveInput,
        trigger: UGenRecursiveInput,
        activs: UGenRecursiveInput,
        method: UGenRecursiveInput = 0,
        residual: UGenRecursiveInput = 0,
    ) -> UGenOperable:
        return cls._build(
            CalculationRate.AUDIO, dict_, trigger, activs, method, residual
        )

    @classmethod
    def kr(
        cls,
        *,
        dict_: UGenRecursiveInput,
        trigger: UGenRecursiveInput,
        activs: UGenRecursiveInput,
        method: UGenRecursiveInput = 0,
        residual: UGenRecursiveInput = 0,
    ) -> UGenOperable:
        return cls._build(
            CalculationRate.CONTROL, dict_, trigger, activs, method, residual
        )


@ugen(ir=True)
class Getenv(UGen):
    """The value of an environment variable on the server, or ``defaultval`` (MCLDUGens)."""

    key_size = param()
    defaultval = param(0)
    key_codes = param(unexpanded=True)

    @classmethod
    def ir(cls, *, key: object, defaultval: UGenScalarInput = 0) -> UGenOperable:
        text = str(key)
        return cls._new_single(
            calculation_rate=CalculationRate.SCALAR,
            key_size=len(text),
            defaultval=defaultval,
            key_codes=_codes(text),
        )


@ugen(ar=True)
class NovaDiskOut(UGen):
    """Records channels to a sound file (NovaDiskIO; not in a default sc3-plugins build).

    Sends the channel count of ``signal``. sclang sends ``signal.size``, which is 0 for a
    single UGen; the plugin then records no channels.
    """

    channel_count_ = param()
    signal = param(unexpanded=True)
    filename_size = param()
    filename_codes = param(unexpanded=True)

    @classmethod
    def ar(cls, *, signal: UGenRecursiveInput, filename: object) -> UGenOperable:
        channels = _as_list(signal)
        name = str(filename)
        return cls._new_single(
            calculation_rate=CalculationRate.AUDIO,
            channel_count_=len(channels),
            signal=channels,
            filename_size=len(name),
            filename_codes=_codes(name),
        )


@ugen(kr=True)
class TextVU(UGen):
    """Prints a text level meter of ``source`` to the server's console (MCLDUGens).

    Returns ``source``, as sclang does. A numeric ``trig`` is a rate in Hz. ``ana`` maps
    the source to the level shown; by default its amplitude.
    """

    trig = param()
    level = param()
    width = param(21)
    reset = param(0)
    label_size = param()
    label = param(unexpanded=True)

    @classmethod
    def _build(
        cls,
        source: UGenRecursiveInput,
        trig: UGenRecursiveInput,
        label: str | None,
        width: UGenRecursiveInput,
        reset: UGenRecursiveInput,
        ana: Callable[[Any], UGenRecursiveInput] | None,
    ) -> UGenOperable:
        rate = CalculationRate.from_expr(source)
        if label is None:
            label = f"UGen({type(getattr(source, 'ugen', source)).__name__})"
        release = 1 / float(trig) if isinstance(trig, (int, float)) else 5

        def amplitude(sig: Any) -> UGenRecursiveInput:
            if rate == CalculationRate.AUDIO:
                level = Amplitude._new_single(
                    calculation_rate=CalculationRate.AUDIO,
                    source=sig,
                    release_time=release,
                )
                return A2K._new_single(
                    calculation_rate=CalculationRate.CONTROL, source=level
                )
            return Amplitude._new_single(
                calculation_rate=CalculationRate.CONTROL,
                source=sig,
                release_time=release,
            )

        analyse = ana or amplitude
        if isinstance(trig, (int, float)):
            trig = Impulse._new_single(
                calculation_rate=CalculationRate.CONTROL, frequency=trig, phase=0
            )
        cls._new_single(
            calculation_rate=CalculationRate.CONTROL,
            trig=trig,
            level=analyse(source),
            width=width,
            reset=reset,
            label_size=len(label),
            label=_codes(label),
        )
        return source  # type: ignore[return-value]

    @classmethod
    def ar(
        cls,
        *,
        source: UGenRecursiveInput,
        trig: UGenRecursiveInput = 2,
        label: str | None = None,
        width: UGenRecursiveInput = 21,
        reset: UGenRecursiveInput = 0,
        ana: Callable[[Any], UGenRecursiveInput] | None = None,
    ) -> UGenOperable:
        return cls._build(source, trig, label, width, reset, ana)

    @classmethod
    def kr(
        cls,
        *,
        source: UGenRecursiveInput,
        trig: UGenRecursiveInput = 2,
        label: str | None = None,
        width: UGenRecursiveInput = 21,
        reset: UGenRecursiveInput = 0,
        ana: Callable[[Any], UGenRecursiveInput] | None = None,
    ) -> UGenOperable:
        return cls._build(source, trig, label, width, reset, ana)


@ugen(ar=True, kr=True, is_multichannel=True, channel_count=2)
class SOMRd(UGen):
    """The best-matching node of a self-organising map, one output per dimension (MCLDUGens)."""

    bufnum = param()
    netsize = param(10)
    numdims = param(2)
    gate = param(1)
    inputdata = param(unexpanded=True)

    @classmethod
    def _build(
        cls,
        rate: CalculationRate,
        bufnum: UGenRecursiveInput,
        inputdata: UGenRecursiveInput,
        netsize: UGenRecursiveInput,
        numdims: int,
        gate: UGenRecursiveInput,
    ) -> UGenOperable:
        if not 1 <= numdims <= 4:
            raise ValueError(f"numdims must be between 1 and 4, not {numdims}")
        return cls._new_single(
            calculation_rate=rate,
            channel_count=int(numdims),
            bufnum=bufnum,
            netsize=netsize,
            numdims=numdims,
            gate=gate,
            inputdata=_as_list(inputdata),
        )

    @classmethod
    def ar(
        cls,
        *,
        bufnum: UGenRecursiveInput,
        inputdata: UGenRecursiveInput,
        netsize: UGenRecursiveInput = 10,
        numdims: int = 2,
        gate: UGenRecursiveInput = 1,
    ) -> UGenOperable:
        return cls._build(
            CalculationRate.AUDIO, bufnum, inputdata, netsize, numdims, gate
        )

    @classmethod
    def kr(
        cls,
        *,
        bufnum: UGenRecursiveInput,
        inputdata: UGenRecursiveInput,
        netsize: UGenRecursiveInput = 10,
        numdims: int = 2,
        gate: UGenRecursiveInput = 1,
    ) -> UGenOperable:
        return cls._build(
            CalculationRate.CONTROL, bufnum, inputdata, netsize, numdims, gate
        )


__all__ = [
    "FeatureSave",
    "Getenv",
    "MatchingPResynth",
    "NovaDiskOut",
    "SOMRd",
    "TextVU",
]
