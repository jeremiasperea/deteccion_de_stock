"""SystemClock wraps stdlib; FakeClock drives RetryPolicy backoff (D-B, D-E)."""

from __future__ import annotations

import time
from datetime import datetime

import pytest
from tests.fakes import FakeClock

from depot_vision.adapters.system_clock import SystemClock
from depot_vision.domain.errors import CameraUnavailable
from depot_vision.domain.retry import RetryPolicy
from depot_vision.ports import Clock


def test_conforms_to_clock_port() -> None:
    assert isinstance(SystemClock(), Clock)


def test_now_is_naive_local_wall_clock() -> None:
    # Matches the monolith's datetime.now(): CSV timestamps stay naive local ISO 8601.
    before = datetime.now()
    now = SystemClock().now()
    after = datetime.now()
    assert now.tzinfo is None
    assert before <= now <= after


def test_monotonic_never_decreases() -> None:
    clock = SystemClock()
    first = clock.monotonic()
    assert clock.monotonic() >= first


def test_sleep_delegates_to_time_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[float] = []
    monkeypatch.setattr(time, "sleep", calls.append)
    SystemClock().sleep(0.25)
    assert calls == [0.25]


def test_fake_clock_drives_backoff_schedule_without_real_delay(fake_clock: FakeClock) -> None:
    policy = RetryPolicy(base_delay=0.5, max_delay=2.0, max_attempts=5, degrade_after=3)
    attempts = 0

    def always_fails() -> None:
        raise CameraUnavailable("down")

    attempt = 0
    while True:
        try:
            always_fails()
        except CameraUnavailable:
            attempts += 1
            attempt += 1
            if policy.is_exhausted(attempt):
                break
            fake_clock.sleep(policy.delay_for(attempt))

    assert attempts == 5
    assert fake_clock.sleeps == [0.5, 1.0, 2.0, 2.0]
    assert fake_clock.monotonic() == 5.5
