"""EventRenderer: domain events -> mutations of Flet controls (no Page needed)."""

from __future__ import annotations

from datetime import datetime

import flet as ft

from depot_vision.domain.counting import TARGET_CLASSES, CountSnapshot
from depot_vision.domain.errors import CameraUnavailable
from depot_vision.domain.events import (
    DetectionLogged,
    FrameRendered,
    LogEmitted,
    QueueSaturated,
    SessionFault,
    SessionStateChanged,
    ShutdownTimedOut,
)
from depot_vision.domain.frames import EncodedImage
from depot_vision.domain.session import SessionState
from depot_vision.presentation.event_renderer import EventRenderer, RenderTargets

FIXED_NOW = datetime(2026, 10, 2, 13, 5, 9, 123456)


def make_targets() -> RenderTargets:
    return RenderTargets(
        image=ft.Image(src="placeholder"),
        fps_text=ft.Text("⚡ -- FPS"),
        stats_col=ft.Column([ft.Text("Presioná Iniciar para comenzar.")]),
        detect_log=ft.Column([]),
        degraded_indicator=ft.Container(visible=False),
    )


def make_renderer(targets: RenderTargets, log_retention: int = 200) -> EventRenderer:
    return EventRenderer(targets, log_retention=log_retention, now=lambda: FIXED_NOW)


def snapshot(**counts: int) -> CountSnapshot:
    by_raw = {raw.replace("_", " "): n for raw, n in counts.items()}
    return CountSnapshot(counts={TARGET_CLASSES[raw]: n for raw, n in by_raw.items()})


def frame(
    data: bytes = b"\xff\xd8jpeg",
    snap: CountSnapshot | None = None,
    fps: float = 29.97,
    number: int = 7,
) -> FrameRendered:
    return FrameRendered(
        image=EncodedImage(data=data, media_type="image/jpeg"),
        snapshot=snap or snapshot(),
        fps=fps,
        frame_number=number,
    )


def test_frame_bytes_are_assigned_to_image_src() -> None:
    targets = make_targets()
    make_renderer(targets).render(frame(data=b"\xff\xd8abc"))
    assert targets.image.src == b"\xff\xd8abc"


def test_image_uses_gapless_playback() -> None:
    targets = make_targets()
    make_renderer(targets).render(frame())
    assert targets.image.gapless_playback is True


def test_degraded_state_shows_indicator() -> None:
    targets = make_targets()
    make_renderer(targets).render(SessionStateChanged(SessionState.DEGRADED))
    assert targets.degraded_indicator.visible is True


def test_recovery_to_running_clears_indicator() -> None:
    targets = make_targets()
    renderer = make_renderer(targets)
    renderer.render(SessionStateChanged(SessionState.DEGRADED))
    renderer.render(SessionStateChanged(SessionState.RUNNING))
    assert targets.degraded_indicator.visible is False


def test_stopping_or_error_also_clear_indicator() -> None:
    for state in (SessionState.STOPPING, SessionState.ERROR, SessionState.IDLE):
        targets = make_targets()
        renderer = make_renderer(targets)
        renderer.render(SessionStateChanged(SessionState.DEGRADED))
        renderer.render(SessionStateChanged(state))
        assert targets.degraded_indicator.visible is False, state


def test_fps_and_frame_counter_text_on_every_frame() -> None:
    targets = make_targets()
    renderer = make_renderer(targets)
    renderer.render(frame(fps=29.97, number=7))
    assert targets.fps_text.value == "⚡ 30.0 FPS  •  🖼 Frame #7"
    renderer.render(frame(fps=12.34, number=8))
    assert targets.fps_text.value == "⚡ 12.3 FPS  •  🖼 Frame #8"


def _cards(targets: RenderTargets) -> list[ft.Container]:
    (row,) = targets.stats_col.controls
    assert isinstance(row, ft.Row)
    return [c for c in row.controls if isinstance(c, ft.Container)]


def _card_texts(card: ft.Container) -> list[ft.Text]:
    assert isinstance(card.content, ft.Column)
    return [t for t in card.content.controls if isinstance(t, ft.Text)]


def test_stat_cards_follow_target_class_order_plus_total() -> None:
    targets = make_targets()
    make_renderer(targets).render(frame(snap=snapshot(person=2, cup=1)))
    cards = _cards(targets)
    assert len(cards) == 11
    names = [_card_texts(c)[2].value for c in cards]
    assert names == [t.label.split(" ", 1)[1] for t in TARGET_CLASSES.values()] + ["TOTAL"]
    emojis = [_card_texts(c)[0].value for c in cards[:10]]
    assert emojis == [t.label.split(" ", 1)[0] for t in TARGET_CLASSES.values()]
    assert _card_texts(cards[10])[0].value == "∑"


def test_active_card_uses_highlight_colors_and_inactive_uses_muted() -> None:
    targets = make_targets()
    make_renderer(targets).render(frame(snap=snapshot(person=2)))
    person, bottle, total = _cards(targets)[0], _cards(targets)[1], _cards(targets)[10]
    assert _card_texts(person)[1].value == "2"
    assert _card_texts(person)[1].color == "#4a9eff"
    assert person.bgcolor == "#1e3a5f"
    assert _border_color(person) == "#4a9eff"
    assert _card_texts(bottle)[1].value == "0"
    assert _card_texts(bottle)[1].color == "#555577"
    assert bottle.bgcolor == "#1a1a2e"
    assert _border_color(bottle) == "#2a2a4a"
    assert _card_texts(total)[1].value == "2"
    assert total.bgcolor == "#1e2a0a"
    assert _border_color(total) == "#f0b429"
    assert person.width == 88


def _border_color(card: ft.Container) -> str:
    assert card.border is not None and card.border.top is not None
    return str(card.border.top.color)


def _log_values(targets: RenderTargets) -> list[str]:
    return [c.value for c in targets.detect_log.controls if isinstance(c, ft.Text)]


def test_detection_logged_renders_entry_with_timestamp_and_style() -> None:
    targets = make_targets()
    make_renderer(targets).render(DetectionLogged("📦 [13:05:09] Persona:2"))
    (entry,) = targets.detect_log.controls
    assert isinstance(entry, ft.Text)
    assert entry.value == "[13:05:09.123] 📦 [13:05:09] Persona:2"
    assert entry.size == 11
    assert entry.font_family == "monospace"
    assert entry.color == "#aaffcc"


def test_log_lane_events_render_with_colors() -> None:
    targets = make_targets()
    renderer = make_renderer(targets)
    renderer.render(LogEmitted("hola"))
    renderer.render(SessionFault(CameraUnavailable("no camera")))
    renderer.render(QueueSaturated(depth=500))
    renderer.render(ShutdownTimedOut(timeout_s=5.0))
    texts = [c for c in targets.detect_log.controls if isinstance(c, ft.Text)]
    # newest first
    assert [t.color for t in texts] == ["#ffaa00", "#ffaa00", "#ff4444", "#aaaacc"]
    assert "5" in texts[0].value
    assert "500" in texts[1].value
    assert "no camera" in texts[2].value
    assert texts[3].value == "[13:05:09.123] hola"


def test_log_is_newest_first_and_bounded_by_retention() -> None:
    targets = make_targets()
    renderer = make_renderer(targets, log_retention=3)
    for i in range(5):
        renderer.render(LogEmitted(f"m{i}"))
    assert [v.split("] ")[1] for v in _log_values(targets)] == ["m4", "m3", "m2"]


def test_renderer_renders_every_detection_event_it_receives() -> None:
    # Cadence (every 30 frames, count > 0) is enforced upstream by the capture loop.
    targets = make_targets()
    renderer = make_renderer(targets)
    renderer.render(frame(number=1, snap=snapshot()))
    assert _log_values(targets) == []
    renderer.render(DetectionLogged("a"))
    renderer.render(DetectionLogged("b"))
    assert len(_log_values(targets)) == 2


def test_idle_resets_fps_text_and_shows_stopped_placeholder() -> None:
    targets = make_targets()
    renderer = make_renderer(targets)
    renderer.render(frame())
    renderer.render(SessionStateChanged(SessionState.IDLE))
    assert targets.fps_text.value == "⚡ -- FPS"
    assert targets.image.src == "https://placehold.co/640x480/0d0d1a/333366?text=Detenido"
