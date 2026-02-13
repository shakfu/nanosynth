"""Envelope-related UGens (excluding EnvGen which stays in nanosynth.envelopes)."""

from ..synthdef import UGen, param, ugen


@ugen(kr=True)
class Done(UGen):
    source = param()


@ugen(kr=True)
class Free(UGen):
    trigger = param(0)
    node_id = param()


@ugen(kr=True)
class FreeSelf(UGen):
    trigger = param()


@ugen(kr=True)
class FreeSelfWhenDone(UGen):
    source = param()


@ugen(kr=True, has_done_flag=True)
class Linen(UGen):
    gate = param(1.0)
    attack_time = param(0.01)
    sustain_level = param(1.0)
    release_time = param(1.0)
    done_action = param(0)


@ugen(kr=True)
class Pause(UGen):
    trigger = param()
    node_id = param()


@ugen(kr=True)
class PauseSelf(UGen):
    trigger = param()


@ugen(kr=True)
class PauseSelfWhenDone(UGen):
    source = param()
