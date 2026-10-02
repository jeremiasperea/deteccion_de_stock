"""History guard: clear only with no live worker; Start clears before spawn (FT7, FIX 4)."""

from __future__ import annotations

import asyncio

import pytest
from tests.fakes import CallLog, FakeFrameSource, FakeRepository, FakeWorker, RecordingBus

from depot_vision.adapters.in_memory_repository import InMemoryCountRepository
from depot_vision.application.session_controller import SessionController
from depot_vision.domain.counting import CountSnapshot
from depot_vision.domain.errors import CameraUnavailable, InvalidTransition
from depot_vision.domain.session import SessionState

S = SessionState


def _controller(log: CallLog | None = None) -> tuple[SessionController, FakeWorker]:
    worker = FakeWorker(log)
    controller = SessionController(
        bus=RecordingBus(),
        repository=FakeRepository(log),
        frame_source=FakeFrameSource(),
        worker_factory=lambda: worker,
        stop_timeout_s=1.0,
    )
    return controller, worker


def test_start_clears_history_before_spawning_the_worker() -> None:
    log = CallLog()
    controller, _ = _controller(log)
    controller.start()
    assert log.entries.index("clear") < log.entries.index("spawn")


def test_clear_history_is_legal_when_idle() -> None:
    log = CallLog()
    controller, _ = _controller(log)
    controller.clear_history()
    assert log.entries == ["clear"]


@pytest.mark.parametrize("target", [S.STARTING, S.RUNNING, S.PAUSED, S.DEGRADED])
def test_clear_history_is_illegal_in_active_states(target: SessionState) -> None:
    controller, _ = _controller()
    controller.start()
    if target is not S.STARTING:
        controller.notify_running()
    if target is S.PAUSED:
        controller.pause()
    if target is S.DEGRADED:
        controller.notify_degraded()
    with pytest.raises(InvalidTransition):
        controller.clear_history()


def test_clear_history_is_legal_in_error_once_worker_exited() -> None:
    controller, worker = _controller()
    controller.start()
    controller.notify_fault(CameraUnavailable("gone"))
    with pytest.raises(InvalidTransition):  # worker thread still alive
        controller.clear_history()
    worker.alive = False
    controller.clear_history()


def test_clear_history_is_illegal_while_orphan_is_live() -> None:
    controller, worker = _controller()
    worker.exits_on_join = False
    controller.start()
    controller.notify_running()
    asyncio.run(controller.stop())
    with pytest.raises(InvalidTransition):
        controller.clear_history()


def test_worker_live_predicate_guards_the_real_repository() -> None:
    holder: list[SessionController] = []
    repo = InMemoryCountRepository(worker_live=lambda: holder[0].worker_live())
    worker = FakeWorker()
    controller = SessionController(
        bus=RecordingBus(),
        repository=repo,
        frame_source=FakeFrameSource(),
        worker_factory=lambda: worker,
        stop_timeout_s=1.0,
    )
    holder.append(controller)
    repo.append(CountSnapshot(counts={}))
    controller.start()
    assert repo.snapshot() == ()  # cleared by Start, before spawn
    repo.append(CountSnapshot(counts={}))
    with pytest.raises(InvalidTransition):
        repo.clear()
    controller.notify_running()
    asyncio.run(controller.stop())
    repo.clear()
    assert repo.snapshot() == ()
