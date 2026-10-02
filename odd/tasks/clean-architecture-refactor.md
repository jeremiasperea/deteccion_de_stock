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
  T2: `refactor/ca-2-ports` (from `refactor/ca-1b-domain`).
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

### T3a — Adapters: capture, detector, clock (installs heavy runtime stack)
- [ ] 3.1–3.8

### T3b — Adapters: annotator, encoder, repository, exporter
- [ ] 3.9–3.19

### T4a — SessionController + ordered shutdown
- [ ] 4.1–4.7

### T4b — Capture loop + bounded event bus
- [ ] 4.8–4.13

### T5a — Presentation: renderer, theme, DEGRADED indicator
- [ ] 5.1–5.7

### T5b — View wiring, drain loop, app.py rewiring
- [ ] 5.8–5.15

### G — Human validation gate (user, real camera) — blocks T6
- [ ] G.1

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
  lint-imports. +120/-22.

## Next step

RDD assess on F3 commit, then T3a. T3a installs the heavy runtime stack
(opencv-python, ultralytics → torch, pandas, numpy; multi-GB) into `.venv-linux`.
T3a branch: `refactor/ca-3a-adapters` (from `refactor/ca-2-ports`).
