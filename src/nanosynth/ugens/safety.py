"""Safety and diagnostic UGens."""

from ..synthdef import UGen, param, ugen


@ugen(ar=True, kr=True)
class CheckBadValues(UGen):
    source = param()
    ugen_id = param(0)
    post_mode = param(2)


@ugen(ar=True, kr=True)
class Sanitize(UGen):
    source = param()
    replace = param(0.0)
