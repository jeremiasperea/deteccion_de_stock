"""ThreadWorkerHandle: real thread, driven by events only (no sleeps)."""

from __future__ import annotations

import threading

from depot_vision.application.worker import ThreadWorkerHandle, WorkerHandle, WorkerSignals


def test_conforms_to_worker_handle_and_exits_when_stop_requested() -> None:
    entered = threading.Event()

    def body(signals: WorkerSignals) -> None:
        entered.set()
        signals.stop.wait()

    handle: WorkerHandle = ThreadWorkerHandle(body)
    handle.start()
    assert entered.wait(1.0)
    assert handle.is_alive()
    assert handle.join(0.01) is False  # still running: timeout reports not exited
    handle.request_stop()
    assert handle.join(1.0) is True
    assert not handle.is_alive()


def test_pause_and_resume_toggle_the_paused_signal() -> None:
    seen: list[WorkerSignals] = []

    def body(signals: WorkerSignals) -> None:
        seen.append(signals)

    handle = ThreadWorkerHandle(body)
    handle.pause()
    handle.start()
    handle.join(1.0)
    assert seen[0].paused.is_set()
    handle.resume()
    assert not seen[0].paused.is_set()
