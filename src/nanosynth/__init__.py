"""nanosynth -- minimal embedded SuperCollider synthesis engine wrapper."""

__version__ = "0.1.4"

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
    SynthDefGraph,
    UGen,
    UGenInput,
    UGenNode,
    control,
    param,
    synthdef,
    ugen,
)
from .envelopes import EnvGen, Envelope
from .patterns import (
    Clock,
    Pbind,
    Pchoose,
    Pconst,
    Pgeom,
    Pn,
    Prand,
    Pseq,
    Pseries,
    Pwhite,
    Pattern,
    Player,
    Rest,
)
from .proxy import Ndef, NodeProxy
from .score import Score
from .server import Bus, Group, Server, Synth
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
    "Bus",
    "CalculationRate",
    "Clock",
    "Default",
    "DoneAction",
    "EmbeddedProcessProtocol",
    "EnvGen",
    "Envelope",
    "Group",
    "Ndef",
    "NodeProxy",
    "OscBundle",
    "OscMessage",
    "Options",
    "Param",
    "Pattern",
    "Pbind",
    "Pchoose",
    "Pconst",
    "Pgeom",
    "Player",
    "Pn",
    "Prand",
    "Pseq",
    "Pseries",
    "PseudoUGen",
    "Pwhite",
    "Rest",
    "Score",
    "Server",
    "Synth",
    "SynthDef",
    "SynthDefBuilder",
    "SynthDefGraph",
    "UGen",
    "UGenInput",
    "UGenNode",
    "compile_synthdefs",
    "control",
    "find_free_port",
    "find_ugen_plugins_path",
    "param",
    "synthdef",
    "ugen",
] + _COMMON_UGENS
