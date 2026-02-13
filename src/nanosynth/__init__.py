"""nanosynth -- minimal embedded SuperCollider synthesis engine wrapper."""

from .osc import OscBundle, OscMessage, find_free_port
from .scsynth import EmbeddedProcessProtocol, Options, find_ugen_plugins_path
from .synthdef import (
    CalculationRate,
    DoneAction,
    Param,
    SynthDef,
    SynthDefBuilder,
    UGen,
    compile_synthdefs,
    param,
    synthdef,
    ugen,
)
from .envelopes import EnvGen, Envelope
from .ugens import *  # noqa: F403
from .ugens import __all__ as _ugen_names

__all__ = [
    "CalculationRate",
    "DoneAction",
    "EmbeddedProcessProtocol",
    "EnvGen",
    "Envelope",
    "OscBundle",
    "OscMessage",
    "Options",
    "Param",
    "SynthDef",
    "SynthDefBuilder",
    "UGen",
    "compile_synthdefs",
    "find_free_port",
    "find_ugen_plugins_path",
    "param",
    "synthdef",
    "ugen",
] + _ugen_names
