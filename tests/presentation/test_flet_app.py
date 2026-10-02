"""Composition root: wiring and ``run()``, with no window, camera or model."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import flet as ft
import numpy as np
import pytest
from tests.presentation.fake_page import FakePage

from depot_vision.domain.config import AppConfig
from depot_vision.domain.detections import Detection
from depot_vision.domain.errors import InvalidTransition
from depot_vision.domain.frames import Frame
from depot_vision.domain.session import SessionState
from depot_vision.presentation.flet_app import ComposedApp, compose, run


class StubSource:
    def __init__(self) -> None:
        self.closed = 0
        self._open = False

    def open(self) -> None:
        self._open = True

    def read(self) -> Frame:
        return Frame(pixels=np.zeros((48, 64, 3), dtype=np.uint8))

    def close(self) -> None:
        self.closed += 1
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open


class StubDetector:
    def load(self) -> None:
        pass

    def detect(self, frame: Frame) -> Sequence[Detection]:
        return ()


def build(tmp_path: Path, **overrides: str) -> tuple[ComposedApp, StubSource, FakePage]:
    source = StubSource()
    config = AppConfig.from_mapping({"stop_timeout_s": "5", **overrides})
    app = compose(config, home=tmp_path, frame_source=source, detector=StubDetector())
    page = FakePage()
    app.view.mount(page.as_page())
    return app, source, page


def wait_until(condition: Callable[[], bool], *, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.005)


def test_export_dir_is_resolved_against_home(tmp_path: Path) -> None:
    app, _, _ = build(tmp_path, export_dir="~/out")
    assert app.export_dir == tmp_path / "out"


def test_mounting_the_composed_view_builds_the_page_without_a_window(tmp_path: Path) -> None:
    _, _, page = build(tmp_path)
    assert len(page.controls_added) == 2
    assert len(page.run_tasks) == 1


def test_real_session_runs_frames_through_the_full_stack_and_stops_cleanly(
    tmp_path: Path,
) -> None:
    app, source, _ = build(tmp_path)
    assert app.controller.start()

    def frame_shown() -> bool:
        app.view.pump()
        return isinstance(app.view.image.src, bytes)

    wait_until(frame_shown)
    # the repository sees the live worker through the controller wiring
    with pytest.raises(InvalidTransition):
        app.repository.clear()

    asyncio.run(app.view.on_stop(None))
    assert app.controller.state is SessionState.IDLE
    assert source.closed == 1
    app.repository.clear()  # no live worker any more


def test_run_loads_config_from_argv_and_hands_main_to_the_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # no stray depot_vision.ini
    monkeypatch.delenv("DEPOT_VISION_CONFIG", raising=False)
    mains: list[Callable[[ft.Page], Any]] = []
    configs: list[AppConfig] = []

    def fake_compose(config: AppConfig) -> ComposedApp:
        configs.append(config)
        return compose(config, home=tmp_path, frame_source=StubSource(), detector=StubDetector())

    run(["--export-dir", "~/csv"], runner=mains.append, composer=fake_compose)

    assert len(mains) == 1 and configs == []  # nothing is built before the runner calls main
    page = FakePage()
    mains[0](page.as_page())
    assert [c.export_dir for c in configs] == ["~/csv"]
    assert len(page.controls_added) == 2
