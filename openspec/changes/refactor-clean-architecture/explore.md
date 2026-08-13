# Exploration — Clean Architecture Refactor

- **Change**: `refactor-clean-architecture`
- **Phase**: explore
- **Status**: complete
- **Baseline**: `193c577` (monolith), `42432bf` (SDD scaffold)
- **Subject**: `app.py`, 438 lines, single-file monolith

## 1. Flet API verification — confirmed defect

`app.py:164` assigns raw JPEG bytes to `Image.src`:

```python
_, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
frame_bytes = bytes(buf)
...
img_ctrl.src = fb          # fb is `bytes`
```

Verified against the official Flet documentation for v0.84.0 (`website/docs/controls/image.md`):

| Property | Accepted type | Purpose |
| --- | --- | --- |
| `src` | `str` | URL or asset path |
| `src_bytes` | `bytes` | in-memory image data |
| `src_base64` | `str` | base64-encoded image data |

`src` is typed as a URL/asset path string. Passing `bytes` to it is not a supported
contract in any documented Flet version. The initial value set at `app.py:276` is a
`https://placehold.co/...` URL, which confirms `src` is being used as a URL field —
and then reassigned with binary data every frame.

**Conclusion**: the live video feed is driven through an unsupported property
assignment. The presentation refactor therefore **fixes** behavior rather than
preserving it. This must be captured as an explicit spec requirement, not applied as
a silent cleanup.

**Correct target**: `src_bytes` for the encoded frame. Additionally,
`gapless_playback=True` is documented as the way to prevent flickering when the image
source changes repeatedly — directly applicable to a live camera feed and currently
unset.

**Secondary finding**: `requirements.txt` pins `flet>=0.21.0` while the module
docstring claims Flet 0.85.1. `src_bytes` is documented for the 0.84+ line; older
releases exposed `src_base64` only. An unpinned lower bound means the same source can
bind to two incompatible image APIs. The dependency floor must be pinned to a version
whose image API the code actually targets.

## 2. Testable seams

Each row is a responsibility currently fused into `detection_worker()` or `main()`.

| Responsibility | Current location | Hard dependency | Why untestable today | Minimal port |
| --- | --- | --- | --- | --- |
| Frame capture | `app.py:92-121` | `cv2.VideoCapture`, global `state.cap` | Requires real camera hardware; lifecycle owned by a module global | `FrameSource`: `open()`, `read() -> Frame`, `close()` |
| Inference | `app.py:88`, `app.py:123` | `ultralytics.YOLO`, cwd-relative weights | Loads a 6.5 MB model; cwd-dependent path | `ObjectDetector`: `detect(Frame) -> Sequence[RawDetection]` |
| Counting policy | `app.py:126-131` | none (pure logic) | Pure, but interleaved line-by-line with `cv2` drawing calls | `CountingPolicy`: `apply(detections) -> CountSnapshot` |
| Annotation / encoding | `app.py:132-151` | `cv2` drawing + `imencode` | Needs a real frame buffer; output never asserted | `FrameAnnotator`, `FrameEncoder` |
| History / export | `app.py:220-222`, `app.py:384-394` | `pandas`, filesystem, `~/Desktop` | Writes to a hardcoded user directory; no injectable path | `CountRepository.append(snapshot)`, `CountExporter.export(dest) -> Path` |
| UI update transport | `app.py:72-82`, `app.py:328-343` | `threading.Lock`, unbounded `list`, Flet controls | Worker constructs `Container`/`Column`/`Text` directly | `EventBus` publishing typed domain events |
| Session lifecycle | `app.py:345-382` | module-global flags | No explicit states; no join; no observable transitions | `SessionController` with an explicit state machine |

**Highest-value first extraction**: counting policy. It is already pure, it carries the
actual business rule (target classes + confidence threshold), and it can reach full
unit coverage with zero hardware, zero I/O, and no mocks. It is the natural RED/GREEN
entry point for Strict TDD.

**Proposed session states**: `IDLE`, `STARTING`, `RUNNING`, `PAUSED`, `DEGRADED`,
`STOPPING`, `ERROR`. The current code has only two booleans (`running`, `paused`),
which cannot express "camera failed but the app is still alive" — the single most
important state for fault tolerance.

## 3. Sequencing approaches

### A. Domain-first, bottom-up
Extract pure domain (entities, value objects, counting policy), then ports, then
adapters, then presentation. `app.py` keeps running untouched until late phases.

- **Pro**: every step is unit-testable without hardware or toolchain-heavy deps; matches
  Strict TDD naturally; slices are small and independently reviewable.
- **Con**: the app shows no user-visible improvement until the final phases.

### B. Strangler fig
Build `src/depot_vision/` alongside `app.py` and route one responsibility at a time
through the new package, deleting the corresponding monolith code as each route lands.

- **Pro**: the application stays runnable at every commit; rollback is per-slice.
- **Con**: a transitional adapter layer exists temporarily, which is extra code that
  will be deleted.

### C. Parallel rewrite behind a flag
Write the new implementation completely, then switch over.

- **Pro**: clean final result, no transitional shims.
- **Con**: **rejected**. With zero existing tests there is no oracle to diff old behavior
  against new. A single switchover PR also blows the 400-line review budget by an order
  of magnitude, defeating the agreed `auto-chain` delivery strategy.

### Recommendation: A executed inside B

Domain-first extraction, performed as a strangler fig. Rationale against this project's
actual constraints:

| Constraint | Why A-inside-B wins |
| --- | --- |
| Zero existing tests | Domain-first produces tests before it produces abstractions; correctness is established, not assumed |
| No working toolchain | Phase 0 blocks every approach equally, but A needs only `pytest` to start — no camera, no GPU, no model weights |
| 400-line review budget | Each port + adapter + its tests is a natural sub-400-line slice |
| `auto-chain` delivery | Slices form a linear dependency chain, which is exactly what stacked PRs express |

## 4. Preserve vs. fix boundary

This boundary is the contract the specs must encode. Everything in the FIX column
requires its own failing test first.

### PRESERVE — observable behavior that must not change

1. The ten COCO target classes, their Spanish display names, and their emoji.
2. Default confidence threshold `0.4` (becomes configurable; the default stays `0.4`).
3. Per-class bounding-box colors.
4. CSV schema: one column per detected class plus `timestamp` in ISO 8601, missing
   values filled with `0`.
5. CSV filename format `conteo_YYYYMMDD_HHMMSS.csv`.
6. Control semantics: Start opens the camera and begins detection; Pause freezes
   processing while the camera stays open; Stop closes the camera; Export writes the
   history.
7. FPS overlay and frame counter on the rendered frame.
8. Detection log entries emitted every 30 frames when at least one object is counted.

### FIX — current defects; each becomes a spec requirement with a RED test

1. `Image.src = bytes` → `src_bytes`, plus `gapless_playback=True` (section 1).
2. `app.py:372` — `page.run_task(ui_loop)` is re-invoked on every Start while `ui_loop`
   is an unterminated `while True`. Repeated Start/Stop cycles accumulate concurrent UI
   drain loops that never exit.
3. `app.py:381` — Stop sets a flag and returns; the worker thread is never joined, so
   shutdown completion is unobservable and camera release is unordered.
4. History mutation is unsynchronized as a **composite**: the worker appends
   (`app.py:220`) while the UI thread clears (`app.py:351`) and the export path reads the
   whole list (`app.py:392`). Individual `list.append` calls are atomic under the GIL;
   the clear/append/read interleaving is not.
5. `app.py:391` — export path hardcoded to `~/Desktop`, which does not exist on Linux or
   on non-English Windows installations.
6. `app.py:392` — non-atomic CSV write; an interrupted export leaves a truncated file.
7. `app.py:227` — a single broad `except Exception` wraps the entire worker: any failure
   terminates detection permanently, with no retry and no backoff on camera open or
   frame read.
8. `app.py:74` — the UI queue is an unbounded `list`. If the drain loop stalls, memory
   growth is unbounded. Needs a bounded queue with an explicit drop policy.
9. `app.py:88` — `YOLO("yolov8n.pt")` resolves relative to the current working
   directory; launching from any other directory fails.
10. `requirements.txt` lower bound conflicts with the documented target Flet version
    (section 1).
11. `app.py:340-342` — `page.update()` wrapped in `except Exception: pass`, silently
    discarding UI failures.

## 5. Correction to a prior assumption

An earlier statement in this session described `state.history.append` as an unprotected
race on its own. That is imprecise: `list.append` is atomic under CPython's GIL. The
actual defect is the **composite** clear/append/read interleaving described in FIX item
4. The defect is real; the mechanism stated originally was not exact.

## 6. Open questions for the proposal phase

1. **Toolchain rebuild is a hard prerequisite.** No Linux-native virtualenv exists and
   no project dependency is installed. Strict TDD cannot execute a single RED test until
   Phase 0 lands. This is a blocking dependency for every later phase.
2. **Runtime verification is hardware-bound.** Camera and model behavior cannot be
   verified in this environment. Adapter-level tests must run against recorded fixtures;
   end-to-end verification requires the user to run the app on the target machine.
3. **Configuration mechanism** — environment variables, a config file, or CLI flags —
   is an open design decision deferred to `sdd-design`.
