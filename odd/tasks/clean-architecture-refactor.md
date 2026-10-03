# Feature: Clean Architecture Refactor (full scope)

## Objective

Decompose the `app.py` Flet + YOLOv8 + OpenCV monolith into a layered `depot_vision`
package (domain → ports → adapters → application → presentation) while preserving
observable behavior, and fix the concurrency/robustness defects of the monolith.

## Problem / Why

- `ui_loop` is spawned on every Start (N concurrent infinite drain loops).
- Unbounded `ui_queue` retains a JPEG closure per frame.
- Stop→Start race on global `state.cap` (old worker's `finally` can release the new camera).
- Export hardcoded to `~/Desktop`, no error handling; YOLO reloaded on every Start;
  `page.update()` failures silently swallowed.

## Scope

Full scope of the prior SDD change `openspec/changes/refactor-clean-architecture/`
(user chose "completo" on 2026-10-02 over a lean re-scope). That change's
`proposal.md`, `design.md` and `specs/**` remain the authoritative requirement
references; this document is the live checklist (ODD now drives execution).

## Constraints

- Strict TDD: ON — source `openspec/config.yaml` (`strict_tdd: true`). Runner:
  `.venv-linux/bin/pytest`. Observed RED before GREEN for every behavior.
- `app.py` stays byte-identical (freeze test) until task 5b.
- Domain imports only stdlib + `depot_vision.domain`.
- Artifacts in English. Conventional Commits, no AI attribution.
- `~400` authored lines per task is advisory only.

## Applicable checks

`.venv-linux/bin/pytest -q`, `.venv-linux/bin/ruff check .`, `.venv-linux/bin/mypy`.

## Delivery

- Branches: one per slice. T1b: `refactor/ca-1b-domain` (from `main` @ c5f2c01).
  T2 + F3: `refactor/ca-2-ports` (from `refactor/ca-1b-domain`).
  T3a: `refactor/ca-3a-adapters` (from `refactor/ca-2-ports`).
  T3b: `refactor/ca-3b-adapters` (from `refactor/ca-3a-adapters`).
  T4a: `refactor/ca-4a-controller` (from `refactor/ca-3b-adapters`).
  T4b: `refactor/ca-4b-loop` (from `refactor/ca-4a-controller`).
  T5a: `refactor/ca-5a-presentation` (from `refactor/ca-4b-loop`).
  T5b: `refactor/ca-5b-wiring` (from `refactor/ca-5a-presentation`).
- Strategy: `auto-chain` (inherited). Chain strategy: `stacked-to-main` (user choice
  2026-10-02): each PR targets the previous slice branch; merged to `main` in order.
- Forecast remaining: ~4000 authored lines.
- RDD: on (default).

## Done before ODD migration (SDD, on main)

Phase 0 (toolchain), 1a (counting/detections/errors), 1b tasks 1.9–1.14
(retry, metrics, session). Commits up to c5f2c01.

## Checklist

Task text and spec references: `openspec/changes/refactor-clean-architecture/tasks.md`.

### T1b — Finish domain core (route: delegated writer, trigger: 2+ non-trivial files)
- [x] 1.15/1.16 `domain/config.py` `AppConfig.from_mapping` (+ traversal guard)
- [x] 1.17/1.18 `domain/events.py`
- [x] 1.19/1.20 `tests/architecture/test_dependency_rule.py` + `domain/frames.py`
- [x] 1.21 freeze test green
- [ ] F1 follow-up: `ruff format` pre-existing drift in `tests/domain/test_counting.py`,
  `tests/architecture/test_monolith_frozen.py` (predates T1b; separate style commit)
- [ ] F2 follow-up (review suggestions): boundary coverage in `test_config.py`;
  prove relative-import rejection in `test_dependency_rule.py:58-62`.
  (Item 3, traversal guard vs absolute paths, resolved in T2.)
- [x] F3 follow-up (T2 review warnings, non-blocking) — done on `refactor/ca-2-ports`.
  Product decision (user, 2026-10-02): missing explicit `$DEPOT_VISION_CONFIG` keeps
  falling through, now with a logged warning. `argv` is now a required keyword-only
  parameter (composition root must pass `sys.argv[1:]`); names like `a:b` are rejected
  as drive-anchored. Original items:
  - `domain/config.py:107-117` Windows drive-relative / anchored weights names
    (`C:foo.pt`, `\foo.pt`) can escape the weights dir — tighten guard.
  - `layered_config_provider.py:64` `is_file()` `OSError`/`PermissionError` escapes
    untyped — wrap as `InvalidConfiguration`.
  - `layered_config_provider.py:55-65` explicit `$DEPOT_VISION_CONFIG` pointing to a
    missing file silently falls through — decide: error vs fallthrough (product call).
  - `layered_config_provider.py:71-73` INI without `[depot_vision]` section silently
    yields defaults — at least surface it.
  - `layered_config_provider.py:27-29` misleading parser name; `pyproject.toml:52-58`
    stale import-linter comment.
  - `layered_config_provider.py:41-42` empty `argv` default silently ignored the CLI.
- [ ] F4 follow-up (F3 review warnings, non-blocking): `from_mapping` key duplication
  (`config.py:139-160`); INI inline comments not stripped (`layered_config_provider.py:82`).
- [x] F5 follow-up: extend import-linter to adapters (done in 4.12).

Accepted T1b design choices (design.md left them open): `EventClass` = FRAME/STATE/LOG;
`SessionFault` and `QueueSaturated` classified LOG (durable lane per D-C); only FRAME
is droppable. Config validation runs in `__post_init__`; package-relative weights and
`export_dir` expansion deferred to T2 (2.5/2.6).

### T2 — Ports + config resolution (route: delegated writer; trigger: 6 new + 5 modified files)
- [x] 2.1–2.9 (F2 item 3 resolved: `..` guard applies only to relative weights names)

Accepted T2 choices: resolution is pure path math in domain (`resolve_model_weights` →
`ModelWeightsLocation(path, is_override)`; T3a detector adapter must log overrides);
`resolve_export_dir(home)`; INI section `[depot_vision]`; flags `--key-with-dashes`,
unknown flags ignored; missing `$DEPOT_VISION_CONFIG` falls through; new CI
`architecture` job runs `PYTHONPATH=src lint-imports`.

### T3a — Adapters: capture, detector, clock (route: delegated writer + inline fixes)
- [x] 3.1–3.8

Accepted T3a choices: capture/model factories injected (tests never touch a camera,
download weights, or run inference); ultralytics imported lazily; `FakeClock` in
`tests/fakes.py` (pytest `pythonpath` now `["src", "."]`); detector logs a warning on
absolute weights override; `SystemClock.now()` returns naive local time (preserves the
monolith's CSV timestamp format — writer's UTC choice reverted inline with RED→GREEN).
CI: new `requirements-ci.txt` (opencv-python-headless, numpy, flet) for `test` and
`typecheck` jobs; mypy override for missing `ultralytics`; `cast` instead of
`type: ignore` in the YOLO factory. Fixed pre-existing CI break: `typecheck` lacked
flet for `scripts/check_flet_capability.py`.

### T3b — Adapters: annotator, encoder, repository, exporter (route: delegated writer)
- [x] F6 capture leak in `OpenCVFrameSource.open()` when `set()`/`isOpened()` raises
- [x] 3.9–3.19

Design correction (parent, T3b): D-B's `FrameAnnotator.annotate(frame, snapshot,
overlay)` could not draw boxes (`CountSnapshot` has counts only). Port widened to
`annotate(frame, detections: Sequence[Detection], overlay)`; domain gained
`CountingPolicy.select()` (single home of the class + strict `> threshold` rule; `apply`
counts `select`'s output). Rejected alternative: adapter-only `draw_detections`
(application would depend on a concrete adapter).
Accepted T3b choices: optional `CountSnapshot.timestamp` stamped by the worker (T4b:
`dataclasses.replace(snapshot, timestamp=clock.now())`), exporter falls back to export
time; repository "worker live" is an injected predicate; encoder test compares decoded
pixels with tolerance (libjpeg builds differ), annotator uses exact pixel goldens
generated from verbatim `app.py` drawing code; `requirements-ci.txt` + pandas, mypy
`ignore_missing_imports` for pandas.

### T4a — SessionController + ordered shutdown (route: delegated writer + inline fix)
- [x] F7 (T3b review warnings): encoder raises typed `EncodingFailed` (new domain error,
  added inline RED→GREEN); annotator goldens fed from stored raw pixels
  (`frame_64x48_pixels.npy`), not a JPEG decode; `Overlay` docstring corrected.
- [x] 4.1–4.7

Accepted T4a choices: `stop()` is async (`begin_stop()` sync: STOPPING + signal; then
optional `drain` callback → `join(timeout)` via `run_in_executor` → release); illegal
commands return `False` without side effects; worker reports via `notify_running`,
`notify_degraded`, `notify_recovered`, `notify_fault(error)`; a fault from RUNNING/PAUSED
goes STOPPING → ERROR (table has no direct edge); a fault during STOPPING is only logged;
`ShutdownTimedOut` LOG event added (named in design, was missing); `worker_live()` is
true for current worker or any orphan — composition root wires it into the repository
via a lambda/holder; `stop_timeout_s` required kw-arg. Threads injectable through
`WorkerFactory`/`ThreadWorkerHandle` (application/worker.py).
TDD note: `ThreadWorkerHandle` was written before its test (deviation from strict TDD,
reported by the writer); its test is event-driven, no sleeps.

### T4b — Capture loop + bounded event bus (route: delegated writer)
- [x] F8 (T4a review warnings): `start()` no longer sticks in STARTING and `stop()` no
  longer wedges in STOPPING when collaborators raise (→ ERROR + `SessionFault`, never
  raises); `FakeClock.now()` naive like `SystemClock`.
- [x] 4.8–4.13 (closes F5: import-linter contract `application | adapters > ports >
  domain`, probes in both directions now break it)

Accepted T4b choices: commands report operational failures via `SessionFault` + return
value, never exceptions; a join that raised leaves the worker orphaned; exhaustion is
checked before sleeping (8 read failures sleep 15.75 s, not D-E's 19.75 s — no useless
final wait); inference exhaustion faults with `InferenceFailed` (3 attempts), model-load
failure faults immediately; separate read/inference counters; `QueueOverflow` error
added; bus notices re-arm on every `drain()`; retry sleeps not interruptible (worst case
4 s cap < 5 s default `stop_timeout_s`); no `CaptureLoopExited` event.
Design correction (parent, T4b): `FrameRendered` carries `snapshot`, `fps`,
`frame_number` with the image (one coalesced FRAME event feeds image, stats cards and
FPS text, as the monolith's single `_update_ui` closure).
T5b must: forward the bus's `SessionFault(QueueOverflow)` to `controller.notify_fault`.

### T5a — Presentation: renderer, theme, DEGRADED indicator (route: delegated writer)
- [x] 5.1–5.7 (import-linter: `presentation` added on top of the layers contract)

Accepted T5a choices: `RenderTargets(image, fps_text, stats_col, detect_log,
degraded_indicator)` + `EventRenderer(targets, log_retention=200, now=...)`; renderer
never calls `page.update()` (T5b view owns it); detection-log cadence enforced upstream
by the capture loop, renderer renders every `DetectionLogged`; log stamped from injected
`now`; IDLE/ERROR reset FPS text and placeholder (monolith `_restore`); log keeps
exactly 200 entries (monolith kept 201). Buttons are T5b.
Pending user confirmation (new UI copy, no monolith equivalent): `SessionFault` →
`💥 {ErrorType}: {msg}`; `QueueSaturated` → `⚠️ Cola de eventos saturada (profundidad N)`;
`ShutdownTimedOut` → `⚠️ El hilo no finalizó en Xs y quedó huérfano`; DEGRADED label →
`⚠️ Cámara degradada — reintentando...`.
Check at gate G.1: button hover bgcolor uses `ControlState.DEFAULT`/`HOVERED` keys
instead of the monolith's raw `""`/`"hovered"`.

### T5b — View wiring, drain loop, app.py rewiring (route: delegated writer)
- [x] F9 (T5a review warnings): ERROR reset now proven (mutation: removing ERROR from
  reset states fails a test); exact-string asserts for ShutdownTimedOut/QueueSaturated/
  SessionFault log lines.
- [x] 5.8–5.15 (`test_monolith_frozen.py` deleted; `app.py` delegates to
  `flet_app.run()` through a `sys.path` shim; dead monolith code stays until T6)

Accepted T5b choices: single drain loop started once at mount; `page.update()` failure
→ logged + `UiUpdateFailed` (new error) published as `SessionFault`, gives up after 5
consecutive failures; Start disabled while STOPPING; Start from ERROR first reaps via
`stop()`; bus `QueueOverflow` forwarded to `notify_fault` then `controller.stop()`
scheduled via `page.run_task`; buttons are `ft.Button` with `content` label (Flet
0.85.3 `ElevatedButton.text` assignment did not update the label — monolith's Pause
label toggle was likely broken).
T6 implications: `app.py` needs the `sys.path` shim (package not installed) unless T6
adds a build-system / editable install — T6.1's "only `from … import run; run()`"
wording must account for it. `extend-exclude = ["app.py"]` stays until T6.
Known gaps (not fixed): `target_fps` config unused (loop keeps fixed 0.03 s pacing);
monolith worker log lines ("Hilo de detección iniciado", "Cargando modelo", …) no longer
emitted; window close during a session does not stop it (same as monolith).
Weights: default `yolov8n.pt` resolves to `src/depot_vision/weights/yolov8n.pt` (dir
absent). Verified in ultralytics source (`utils/downloads.py` `attempt_download_asset` +
`safe_download` mkdir parents): missing asset is downloaded to that path; `*.pt` is
gitignored. Not exercised by a real download — confirm at G.1.
- [x] F10 (T5b review warnings): drain loop `finally` awaits `controller.stop()` on
  give-up or crash (skipped on orderly teardown; a failing stop is logged), so the
  worker is never left running without a UI; per-event `_handle` failures are isolated
  (logged, published as `SessionFault(UiUpdateFailed)`, batch continues); a failing
  `SessionFault` render is never republished (no feedback loop).
Pending user confirmation (new UI copy): `❌ No se pudo exportar: {error}`;
`⏳ Iniciando...` now default log color (monolith `#ffcc44`).

### G — Human validation gate (user, real camera) — blocks T6
- [ ] G.1 — attempt 1 (2026-10-03): launched on Windows (global Python 3.13, flet
  0.85.1, opencv 4.13.0, ultralytics 8.4.51, torch 2.11.0+cpu) with cwd `C:\Users\odinj`
  (a `\\wsl.localhost` cwd breaks the ultralytics import via `/etc/os-release`). Camera
  verified readable (640x480). Weights auto-downloaded to `src/depot_vision/weights/`.
  App exited 0 with no logged errors. **User reports it did not go well — failures not
  yet described; diagnosis pending.**
- [ ] F11 follow-up (F10 review warning): orderly-teardown branch of the drain-loop
  `finally` is untested (`view.py:166-167`).

### T6 — Strangler cleanup
- [ ] 6.1–6.4

## Progress / evidence

- 2026-10-02: branch created; `.venv-linux` recreated (python 3.12);
  baseline `pytest` 26 passed, `ruff` clean, `mypy` clean (15 files).
- T1b (route: delegated writer; trigger: 7 new non-trivial files): RED observed for
  config/events/frames (ModuleNotFoundError) and dependency rule (temporary numpy probe).
  `pytest` 70 passed, `ruff check` clean, `mypy` clean (22 files); parent spot check
  re-ran pytest + mypy. ~545 authored lines. Commit ef91954.
  RDD: assessed medium (slice_budget_reached) → consent granted → 1 lens (reliability)
  → approved, acknowledged, authority burned (lineage review-67e9229342a34cbf).
  Reviewed boundary advances to ef91954. Non-blocking suggestions logged as F2.
- T2: RED observed for ports (ImportError Clock), provider (ModuleNotFoundError),
  weights resolution (ImportError WEIGHTS_DIR), import-linter (temporary probe import).
  `pytest` 107 passed, `ruff check` clean, `mypy` clean (27 files), `lint-imports`
  1 kept / 0 broken; parent spot check re-ran pytest, mypy, lint-imports. ~560 lines.
  Commit f6b3f37. RDD: assessed high (shell_source in ci.yml) → granted → 4 lenses →
  approved, acknowledged, burned (lineage review-55ed1556adb5f5ad). Stop hook then
  required the accumulated range c5f2c01..f6b3f37 → granted → 4 lenses → approved,
  acknowledged, burned (lineage review-e73ad0ff504f4f16). Reviewed boundary: f6b3f37.
  Non-blocking warnings consolidated as F3.
- Doc commit baf47da re-triggered the stop hook on c5f2c01..baf47da → granted → 4 lenses
  → approved, acknowledged, burned (lineage review-a1073fac6ee2b9f5). Lesson: fold doc
  updates into work-unit commits; no standalone docs commits after a review.
- F3 (route: delegated writer; trigger: 5 non-trivial files): RED observed for Windows
  anchors (DID NOT RAISE), OSError probe (raw PermissionError), env/section warnings
  (caplog assert), required argv (DID NOT RAISE TypeError). `pytest` 117 passed, `ruff`
  clean, `mypy` clean (27 files), `lint-imports` 1 kept; parent re-ran pytest +
  lint-imports. +120/-22. Commit f646a1c (per-commit assess: medium, under_budget).
  Selectorless preflight then required accumulated c5f2c01..f646a1c → granted →
  4 lenses → approved, acknowledged, burned (lineage review-5f526048a9e7232e).
  New non-blocking warnings logged as F4.
- T3a: runtime stack installed in `.venv-linux` (torch CPU-only wheel: opencv 5.0.0,
  ultralytics 8.4.171, torch 2.14.1+cpu, numpy 2.5.2, pandas 3.0.6). RED observed for
  each adapter (ModuleNotFoundError) and for naive local `now()` (tzinfo assert).
  `pytest` 140 passed, `ruff check` clean, `mypy` clean (35 files), `lint-imports`
  1 kept — in `.venv-linux` AND a CI-like venv (dev + ci requirements only).
  ~560 authored lines. Commit 3af0f39. Accumulated c5f2c01..3af0f39 → granted →
  4 lenses → approved, acknowledged, burned (lineage review-6b4a2af3dceeaf41);
  warning on capture leak became F6 (fixed in T3b).
- T3b: RED observed for F6 (`capture.released` 0 == 1), each new adapter
  (ModuleNotFoundError), snapshot timestamp (AttributeError), `select` (AttributeError),
  widened port (mypy arg-type), annotator rewiring (10 golden failures), ExportFailed
  (temporary bare raise). `pytest` 183 passed, `ruff` clean, `mypy` clean (45 files),
  `lint-imports` 1 kept — both `.venv-linux` and CI-like venv; parent re-ran pytest + mypy.
  Commit 64464ec. Accumulated c5f2c01..64464ec → granted → 4 lenses (one slot re-run
  after a script dropped it; re-offered by bound STATUS) → approved, acknowledged,
  burned (lineage review-a129ce70f6400491). Warnings became F7.
- T4a: RED observed for F7a (2 failed), application modules (ModuleNotFoundError),
  `ShutdownTimedOut` (ImportError), fault-in-STOPPING rule, `EncodingFailed`
  (ImportError). `pytest` 253 passed ×4 runs (no flakiness), `ruff` clean, `mypy` clean
  (52 files), `lint-imports` 1 kept — both envs; parent re-ran full suite in both.
  `application/` imports only domain, ports and stdlib (grep-verified; contract in 4.12).
  Commit c9b741b. Accumulated c5f2c01..c9b741b → granted → 4 lenses → approved,
  acknowledged, burned (lineage review-7d65740fc8de9455). Warnings became F8.
- T4b: RED observed for F8a/b (raw exceptions escaped, 5 tests), F8c (tzinfo assert),
  capture loop + bus (ModuleNotFoundError), import-linter (old contract kept both probe
  violations), `FrameRendered` payload (10 TypeErrors). `pytest` 289 passed ×3,
  `ruff` clean, `mypy` clean (58 files), `lint-imports` 1 kept — both envs; parent
  re-ran pytest in both + lint-imports. Commit 0d3de8c.
  Accumulated c5f2c01..0d3de8c → granted → terminal stop
  `lens_context_budget_exceeded` (no authority created; cannot succeed on retry).
  Reduced scope per contract: c9b741b..0d3de8c → granted → 1 lens → approved,
  acknowledged, burned (lineage review-4017ac451bc0bbdb). From here on, review each
  work-unit commit against the last reviewed boundary.
- T5a: RED observed (ModuleNotFoundError; DEGRADED indicator 1 failed; FPS/cards/log
  8 failed). `pytest` 302 passed ×3, `ruff` clean, `mypy` clean (62 files),
  `lint-imports` 1 kept — both envs; parent re-ran pytest in both + lint-imports.
  Commit b16dbd4. Per-commit 0d3de8c..b16dbd4 → granted → 1 lens → approved,
  acknowledged, burned (lineage review-00cef51f1635871e); warnings became F9. Stop hook
  re-offered accumulated c5f2c01..b16dbd4 → granted → terminal
  `lens_context_budget_exceeded` again (exits: reduce scope — being done per commit —
  or user-chosen clone disable).
- T5b: RED observed for F9 (mutation tests), view and flet_app (ModuleNotFoundError).
  `pytest` 335 passed ×3, `ruff` clean, `mypy` clean (66 files), `lint-imports` 1 kept
  — both envs; import smoke opens no window; parent re-ran pytest in both, mypy,
  lint-imports. Commit cd00976. A power cut interrupted the first consent prompt; a
  fresh START was obtained → granted → 1 lens → approved, acknowledged, burned (lineage
  review-3eb8b9addc9864b0). Warnings became F10.
- F10: RED observed (worker never signalled `0 == 1`; missing stop-failure log;
  `ValueError: render broke` escaped `pump`). `pytest` 340 passed ×3, `ruff` clean,
  `mypy` clean (66 files), `lint-imports` 1 kept; CI-like venv recreated after the
  power cut (scratchpad wiped) — 340 passed, mypy clean, lint-imports 1 kept.

## Next step

Diagnose G.1 attempt 1 failures with the user, fix them, re-run G.1. T6 blocked until
G.1 passes. F10 reviewed per commit (lineage review-397162127bcb4ee0, approved, burned;
accumulated c5f2c01..da0d678 ended in terminal `lens_context_budget_exceeded`).
