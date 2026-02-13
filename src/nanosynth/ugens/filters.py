"""Filter UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, kr=True, is_pure=True)
class APF(UGen):
    source = param()
    frequency = param(440.0)
    radius = param(0.8)


@ugen(ar=True, kr=True, is_pure=True)
class BPF(UGen):
    source = param()
    frequency = param(440.0)
    reciprocal_of_q = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BPZ2(UGen):
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class BRF(UGen):
    source = param()
    frequency = param(440.0)
    reciprocal_of_q = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class BRZ2(UGen):
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class Decay(UGen):
    source = param()
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class Decay2(UGen):
    source = param()
    attack_time = param(0.01)
    decay_time = param(1.0)


@ugen(ar=True, kr=True)
class DetectSilence(UGen):
    source = param()
    threshold = param(0.0001)
    time = param(0.1)
    done_action = param(0)


@ugen(ar=True, kr=True, is_pure=True)
class FOS(UGen):
    source = param()
    a_0 = param(0.0)
    a_1 = param(0.0)
    b_1 = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class Formlet(UGen):
    source = param()
    frequency = param(440.0)
    attack_time = param(1.0)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class HPF(UGen):
    source = param()
    frequency = param(440.0)


@ugen(ar=True, kr=True, is_pure=True)
class HPZ1(UGen):
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class HPZ2(UGen):
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class Integrator(UGen):
    source = param()
    coefficient = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class Lag(UGen):
    source = param()
    lag_time = param(0.1)


@ugen(ar=True, kr=True, is_pure=True)
class LagUD(UGen):
    source = param()
    lag_time_up = param(0.1)
    lag_time_down = param(0.1)


@ugen(ar=True, kr=True, is_pure=True)
class Lag2(UGen):
    source = param()
    lag_time = param(0.1)


@ugen(ar=True, kr=True, is_pure=True)
class Lag2UD(UGen):
    source = param()
    lag_time_up = param(0.1)
    lag_time_down = param(0.1)


@ugen(ar=True, kr=True, is_pure=True)
class Lag3(UGen):
    source = param()
    lag_time = param(0.1)


@ugen(ar=True, kr=True, is_pure=True)
class Lag3UD(UGen):
    source = param()
    lag_time_up = param(0.1)
    lag_time_down = param(0.1)


@ugen(ar=True, kr=True, is_pure=True)
class LeakDC(UGen):
    source = param()
    coefficient = param(0.995)


@ugen(ar=True, kr=True, is_pure=True)
class LPF(UGen):
    source = param()
    frequency = param(440.0)


@ugen(ar=True, kr=True, is_pure=True)
class LPZ1(UGen):
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class LPZ2(UGen):
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class Median(UGen):
    length = param(3)
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class MidEQ(UGen):
    source = param()
    frequency = param(440.0)
    reciprocal_of_q = param(1.0)
    db = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class MoogFF(UGen):
    source = param()
    frequency = param(100.0)
    gain = param(2.0)
    reset = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class OnePole(UGen):
    source = param()
    coefficient = param(0.5)


@ugen(ar=True, kr=True, is_pure=True)
class OneZero(UGen):
    source = param()
    coefficient = param(0.5)


@ugen(ar=True, kr=True, is_pure=True)
class RHPF(UGen):
    source = param()
    frequency = param(440.0)
    reciprocal_of_q = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class RLPF(UGen):
    source = param()
    frequency = param(440.0)
    reciprocal_of_q = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class Ramp(UGen):
    source = param()
    lag_time = param(0.1)


@ugen(ar=True, kr=True, is_pure=True)
class Ringz(UGen):
    source = param()
    frequency = param(440.0)
    decay_time = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class SOS(UGen):
    source = param()
    a_0 = param(0.0)
    a_1 = param(0.0)
    a_2 = param(0.0)
    b_1 = param(0.0)
    b_2 = param(0.0)


@ugen(ar=True, kr=True, is_pure=True)
class Slew(UGen):
    source = param()
    up = param(1.0)
    down = param(1.0)


@ugen(ar=True, kr=True, is_pure=True)
class Slope(UGen):
    source = param()


@ugen(ar=True, kr=True, is_pure=True)
class TwoPole(UGen):
    source = param()
    frequency = param(440.0)
    radius = param(0.8)


@ugen(ar=True, kr=True, is_pure=True)
class TwoZero(UGen):
    source = param()
    frequency = param(440.0)
    radius = param(0.8)
