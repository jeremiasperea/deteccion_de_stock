"""SessionController state machine: full transition matrix via fake ports (FT2, PRESERVE 6)."""

from __future__ import annotations

import asyncio

import pytest
from tests.fakes import FakeFrameSource, FakeRepository, FakeWorker, RecordingBus

from depot_vision.application.session_controller import SessionController
from depot_vision.domain.errors import CameraUnavailable
from depot_vision.domain.events import SessionFault
from depot_vision.domain.session import SessionState

S = SessionState


class Rig:
    def __init__(self) -> None:
        self.bus = RecordingBus()
        self.source = FakeFrameSource()
        self.repo = FakeRepository()
        self.workers: list[FakeWorker] = []
        self.controller = SessionController(
            bus=self.bus,
            repository=self.repo,
            frame_source=self.source,
            worker_factory=self._make,
            stop_timeout_s=5.0,
        )

    def _make(self) -> FakeWorker:
        worker = FakeWorker()
        self.workers.append(worker)
        return worker

    @property
    def worker(self) -> FakeWorker:
        return self.workers[-1]

    def stop(self) -> bool:
        return asyncio.run(self.controller.stop())

    def to(self, state: SessionState) -> None:
        """Drive the controller into ``state`` through public operations."""
        c = self.controller
        if state is S.IDLE:
            return
        c.start()
        if state is S.STARTING:
            return
        if state is S.ERROR:
            c.notify_fault(CameraUnavailable("gone"))
            return
        c.notify_running()
        if state is S.PAUSED:
            c.pause()
        elif state is S.DEGRADED:
            c.notify_degraded()
        elif state is S.STOPPING:
            c.begin_stop()
        assert c.state is state


def test_starts_idle() -> None:
    assert Rig().controller.state is S.IDLE


def test_start_goes_starting_then_running_and_publishes_each() -> None:
    rig = Rig()
    assert rig.controller.start() is True
    assert rig.controller.state is S.STARTING
    assert rig.worker.started == 1
    assert rig.controller.notify_running() is True
    assert rig.controller.state is S.RUNNING
    assert rig.bus.states() == [S.STARTING, S.RUNNING]


@pytest.mark.parametrize(
    "state", [S.STARTING, S.RUNNING, S.PAUSED, S.DEGRADED, S.STOPPING, S.ERROR]
)
def test_start_is_ignored_unless_idle(state: SessionState) -> None:
    rig = Rig()
    rig.to(state)
    published = len(rig.bus.events)
    assert rig.controller.start() is False
    assert rig.controller.state is state
    assert len(rig.workers) == 1
    assert len(rig.bus.events) == published


def test_pause_toggles_running_and_paused_keeping_source_open() -> None:
    rig = Rig()
    rig.to(S.RUNNING)
    assert rig.controller.pause() is True
    assert rig.controller.state is S.PAUSED
    assert rig.worker.paused is True
    assert rig.source.closed == 0
    assert rig.controller.pause() is True
    assert rig.controller.state is S.RUNNING
    assert rig.worker.paused is False
    assert rig.bus.states() == [S.STARTING, S.RUNNING, S.PAUSED, S.RUNNING]


@pytest.mark.parametrize("state", [S.IDLE, S.STARTING, S.DEGRADED, S.STOPPING, S.ERROR])
def test_pause_is_ignored_outside_running_and_paused(state: SessionState) -> None:
    rig = Rig()
    rig.to(state)
    assert rig.controller.pause() is False
    assert rig.controller.state is state


def test_degraded_entry_and_exit_publish_state_changes() -> None:
    rig = Rig()
    rig.to(S.RUNNING)
    assert rig.controller.notify_degraded() is True
    assert rig.controller.state is S.DEGRADED
    assert rig.controller.notify_recovered() is True
    assert rig.controller.state is S.RUNNING
    assert rig.bus.states() == [S.STARTING, S.RUNNING, S.DEGRADED, S.RUNNING]


@pytest.mark.parametrize(
    ("notify", "legal_from"),
    [
        ("notify_running", {S.STARTING}),
        ("notify_degraded", {S.RUNNING}),
        ("notify_recovered", {S.DEGRADED}),
    ],
)
@pytest.mark.parametrize("state", list(SessionState))
def test_worker_notifications_apply_only_from_their_source_state(
    notify: str, legal_from: set[SessionState], state: SessionState
) -> None:
    rig = Rig()
    rig.to(state)
    published = len(rig.bus.events)
    applied = getattr(rig.controller, notify)()
    assert applied is (state in legal_from)
    if state not in legal_from:
        assert rig.controller.state is state
        assert len(rig.bus.events) == published


def test_fault_while_starting_goes_error_and_logs_session_fault() -> None:
    rig = Rig()
    rig.to(S.STARTING)
    error = CameraUnavailable("no camera")
    assert rig.controller.notify_fault(error) is True
    assert rig.controller.state is S.ERROR
    faults = [e for e in rig.bus.events if isinstance(e, SessionFault)]
    assert [f.error for f in faults] == [error]


def test_fault_while_degraded_goes_error() -> None:
    rig = Rig()
    rig.to(S.DEGRADED)
    rig.controller.notify_fault(CameraUnavailable("exhausted"))
    assert rig.controller.state is S.ERROR


@pytest.mark.parametrize("state", [S.RUNNING, S.PAUSED])
def test_fault_while_running_or_paused_passes_through_stopping(state: SessionState) -> None:
    rig = Rig()
    rig.to(state)
    rig.controller.notify_fault(CameraUnavailable("queue overflow"))
    assert rig.controller.state is S.ERROR
    assert rig.bus.states()[-2:] == [S.STOPPING, S.ERROR]


@pytest.mark.parametrize("state", [S.IDLE, S.STOPPING, S.ERROR])
def test_fault_in_idle_stopping_or_error_is_logged_without_state_change(
    state: SessionState,
) -> None:
    rig = Rig()
    rig.to(state)
    assert rig.controller.notify_fault(CameraUnavailable("late")) is False
    assert rig.controller.state is state
    assert any(isinstance(e, SessionFault) for e in rig.bus.events)


@pytest.mark.parametrize("state", [S.RUNNING, S.PAUSED, S.DEGRADED, S.ERROR])
def test_stop_returns_to_idle_from_stoppable_states(state: SessionState) -> None:
    rig = Rig()
    rig.to(state)
    assert rig.stop() is True
    assert rig.controller.state is S.IDLE


@pytest.mark.parametrize("state", [S.IDLE, S.STARTING, S.STOPPING])
def test_stop_is_ignored_in_unstoppable_states(state: SessionState) -> None:
    rig = Rig()
    rig.to(state)
    assert rig.stop() is False
    assert rig.controller.state is state
    assert rig.source.closed == 0


def test_start_again_after_stop() -> None:
    rig = Rig()
    rig.to(S.RUNNING)
    rig.stop()
    assert rig.controller.start() is True
    assert len(rig.workers) == 2
