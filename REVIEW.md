# Code Review: nanosynth

Review of architecture, API surface, code quality, and improvement opportunities. Organized from low-hanging fruit to deeper architectural changes.

---

## Summary Assessment

This is a well-engineered project. The core graph system is solid, the type safety is genuine (not cosmetic), the build system handles a genuinely hard problem (vendoring and cross-platform compiling SC + libsndfile + PortAudio), and the test suite is thorough at the unit level. The critique below is relative to a high baseline.

---

## 1. Low-Hanging Fruit

### 1.1 Missing `BinaryOperator` / `UnaryOperator` entries

`BinaryOperator` only defines 7 of SuperCollider's ~30 binary operators. `UnaryOperator` only defines 2 of ~30. This means users cannot express `pow`, `min`, `max`, `round`, `trunc`, `atan2`, `hypot`, `bitAnd`, `bitOr`, `lcm`, `gcd`, `amclip`, `scaleneg`, `clip2`, `wrap2`, `fold2`, `excess`, `ring1`-`ring4`, `sumsqr`, `difsqr`, `sqrsum`, `sqrdif`, `absdif`, `thresh`, or unary ops like `reciprocal`, `sqrt`, `exp`, `log`, `log2`, `log10`, `sin`, `cos`, `tan`, `tanh`, `midicps`, `cpsmidi`, `midiratio`, `ratiomidi`, `dbamp`, `ampdb`, `distort`, `softclip`, `squared`, `cubed`, `sign`, `frac`, `ceil`, `floor`, etc.

This is probably the single biggest usability gap. Anyone doing non-trivial synthesis will hit the wall of `SinOsc.ar(frequency=440).midicps()` not existing, or not being able to write `sig.clip2(1.0)` or `freq.pow(2)`.

**Fix**: Extend both enums to cover SC's full operator set, and add corresponding dunder methods / named methods to `UGenOperable`. For example:

```python
class UGenOperable:
    def midicps(self) -> UGenOperable: ...
    def clip2(self, b) -> UGenOperable: ...
    def pow(self, b) -> UGenOperable: ...  # __pow__ / __rpow__
    def max(self, b) -> UGenOperable: ...
    def min(self, b) -> UGenOperable: ...
    def round(self, b) -> UGenOperable: ...
    def sqrt(self) -> UGenOperable: ...
    def log(self) -> UGenOperable: ...
    def exp(self) -> UGenOperable: ...
    def tanh(self) -> UGenOperable: ...
    # ...etc
```

Priority: **high**. Effort: **low-medium** (mechanical expansion, all follow the same pattern).

### 1.2 `Server.send_msg` is fire-and-forget with no reply handling

Every `send_msg` call is one-way. There is no mechanism to receive `/done`, `/fail`, or `/n_go` replies. This means:

- `send_synthdef` has no way to know if the SynthDef was accepted or rejected
- `synth` has no way to know if the synth was actually created
- No way to query server state (`/status`, `/g_queryTree`, `/b_query`)

**Fix (incremental)**:
1. Add a reply listener thread that reads the UDP socket
2. Add `query_status() -> dict` and `query_tree() -> dict`
3. Make `send_synthdef` optionally wait for `/done`
4. Expose a `subscribe(address, callback)` mechanism for async replies

This does not require the full async protocol from the TODO -- a simple reader thread + `threading.Event` for sync replies would suffice.

Priority: **high**. Effort: **medium**.

### 1.3 No buffer management

There is no API for allocating, reading, writing, or freeing buffers. This is required for any sample-based synthesis (PlayBuf, BufRd, GrainBuf, FFT, Warp1, convolution, etc.). The UGens exist but are unusable from the high-level API.

**Fix**: Add buffer methods to `Server`:

```python
def alloc_buffer(self, frames: int, channels: int = 1) -> int: ...
def read_buffer(self, buf_num: int, path: str, ...) -> None: ...
def free_buffer(self, buf_num: int) -> None: ...
```

Plus a buffer ID allocator (like `_node_id_counter`).

Priority: **high**. Effort: **low**.

### 1.4 No `AddAction` enum

The `action` parameter on `synth()` and `group()` accepts raw ints (0-4). This is opaque. SuperCollider defines `addToHead`, `addToTail`, `addBefore`, `addAfter`, `addReplace`.

**Fix**: Add an `AddAction` IntEnum and accept it in the API. Keep raw int support for backwards compat.

Priority: **low**. Effort: **trivial**.

### 1.5 `ConstantProxy.__eq__` breaks the `__eq__` contract

`ConstantProxy.__eq__` returns `True` for `ConstantProxy(1.0) == 1.0`, which is fine, but it also means `ConstantProxy(1.0) == True` since `float(True) == 1.0`. More importantly, `UGenOperable.__gt__` and `__lt__` return `UGenOperable` objects (which are truthy), not booleans. This means `if sig > 0:` silently always takes the truthy branch rather than doing a comparison. This is a common footgun in DSP DSLs.

**Mitigation**: Document this clearly. Alternatively, add a `__bool__` on `UGenOperable` that raises `TypeError("Cannot use UGen expressions in boolean context; use .gt() / .lt() for signal-rate comparison")`. Python's data model does not allow `__gt__` to return non-bool for use in `if` statements, but a `__bool__` trap catches the most common mistake.

Priority: **medium**. Effort: **trivial**.

### 1.6 `server.py:70` calls `_shutdown()` directly

`Server.quit()` reaches into `self._protocol._shutdown()`, a private method. This couples `Server` to `EmbeddedProcessProtocol` internals.

**Fix**: `EmbeddedProcessProtocol.quit()` should handle the full shutdown sequence, or expose a public `shutdown()` method. The Server should just call `self._protocol.quit()`.

Priority: **low**. Effort: **trivial**.

### 1.7 Thread-local initialization is fragile

`synthdef.py:654`: `_local._active_builders = []` executes at module load time, but only initializes the main thread's storage. The `SynthDefBuilder.__init__` and `__enter__` methods both have `if not hasattr(_local, "_active_builders")` guards, but `UGen.__init__` at line 733 has a different guard pattern: `if hasattr(_local, "_active_builders") and _local._active_builders:`. If a UGen is constructed in a thread that never created a builder, this works correctly (skips registration). But the inconsistency in guard patterns across the module is a maintenance risk.

**Fix**: Centralize the guard into a single function: `def _get_active_builders() -> list[SynthDefBuilder]`.

Priority: **low**. Effort: **trivial**.

---

## 2. API Design Improvements

### 2.1 `SynthDefBuilder` kwarg API is limited for parameter metadata

Currently, `SynthDefBuilder(frequency=440.0)` creates a control-rate parameter with no lag. To specify rate or lag, you must pass a `Parameter` object:

```python
SynthDefBuilder(frequency=Parameter(value=440.0, rate=ParameterRate.AUDIO, lag=0.1))
```

This is verbose. The `@synthdef` decorator solves this with positional rate/lag specs, but the builder API (which is the primary API per the README) has no ergonomic equivalent.

**Alternative**: Allow tuple syntax in kwargs:

```python
SynthDefBuilder(
    frequency=440.0,                      # control-rate, no lag
    amplitude=("kr", 0.3, 0.1),           # control-rate, default 0.3, lag 0.1
    bus=("ir", 0),                        # scalar-rate
)
```

Or, a `param()` function that returns a `Parameter`:

```python
SynthDefBuilder(
    frequency=440.0,
    amplitude=param(0.3, rate="kr", lag=0.1),
)
```

Wait -- `param()` already exists but returns a `Param` (for the `@ugen` decorator), not a `Parameter`. This naming collision is confusing.

**Suggestion**: Rename the `@ugen` decorator's `Param` to `UGenParam` or `ParamSpec` internally, and let `param()` in the public API be the user-facing builder helper. Or add a separate `synth_param()` / `control()` function for the builder context.

Priority: **medium**. Effort: **low**.

### 2.2 Flat namespace pollution

`__init__.py` does `from .ugens import *`, exporting 290+ names into the top-level `nanosynth` namespace. This makes tab-completion noisy and risks name collisions. The README examples already use `from nanosynth.ugens import SinOsc, Out, Pan2`, suggesting the intended import pattern is qualified.

**Counter-argument**: Flat namespace is convenient for REPL/notebook use, which is a common audio synthesis workflow.

**Suggestion**: Keep the star import but consider whether it's worth the tradeoff. At minimum, document the recommended import pattern prominently. An alternative: only export the most common UGens (say, top 30) at the top level, and keep the rest in `nanosynth.ugens`.

Priority: **low** (mostly a taste question). Effort: **trivial**.

### 2.3 `Server.synth()` returns an int, not a Synth object

Returning a raw node ID means there's no way to do `node.set(frequency=880)` -- you must do `server.set(node_id, frequency=880)`. This is workable but less Pythonic than returning a lightweight `Synth` proxy.

```python
class Synth:
    def __init__(self, server: Server, node_id: int, name: str): ...
    def set(self, **params: float) -> None: ...
    def free(self) -> None: ...
    def __enter__(self) -> Synth: ...
    def __exit__(self, ...): self.free()
```

This composes better with context managers and method chaining.

Priority: **medium**. Effort: **low**.

---

## 3. Testing Gaps

### 3.1 No negative / adversarial tests for the compiler

The test suite validates that correct graphs compile correctly, but doesn't test:

- Graphs with cycles (should be caught by topological sort)
- Extremely deep UGen chains (stack overflow in recursive expansion?)
- Graphs with thousands of UGens (performance regression)
- Invalid SCgf bytes consumed by a real scsynth (round-trip validation)
- Empty UGen names, very long names, names with special characters

Priority: **medium**. Effort: **low**.

### 3.2 No concurrency tests

The `SynthDefBuilder` uses thread-local storage and UUID-based scope isolation. There are no tests verifying that two threads can build SynthDefs concurrently without interference.

Priority: **medium**. Effort: **low**.

### 3.3 No property-based tests

The UGen system has clear algebraic properties that are ripe for property-based testing (hypothesis):

- `sig + 0 == sig` (identity optimization)
- `sig * 1 == sig`
- `compile(a + b)` should produce the same bytes regardless of Python object identity
- Multichannel expansion: `SinOsc.ar(frequency=[440, 880])` should produce 2 UGens
- Topological sort is deterministic across runs

Priority: **low**. Effort: **medium**.

---

## 4. Deeper Architectural Opportunities

### 4.1 Bidirectional OSC / reply handling (prerequisite for many features)

This is the most impactful architectural change. Currently the system is write-only (Python -> scsynth). Many useful features require reading replies:

- **Status monitoring**: CPU load, peak CPU, UGen count, synth count, group count
- **Node notifications**: `/n_go`, `/n_end`, `/n_off`, `/n_on`, `/n_move`, `/n_info`
- **Buffer queries**: `/b_info` replies
- **Trigger callbacks**: `/tr` messages from `SendTrig` / `SendReply` UGens
- **Error handling**: `/fail` messages from the server

**Architecture sketch**:

```python
class Server:
    def __init__(self):
        self._reply_port = find_free_port()
        self._reply_socket = socket.socket(AF_INET, SOCK_DGRAM)
        self._reply_thread = threading.Thread(target=self._reply_loop, daemon=True)
        self._pending: dict[str, threading.Event] = {}
        self._subscribers: dict[str, list[Callable]] = {}

    def _reply_loop(self):
        while self._running:
            data, addr = self._reply_socket.recvfrom(65536)
            msg = OscMessage.from_datagram(data)
            # dispatch to pending futures and subscribers

    def on(self, address: str, callback: Callable) -> None: ...
    def wait(self, address: str, timeout: float = 5.0) -> OscMessage: ...
```

This unlocks: buffer management with confirmation, node lifecycle tracking, real-time meter data, trigger-based sequencing from Python, and proper error reporting.

Priority: **high**. Effort: **high**.

### 4.2 Non-realtime rendering (NRT)

SuperCollider supports offline rendering via NRT mode -- process an OSC score file and render to a sound file without real-time constraints. This is valuable for:

- Deterministic, reproducible audio output
- Rendering longer-than-realtime pieces
- CI testing (no audio hardware needed)
- Batch processing

The embedded libscsynth already supports this via `World_NonRealTimeSynthesis`. The C++ binding would need a new function, and the Python side would need an `nrt_render(score, output_path, ...)` API.

**Architecture sketch**:

```python
class Score:
    """A timed sequence of OSC bundles for offline rendering."""
    def add(self, time: float, msg: OscMessage) -> None: ...
    def render(self, path: str, duration: float, sample_rate: int = 44100, ...) -> None: ...
```

Priority: **high** (unlocks testability and batch use cases). Effort: **medium-high**.

### 4.3 SynthDef decompiler / graph introspection

`dump_ugens()` produces a string representation, but there's no structured graph introspection API. Users cannot programmatically:

- Walk the UGen graph
- Query input sources for a given UGen
- Compute signal flow paths
- Visualize the graph (e.g., export to DOT/Graphviz)

**Fix**: Add a `SynthDef.graph()` method returning a lightweight DAG structure:

```python
@dataclass
class UGenNode:
    index: int
    ugen: UGen
    inputs: list[tuple[UGenNode, int] | float]  # (source_node, output_index) or constant
    outputs: list[list[UGenNode]]  # consumers per output

def graph(self) -> list[UGenNode]: ...
def to_dot(self) -> str: ...  # Graphviz DOT format
```

Priority: **medium**. Effort: **low-medium**.

### 4.4 Replace `exec()`-based code generation

This is already in TODO.md. The current `_create_fn` / `_add_init` / `_add_rate_fn` machinery generates Python source as strings and `exec()`s them. This works (it's the same approach as `dataclasses`) but has real costs:

- Generated methods don't appear in source for debugging
- Stack traces show `<string>` instead of real file locations
- Static analysis tools can't see the generated signatures
- The code generation logic in `_add_init` is hard to follow (string template assembly)

**Alternative: `__init_subclass__` + closures**. Rather than generating source code, build closures directly:

```python
def _make_init(params, ...):
    def __init__(self, *, calculation_rate, **kwargs):
        # real Python function, debuggable, inspectable
        ...
    return __init__
```

The tradeoff is that you lose the nice `inspect.signature()` that `exec`-based generation provides (since the generated function has the actual parameter names in its signature). You could recover this with `__signature__` overrides.

Priority: **low** (current approach works). Effort: **medium**.

### 4.5 Lazy / deferred graph compilation

Currently, `SynthDefBuilder.build()` deep-copies the entire UGen list, sorts, optimizes, and compiles eagerly. For interactive use (REPL, live coding), it would be useful to have a lazy mode where the SynthDef is only compiled when first needed (e.g., on `send()` or `compile()`).

This is a minor point -- `build()` is fast -- but worth noting for live-coding scenarios where you want to define many SynthDefs and only compile the ones you actually use.

Priority: **low**. Effort: **low**.

---

## 5. Code Quality Observations

### 5.1 `synthdef.py` is 1613 lines

This file contains: type aliases, the `@ugen` decorator system, `UGenOperable`, `UGenScalar`, `OutputProxy`, `ConstantProxy`, `UGenVector`, `UGen`, `UnaryOpUGen`, `BinaryOpUGen`, `Parameter`, `Control`, `LagControl`, `TrigControl`, `AudioControl`, `SynthDef`, `SynthDefBuilder`, and the `@synthdef` decorator. It's the god module.

**Suggestion**: Split into:
- `types.py` -- type aliases, `UGenOperable`, `UGenScalar`, `OutputProxy`, `ConstantProxy`, `UGenVector`
- `ugen.py` -- `UGen` base class, `@ugen` decorator, `param()`
- `operators.py` -- `UnaryOpUGen`, `BinaryOpUGen`, operator computation helpers
- `parameters.py` -- `Parameter`, `Control`, `LagControl`, `TrigControl`, `AudioControl`
- `synthdef.py` -- `SynthDef`, `SynthDefBuilder`, `@synthdef`

Counter-argument: circular imports between these modules are likely (e.g., `UGen` references `SynthDefBuilder` and vice versa). The current monolithic structure avoids that. Whether the split is worth the import gymnastics is debatable.

Priority: **low**. Effort: **medium** (refactoring risk).

### 5.2 `_initiate_topological_sort` has a subtle bug-risk

Line 1416:
```python
sort_bundle.descendants[:] = sorted(
    sort_bundles[ugen].descendants,
    key=lambda x: ugens.index(ugen),  # <-- always sorts by same key
)
```

The `key` lambda captures `ugen` from the outer loop, but uses `ugens.index(ugen)` which is the *same value* for every element in the sort. This means the sort is a no-op (stable sort with identical keys preserves order). If the intent was to sort descendants by their position in the original `ugens` list, it should be `key=lambda x: ugens.index(x)`.

If this is intentional (i.e., "don't reorder, just copy"), the `sorted()` call is misleading. If it's a bug, it means descendant ordering is accidentally correct only because insertion order happens to match.

Priority: **medium** (potential correctness issue). Effort: **trivial**.

### 5.3 `SynthDef.send()` and `play()` accept `server: "Any"`

These methods type their `server` parameter as `Any` to avoid a circular import with `server.py`. This defeats type checking at the call site. A `Protocol` would preserve type safety:

```python
class ServerProtocol(Protocol):
    def send_synthdef(self, synthdef: SynthDef) -> None: ...
    def synth(self, name: str, target: int = ..., action: int = ..., **params: float) -> int: ...
```

Priority: **low**. Effort: **trivial**.

### 5.4 No `__all__` in `ugens/__init__.py`?

The ugens package exports 290+ names. Verifying that `from nanosynth.ugens import *` picks up exactly the right set depends on the `__init__.py` import structure. If there's no explicit `__all__`, any helper function or import in any ugen module could leak. Worth verifying.

Priority: **low**. Effort: **trivial**.

---

## 6. Documentation

### 6.1 No API reference docs

The README is good as a tutorial / quick-start, but there's no generated API reference. For 290+ UGens, each with their own parameter signatures, this is a significant gap. Users currently have to read source code or use `help()` in the REPL.

**Fix**: Set up pdoc, mkdocstrings, or sphinx-autodoc. The auto-generated docstrings from `@ugen` (showing rate tokens and parameter defaults) are a good starting point.

Priority: **medium**. Effort: **low-medium**.

### 6.2 No "Concepts" documentation

The project has several non-obvious concepts that aren't documented anywhere:

- Multichannel expansion (what happens when you pass a list as a parameter)
- Calculation rates (SCALAR vs CONTROL vs AUDIO vs DEMAND) and when each matters
- The scope system (why cross-builder wiring fails)
- The parameter rate system (CONTROL vs TRIGGER vs AUDIO vs SCALAR parameters)
- The `unexpanded` parameter flag
- How `is_width_first` works and why it matters
- The optimization pass (dead code elimination)
- The `Default` sentinel and when to use it

Priority: **medium**. Effort: **medium**.

---

## 7. Feature Gaps (relative to SuperCollider's sclang)

For completeness, here are SC features that nanosynth does not yet expose. These are not necessarily all worth implementing, but they represent the gap between "compile SynthDefs" and "replace sclang for synthesis work":

| Feature | SC equivalent | Difficulty |
|---------|--------------|------------|
| Buffer management | `Buffer.read`, `Buffer.alloc` | Low |
| Bus allocation | `Bus.audio`, `Bus.control` | Low |
| Node ordering / groups | `Group`, `ParGroup` | Low |
| Patterns / sequencing | `Pbind`, `Pseq`, `Prand` | High |
| MIDI input | `MIDIFunc`, `MIDIIn` | Medium |
| Recording | `Server.record` | Low |
| Scope / metering | `Stethoscope`, `ServerMeter` | High |
| SynthDef variants | `SynthDef.variants` | Low |
| Node proxies / live coding | `NodeProxy`, `Ndef` | High |
| Routing / send effects | `Out.ar` to buses | Already works |
| NRT rendering | `Score.recordNRT` | Medium |

The first three (buffers, buses, node ordering) are straightforward OSC wrappers and would make the library significantly more useful for real synthesis work. Patterns/sequencing is a large design space that may be better served by a separate package.

---

## 8. Prioritized Recommendations

**Do first** (high impact, low-medium effort):
1. Extend `BinaryOperator` / `UnaryOperator` and add methods to `UGenOperable`
2. Add buffer management to `Server`
3. Add reply handling (at minimum: `/done` waiting for `send_synthdef`)

**Do next** (medium impact, low effort):
4. Add `Synth` / `Group` proxy objects returned from `server.synth()` / `server.group()`
5. Add `AddAction` enum
6. Fix the `_initiate_topological_sort` key lambda (5.2)
7. Add `__bool__` trap to `UGenOperable` (1.5)

**Consider** (high effort or lower priority):
8. Bidirectional OSC / full reply handling
9. NRT rendering support
10. API reference docs generation
11. Split `synthdef.py` into smaller modules
12. `__init_subclass__` refactor of code generation
