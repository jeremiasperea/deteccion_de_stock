# Detection & Counting Specification

## Purpose

Converts raw detector output into a countable, per-class inventory signal. Pure domain logic — no hardware, I/O, or mocks required to test it.

## Requirements

### Requirement: Target Class Set and Display Labels

The system MUST recognize exactly the ten target classes used today, each with its fixed Spanish display label and emoji. (PRESERVE 1)

#### Scenario: Known target class is labeled
- GIVEN a raw detection for one of the ten target classes
- WHEN the counting policy processes it
- THEN the resulting count entry MUST carry that class's exact Spanish label and emoji

#### Scenario: Non-target class is excluded
- GIVEN a raw detection for a COCO class outside the ten target classes
- WHEN the counting policy processes it
- THEN the detection MUST NOT appear in the count snapshot

### Requirement: Confidence Threshold Filtering

The system MUST discard raw detections below the active confidence threshold and MUST default that threshold to `0.4` when no configuration is supplied. (PRESERVE 2)

#### Scenario: Below-threshold detection discarded
- GIVEN a raw detection with confidence below the active threshold
- WHEN the counting policy processes it
- THEN the detection MUST NOT contribute to the count snapshot

#### Scenario: Default threshold applies without configuration
- GIVEN no confidence threshold is supplied by configuration
- WHEN the counting policy initializes
- THEN the active threshold MUST equal `0.4`

### Requirement: Count Snapshot Production

The system MUST produce a `CountSnapshot` mapping each target class to its count for one processed frame.

#### Scenario: Snapshot reflects frame detections
- GIVEN a frame's raw detections after class and confidence filtering
- WHEN the counting policy builds a snapshot
- THEN the snapshot MUST contain one count per target class present, and zero for target classes absent

#### Scenario: Snapshot production has no side effects
- GIVEN the same set of filtered detections
- WHEN the counting policy runs twice
- THEN both snapshots MUST be equal, with no hardware, I/O, or mock required to assert it
