"""nanosynth -- minimal embedded SuperCollider synthesis engine wrapper."""

__version__ = "0.1.2"

from .enums import AddAction, CalculationRate, DoneAction
from .osc import OscBundle, OscMessage, find_free_port
from .scsynth import EmbeddedProcessProtocol, Options, find_ugen_plugins_path
from .compiler import compile_synthdefs
from .synthdef import (
    Default,
    Param,
    PseudoUGen,
    SynthDef,
    SynthDefBuilder,
    UGen,
    control,
    param,
    synthdef,
    ugen,
)
from .envelopes import EnvGen, Envelope
from .server import Group, Server, Synth
from .ugens import *  # noqa: F403

# Common UGens exported via star-import. The full set remains available
# via ``from nanosynth.ugens import *`` or qualified imports.
_COMMON_UGENS = [
    "BPF",
    "BrownNoise",
    "BufRd",
    "DelayL",
    "DelayN",
    "Dust",
    "FreeVerb",
    "HPF",
    "Impulse",
    "In",
    "LFNoise0",
    "LFNoise1",
    "LFNoise2",
    "LFPulse",
    "LFSaw",
    "LPF",
    "Line",
    "Mix",
    "Out",
    "Pan2",
    "PinkNoise",
    "PlayBuf",
    "Pulse",
    "RLPF",
    "Resonz",
    "Saw",
    "SinOsc",
    "WhiteNoise",
    "XLine",
]

__all__ = [
    "AddAction",
    "CalculationRate",
    "Default",
    "DoneAction",
    "EmbeddedProcessProtocol",
    "EnvGen",
    "Envelope",
    "Group",
    "OscBundle",
    "OscMessage",
    "Options",
    "Param",
    "PseudoUGen",
    "Server",
    "Synth",
    "SynthDef",
    "SynthDefBuilder",
    "UGen",
    "compile_synthdefs",
    "control",
    "find_free_port",
    "find_ugen_plugins_path",
    "param",
    "synthdef",
    "ugen",
] + _COMMON_UGENS
