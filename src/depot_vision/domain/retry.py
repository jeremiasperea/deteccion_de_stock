"""Retry-with-bounded-backoff domain policy (FT1, replaces FIX 7).

Pure domain value object — no sleeping, no clock reads, no I/O. Callers
(the application layer, via a ``Clock`` port) own actually waiting out the
delay this returns. See design.md D-E for the schedule tables this pins.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """A bounded exponential backoff schedule, capped and attempt-limited.

    ``degrade_after`` is the consecutive-failure count at which the caller
    should surface a ``DEGRADED`` state (D-E); it is exposed as data for the
    application layer to read and is not consumed by this class's own logic.
    """

    base_delay: float
    max_delay: float
    max_attempts: int
    degrade_after: int

    def delay_for(self, attempt: int) -> float:
        """Delay before retry number ``attempt`` (1-indexed), capped at ``max_delay``."""
        return min(self.base_delay * 2 ** (attempt - 1), self.max_delay)

    def is_exhausted(self, attempt: int) -> bool:
        """Whether the retry budget is used up after ``attempt`` failures."""
        return attempt >= self.max_attempts
