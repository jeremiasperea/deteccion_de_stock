# Proposal: Clean Architecture Refactor of the Stock Detection App

- **Change**: `refactor-clean-architecture`
- **Phase**: proposal
- **Baseline**: `193c577` (monolith), `a74c19c` (exploration)
- **Input**: `openspec/changes/refactor-clean-architecture/explore.md` (authoritative)
- **Risk level**: High (any slice touching `app.py` has zero test coverage today)

## Intent

`app.py` is a 438-line monolith where camera I/O, YOLO inference, counting rules, drawing, CSV export, threading and Flet UI are fused into two functions. Three concrete capabilities are blocked by that shape:

| Blocked capability | Why it is blocked today |
| --- | --- |
| Verify the counting rule without hardware | The business rule (10 target classes + confidence threshold) is interleaved line-by-line with `cv2` drawing calls |
| Swap or upgrade the detection model | `YOLO("yolov8n.pt")` is constructed inline, resolved against the current working directory |
| Run outside one Windows desktop | Export is hardcoded to `~/Desktop`; the venv is Windows-layout only |

A fourth driver is reliability: a single broad `except Exception` ends detection permanently on any failure, and Stop never joins the worker thread. The app can die silently and cannot report that it is degraded.

This refactor makes the domain testable, the infrastructure replaceable, and the runtime fault-tolerant — while fixing 11 confirmed defects that the exploration verified against the Flet 0.84 documentation and the source.

## Scope

### In Scope

1. **Phase 0 — toolchain**: Linux-native venv, pinned dependencies (Flet floor pinned to the version whose image API the code targets), `pytest`, `ruff`, `mypy`, CI. Strict TDD is unenforceable without it.
2. **Layered package** `src/depot_vision/` with domain, application, ports, adapters, presentation.
3. **Domain extraction**: counting policy, entities/value objects, typed domain exceptions.
4. **Ports and adapters** for every seam in the exploration's seam table.
5. **Application layer**: `SessionController` with an explicit state machine.
6. **Fault-tolerance requirements** (first-class, not cleanup) — see below.
7. **Presentation fix**: `src_bytes` + `gapless_playback=True`, one terminating UI drain loop, no silently swallowed `page.update()`.
8. **All 11 FIX items** from the exploration, each with a preceding RED test.
9. **`app.py` reduced to a thin entrypoint** delegating to the package.

### Out of Scope (explicit non-goals)

- No new features, screens, or UI redesign beyond what the FIX list requires.
- No model retraining, no new detection classes, no accuracy tuning.
- No change to the 8 PRESERVE items (classes, Spanish labels, emoji, colors, `0.4` default, CSV schema and filename format, control semantics, FPS/frame overlay, 30-frame log cadence).
- No packaging/distribution, installer, or telemetry work.
- No database; CSV stays the export format.

## Target architecture

Dependency rule: **all source dependencies point inward**. Domain knows nothing about `cv2`, `ultralytics`, `pandas`, or Flet.

```
presentation (Flet)  ─┐
adapters (cv2, YOLO, pandas, fs) ─┤──► ports (Protocols) ──► application ──► domain
```

| Layer | Contents | May import |
| --- | --- | --- |
| `domain` | `Frame`, `Detection`, `CountSnapshot`, `TargetClass`, counting policy, typed exceptions | stdlib only |
| `application` | `SessionController`, session state machine, event publishing, use cases | domain, ports |
| `ports` | `FrameSource`, `ObjectDetector`, `FrameAnnotator`, `FrameEncoder`, `CountRepository`, `CountExporter`, `EventBus`, `Clock`, `ConfigProvider` | domain |
| `adapters` | OpenCV capture, Ultralytics detector, pandas/atomic-CSV exporter, in-memory repository | ports, domain |
| `presentation` | Flet page, controls, event rendering | application, domain |

Session states: `IDLE`, `STARTING`, `RUNNING`, `PAUSED`, `DEGRADED`, `STOPPING`, `ERROR`. `DEGRADED` is the state the current two booleans cannot express: camera or inference failing while the app stays alive and observable.

## Fault-tolerance requirements (first-class scope)

| # | Requirement | Replaces |
| --- | --- | --- |
| FT1 | Retry with bounded backoff on camera open and frame read | FIX 7 — broad `except Exception` kills the worker |
| FT2 | Explicit session state machine including `DEGRADED` | two ad-hoc booleans |
| FT3 | Bounded UI event queue with a **type-differentiated** overflow policy (see Resolved Decisions D2) | FIX 8 — unbounded `list` |
| FT4 | Ordered shutdown: signal → drain → `thread.join(timeout)` → release camera | FIX 3 — Stop returns without joining |
| FT5 | Atomic CSV write (temp file + `os.replace`) | FIX 6 — truncated file on interruption |
| FT6 | Typed domain exceptions (`CameraUnavailable`, `InferenceFailed`, `ExportFailed`) with layer-appropriate handling | FIX 7, FIX 11 — catch-all and silent `pass` |
| FT7 | Guarded history access (single owner + snapshot reads) | FIX 4 — composite clear/append/read interleaving |
| FT8 | Package-relative model weights resolution and configurable export directory | FIX 9, FIX 5 — cwd and `~/Desktop` |

## Resolved Decisions

The proposal phase raised three product questions. The user answered them explicitly.
These are binding inputs for `sdd-spec` and `sdd-design` and override any earlier
wording in this document.

### D1 — `DEGRADED` is user-visible

The UI MUST surface a distinct indicator when the session is `DEGRADED` (camera or
inference failing while the app stays alive and retrying). Rationale: today the app
dies silently and the last successful frame stays frozen on screen, so an operator
cannot distinguish "no objects present" from "capture is dead". A fault-tolerance
requirement that is invisible to the operator does not protect the operator.

Affects: `capture-session`, `live-video-presentation`. Requires a spec requirement and
a test asserting the indicator appears on transition into `DEGRADED` and clears on
recovery.

### D2 — Type-differentiated queue overflow policy (supersedes "newest-wins")

FT3's overflow policy is differentiated by event type, not uniform:

| Event type | Overflow behavior |
| --- | --- |
| Frame events | **Coalesce** — only the most recent frame is retained; superseded frames are dropped |
| Session state events | **Never dropped** — the queue MUST NOT discard a state transition |
| Log / detection events | **Never dropped** — bounded by retention, not by overflow |

Rationale: a stale frame has no value on a live feed, but a discarded error log or a
lost state transition destroys the diagnostic trail that the whole fault-tolerance
effort exists to produce. If the queue must lose something, it loses pixels, never
evidence.

This supersedes the uniform newest-wins policy stated earlier in this proposal.

Affects: `live-video-presentation`, `capture-session`. The queue contract belongs in
`sdd-design`; the non-droppable guarantee belongs in the spec as a testable
requirement.

### D3 — `src_bytes` accepted as a behavior fix, with a user validation gate

The `src` → `src_bytes` correction is accepted as an explicit fix, not a preservation.
A visual difference in the live feed is acceptable. Phase 5 carries a **mandatory
validation gate**: the user runs the app on the target machine with a real camera and
confirms the feed renders correctly before Phase 6 proceeds.

Rationale: camera and model behavior cannot be verified in the development
environment. Deferring confirmation to the end would make it impossible to attribute a
regression to the phase that caused it.

Affects: `live-video-presentation`, Phase 5 exit criteria.

## Capabilities

### New Capabilities

- `detection-counting`: target classes, confidence threshold, count snapshot production (PRESERVE 1–2).
- `capture-session`: session lifecycle state machine, start/pause/stop semantics, retry/backoff, degraded operation, ordered shutdown (PRESERVE 6; FT1, FT2, FT4).
- `live-video-presentation`: frame annotation, encoding, `src_bytes` rendering, FPS/frame overlay, bounded UI event delivery, detection log cadence (PRESERVE 3, 7, 8; FIX 1, 2, 11; FT3).
- `count-history-export`: history accumulation, CSV schema and filename, atomic write, configurable destination (PRESERVE 4–5; FT5, FT7, FT8).
- `runtime-configuration`: resolution of confidence threshold, model weights path, export directory, queue bounds (FIX 5, 9; mechanism chosen in `sdd-design`).

### Modified Capabilities

- None. `openspec/specs/` is empty; this change creates the first specs.

## Approach

Domain-first, bottom-up extraction, executed as a **strangler fig** (exploration recommendation A-inside-B). `app.py` keeps running while responsibilities migrate one at a time into `src/depot_vision/`; monolith code is deleted only when its replacement is routed and tested. Parallel rewrite was rejected: with zero existing tests there is no oracle to diff old behavior against, and a single switchover exceeds the 400-line review budget by an order of magnitude.

### Phased slicing

Every phase is independently shippable, leaves the app runnable, and targets ≤400 changed lines (`auto-chain` delivery).

| Phase | Deliverable | Touches `app.py` | Runnable after |
| --- | --- | --- | --- |
| 0 | Toolchain: Linux venv, pinned deps, `pytest`, `ruff`, `mypy`, CI | No (only `requirements*.txt`) | Yes |
| 1 | Domain core: entities, value objects, counting policy, typed exceptions + unit tests | No | Yes |
| 2 | Port protocols + configuration resolution + tests | No | Yes |
| 3 | Adapters: capture (FT1), detector, annotator/encoder, repository, atomic exporter (FT5) against recorded fixtures | No | Yes |
| 4 | Application: `SessionController` state machine (FT2), bounded queue (FT3), ordered shutdown (FT4) | No | Yes |
| 5 | Presentation: Flet UI on the controller; FIX 1, 2, 11 | **Yes — high risk** | Yes |
| 6 | Strangler cleanup: `app.py` → thin entrypoint, delete dead monolith code, update docs | **Yes — high risk** | Yes |

Phase 0 is a hard prerequisite: no RED test can execute until it lands.

## Affected Areas

| Area | Impact | Description |
| --- | --- | --- |
| `app.py` | Modified → thin entrypoint | High risk: zero test coverage today. Untouched until Phase 5 |
| `src/depot_vision/**` | New | Layered package (domain, application, ports, adapters, presentation) |
| `tests/**` | New | Unit tests per layer; adapter tests against recorded fixtures |
| `requirements.txt` | Modified | Pinned floors; Flet pinned to the targeted image API |
| `pyproject.toml` / CI config | New | pytest, ruff, mypy, coverage configuration |
| `.venv/` | Replaced | Windows-layout venv replaced by a Linux-native one |

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Camera and model behavior cannot be verified in this environment | **High (certain)** | Adapter tests run against recorded fixtures; end-to-end verification requires the user to run the app on the target machine and confirm |
| `app.py` changes regress behavior undetected (zero coverage) | Medium | Phases 5–6 land last, after the PRESERVE list is covered by tests at lower layers; each is a separate revertible slice |
| Flet version pin mismatches the installed runtime | Medium | Phase 0 pins the floor and CI asserts the resolved version before Phase 5 uses `src_bytes` |
| `src_bytes` fix behaves differently on the user's machine than the current (unsupported) `src` assignment | Medium | Explicit spec requirement, not a silent cleanup; user confirmation required at Phase 5 |
| Strangler transitional shims linger as dead code | Low | Phase 6 explicitly deletes them; archive gate warns on destructive deltas |
| Toolchain rebuild blocked by network/dependency availability | Low | Phase 0 is standalone; failure blocks the change before any source is touched |

## Rollback Plan

1. **Per-slice**: every phase is one PR in the chain. `git revert` of that PR restores the previous runnable state; no phase depends on a later one.
2. **Phases 0–4**: `src/depot_vision/` is additive and unrouted. Deleting the package restores the exact `193c577` runtime path; `app.py` is byte-identical.
3. **Phase 5**: the highest-risk slice. Rollback is a single revert restoring the previous Flet wiring in `app.py`. Revert this slice alone before reverting 1–4.
4. **Phase 6**: reverting restores the monolith code paths alongside the package; the app stays runnable in either state.
5. **Toolchain**: `requirements.txt` and venv changes are revertible independently; the prior Windows venv is not deleted until Phase 6.

## Dependencies

- **Blocking**: Phase 0 toolchain (Linux-native venv + pinned deps + pytest). Strict TDD cannot produce a RED test before it.
- **User-bound**: end-to-end verification on the target machine with a real camera and `yolov8n.pt`.
- **Deferred to `sdd-design`**: configuration mechanism (env vars, config file, or CLI flags).

## Success Criteria

- [ ] `pytest` runs green in a Linux-native venv from a clean checkout.
- [ ] `ruff` and `mypy` pass on `src/depot_vision/`.
- [ ] The counting policy is unit-tested with no hardware, no I/O, and no mocks.
- [ ] `domain` imports no third-party package; the dependency rule is enforced by a test.
- [ ] All 8 PRESERVE items are covered by tests or explicit spec requirements.
- [ ] All 11 FIX items have a requirement and a test that failed before the fix.
- [ ] FT1–FT8 are each covered by a requirement and a test.
- [ ] Every PR in the chain is ≤400 changed lines and leaves the app runnable.
- [ ] The user confirms the app runs on the target machine with a live camera feed.
