"""Composition root: builds config, adapters, controller, bus and view (D-A, D-F).

This is the only module that knows concrete adapters. ``compose`` wires one
application graph; ``run`` loads the configuration (CLI > env > INI > defaults),
then hands a ``main(page)`` to the Flet runner, which builds the graph when the
page opens. Importing this module opens no window and touches no camera.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import flet as ft

from depot_vision.adapters.bounded_event_bus import BoundedEventBus
from depot_vision.adapters.cv2_annotator import Cv2Annotator
from depot_vision.adapters.cv2_encoder import Cv2Encoder
from depot_vision.adapters.in_memory_repository import InMemoryCountRepository
from depot_vision.adapters.layered_config_provider import LayeredConfigProvider
from depot_vision.adapters.opencv_frame_source import OpenCVFrameSource
from depot_vision.adapters.pandas_csv_exporter import PandasCsvExporter
from depot_vision.adapters.system_clock import SystemClock
from depot_vision.adapters.ultralytics_detector import UltralyticsDetector
from depot_vision.application.capture_loop import CaptureLoop
from depot_vision.application.session_controller import SessionController
from depot_vision.application.worker import ThreadWorkerHandle
from depot_vision.domain.config import AppConfig
from depot_vision.domain.counting import CountingPolicy
from depot_vision.domain.retry import RetryPolicy
from depot_vision.ports import CountRepository, FrameSource, ObjectDetector
from depot_vision.presentation.view import DepotVisionView

#: Camera open / frame read backoff (D-E).
READ_RETRY = RetryPolicy(base_delay=0.25, max_delay=4.0, max_attempts=8, degrade_after=2)
#: Inference backoff (D-E).
INFERENCE_RETRY = RetryPolicy(base_delay=0.25, max_delay=1.0, max_attempts=3, degrade_after=2)


@dataclass(frozen=True)
class ComposedApp:
    view: DepotVisionView
    controller: SessionController
    repository: CountRepository
    export_dir: Path


def compose(
    config: AppConfig,
    *,
    home: Path | None = None,
    frame_source: FrameSource | None = None,
    detector: ObjectDetector | None = None,
) -> ComposedApp:
    """Wire one application graph; ``frame_source``/``detector`` are test seams."""
    clock = SystemClock()
    bus = BoundedEventBus(
        soft_capacity=config.queue_soft_capacity, hard_ceiling=config.queue_hard_ceiling
    )
    source = frame_source if frame_source is not None else OpenCVFrameSource(config)
    model = detector if detector is not None else UltralyticsDetector(config)
    export_dir = Path(config.resolve_export_dir(home if home is not None else Path.home()))

    # The graph is cyclic by nature (controller <-> worker <-> view <-> repository);
    # late-bound closures break each cycle without any layer importing upward.
    controller: SessionController
    loop: CaptureLoop
    view: DepotVisionView

    repository = InMemoryCountRepository(worker_live=lambda: controller.worker_live())
    controller = SessionController(
        bus=bus,
        repository=repository,
        frame_source=source,
        worker_factory=lambda: ThreadWorkerHandle(loop.run),
        stop_timeout_s=config.stop_timeout_s,
        drain=lambda: view.pump(),
    )
    loop = CaptureLoop(
        source=source,
        detector=model,
        annotator=Cv2Annotator(),
        encoder=Cv2Encoder(),
        repository=repository,
        bus=bus,
        clock=clock,
        notifier=controller,
        policy=CountingPolicy(confidence_threshold=config.confidence_threshold),
        read_retry=READ_RETRY,
        inference_retry=INFERENCE_RETRY,
    )
    view = DepotVisionView(
        controller=controller,
        bus=bus,
        repository=repository,
        exporter=PandasCsvExporter(clock),
        export_dir=export_dir,
        log_retention=config.log_retention,
    )
    return ComposedApp(
        view=view, controller=controller, repository=repository, export_dir=export_dir
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    runner: Callable[[Callable[[ft.Page], None]], Any] = ft.run,
    composer: Callable[[AppConfig], ComposedApp] = compose,
) -> None:
    """Load the configuration, then start the Flet app (blocks until it closes)."""
    config = LayeredConfigProvider(argv=sys.argv[1:] if argv is None else argv).load()

    def main(page: ft.Page) -> None:
        composer(config).view.mount(page)

    runner(main)
