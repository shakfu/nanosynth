"""nanosynth -- minimal embedded SuperCollider synthesis engine wrapper."""

__version__ = "0.1.1"

from .enums import CalculationRate, DoneAction
from .osc import OscBundle, OscMessage, find_free_port
from .scsynth import EmbeddedProcessProtocol, Options, find_ugen_plugins_path
from .compiler import compile_synthdefs
from .synthdef import (
    Param,
    SynthDef,
    SynthDefBuilder,
    UGen,
    param,
    synthdef,
    ugen,
)
from .envelopes import EnvGen, Envelope
from .server import Server
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
    "Server",
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
