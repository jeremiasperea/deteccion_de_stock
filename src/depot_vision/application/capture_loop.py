"""Capture worker body: read -> detect -> count -> annotate -> encode -> publish (D-E, FT1).

Orchestrates ports only. Camera open/read and inference failures follow the
bounded-backoff ``RetryPolicy`` waited out through the injected ``Clock``:
reaching ``degrade_after`` consecutive failures notifies DEGRADED, a fully
successful frame resets the counters and notifies recovery, and an exhausted
budget reports a typed fault. The loop never closes the camera: release
belongs to the controller after a successful join (FT4). Pacing and pause
cadence reproduce the monolith (PRESERVE 8).
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from depot_vision.application.faults import as_fault
from depot_vision.application.worker import WorkerSignals
from depot_vision.domain.counting import TARGET_CLASSES, CountingPolicy
from depot_vision.domain.errors import (
    CameraUnavailable,
    DepotVisionError,
    FrameReadFailed,
    InferenceFailed,
)
from depot_vision.domain.events import DetectionLogged, FrameRendered, LogEmitted
from depot_vision.domain.frames import Overlay
from depot_vision.domain.metrics import FpsMeter
from depot_vision.domain.retry import RetryPolicy
from depot_vision.ports import (
    Clock,
    CountRepository,
    EventBus,
    FrameAnnotator,
    FrameEncoder,
    FrameSource,
    ObjectDetector,
)

#: Idle wait while paused (monolith ``time.sleep(0.05)``).
PAUSE_SLEEP_S = 0.05
#: Wait after every processed frame, capping throughput near 30 fps (monolith ``time.sleep(0.03)``).
FRAME_PACING_S = 0.03
#: A history snapshot and detection log are recorded every Nth frame that has detections.
DETECTION_LOG_EVERY = 30


class SessionNotifier(Protocol):
    """The slice of ``SessionController`` the worker reports through."""

    def notify_running(self) -> bool: ...

    def notify_degraded(self) -> bool: ...

    def notify_recovered(self) -> bool: ...

    def notify_fault(self, error: DepotVisionError) -> bool: ...


class CaptureLoop:
    def __init__(
        self,
        *,
        source: FrameSource,
        detector: ObjectDetector,
        annotator: FrameAnnotator,
        encoder: FrameEncoder,
        repository: CountRepository,
        bus: EventBus,
        clock: Clock,
        notifier: SessionNotifier,
        policy: CountingPolicy,
        read_retry: RetryPolicy,
        inference_retry: RetryPolicy,
    ) -> None:
        self._source = source
        self._detector = detector
        self._annotator = annotator
        self._encoder = encoder
        self._repository = repository
        self._bus = bus
        self._clock = clock
        self._notifier = notifier
        self._policy = policy
        self._read_retry = read_retry
        self._inference_retry = inference_retry

    def run(self, signals: WorkerSignals) -> None:
        """Thread body: returns on stop request or after reporting a fault."""
        try:
            if self._start_up(signals):
                self._process(signals)
        except Exception as exc:  # last resort: surface it, never die silently
            self._notifier.notify_fault(as_fault(exc))

    def _start_up(self, signals: WorkerSignals) -> bool:
        try:
            self._detector.load()
        except InferenceFailed as exc:
            self._notifier.notify_fault(exc)
            return False
        failures = 0
        while not signals.stop.is_set():
            try:
                self._source.open()
            except CameraUnavailable as exc:
                failures += 1
                if self._read_retry.is_exhausted(failures):
                    self._notifier.notify_fault(exc)
                    return False
                self._bus.publish(LogEmitted(message=f"Camera unavailable, retrying: {exc}"))
                self._clock.sleep(self._read_retry.delay_for(failures))
                continue
            self._notifier.notify_running()
            return True
        return False

    def _process(self, signals: WorkerSignals) -> None:
        clock = self._clock
        meter = FpsMeter()
        previous = clock.monotonic()
        frame_count = 0
        read_failures = 0
        inference_failures = 0
        degraded = False

        while not signals.stop.is_set():
            if signals.paused.is_set():
                clock.sleep(PAUSE_SLEEP_S)
                continue

            try:
                frame = self._source.read()
            except FrameReadFailed as exc:
                read_failures += 1
                if self._read_retry.is_exhausted(read_failures):
                    fault = CameraUnavailable(f"frame read failed {read_failures} times: {exc}")
                    fault.__cause__ = exc
                    self._notifier.notify_fault(fault)
                    return
                self._bus.publish(LogEmitted(message="⚠️ Frame vacío, reintentando..."))
                degraded = self._degrade_if_due(degraded, read_failures, self._read_retry)
                clock.sleep(self._read_retry.delay_for(read_failures))
                continue
            read_failures = 0

            try:
                detections = self._detector.detect(frame)
            except InferenceFailed as exc:
                inference_failures += 1
                if self._inference_retry.is_exhausted(inference_failures):
                    self._notifier.notify_fault(exc)
                    return
                self._bus.publish(LogEmitted(message=f"Inference failed, retrying: {exc}"))
                degraded = self._degrade_if_due(degraded, inference_failures, self._inference_retry)
                clock.sleep(self._inference_retry.delay_for(inference_failures))
                continue
            inference_failures = 0
            if degraded:
                self._notifier.notify_recovered()
                degraded = False

            selected = self._policy.select(detections)
            snapshot = dataclasses.replace(self._policy.apply(detections), timestamp=clock.now())
            now = clock.monotonic()
            meter.update(now, previous)
            previous = now
            frame_count += 1

            annotated = self._annotator.annotate(
                frame, selected, Overlay(fps=meter.fps, frame_count=frame_count)
            )
            self._bus.publish(
                FrameRendered(
                    image=self._encoder.encode(annotated),
                    snapshot=snapshot,
                    fps=meter.fps,
                    frame_number=frame_count,
                )
            )

            total = sum(snapshot.counts.values())
            if frame_count % DETECTION_LOG_EVERY == 0 and total > 0 and snapshot.timestamp:
                self._repository.append(snapshot)
                parts = [
                    f"{target.label.split()[-1]}:{n}"
                    for target in TARGET_CLASSES.values()
                    if (n := snapshot.count_for(target)) > 0
                ]
                stamp = snapshot.timestamp.strftime("%H:%M:%S")
                self._bus.publish(DetectionLogged(message=f"📦 [{stamp}] " + "  ".join(parts)))

            clock.sleep(FRAME_PACING_S)

    def _degrade_if_due(self, degraded: bool, failures: int, policy: RetryPolicy) -> bool:
        if not degraded and failures >= policy.degrade_after:
            self._notifier.notify_degraded()
            return True
        return degraded
