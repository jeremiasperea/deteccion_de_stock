"""Controller never wedges when a collaborator raises during start or stop (F8)."""

from __future__ import annotations

import asyncio

from tests.fakes import FakeFrameSource, FakeRepository, FakeWorker, RecordingBus

from depot_vision.application.session_controller import SessionController
from depot_vision.application.worker import WorkerHandle
from depot_vision.domain.events import SessionFault
from depot_vision.domain.session import SessionState

S = SessionState


class BoomOnStart(FakeWorker):
    def start(self) -> None:
        raise OSError("thread limit")


class BoomOnJoin(FakeWorker):
    def join(self, timeout: float) -> bool:
        raise RuntimeError("join exploded")


class BoomOnClose(FakeFrameSource):
    def close(self) -> None:
        raise OSError("device busy")


def _controller(
    factory: object,
    *,
    source: FakeFrameSource | None = None,
    drain: object = None,
) -> tuple[SessionController, RecordingBus]:
    bus = RecordingBus()
    kwargs: dict[str, object] = {}
    if drain is not None:
        kwargs["drain"] = drain
    controller = SessionController(
        bus=bus,
        repository=FakeRepository(),
        frame_source=source or FakeFrameSource(),
        worker_factory=factory,  # type: ignore[arg-type]
        stop_timeout_s=1.0,
        **kwargs,  # type: ignore[arg-type]
    )
    return controller, bus


def _running(worker: WorkerHandle, **kw: object) -> tuple[SessionController, RecordingBus]:
    controller, bus = _controller(lambda: worker, **kw)  # type: ignore[arg-type]
    assert controller.start()
    controller.notify_running()
    return controller, bus


def _faults(bus: RecordingBus) -> list[SessionFault]:
    return [e for e in bus.events if isinstance(e, SessionFault)]


def test_factory_failure_moves_to_error_with_fault_and_no_worker() -> None:
    def factory() -> WorkerHandle:
        raise RuntimeError("cannot build worker")

    controller, bus = _controller(factory)
    assert controller.start() is False
    assert controller.state is S.ERROR
    assert controller.worker_live() is False
    assert len(_faults(bus)) == 1


def test_worker_start_failure_moves_to_error_and_drops_the_worker() -> None:
    worker = BoomOnStart()
    controller, bus = _controller(lambda: worker)
    assert controller.start() is False
    assert controller.state is S.ERROR
    assert controller.worker_live() is False
    assert len(_faults(bus)) == 1
    assert asyncio.run(controller.stop()) is True  # recoverable via stop
    assert controller.state is S.IDLE


def test_drain_failure_still_joins_releases_and_ends_in_error() -> None:
    worker = FakeWorker()
    source = FakeFrameSource()

    def bad_drain() -> None:
        raise RuntimeError("drain exploded")

    controller, bus = _running(worker, source=source, drain=bad_drain)
    assert asyncio.run(controller.stop()) is True
    assert controller.state is S.ERROR
    assert worker.join_timeouts == [1.0]
    assert source.closed == 1
    assert len(_faults(bus)) == 1


def test_join_failure_orphans_the_worker_without_closing_and_ends_in_error() -> None:
    worker = BoomOnJoin()
    source = FakeFrameSource()
    controller, bus = _running(worker, source=source)
    assert asyncio.run(controller.stop()) is True
    assert controller.state is S.ERROR
    assert source.closed == 0
    assert controller.has_orphans is True
    assert len(_faults(bus)) == 1


def test_close_failure_ends_in_error_with_no_orphans_and_is_retryable() -> None:
    worker = FakeWorker()
    controller, bus = _running(worker, source=BoomOnClose())
    assert asyncio.run(controller.stop()) is True
    assert controller.state is S.ERROR
    assert controller.has_orphans is False
    assert len(_faults(bus)) == 1
    assert controller.begin_stop() is True  # ERROR -> STOPPING is still available
