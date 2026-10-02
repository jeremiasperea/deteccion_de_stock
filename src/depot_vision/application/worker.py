"""Worker abstraction the ``SessionController`` drives (D-D).

The controller never sees threads directly: it owns a ``WorkerHandle`` created
by an injected factory, so tests substitute deterministic fakes and the capture
loop (Phase 4b) plugs in as the body of a ``ThreadWorkerHandle``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

__all__ = ["ThreadWorkerHandle", "WorkerFactory", "WorkerHandle", "WorkerSignals"]


class WorkerHandle(Protocol):
    def start(self) -> None: ...

    def request_stop(self) -> None:
        """Signal the worker to exit at the head of its loop; never blocks."""
        ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...

    def join(self, timeout: float) -> bool:
        """Wait up to ``timeout`` seconds; return whether the worker has exited."""
        ...

    def is_alive(self) -> bool: ...


WorkerFactory = Callable[[], WorkerHandle]


@dataclass(frozen=True)
class WorkerSignals:
    """Events a worker body observes: exit when ``stop`` is set, idle while ``paused``."""

    stop: threading.Event
    paused: threading.Event


class ThreadWorkerHandle:
    """``WorkerHandle`` backed by a daemon ``threading.Thread`` running ``body``."""

    def __init__(self, body: Callable[[WorkerSignals], None]) -> None:
        self._signals = WorkerSignals(stop=threading.Event(), paused=threading.Event())
        # daemon=True is only a process-exit safety net, never the shutdown mechanism.
        self._thread = threading.Thread(target=body, args=(self._signals,), daemon=True)

    def start(self) -> None:
        self._thread.start()

    def request_stop(self) -> None:
        self._signals.stop.set()

    def pause(self) -> None:
        self._signals.paused.set()

    def resume(self) -> None:
        self._signals.paused.clear()

    def join(self, timeout: float) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def is_alive(self) -> bool:
        return self._thread.is_alive()
