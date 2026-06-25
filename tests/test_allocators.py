"""Unit tests for the reclaiming id allocators in server.py."""

import threading

import pytest

from nanosynth.exceptions import EngineError
from nanosynth.server import _BlockAllocator, _NodeIdAllocator


class TestNodeIdAllocator:
    def test_starts_at_initial(self) -> None:
        alloc = _NodeIdAllocator()
        assert alloc.allocate() == 1000

    def test_sequential(self) -> None:
        alloc = _NodeIdAllocator()
        assert [alloc.allocate() for _ in range(5)] == [1000, 1001, 1002, 1003, 1004]

    def test_wraps_at_maximum(self) -> None:
        alloc = _NodeIdAllocator(initial=10, maximum=12)
        assert [alloc.allocate() for _ in range(5)] == [10, 11, 12, 10, 11]

    def test_thread_safe_unique(self) -> None:
        alloc = _NodeIdAllocator()
        ids: list[int] = []
        lock = threading.Lock()

        def worker() -> None:
            local = [alloc.allocate() for _ in range(100)]
            with lock:
                ids.extend(local)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(ids) == len(set(ids)) == 800


class TestBlockAllocator:
    def test_starts_at_zero(self) -> None:
        alloc = _BlockAllocator(16)
        assert alloc.allocate() == 0

    def test_sequential_single(self) -> None:
        alloc = _BlockAllocator(16)
        assert [alloc.allocate() for _ in range(4)] == [0, 1, 2, 3]

    def test_start_offset(self) -> None:
        alloc = _BlockAllocator(16, start=100)
        assert alloc.allocate() == 100
        assert alloc.allocate() == 101

    def test_contiguous_multichannel(self) -> None:
        alloc = _BlockAllocator(16)
        base = alloc.allocate(4)
        assert base == 0
        assert alloc.allocate() == 4  # next block starts after the 4-wide one

    def test_reclaim_lowest_first(self) -> None:
        alloc = _BlockAllocator(16)
        a, b, c = alloc.allocate(), alloc.allocate(), alloc.allocate()
        assert (a, b, c) == (0, 1, 2)
        alloc.free(b)
        assert alloc.allocate() == 1  # the freed id is reused

    def test_free_coalesces(self) -> None:
        alloc = _BlockAllocator(16)
        ids = [alloc.allocate() for _ in range(4)]  # 0,1,2,3
        for i in ids:
            alloc.free(i)
        # Fully reclaimed: a 4-wide block fits back at the start.
        assert alloc.allocate(4) == 0

    def test_freed_multichannel_block_reusable(self) -> None:
        alloc = _BlockAllocator(16)
        base = alloc.allocate(4)
        alloc.allocate(2)  # 4..5
        alloc.free(base)
        assert alloc.allocate(4) == 0  # the freed 4-wide block is handed back

    def test_capacity_exhaustion_raises(self) -> None:
        alloc = _BlockAllocator(4, name="test")
        for _ in range(4):
            alloc.allocate()
        with pytest.raises(EngineError, match="exhausted"):
            alloc.allocate()

    def test_exhaustion_then_free_recovers(self) -> None:
        alloc = _BlockAllocator(2)
        x = alloc.allocate()
        alloc.allocate()
        with pytest.raises(EngineError):
            alloc.allocate()
        alloc.free(x)
        assert alloc.allocate() == x

    def test_multichannel_too_large_raises(self) -> None:
        alloc = _BlockAllocator(4)
        with pytest.raises(EngineError):
            alloc.allocate(5)

    def test_allocated_set_tracks_base_ids(self) -> None:
        alloc = _BlockAllocator(16)
        a = alloc.allocate()
        b = alloc.allocate(2)
        assert alloc.allocated == {a, b}
        alloc.free(a)
        assert alloc.allocated == {b}

    def test_reserve_carves_explicit_id(self) -> None:
        alloc = _BlockAllocator(16)
        alloc.reserve(5)
        assert 5 in alloc.allocated
        # Auto-allocation skips the reserved id.
        ids = [alloc.allocate() for _ in range(6)]
        assert 5 not in ids
        assert ids == [0, 1, 2, 3, 4, 6]

    def test_reserve_is_idempotent(self) -> None:
        alloc = _BlockAllocator(16)
        alloc.reserve(5)
        alloc.reserve(5)  # no error, no double-tracking
        assert alloc.allocated == {5}

    def test_reserved_id_freed_and_reusable(self) -> None:
        alloc = _BlockAllocator(16)
        alloc.reserve(5)
        alloc.free(5)
        assert 5 not in alloc.allocated
        assert alloc.allocate(6) == 0  # 0..5 free again as a contiguous block

    def test_free_unallocated_is_noop(self) -> None:
        alloc = _BlockAllocator(16)
        alloc.free(7)  # never allocated
        assert alloc.allocated == set()

    def test_invalid_count_raises(self) -> None:
        alloc = _BlockAllocator(16)
        with pytest.raises(ValueError):
            alloc.allocate(0)

    def test_concurrent_allocations_unique(self) -> None:
        alloc = _BlockAllocator(1000)
        out: list[int] = []
        lock = threading.Lock()

        def worker() -> None:
            local = [alloc.allocate() for _ in range(100)]
            with lock:
                out.extend(local)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(out) == len(set(out)) == 800
