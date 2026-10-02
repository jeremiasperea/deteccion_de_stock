"""Minimal ``ft.Page`` stand-in: records what the view does, opens no window."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import flet as ft


class FakePage:
    def __init__(self) -> None:
        self.window = SimpleNamespace(width=None, height=None)
        self.title = ""
        self.bgcolor: str | None = None
        self.padding: Any = None
        self.fonts: dict[str, str] = {}
        self.controls_added: list[Any] = []
        self.updates = 0
        self.update_error: Exception | None = None
        self.run_tasks: list[Callable[..., Any]] = []
        self.dialogs: list[Any] = []
        self.on_close: Callable[..., Any] | None = None
        self.on_disconnect: Callable[..., Any] | None = None

    def add(self, *controls: Any) -> None:
        self.controls_added.extend(controls)

    def update(self) -> None:
        self.updates += 1
        if self.update_error is not None:
            raise self.update_error

    def run_task(self, handler: Callable[..., Any], *args: Any) -> None:
        self.run_tasks.append(handler)

    def show_dialog(self, dialog: Any) -> None:
        self.dialogs.append(dialog)

    def snackbar_texts(self) -> list[str]:
        return [str(d.content.value) for d in self.dialogs]

    def as_page(self) -> ft.Page:
        return cast(ft.Page, self)
