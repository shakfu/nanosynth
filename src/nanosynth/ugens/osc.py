"""Oscillator UGens."""

from ..synthdef import UGen, param, ugen


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


@ugen(ar=True, kr=True, is_pure=True)
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


@ugen(ar=True, kr=True, is_pure=True)
class LFPar(UGen):
    frequency = param(440.0)
    initial_phase = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
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


@ugen(ar=True, kr=True, is_pure=True)
class SinOsc(UGen):
    frequency = param(440.0)
    phase = param(0.0)


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


@ugen(ar=True, kr=True, is_pure=True)
class WrapIndex(UGen):
    buffer_id = param()
    source = param()
