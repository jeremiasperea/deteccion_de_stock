"""``Clock`` adapter over the standard library."""

from __future__ import annotations

import time
from datetime import datetime


class SystemClock:
    """Real wall clock, monotonic clock and blocking sleep."""

    def now(self) -> datetime:
        # Naive local time, as the monolith's datetime.now() (CSV timestamp format).
        return datetime.now()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
