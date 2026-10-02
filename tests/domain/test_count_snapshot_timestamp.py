"""CountSnapshot may carry the moment it was counted (per-row CSV timestamp)."""

from __future__ import annotations

import dataclasses
from datetime import datetime

from depot_vision.domain.counting import CountingPolicy, CountSnapshot


def test_timestamp_defaults_to_none() -> None:
    assert CountSnapshot(counts={}).timestamp is None
    assert CountingPolicy().apply([]).timestamp is None


def test_timestamp_can_be_stamped_with_replace() -> None:
    moment = datetime(2026, 1, 1, 12, 30, 15)
    stamped = dataclasses.replace(CountSnapshot(counts={}), timestamp=moment)
    assert stamped.timestamp == moment
