"""Realtime smoke tests against a genuinely booted engine.

Unlike the rest of the suite (which mocks the protocol or renders offline via
NRT), these boot a real in-process World, exercise the live OSC round-trip
(/sync -> /synced), the reclaiming allocators, and a clean quit.

These are opt-in for two reasons: real audio boot can hang or fail on a
headless machine with no audio device, and scsynth and supernova share
process-global libscsynth state so they cannot both be booted in one process.
Select an engine with the ``NANOSYNTH_TEST_REALTIME`` environment variable:

    NANOSYNTH_TEST_REALTIME=scsynth   pytest tests/test_realtime_smoke.py
    NANOSYNTH_TEST_REALTIME=supernova pytest tests/test_realtime_smoke.py

(``=1`` is an alias for ``scsynth``.) Run each in its own process/CI job; do
not select both at once.

IMPORTANT -- run this file on its OWN, not as part of the full suite. The NRT
integration tests create scsynth Worlds, which claims the scsynth engine for
the whole process; the cross-engine guard then (correctly) rejects a later
``supernova`` boot with ``ServerCannotBoot``. So ``NANOSYNTH_TEST_REALTIME=
supernova pytest tests/`` (the whole suite) makes the supernova cases error.
``=scsynth`` is full-suite-safe (same engine kind), but invoking just this file
per engine is the supported pattern. The guard turns what used to be a segfault
into a clean error, but the one-engine-per-process rule still stands.
"""

import os

import pytest

from nanosynth import EmbeddedSupernovaProtocol, Options, Server
from nanosynth.scsynth import EmbeddedProcessProtocol

_MODE = os.environ.get("NANOSYNTH_TEST_REALTIME", "")
_ALLOWED = {
    "1": {"scsynth"},
    "scsynth": {"scsynth"},
    "supernova": {"supernova"},
}.get(_MODE, set())


@pytest.fixture(
    params=[
        pytest.param(EmbeddedProcessProtocol, id="scsynth"),
        pytest.param(EmbeddedSupernovaProtocol, id="supernova"),
    ]
)
def protocol_cls(request):
    cls = request.param
    name = "supernova" if cls is EmbeddedSupernovaProtocol else "scsynth"
    if name not in _ALLOWED:
        pytest.skip(f"set NANOSYNTH_TEST_REALTIME={name} to run this engine")
    return cls


@pytest.fixture()
def booted(protocol_cls):
    server = Server(Options(verbosity=-1), protocol=protocol_cls())
    server.boot()
    try:
        yield server
    finally:
        if server.is_running:
            server.quit()


def test_boot_and_quit_lifecycle(protocol_cls) -> None:
    server = Server(Options(verbosity=-1), protocol=protocol_cls())
    assert server.is_running is False
    server.boot()
    assert server.is_running is True
    server.quit()
    assert server.is_running is False


def test_reboot_in_same_process(protocol_cls) -> None:
    server = Server(Options(verbosity=-1), protocol=protocol_cls())
    server.boot()
    server.quit()
    server.boot()  # the global active-world flag must have been cleared
    assert server.is_running is True
    server.quit()


def test_sync_round_trip(booted: Server) -> None:
    # The live engine must acknowledge /sync with /synced.
    assert booted.sync(timeout=5.0) is True


def test_buffer_alloc_free_reclaim(booted: Server) -> None:
    b1 = booted.alloc_buffer(1024)
    booted.sync(timeout=5.0)
    booted.free_buffer(b1)
    booted.sync(timeout=5.0)
    b2 = booted.alloc_buffer(1024)
    assert b2 == b1  # freed id is reclaimed by the allocator


def test_node_id_allocation(booted: Server) -> None:
    a = booted.next_node_id()
    b = booted.next_node_id()
    assert b == a + 1


def test_double_quit_is_safe(booted: Server) -> None:
    booted.quit()
    booted.quit()  # second quit is a no-op, must not raise
    assert booted.is_running is False


def test_buffer_data_round_trip(booted: Server) -> None:
    import numpy as np

    from nanosynth.exceptions import EngineError
    from nanosynth.scsynth import EmbeddedProcessProtocol

    if not isinstance(booted._protocol, EmbeddedProcessProtocol):
        # Direct buffer access is scsynth-only; supernova must reject cleanly.
        with pytest.raises(EngineError):
            booted.get_buffer_data(0)
        return

    data = np.random.randn(512, 2).astype(np.float32)
    buffer_id = booted.alloc_buffer_from_array(data)
    frames, channels, sample_rate = booted.buffer_info(buffer_id)
    assert (frames, channels) == (512, 2)
    assert sample_rate > 0
    out = booted.get_buffer_data(buffer_id)
    assert out.shape == (512, 2)
    assert out.dtype == np.float32
    assert np.array_equal(out, data)  # exact byte-for-byte round-trip
    booted.free_buffer(buffer_id)
