"""Pure mapping from domain events to Flet control mutations.

The renderer never calls ``page.update()``; the view owns update cadence.
Detection-log cadence (every 30 frames, count > 0) is enforced upstream by the
capture loop: this renderer shows every ``DetectionLogged`` it receives.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import flet as ft

from depot_vision.domain.counting import TARGET_CLASSES, CountSnapshot
from depot_vision.domain.events import (
    AppEvent,
    DetectionLogged,
    FrameRendered,
    LogEmitted,
    QueueSaturated,
    SessionFault,
    SessionStateChanged,
    ShutdownTimedOut,
)
from depot_vision.domain.session import SessionState
from depot_vision.presentation import theme

_RESET_STATES = frozenset({SessionState.IDLE, SessionState.ERROR})


@dataclass(frozen=True)
class RenderTargets:
    """The controls the renderer mutates."""

    image: ft.Image
    fps_text: ft.Text
    stats_col: ft.Column
    detect_log: ft.Column
    degraded_indicator: ft.Control


def _card(emoji: str, value: int, name: str, *, bg: str, border: str, color: str) -> ft.Container:
    center = ft.TextAlign.CENTER
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(emoji, size=20, text_align=center, color=color if emoji == "∑" else None),
                ft.Text(
                    str(value),
                    size=26,
                    weight=ft.FontWeight.BOLD,
                    color=color,
                    text_align=center,
                ),
                ft.Text(name, size=10, color=theme.LABEL, text_align=center),
            ],
            spacing=2,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=bg,
        border=theme.border_all(1, border),
        border_radius=theme.CARD_RADIUS,
        padding=ft.Padding(
            left=theme.CARD_PADDING,
            top=theme.CARD_PADDING,
            right=theme.CARD_PADDING,
            bottom=theme.CARD_PADDING,
        ),
        width=theme.CARD_WIDTH,
        animate=ft.Animation(theme.CARD_ANIMATION_MS, ft.AnimationCurve.EASE_OUT),
    )


def build_stat_cards(snapshot: CountSnapshot) -> list[ft.Control]:
    """One card per target class (domain order) followed by the TOTAL card."""
    cards: list[ft.Control] = []
    total = 0
    for target in TARGET_CLASSES.values():
        n = snapshot.count_for(target)
        total += n
        emoji, name = target.label.split(" ", 1)
        active = n > 0
        cards.append(
            _card(
                emoji,
                n,
                name,
                bg=theme.CARD_ACTIVE_BG if active else theme.CARD_INACTIVE_BG,
                border=theme.CARD_ACTIVE_BORDER if active else theme.CARD_INACTIVE_BORDER,
                color=theme.CARD_ACTIVE_TEXT if active else theme.CARD_INACTIVE_TEXT,
            )
        )
    cards.append(
        _card("∑", total, "TOTAL", bg=theme.TOTAL_BG, border=theme.TOTAL_BORDER, color=theme.GOLD)
    )
    return cards


class EventRenderer:
    def __init__(
        self,
        targets: RenderTargets,
        *,
        log_retention: int = 200,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._t = targets
        self._log_retention = log_retention
        self._now = now

    def render(self, event: AppEvent) -> None:
        if isinstance(event, FrameRendered):
            self._render_frame(event)
        elif isinstance(event, SessionStateChanged):
            self._render_state(event.state)
        elif isinstance(event, DetectionLogged):
            self._log(event.message, theme.LOG_DETECTION)
        elif isinstance(event, LogEmitted):
            self._log(event.message, theme.LOG_DEFAULT)
        elif isinstance(event, SessionFault):
            self._log(f"💥 {type(event.error).__name__}: {event.error}", theme.LOG_ERROR)
        elif isinstance(event, QueueSaturated):
            self._log(f"⚠️ Cola de eventos saturada (profundidad {event.depth})", theme.LOG_WARNING)
        elif isinstance(event, ShutdownTimedOut):
            self._log(
                f"⚠️ El hilo no finalizó en {event.timeout_s:g}s y quedó huérfano",
                theme.LOG_WARNING,
            )

    def _render_frame(self, event: FrameRendered) -> None:
        t = self._t
        t.image.src = event.image.data
        t.image.gapless_playback = True
        t.fps_text.value = f"⚡ {event.fps:.1f} FPS  •  🖼 Frame #{event.frame_number}"
        t.stats_col.controls = [
            ft.Row(build_stat_cards(event.snapshot), wrap=True, spacing=6, run_spacing=6)
        ]

    def _render_state(self, state: SessionState) -> None:
        t = self._t
        t.degraded_indicator.visible = state is SessionState.DEGRADED
        if state in _RESET_STATES:
            t.fps_text.value = theme.FPS_IDLE_TEXT
            t.image.src = theme.PLACEHOLDER_STOPPED

    def _log(self, message: str, color: str) -> None:
        stamp = self._now().strftime("%H:%M:%S.%f")[:-3]
        entry = ft.Text(
            f"[{stamp}] {message}",
            size=theme.LOG_FONT_SIZE,
            font_family=theme.LOG_FONT,
            color=color,
        )
        # Newest first; keep the most recent ``log_retention`` entries.
        self._t.detect_log.controls = [entry, *self._t.detect_log.controls][: self._log_retention]
