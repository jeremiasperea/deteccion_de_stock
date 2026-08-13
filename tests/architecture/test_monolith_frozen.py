"""Freeze test for the pre-refactor monolith.

Asserts that `app.py` has not been modified since the refactor's baseline
commit (`193c577`). This protects every additive phase (0 through 4) from
accidentally touching the still-authoritative monolith runtime path while
the new `src/depot_vision/**` package is built up alongside it unrouted.

The expected digest is a hardcoded literal computed from `193c577:app.py`.
It must NOT be recomputed from the file under test here — doing so would
make this assertion vacuously true regardless of any edit and would
protect nothing.

Deleted intentionally in Phase 5b (task 5.13) once `app.py` is rewired to
delegate to `presentation/flet_app.py` and the freeze is lifted on purpose.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

BASELINE_APP_PY_SHA256 = (
    "8f47847d27acb716451f6eef13ce4858941c4c713798886cd008dea8fbb3e7fe"
)

APP_PY_PATH = Path(__file__).resolve().parents[2] / "app.py"


def test_app_py_matches_frozen_baseline() -> None:
    digest = hashlib.sha256(APP_PY_PATH.read_bytes()).hexdigest()
    assert digest == BASELINE_APP_PY_SHA256, (
        "app.py changed since the refactor baseline (193c577). Phases 0-4 "
        "must not modify app.py; if this change is Phase 5b's intentional "
        "rewiring, delete this test per task 5.13 instead of relaxing it."
    )
