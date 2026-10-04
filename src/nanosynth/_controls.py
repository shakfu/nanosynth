"""Synth controls whose names collide with a method's own parameters.

``Server.synth(name, target, action, **params)`` cannot receive a control
named ``target`` through ``**params``. Such names go in a ``controls``
mapping instead. Callers that forward user-chosen names use :func:`call`,
which keeps the plain ``**params`` call shape unless a name would collide,
so duck-typed servers without ``controls`` keep working.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, SupportsFloat, TypeVar

from .osc import OscArgument

R = TypeVar("R")

#: Parameter names of ``Server.synth`` / ``SynthDef.play``-style methods.
SYNTH_PARAMS = frozenset({"name", "target", "action", "controls"})
#: Parameter names of ``Server.set``-style methods.
SET_PARAMS = frozenset({"node_id", "controls"})

Controls = Mapping[str, SupportsFloat] | SupportsFloat | None


def control_args(controls: Controls, params: Mapping[str, Any]) -> list[OscArgument]:
    """Flatten *controls* and keyword *params* into OSC name/value pairs.

    A non-mapping *controls* is a control literally named ``controls``, as
    passed before the mapping existed.

    Raises:
        TypeError: If a name is given both ways.
    """
    if controls is not None and not isinstance(controls, Mapping):
        params = {**params, "controls": controls}
        controls = None
    if controls:
        duplicate = controls.keys() & params.keys()
        if duplicate:
            raise TypeError(f"control(s) given twice: {', '.join(sorted(duplicate))}")
        params = {**controls, **params}
    args: list[OscArgument] = []
    for key, value in params.items():
        args.append(key)
        args.append(float(value))
    return args


def call(
    method: Callable[..., R],
    first: Any,
    params: Mapping[str, Any],
    reserved: frozenset[str],
) -> R:
    """``method(first, **params)``, or ``controls=params`` if a name collides."""
    if reserved.isdisjoint(params):
        return method(first, **params)
    return method(first, controls=dict(params))
