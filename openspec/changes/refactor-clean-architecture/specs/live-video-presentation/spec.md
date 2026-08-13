# Live Video Presentation Specification

## Purpose

Defines frame annotation/encoding, live feed rendering, and delivery of UI/session/log events without unbounded memory growth or silently swallowed failures.

## Requirements

### Requirement: Frame Rendering via src_bytes

The rendered frame MUST be assigned to the Flet `Image.src_bytes` property, and the image control MUST set `gapless_playback=True`. (FIX 1)

#### Scenario: Encoded frame assigned to src_bytes
- GIVEN an annotated frame has been JPEG-encoded to bytes
- WHEN the presentation layer updates the image control
- THEN the bytes MUST be assigned to `src_bytes`, not `src`, and `gapless_playback` MUST be `True`

#### Scenario: Mandatory user validation gate before Phase 6 (D3)
- GIVEN the Phase 5 presentation slice is complete
- WHEN the user runs the application on the target machine with a real camera
- THEN the user MUST confirm the live feed renders correctly before Phase 6 proceeds; this confirmation is a mandatory exit criterion, not an automated test

### Requirement: Terminating UI Drain Loop

At most one UI drain loop MUST be active at a time, and it MUST terminate when the session stops. (FIX 2)

#### Scenario: Repeated Start does not accumulate loops
- GIVEN a UI drain loop is already running
- WHEN Start is triggered again
- THEN the system MUST NOT start a second concurrent drain loop

#### Scenario: Drain loop exits on Stop
- GIVEN the session is stopping
- WHEN the drain loop observes the stop signal
- THEN it MUST exit within a bounded time rather than running as an unterminated loop

### Requirement: Bounded Event Queue With Type-Differentiated Overflow

The UI event queue MUST be bounded. On overflow, frame events MUST coalesce (only the most recent retained); session state events and log/detection events MUST NOT be dropped. (FT3, D2; replaces FIX 8)

#### Scenario: Frame overflow coalesces
- GIVEN the queue is at capacity and holds a pending frame event
- WHEN a new frame event arrives
- THEN the older frame event MUST be dropped and the new one retained

#### Scenario: State event is never dropped
- GIVEN the queue is at capacity
- WHEN a session state transition event arrives
- THEN the queue MUST accept it without dropping it or any other non-frame event

#### Scenario: Log or detection event is never dropped
- GIVEN the queue is at capacity
- WHEN a detection log event arrives
- THEN the queue MUST accept it without discarding it or any pending state event

### Requirement: DEGRADED Indicator Visibility

The UI MUST display a distinct, visible indicator while the session is `DEGRADED`, and MUST clear it on recovery. (D1)

#### Scenario: Indicator appears on DEGRADED
- GIVEN the session transitions to `DEGRADED`
- WHEN the UI receives the state-change event
- THEN a distinct DEGRADED indicator MUST become visible

#### Scenario: Indicator clears on recovery
- GIVEN the DEGRADED indicator is visible
- WHEN the session transitions back to `RUNNING`
- THEN the indicator MUST be cleared

### Requirement: FPS and Frame Counter Overlay

The rendered frame MUST display an FPS overlay and a running frame counter. (PRESERVE 7)

#### Scenario: Overlay present on every rendered frame
- GIVEN a frame has been annotated
- WHEN it is rendered
- THEN it MUST include the current FPS value and the frame counter

### Requirement: Detection Log Cadence

The system MUST emit a detection log entry every 30 processed frames when at least one target class was counted in that frame. (PRESERVE 8)

#### Scenario: Log emitted at cadence boundary
- GIVEN 30 frames have been processed since the last log entry and the current frame counted at least one object
- WHEN the 30th frame completes
- THEN a detection log entry MUST be emitted

#### Scenario: No log when nothing counted
- GIVEN the cadence boundary is reached but no object was counted in that frame
- WHEN the boundary is evaluated
- THEN no detection log entry MUST be emitted

### Requirement: No Silent UI Update Failures

`page.update()` failures MUST NOT be silently discarded. (FT6; replaces FIX 11)

#### Scenario: Update failure is observable
- GIVEN a `page.update()` call raises an exception
- WHEN the presentation layer handles it
- THEN the failure MUST be logged or re-raised as a typed exception, and MUST NOT be swallowed by a bare `except: pass`

### Requirement: Per-Class Bounding Box Colors

Each target class MUST be drawn with its existing fixed bounding-box color. (PRESERVE 3)

#### Scenario: Class renders with its assigned color
- GIVEN a detection for a target class
- WHEN the frame is annotated
- THEN the bounding box MUST use that class's existing assigned color
