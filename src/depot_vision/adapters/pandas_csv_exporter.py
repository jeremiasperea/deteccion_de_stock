"""``CountExporter`` adapter writing the history as CSV through pandas.

The write is atomic (FT5): rows go to a temp file in the destination directory
and ``os.replace`` swaps it in, so an interrupted export leaves the destination
absent or holding its previous complete contents. I/O failures surface as
``ExportFailed`` (FT6) and never leave a temp file behind.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from depot_vision.domain.counting import TARGET_CLASSES, CountSnapshot
from depot_vision.domain.errors import ExportFailed
from depot_vision.ports import Clock

FILENAME_FORMAT = "conteo_%Y%m%d_%H%M%S.csv"
TIMESTAMP_COLUMN = "timestamp"


class PandasCsvExporter:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def export(self, history: Sequence[CountSnapshot], destination_dir: Path) -> Path:
        exported_at = self._clock.now()
        destination = destination_dir / exported_at.strftime(FILENAME_FORMAT)
        frame = self._to_frame(history, exported_at.isoformat())
        temp_path: Path | None = None
        try:
            destination_dir.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(dir=destination_dir, prefix=".conteo_", suffix=".tmp")
            os.close(fd)
            temp_path = Path(temp_name)
            frame.to_csv(temp_path, index=False)
            os.replace(temp_path, destination)
            temp_path = None
        except OSError as exc:
            raise ExportFailed(f"could not export counts to {destination}: {exc}") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return destination

    @staticmethod
    def _to_frame(history: Sequence[CountSnapshot], fallback_timestamp: str) -> pd.DataFrame:
        rows = [
            {
                **{raw: snap.count_for(tc) for raw, tc in TARGET_CLASSES.items()},
                TIMESTAMP_COLUMN: (
                    snap.timestamp.isoformat() if snap.timestamp else fallback_timestamp
                ),
            }
            for snap in history
        ]
        return pd.DataFrame(rows, columns=[*TARGET_CLASSES, TIMESTAMP_COLUMN])
