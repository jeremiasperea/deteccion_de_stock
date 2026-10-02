"""Fault normalization shared by the controller and the capture loop."""

from __future__ import annotations

from depot_vision.domain.errors import DepotVisionError


def as_fault(exc: Exception) -> DepotVisionError:
    """Return ``exc`` if already typed, else wrap it (keeping the original as ``__cause__``)."""
    if isinstance(exc, DepotVisionError):
        return exc
    wrapped = DepotVisionError(f"{type(exc).__name__}: {exc}")
    wrapped.__cause__ = exc
    return wrapped
