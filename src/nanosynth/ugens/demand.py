"""Demand-rate UGens."""

from ..synthdef import UGen, param, ugen


@ugen(dr=True)
class Dbrown(UGen):
    minimum = param(0.0)
    maximum = param(1.0)
    step = param(0.01)
    length = param(float("inf"))


@ugen(dr=True)
class Dbufrd(UGen):
    buffer_id = param(0)
    phase = param(0)
    loop = param(1)


@ugen(dr=True)
class Dbufwr(UGen):
    source = param(0.0)
    buffer_id = param(0.0)
    phase = param(0.0)
    loop = param(1.0)


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
    start = param(1)
    grow = param(2)
    length = param(float("inf"))


@ugen(dr=True)
class Dibrown(UGen):
    minimum = param(0)
    maximum = param(12)
    step = param(1)
    length = param(float("inf"))


@ugen(dr=True)
class Diwhite(UGen):
    minimum = param(0)
    maximum = param(1)
    length = param(float("inf"))


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


@ugen(dr=True)
class Dunique(UGen):
    source = param()
    max_buffer_size = param(1024)
    protected = param(True)


@ugen(ar=True, kr=True)
class Duty(UGen):
    duration = param(1.0)
    reset = param(0.0)
    level = param(1.0)
    done_action = param(0.0)


@ugen(dr=True)
class Dwhite(UGen):
    minimum = param(0.0)
    maximum = param(0.0)
    length = param(float("inf"))


@ugen(dr=True)
class Dxrand(UGen):
    repeats = param(1)
    sequence = param(unexpanded=True)
