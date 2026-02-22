"""Concurrency stress tests for SynthDefBuilder thread isolation and Server OSC dispatch.

Verifies that dozens of concurrent SynthDefBuilder.build() calls produce
correct, isolated results, and that Server reply handling is thread-safe
under contention.
"""

import threading
import time
from unittest.mock import MagicMock, PropertyMock


from nanosynth.scsynth import BootStatus
from nanosynth.server import Server
from nanosynth.exceptions import SynthDefError
from nanosynth.synthdef import SynthDefBuilder, _get_active_builders
from nanosynth.ugens import LPF, Out, SinOsc
from nanosynth.ugens.basic import Mix


# ---------------------------------------------------------------------------
# SynthDefBuilder thread isolation stress tests
# ---------------------------------------------------------------------------


class TestBuilderThreadIsolation:
    def test_many_threads_independent_builds(self):
        """50 threads building SynthDefs concurrently produce correct results."""
        results: dict[int, bytes] = {}
        errors: list[Exception] = []
        n_threads = 50

        def build_synthdef(thread_id: int) -> None:
            try:
                freq = 200.0 + thread_id * 10
                with SynthDefBuilder() as builder:
                    sig = SinOsc.ar(frequency=freq) * 0.1
                    Out.ar(bus=0, source=sig)
                sd = builder.build(name=f"thread_{thread_id}")
                results[thread_id] = sd.compile()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=build_synthdef, args=(i,)) for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errors in threads: {errors}"
        assert len(results) == n_threads
        # Each thread should produce unique bytes (different frequencies)
        unique_bytecodes = set(results.values())
        assert len(unique_bytecodes) == n_threads

    def test_active_builders_isolated_per_thread(self):
        """Each thread has its own empty builder stack."""
        stacks_seen: dict[int, int] = {}
        barrier = threading.Barrier(10)

        def check_stack(thread_id: int) -> None:
            # Enter a builder context in each thread
            with SynthDefBuilder():
                barrier.wait(timeout=5)
                # Each thread should see exactly 1 builder (its own)
                builders = _get_active_builders()
                stacks_seen[thread_id] = len(builders)

        threads = [threading.Thread(target=check_stack, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(stacks_seen) == 10
        for thread_id, count in stacks_seen.items():
            assert count == 1, f"Thread {thread_id} saw {count} builders, expected 1"

    def test_nested_builders_isolated_per_thread(self):
        """Nested builder contexts in separate threads don't leak."""
        stacks_seen: dict[int, int] = {}
        barrier = threading.Barrier(10)

        def nested_build(thread_id: int) -> None:
            with SynthDefBuilder():
                with SynthDefBuilder():
                    barrier.wait(timeout=5)
                    stacks_seen[thread_id] = len(_get_active_builders())

        threads = [threading.Thread(target=nested_build, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        for thread_id, count in stacks_seen.items():
            assert count == 2, f"Thread {thread_id} saw {count} builders, expected 2"

    def test_cross_thread_ugen_raises(self):
        """UGens from one thread's builder cannot be used in another thread's builder."""
        ugen_from_thread: list = []
        error_raised = threading.Event()

        def producer():
            with SynthDefBuilder():
                sig = SinOsc.ar()
                ugen_from_thread.append(sig)
                # Wait for consumer to try using our UGen
                time.sleep(0.2)

        def consumer():
            # Wait for producer to create a UGen
            time.sleep(0.05)
            try:
                with SynthDefBuilder():
                    Out.ar(bus=0, source=ugen_from_thread[0])
            except SynthDefError:
                error_raised.set()

        t1 = threading.Thread(target=producer)
        t2 = threading.Thread(target=consumer)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert error_raised.is_set(), "Expected SynthDefError for cross-thread UGen use"

    def test_concurrent_complex_graphs(self):
        """Concurrent builds of complex graphs (Mix, LPF, parameters) succeed."""
        results: dict[int, str] = {}
        errors: list[Exception] = []

        def build_complex(thread_id: int) -> None:
            try:
                with SynthDefBuilder(freq=440.0 + thread_id, amp=0.1) as builder:
                    sources = [
                        SinOsc.ar(frequency=builder["freq"] * float(i + 1))
                        for i in range(4)
                    ]
                    sig = Mix.new(sources) * builder["amp"]
                    sig = LPF.ar(source=sig, frequency=2000.0)
                    Out.ar(bus=0, source=sig)
                sd = builder.build(name=f"complex_{thread_id}")
                results[thread_id] = sd.effective_name
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=build_complex, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errors in threads: {errors}"
        assert len(results) == 30

    def test_deterministic_under_concurrency(self):
        """Same SynthDef built in parallel produces identical bytes each time."""
        all_bytes: list[bytes] = []
        lock = threading.Lock()

        def build_same() -> None:
            with SynthDefBuilder() as builder:
                Out.ar(bus=0, source=SinOsc.ar(frequency=440.0) * 0.3)
            sd = builder.build(name="deterministic")
            with lock:
                all_bytes.append(sd.compile())

        threads = [threading.Thread(target=build_same) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(all_bytes) == 20
        assert all(b == all_bytes[0] for b in all_bytes), (
            "Concurrent builds produced non-deterministic output"
        )


# ---------------------------------------------------------------------------
# Server reply dispatch stress tests
# ---------------------------------------------------------------------------


def _make_mock_server() -> Server:
    """Create a Server with a mocked protocol in ONLINE state."""
    protocol = MagicMock()
    type(protocol).status = PropertyMock(return_value=BootStatus.ONLINE)
    server = Server.__new__(Server)
    server._protocol = protocol
    server._options = MagicMock()
    type(server._options).output_bus_channel_count = PropertyMock(return_value=8)
    type(server._options).input_bus_channel_count = PropertyMock(return_value=8)
    type(server._options).audio_bus_channel_count = PropertyMock(return_value=1024)
    type(server._options).control_bus_channel_count = PropertyMock(return_value=16384)
    type(server._options).first_private_bus_id = PropertyMock(return_value=16)
    server._node_id_counter = 1000
    server._reply_handlers: dict = {}
    server._pending_replies: dict = {}
    server._reply_lock = threading.Lock()
    server._allocated_buffers: set = set()
    server._next_buffer_id = 0
    server._audio_bus_allocator_index = 16
    server._control_bus_allocator_index = 0
    server._is_recording = False
    return server


class TestServerConcurrentReplies:
    def test_many_concurrent_waiters(self):
        """20 threads waiting for different reply addresses all get resolved."""
        from nanosynth.osc import OscMessage

        server = _make_mock_server()
        results: dict[int, bool] = {}

        def waiter(thread_id: int) -> None:
            address = f"/done_{thread_id}"
            msg = server.wait_for_reply(address, timeout=5.0)
            results[thread_id] = msg is not None

        threads = [threading.Thread(target=waiter, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()

        # Give threads time to register their waiters
        time.sleep(0.05)

        # Dispatch replies for all addresses (as raw datagrams)
        for i in range(20):
            datagram = OscMessage(f"/done_{i}").to_datagram()
            server._dispatch_reply(datagram)

        for t in threads:
            t.join(timeout=10)

        assert len(results) == 20
        assert all(results.values()), "Some waiters did not receive replies"

    def test_concurrent_handler_registration(self):
        """Many threads registering/unregistering handlers concurrently without crash."""
        server = _make_mock_server()
        errors: list[Exception] = []

        def register_unregister(thread_id: int) -> None:
            try:

                def handler(msg):
                    pass

                for _ in range(50):
                    server.on(f"/addr_{thread_id}", handler)
                    server.off(f"/addr_{thread_id}", handler)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=register_unregister, args=(i,)) for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errors during concurrent handler registration: {errors}"

    def test_concurrent_dispatches(self):
        """Many threads dispatching replies concurrently without crash."""
        from nanosynth.osc import OscMessage

        server = _make_mock_server()
        received: list[str] = []
        lock = threading.Lock()

        def handler(msg):
            with lock:
                received.append(msg.address)

        server.on("/test", handler)

        # Pre-encode the datagram to avoid per-dispatch overhead
        datagram = OscMessage("/test", 0).to_datagram()

        def dispatch(thread_id: int) -> None:
            for _ in range(10):
                server._dispatch_reply(datagram)

        threads = [threading.Thread(target=dispatch, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(received) == 100  # 10 threads * 10 dispatches

    def test_waiter_timeout(self):
        """wait_for_reply with a short timeout returns None when no reply comes."""
        server = _make_mock_server()
        result = server.wait_for_reply("/never", timeout=0.05)
        assert result is None
