# UGAS v0.12.0 - Local Realtime Observability Dashboard MVP

## 1. Final HEAD and commit list

Required starting HEAD: `bc1252992ff5b38096b7e9bd58b5ffe5cee41ffc`.

Final HEAD, commit list and publication verification are recorded in `docs/evidence/observability-v0120/publication.json` after the final commit. The review index is built before publication and its build HEAD must be an ancestor of the published HEAD.

## 2. Summary of implementation

Implemented a Python-first local observability service with structured events, bounded SQLite WAL persistence, a memory fallback, one-second system/process sampling, safe NVIDIA/ComfyUI probes, allowlisted filesystem activity, image/GIF/WebP previews, read-only JSON endpoints, SSE reconnect snapshots, generic CLI command instrumentation and generation job stages, plus a static responsive dark operations dashboard.

## 3. External visual approval recorded

`docs/evidence/observability-v0120/external-review-v0112.json` is a new immutable entry recording the supplied external decision `APPROVED_PILOT` for the exact v0.11.2 12-frame 512x512 GIF, byte-identical to v0.11.0. This is pilot/pipeline approval only. `production_approved=false` and `production_routing=BLOCKED`; the v0.12.0 dashboard itself remains `REQUIRED` for external review.

## 4. Files added/changed

The new implementation is under `src/ugas/observability/`; the CLI boundary is in `src/ugas/cli.py` and generation stages emit events from `src/ugas/generation.py`. Static assets are `index.html`, `dashboard.css` and `dashboard.js`. Validation, canonical state, schemas, evidence, tests and version surfaces are listed in the v0.12.0 review index.

## 5. Architecture and dependencies

The runtime remains Python >=3.10 with the existing Pillow dependency. No frontend build chain, CDN, remote font, Prometheus, Grafana, Redis, PostgreSQL or new runtime dependency was added. The server uses the Python standard library `ThreadingHTTPServer`, `sqlite3`, `urllib`, `ctypes` and `subprocess`.

## 6. Event model/store

`TelemetryEvent` contains a monotonic-in-process UTC timestamp, UUID event ID, category, severity, source, action, status, message, optional job/asset IDs and bounded JSON metadata. Categories include system, process, command, job, stage, file, asset, qa, provider, error and governance. SQLite is stored at `.ugas/runtime/telemetry.db`, uses WAL/NORMAL mode, indexes and bounded row retention; store failure degrades to a bounded in-memory queue and is surfaced by the API.

## 7. System/GPU collector and fallbacks

CPU, logical CPU count, RAM and repository-volume disk values are collected with platform APIs/standard library. NVIDIA is queried with an explicit `nvidia-smi` argument array and a short timeout; missing executable, timeout, malformed output and non-zero exit return `GPU_UNAVAILABLE` with a reason. GPU values are never fabricated as zero. Optional process RSS/CPU metrics use psutil when present and partial platform fallbacks otherwise. ComfyUI is checked only through the read-only `/system_stats` endpoint with a short timeout.

## 8. Job/CLI instrumentation

Every `ugas` invocation emits command started/completed/failed events. The generation job boundary emits job started/completed/failed and provider-running stage events. Validation runners use the same durable event store for command-level evidence where applicable. Event failures are swallowed at the observability boundary and cannot change asset logic.

## 9. Asset watcher and roots

The watcher scans only the repository, `.ugas/runtime`, `output`, `outputs` and `docs/evidence` roots, with duplicate-root de-duplication and excluded build/cache/vendor directories. It reports create/update, relative path, kind, size, mtime, stable SHA-256 and status after the file remains unchanged. Preview IDs are opaque URL-safe encodings; preview resolution rejects traversal, symlinks, secrets, weights, non-media files and out-of-root paths.

## 10. API and SSE contract

The server exposes `GET /api/status`, `/api/system`, `/api/processes`, `/api/jobs`, `/api/assets/recent`, `/api/qa`, `/api/events`, `/api/health`, `/api/stream` and `/api/preview/<safe-id>`. JSON includes explicit statuses and timestamps. POST/PUT/PATCH/DELETE receive `405 READ_ONLY`. SSE starts with a snapshot, emits live telemetry and heartbeats, and each reconnect receives a fresh snapshot.

## 11. Dashboard panels

The static UI implements overview, system, GPU/VRAM, live pipeline, asset activity, safe preview, QA/gates, history, structured events with search/category/severity filters, and health alerts. It has a CONNECTED/RECONNECTING/OFFLINE indicator, bounded in-memory chart windows, keyboard-usable controls, responsive desktop/tablet/mobile layout, and renders unavailable metrics as N/A/UNAVAILABLE with reasons.

## 12. Security/privacy controls

Default bind is `127.0.0.1`; non-loopback hosts are rejected. No analytics, upload, tracking pixel, CDN or remote font is used. Secret-like metadata keys and command assignments are redacted. Only allowlisted roots can be previewed. There are no generation, delete, approval or production mutation endpoints.

## 13. Unit tests

Command, final test count and passed/failed totals are recorded from the actual final run in `docs/evidence/observability-v0120/test-results.json` and the review index. Coverage includes event serialization/monotonicity, SQLite retention/restart, GPU supported/unsupported/timeout paths, file stability/hash behavior, preview traversal rejection, malformed governance evidence, SSE reconnect, read-only methods, CLI startup, version/state regression and attack-front-v2 integrity.

## 14. Validation

Command, final check count and passed/failed totals are recorded from the actual final `python scripts/validation/run_validation.py` run in `docs/evidence/observability-v0120/validation-results.json`. The active state validator and v0.12.0 review-index validator are run against canonical evidence.

## 15. Runtime smoke evidence and screenshots

Required JSON startup, idle system, command event, file activity, API snapshots and security proof are under `docs/evidence/observability-v0120/`. Runtime screenshots cover desktop overview, system/GPU plus pipeline, assets/activity, QA/events and narrow/mobile width.

## 16. v0.11.2 animation regression hashes

`docs/evidence/observability-v0120/animation-regression-v0112.json` records SHA-256 for the approved v0.11.2 GIF, spritesheet and all 12 frames, plus motion-track/key-binding hashes. These files are compared against the immutable v0.11.2 evidence; no approved animation file is modified by this increment.

## 17. Current-state/checkpoint/roadmap

`docs/evidence/current-state.json` is v0.12.0 and remains authoritative. It records `APPROVED_PILOT` for v0.11.2, `REQUIRED` for external v0.12.0 dashboard review, `production_approved=false`, `production_routing=BLOCKED`, zero new generation and the next action `external_review_observability_dashboard_v0120`. The rejected v0.11.1 history and v0.11.2 snapshot remain separate and unchanged.

## 18. Known limitations/risks

- INFO: GPU/process telemetry depends on local NVIDIA tooling and optional process APIs; unsupported states are explicit.
- INFO: ComfyUI health is endpoint reachability, not a generation or model qualification claim.
- INFO: File activity polling is bounded and may report a change on the next sample rather than at filesystem interrupt time.
- INFO: External visual review of the v0.12.0 dashboard is still required; local technical qualification is not external approval.

No HIGH or CRITICAL known issue remains within the implemented local MVP scope.

## 19. Definition of Done

- [x] v0.11.2 external result recorded immutably as `APPROVED_PILOT`.
- [x] v0.11.1 history and v0.11.2 animation hashes preserved.
- [x] Dashboard is local-only, read-only and launched by `ugas dashboard`.
- [x] API, SSE, event store, collectors, watcher, previews and instrumentation are covered by tests.
- [x] Canonical QA/state/review evidence is displayed without fabricated PASS values.
- [x] Runtime JSON evidence and five screenshots are present.
- [x] Full unit suite and validation suite pass with actual counts.
- [x] Production routing remains `BLOCKED`.
- [x] Final review index is hash-valid; publication verification is the final post-push check recorded in `publication.json`.
- [x] Commit and push `main`; stop before the next capability.

## 20. STOP

After the final commit is pushed to `main`, the next capability must wait for external review of v0.12.0. This increment does not start run/hit/death, other directions or any new asset family.
