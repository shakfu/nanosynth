"""SCgf binary compiler for nanosynth."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .synthdef import OutputProxy, SynthDef, UGen


def _compile_constants(synthdef: SynthDef) -> bytes:
    return b"".join(
        [
            _encode_unsigned_int_32bit(len(synthdef.constants)),
            *(_encode_float(constant) for constant in synthdef.constants),
        ]
    )


def _compile_parameters(synthdef: SynthDef) -> bytes:
    result = [
        _encode_unsigned_int_32bit(sum(len(control) for control in synthdef.controls))
    ]
    for control in synthdef.controls:
        for parameter in control.parameters:
            for value in parameter.value:
                result.append(_encode_float(value))
    result.append(_encode_unsigned_int_32bit(len(synthdef.parameters)))
    for name, (_, index) in synthdef.parameters.items():
        result.append(_encode_string(name) + _encode_unsigned_int_32bit(index))
    return b"".join(result)


def _compile_synthdef(synthdef: SynthDef, name: str) -> bytes:
    return b"".join(
        [
            _encode_string(name),
            _compile_ugen_graph(synthdef),
        ]
    )


def _compile_ugen(ugen: UGen, synthdef: SynthDef) -> bytes:
    return b"".join(
        [
            _encode_string(type(ugen).__name__),
            _encode_unsigned_int_8bit(ugen.calculation_rate),
            _encode_unsigned_int_32bit(len(ugen.inputs)),
            _encode_unsigned_int_32bit(len(ugen)),
            _encode_unsigned_int_16bit(int(ugen.special_index)),
            *(_compile_ugen_input_spec(input_, synthdef) for input_ in ugen.inputs),
            *(
                _encode_unsigned_int_8bit(ugen.calculation_rate)
                for _ in range(len(ugen))
            ),
        ]
    )


def _compile_ugens(synthdef: SynthDef) -> bytes:
    return b"".join(
        [
            _encode_unsigned_int_32bit(len(synthdef.ugens)),
            *(_compile_ugen(ugen, synthdef) for ugen in synthdef.ugens),
        ]
    )


def _compile_ugen_graph(synthdef: SynthDef) -> bytes:
    return b"".join(
        [
            _compile_constants(synthdef),
            _compile_parameters(synthdef),
            _compile_ugens(synthdef),
            _encode_unsigned_int_16bit(0),  # no variants
        ]
    )


def _compile_ugen_input_spec(input_: OutputProxy | float, synthdef: SynthDef) -> bytes:
    if isinstance(input_, float):
        return _encode_unsigned_int_32bit(0xFFFFFFFF) + _encode_unsigned_int_32bit(
            synthdef._constants.index(input_)
        )
    else:
        return _encode_unsigned_int_32bit(
            synthdef._ugens.index(input_.ugen)
        ) + _encode_unsigned_int_32bit(input_.index)


def _encode_string(value: str) -> bytes:
    return struct.pack(">B", len(value)) + value.encode("ascii")


def _encode_float(value: float) -> bytes:
    return struct.pack(">f", value)


def _encode_unsigned_int_8bit(value: int) -> bytes:
    return struct.pack(">B", value)


def _encode_unsigned_int_16bit(value: int) -> bytes:
    return struct.pack(">H", value)


def _encode_unsigned_int_32bit(value: int) -> bytes:
    return struct.pack(">I", value)


def compile_synthdefs(
    synthdef: SynthDef,
    *synthdefs: SynthDef,
    use_anonymous_names: bool = False,
) -> bytes:
    synthdefs_ = (synthdef,) + synthdefs
    return b"".join(
        [
            b"SCgf",
            _encode_unsigned_int_32bit(2),
            _encode_unsigned_int_16bit(len(synthdefs_)),
            *(
                _compile_synthdef(
                    sd,
                    (
                        sd.anonymous_name
                        if not sd.name or use_anonymous_names
                        else sd.name
                    ),
                )
                for sd in synthdefs_
            ),
        ]
    )
