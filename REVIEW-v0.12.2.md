# UGAS v0.12.2 review - QA cache integrity + Docker always-on local observability

## 1. Final HEAD and commit list

Base rejected by this correction: `f83c6a1c680a2c27a90f41d96cc8d1924c577db1`. The final implementation and publication commits are recorded in `docs/evidence/observability-v0122/publication.json` after `git push origin main`; the external reviewer resolves the final remote HEAD.

## 2. v0.12.1 rejected history

`REVIEW-v0.12.1.md`, `docs/evidence/observability-v0121/`, `docs/evidence/current-state-v0.12.1.json`, `schemas/current-state-v0.12.1.json` and `docs/evidence/review-index-v0.12.1.json` remain preserved. v0.12.2 does not rewrite those records.

## 3. F-09 cache invalidation

`ActiveEvidenceCache` binds each generation to Git HEAD, porcelain worktree status including untracked files, the indexed artifact-set SHA, index build head and authoritative-file stats. A dirty or unavailable worktree is `GAP` with `WORKTREE_DIRTY_UNBOUND` or `GIT_STATUS_UNAVAILABLE`; state/index failures remain fail-closed. The API exposes `current_head`, `validated_head`, `worktree_clean`, `cache_checked_at`, `cache_generation`, `cache_fingerprint`, `stale` and `reason`. Hash-heavy validation runs on the collector path; snapshot/HTTP reads cached data only.

## 4. QA-NC-01..08

The exact fixture IDs are implemented in `tests/test_observability_v0122.py` and executed by `scripts/validation/run_observability_v0122.py`: malformed JSON, schema-invalid state, contradictory test counts, contradictory validation counts, tampered review-index integrity, production governance contradiction, source mutation after clean PASS and descendant HEAD against the old index. Evidence is `docs/evidence/observability-v0122/qa-negative-controls-v0122.json`; no renamed count-only substitutes are used.

## 5. F-11 stale-last-known integration

The test patches only the probe boundary, performs a successful `ObservabilityService.refresh()`, then a timeout/failure refresh, and queries `/api/system` and `/api/processes`. The prior GPU/ComfyUI samples, age and degraded state are retained; no zero is fabricated and the API request does not invoke the slow probe. Evidence: `stale-last-known-integration-v0122.json`.

## 6. F-12 generation telemetry

The test calls the real `_run_job` instrumentation path with a deterministic fake provider and a 2x2 in-memory PNG. It proves parent command binding, production stage names and `/api/jobs` projection without a real generation, model download or new asset family. Evidence: `generation-telemetry-contract-v0122.json`.

## 7. Docker architecture and files

The observer is defined by `docker/Dockerfile.dashboard`, `compose.yaml`, optional `compose.gpu.yaml`, `.dockerignore`, the seven scripts under `scripts/docker/` and `docs/docker-local-dashboard.md`. The image is Python 3.12 slim-compatible with Git and psutil, runs as UID 10001, and mounts the host repository read-only plus only `.ugas/runtime` read-write.

## 8. Networking and trusted bind

Compose publishes `127.0.0.1:${UGAS_DASHBOARD_PORT:-8765}:8765`. Native non-loopback binds are rejected. Only `UGAS_CONTAINERIZED=1` permits the container-internal `0.0.0.0:8765` bind; arbitrary non-loopback container binds remain rejected. No wildcard CORS, CDN, external fonts, tunnel or remote analytics are used.

## 9. Host repository and shared SQLite

The container and host CLI share `.ugas/runtime/telemetry.db`; native UGAS commands are the single SQLite writer and the container uses `UGAS_TELEMETRY_READ_ONLY=1` to observe it read-only across the Docker Desktop Windows/VM boundary. The host repository itself is read-only in the container. A host `python -m ugas.cli models list` event and an allowlisted runtime file created/stabilized on the host are queried through the running container API. Evidence: `docker-cross-process-telemetry-v0122.json` and `docker-file-watch-v0122.json`.

## 10. GPU and ComfyUI

The up script preflights actual container `nvidia-smi` support and selects `compose.gpu.yaml` only when usable. Unsupported passthrough yields `GPU_CONTAINER_RUNTIME_GAP` with its reason while CPU/RAM/disk/repository/events remain online. ComfyUI is never started or mutated; the container probes `http://host.docker.internal:8188` and reports its actual status. Evidence: `docker-preflight-v0122.json` and `docker-gpu-v0122.json`.

## 11. Restart and autostart

The service uses `restart: unless-stopped`. `install-dashboard-autostart.ps1` registers only the per-user `UGAS-Dashboard-AlwaysOn` task; it waits for Docker Engine and invokes the idempotent up script. `uninstall-dashboard-autostart.ps1` removes only that task. Permission failures return `AUTOSTART_INSTALL_GAP` with remediation.

## 12. Container at STOP

The executor leaves `ugas-dashboard` running and healthy at `http://127.0.0.1:8765/`; it does not run `docker compose down`. The exact container ID, health and start time are in `docker-runtime-v0122.json`.

## 13. v0.11.2 regression

The approved attack-front-v2 GIF, spritesheet, all 12 raw frames, motion tracks and key bindings remain byte/semantic-identical. `new_generation=0`; no animation pixels, rig, masks or bindings changed. Evidence: `animation-regression-v0112-v0122.json`.

## 14. Unit tests

Run `python -m unittest discover -s tests -q`. Record the actual count, passed and failed values in `test-results-v0122.json`; historical v0.12.1 counts are not copied as targets.

## 15. Validation

Run `python scripts/validation/run_validation.py`. Record the actual check count, passed and failed values in `validation-results-v0122.json`; preserved historical snapshot drift is isolated and never reclassified as a current pass.

## 16. Runtime/evidence/screenshots

All required machine evidence is under `docs/evidence/observability-v0122/`; the final review index is `docs/evidence/review-index-v0.12.2.json`. Required screenshots are `dashboard-docker-overview-v0122.png` and `dashboard-docker-live-activity-v0122.png`.

## 17. State/checkpoint/roadmap policy

`docs/evidence/current-state.json`, `CHECKPOINT.md`, `README.md`, `INSTALL.md`, `docs/2d-master-pipeline.md`, `docs/comfyui.md` and `docs/roadmap.md` identify v0.12.2, `runtime_mode=DOCKER_ALWAYS_ON_LOCAL` and `ALWAYS_ON_DASHBOARD_POLICY=ENABLED` while preserving v0.12.0/v0.12.1 history.

## 18. Known limitations and risks

- HIGH: external dashboard visual review is still required; technical Docker qualification is not external approval.
- MEDIUM: NVIDIA passthrough depends on the installed Docker Desktop runtime; the explicit runtime gap is retained when unsupported.
- MEDIUM: ComfyUI availability depends on the host endpoint and is reported, never fabricated.
- LOW: per-user Task Scheduler registration can be denied by local policy and then reports `AUTOSTART_INSTALL_GAP`.

## 19. Definition of Done and STOP

Done requires Stage A exact QA/integrity gates green, Stage B Docker build/run/security/persistence/cross-process/file-watch/autostart proofs, actual tests and validation counts, byte-identical animation evidence, production blocked, `new_generation=0`, final remote publication verification, and the container left running. After these conditions, STOP for `external_review_observability_dashboard_v0122`; do not self-claim external approval or production routing.
