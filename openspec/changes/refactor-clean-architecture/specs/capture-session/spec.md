# Capture Session Specification

## Purpose

Defines the session lifecycle state machine owning camera capture and detection triggering, replacing the current two-boolean model with explicit, fault-tolerant states.

## Requirements

### Requirement: Explicit Session States

The system MUST represent session lifecycle as one of `IDLE`, `STARTING`, `RUNNING`, `PAUSED`, `DEGRADED`, `STOPPING`, `ERROR`, and MUST expose the current state as an observable value. (FT2)

#### Scenario: Start transitions to RUNNING
- GIVEN the session is `IDLE`
- WHEN Start is triggered and the camera opens successfully
- THEN the session state MUST become `RUNNING`

#### Scenario: Failure transitions to DEGRADED and is published
- GIVEN the session is `RUNNING`
- WHEN camera read or inference fails but the retry budget is not exhausted
- THEN the session state MUST become `DEGRADED` and a state-change event MUST be published (D1)

#### Scenario: Recovery clears DEGRADED
- GIVEN the session is `DEGRADED`
- WHEN a subsequent camera read and inference succeed
- THEN the session state MUST return to `RUNNING` and a state-change event MUST be published (D1)

### Requirement: Control Semantics

Start MUST open the camera and begin detection; Pause MUST freeze processing while leaving the camera open; Stop MUST close the camera. (PRESERVE 6)

#### Scenario: Pause keeps camera open
- GIVEN the session is `RUNNING`
- WHEN Pause is triggered
- THEN the state MUST become `PAUSED`, frame processing MUST stop, and the camera connection MUST remain open

#### Scenario: Stop closes camera
- GIVEN the session is `RUNNING` or `PAUSED`
- WHEN Stop is triggered
- THEN the camera MUST be released and the state MUST become `IDLE`

### Requirement: Retry With Bounded Backoff

On camera-open or frame-read failure, the system MUST retry with a bounded backoff instead of terminating detection permanently. (FT1; replaces FIX 7)

#### Scenario: Transient failure is retried
- GIVEN a camera read fails once
- WHEN the retry policy runs
- THEN the system MUST attempt at least one further retry within a bounded delay before declaring `DEGRADED`

#### Scenario: Exhausted retry budget stays observable
- GIVEN repeated camera failures exceed the retry budget
- WHEN the budget is exhausted
- THEN the system MUST stop retrying while keeping the session state observable rather than silently frozen

### Requirement: Ordered Shutdown

Stop MUST signal the worker, drain pending work, join the worker thread with a timeout, and only then release the camera — in that order. (FT4; replaces FIX 3)

#### Scenario: Stop joins the worker thread before releasing the camera
- GIVEN the session is `RUNNING`
- WHEN Stop is triggered
- THEN the worker thread MUST be joined (or the join MUST time out) before the camera is released, and Stop MUST NOT return earlier

### Requirement: Typed Fault Exceptions

Camera and inference failures MUST raise typed exceptions (`CameraUnavailable`, `InferenceFailed`) instead of being caught by one broad exception handler. (FT6; replaces FIX 7)

#### Scenario: Camera failure raises a typed exception
- GIVEN the camera fails to open
- WHEN the capture adapter is invoked
- THEN it MUST raise `CameraUnavailable`, and the application layer MUST handle it without terminating the process
