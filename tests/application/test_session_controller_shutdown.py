"""Ordered shutdown: signal -> drain -> join(timeout) -> release (FT4, FIX 3)."""

from __future__ import annotations

import asyncio

from tests.fakes import CallLog, FakeFrameSource, FakeRepository, FakeWorker, RecordingBus

from depot_vision.application.session_controller import SessionController
from depot_vision.domain.errors import CameraUnavailable
from depot_vision.domain.events import ShutdownTimedOut
from depot_vision.domain.session import SessionState

S = SessionState


def _rig(
    *, exits_on_join: bool = True
) -> tuple[SessionController, FakeWorker, FakeFrameSource, CallLog, RecordingBus]:
    log = CallLog()
    bus = RecordingBus(log)
    source = FakeFrameSource(log)
    workers = [FakeWorker(log, exits_on_join=exits_on_join)]
    controller = SessionController(
        bus=bus,
        repository=FakeRepository(log),
        frame_source=source,
        worker_factory=lambda: workers[0],
        stop_timeout_s=2.5,
        drain=lambda: log.add("drain"),
    )
    controller.start()
    controller.notify_running()
    log.entries.clear()
    return controller, workers[0], source, log, bus


def test_stop_runs_signal_drain_join_release_in_order() -> None:
    controller, worker, source, log, _ = _rig()
    assert asyncio.run(controller.stop()) is True
    assert log.entries == [
        "publish:SessionStateChanged",  # STOPPING
        "signal",
        "drain",
        "join",
        "close",
        "publish:SessionStateChanged",  # IDLE
    ]
    assert worker.join_timeouts == [2.5]
    assert source.closed == 1
    assert controller.state is S.IDLE


def test_join_timeout_retains_orphan_does_not_close_and_goes_error() -> None:
    controller, worker, source, _, bus = _rig(exits_on_join=False)
    assert asyncio.run(controller.stop()) is True
    assert controller.state is S.ERROR
    assert source.closed == 0
    assert controller.has_orphans is True
    timeouts = [e for e in bus.events if isinstance(e, ShutdownTimedOut)]
    assert [t.timeout_s for t in timeouts] == [2.5]
    assert worker.is_alive()


def test_orphan_locks_out_start_and_counts_as_live_worker() -> None:
    controller, _, _, _, _ = _rig(exits_on_join=False)
    asyncio.run(controller.stop())
    assert controller.start() is False
    assert controller.worker_live() is True


def test_later_stop_reaps_orphan_closes_source_and_returns_idle() -> None:
    controller, worker, source, _, _ = _rig(exits_on_join=False)
    asyncio.run(controller.stop())
    worker.exits_on_join = True
    assert asyncio.run(controller.stop()) is True
    assert controller.state is S.IDLE
    assert controller.has_orphans is False
    assert source.closed == 1
    assert controller.worker_live() is False
    assert controller.start() is True


def test_repeated_join_timeout_keeps_error_and_orphan() -> None:
    controller, _, source, _, bus = _rig(exits_on_join=False)
    asyncio.run(controller.stop())
    asyncio.run(controller.stop())
    assert controller.state is S.ERROR
    assert source.closed == 0
    assert len([e for e in bus.events if isinstance(e, ShutdownTimedOut)]) == 2


def test_stop_after_fault_joins_and_closes() -> None:
    controller, worker, source, _, _ = _rig()
    controller.notify_fault(CameraUnavailable("x"))
    assert asyncio.run(controller.stop()) is True
    assert controller.state is S.IDLE
    assert source.closed == 1
    assert worker.join_timeouts == [2.5]
