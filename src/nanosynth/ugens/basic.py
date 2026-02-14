"""Basic utility UGens: MulAdd, Sum3, Sum4, Mix."""

import itertools
from collections.abc import Iterable, Sequence
from typing import Any, SupportsInt, Union

from ..enums import CalculationRate
from ..synthdef import (
    PseudoUGen,
    UGen,
    UGenOperable,
    UGenRecursiveInput,
    UGenScalar,
    UGenScalarInput,
    UGenVector,
    UGenVectorInput,
    param,
    ugen,
)


def _flatten(
    iterable: Iterable[Any],
    terminal_types: type | tuple[type, ...] | None = None,
) -> list[Any]:
    result: list[Any] = []
    for x in iterable:
        if terminal_types and isinstance(x, terminal_types):
            result.append(x)
        elif isinstance(x, Iterable) and not isinstance(x, str):
            result.extend(_flatten(x, terminal_types))
        else:
            result.append(x)
    return result


def _group_by_count(iterable: Iterable[Any], count: int) -> list[list[Any]]:
    iterator = iter(iterable)
    groups: list[list[Any]] = []
    while True:
        group = list(itertools.islice(iterator, count))
        if not group:
            break
        groups.append(group)
    return groups


def _zip_cycled(*args: Sequence[Any]) -> list[tuple[Any, ...]]:
    if not args:
        return []
    maximum_i = max(len(a) for a in args) - 1
    cycles = [itertools.cycle(a) for a in args]
    result: list[tuple[Any, ...]] = []
    for i, values in enumerate(zip(*cycles)):
        result.append(values)
        if i == maximum_i:
            break
    return result


@ugen(new=True)
class MulAdd(UGen):
    source = param()
    multiplier = param(1.0)
    addend = param(0.0)

    @classmethod
    def _new_single(  # type: ignore[override]
        cls,
        *,
        addend: UGenRecursiveInput = 0,
        multiplier: UGenRecursiveInput = 0,
        source: UGenRecursiveInput = 0,
        calculation_rate: CalculationRate | None = None,
        special_index: SupportsInt = 0,
        **kwargs: Union[UGenScalarInput, UGenVectorInput],
    ) -> UGenOperable:
        def _inputs_are_valid(
            source: UGenRecursiveInput,
            multiplier: UGenRecursiveInput,
            addend: UGenRecursiveInput,
        ) -> bool:
            if CalculationRate.from_expr(source) == CalculationRate.AUDIO:
                return True
            return (
                CalculationRate.from_expr(source) == CalculationRate.CONTROL
                and CalculationRate.from_expr(multiplier)
                in (CalculationRate.CONTROL, CalculationRate.SCALAR)
                and CalculationRate.from_expr(addend)
                in (CalculationRate.CONTROL, CalculationRate.SCALAR)
            )

        if multiplier == 0.0:
            return addend  # type: ignore[return-value]
        minus = multiplier == -1
        no_multiplier = multiplier == 1
        no_addend = addend == 0
        if no_multiplier and no_addend:
            return source  # type: ignore[return-value]
        if minus and no_addend:
            return -source  # type: ignore[operator]
        if no_addend:
            return source * multiplier  # type: ignore[operator]
        if minus:
            return addend - source  # type: ignore[operator]
        if no_multiplier:
            return source + addend  # type: ignore[operator]
        if _inputs_are_valid(source, multiplier, addend):
            return cls(
                addend=addend,
                multiplier=multiplier,
                calculation_rate=CalculationRate.from_expr(
                    (source, multiplier, addend)
                ),
                source=source,
            )[0]
        if _inputs_are_valid(multiplier, source, addend):
            return cls(
                addend=addend,
                multiplier=source,
                calculation_rate=CalculationRate.from_expr(
                    (multiplier, source, addend)
                ),
                source=multiplier,
            )[0]
        return (source * multiplier) + addend  # type: ignore[operator]


@ugen(new=True)
class Sum3(UGen):
    input_one = param()
    input_two = param()
    input_three = param()

    @classmethod
    def _new_single(  # type: ignore[override]
        cls,
        *,
        input_one: UGenRecursiveInput = 0,
        input_two: UGenRecursiveInput = 0,
        input_three: UGenRecursiveInput = 0,
        **kwargs: Any,
    ) -> UGenOperable:
        if input_three == 0:
            return input_one + input_two  # type: ignore[operator]
        if input_two == 0:
            return input_one + input_three  # type: ignore[operator]
        if input_one == 0:
            return input_two + input_three  # type: ignore[operator]
        return cls(
            calculation_rate=None,  # type: ignore[arg-type]
            input_one=input_one,
            input_two=input_two,
            input_three=input_three,
        )[0]

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: Any,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        inputs = sorted(
            [kwargs["input_one"], kwargs["input_two"], kwargs["input_three"]],
            key=lambda x: CalculationRate.from_expr(x),
            reverse=True,
        )
        calculation_rate = CalculationRate.from_expr(inputs)
        kwargs.update(
            input_one=inputs[0],
            input_two=inputs[1],
            input_three=inputs[2],
        )
        return calculation_rate, kwargs


@ugen(new=True)
class Sum4(UGen):
    input_one = param()
    input_two = param()
    input_three = param()
    input_four = param()

    @classmethod
    def _new_single(  # type: ignore[override]
        cls,
        *,
        input_one: UGenRecursiveInput = 0,
        input_two: UGenRecursiveInput = 0,
        input_three: UGenRecursiveInput = 0,
        input_four: UGenRecursiveInput = 0,
        **kwargs: Any,
    ) -> UGenOperable:
        if input_one == 0:
            return Sum3._new_single(
                input_one=input_two,
                input_two=input_three,
                input_three=input_four,
            )
        if input_two == 0:
            return Sum3._new_single(
                input_one=input_one,
                input_two=input_three,
                input_three=input_four,
            )
        if input_three == 0:
            return Sum3._new_single(
                input_one=input_one,
                input_two=input_two,
                input_three=input_four,
            )
        if input_four == 0:
            return Sum3._new_single(
                input_one=input_one,
                input_two=input_two,
                input_three=input_three,
            )
        return cls(
            calculation_rate=None,  # type: ignore[arg-type]
            input_one=input_one,
            input_two=input_two,
            input_three=input_three,
            input_four=input_four,
        )[0]

    def _postprocess_kwargs(
        self,
        *,
        calculation_rate: CalculationRate,
        **kwargs: Any,
    ) -> tuple[CalculationRate, dict[str, Any]]:
        inputs = sorted(
            [
                kwargs["input_one"],
                kwargs["input_two"],
                kwargs["input_three"],
                kwargs["input_four"],
            ],
            key=lambda x: CalculationRate.from_expr(x),
            reverse=True,
        )
        calculation_rate = CalculationRate.from_expr(inputs)
        kwargs.update(
            input_one=inputs[0],
            input_two=inputs[1],
            input_three=inputs[2],
            input_four=inputs[3],
        )
        return calculation_rate, kwargs


class Mix(PseudoUGen):
    """A down-to-mono signal mixer."""

    @classmethod
    def new(
        cls,
        sources: UGenRecursiveInput | Sequence[UGenRecursiveInput],
    ) -> UGenOperable:
        if not isinstance(sources, Sequence):
            sources = [sources]
        flat = _flatten(sources, terminal_types=UGenScalar)
        summed_sources: list[UGenOperable] = []
        for part in _group_by_count(flat, 4):
            if len(part) == 4:
                result = Sum4.new(  # type: ignore[attr-defined]
                    input_one=part[0],
                    input_two=part[1],
                    input_three=part[2],
                    input_four=part[3],
                )
                if isinstance(result, UGenVector):
                    summed_sources.extend(result)
                else:
                    summed_sources.append(result)
            elif len(part) == 3:
                result = Sum3.new(  # type: ignore[attr-defined]
                    input_one=part[0],
                    input_two=part[1],
                    input_three=part[2],
                )
                if isinstance(result, UGenVector):
                    summed_sources.extend(result)
                else:
                    summed_sources.append(result)
            elif len(part) == 2:
                summed_sources.append(part[0] + part[1])
            else:
                summed_sources.append(part[0])
        if len(summed_sources) == 1:
            return summed_sources[0]
        return Mix.new(summed_sources)

    @classmethod
    def multichannel(
        cls,
        sources: UGenRecursiveInput | Sequence[UGenRecursiveInput],
        channel_count: int,
    ) -> UGenVector:
        flat = _flatten(sources, terminal_types=UGenScalar)  # type: ignore[arg-type]
        parts: list[list[Any]] = []
        for i in range(0, len(flat), channel_count):
            parts.append(flat[i : i + channel_count])
        mixes: list[UGenOperable] = []
        for columns in zip(*parts):
            mixes.append(cls.new(list(columns)))
        return UGenVector(*mixes)


def _get_method_for_rate(cls: type[UGen], calculation_rate: CalculationRate) -> Any:
    """Get the constructor method matching the calculation rate."""
    if calculation_rate == CalculationRate.AUDIO:
        return cls.ar  # type: ignore[attr-defined]
    elif calculation_rate == CalculationRate.CONTROL:
        return cls.kr  # type: ignore[attr-defined]
    elif calculation_rate == CalculationRate.SCALAR:
        return cls.ir  # type: ignore[attr-defined]
    return cls.new  # type: ignore[attr-defined]
