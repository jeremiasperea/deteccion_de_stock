"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from tests.fakes import FakeClock


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()
