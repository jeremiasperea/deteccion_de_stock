"""Typed domain fault exceptions (FT6, replaces FIX 7/11).

Distinct exception types per failure mode, so the application layer can
handle each fault deliberately instead of a bare ``except Exception``.
"""

from __future__ import annotations


class DepotVisionError(Exception):
    """Base type for all typed depot_vision domain faults."""


class CameraUnavailable(DepotVisionError):
    """Raised when a FrameSource cannot be opened."""


class FrameReadFailed(DepotVisionError):
    """Raised when a FrameSource fails to read a frame."""


class InferenceFailed(DepotVisionError):
    """Raised when an ObjectDetector fails to load or run inference."""


class EncodingFailed(DepotVisionError):
    """Raised when a FrameEncoder cannot encode a frame."""


class ExportFailed(DepotVisionError):
    """Raised when a CountExporter fails to write its destination."""


class InvalidConfiguration(DepotVisionError):
    """Raised when configuration values fail coercion or validation."""


class InvalidTransition(DepotVisionError):
    """Raised on an illegal session or history state transition."""
