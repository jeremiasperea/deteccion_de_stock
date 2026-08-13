# Count History & Export Specification

## Purpose

Defines accumulation of per-frame count snapshots into session history and their export to CSV, including atomicity, guarded access, and schema guarantees.

## Requirements

### Requirement: Guarded History Access

History MUST have a single owner for mutation; clear, append, and read MUST NOT interleave as an unsynchronized composite operation. (FT7; replaces FIX 4)

#### Scenario: Export reads a consistent snapshot
- GIVEN history is being appended to concurrently
- WHEN an export reads the history
- THEN it MUST read a consistent snapshot, never a partially cleared or partially appended list

#### Scenario: Clear does not race with append
- GIVEN a clear operation and an append operation are requested close together
- WHEN both are processed
- THEN one operation MUST complete fully before the other starts, never an interleaved partial state

### Requirement: CSV Schema

Exported CSV MUST have one column per target class plus an ISO 8601 `timestamp` column, with missing class values filled with `0`. (PRESERVE 4)

#### Scenario: Row has all class columns filled
- GIVEN a history entry counted only some target classes
- WHEN it is exported
- THEN every target class column MUST be present, with `0` for classes not counted in that entry

#### Scenario: Timestamp is ISO 8601
- GIVEN a history entry
- WHEN it is exported
- THEN its `timestamp` column MUST be formatted as ISO 8601

### Requirement: CSV Filename Format

Exported files MUST be named `conteo_YYYYMMDD_HHMMSS.csv` using the export moment. (PRESERVE 5)

#### Scenario: Filename matches format
- GIVEN an export is triggered
- WHEN the file is written
- THEN its name MUST match `conteo_YYYYMMDD_HHMMSS.csv` with the current date and time

### Requirement: Export Control Semantic

Export MUST write the currently accumulated history to a CSV file. (PRESERVE 6, export leg)

#### Scenario: Export triggers a write
- GIVEN history contains one or more entries
- WHEN Export is triggered
- THEN a CSV file containing that history MUST be written

### Requirement: Atomic CSV Write

Export MUST write to a temporary file and atomically replace the destination (e.g. `os.replace`), so an interrupted export never leaves a truncated destination file. (FT5; replaces FIX 6)

#### Scenario: Interrupted write leaves no truncated file
- GIVEN an export is interrupted after the temp file is partially written but before the atomic replace
- WHEN the interruption occurs
- THEN the destination CSV path MUST either not exist yet or still hold its previous complete contents

### Requirement: Configurable Export Destination

The export directory MUST be resolvable through configuration rather than hardcoded to `~/Desktop`. (FT8 partial; replaces FIX 5)

#### Scenario: Export uses configured directory
- GIVEN an export directory is supplied through configuration
- WHEN Export is triggered
- THEN the CSV MUST be written under that configured directory

#### Scenario: Export works without a Windows-only path
- GIVEN no `~/Desktop` directory exists on the host
- WHEN Export is triggered with a valid configured directory
- THEN the export MUST succeed

### Requirement: Export Failure is Typed

Export I/O failures MUST raise `ExportFailed` rather than failing silently. (FT6 partial)

#### Scenario: Write failure surfaces as ExportFailed
- GIVEN the configured export directory is not writable
- WHEN Export is triggered
- THEN the system MUST raise `ExportFailed` and MUST NOT leave a partially written destination file
