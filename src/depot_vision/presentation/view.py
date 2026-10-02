"""Flet view: builds the controls and owns the single UI drain loop (FIX 2, FIX 11).

The loop is started exactly once at page mount (``_ui_loop_started``), never by
Start, and ends only when ``_ui_stop`` is set at page teardown. Each batch is
drained from the bus, rendered by the ``EventRenderer`` and shown with a single
``page.update()``. A failing update is logged and raised as ``UiUpdateFailed``
(never swallowed); the loop reports it on the bus and gives up after
``MAX_CONSECUTIVE_UPDATE_FAILURES`` in a row.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import flet as ft

from depot_vision.application.session_controller import SessionController
from depot_vision.domain.errors import ExportFailed, QueueOverflow, UiUpdateFailed
from depot_vision.domain.events import (
    AppEvent,
    LogEmitted,
    SessionFault,
    SessionStateChanged,
)
from depot_vision.domain.session import SessionState
from depot_vision.ports import CountExporter, CountRepository, EventBus
from depot_vision.presentation import theme
from depot_vision.presentation.event_renderer import EventRenderer, RenderTargets

logger = logging.getLogger(__name__)

#: Drain cadence (monolith ``asyncio.sleep(0.03)``).
DRAIN_INTERVAL_S = 0.03
#: Consecutive failed ``page.update()`` calls after which the drain loop gives up.
MAX_CONSECUTIVE_UPDATE_FAILURES = 5

_S = SessionState
_BUSY_STATES = frozenset({_S.STARTING, _S.RUNNING, _S.DEGRADED, _S.PAUSED})
_PAUSE_LABEL = theme.BUTTON_PAUSE[0]
_RESUME_LABEL = "▶ Reanudar"


def _button(spec: tuple[str, str, str, str, str], *, disabled: bool = False) -> ft.Button:
    label, bg, hover_bg, text, border = spec
    return ft.Button(label, disabled=disabled, style=theme.button_style(bg, hover_bg, text, border))


class DepotVisionView:
    def __init__(
        self,
        *,
        controller: SessionController,
        bus: EventBus,
        repository: CountRepository,
        exporter: CountExporter,
        export_dir: Path,
        log_retention: int = 200,
        drain_interval_s: float = DRAIN_INTERVAL_S,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._controller = controller
        self._bus = bus
        self._repository = repository
        self._exporter = exporter
        self._export_dir = export_dir
        self._drain_interval_s = drain_interval_s
        self._page: ft.Page | None = None
        self._ui_stop = threading.Event()
        self._ui_loop_started = False
        self._shutdown_scheduled = False

        self.image = ft.Image(
            src=theme.PLACEHOLDER_START,
            width=640,
            height=480,
            fit=ft.BoxFit.CONTAIN,
            border_radius=8,
        )
        self.fps_text = ft.Text(
            theme.FPS_IDLE_TEXT, size=11, color=theme.MUTED, font_family=theme.LOG_FONT
        )
        self.stats_col = ft.Column(
            [ft.Text("Presioná Iniciar para comenzar.", size=12, color=theme.MUTED)], spacing=8
        )
        self.detect_log = ft.Column([], spacing=1, scroll=ft.ScrollMode.AUTO)
        self.degraded_indicator = ft.Container(
            content=ft.Text(theme.DEGRADED_LABEL, size=11, color=theme.DEGRADED_TEXT),
            bgcolor=theme.DEGRADED_BG,
            border=theme.border_all(1, theme.DEGRADED_BORDER),
            border_radius=6,
            padding=6,
            visible=False,
        )
        self.targets = RenderTargets(
            image=self.image,
            fps_text=self.fps_text,
            stats_col=self.stats_col,
            detect_log=self.detect_log,
            degraded_indicator=self.degraded_indicator,
        )
        self._renderer = EventRenderer(self.targets, log_retention=log_retention, now=now)

        self.btn_start = _button(theme.BUTTON_START)
        self.btn_pause = _button(theme.BUTTON_PAUSE, disabled=True)
        self.btn_stop = _button(theme.BUTTON_STOP)
        self.btn_export = _button(theme.BUTTON_EXPORT)
        self.btn_start.on_click = self.on_start
        self.btn_pause.on_click = self.on_pause
        self.btn_stop.on_click = self.on_stop
        self.btn_export.on_click = self.on_export

    # -- mounting -----------------------------------------------------------

    def mount(self, page: ft.Page) -> None:
        if self._ui_loop_started:
            return  # already mounted: never a second drain loop
        self._page = page
        page.title = "Sistema de Conteo en Depósito"
        page.bgcolor = theme.PAGE_BG
        page.window.width = 1200
        page.window.height = 800
        page.padding = 0
        page.fonts = {"monospace": "Consolas"}
        page.on_close = self._on_page_closed
        page.on_disconnect = self._on_page_closed
        page.add(self._header(), self._body())
        self._ui_loop_started = True
        page.run_task(self.run_drain_loop)

    def shutdown(self) -> None:
        """Ask the drain loop to exit (page teardown); not tied to Stop."""
        self._ui_stop.set()

    def _on_page_closed(self, _event: object = None) -> None:
        self.shutdown()

    # -- drain loop ---------------------------------------------------------

    async def run_drain_loop(self) -> None:
        failures = 0
        try:
            while not self._ui_stop.is_set():
                try:
                    self.pump()
                    failures = 0
                except UiUpdateFailed as exc:
                    failures += 1
                    self._bus.publish(SessionFault(error=exc))
                    if failures >= MAX_CONSECUTIVE_UPDATE_FAILURES:
                        logger.error("UI drain loop giving up after %d failed updates", failures)
                        raise
                await asyncio.sleep(self._drain_interval_s)
        except Exception:
            logger.exception("UI drain loop terminated unexpectedly")
            raise

    def pump(self) -> None:
        """Drain the bus, render the batch, then one ``page.update()``."""
        events = self._bus.drain()
        if not events:
            return
        for event in events:
            self._handle(event)
        self._update_page()

    def _handle(self, event: AppEvent) -> None:
        self._renderer.render(event)
        if isinstance(event, SessionStateChanged):
            self._apply_state(event.state)
        elif isinstance(event, SessionFault) and isinstance(event.error, QueueOverflow):
            self._controller.notify_fault(event.error)
            self._schedule_overflow_shutdown()

    def _apply_state(self, state: SessionState) -> None:
        self.btn_start.disabled = state in _BUSY_STATES or state is _S.STOPPING
        self.btn_pause.disabled = state not in _BUSY_STATES
        self.btn_pause.content = _RESUME_LABEL if state is _S.PAUSED else _PAUSE_LABEL

    def _schedule_overflow_shutdown(self) -> None:
        if self._page is None or self._shutdown_scheduled:
            return
        self._shutdown_scheduled = True
        self._page.run_task(self._shutdown_after_overflow)

    async def _shutdown_after_overflow(self) -> None:
        try:
            await self._controller.stop()
        finally:
            self._shutdown_scheduled = False

    def _update_page(self) -> None:
        if self._page is None:
            return
        try:
            self._page.update()
        except Exception as exc:
            logger.exception("page.update() failed")
            raise UiUpdateFailed(f"page.update() failed: {exc}") from exc

    # -- command handlers ---------------------------------------------------

    async def on_start(self, _event: object) -> None:
        if self._controller.state is _S.ERROR:
            await self._controller.stop()  # reap the failed session first
        if self._controller.start():
            self.detect_log.controls = []
            self._bus.publish(LogEmitted("⏳ Iniciando..."))

    async def on_pause(self, _event: object) -> None:
        self._controller.pause()

    async def on_stop(self, _event: object) -> None:
        await self._controller.stop()

    def on_export(self, _event: object) -> None:
        history = self._repository.snapshot()
        if not history:
            self._snackbar("No hay datos para exportar aún.")
            return
        try:
            path = self._exporter.export(history, self._export_dir)
        except ExportFailed as exc:
            logger.warning("CSV export failed: %s", exc)
            self._snackbar(f"❌ No se pudo exportar: {exc}")
            return
        self._snackbar(f"✅ Exportado: {path.name}")

    def _snackbar(self, message: str) -> None:
        if self._page is not None:
            self._page.show_dialog(ft.SnackBar(content=ft.Text(message), open=True))

    # -- layout (lifted from the monolith) -----------------------------------

    def _header(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                "DEPOT VISION",
                                size=20,
                                weight=ft.FontWeight.BOLD,
                                color=theme.ACCENT,
                                font_family=theme.LOG_FONT,
                            ),
                            ft.Text(
                                "Conteo y Clasificación en Depósito · YOLOv8 + Flet",
                                size=11,
                                color=theme.MUTED,
                            ),
                        ],
                        spacing=2,
                    )
                ]
            ),
            bgcolor=theme.HEADER_BG,
            padding=ft.Padding(left=20, top=12, right=20, bottom=12),
            border=ft.Border(bottom=ft.BorderSide(1, theme.HEADER_BORDER)),
        )

    def _body(self) -> ft.Container:
        cam_container = ft.Container(
            content=self.image,
            bgcolor=theme.CAMERA_BG,
            border=theme.border_all(1, theme.CAMERA_BORDER),
            border_radius=10,
            padding=4,
        )
        log_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "🛠 LOG DE SISTEMA", size=10, color=theme.MUTED, font_family=theme.LOG_FONT
                    ),
                    ft.Divider(height=1, color=theme.LOG_BORDER),
                    self.detect_log,
                ],
                spacing=4,
            ),
            bgcolor=theme.LOG_BG,
            border=theme.border_all(1, theme.LOG_BORDER),
            border_radius=8,
            padding=10,
            height=240,
        )
        right_panel = ft.Container(
            content=ft.Column(
                [
                    self.fps_text,
                    self.degraded_indicator,
                    ft.Divider(height=1, color=theme.LOG_BORDER),
                    ft.Text(
                        "OBJETOS DETECTADOS", size=10, color="#333355", font_family=theme.LOG_FONT
                    ),
                    self.stats_col,
                    ft.Divider(height=1, color=theme.LOG_BORDER),
                    log_container,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            bgcolor=theme.HEADER_BG,
            border=theme.border_all(1, theme.LOG_BORDER),
            border_radius=10,
            padding=14,
            expand=True,
        )
        buttons = ft.Row(
            [self.btn_start, self.btn_pause, self.btn_stop, self.btn_export], spacing=8
        )
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Column([cam_container, buttons], spacing=10), right_panel],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        expand=True,
                    )
                ],
                expand=True,
            ),
            padding=ft.Padding(left=14, top=14, right=14, bottom=14),
            expand=True,
        )
