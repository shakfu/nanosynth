"""Property-based tests (hypothesis) for the SynthDef graph frontend.

These exercise invariants that example-based tests under-sample: algebraic
identity laws for the arithmetic operators, constant folding equivalence with
Python floats, multichannel expansion arity, and determinism of graph
compilation (which subsumes topological-sort determinism).
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from nanosynth.synthdef import (
    ConstantProxy,
    OutputProxy,
    SynthDef,
    SynthDefBuilder,
    UGenVector,
)
from nanosynth.ugens import Out, Saw, SinOsc, WhiteNoise

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Finite, audio-range frequencies. Bounded well below overflow so that
# constant folding of products stays exact. allow_subnormal=False because the
# scsynth C extension is built with -ffast-math, which flips the CPU into
# flush-to-zero mode process-wide; hypothesis otherwise refuses to build a
# floats() strategy that could emit unrepresentable subnormals.
frequencies = st.floats(
    min_value=20.0,
    max_value=20000.0,
    allow_nan=False,
    allow_infinity=False,
    allow_subnormal=False,
)

# A leaf recipe names a source UGen and a frequency (ignored by WhiteNoise).
leaf_recipes = st.builds(
    lambda source, freq: ("leaf", source, freq),
    st.sampled_from(["sin", "saw", "noise"]),
    frequencies,
)

# A full recipe is a tree of binary ops over leaves. Kept as plain data so the
# same recipe can be rebuilt in independent builders to check determinism.
signal_recipes = st.recursive(
    leaf_recipes,
    lambda children: st.builds(
        lambda op, left, right: ("op", op, left, right),
        st.sampled_from(["+", "-", "*"]),
        children,
        children,
    ),
    max_leaves=8,
)


def _build_signal(recipe: tuple[Any, ...]) -> Any:
    """Materialize a recipe into a single-channel signal inside an active builder."""
    if recipe[0] == "leaf":
        _, source, freq = recipe
        if source == "sin":
            return SinOsc.ar(frequency=freq)
        if source == "saw":
            return Saw.ar(frequency=freq)
        return WhiteNoise.ar()
    _, op, left_recipe, right_recipe = recipe
    left = _build_signal(left_recipe)
    right = _build_signal(right_recipe)
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    return left * right


def _compile_recipe(recipe: tuple[Any, ...]) -> SynthDef:
    with SynthDefBuilder() as builder:
        Out.ar(bus=0, source=_build_signal(recipe))
    return builder.build(name="prop")


# ---------------------------------------------------------------------------
# Algebraic identity laws
# ---------------------------------------------------------------------------


@given(leaf_recipes)
def test_additive_identity(leaf: tuple[Any, ...]) -> None:
    """Adding/subtracting zero returns the original signal, no UGen emitted."""
    with SynthDefBuilder():
        sig = _build_signal(leaf)
        assert isinstance(sig, OutputProxy)
        assert (sig + 0) is sig
        assert (0 + sig) is sig
        assert (sig - 0) is sig


@given(leaf_recipes)
def test_multiplicative_identity(leaf: tuple[Any, ...]) -> None:
    """Multiplying/dividing by one and raising to the first power are no-ops."""
    with SynthDefBuilder():
        sig = _build_signal(leaf)
        assert (sig * 1) is sig
        assert (1 * sig) is sig
        assert (sig / 1) is sig
        assert (sig**1) is sig


@given(leaf_recipes)
def test_multiplicative_zero(leaf: tuple[Any, ...]) -> None:
    """Multiplying a signal by zero folds to the constant 0."""
    with SynthDefBuilder():
        sig = _build_signal(leaf)
        for zero in (sig * 0, 0 * sig):
            assert isinstance(zero, ConstantProxy)
            assert float(zero) == 0.0


@given(leaf_recipes)
def test_power_zero_is_one(leaf: tuple[Any, ...]) -> None:
    """A signal raised to the zeroth power folds to the constant 1."""
    with SynthDefBuilder():
        sig = _build_signal(leaf)
        result = sig**0
        assert isinstance(result, ConstantProxy)
        assert float(result) == 1.0


# ---------------------------------------------------------------------------
# Constant folding
# ---------------------------------------------------------------------------

constants = st.floats(
    min_value=-1.0e6,
    max_value=1.0e6,
    allow_nan=False,
    allow_infinity=False,
    allow_subnormal=False,  # see the note on `frequencies` above (-ffast-math)
)


@given(constants, constants)
def test_constant_folding_matches_python(a: float, b: float) -> None:
    """Arithmetic on two constants folds to the same value Python computes."""
    assert float(ConstantProxy(a) + b) == a + b
    assert float(ConstantProxy(a) - b) == a - b
    assert float(ConstantProxy(a) * b) == a * b


# ---------------------------------------------------------------------------
# Multichannel expansion
# ---------------------------------------------------------------------------


@given(st.integers(min_value=2, max_value=16))
def test_expansion_arity(n: int) -> None:
    """A list of n frequencies expands to a UGenVector of exactly n channels."""
    with SynthDefBuilder():
        freqs = [100.0 * (i + 1) for i in range(n)]
        vector = SinOsc.ar(frequency=freqs)
        assert isinstance(vector, UGenVector)
        assert len(vector) == n


@given(st.integers(min_value=2, max_value=16), st.integers(min_value=2, max_value=16))
def test_binary_expansion_takes_max_width(m: int, n: int) -> None:
    """Combining vectors of width m and n expands to max(m, n) channels."""
    with SynthDefBuilder():
        left = SinOsc.ar(frequency=[100.0 * (i + 1) for i in range(m)])
        right = SinOsc.ar(frequency=[50.0 * (i + 1) for i in range(n)])
        result = left * right
        assert isinstance(result, UGenVector)
        assert len(result) == max(m, n)


# ---------------------------------------------------------------------------
# Compilation / topological-sort determinism
# ---------------------------------------------------------------------------


@given(signal_recipes)
@settings(deadline=None, max_examples=200)
def test_compile_is_deterministic(recipe: tuple[Any, ...]) -> None:
    """Compiling the same graph twice yields byte-identical SCgf output."""
    first = _compile_recipe(recipe)
    second = _compile_recipe(recipe)
    assert first.compile() == second.compile()


@given(signal_recipes)
@settings(deadline=None, max_examples=200)
def test_ugen_ordering_is_deterministic(recipe: tuple[Any, ...]) -> None:
    """The topologically sorted UGen sequence is stable across rebuilds."""
    first = _compile_recipe(recipe)
    second = _compile_recipe(recipe)
    types_first = [type(u).__name__ for u in first.ugens]
    types_second = [type(u).__name__ for u in second.ugens]
    assert types_first == types_second


@given(signal_recipes, st.sampled_from(["a", "name_2", "synth-def"]))
@settings(deadline=None, max_examples=100)
def test_name_does_not_affect_graph(recipe: tuple[Any, ...], name: str) -> None:
    """The compiled graph body is independent of the SynthDef name.

    Compiling with anonymous (content-hash) names must be identical regardless
    of the declared name, since the name is metadata, not part of the graph.
    """
    with SynthDefBuilder() as builder:
        Out.ar(bus=0, source=_build_signal(recipe))
    named = builder.build(name=name)

    with SynthDefBuilder() as builder:
        Out.ar(bus=0, source=_build_signal(recipe))
    anonymous = builder.build(name="different")

    assert named.compile(use_anonymous_name=True) == anonymous.compile(
        use_anonymous_name=True
    )
