"""Enum types for nanosynth."""

import enum
from collections.abc import Sequence as SequenceABC
from typing import SupportsFloat, SupportsInt, cast


class CalculationRate(enum.IntEnum):
    """UGen computation rate.

    Determines how often a UGen computes new output values:

    - ``SCALAR`` (0) -- computed once at synth creation (initial rate, ``.ir``).
    - ``CONTROL`` (1) -- computed once per control block, typically every 64
      samples (control rate, ``.kr``).
    - ``AUDIO`` (2) -- computed every sample (audio rate, ``.ar``).
    - ``DEMAND`` (3) -- computed only when explicitly demanded by another UGen
      (demand rate, ``.dr``), used with ``Demand``, ``Duty``, etc.

    When combining UGens at different rates, the result runs at the highest
    rate among its inputs (e.g. audio-rate + control-rate = audio-rate).
    """

    SCALAR = 0
    CONTROL = 1
    AUDIO = 2
    DEMAND = 3

    @classmethod
    def from_expr(cls, expr: object) -> "CalculationRate":
        """Coerce an arbitrary value to a CalculationRate.

        Accepts CalculationRate instances, ParameterRate, numeric types
        (treated as SCALAR), rate-token strings (``"ar"``, ``"kr"``,
        ``"ir"``), and sequences (returns the maximum rate).
        """
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
    """SynthDef parameter rate.

    Controls how a ``SynthDefBuilder`` parameter is exposed to the server:

    - ``SCALAR`` (0) -- set once at synth creation; uses ``Control.ir``.
    - ``TRIGGER`` (1) -- re-triggers when the value changes; uses ``TrigControl``.
    - ``AUDIO`` (2) -- audio-rate input; uses ``AudioControl``.
    - ``CONTROL`` (3) -- standard control-rate parameter; uses ``Control.kr``
      (or ``LagControl`` when a lag is specified).

    Distinct from ``CalculationRate``: this enum governs which Control UGen
    type is generated, not the per-sample computation rate.
    """

    SCALAR = 0
    TRIGGER = 1
    AUDIO = 2
    CONTROL = 3

    @classmethod
    def from_expr(cls, expr: object) -> "ParameterRate":
        """Coerce a value to a ParameterRate.

        Accepts ParameterRate instances, rate-token strings (``"ar"``,
        ``"kr"``, ``"ir"``), or integers.
        """
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
    """SuperCollider binary operator special indices.

    Each member maps to a BinaryOpUGen ``special_index`` value that selects
    the operation performed on two input signals. The 43 operators cover
    arithmetic, comparison, bitwise, power, trigonometric, ring modulation,
    and clipping operations.
    """

    ADDITION = 0
    SUBTRACTION = 1
    MULTIPLICATION = 2
    INTEGER_DIVISION = 3
    FLOAT_DIVISION = 4
    MODULO = 5
    EQUAL = 6
    NOT_EQUAL = 7
    LESS_THAN = 8
    GREATER_THAN = 9
    LESS_THAN_OR_EQUAL = 10
    GREATER_THAN_OR_EQUAL = 11
    MINIMUM = 14
    MAXIMUM = 15
    BITWISE_AND = 16
    BITWISE_OR = 17
    BITWISE_XOR = 18
    LCM = 19
    GCD = 20
    ROUND = 21
    ROUND_UP = 22
    TRUNCATION = 23
    ATAN2 = 24
    HYPOT = 25
    HYPOTX = 26
    POWER = 27
    SHIFT_LEFT = 28
    SHIFT_RIGHT = 29
    RING1 = 32
    RING2 = 33
    RING3 = 34
    RING4 = 35
    DIFFERENCE_OF_SQUARES = 36
    SUM_OF_SQUARES = 37
    SQUARE_OF_SUM = 38
    SQUARE_OF_DIFFERENCE = 39
    ABSOLUTE_DIFFERENCE = 40
    THRESHOLD = 41
    AMPLITUDE_CLIPPING = 42
    SCALE_NEGATIVE = 43
    CLIP2 = 44
    EXCESS = 45
    FOLD2 = 46
    WRAP2 = 47

    @classmethod
    def from_expr(cls, expr: object) -> "BinaryOperator":
        if isinstance(expr, cls):
            return expr
        return cls(int(cast(SupportsInt, expr)))


class UnaryOperator(enum.IntEnum):
    """SuperCollider unary operator special indices.

    Each member maps to a UnaryOpUGen ``special_index`` value that selects
    the operation performed on a single input signal. The 34 operators cover
    math (floor, ceil, sqrt, exp, log, trig), pitch conversion (midicps,
    cpsmidi, dbamp, ampdb), and waveshaping (distort, softclip, tanh).
    """

    NEGATIVE = 0
    BIT_NOT = 4
    ABSOLUTE_VALUE = 5
    CEILING = 8
    FLOOR = 9
    FRACTIONAL_PART = 10
    SIGN = 11
    SQUARED = 12
    CUBED = 13
    SQUARE_ROOT = 14
    EXPONENTIAL = 15
    RECIPROCAL = 16
    MIDICPS = 17
    CPSMIDI = 18
    MIDIRATIO = 19
    RATIOMIDI = 20
    DBAMP = 21
    AMPDB = 22
    OCTCPS = 23
    CPSOCT = 24
    LOG = 25
    LOG2 = 26
    LOG10 = 27
    SIN = 28
    COS = 29
    TAN = 30
    ARCSIN = 31
    ARCCOS = 32
    ARCTAN = 33
    SINH = 34
    COSH = 35
    TANH = 36
    DISTORT = 42
    SOFTCLIP = 43

    @classmethod
    def from_expr(cls, expr: object) -> "UnaryOperator":
        if isinstance(expr, cls):
            return expr
        return cls(int(cast(SupportsInt, expr)))


class DoneAction(enum.IntEnum):
    """Action to take when a UGen finishes (e.g. when an envelope completes).

    Passed to ``EnvGen``, ``Line``, ``XLine``, ``Linen``, and other UGens
    with a ``done_action`` parameter. The most common values:

    - ``NOTHING`` (0) -- do nothing when done.
    - ``PAUSE_SYNTH`` (1) -- pause the enclosing synth (can be resumed).
    - ``FREE_SYNTH`` (2) -- free (delete) the enclosing synth. This is the
      most commonly used done action.
    - ``FREE_SYNTH_AND_ENCLOSING_GROUP`` (14) -- free the synth and its
      enclosing group.
    """

    NOTHING = 0
    PAUSE_SYNTH = 1
    FREE_SYNTH = 2
    FREE_SYNTH_AND_PRECEDING_NODE = 3
    FREE_SYNTH_AND_FOLLOWING_NODE = 4
    FREE_SYNTH_AND_ALL_SIBLING_NODES = 13
    FREE_SYNTH_AND_ENCLOSING_GROUP = 14


class EnvelopeShape(enum.IntEnum):
    """Interpolation curve shape for envelope segments.

    Controls how the ``Envelope`` class interpolates between breakpoints:

    - ``STEP`` (0) -- jump immediately to the target value.
    - ``LINEAR`` (1) -- straight-line interpolation (default).
    - ``EXPONENTIAL`` (2) -- exponential curve (values must not cross zero).
    - ``SINE`` (3) -- sinusoidal S-curve.
    - ``WELCH`` (4) -- Welch window curve (sinusoidal half-arch).
    - ``CUSTOM`` (5) -- curvature controlled by a numeric curve value
      (positive = slow start, negative = fast start).
    - ``SQUARED`` (6) -- squared interpolation.
    - ``CUBED`` (7) -- cubed interpolation.
    - ``HOLD`` (8) -- hold the start value until the end of the segment.

    When a numeric value is passed as a curve to ``Envelope``, it is
    automatically treated as ``CUSTOM`` with that curvature.
    """

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
        """Coerce a value to an EnvelopeShape.

        Accepts EnvelopeShape instances, shape name strings, integers,
        or None (defaults to LINEAR).
        """
        if expr is None:
            return cls.LINEAR
        if isinstance(expr, cls):
            return expr
        if isinstance(expr, str):
            return cls[expr.upper()]
        return cls(int(cast(SupportsInt, expr)))
