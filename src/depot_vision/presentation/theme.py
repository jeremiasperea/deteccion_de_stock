"""Visual constants of the Depot Vision UI, lifted verbatim from the monolith."""

from __future__ import annotations

import flet as ft

# Page / surfaces
PAGE_BG = "#0d0d1a"
HEADER_BG = "#111128"
HEADER_BORDER = "#1e1e3a"
CAMERA_BG = "#0a0a18"
CAMERA_BORDER = "#1e1e3a"
LOG_BG = "#08080f"
LOG_BORDER = "#1e1e3a"

# Text
ACCENT = "#4a9eff"
MUTED = "#555577"
LABEL = "#8888aa"
GOLD = "#f0b429"

# Stat cards
CARD_WIDTH = 88
CARD_RADIUS = 10
CARD_PADDING = 8
CARD_ACTIVE_BG = "#1e3a5f"
CARD_ACTIVE_BORDER = ACCENT
CARD_ACTIVE_TEXT = ACCENT
CARD_INACTIVE_BG = "#1a1a2e"
CARD_INACTIVE_BORDER = "#2a2a4a"
CARD_INACTIVE_TEXT = "#555577"
TOTAL_BG = "#1e2a0a"
TOTAL_BORDER = GOLD
CARD_ANIMATION_MS = 200

# Log lane
LOG_FONT = "monospace"
LOG_FONT_SIZE = 11
LOG_DEFAULT = "#aaaacc"
LOG_OK = "#66ff99"
LOG_DETECTION = "#aaffcc"
LOG_WARNING = "#ffaa00"
LOG_ERROR = "#ff4444"
LOG_DIM = "#888899"

# Degraded indicator (new in the refactor; reuses the log warning amber)
DEGRADED_BG = "#3a2a00"
DEGRADED_BORDER = LOG_WARNING
DEGRADED_TEXT = LOG_WARNING
DEGRADED_LABEL = "⚠️ Cámara degradada — reintentando..."

# Copy shown on the image / fps text
FPS_IDLE_TEXT = "⚡ -- FPS"
PLACEHOLDER_START = "https://placehold.co/640x480/0d0d1a/333366?text=Presiona+Iniciar"
PLACEHOLDER_STOPPED = "https://placehold.co/640x480/0d0d1a/333366?text=Detenido"

# Buttons: (label, bg, hover bg, text, border)
BUTTON_START = ("▶ Iniciar", "#1a3a6a", "#1e4a8a", ACCENT, "#2a5aaa")
BUTTON_PAUSE = ("⏸ Pausar", "#1a2a1a", "#1e3a1e", "#44cc88", "#2a6a3a")
BUTTON_STOP = ("⏹ Detener", "#2a1a1a", "#3a1e1e", "#ff6644", "#6a2a2a")
BUTTON_EXPORT = ("💾 Exportar CSV", "#1a1a0a", "#2a2a0e", GOLD, "#6a5a0a")


def border_all(width: float, color: str) -> ft.Border:
    side = ft.BorderSide(width, color)
    return ft.Border(top=side, bottom=side, left=side, right=side)


def button_style(bg: str, hover_bg: str, text: str, border: str) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor={ft.ControlState.DEFAULT: bg, ft.ControlState.HOVERED: hover_bg},
        color=text,
        shape=ft.RoundedRectangleBorder(radius=6),
        side=ft.BorderSide(1, border),
    )
