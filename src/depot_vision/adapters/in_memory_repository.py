"""``CountRepository`` adapter keeping history in a lock-guarded list (FT7).

The capture worker is the only writer (``append``); ``snapshot`` hands out an
immutable tuple copy that any thread may read. ``clear`` is legal only while no
worker is live; liveness is supplied by the session controller as a predicate
so this adapter stays free of any threading-lifecycle knowledge.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from depot_vision.domain.counting import CountSnapshot
from depot_vision.domain.errors import InvalidTransition


def _never_live() -> bool:
    return False


class InMemoryCountRepository:
    def __init__(self, worker_live: Callable[[], bool] = _never_live) -> None:
        self._worker_live = worker_live
        self._lock = threading.Lock()
        self._history: list[CountSnapshot] = []

    def append(self, snapshot: CountSnapshot) -> None:
        with self._lock:
            self._history.append(snapshot)

    def snapshot(self) -> tuple[CountSnapshot, ...]:
        with self._lock:
            return tuple(self._history)

    def clear(self) -> None:
        with self._lock:
            if self._worker_live():
                raise InvalidTransition("cannot clear history while a worker is live")
            self._history.clear()
