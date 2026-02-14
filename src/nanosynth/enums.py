"""Enum types for nanosynth."""

import enum
from collections.abc import Sequence as SequenceABC
from typing import SupportsFloat, SupportsInt, cast


class CalculationRate(enum.IntEnum):
    SCALAR = 0
    CONTROL = 1
    AUDIO = 2
    DEMAND = 3

    @classmethod
    def from_expr(cls, expr: object) -> "CalculationRate":
        if expr is None:
            return cls.SCALAR
        if isinstance(expr, cls):
            return expr
        if hasattr(expr, "calculation_rate"):
            return cast("CalculationRate", expr.calculation_rate)
        if isinstance(expr, ParameterRate):
            return {
                ParameterRate.AUDIO: cls.AUDIO,
                ParameterRate.CONTROL: cls.CONTROL,
                ParameterRate.SCALAR: cls.SCALAR,
                ParameterRate.TRIGGER: cls.CONTROL,
            }[expr]
        if isinstance(expr, (int, float, SupportsFloat)):
            return cls.SCALAR
        if isinstance(expr, str):
            return cls[expr.upper()]
        if isinstance(expr, SequenceABC):
            return max(cls.from_expr(item) for item in expr)
        return cls(int(cast(SupportsInt, expr)))

    @property
    def token(self) -> str:
        return {0: "ir", 1: "kr", 2: "ar", 3: "dr"}.get(self.value, "new")


class ParameterRate(enum.IntEnum):
    SCALAR = 0
    TRIGGER = 1
    AUDIO = 2
    CONTROL = 3

    @classmethod
    def from_expr(cls, expr: object) -> "ParameterRate":
        if expr is None:
            return cls.CONTROL
        if isinstance(expr, cls):
            return expr
        if isinstance(expr, str):
            token_map = {"ar": cls.AUDIO, "kr": cls.CONTROL, "ir": cls.SCALAR}
            lower = expr.lower()
            if lower in token_map:
                return token_map[lower]
            return cls[expr.upper()]
        return cls(int(cast(SupportsInt, expr)))


class BinaryOperator(enum.IntEnum):
    ADDITION = 0
    SUBTRACTION = 1
    MULTIPLICATION = 2
    FLOAT_DIVISION = 4
    MODULO = 5
    LESS_THAN = 8
    GREATER_THAN = 9

    @classmethod
    def from_expr(cls, expr: object) -> "BinaryOperator":
        if isinstance(expr, cls):
            return expr
        return cls(int(cast(SupportsInt, expr)))


class UnaryOperator(enum.IntEnum):
    NEGATIVE = 0
    ABSOLUTE_VALUE = 5

    @classmethod
    def from_expr(cls, expr: object) -> "UnaryOperator":
        if isinstance(expr, cls):
            return expr
        return cls(int(cast(SupportsInt, expr)))


class DoneAction(enum.IntEnum):
    NOTHING = 0
    PAUSE_SYNTH = 1
    FREE_SYNTH = 2
    FREE_SYNTH_AND_PRECEDING_NODE = 3
    FREE_SYNTH_AND_FOLLOWING_NODE = 4
    FREE_SYNTH_AND_ALL_SIBLING_NODES = 13
    FREE_SYNTH_AND_ENCLOSING_GROUP = 14


class EnvelopeShape(enum.IntEnum):
    STEP = 0
    LINEAR = 1
    EXPONENTIAL = 2
    SINE = 3
    WELCH = 4
    CUSTOM = 5
    SQUARED = 6
    CUBED = 7
    HOLD = 8

    @classmethod
    def from_expr(cls, expr: object) -> "EnvelopeShape":
        if expr is None:
            return cls.LINEAR
        if isinstance(expr, cls):
            return expr
        if isinstance(expr, str):
            return cls[expr.upper()]
        return cls(int(cast(SupportsInt, expr)))
