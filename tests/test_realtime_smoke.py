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
import sys

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


def test_status_query(booted: Server) -> None:
    st = booted.status(timeout=5.0)
    assert st.actual_sample_rate > 0
    assert st.num_groups >= 1  # at least the default group exists
    assert st.num_synths == 0


def test_version_query(booted: Server) -> None:
    v = booted.version(timeout=5.0)
    assert v.program in ("scsynth", "supernova")
    assert v.major >= 3


def test_query_tree_and_reset(booted: Server) -> None:
    tree = booted.query_tree(0, timeout=5.0)
    assert tree.node_id == 0 and tree.is_group
    # The default group (node 1) should be a child of the root.
    assert any(child.node_id == 1 for child in tree.children)
    booted.reset()
    booted.sync(timeout=5.0)
    assert booted.status(timeout=5.0).num_synths == 0


def test_node_free_notification(booted: Server) -> None:
    from nanosynth import SynthDefBuilder
    from nanosynth.enums import DoneAction
    from nanosynth.envelopes import EnvGen, Envelope
    from nanosynth.ugens import Out, SinOsc

    with SynthDefBuilder(freq=440.0) as b:
        env = EnvGen.kr(
            envelope=Envelope.percussive(attack_time=0.01, release_time=0.1),
            done_action=DoneAction.FREE_SYNTH,
        )
        Out.ar(bus=0, source=SinOsc.ar(frequency=b["freq"]) * env * 0.0)  # silent
    b.build(name="smoke_ping").send(booted)
    booted.sync(timeout=5.0)

    booted.enable_notifications()
    node = booted.synth("smoke_ping", freq=440.0)
    # The self-freeing envelope should fire /n_end within the release window.
    assert node.wait_free(timeout=3.0) is True


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


# ---------------------------------------------------------------------------
# GIL/mutex lock-order regression
# ---------------------------------------------------------------------------

# Drives outgoing packets and incoming replies concurrently -- the interleaving
# that used to deadlock the process. python_reply_func took the reply mutex and
# then blocked on the GIL, while world_send_packet held the GIL and blocked on
# that same mutex. Both callbacks now take the GIL first.
#
# Run in a subprocess so a regression shows up as a timeout rather than wedging
# the whole pytest session: once the GIL is deadlocked, nothing in-process can
# recover, including pytest's own timeout handling.
_STRESS_SOURCE = """
import faulthandler, sys, threading, time
from nanosynth import Options, Server
from nanosynth.enums import DoneAction
from nanosynth.envelopes import EnvGen, Envelope
from nanosynth.synthdef import SynthDefBuilder
from nanosynth.ugens import Out, SinOsc

with SynthDefBuilder(freq=440.0, amp=0.0, gate=1.0) as builder:
    env = EnvGen.kr(
        envelope=Envelope.asr(attack_time=0.01, release_time=0.05),
        gate=builder["gate"],
        done_action=DoneAction.FREE_SYNTH,
    )
    Out.ar(bus=0, source=SinOsc.ar(frequency=builder["freq"]) * env * builder["amp"])
stress = builder.build(name="stress")

stop = threading.Event()

def sender(server, index):
    count = 0
    while not stop.is_set():
        count += 1
        try:
            if count % 2:
                with server.at(time.time() + 0.02):
                    node = server.synth("stress", freq=200.0 + index, amp=0.0)
                with server.at(time.time() + 0.05):
                    server.set(node, gate=0.0)
            else:
                server.free(server.synth("stress", freq=300.0 + index, amp=0.0))
        except Exception:
            pass
        time.sleep(0.002)

def replier(server):
    while not stop.is_set():
        try:
            server.status(timeout=2.0)
            server.sync(timeout=2.0)
        except Exception:
            pass

server = Server(Options(verbosity=-1))
server.boot()
try:
    server.send_synthdef(stress)
    server.sync(timeout=5.0)
    server.enable_notifications()   # /n_go + /n_end multiply the reply traffic
    seen = [0]
    server.on_node(lambda ev: seen.__setitem__(0, seen[0] + 1))

    # Fires from a C thread, so it still works when every Python thread is
    # stuck waiting for the GIL.
    faulthandler.dump_traceback_later(20, exit=True)

    threads = [threading.Thread(target=sender, args=(server, i), daemon=True)
               for i in range(6)]
    threads += [threading.Thread(target=replier, args=(server,), daemon=True)
                for _ in range(4)]
    for t in threads:
        t.start()
    time.sleep(8.0)
    stop.set()
    for t in threads:
        t.join(timeout=5.0)
    faulthandler.cancel_dump_traceback_later()
    # A deadlock starves the reply path first, so require replies actually flowed.
    assert seen[0] > 100, "no node events -- reply path stalled"
    print("OK", seen[0])
finally:
    stop.set()
    server.quit()
"""


def test_concurrent_send_and_reply_does_not_deadlock(protocol_cls) -> None:
    """Sends and replies in flight together must not deadlock on the GIL."""
    import subprocess

    if protocol_cls is not EmbeddedProcessProtocol:
        pytest.skip("scsynth-only stress; supernova has its own reply endpoint")

    result = subprocess.run(
        [sys.executable, "-c", _STRESS_SOURCE],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, (
        f"stress subprocess failed (deadlock?):\n{result.stdout[-2000:]}\n"
        f"{result.stderr[-4000:]}"
    )
    assert "OK" in result.stdout
