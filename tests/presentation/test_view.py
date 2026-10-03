"""DepotVisionView: single drain loop, typed update failures, state-driven buttons."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest
from tests.fakes import FakeFrameSource, FakeRepository, FakeWorker, RecordingBus
from tests.presentation.fake_page import FakePage

from depot_vision.adapters.in_memory_repository import InMemoryCountRepository
from depot_vision.application.session_controller import SessionController
from depot_vision.domain.counting import TARGET_CLASSES, CountSnapshot
from depot_vision.domain.errors import ExportFailed, QueueOverflow, UiUpdateFailed
from depot_vision.domain.events import LogEmitted, SessionFault, SessionStateChanged
from depot_vision.domain.session import SessionState
from depot_vision.ports import CountRepository
from depot_vision.presentation.view import (
    MAX_CONSECUTIVE_UPDATE_FAILURES,
    DepotVisionView,
)

EXPORT_DIR = Path("/exports")


class FakeExporter:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[tuple[CountSnapshot, ...], Path]] = []
        self.error = error

    def export(self, history: Sequence[CountSnapshot], destination_dir: Path) -> Path:
        self.calls.append((tuple(history), destination_dir))
        if self.error is not None:
            raise self.error
        return destination_dir / "conteo_20260102_030405.csv"


class Harness:
    def __init__(
        self, *, repository: CountRepository | None = None, exporter: FakeExporter | None = None
    ):
        self.bus = RecordingBus()
        self.worker = FakeWorker()
        self.workers: list[FakeWorker] = []
        self.repository = repository or FakeRepository()
        self.exporter = exporter or FakeExporter()
        self.page = FakePage()
        self.controller = SessionController(
            bus=self.bus,
            repository=self.repository,
            frame_source=FakeFrameSource(),
            worker_factory=self._new_worker,
            stop_timeout_s=1.0,
            drain=lambda: self.view.pump(),
        )
        self.view = DepotVisionView(
            controller=self.controller,
            bus=self.bus,
            repository=self.repository,
            exporter=self.exporter,
            export_dir=EXPORT_DIR,
            drain_interval_s=0.001,
            now=lambda: datetime(2026, 1, 1, 12, 0, 0),
        )

    def _new_worker(self) -> FakeWorker:
        worker = FakeWorker()
        self.workers.append(worker)
        return worker

    def mount(self) -> FakePage:
        self.view.mount(self.page.as_page())
        return self.page

    def pump(self) -> None:
        self.view.pump()


def make_running(h: Harness) -> None:
    assert h.controller.start()
    assert h.controller.notify_running()
    h.pump()


# -- mount / single drain loop (5.8) ----------------------------------------


def test_mount_starts_exactly_one_drain_loop() -> None:
    h = Harness()
    page = h.mount()
    assert len(page.run_tasks) == 1
    assert page.run_tasks[0] == h.view.run_drain_loop


def test_remounting_does_not_start_a_second_loop() -> None:
    h = Harness()
    page = h.mount()
    h.view.mount(page.as_page())
    assert len(page.run_tasks) == 1


def test_repeated_start_never_starts_another_drain_loop() -> None:
    h = Harness()
    page = h.mount()
    for _ in range(3):
        asyncio.run(h.view.on_start(None))
        h.controller.notify_running()
        asyncio.run(h.view.on_stop(None))
    assert len(page.run_tasks) == 1


def test_drain_loop_exits_when_ui_stop_is_set() -> None:
    h = Harness()
    h.mount()

    async def scenario() -> None:
        task = asyncio.create_task(h.view.run_drain_loop())
        await asyncio.sleep(0)
        h.view.shutdown()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())


def test_page_close_handlers_signal_the_loop_to_stop() -> None:
    h = Harness()
    page = h.mount()
    assert page.on_close is not None and page.on_disconnect is not None

    async def scenario() -> None:
        task = asyncio.create_task(h.view.run_drain_loop())
        await asyncio.sleep(0)
        assert page.on_close is not None
        page.on_close(None)
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())


def test_mount_applies_page_chrome() -> None:
    h = Harness()
    page = h.mount()
    assert page.title == "Sistema de Conteo en Depósito"
    assert page.bgcolor == "#0d0d1a"
    assert (page.window.width, page.window.height) == (1200, 800)
    assert page.fonts == {"monospace": "Consolas"}
    assert len(page.controls_added) == 2  # header + body


# -- pump: render + one update per batch ------------------------------------


def test_pump_renders_events_with_one_page_update_per_batch() -> None:
    h = Harness()
    page = h.mount()
    h.bus.publish(LogEmitted("uno"))
    h.bus.publish(LogEmitted("dos"))
    h.pump()
    assert page.updates == 1
    assert len(h.view.targets.detect_log.controls) == 2


def test_pump_without_events_does_not_update_the_page() -> None:
    h = Harness()
    page = h.mount()
    h.pump()
    assert page.updates == 0


# -- page.update() failures (5.10) ------------------------------------------


def test_update_failure_is_logged_and_raised_as_typed_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = Harness()
    page = h.mount()
    boom = RuntimeError("socket closed")
    page.update_error = boom
    h.bus.publish(LogEmitted("x"))
    with caplog.at_level(logging.ERROR), pytest.raises(UiUpdateFailed) as info:
        h.pump()
    assert info.value.__cause__ is boom
    assert any("page.update() failed" in r.getMessage() for r in caplog.records)


def test_drain_loop_publishes_update_failure_then_gives_up_after_the_limit() -> None:
    h = Harness()
    page = h.mount()
    page.update_error = RuntimeError("gone")
    h.bus.publish(LogEmitted("x"))
    with pytest.raises(UiUpdateFailed):
        asyncio.run(h.view.run_drain_loop())
    assert page.updates == MAX_CONSECUTIVE_UPDATE_FAILURES
    faults = [e for e in h.bus.events if isinstance(e, SessionFault)]
    assert faults and isinstance(faults[0].error, UiUpdateFailed)


def test_drain_loop_recovers_when_update_succeeds_again() -> None:
    h = Harness()
    page = h.mount()
    page.update_error = RuntimeError("blip")
    h.bus.publish(LogEmitted("x"))

    async def scenario() -> None:
        task = asyncio.create_task(h.view.run_drain_loop())
        await asyncio.sleep(0)  # first batch fails once and is reported on the bus
        page.update_error = None
        h.bus.publish(LogEmitted("y"))

        async def recovered() -> None:
            while page.updates < 2:  # failed attempt + one successful batch
                await asyncio.sleep(0.001)

        await asyncio.wait_for(recovered(), timeout=5)
        assert not task.done()  # the loop survived the transient failure
        h.view.shutdown()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())


# -- give-up / bad-event resilience (F10) ----------------------------------


def test_drain_loop_give_up_stops_the_session_and_releases_the_worker() -> None:
    h = Harness()
    page = h.mount()
    make_running(h)
    page.update_error = RuntimeError("gone")
    h.bus.publish(LogEmitted("x"))
    with pytest.raises(UiUpdateFailed):
        asyncio.run(h.view.run_drain_loop())
    assert h.workers[0].stop_requested == 1
    assert h.controller.state is not SessionState.RUNNING


def test_drain_loop_unexpected_exception_stops_the_session() -> None:
    h = Harness()
    h.mount()
    make_running(h)

    def boom() -> list[object]:
        raise RuntimeError("bus broke")

    h.bus.drain = boom  # type: ignore[method-assign,assignment]
    with pytest.raises(RuntimeError):
        asyncio.run(h.view.run_drain_loop())
    assert h.workers[0].stop_requested == 1


def test_drain_loop_survives_a_failing_stop_during_give_up(
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = Harness()
    page = h.mount()
    page.update_error = RuntimeError("gone")
    h.bus.publish(LogEmitted("x"))

    async def bad_stop() -> bool:
        raise RuntimeError("stop broke")

    h.controller.stop = bad_stop  # type: ignore[method-assign]
    with caplog.at_level(logging.ERROR), pytest.raises(UiUpdateFailed):
        asyncio.run(h.view.run_drain_loop())
    assert any("stopping the session" in r.getMessage() for r in caplog.records)


def test_one_bad_event_is_isolated_faulted_and_the_batch_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = Harness()
    page = h.mount()
    real_render = h.view._renderer.render

    def flaky(event: object) -> None:
        if isinstance(event, LogEmitted) and event.message == "bad":
            raise ValueError("render broke")
        real_render(event)  # type: ignore[arg-type]

    h.view._renderer.render = flaky  # type: ignore[method-assign]
    h.bus.publish(LogEmitted("bad"))
    h.bus.publish(LogEmitted("good"))
    with caplog.at_level(logging.ERROR):
        h.pump()  # must not raise
    assert page.updates == 1
    assert len(h.view.detect_log.controls) == 1  # "good" rendered
    assert any(r.exc_info for r in caplog.records)
    faults = [e for e in h.bus.events if isinstance(e, SessionFault)]
    assert len(faults) == 1 and isinstance(faults[0].error, UiUpdateFailed)


def test_failing_fault_rendering_does_not_republish_endlessly() -> None:
    h = Harness()
    h.mount()

    def always_fails(event: object) -> None:
        raise ValueError("render broke")

    h.view._renderer.render = always_fails  # type: ignore[method-assign]
    h.bus.publish(LogEmitted("x"))
    published: list[object] = []
    real_publish = h.bus.publish

    def spy(event: object) -> None:
        published.append(event)
        real_publish(event)  # type: ignore[arg-type]

    h.bus.publish = spy  # type: ignore[method-assign]
    for _ in range(5):
        h.pump()
    assert len([e for e in published if isinstance(e, SessionFault)]) == 1


# -- QueueOverflow forwarding (T5b obligation) -------------------------------


def test_queue_overflow_fault_is_forwarded_to_the_controller_and_shuts_down() -> None:
    h = Harness()
    page = h.mount()
    make_running(h)
    h.bus.publish(SessionFault(QueueOverflow("ceiling")))
    h.pump()
    assert h.controller.state is SessionState.ERROR
    assert len(page.run_tasks) == 2  # drain loop + ordered-shutdown task
    asyncio.run(page.run_tasks[1]())
    assert h.controller.state is SessionState.IDLE
    assert h.workers[0].stop_requested == 1


def test_other_faults_are_not_forwarded() -> None:
    h = Harness()
    h.mount()
    make_running(h)
    h.bus.publish(SessionFault(ExportFailed("disk")))
    h.pump()
    assert h.controller.state is SessionState.RUNNING


# -- buttons driven by SessionStateChanged -----------------------------------


def _flags(h: Harness) -> tuple[bool, bool, str]:
    v = h.view
    return bool(v.btn_start.disabled), bool(v.btn_pause.disabled), str(v.btn_pause.content)


def test_initial_buttons_match_the_monolith() -> None:
    h = Harness()
    h.mount()
    assert _flags(h) == (False, True, "⏸ Pausar")
    assert h.view.btn_start.content == "▶ Iniciar"
    assert h.view.btn_stop.content == "⏹ Detener"
    assert h.view.btn_export.content == "💾 Exportar CSV"


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (SessionState.STARTING, (True, False, "⏸ Pausar")),
        (SessionState.RUNNING, (True, False, "⏸ Pausar")),
        (SessionState.DEGRADED, (True, False, "⏸ Pausar")),
        (SessionState.PAUSED, (True, False, "▶ Reanudar")),
        (SessionState.STOPPING, (True, True, "⏸ Pausar")),
        (SessionState.IDLE, (False, True, "⏸ Pausar")),
        (SessionState.ERROR, (False, True, "⏸ Pausar")),
    ],
)
def test_state_event_drives_start_and_pause_buttons(
    state: SessionState, expected: tuple[bool, bool, str]
) -> None:
    h = Harness()
    h.mount()
    h.bus.publish(SessionStateChanged(SessionState.PAUSED))  # dirty the pause label first
    h.bus.publish(SessionStateChanged(state))
    h.pump()
    assert _flags(h) == expected


# -- command handlers ---------------------------------------------------------


def test_start_click_starts_the_controller_and_resets_the_log() -> None:
    h = Harness()
    h.mount()
    h.bus.publish(LogEmitted("old"))
    h.pump()
    asyncio.run(h.view.on_start(None))
    assert h.controller.state is SessionState.STARTING
    assert h.workers[0].started == 1
    h.pump()
    assert h.view.btn_start.disabled is True and h.view.btn_pause.disabled is False
    texts = [c.value for c in h.view.targets.detect_log.controls]  # type: ignore[attr-defined]
    assert len(texts) == 1 and texts[0].endswith("⏳ Iniciando...")


def test_start_click_after_error_reaps_the_session_then_starts() -> None:
    h = Harness()
    h.mount()
    h.controller.start()
    h.controller.notify_fault(QueueOverflow("x"))
    assert h.controller.state is SessionState.ERROR
    asyncio.run(h.view.on_start(None))
    assert h.controller.state is SessionState.STARTING
    assert len(h.workers) == 2


def test_pause_click_toggles_pause_and_label() -> None:
    h = Harness()
    h.mount()
    make_running(h)
    asyncio.run(h.view.on_pause(None))
    h.pump()
    assert h.controller.state is SessionState.PAUSED
    assert h.view.btn_pause.content == "▶ Reanudar"
    asyncio.run(h.view.on_pause(None))
    h.pump()
    assert h.controller.state is SessionState.RUNNING
    assert h.view.btn_pause.content == "⏸ Pausar"


def test_stop_click_runs_the_async_controller_stop() -> None:
    h = Harness()
    h.mount()
    make_running(h)
    asyncio.run(h.view.on_stop(None))
    assert h.controller.state is SessionState.IDLE
    assert h.workers[0].stop_requested == 1
    h.pump()  # the drain loop's next tick renders the IDLE transition
    assert h.view.btn_start.disabled is False


# -- export -------------------------------------------------------------------


def test_export_with_empty_history_shows_the_no_data_snackbar() -> None:
    h = Harness()
    page = h.mount()
    h.view.on_export(None)
    assert page.snackbar_texts() == ["No hay datos para exportar aún."]
    assert h.exporter.calls == []


def test_export_writes_to_the_configured_dir_and_reports_the_filename() -> None:
    repo = InMemoryCountRepository()
    snap = CountSnapshot(counts={TARGET_CLASSES["person"]: 2})
    repo.append(snap)
    h = Harness(repository=repo)
    page = h.mount()
    h.view.on_export(None)
    assert h.exporter.calls == [((snap,), EXPORT_DIR)]
    assert page.snackbar_texts() == ["✅ Exportado: conteo_20260102_030405.csv"]
    assert page.dialogs[0].open is True


def test_export_failure_is_reported_in_a_snackbar_not_raised() -> None:
    repo = InMemoryCountRepository()
    repo.append(CountSnapshot(counts={TARGET_CLASSES["person"]: 1}))
    h = Harness(repository=repo, exporter=FakeExporter(error=ExportFailed("disk full")))
    page = h.mount()
    h.view.on_export(None)
    assert page.snackbar_texts() == ["❌ No se pudo exportar: disk full"]
