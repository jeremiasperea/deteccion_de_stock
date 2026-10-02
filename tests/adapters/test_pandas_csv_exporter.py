"""PandasCsvExporter: schema, filename, atomic write and typed failure (FT5, FT6)."""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from tests.fakes import FakeClock

from depot_vision.adapters.pandas_csv_exporter import PandasCsvExporter
from depot_vision.domain.counting import TARGET_CLASSES, CountSnapshot
from depot_vision.domain.errors import ExportFailed
from depot_vision.ports import CountExporter

T1 = datetime(2026, 3, 4, 5, 6, 7)
T2 = datetime(2026, 3, 4, 5, 6, 8, 500000)


def _snap(raw: dict[str, int], timestamp: datetime | None = None) -> CountSnapshot:
    return CountSnapshot(counts={TARGET_CLASSES[k]: v for k, v in raw.items()}, timestamp=timestamp)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_conforms_to_count_exporter_port(fake_clock: FakeClock) -> None:
    assert isinstance(PandasCsvExporter(fake_clock), CountExporter)


def test_schema_has_every_class_column_plus_timestamp_with_zero_fill(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    history = [_snap({"person": 2}, T1), _snap({"cup": 1, "book": 3}, T2)]
    path = PandasCsvExporter(fake_clock).export(history, tmp_path)
    with path.open(newline="") as handle:
        header = next(csv.reader(handle))
    assert header == [*TARGET_CLASSES, "timestamp"]
    rows = _rows(path)
    assert rows[0]["person"] == "2" and rows[0]["cup"] == "0"
    assert rows[1]["cup"] == "1" and rows[1]["book"] == "3" and rows[1]["person"] == "0"
    assert all(row[name] != "" for row in rows for name in TARGET_CLASSES)


def test_timestamp_column_is_iso_8601(tmp_path: Path, fake_clock: FakeClock) -> None:
    path = PandasCsvExporter(fake_clock).export([_snap({}, T1), _snap({}, T2)], tmp_path)
    stamps = [row["timestamp"] for row in _rows(path)]
    assert stamps == [T1.isoformat(), T2.isoformat()]
    assert [datetime.fromisoformat(s) for s in stamps] == [T1, T2]


def test_unstamped_snapshot_falls_back_to_export_moment(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    path = PandasCsvExporter(fake_clock).export([_snap({"person": 1})], tmp_path)
    assert _rows(path)[0]["timestamp"] == fake_clock.now().isoformat()


def test_filename_uses_injected_clock(tmp_path: Path, fake_clock: FakeClock) -> None:
    path = PandasCsvExporter(fake_clock).export([_snap({"person": 1}, T1)], tmp_path)
    assert path == tmp_path / "conteo_20260101_000000.csv"
    assert path.exists()
    assert [p.name for p in tmp_path.iterdir()] == [path.name]


def test_creates_missing_destination_directory(tmp_path: Path, fake_clock: FakeClock) -> None:
    target = tmp_path / "nested" / "exports"
    path = PandasCsvExporter(fake_clock).export([_snap({"person": 1}, T1)], target)
    assert path.parent == target and path.exists()


def test_interrupted_write_leaves_destination_absent_and_no_temp(
    tmp_path: Path, fake_clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def partial_then_die(self: pd.DataFrame, path: str, **kwargs: object) -> None:
        Path(path).write_text("person,bottle\n1,")
        raise KeyboardInterrupt

    monkeypatch.setattr(pd.DataFrame, "to_csv", partial_then_die)
    with pytest.raises(KeyboardInterrupt):
        PandasCsvExporter(fake_clock).export([_snap({"person": 1}, T1)], tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_interrupted_write_keeps_previous_complete_destination(
    tmp_path: Path, fake_clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = PandasCsvExporter(fake_clock)
    destination = exporter.export([_snap({"person": 1}, T1)], tmp_path)
    previous = destination.read_text()

    def partial_then_die(self: pd.DataFrame, path: str, **kwargs: object) -> None:
        Path(path).write_text("person,bot")
        raise OSError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_csv", partial_then_die)
    with pytest.raises(ExportFailed):
        exporter.export([_snap({"person": 9}, T2)], tmp_path)
    assert destination.read_text() == previous
    assert list(tmp_path.iterdir()) == [destination]


def test_replace_failure_raises_export_failed_and_removes_temp(
    tmp_path: Path, fake_clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny(src: object, dst: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(os, "replace", deny)
    with pytest.raises(ExportFailed):
        PandasCsvExporter(fake_clock).export([_snap({"person": 1}, T1)], tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_unwritable_directory_raises_export_failed_without_partial_file(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("occupied")
    with pytest.raises(ExportFailed):
        PandasCsvExporter(fake_clock).export([_snap({"person": 1}, T1)], blocker / "exports")
    assert [p.name for p in tmp_path.iterdir()] == ["not_a_dir"]


def test_read_only_directory_raises_export_failed(tmp_path: Path, fake_clock: FakeClock) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        if os.access(locked, os.W_OK):
            pytest.skip("directory permissions are not enforced for this user")
        with pytest.raises(ExportFailed):
            PandasCsvExporter(fake_clock).export([_snap({"person": 1}, T1)], locked)
        assert list(locked.iterdir()) == []
    finally:
        locked.chmod(0o700)
