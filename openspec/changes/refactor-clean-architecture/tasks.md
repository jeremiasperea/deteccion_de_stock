# Tasks: Clean Architecture Refactor of the Stock Detection App

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~4500–5500 total across 7 phases (source + tests + fixtures + config) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | 12 work units (see table below), several phases split into `a`/`b` sub-units |
| Delivery strategy | auto-chain |
| Chain strategy | pending — see Delivery Reality Check |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Delivery Reality Check (blocking, resolve before `sdd-apply`)

This repository was `git init`-ed locally this session and **has no remote configured**. `auto-chain` assumes a forge capable of stacked PRs (base-branch targeting, PR review UI). Without a remote, "PR" is not yet a real artifact — only local sequential branches/commits are possible today.

- Phase/work-unit boundaries below are written as **slice boundaries**, valid as either stacked PRs (once a remote exists) or sequential local branches merged to `main` in order.
- **Orchestrator MUST resolve two things with the user before `sdd-apply`**: (1) which chain strategy — `stacked-to-main` or `feature-branch-chain` (design's own rollout text ["each phase is one stacked PR ≤400 lines, targeting the previous phase's branch, revertible independently"] matches `stacked-to-main` semantics, but the user has not confirmed it); (2) whether to add a remote now, defer PR creation until one exists, or proceed with local branch-per-slice only.
- `auto-chain`'s normal "No decision needed" default does not apply here because chain_strategy is unresolved and the delivery substrate (forge) does not exist yet.

### Per-Phase Line Estimate vs 400-line Budget

| Phase | Est. lines | Risk | Split needed |
|---|---|---|---|
| 0 — Toolchain | ~150–200 | Low | No |
| 1 — Domain core | ~800–1000 | **High** | Yes → 1a, 1b |
| 2 — Ports + config | ~300–400 | Medium | No (borderline) |
| 3 — Adapters | ~1000–1200 | **High** | Yes → 3a, 3b |
| 4 — Application | ~800–900 | **High** | Yes → 4a, 4b |
| 5 — Presentation | ~700–900 | **High** | Yes → 5a, 5b |
| 6 — Strangler cleanup | ~300–400 | Medium | No (borderline) |

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 0 | Toolchain: venv, pyproject, requirements, CI, freeze test | PR 0 | `pytest tests/architecture -q` | N/A — no runtime behavior yet | Delete `pyproject.toml`, `requirements.txt`, `.github/workflows/ci.yml`, `tests/architecture/` |
| 1a | `counting.py`, `detections.py`, `errors.py` | PR 1a | `pytest tests/domain/test_counting.py -q` | N/A — pure domain, no I/O | Delete `src/depot_vision/domain/{counting,detections,errors}.py` + tests |
| 1b | `retry.py`, `metrics.py`, `session.py`, `config.py`, `events.py`, dependency-rule test | PR 1b | `pytest tests/domain tests/architecture/test_dependency_rule.py -q` | N/A — pure domain, no I/O | Delete remaining `src/depot_vision/domain/**` + tests |
| 2 | `ports/__init__.py`, `layered_config_provider.py`, `depot_vision.ini.example` | PR 2 | `pytest tests/ports tests/adapters/test_layered_config_provider.py -q` | N/A — Protocols + config parsing only | Delete `src/depot_vision/ports/`, `layered_config_provider.py` |
| 3a | Capture + detector + clock adapters | PR 3a | `pytest tests/adapters/test_opencv_frame_source.py tests/adapters/test_ultralytics_detector.py tests/adapters/test_system_clock.py -q` | N/A — recorded fixtures only, no live camera | Delete the 3 adapter files + fixtures |
| 3b | Annotator, encoder, repository, exporter adapters | PR 3b | `pytest tests/adapters/test_cv2_annotator.py tests/adapters/test_cv2_encoder.py tests/adapters/test_in_memory_repository.py tests/adapters/test_pandas_csv_exporter.py -q` | N/A — golden-byte + `tmp_path` fixtures | Delete the 4 adapter files + fixtures |
| 4a | `session_controller.py` incl. ordered shutdown | PR 4a | `pytest tests/application/test_session_controller_transitions.py tests/application/test_session_controller_shutdown.py -q` | N/A — fake ports + `FakeClock` | Delete `session_controller.py` + tests |
| 4b | `capture_loop.py`, `bounded_event_bus.py` | PR 4b | `pytest tests/application/test_capture_loop.py tests/application/test_event_bus_queue.py -q` | N/A — fake ports + `FakeClock` | Delete `capture_loop.py`, `bounded_event_bus.py` + tests |
| 5a | `event_renderer.py`, `theme.py` | PR 5a | `pytest tests/presentation/test_event_renderer.py -q` | N/A — synthetic event streams | Delete `event_renderer.py`, `theme.py` + tests |
| 5b | `view.py`, `flet_app.py`, app.py rewiring + freeze-test deletion | PR 5b | `pytest tests/presentation -q` | **Yes — mandatory**: `python app.py` on target machine with real camera (D3 gate) | Revert `app.py` to Phase-4-end state; restores prior Flet wiring |
| G | D3 human validation gate | N/A (not a PR) | N/A | User confirms live feed on target machine | N/A — blocking checkpoint, not a code change |
| 6 | `app.py` → thin entrypoint, delete dead monolith code | PR 6 | `pytest -q` (full suite) | `python app.py` smoke run with real camera (informal re-confirmation) | Revert `app.py`; restores Phase-5-end state, package stays intact |

## Phase 0: Toolchain (blocking — no RED test can execute until this lands)

- [x] 0.1 **ORCHESTRATOR OVERRIDE — venv location changed.** Original text: "Create Linux-native venv (`python3.10 -m venv .venv`)". Do NOT do that: the existing `.venv/` is a Windows-layout virtualenv (`Scripts/`, `Lib/`, a PE32+ `python.exe`) and may be the user's real Windows runtime for the camera-dependent D3 gate; overwriting it is destructive and not recoverable from this repo. Instead created the Linux venv at **`.venv-linux/`**, left `.venv/` completely untouched, and added `.venv-linux/` to `.gitignore` (`.venv/` was already ignored).
- [x] 0.2 Create `pyproject.toml`: `pytest`, `ruff`, `mypy`, `coverage` config sections (Success Criteria). `mypy.files` intentionally omits `src` until Phase 1 creates `src/depot_vision/` (mypy hard-errors on a configured path that does not exist yet — Phase 1 must add `"src"` back to `tool.mypy.files`). `ruff.extend-exclude` excludes `app.py` — it is the frozen monolith (see 0.5), not in-scope for lint/format until Phase 5b lifts the freeze.
- [x] 0.3 **ORCHESTRATOR OVERRIDE — split install.** `requirements.txt` still pins everything per D-G (`flet>=0.84.0,<0.86.0` + floors for opencv-python/ultralytics/pandas/numpy), but only `flet` was installed into `.venv-linux/` in Phase 0 — `opencv-python`, `ultralytics`, `pandas`, `numpy` are multi-GB and not needed until Phase 3's adapters. Added **`requirements-dev.txt`** (`pytest`, `pytest-cov`, `ruff`, `mypy`) for the tooling actually installed now. **Phase 3 owns installing the heavy runtime stack** from `requirements.txt` before its adapter tasks (3.1+) begin.
- [x] 0.4 Create `.github/workflows/ci.yml`: `lint` (ruff), `typecheck` (mypy), `test` (pytest) jobs, each installing only `requirements-dev.txt` — not the heavy stack (Success Criteria)
- [x] 0.5 Write `tests/architecture/test_monolith_frozen.py` asserting `sha256(app.py)` equals the baseline digest `8f47847d27acb716451f6eef13ce4858941c4c713798886cd008dea8fbb3e7fe` (computed from `193c577:app.py`; the working tree matches — verified via `sha256sum app.py` vs `git show 193c577:app.py | sha256sum`). Literal is hardcoded, not recomputed at test time (app.py Decomposition table, Phase 0 row)
- [x] 0.6 Add CI job (`flet-capability`) + reusable `scripts/check_flet_capability.py` asserting that `Image.src` accepts `bytes` directly — a positive functional check (construct `ft.Image(src=b"...")`, assert the value survives as `bytes`), failing the build if it does not, and reporting the resolved Flet version (D-G, corrected). **Original assertion (`hasattr(ft.Image, "src_bytes")`) was based on a false premise — see `explore.md` section 1 — and failed unconditionally on every version in the pinned range; corrected to a functional check on `Image.src` itself, which now passes.**
- [x] 0.7 Verify: clean state → `.venv-linux/` → `pytest` runs green, `ruff` runs clean, `mypy` runs clean (Success Criteria). See verbatim command output in apply-progress / PR 0 description.

### Phase 0 Finding — D-G / Open Question 2, now resolved (was: falsified premise)

`scripts/check_flet_capability.py`'s original assertion (`hasattr(ft.Image, "src_bytes")`) failed against every Flet version actually resolvable in the pinned range, because the premise itself was false, not because of a real capability gap:

- Resolved version in `.venv-linux/`: **flet 0.85.3** (within the `>=0.84.0,<0.86.0` pin).
- `hasattr(ft.Image, "src_bytes")` → **`False`**. Also checked against `flet==0.84.0` (the pin floor) via a throwaway venv: same absence.
- Verified against the installed package source (not inferred, not from documentation): `Image.__init__` takes `src: Union[str, bytes]` directly — raw bytes are assigned straight to `src`. There is no separate `src_bytes` attribute in this Flet generation at all — it is not merely missing on this range, it never existed as a distinct field.
- `app.py:164`'s existing `img_ctrl.src = fb` (raw JPEG bytes) is therefore **already correct**, supported usage — not a defect. **FIX 1 is withdrawn.**
- **Resolution (supersedes the (a)/(b) decision this section originally deferred to Phase 5)**: option (a) — design against `Image.src = <bytes>` directly — is confirmed correct. The port already returns `EncodedImage(data, media_type)`, so only `presentation/event_renderer.py` is affected, and it needs no behavior change from what `app.py:164` already does. `gapless_playback=True` survives independently as **ENH-1** (see `explore.md` section 1, `proposal.md` D3).
- `scripts/check_flet_capability.py` is corrected to the positive functional check described in task 0.6 above and now **passes**.
- This resolves design Open Question 2; it is no longer open (see `design.md` D-G and Open Questions).

## Phase 1a: Domain core — counting, detections, errors

- [ ] 1.1 RED `tests/domain/test_counting.py`: known target class carries its Spanish label + emoji; non-target class excluded (detection-counting "Target Class Set and Display Labels"; PRESERVE 1)
- [ ] 1.2 GREEN: `domain/detections.py` (`BoundingBox`, `Detection`) + `domain/counting.py` (`TargetClass`, `TARGET_CLASSES`, `CountingPolicy` skeleton) to pass 1.1
- [ ] 1.3 RED `tests/domain/test_counting.py`: below-threshold detection discarded; default threshold `0.4` with no config (detection-counting "Confidence Threshold Filtering"; PRESERVE 2)
- [ ] 1.4 GREEN: implement threshold filtering + default in `CountingPolicy`
- [ ] 1.5 RED `tests/domain/test_counting.py`: `CountSnapshot` reflects filtered detections; same input twice ⇒ equal snapshots, no I/O/mocks (detection-counting "Count Snapshot Production")
- [ ] 1.6 GREEN: `CountSnapshot` dataclass + `CountingPolicy.apply()`
- [ ] 1.7 RED `tests/domain/test_errors.py`: typed exceptions exist and are distinct types (`CameraUnavailable`, `FrameReadFailed`, `InferenceFailed`, `ExportFailed`, `InvalidConfiguration`, `InvalidTransition`) (FT6, replaces FIX 7/11)
- [ ] 1.8 GREEN: `domain/errors.py`

## Phase 1b: Domain core — retry, metrics, session, config, events, dependency rule

- [ ] 1.9 RED `tests/domain/test_retry.py`: `delay_for`/`is_exhausted` match D-E schedule tables for camera (base 0.25s, cap 4.0s, 8 attempts, degrade after 2) and inference (0.25s/1.0s/3/2) (FT1; capture-session "Retry With Bounded Backoff")
- [ ] 1.10 GREEN: `domain/retry.py` `RetryPolicy`
- [ ] 1.11 RED `tests/domain/test_metrics.py`: `FpsMeter` computes FPS from monotonic timestamps (PRESERVE 7 support)
- [ ] 1.12 GREEN: `domain/metrics.py` `FpsMeter`
- [ ] 1.13 RED `tests/domain/test_session.py`: legal-transition table incl. `IDLE→STARTING→RUNNING`, `RUNNING↔DEGRADED`, ordered-shutdown states (FT2; capture-session "Explicit Session States")
- [ ] 1.14 GREEN: `domain/session.py` `SessionState` enum + transition table
- [ ] 1.15 RED `tests/domain/test_config.py`: `AppConfig.from_mapping` coercion/validation, defaults per D-A key table, `InvalidConfiguration` on bad input, `..` traversal in `model_weights` raises (D-A; runtime-configuration "Configurable Confidence Threshold"; Threat Matrix filesystem-input safeguard, FIX 9)
- [ ] 1.16 GREEN: `domain/config.py` `AppConfig` + `from_mapping`
- [ ] 1.17 RED `tests/domain/test_events.py`: `AppEvent` hierarchy + `EventClass` distinguish frame/state/log event kinds (supports D2, FT3)
- [ ] 1.18 GREEN: `domain/events.py`
- [ ] 1.19 RED `tests/architecture/test_dependency_rule.py`: ast-walk fails if any `domain/**` top-level import is outside stdlib/`depot_vision.domain` (D-F)
- [ ] 1.20 GREEN: fix any violating import until 1.19 passes; `domain/frames.py` (`PixelBuffer`, `Frame`, `EncodedImage`, `Overlay`)
- [ ] 1.21 Verify `tests/architecture/test_monolith_frozen.py` still green (app.py untouched)

## Phase 2: Ports + configuration resolution

- [ ] 2.1 RED `tests/ports/test_protocol_conformance.py`: in-memory fakes for all nine Protocols fail to import/conform before `ports/__init__.py` exists (D-B)
- [ ] 2.2 GREEN: `ports/__init__.py` — `FrameSource`, `ObjectDetector`, `FrameAnnotator`, `FrameEncoder`, `CountRepository`, `CountExporter`, `EventBus`, `Clock`, `ConfigProvider` exactly per D-B signatures
- [ ] 2.3 RED `tests/adapters/test_layered_config_provider.py`: CLI > env (`DEPOT_VISION_*`) > INI > default precedence via injected mapping, file search order `$DEPOT_VISION_CONFIG` → `./depot_vision.ini` → `~/.config/depot_vision/config.ini`, missing file is not an error (D-A)
- [ ] 2.4 GREEN: `adapters/layered_config_provider.py` — gathers string layers only, delegates coercion to `AppConfig.from_mapping`
- [ ] 2.5 RED `tests/domain/test_config.py`: package-relative `model_weights` resolves under `depot_vision/weights/`; absolute paths accepted and logged as override; `export_dir` defaults to `~` (D-A; runtime-configuration "Package-Relative Model Weights Resolution", FT8, FIX 9/5)
- [ ] 2.6 GREEN: implement resolution rules in `domain/config.py`
- [ ] 2.7 Create `depot_vision.ini.example` documenting all D-A config keys
- [ ] 2.8 Add `import-linter` `layers` contract to `pyproject.toml` (initial: `ports > domain`) (D-F, staged)
- [ ] 2.9 Verify freeze test + dependency-rule test still pass

## Phase 3a: Adapters — capture, detector, clock

- [ ] 3.1 Add `tests/fixtures/` recorded JPEG frames + serialized detection set
- [ ] 3.2 RED `tests/adapters/test_opencv_frame_source.py`: `open()` raises `CameraUnavailable`, `read()` raises `FrameReadFailed`, `close()` idempotent, against fixture-driven fakes (FT1)
- [ ] 3.3 GREEN: `adapters/opencv_frame_source.py`
- [ ] 3.4 RED `tests/adapters/test_ultralytics_detector.py`: `load()`/`detect()` raise `InferenceFailed` on failure; weights path resolved package-relative (FT8, FIX 9)
- [ ] 3.5 GREEN: `adapters/ultralytics_detector.py`
- [ ] 3.6 RED `tests/adapters/test_system_clock.py`: `now()`/`monotonic()`/`sleep()` wrap stdlib correctly; reused in a `FakeClock`-driven backoff integration test against `RetryPolicy` (D-B)
- [ ] 3.7 GREEN: `adapters/system_clock.py`
- [ ] 3.8 Verify freeze + dependency-rule tests still pass

## Phase 3b: Adapters — annotator, encoder, repository, exporter

- [ ] 3.9 RED `tests/adapters/test_cv2_annotator.py`: golden-byte annotation per target class with its existing fixed BGR color (live-video-presentation "Per-Class Bounding Box Colors"; PRESERVE 3)
- [ ] 3.10 GREEN: `adapters/cv2_annotator.py` + `CLASS_COLORS` BGR palette
- [ ] 3.11 RED `tests/adapters/test_cv2_encoder.py`: `encode()` produces golden bytes against a recorded fixture frame
- [ ] 3.12 GREEN: `adapters/cv2_encoder.py`
- [ ] 3.13 RED `tests/adapters/test_in_memory_repository.py`: single-writer `append`, `snapshot()` returns immutable tuple copy safe from any thread, `clear()` raises `InvalidTransition` when a worker is live (count-history-export "Guarded History Access"; FT7, FIX 4)
- [ ] 3.14 GREEN: `adapters/in_memory_repository.py`
- [ ] 3.15 RED `tests/adapters/test_pandas_csv_exporter.py`: temp-file + `os.replace`, interrupted write leaves destination absent or previous-complete; CSV has one column per target class + ISO 8601 `timestamp`, missing classes filled `0`; filename `conteo_YYYYMMDD_HHMMSS.csv` (count-history-export "Atomic CSV Write", "CSV Schema", "CSV Filename Format"; FT5, FIX 6; PRESERVE 4–5)
- [ ] 3.16 GREEN: `adapters/pandas_csv_exporter.py`
- [ ] 3.17 RED `tests/adapters/test_pandas_csv_exporter.py`: unwritable configured directory raises `ExportFailed`, no partial file left (count-history-export "Export Failure is Typed"; FT6)
- [ ] 3.18 GREEN: raise `ExportFailed` on write failure in the exporter
- [ ] 3.19 Verify freeze + dependency-rule tests still pass

## Phase 4a: Application — SessionController + ordered shutdown

- [ ] 4.1 RED `tests/application/test_session_controller_transitions.py`: full transition matrix incl. `DEGRADED` entry/exit, via fake ports (capture-session "Explicit Session States", "Control Semantics"; FT2; PRESERVE 6)
- [ ] 4.2 GREEN: `application/session_controller.py` state machine + `start`/`pause`/`stop` commands
- [ ] 4.3 RED `tests/application/test_session_controller_shutdown.py`: signal → drain → `join(timeout)` → release order; join-timeout branch retains orphan, locks out Start, later `stop()` reaps and closes (capture-session "Ordered Shutdown"; FT4, FIX 3)
- [ ] 4.4 GREEN: implement ordered shutdown + orphan handling via `loop.run_in_executor`
- [ ] 4.5 RED `tests/application/test_session_controller_history.py`: `clear()` legal only in `IDLE`/`ERROR` with no live worker; Start clears before spawning the thread (FT7, FIX 4)
- [ ] 4.6 GREEN: wire `CountRepository.clear()` guard into `start()`
- [ ] 4.7 Verify freeze + dependency-rule tests still pass

## Phase 4b: Application — capture loop + bounded event bus

- [ ] 4.8 RED `tests/application/test_capture_loop.py`: retry/backoff wiring on read/inference failure via `FakeClock`+`RetryPolicy`; failure ≥ `degrade_after` ⇒ `DEGRADED`; success resets counter and returns `RUNNING`; exhausted budget ⇒ `SessionFault(CameraUnavailable)` + `ERROR` (capture-session "Retry With Bounded Backoff", "Failure transitions to DEGRADED", "Recovery clears DEGRADED"; FT1)
- [ ] 4.9 GREEN: `application/capture_loop.py` worker body orchestration over ports
- [ ] 4.10 RED `tests/application/test_event_bus_queue.py`: frame lane coalesces (overwrite, capacity 1); state/log lanes never dropped; `QueueSaturated` at `soft_capacity` re-armed below half; `SessionFault(QueueOverflow)` at `hard_ceiling` (live-video-presentation "Bounded Event Queue With Type-Differentiated Overflow"; FT3, D2, FIX 8)
- [ ] 4.11 GREEN: `adapters/bounded_event_bus.py` — lock-guarded `deque` (durable) + single-slot frame reference
- [ ] 4.12 Extend `import-linter` `layers` contract to `application > ports > domain`, `adapters > ports > domain` (D-F)
- [ ] 4.13 Verify freeze + dependency-rule + import-linter tests still pass

## Phase 5a: Presentation — event rendering, theme, DEGRADED indicator

- [ ] 5.1 RED `tests/presentation/test_event_renderer.py`: `FrameRendered` → bytes assigned to `Image.src` (this is the existing `app.py:164` behavior, now confirmed correct on the pinned Flet — FIX 1 withdrawn, no separate `src_bytes` property exists), `gapless_playback=True` (live-video-presentation "Frame Rendering via Image.src (bytes)"; ENH-1)
- [ ] 5.2 GREEN: `presentation/event_renderer.py` (event → control mapping) + `presentation/theme.py`
- [ ] 5.3 RED `tests/presentation/test_event_renderer.py`: `SessionStateChanged(DEGRADED)` → distinct indicator visible; back to `RUNNING` → indicator cleared (live-video-presentation "DEGRADED Indicator Visibility"; D1)
- [ ] 5.4 GREEN: implement DEGRADED indicator in `event_renderer.py`
- [ ] 5.5 RED `tests/presentation/test_event_renderer.py`: FPS + frame-counter overlay on every rendered frame; detection log emitted every 30 frames only when count > 0 (live-video-presentation "FPS and Frame Counter Overlay", "Detection Log Cadence"; PRESERVE 7–8)
- [ ] 5.6 GREEN: wire `FpsMeter` + log-cadence rendering into `event_renderer.py`
- [ ] 5.7 Verify freeze + dependency-rule + import-linter tests still pass

## Phase 5b: Presentation — view wiring, drain loop, app.py rewiring

- [ ] 5.8 RED `tests/presentation/test_view.py`: UI drain loop starts exactly once at page mount (`_ui_loop_started` guard), not restarted by repeated Start (live-video-presentation "Terminating UI Drain Loop"; FIX 2)
- [ ] 5.9 GREEN: `presentation/view.py` — controls + single `while not self._ui_stop.is_set()` drain loop
- [ ] 5.10 RED `tests/presentation/test_view.py`: `page.update()` failure is logged/re-raised as typed exception, never bare `except: pass` (live-video-presentation "No Silent UI Update Failures"; FT6, FIX 11)
- [ ] 5.11 GREEN: wrap `page.update()` calls with typed-exception handling
- [ ] 5.12 GREEN (wiring): `presentation/flet_app.py`; rewire `app.py` `main()` (lines 64–249 rewired, 275–343 replaced) to build `SessionController` + all adapters via `layered_config_provider` and delegate to `flet_app.run()`
- [ ] 5.13 Delete `tests/architecture/test_monolith_frozen.py` (freeze lifted — explicit Phase 5 signal per design's app.py Decomposition table)
- [ ] 5.14 Extend `import-linter` `layers` contract to the full `presentation > adapters > ports > application > domain` chain (D-F, complete)
- [ ] 5.15 Verify: full `pytest` suite green, `ruff`/`mypy` clean on `src/depot_vision/**`

## Human Validation Gate (blocking — between Phase 5 and Phase 6)

- [ ] G.1 **[Human-performed, not automatable]** User runs the app on the target machine with a real camera; confirms the live feed and the rewired session controls (event bus, drain loop, `DEGRADED` indicator, `SessionController` wiring) behave correctly before Phase 6 proceeds (D3, rewritten rationale — the gate covers the Phase 5 presentation-layer rewiring, not an image-API behavior change, since FIX 1 is withdrawn; live-video-presentation "Mandatory user validation gate before Phase 6"). Phase 6 tasks MUST NOT start until this is explicitly confirmed.

## Phase 6: Strangler cleanup

- [ ] 6.1 RED `tests/test_entrypoint_smoke.py`: failing smoke test asserting `app.py` is only `from depot_vision.presentation.flet_app import run; run()` and building the page with fake ports succeeds — fails against Phase-5-end `app.py`, which still holds leftover monolith scaffolding
- [ ] 6.2 GREEN: rewrite `app.py` to the thin entrypoint; delete `detection_worker`, `AppState`, and module globals (Proposal "app.py reduced to a thin entrypoint")
- [ ] 6.3 Verify: entrypoint smoke test green, full `pytest` suite green, `ruff`/`mypy` clean
- [ ] 6.4 Update README/docs: package layout, `depot_vision.ini.example` usage, CI, note that the prior Windows `.venv/` is no longer used

## Key Learnings

1. Design's per-phase `app.py` decomposition table drove exact line-range traceability for every extraction task.
2. Domain, adapters, and application phases each independently exceed the 400-line budget once RED tests and fixtures are counted, forcing an `a`/`b` split within three of the seven phases.
3. `chain_strategy` cannot resolve to `stacked-to-main` by default here because the repository has no remote — the SDD guard's "pending" value exists precisely for this case.
4. The D3 human validation gate is structurally a blocking checklist item between two phases, not a task inside either phase, so it needed its own heading to stay visible.
