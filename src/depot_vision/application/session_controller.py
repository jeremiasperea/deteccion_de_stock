"""Session lifecycle controller (FT2, FT4, FT7, PRESERVE 6).

Owns the ``SessionState`` and the worker handle. UI-thread commands
(``start``/``pause``/``stop``) and worker-thread notifications
(``notify_*``) funnel through one lock-guarded transition helper that
validates against the domain table and publishes ``SessionStateChanged``.
Commands that are not legal in the current state are ignored and return
``False``, matching the monolith's control semantics.

Ordered shutdown: signal -> drain -> ``join(timeout)`` (via
``loop.run_in_executor`` so the UI loop stays responsive) -> release. On join
timeout the worker is retained as an orphan, the source stays open and Start
is locked out until a later ``stop()`` reaps it.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable

from depot_vision.application.faults import as_fault
from depot_vision.application.worker import WorkerFactory, WorkerHandle
from depot_vision.domain.errors import DepotVisionError, InvalidTransition
from depot_vision.domain.events import SessionFault, SessionStateChanged, ShutdownTimedOut
from depot_vision.domain.session import SessionState, is_legal_transition
from depot_vision.ports import CountRepository, EventBus, FrameSource

S = SessionState


def _no_drain() -> None:
    return None


class SessionController:
    def __init__(
        self,
        *,
        bus: EventBus,
        repository: CountRepository,
        frame_source: FrameSource,
        worker_factory: WorkerFactory,
        stop_timeout_s: float,
        drain: Callable[[], None] = _no_drain,
    ) -> None:
        self._bus = bus
        self._repository = repository
        self._source = frame_source
        self._worker_factory = worker_factory
        self._stop_timeout_s = stop_timeout_s
        self._drain = drain
        self._lock = threading.RLock()
        self._state = S.IDLE
        self._worker: WorkerHandle | None = None
        self._orphans: list[WorkerHandle] = []

    # -- observation -------------------------------------------------------

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def has_orphans(self) -> bool:
        return bool(self._orphans)

    def worker_live(self) -> bool:
        """Predicate for ``CountRepository``: any worker (current or orphan) alive."""
        with self._lock:
            current = self._worker is not None and self._worker.is_alive()
            return current or any(o.is_alive() for o in self._orphans)

    # -- UI-thread commands ------------------------------------------------

    def start(self) -> bool:
        with self._lock:
            if self._state is not S.IDLE or self._orphans:
                return False
            self.clear_history()  # before the worker thread exists (FT7)
            self._move(S.STARTING)
            try:
                worker = self._worker_factory()
                self._worker = worker
                worker.start()
            except Exception as exc:
                self._worker = None  # never leave a half-started handle behind
                self._bus.publish(SessionFault(error=as_fault(exc)))
                self._move(S.ERROR)
                return False
            return True

    def pause(self) -> bool:
        with self._lock:
            if self._worker is None:
                return False
            if self._state is S.RUNNING:
                self._worker.pause()
                self._move(S.PAUSED)
                return True
            if self._state is S.PAUSED:
                self._worker.resume()
                self._move(S.RUNNING)
                return True
            return False

    def clear_history(self) -> None:
        """Clear history; legal only in IDLE/ERROR with no live worker (FT7)."""
        with self._lock:
            if self._state not in (S.IDLE, S.ERROR) or self.worker_live():
                raise InvalidTransition(f"cannot clear history in {self._state.name}")
            self._repository.clear()

    def begin_stop(self) -> bool:
        """Step 1 of shutdown: enter STOPPING and signal the worker."""
        with self._lock:
            if not is_legal_transition(self._state, S.STOPPING):
                return False
            self._move(S.STOPPING)
            for worker in self._live_handles():
                worker.request_stop()
            return True

    async def stop(self) -> bool:
        """Signal, drain, join with timeout, then release (or orphan on timeout).

        Collaborator failures never wedge the controller in STOPPING: they are
        published as ``SessionFault`` events (never re-raised, like ``start``)
        and the session ends in ERROR instead of IDLE.
        """
        if not self.begin_stop():
            return False
        handles = self._live_handles()
        exited: list[WorkerHandle] = []
        errors: list[Exception] = []
        timed_out = False
        try:
            try:
                self._drain()
            except Exception as exc:
                errors.append(exc)  # still join: the stop signal is already sent
            loop = asyncio.get_running_loop()
            for handle in handles:
                try:
                    if await loop.run_in_executor(None, handle.join, self._stop_timeout_s):
                        exited.append(handle)
                    else:
                        timed_out = True
                except Exception as exc:
                    errors.append(exc)  # outcome unknown: the handle stays an orphan
        finally:
            self._finish_stop(handles, exited, errors, timed_out)
        return True

    def _finish_stop(
        self,
        handles: list[WorkerHandle],
        exited: list[WorkerHandle],
        errors: list[Exception],
        timed_out: bool,
    ) -> None:
        with self._lock:
            self._orphans = [h for h in handles if h not in exited]
            self._worker = None
            if not self._orphans:
                try:
                    self._source.close()
                except Exception as exc:
                    errors.append(exc)
            if timed_out:
                self._bus.publish(ShutdownTimedOut(timeout_s=self._stop_timeout_s))
            for error in errors:
                self._bus.publish(SessionFault(error=as_fault(error)))
            self._move(S.ERROR if self._orphans or errors else S.IDLE)

    # -- worker-thread notifications --------------------------------------

    def notify_running(self) -> bool:
        return self._notify(S.STARTING, S.RUNNING)

    def notify_degraded(self) -> bool:
        return self._notify(S.RUNNING, S.DEGRADED)

    def notify_recovered(self) -> bool:
        return self._notify(S.DEGRADED, S.RUNNING)

    def notify_fault(self, error: DepotVisionError) -> bool:
        """Log the fault and move to ERROR; RUNNING/PAUSED pass through STOPPING."""
        with self._lock:
            self._bus.publish(SessionFault(error=error))
            if self._state in (S.RUNNING, S.PAUSED):
                self._move(S.STOPPING)
            elif self._state not in (S.STARTING, S.DEGRADED):
                return False  # IDLE/ERROR: nothing to do; STOPPING: stop() owns the outcome
            self._move(S.ERROR)
            return True

    # -- internals ---------------------------------------------------------

    def _live_handles(self) -> list[WorkerHandle]:
        handles = list(self._orphans)
        if self._worker is not None:
            handles.append(self._worker)
        return handles

    def _notify(self, source: SessionState, target: SessionState) -> bool:
        with self._lock:
            if self._state is not source:
                return False
            self._move(target)
            return True

    def _move(self, target: SessionState) -> None:
        if not is_legal_transition(self._state, target):
            raise InvalidTransition(f"{self._state.name} -> {target.name} is not legal")
        self._state = target
        self._bus.publish(SessionStateChanged(state=target))
