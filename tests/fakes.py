"""Shared in-memory test doubles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


class FakeClock:
    """Deterministic ``Clock``: ``sleep`` advances time instantly and is recorded."""

    def __init__(self) -> None:
        self._monotonic = 0.0
        self._start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self._start + timedelta(seconds=self._monotonic)

    def monotonic(self) -> float:
        return self._monotonic

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._monotonic += seconds
