"""
SynthDef builder and SCgf compiler for nanosynth.

Ported from supriya's ugens/core.py -- minimal subset for defining UGen graphs
in Python and compiling them to SuperCollider's SCgf binary format.
"""

import copy
import enum
import hashlib
import operator
import threading
import uuid
from collections.abc import Sequence as SequenceABC
from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    NamedTuple,
    SupportsFloat,
    SupportsInt,
    Union,
    cast,
    overload,
)

from .enums import (  # noqa: F401
    BinaryOperator,
    CalculationRate,
    DoneAction,
    EnvelopeShape,
    ParameterRate,
    UnaryOperator,
)


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

UGenScalarInput = Union[SupportsFloat, "UGenScalar"]
UGenVectorInput = Union["UGenSerializable", SequenceABC[UGenScalarInput]]
UGenRecursiveInput = Union[
    SupportsFloat,
    "UGenOperable",
    "UGenSerializable",
    SequenceABC["UGenRecursiveInput"],
]
UGenParams = dict[str, Union[UGenScalarInput, UGenVectorInput]]
UGenRecursiveParams = Union[UGenParams, list["UGenRecursiveParams"]]


# ---------------------------------------------------------------------------
# @ugen / @param decorator support
# ---------------------------------------------------------------------------


class Missing:
    """Sentinel for required parameters (no default)."""

    pass


MISSING = Missing()


class Default:
    """Sentinel for parameters whose default is computed from other parameters."""

    def __repr__(self) -> str:
        return "Default()"


class Param(NamedTuple):
    default: "Missing | Default | float | None" = MISSING
    unexpanded: bool = False


def _format_value(value: object) -> str:
    if value == float("inf"):
        value_repr = 'float("inf")'
    elif value == float("-inf"):
        value_repr = 'float("-inf")'
    elif isinstance(value, Missing):
        value_repr = "Missing()"
    elif isinstance(value, Default):
        value_repr = "Default()"
    elif isinstance(value, enum.Enum):
        value_repr = f"{type(value).__name__}.{value.name}"
    else:
        value_repr = repr(value)
    return value_repr


def _get_fn_globals() -> dict[str, Any]:
    return {
        "CalculationRate": CalculationRate,
        "Default": Default,
        "Missing": Missing,
        "SupportsFloat": SupportsFloat,
        "UGenRecursiveInput": UGenRecursiveInput,
        "UGenScalar": UGenScalar,
        "UGenSerializable": UGenSerializable,
        "UGenVector": UGenVector,
        "UGenScalarInput": UGenScalarInput,
        "UGenVectorInput": UGenVectorInput,
        "Union": Union,
    }


def _create_fn(
    *,
    cls: type["UGen"],
    name: str,
    args: list[str],
    body: list[str],
    return_type: Any,
    globals_: dict[str, Any] | None = None,
    decorator: Callable[..., Any] | None = None,
    override: bool = False,
) -> None:
    if name in cls.__dict__ and not override:
        return
    globals_ = globals_ or {}
    locals_ = {"_return_type": return_type}
    args_ = ",\n        ".join(args)
    body_ = "\n".join(f"        {line}" for line in body)
    text = f"    def {name}(\n        {args_}\n    ) -> _return_type:\n{body_}"
    local_vars = ", ".join(locals_.keys())
    text = f"def __create_fn__({local_vars}):\n{text}\n    return {name}"
    namespace: dict[str, Callable[..., Any]] = {}
    exec(text, globals_, namespace)
    value = namespace["__create_fn__"](**locals_)
    value.__qualname__ = f"{cls.__qualname__}.{value.__name__}"
    if decorator:
        value = decorator(value)
    setattr(cls, name, value)


def _add_init(
    cls: type["UGen"],
    params: dict[str, Param],
    is_multichannel: bool,
    channel_count: int,
    fixed_channel_count: bool,
) -> None:
    parent_class = UGen
    args = ["self", "*", "calculation_rate: CalculationRate"]
    body = [
        f"{'self._channel_count = channel_count' if is_multichannel and not fixed_channel_count else ''}"
    ]
    if is_multichannel and fixed_channel_count:
        body = [f"self._channel_count = {channel_count}"]
    elif not is_multichannel and channel_count != 1:
        body = [f"self._channel_count = {channel_count}"]
    else:
        body = []
    body.append(f"{parent_class.__name__}.__init__(")
    body.append("    self,")
    body.append("    calculation_rate=calculation_rate,")
    for key, param in params.items():
        value_repr = _format_value(param.default)
        type_ = "UGenVectorInput" if param.unexpanded else "UGenScalarInput"
        prefix = f"{key}: {type_}"
        args.append(
            f"{prefix} = {value_repr}"
            if not isinstance(param.default, Missing)
            else prefix
        )
        body.append(f"    {key}={key},")
    if is_multichannel and not fixed_channel_count:
        args.append(f"channel_count: int = {channel_count or 1}")
        body.insert(0, "self._channel_count = channel_count")
    args.append("**kwargs")
    body.append("    **kwargs,")
    body.append(")")
    _create_fn(
        cls=cls,
        name="__init__",
        args=args,
        body=body,
        globals_={**_get_fn_globals(), parent_class.__name__: parent_class},
        return_type=None,
    )


def _add_param_fn(cls: type["UGen"], name: str, index: int, unexpanded: bool) -> None:
    _create_fn(
        cls=cls,
        name=name,
        args=["self"],
        body=(
            [f"return self._inputs[{index}:]"]
            if unexpanded
            else [f"return self._inputs[{index}]"]
        ),
        decorator=property,
        globals_=_get_fn_globals(),
        override=True,
        return_type=UGenVector if unexpanded else UGenScalar,
    )


def _add_rate_fn(
    cls: type["UGen"],
    rate: CalculationRate | None,
    params: dict[str, "Param"],
    is_multichannel: bool,
    channel_count: int,
    fixed_channel_count: bool,
) -> None:
    args = ["cls"]
    if params:
        args.append("*")
    for key, param in params.items():
        value_repr = _format_value(param.default)
        prefix = f"{key}: UGenRecursiveInput"
        args.append(
            f"{prefix} = {value_repr}"
            if not isinstance(param.default, Missing)
            else prefix
        )
    body = ["return cls._new_expanded("]
    if rate is None:
        body.append("    calculation_rate=None,")
    else:
        body.append(f"    calculation_rate=CalculationRate.{rate.name},")
    if is_multichannel and not fixed_channel_count:
        args.append(f"channel_count: int = {channel_count or 1}")
        body.append("    channel_count=channel_count,")
    body.extend(f"    {name}={name}," for name in params)
    body.append(")")
    _create_fn(
        cls=cls,
        name=rate.token if rate is not None else "new",
        args=args,
        body=body,
        decorator=classmethod,
        globals_=_get_fn_globals(),
        return_type=UGenOperable,
    )


def _process_class(
    cls: type["UGen"],
    *,
    ar: bool = False,
    kr: bool = False,
    ir: bool = False,
    dr: bool = False,
    new: bool = False,
    has_done_flag: bool = False,
    is_multichannel: bool = False,
    is_output: bool = False,
    is_pure: bool = False,
    is_width_first: bool = False,
    channel_count: int = 1,
    fixed_channel_count: bool = False,
) -> type["UGen"]:
    params: dict[str, Param] = {}
    unexpanded_keys = []
    valid_calculation_rates = []
    for name, value in cls.__dict__.items():
        if not isinstance(value, Param):
            continue
        params[name] = value
        if value.unexpanded:
            unexpanded_keys.append(name)
        _add_param_fn(cls, name, len(params) - 1, value.unexpanded)
    _add_init(cls, params, is_multichannel, channel_count, fixed_channel_count)
    for should_add, rate in [
        (ar, CalculationRate.AUDIO),
        (kr, CalculationRate.CONTROL),
        (ir, CalculationRate.SCALAR),
        (dr, CalculationRate.DEMAND),
        (new, None),
    ]:
        if not should_add:
            continue
        _add_rate_fn(
            cls, rate, params, is_multichannel, channel_count, fixed_channel_count
        )
        if rate is not None:
            valid_calculation_rates.append(rate)
    cls._has_done_flag = bool(has_done_flag)
    cls._is_output = bool(is_output)
    cls._is_pure = bool(is_pure)
    cls._is_width_first = bool(is_width_first)
    cls._ordered_keys = tuple(params.keys())
    cls._unexpanded_keys = frozenset(unexpanded_keys)
    cls._valid_calculation_rates = tuple(valid_calculation_rates)  # type: ignore[attr-defined]
    if cls.__doc__ is None:
        rate_tokens = ", ".join(r.token for r in valid_calculation_rates)
        lines = [f"{cls.__name__} -- {rate_tokens}" if rate_tokens else cls.__name__]
        if params:
            lines.append("")
            lines.append("Parameters:")
            for name, p in params.items():
                if isinstance(p.default, Missing):
                    lines.append(f"    {name} (required)")
                else:
                    lines.append(f"    {name} (default: {p.default})")
        cls.__doc__ = "\n".join(lines)
    return cls


def param(
    default: Missing | Default | float | None = MISSING,
    *,
    unexpanded: bool = False,
) -> Param:
    """Define a UGen parameter. Akin to dataclasses.field."""
    return Param(default, unexpanded)


def ugen(
    *,
    ar: bool = False,
    kr: bool = False,
    ir: bool = False,
    dr: bool = False,
    new: bool = False,
    has_done_flag: bool = False,
    is_multichannel: bool = False,
    is_output: bool = False,
    is_pure: bool = False,
    is_width_first: bool = False,
    channel_count: int = 1,
    fixed_channel_count: bool = False,
) -> Callable[[type["UGen"]], type["UGen"]]:
    """Decorate a UGen class. Akin to dataclasses.dataclass."""

    def wrap(cls: type[UGen]) -> type[UGen]:
        return _process_class(
            cls,
            ar=ar,
            kr=kr,
            ir=ir,
            dr=dr,
            new=new,
            has_done_flag=has_done_flag,
            is_multichannel=is_multichannel,
            is_output=is_output,
            is_pure=is_pure,
            is_width_first=is_width_first,
            channel_count=channel_count,
            fixed_channel_count=fixed_channel_count,
        )

    if is_multichannel and fixed_channel_count:
        raise ValueError(
            "is_multichannel and fixed_channel_count are mutually exclusive"
        )
    return wrap


# ---------------------------------------------------------------------------
# Protocols / ABCs
# ---------------------------------------------------------------------------


class UGenSerializable:
    __slots__ = ()

    def serialize(self) -> "UGenVector":
        raise NotImplementedError


class PseudoUGen:
    """Base class for virtual UGens that compose other UGens."""

    def __init__(self) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _compute_binary_op(
    left: UGenRecursiveInput,
    right: UGenRecursiveInput,
    special_index: BinaryOperator,
    float_operator: Callable[..., Any] | None = None,
) -> "UGenOperable":
    def recurse(all_expanded_params: UGenRecursiveParams) -> "UGenOperable":
        if not isinstance(all_expanded_params, dict) and len(all_expanded_params) == 1:
            all_expanded_params = all_expanded_params[0]
        if isinstance(all_expanded_params, dict):
            if (
                isinstance(left, SupportsFloat)
                and isinstance(right, SupportsFloat)
                and float_operator is not None
            ):
                return ConstantProxy(float_operator(float(left), float(right)))
            return BinaryOpUGen._new_single(
                calculation_rate=max(
                    [
                        CalculationRate.from_expr(left),
                        CalculationRate.from_expr(right),
                    ]
                ),
                special_index=special_index,
                **all_expanded_params,
            )
        return UGenVector(
            *(recurse(expanded_params) for expanded_params in all_expanded_params)
        )

    return recurse(UGen._expand_params({"left": left, "right": right}))


def _compute_unary_op(
    source: UGenRecursiveInput,
    special_index: UnaryOperator,
    float_operator: Callable[..., Any] | None = None,
) -> "UGenOperable":
    def recurse(all_expanded_params: UGenRecursiveParams) -> "UGenOperable":
        if not isinstance(all_expanded_params, dict) and len(all_expanded_params) == 1:
            all_expanded_params = all_expanded_params[0]
        if isinstance(all_expanded_params, dict):
            if isinstance(source, SupportsFloat) and float_operator is not None:
                return ConstantProxy(float_operator(float(source)))
            return UnaryOpUGen._new_single(
                calculation_rate=max([CalculationRate.from_expr(source)]),
                special_index=special_index,
                **all_expanded_params,
            )
        return UGenVector(
            *(recurse(expanded_params) for expanded_params in all_expanded_params)
        )

    return recurse(UGen._expand_params({"source": source}))


# ---------------------------------------------------------------------------
# Core UGen graph classes
# ---------------------------------------------------------------------------


class UGenOperable:
    """Mixin for UGen arithmetic operations."""

    __slots__ = ()

    def __abs__(self) -> "UGenOperable":
        return _compute_unary_op(
            source=self,
            special_index=UnaryOperator.ABSOLUTE_VALUE,
            float_operator=operator.abs,
        )

    def __add__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=self,
            right=expr,
            special_index=BinaryOperator.ADDITION,
            float_operator=operator.add,
        )

    def __radd__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=expr,
            right=self,
            special_index=BinaryOperator.ADDITION,
            float_operator=operator.add,
        )

    def __sub__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=self,
            right=expr,
            special_index=BinaryOperator.SUBTRACTION,
            float_operator=operator.sub,
        )

    def __rsub__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=expr,
            right=self,
            special_index=BinaryOperator.SUBTRACTION,
            float_operator=operator.sub,
        )

    def __mul__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=self,
            right=expr,
            special_index=BinaryOperator.MULTIPLICATION,
            float_operator=operator.mul,
        )

    def __rmul__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=expr,
            right=self,
            special_index=BinaryOperator.MULTIPLICATION,
            float_operator=operator.mul,
        )

    def __truediv__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=self,
            right=expr,
            special_index=BinaryOperator.FLOAT_DIVISION,
            float_operator=operator.truediv,
        )

    def __rtruediv__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=expr,
            right=self,
            special_index=BinaryOperator.FLOAT_DIVISION,
            float_operator=operator.truediv,
        )

    def __mod__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=self,
            right=expr,
            special_index=BinaryOperator.MODULO,
            float_operator=operator.mod,
        )

    def __gt__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=self,
            right=expr,
            special_index=BinaryOperator.GREATER_THAN,
        )

    def __lt__(self, expr: UGenRecursiveInput) -> "UGenOperable":
        return _compute_binary_op(
            left=self,
            right=expr,
            special_index=BinaryOperator.LESS_THAN,
        )

    def __neg__(self) -> "UGenOperable":
        return _compute_unary_op(
            source=self,
            special_index=UnaryOperator.NEGATIVE,
            float_operator=operator.neg,
        )


class UGenScalar(UGenOperable):
    """A UGen scalar."""

    __slots__ = ()

    def __iter__(self) -> Iterator["UGenOperable"]:
        yield self


class OutputProxy(UGenScalar):
    """A UGen output proxy -- reference to a specific output of a UGen."""

    __slots__ = ("ugen", "index")

    def __init__(self, ugen: "UGen", index: int) -> None:
        self.ugen = ugen
        self.index = index

    def __eq__(self, expr: object) -> bool:
        return (
            isinstance(expr, type(self))
            and self.ugen is expr.ugen
            and self.index == expr.index
        )

    def __hash__(self) -> int:
        return hash((type(self), id(self.ugen), self.index))

    def __repr__(self) -> str:
        return repr(self.ugen).replace(">", f"[{self.index}]>")

    @property
    def calculation_rate(self) -> CalculationRate:
        return self.ugen.calculation_rate


class ConstantProxy(UGenScalar):
    """Wraps a float constant, exposing UGenOperable arithmetic."""

    __slots__ = ("value",)

    def __init__(self, value: SupportsFloat) -> None:
        self.value = float(value)

    def __eq__(self, expr: object) -> bool:
        if isinstance(expr, SupportsFloat):
            return float(self) == float(expr)
        return False

    def __float__(self) -> float:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __repr__(self) -> str:
        return f"<{self.value}>"


class UGenVector(UGenOperable, SequenceABC["UGenOperable"]):
    """A sequence of UGenOperables."""

    __slots__ = ("_values",)

    def __init__(self, *values: SupportsFloat | UGenOperable) -> None:
        values_: list[UGen | UGenScalar | "UGenVector"] = []
        for x in values:
            if isinstance(x, (UGen, UGenScalar, UGenVector)):
                values_.append(x)
            elif isinstance(x, UGenSerializable):
                values_.append(UGenVector(*x.serialize()))
            elif isinstance(x, SupportsFloat):
                values_.append(ConstantProxy(float(x)))
            else:
                raise ValueError(
                    f"Expected UGen, UGenScalar, UGenVector, or float, got {type(x).__name__}: {x!r}"
                )
        self._values = tuple(values_)

    @overload
    def __getitem__(self, i: int) -> UGenOperable: ...
    @overload
    def __getitem__(self, i: slice) -> "UGenVector": ...
    def __getitem__(self, i: int | slice) -> "UGenOperable | UGenVector":
        if isinstance(i, int):
            return self._values[i]
        return UGenVector(*self._values[i])

    def __iter__(self) -> Iterator[UGenOperable]:
        yield from self._values

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return f"<UGenVector([{', '.join(repr(x) for x in self)}])>"


class SynthDefError(Exception):
    pass


# Thread-local storage for active builders
_local = threading.local()
_local._active_builders = []


class UGen(UGenOperable, SequenceABC["UGenOperable"]):
    """Base class for all unit generators."""

    __slots__ = (
        "_calculation_rate",
        "_special_index",
        "_inputs",
        "_input_keys",
        "_uuid",
        "_values",
    )

    _channel_count = 1
    _has_done_flag = False
    _is_output = False
    _is_pure = False
    _is_width_first = False
    _ordered_keys: tuple[str, ...] = ()
    _unexpanded_keys: frozenset[str] = frozenset()

    def __init__(
        self,
        *,
        calculation_rate: CalculationRate = CalculationRate.SCALAR,
        special_index: SupportsInt = 0,
        **kwargs: UGenRecursiveInput | None,
    ) -> None:
        calculation_rate, kwargs = self._postprocess_kwargs(
            calculation_rate=calculation_rate, **kwargs
        )
        self._calculation_rate = CalculationRate.from_expr(calculation_rate)
        self._special_index = int(special_index)
        input_keys: list[str | tuple[str, int]] = []
        inputs: list[OutputProxy | float] = []
        for key in self._ordered_keys:
            value = kwargs.pop(key, None)
            if value is None:
                continue
            if isinstance(value, UGenSerializable):
                serialized = value.serialize()
                if any(isinstance(x, UGenVector) for x in serialized):
                    raise ValueError(
                        f"Unexpected UGenVector in serialized input '{key}'"
                    )
                value = cast(SequenceABC[SupportsFloat | UGenScalar], serialized)
            if isinstance(value, SequenceABC) and not isinstance(
                value, (str, UGenScalar)
            ):
                if key not in self._unexpanded_keys:
                    raise ValueError(
                        f"Sequence input for '{key}' requires unexpanded=True in param()"
                    )
                iterator: Iterable[tuple[int | None, Any]] = (
                    (i, v) for i, v in enumerate(value)
                )
            else:
                iterator = ((None, v) for v in [value])
            for i, x in iterator:
                if isinstance(x, ConstantProxy):
                    inputs.append(float(x.value))
                elif isinstance(x, OutputProxy):
                    inputs.append(x)
                elif isinstance(x, SupportsFloat):
                    inputs.append(float(x))
                else:
                    raise ValueError(
                        f"Invalid input type for '{key}': expected float or UGenScalar, got {type(x).__name__}"
                    )
                input_keys.append((key, i) if i is not None else key)
        if kwargs:
            raise ValueError(
                f"{type(self).__name__} received unknown parameters: {', '.join(kwargs)}"
            )
        self._inputs = tuple(inputs)
        self._input_keys = tuple(input_keys)
        self._uuid: uuid.UUID | None = None
        if hasattr(_local, "_active_builders") and _local._active_builders:
            builder = _local._active_builders[-1]
            self._uuid = builder._uuid
            builder._add_ugen(self)
        for input_ in self._inputs:
            if isinstance(input_, OutputProxy) and input_.ugen._uuid != self._uuid:
                raise SynthDefError("UGen input in different scope")
        self._values = tuple(
            OutputProxy(ugen=self, index=i)
            for i in range(getattr(self, "_channel_count", 1))
        )

    @overload
    def __getitem__(self, i: int) -> UGenOperable: ...
    @overload
    def __getitem__(self, i: slice) -> UGenVector: ...
    def __getitem__(self, i: int | slice) -> UGenOperable | UGenVector:
        if isinstance(i, int):
            return self._values[i]
        return UGenVector(*self._values[i])

    def __iter__(self) -> Iterator[UGenOperable]:
        yield from self._values

    def __len__(self) -> int:
        return self._channel_count

    def __repr__(self) -> str:
        return f"<{type(self).__name__}.{self.calculation_rate.token}()>"

    def _eliminate(
        self, sort_bundles: dict["UGen", "SynthDefBuilder.SortBundle"]
    ) -> None:
        if not (sort_bundle := sort_bundles.get(self)) or sort_bundle.descendants:
            return
        del sort_bundles[self]
        for antecedent in tuple(sort_bundle.antecedents):
            if not (antecedent_bundle := sort_bundles.get(antecedent)):
                continue
            antecedent_bundle.descendants.remove(self)
            antecedent._optimize(sort_bundles)

    @classmethod
    def _expand_params(
        cls,
        params: dict[str, UGenRecursiveInput],
        unexpanded_keys: Iterable[str] | None = None,
    ) -> UGenRecursiveParams:
        unexpanded_keys_ = set(unexpanded_keys or ())
        size = 0
        for key, value in params.items():
            if isinstance(value, UGenSerializable):
                params[key] = value = value.serialize()
            if isinstance(value, (SupportsFloat, UGenScalar)):
                continue
            elif isinstance(value, SequenceABC) and not isinstance(value, str):
                if key in unexpanded_keys_:
                    if isinstance(value, SequenceABC) and any(
                        (
                            isinstance(x, SequenceABC)
                            and not isinstance(x, (SupportsFloat, UGenScalar, str))
                        )
                        for x in value
                    ):
                        size = max(size, len(value))
                    else:
                        continue
                else:
                    size = max(size, len(value))
        if not size:
            return cast(dict[str, Union[UGenScalarInput, UGenVectorInput]], params)
        results = []
        for i in range(size):
            new_params: dict[str, UGenRecursiveInput] = {}
            for key, value in params.items():
                if isinstance(value, UGenSerializable):
                    value = value.serialize()
                if isinstance(value, (SupportsFloat, UGenScalar)):
                    new_params[key] = value
                elif isinstance(value, SequenceABC) and not isinstance(value, str):
                    if key in unexpanded_keys_:
                        if isinstance(value, SequenceABC) and all(
                            isinstance(x, (SupportsFloat, UGenScalar)) for x in value
                        ):
                            new_params[key] = value
                        else:
                            new_params[key] = value[i % len(value)]
                    else:
                        new_params[key] = value[i % len(value)]
            results.append(
                cls._expand_params(new_params, unexpanded_keys=unexpanded_keys)
            )
        return results

    @classmethod
    def _new_expanded(
        cls,
        *,
        calculation_rate: CalculationRate | None,
        special_index: int = 0,
        **kwargs: UGenRecursiveInput | None,
    ) -> UGenOperable:
        def recurse(all_expanded_params: UGenRecursiveParams) -> UGenOperable:
            if (
                not isinstance(all_expanded_params, dict)
                and len(all_expanded_params) == 1
            ):
                all_expanded_params = all_expanded_params[0]
            if isinstance(all_expanded_params, dict):
                return cls._new_single(
                    calculation_rate=calculation_rate,
                    special_index=special_index,
                    **all_expanded_params,
                )
            return UGenVector(
                *(recurse(expanded_params) for expanded_params in all_expanded_params)
            )

        filtered = {k: v for k, v in kwargs.items() if v is not None}
        return recurse(
            cls._expand_params(filtered, unexpanded_keys=cls._unexpanded_keys)
        )

    @classmethod
    def _new_single(
        cls,
        *,
        calculation_rate: CalculationRate | None = None,
        special_index: SupportsInt = 0,
        **kwargs: UGenRecursiveInput | None,
    ) -> UGenOperable:
        ugen = cls(
            calculation_rate=CalculationRate.from_expr(calculation_rate),
            special_index=special_index,
            **kwargs,
        )
        if len(ugen) == 1:
            return ugen[0]
        return ugen

    def _optimize(
        self, sort_bundles: dict["UGen", "SynthDefBuilder.SortBundle"]
    ) -> None:
        if not self._is_pure:
            return
        self._eliminate(sort_bundles)

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: UGenRecursiveInput | None,
    ) -> tuple[CalculationRate, dict[str, UGenRecursiveInput | None]]:
        return calculation_rate, kwargs

    @property
    def calculation_rate(self) -> CalculationRate:
        return self._calculation_rate

    @property
    def has_done_flag(self) -> bool:
        return self._has_done_flag

    @property
    def inputs(self) -> tuple[OutputProxy | float, ...]:
        return tuple(self._inputs)

    @property
    def special_index(self) -> int:
        return self._special_index


# ---------------------------------------------------------------------------
# Operator UGens
# ---------------------------------------------------------------------------


class UnaryOpUGen(UGen):
    _ordered_keys = ("source",)
    _is_pure = True

    def __init__(
        self,
        *,
        calculation_rate: CalculationRate,
        source: UGenScalarInput,
        special_index: SupportsInt = 0,
    ) -> None:
        super().__init__(
            calculation_rate=calculation_rate,
            source=source,
            special_index=special_index,
        )

    def __repr__(self) -> str:
        return f"<UnaryOpUGen.{self.calculation_rate.token}({self.operator.name})>"

    @property
    def operator(self) -> UnaryOperator:
        return UnaryOperator(self.special_index)


class BinaryOpUGen(UGen):
    _ordered_keys = ("left", "right")
    _is_pure = True

    def __init__(
        self,
        *,
        calculation_rate: CalculationRate,
        left: UGenScalarInput,
        right: UGenScalarInput,
        special_index: SupportsInt = 0,
    ) -> None:
        super().__init__(
            calculation_rate=calculation_rate,
            left=left,
            right=right,
            special_index=special_index,
        )

    def __repr__(self) -> str:
        return f"<BinaryOpUGen.{self.calculation_rate.token}({self.operator.name})>"

    @classmethod
    def _new_single(
        cls,
        *,
        calculation_rate: CalculationRate | None = None,
        special_index: SupportsInt = 0,
        **kwargs: UGenRecursiveInput | None,
    ) -> UGenOperable:
        def process(
            left: UGenScalar | float,
            right: UGenScalar | float,
        ) -> UGenOperable | float:
            if special_index == BinaryOperator.MULTIPLICATION:
                if left == 0 or right == 0:
                    return ConstantProxy(0)
                if left == 1:
                    return right
                if left == -1:
                    return -right
                if right == 1:
                    return left
                if right == -1:
                    return -left
            if special_index == BinaryOperator.ADDITION:
                if left == 0:
                    return right
                if right == 0:
                    return left
            if special_index == BinaryOperator.SUBTRACTION:
                if left == 0:
                    return -right
                if right == 0:
                    return left
            if special_index == BinaryOperator.FLOAT_DIVISION:
                if right == 1:
                    return left
                if right == -1:
                    return -left
            return cls(
                calculation_rate=max(
                    [
                        CalculationRate.from_expr(left),
                        CalculationRate.from_expr(right),
                    ]
                ),
                special_index=special_index,
                left=left,
                right=right,
            )[0]

        left = kwargs["left"]
        right = kwargs["right"]
        if not isinstance(left, (SupportsFloat, UGenScalar)):
            raise ValueError(
                f"Left operand must be float or UGenScalar, got {type(left).__name__}"
            )
        if not isinstance(right, (SupportsFloat, UGenScalar)):
            raise ValueError(
                f"Right operand must be float or UGenScalar, got {type(right).__name__}"
            )
        result = process(
            float(left) if isinstance(left, SupportsFloat) else left,
            float(right) if isinstance(right, SupportsFloat) else right,
        )
        if isinstance(result, SupportsFloat) and not isinstance(result, UGenOperable):
            return ConstantProxy(result)
        if not isinstance(result, UGenOperable):
            return ConstantProxy(float(result))
        return result

    @property
    def operator(self) -> BinaryOperator:
        return BinaryOperator(self.special_index)


# ---------------------------------------------------------------------------
# Parameter / Control
# ---------------------------------------------------------------------------


class Parameter(UGen):
    def __init__(
        self,
        *,
        name: str | None = None,
        value: float | SequenceABC[float],
        rate: ParameterRate | None = ParameterRate.CONTROL,
        lag: float | None = None,
    ) -> None:
        if isinstance(value, SupportsFloat):
            self.value: tuple[float, ...] = (float(value),)
        else:
            self.value = tuple(float(x) for x in value)
        self.name = name
        self.lag = lag
        self.rate = ParameterRate.from_expr(rate)
        self._channel_count = len(self.value)
        super().__init__(calculation_rate=CalculationRate.from_expr(self.rate))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Parameter):
            return NotImplemented
        return (type(self), self.name, self.value, self.rate, self.lag) == (
            type(other),
            other.name,
            other.value,
            other.rate,
            other.lag,
        )

    def __hash__(self) -> int:
        return hash((type(self), self.name, self.value, self.rate, self.lag))

    def __repr__(self) -> str:
        return f"<Parameter.{self.calculation_rate.token}({self.name})>"


class Control(UGen):
    def __init__(
        self,
        *,
        parameters: SequenceABC[Parameter],
        calculation_rate: CalculationRate,
        special_index: int = 0,
    ) -> None:
        self._parameters = tuple(parameters)
        self._channel_count = sum(len(parameter) for parameter in self._parameters)
        super().__init__(
            calculation_rate=calculation_rate,
            special_index=special_index,
        )

    @property
    def parameters(self) -> SequenceABC[Parameter]:
        return self._parameters


class AudioControl(Control):
    pass


class LagControl(Control):
    _ordered_keys = ("lags",)
    _unexpanded_keys = frozenset(["lags"])

    def __init__(
        self,
        *,
        parameters: SequenceABC[Parameter],
        calculation_rate: CalculationRate,
        special_index: int = 0,
    ) -> None:
        self._parameters = tuple(parameters)
        self._channel_count = sum(len(parameter) for parameter in self._parameters)
        lags = []
        for parameter in parameters:
            lags.extend([parameter.lag or 0.0] * len(parameter))
        UGen.__init__(
            self,
            calculation_rate=calculation_rate,
            lags=lags,
            special_index=special_index,
        )


class TrigControl(Control):
    pass


# ---------------------------------------------------------------------------
# SynthDef
# ---------------------------------------------------------------------------


class SynthDef:
    def __init__(self, ugens: SequenceABC[UGen], name: str | None = None) -> None:
        if not ugens:
            raise SynthDefError("No UGens provided")
        self._ugens = tuple(ugens)
        self._name = name
        constants: list[float] = []
        for ugen in ugens:
            for input_ in ugen.inputs:
                if isinstance(input_, float) and input_ not in constants:
                    constants.append(input_)
        self._constants = tuple(constants)
        self._controls: tuple[Control, ...] = tuple(
            ugen for ugen in ugens if isinstance(ugen, Control)
        )
        self._parameters: dict[str, tuple[Parameter, int]] = (
            self._collect_indexed_parameters(self._controls)
        )
        self._compiled_graph = _compile_ugen_graph(self)

    def __hash__(self) -> int:
        return hash((type(self), self._name, self._compiled_graph))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return False
        return (self._name, self._compiled_graph) == (
            other._name,
            other._compiled_graph,
        )

    def __repr__(self) -> str:
        return f"<SynthDef: {self.effective_name}>"

    def _collect_indexed_parameters(
        self, controls: SequenceABC[Control]
    ) -> dict[str, tuple[Parameter, int]]:
        mapping: dict[str, tuple[Parameter, int]] = {}
        for control in controls:
            index = control.special_index
            for parameter in control.parameters:
                if parameter.name is None:
                    raise ValueError(f"Parameter has no name: {parameter!r}")
                mapping[parameter.name] = (parameter, index)
                index += len(parameter)
        return mapping

    def compile(self, use_anonymous_name: bool = False) -> bytes:
        return compile_synthdefs(self, use_anonymous_names=use_anonymous_name)

    @property
    def anonymous_name(self) -> str:
        return hashlib.md5(self._compiled_graph).hexdigest()

    @property
    def constants(self) -> SequenceABC[float]:
        return self._constants

    @property
    def controls(self) -> SequenceABC[Control]:
        return self._controls

    @property
    def effective_name(self) -> str:
        return self.name or self.anonymous_name

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def parameters(self) -> dict[str, tuple[Parameter, int]]:
        return dict(self._parameters)

    @property
    def ugens(self) -> SequenceABC[UGen]:
        return self._ugens

    # -- High-level convenience methods ----------------------------------------

    def send(self, server: "Any") -> None:
        """Send this SynthDef to a running server."""
        server.send_synthdef(self)

    def play(
        self,
        server: "Any",
        target: int = 1,
        action: int = 0,
        **params: float,
    ) -> int:
        """Send this SynthDef (if needed) and create a synth. Returns node ID."""
        self.send(server)
        result: int = server.synth(
            self.effective_name, target=target, action=action, **params
        )
        return result

    def dump_ugens(self) -> str:
        """Return a human-readable representation of the UGen graph."""
        lines: list[str] = [f"SynthDef: {self.effective_name}"]
        for i, u in enumerate(self._ugens):
            type_name = type(u).__name__
            rate = u.calculation_rate.token
            if isinstance(u, Control):
                param_names = [p.name or "?" for p in u.parameters]
                line = f"  {i}: {type_name}.{rate} - [{', '.join(param_names)}]"
            else:
                parts: list[str] = []
                for input_, key in zip(u._inputs, u._input_keys):
                    if isinstance(key, tuple):
                        key_str = key[0]
                    else:
                        key_str = key
                    if isinstance(input_, OutputProxy):
                        src_name = type(input_.ugen).__name__
                        parts.append(f"{key_str}: {src_name}[{input_.index}]")
                    else:
                        parts.append(f"{key_str}: {input_}")
                if isinstance(u, BinaryOpUGen):
                    op_name = u.operator.name
                    line = f"  {i}: {type_name}.{rate}({op_name}, {', '.join(parts)})"
                elif isinstance(u, UnaryOpUGen):
                    op_name = u.operator.name
                    line = f"  {i}: {type_name}.{rate}({op_name}, {', '.join(parts)})"
                else:
                    line = f"  {i}: {type_name}.{rate}({', '.join(parts)})"
                if len(u) > 1:
                    line += f" -> {len(u)} outputs"
            lines.append(line)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# SynthDefBuilder
# ---------------------------------------------------------------------------


class SynthDefBuilder:
    class SortBundle(NamedTuple):
        ugen: UGen
        width_first_antecedents: tuple[UGen, ...]
        antecedents: list[UGen]
        descendants: list[UGen]

    def __init__(self, **kwargs: Parameter | SequenceABC[float] | float) -> None:
        self._building = False
        self._parameters: dict[str, Parameter] = {}
        self._ugens: list[UGen] = []
        self._uuid = uuid.uuid4()
        if not hasattr(_local, "_active_builders"):
            _local._active_builders = []
        for key, value in kwargs.items():
            if isinstance(value, Parameter):
                self.add_parameter(
                    lag=value.lag, name=key, value=value.value, rate=value.rate
                )
            else:
                self.add_parameter(name=key, value=value)

    def __enter__(self) -> "SynthDefBuilder":
        if not hasattr(_local, "_active_builders"):
            _local._active_builders = []
        _local._active_builders.append(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        _local._active_builders.pop()

    def __getitem__(self, item: str) -> OutputProxy | Parameter:
        """Look up a parameter by name.

        Returns an OutputProxy for scalar parameters, or the Parameter
        itself for multi-channel parameters (sequence values).

        Raises:
            KeyError: If the parameter name does not exist.
        """
        parameter = self._parameters[item]
        if len(parameter) == 1:
            return cast(OutputProxy, parameter[0])
        return parameter

    def _add_ugen(self, ugen: UGen) -> None:
        if ugen._uuid != self._uuid:
            raise SynthDefError("UGen input in different scope")
        if not self._building:
            self._ugens.append(ugen)

    def _build_control_mapping(
        self, parameters: SequenceABC[Parameter]
    ) -> tuple[list[Control], dict[OutputProxy, OutputProxy]]:
        parameter_mapping: dict[ParameterRate, list[Parameter]] = {}
        for parameter in parameters:
            parameter_mapping.setdefault(parameter.rate, []).append(parameter)
        for filtered_parameters in parameter_mapping.values():
            filtered_parameters.sort(key=lambda x: x.name or "")
        controls: list[Control] = []
        control_mapping: dict[OutputProxy, OutputProxy] = {}
        starting_control_index = 0
        for parameter_rate in sorted(ParameterRate):
            filtered_parameters = parameter_mapping.get(parameter_rate, [])
            if not filtered_parameters:
                continue
            if parameter_rate == ParameterRate.SCALAR:
                control = Control(
                    calculation_rate=CalculationRate.SCALAR,
                    parameters=filtered_parameters,
                    special_index=starting_control_index,
                )
            elif parameter_rate == ParameterRate.TRIGGER:
                control = TrigControl(
                    calculation_rate=CalculationRate.CONTROL,
                    parameters=filtered_parameters,
                    special_index=starting_control_index,
                )
            elif parameter_rate == ParameterRate.AUDIO:
                control = AudioControl(
                    calculation_rate=CalculationRate.AUDIO,
                    parameters=filtered_parameters,
                    special_index=starting_control_index,
                )
            elif any(parameter.lag for parameter in filtered_parameters):
                control = LagControl(
                    calculation_rate=CalculationRate.CONTROL,
                    parameters=filtered_parameters,
                    special_index=starting_control_index,
                )
            else:
                control = Control(
                    calculation_rate=CalculationRate.CONTROL,
                    parameters=filtered_parameters,
                    special_index=starting_control_index,
                )
            controls.append(control)
            output_index = 0
            for parameter in filtered_parameters:
                for output in parameter:
                    control_mapping[cast(OutputProxy, output)] = cast(
                        OutputProxy, control[output_index]
                    )
                    output_index += 1
                    starting_control_index += 1
        return controls, control_mapping

    def _initiate_topological_sort(
        self, ugens: list[UGen]
    ) -> dict[UGen, "SynthDefBuilder.SortBundle"]:
        sort_bundles: dict[UGen, SynthDefBuilder.SortBundle] = {}
        width_first_antecedents: list[UGen] = []
        for ugen in ugens:
            sort_bundles[ugen] = self.SortBundle(
                antecedents=[],
                descendants=[],
                ugen=ugen,
                width_first_antecedents=tuple(width_first_antecedents),
            )
            if ugen._is_width_first:
                width_first_antecedents.append(ugen)
        for ugen, sort_bundle in sort_bundles.items():
            for input_ in ugen.inputs:
                if not isinstance(input_, OutputProxy):
                    continue
                if input_.ugen not in sort_bundle.antecedents:
                    sort_bundle.antecedents.append(input_.ugen)
                if (
                    ugen
                    not in (input_sort_bundle := sort_bundles[input_.ugen]).descendants
                ):
                    input_sort_bundle.descendants.append(ugen)
            for antecedent in sort_bundle.width_first_antecedents:
                if antecedent not in sort_bundle.antecedents:
                    sort_bundle.antecedents.append(antecedent)
                if (
                    ugen
                    not in (input_sort_bundle := sort_bundles[antecedent]).descendants
                ):
                    input_sort_bundle.descendants.append(ugen)
            sort_bundle.descendants[:] = sorted(
                sort_bundles[ugen].descendants,
                key=lambda x: ugens.index(ugen),
            )
        return sort_bundles

    def _cleanup_local_bufs(self, ugens: list[UGen]) -> list[UGen]:
        """Insert MaxLocalBufs for any LocalBuf UGens in the graph.

        SuperCollider requires a MaxLocalBufs UGen to be present whenever
        LocalBuf UGens are used (e.g. by FFT). This pass counts LocalBuf
        instances, inserts a MaxLocalBufs just before the first one, and
        wires them together.
        """
        from .ugens.bufio import LocalBuf, MaxLocalBufs

        filtered: list[UGen] = []
        local_bufs: list[UGen] = []
        for ugen in ugens:
            if isinstance(ugen, MaxLocalBufs):
                continue  # remove existing MaxLocalBufs; we'll rebuild
            if isinstance(ugen, LocalBuf):
                local_bufs.append(ugen)
            filtered.append(ugen)
        if local_bufs:
            max_local_bufs = cast(
                OutputProxy,
                MaxLocalBufs.ir(maximum=len(local_bufs)),  # type: ignore[attr-defined]
            )
            for local_buf in local_bufs:
                inputs: list[OutputProxy | float] = list(local_buf._inputs[:2])
                inputs.append(max_local_bufs)
                local_buf._inputs = tuple(inputs)
            index = filtered.index(local_bufs[0])
            filtered[index:index] = [max_local_bufs.ugen]
        return filtered

    def _optimize(self, ugens: list[UGen]) -> list[UGen]:
        sort_bundles = self._initiate_topological_sort(ugens)
        for ugen in ugens:
            ugen._optimize(sort_bundles)
        return list(sort_bundles)

    def _remap_controls(
        self,
        ugens: list[UGen],
        control_mapping: dict[OutputProxy, OutputProxy],
    ) -> list[UGen]:
        for ugen in ugens:
            ugen._inputs = tuple(
                (
                    control_mapping.get(input_, input_)
                    if isinstance(input_, OutputProxy)
                    else input_
                )
                for input_ in ugen._inputs
            )
        return ugens

    def _sort_topologically(self, ugens: list[UGen]) -> list[UGen]:
        sort_bundles = self._initiate_topological_sort(ugens)
        available_ugens: list[UGen] = []
        output_stack: list[UGen] = []
        for ugen in reversed(ugens):
            if not sort_bundles[ugen].antecedents and ugen not in available_ugens:
                available_ugens.append(ugen)
        while available_ugens:
            available_ugen = available_ugens.pop()
            for descendant in reversed(sort_bundles[available_ugen].descendants):
                descendant_sort_bundle = sort_bundles[descendant]
                descendant_sort_bundle.antecedents.remove(available_ugen)
                if (
                    not descendant_sort_bundle.antecedents
                    and descendant_sort_bundle.ugen not in available_ugens
                ):
                    available_ugens.append(descendant_sort_bundle.ugen)
            output_stack.append(available_ugen)
        return output_stack

    def add_parameter(
        self,
        *,
        name: str,
        value: float | SequenceABC[float],
        rate: ParameterRate | None = ParameterRate.CONTROL,
        lag: float | None = None,
    ) -> OutputProxy | Parameter:
        """Add a named parameter to the SynthDef.

        Args:
            name: Parameter name (must be unique within this builder).
            value: Default value. A sequence creates a multi-channel parameter.
            rate: Parameter rate (CONTROL, AUDIO, TRIGGER, or SCALAR).
            lag: Lag time in seconds. Produces a LagControl when set.

        Returns:
            OutputProxy for scalar parameters, or the Parameter for
            multi-channel parameters.

        Raises:
            ValueError: If a parameter with this name already exists.
        """
        if name in self._parameters:
            raise ValueError(f"Duplicate parameter name: '{name}'")
        with self:
            parameter = Parameter(
                lag=lag, name=name, rate=ParameterRate.from_expr(rate), value=value
            )
        self._parameters[name] = parameter
        if len(parameter) == 1:
            return cast(OutputProxy, parameter[0])
        return parameter

    def build(self, name: str | None = None, optimize: bool = True) -> SynthDef:
        """Compile the UGen graph into a SynthDef.

        Performs control mapping, topological sorting, and optional dead
        code elimination. The builder can be reused after calling build().

        Args:
            name: SynthDef name. If None, an anonymous MD5 hash is used.
            optimize: If True, eliminate unused pure UGens from the graph.

        Returns:
            A compiled SynthDef ready for sending to a server.
        """
        try:
            self._building = True
            with self:
                ugens: list[UGen] = copy.deepcopy(self._ugens)
                parameters: list[Parameter] = sorted(
                    [x for x in ugens if isinstance(x, Parameter)],
                    key=lambda x: x.name or "",
                )
                ugens = [x for x in ugens if not isinstance(x, Parameter)]
                controls, control_mapping = self._build_control_mapping(parameters)
                ugens = controls + ugens
                ugens = self._remap_controls(ugens, control_mapping)
                ugens = self._cleanup_local_bufs(ugens)
                ugens = self._sort_topologically(ugens)
                if optimize:
                    ugens = self._optimize(ugens)
        finally:
            self._building = False
        return SynthDef(ugens, name=name)


from .compiler import _compile_ugen_graph, compile_synthdefs  # noqa: E402


# ---------------------------------------------------------------------------
# @synthdef decorator
# ---------------------------------------------------------------------------


def synthdef(*args: str | tuple[str, float]) -> Callable[..., SynthDef]:
    """Decorator for constructing SynthDefs from functions.

    Parameter rates and lags can be specified positionally::

        @synthdef("ar", ("kr", 0.5))
        def my_synth(freq=440, amp=0.1):
            ...

    Without arguments, all parameters default to control rate::

        @synthdef()
        def my_synth(freq=440, amp=0.1):
            ...
    """
    import inspect

    def inner(func: Callable[..., Any]) -> SynthDef:
        signature = inspect.signature(func)
        builder = SynthDefBuilder()
        kwargs: dict[str, OutputProxy | Parameter] = {}
        for i, (name, parameter) in enumerate(signature.parameters.items()):
            rate = ParameterRate.CONTROL
            lag = None
            try:
                arg_i = args[i]
                if isinstance(arg_i, str):
                    rate = ParameterRate.from_expr(arg_i)
                else:
                    rate_expr, lag = arg_i
                    rate = ParameterRate.from_expr(rate_expr)
            except (IndexError, TypeError):
                pass
            value = parameter.default
            if value is inspect._empty:
                value = 0.0
            kwargs[name] = builder.add_parameter(
                name=name, lag=lag, rate=rate, value=value
            )
        with builder:
            func(**kwargs)
        return builder.build(name=func.__name__)

    return inner
