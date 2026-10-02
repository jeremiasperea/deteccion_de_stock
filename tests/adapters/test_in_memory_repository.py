"""InMemoryCountRepository: single-writer append, tuple snapshots, guarded clear (FT7)."""

from __future__ import annotations

import threading

import pytest

from depot_vision.adapters.in_memory_repository import InMemoryCountRepository
from depot_vision.domain.counting import TARGET_CLASSES, CountSnapshot
from depot_vision.domain.errors import InvalidTransition
from depot_vision.ports import CountRepository

PERSON = TARGET_CLASSES["person"]


def _snap(n: int) -> CountSnapshot:
    return CountSnapshot(counts={PERSON: n})


def test_conforms_to_count_repository_port() -> None:
    assert isinstance(InMemoryCountRepository(), CountRepository)


def test_append_preserves_order_and_snapshot_is_tuple() -> None:
    repo = InMemoryCountRepository()
    repo.append(_snap(1))
    repo.append(_snap(2))
    history = repo.snapshot()
    assert isinstance(history, tuple)
    assert history == (_snap(1), _snap(2))


def test_snapshot_is_a_copy_unaffected_by_later_appends() -> None:
    repo = InMemoryCountRepository()
    repo.append(_snap(1))
    before = repo.snapshot()
    repo.append(_snap(2))
    assert before == (_snap(1),)
    assert len(repo.snapshot()) == 2


def test_clear_empties_history_when_no_worker_is_live() -> None:
    repo = InMemoryCountRepository(worker_live=lambda: False)
    repo.append(_snap(1))
    repo.clear()
    assert repo.snapshot() == ()


def test_clear_raises_invalid_transition_when_worker_is_live() -> None:
    repo = InMemoryCountRepository(worker_live=lambda: True)
    repo.append(_snap(1))
    with pytest.raises(InvalidTransition):
        repo.clear()
    assert repo.snapshot() == (_snap(1),)


def test_worker_liveness_is_evaluated_at_clear_time() -> None:
    live = {"value": True}
    repo = InMemoryCountRepository(worker_live=lambda: live["value"])
    with pytest.raises(InvalidTransition):
        repo.clear()
    live["value"] = False
    repo.clear()


def test_concurrent_snapshots_are_consistent_prefixes_while_writer_appends() -> None:
    repo = InMemoryCountRepository()
    total = 2000
    seen: list[tuple[CountSnapshot, ...]] = []

    def writer() -> None:
        for i in range(total):
            repo.append(_snap(i))

    thread = threading.Thread(target=writer)
    thread.start()
    while thread.is_alive():
        seen.append(repo.snapshot())
    thread.join()
    seen.append(repo.snapshot())
    for history in seen:
        assert history == tuple(_snap(i) for i in range(len(history)))
    assert len(seen[-1]) == total
