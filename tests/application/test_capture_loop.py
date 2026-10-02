"""Capture loop: port orchestration, pacing, retry/backoff, DEGRADED and faults (FT1, D-E)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest
from tests.fakes import FakeClock, FakeFrameSource, FakeRepository, FakeWorker, RecordingBus

from depot_vision.application.capture_loop import CaptureLoop
from depot_vision.application.session_controller import SessionController
from depot_vision.application.worker import WorkerSignals
from depot_vision.domain.counting import TARGET_CLASSES, CountingPolicy, CountSnapshot
from depot_vision.domain.detections import BoundingBox, Detection
from depot_vision.domain.errors import (
    CameraUnavailable,
    DepotVisionError,
    EncodingFailed,
    FrameReadFailed,
    InferenceFailed,
)
from depot_vision.domain.events import (
    DetectionLogged,
    FrameRendered,
    LogEmitted,
    SessionFault,
)
from depot_vision.domain.frames import EncodedImage, Frame, Overlay
from depot_vision.domain.retry import RetryPolicy
from depot_vision.domain.session import SessionState

S = SessionState
READ_RETRY = RetryPolicy(base_delay=0.25, max_delay=4.0, max_attempts=8, degrade_after=2)
INFER_RETRY = RetryPolicy(base_delay=0.25, max_delay=1.0, max_attempts=3, degrade_after=2)
BOX = BoundingBox(0, 0, 1, 1)
FRAME = Frame(pixels="px")


def det(name: str, conf: float) -> Detection:
    return Detection(class_name=name, confidence=conf, bounding_box=BOX)


class Script:
    """A scripted collaborator: pops results, then requests stop when it runs dry."""

    def __init__(self, items: Sequence[object], stop: threading.Event | None = None) -> None:
        self.items = list(items)
        self.stop = stop
        self.calls = 0

    def next(self) -> object:
        self.calls += 1
        item = self.items.pop(0)
        if not self.items and self.stop is not None:
            self.stop.set()  # exit at the head of the next iteration
        if isinstance(item, Exception):
            raise item
        return item


class ScriptedSource(FakeFrameSource):
    def __init__(self, reads: Script, opens: Script | None = None) -> None:
        super().__init__()
        self.reads = reads
        self.opens = opens
        self.open_calls = 0

    def open(self) -> None:
        self.open_calls += 1
        if self.opens is not None:
            self.opens.next()

    def read(self) -> Frame:
        item = self.reads.next()
        assert isinstance(item, Frame)
        return item


class ScriptedDetector:
    def __init__(self, results: Script | None = None, load_error: Exception | None = None) -> None:
        self.results = results
        self.load_error = load_error
        self.loaded = 0

    def load(self) -> None:
        self.loaded += 1
        if self.load_error is not None:
            raise self.load_error

    def detect(self, frame: Frame) -> Sequence[Detection]:
        if self.results is None:
            return []
        item = self.results.next()
        assert isinstance(item, list)
        return item


class RecordingAnnotator:
    def __init__(self) -> None:
        self.calls: list[tuple[Frame, tuple[Detection, ...], Overlay]] = []

    def annotate(self, frame: Frame, detections: Sequence[Detection], overlay: Overlay) -> Frame:
        self.calls.append((frame, tuple(detections), overlay))
        return Frame(pixels="annotated")


class FakeEncoder:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.encoded: list[Frame] = []

    def encode(self, frame: Frame) -> EncodedImage:
        if self.error is not None:
            raise self.error
        self.encoded.append(frame)
        return EncodedImage(data=b"jpeg", media_type="image/jpeg")


class StampingRepository(FakeRepository):
    def __init__(self) -> None:
        super().__init__()
        self.appended: list[CountSnapshot] = []

    def append(self, snapshot: CountSnapshot) -> None:
        self.appended.append(snapshot)


@dataclass
class Notifier:
    calls: list[str] = field(default_factory=list)
    faults: list[DepotVisionError] = field(default_factory=list)

    def notify_running(self) -> bool:
        self.calls.append("running")
        return True

    def notify_degraded(self) -> bool:
        self.calls.append("degraded")
        return True

    def notify_recovered(self) -> bool:
        self.calls.append("recovered")
        return True

    def notify_fault(self, error: DepotVisionError) -> bool:
        self.calls.append("fault")
        self.faults.append(error)
        return True


class Rig:
    def __init__(
        self,
        reads: Sequence[object],
        *,
        detections: Sequence[object] | None = None,
        opens: Sequence[object] | None = None,
        load_error: Exception | None = None,
        encoder_error: Exception | None = None,
        notifier: object | None = None,
        bus: RecordingBus | None = None,
    ) -> None:
        self.signals = WorkerSignals(stop=threading.Event(), paused=threading.Event())
        self.clock = FakeClock()
        self.bus = bus or RecordingBus()
        self.notifier = notifier or Notifier()
        self.source = ScriptedSource(
            Script(reads, self.signals.stop), Script(opens) if opens is not None else None
        )
        self.detector = ScriptedDetector(
            Script(detections) if detections is not None else None, load_error
        )
        self.annotator = RecordingAnnotator()
        self.encoder = FakeEncoder(encoder_error)
        self.repo = StampingRepository()
        self.loop = CaptureLoop(
            source=self.source,
            detector=self.detector,
            annotator=self.annotator,
            encoder=self.encoder,
            repository=self.repo,
            bus=self.bus,
            clock=self.clock,
            notifier=self.notifier,  # type: ignore[arg-type]
            policy=CountingPolicy(),
            read_retry=READ_RETRY,
            inference_retry=INFER_RETRY,
        )

    def run(self) -> None:
        self.loop.run(self.signals)


def test_happy_path_runs_the_pipeline_and_publishes_the_frame() -> None:
    rig = Rig([FRAME], detections=[[det("person", 0.9), det("person", 0.3), det("dog", 0.99)]])
    rig.run()
    assert rig.detector.loaded == 1 and rig.source.open_calls == 1
    assert rig.notifier.calls == ["running"]  # type: ignore[attr-defined]
    ((frame, boxes, overlay),) = rig.annotator.calls
    assert frame is FRAME
    assert boxes == (det("person", 0.9),)  # only the selected detections are drawn
    assert overlay.frame_count == 1
    assert rig.encoder.encoded == [Frame(pixels="annotated")]
    (rendered,) = [e for e in rig.bus.events if isinstance(e, FrameRendered)]
    assert rendered.image == EncodedImage(data=b"jpeg", media_type="image/jpeg")
    assert rendered.snapshot.count_for(TARGET_CLASSES["person"]) == 1
    assert rendered.snapshot.timestamp is not None
    assert rendered.frame_number == 1
    assert rendered.fps == overlay.fps


def test_each_rendered_frame_carries_its_own_fps_counts_and_frame_number() -> None:
    rig = Rig([FRAME] * 3, detections=[[], [det("cup", 0.9)], []])
    rig.run()
    rendered = [e for e in rig.bus.events if isinstance(e, FrameRendered)]
    assert [r.frame_number for r in rendered] == [1, 2, 3]
    assert [r.snapshot.count_for(TARGET_CLASSES["cup"]) for r in rendered] == [0, 1, 0]
    assert rendered[1].fps == pytest.approx(1 / 0.03)


def test_frame_pacing_sleeps_30ms_after_each_frame_and_fps_uses_the_clock() -> None:
    rig = Rig([FRAME, FRAME, FRAME])
    rig.run()
    assert rig.clock.sleeps == [0.03, 0.03, 0.03]
    overlays = [o for _, _, o in rig.annotator.calls]
    assert [o.frame_count for o in overlays] == [1, 2, 3]
    assert overlays[1].fps == pytest.approx(1 / 0.03)


def test_paused_loop_sleeps_50ms_and_neither_reads_nor_detects() -> None:
    rig = Rig([FRAME])
    rig.signals.paused.set()
    sleeps_seen: list[float] = []
    original_sleep = rig.clock.sleep

    def sleep(seconds: float) -> None:
        original_sleep(seconds)
        sleeps_seen.append(seconds)
        if len(sleeps_seen) == 3:
            rig.signals.paused.clear()  # resume: the single scripted frame is then read

    rig.clock.sleep = sleep  # type: ignore[method-assign]
    rig.run()
    assert sleeps_seen == [0.05, 0.05, 0.05, 0.03]
    assert rig.source.reads.calls == 1


def test_stop_requested_before_the_loop_reads_nothing() -> None:
    rig = Rig([FRAME])
    rig.signals.stop.set()
    rig.run()
    assert rig.source.reads.calls == 0


def test_history_and_detection_log_only_every_30th_frame_with_a_detection() -> None:
    person = [det("person", 0.9)]
    detections: list[object] = [person if n in (10, 30, 60) else [] for n in range(1, 61)]
    detections[59] = []  # frame 60 has no detections: no append, no log
    rig = Rig([FRAME] * 60, detections=detections)
    rig.run()
    assert len(rig.repo.appended) == 1  # only frame 30: frame 10 is off-cadence, 60 has total 0
    snapshot = rig.repo.appended[0]
    assert snapshot.count_for(TARGET_CLASSES["person"]) == 1
    logs = [e for e in rig.bus.events if isinstance(e, DetectionLogged)]
    assert len(logs) == 1
    stamp = snapshot.timestamp
    assert stamp is not None
    assert logs[0].message == f"📦 [{stamp.strftime('%H:%M:%S')}] Persona:1"


def test_snapshot_timestamp_is_stamped_from_the_injected_clock() -> None:
    detections: list[object] = [[det("cup", 0.9)] if n == 30 else [] for n in range(1, 31)]
    rig = Rig([FRAME] * 30, detections=detections)
    rig.run()
    (snapshot,) = rig.repo.appended
    assert snapshot.timestamp is not None
    assert snapshot.timestamp.tzinfo is None
    elapsed = (snapshot.timestamp - FakeClock().now()).total_seconds()
    assert elapsed == pytest.approx(29 * 0.03)  # stamped at frame 30, after 29 pacing sleeps


def test_single_read_failure_is_retried_after_250ms_without_degrading() -> None:
    rig = Rig([FrameReadFailed("blip"), FRAME])
    rig.run()
    assert rig.clock.sleeps == [0.25, 0.03]
    assert rig.notifier.calls == ["running"]  # type: ignore[attr-defined]
    assert any(isinstance(e, LogEmitted) for e in rig.bus.events)


def test_failures_reaching_degrade_after_notify_degraded_then_recovery_on_success() -> None:
    rig = Rig([FrameReadFailed("a"), FrameReadFailed("b"), FRAME])
    rig.run()
    assert rig.clock.sleeps == [0.25, 0.5, 0.03]
    assert rig.notifier.calls == ["running", "degraded", "recovered"]  # type: ignore[attr-defined]


def test_success_resets_the_failure_counter() -> None:
    reads = [FrameReadFailed("a"), FRAME, FrameReadFailed("b"), FRAME]
    rig = Rig(reads)
    rig.run()
    assert rig.notifier.calls == ["running"]  # type: ignore[attr-defined]
    assert rig.clock.sleeps == [0.25, 0.03, 0.25, 0.03]


def test_exhausted_read_budget_faults_with_camera_unavailable_and_stops_retrying() -> None:
    rig = Rig([FrameReadFailed(str(n)) for n in range(1, 9)])
    rig.run()
    assert rig.clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]
    assert rig.notifier.calls == ["running", "degraded", "fault"]  # type: ignore[attr-defined]
    (fault,) = rig.notifier.faults  # type: ignore[attr-defined]
    assert isinstance(fault, CameraUnavailable)
    assert rig.source.reads.calls == 8


def test_inference_failures_follow_their_own_smaller_budget() -> None:
    boom = InferenceFailed("boom")
    rig = Rig([FRAME] * 3, detections=[boom, boom, boom])
    rig.run()
    assert rig.clock.sleeps == [0.25, 0.5]  # third failure exhausts: no further wait
    assert rig.notifier.calls == ["running", "degraded", "fault"]  # type: ignore[attr-defined]
    assert isinstance(rig.notifier.faults[0], InferenceFailed)  # type: ignore[attr-defined]
    assert not any(isinstance(e, FrameRendered) for e in rig.bus.events)


def test_inference_recovery_clears_degraded() -> None:
    boom = InferenceFailed("boom")
    rig = Rig([FRAME] * 3, detections=[boom, boom, []])
    rig.run()
    assert rig.notifier.calls == ["running", "degraded", "recovered"]  # type: ignore[attr-defined]


def test_camera_open_is_retried_with_backoff_before_running() -> None:
    err = CameraUnavailable("busy")
    rig = Rig([FRAME], opens=[err, err, None])
    rig.run()
    assert rig.source.open_calls == 3
    assert rig.clock.sleeps[:2] == [0.25, 0.5]
    assert rig.notifier.calls == ["running"]  # type: ignore[attr-defined]


def test_exhausted_open_budget_faults_without_ever_running() -> None:
    rig = Rig([FRAME], opens=[CameraUnavailable(str(n)) for n in range(8)])
    rig.run()
    assert rig.notifier.calls == ["fault"]  # type: ignore[attr-defined]
    assert isinstance(rig.notifier.faults[0], CameraUnavailable)  # type: ignore[attr-defined]
    assert rig.source.reads.calls == 0


def test_model_load_failure_faults_before_opening_the_camera() -> None:
    rig = Rig([FRAME], load_error=InferenceFailed("no weights"))
    rig.run()
    assert rig.notifier.calls == ["fault"]  # type: ignore[attr-defined]
    assert rig.source.open_calls == 0


def test_unexpected_failure_becomes_a_typed_fault_instead_of_killing_the_thread() -> None:
    rig = Rig([FRAME], encoder_error=EncodingFailed("bad jpeg"))
    rig.run()
    assert rig.notifier.calls == ["running", "fault"]  # type: ignore[attr-defined]
    assert isinstance(rig.notifier.faults[0], EncodingFailed)  # type: ignore[attr-defined]

    rig2 = Rig([FRAME], encoder_error=RuntimeError("surprise"))
    rig2.run()
    assert isinstance(rig2.notifier.faults[0], DepotVisionError)  # type: ignore[attr-defined]


def _with_controller(reads: Sequence[object]) -> tuple[Rig, SessionController]:
    bus = RecordingBus()
    rig = Rig(reads, bus=bus)
    controller = SessionController(
        bus=bus,
        repository=rig.repo,
        frame_source=rig.source,
        worker_factory=FakeWorker,
        stop_timeout_s=1.0,
    )
    rig.loop = CaptureLoop(
        source=rig.source,
        detector=rig.detector,
        annotator=rig.annotator,
        encoder=rig.encoder,
        repository=rig.repo,
        bus=bus,
        clock=rig.clock,
        notifier=controller,
        policy=CountingPolicy(),
        read_retry=READ_RETRY,
        inference_retry=INFER_RETRY,
    )
    assert controller.start()
    return rig, controller


def test_real_controller_sees_degraded_then_running_again() -> None:
    rig, controller = _with_controller([FrameReadFailed("a"), FrameReadFailed("b"), FRAME])
    rig.run()
    assert rig.bus.states() == [S.STARTING, S.RUNNING, S.DEGRADED, S.RUNNING]
    assert controller.state is S.RUNNING


def test_real_controller_ends_in_error_when_the_read_budget_is_exhausted() -> None:
    rig, controller = _with_controller([FrameReadFailed(str(n)) for n in range(8)])
    rig.run()
    assert controller.state is S.ERROR
    faults = [e for e in rig.bus.events if isinstance(e, SessionFault)]
    assert len(faults) == 1 and isinstance(faults[0].error, CameraUnavailable)
