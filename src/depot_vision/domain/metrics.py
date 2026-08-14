"""Frames-per-second metric (PRESERVE 7).

Reproduces app.py:142-144's exact FPS formula, including its
division-by-zero clamp. FpsMeter never reads a clock itself — timestamps
are always supplied by the caller — so it stays a pure, dependency-free
domain value object with no hidden clock coupling.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Matches app.py:143's clamp: prevents ZeroDivisionError when two frames
#: share an identical timestamp.
_MIN_ELAPSED_SECONDS = 1e-9


@dataclass
class FpsMeter:
    """Tracks the most recently computed frames-per-second value."""

    fps: float = 0.0

    def update(self, now: float, previous: float) -> float:
        """Compute FPS from ``now`` and ``previous`` timestamps and store it."""
        self.fps = 1.0 / max(now - previous, _MIN_ELAPSED_SECONDS)
        return self.fps
