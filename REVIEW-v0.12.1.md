# UGAS v0.12.1 - Observability Integrity, Security and Live Pipeline Correction

## 1. Final HEAD and commit list

Correction base HEAD: `789c82f246e48b119f2eebfade890a854b5a7b63`; previous implementation commit: `d0eb6e06cf9c5eadce586fc1c096ba1ac168daa5`. The v0.12.1 review index is built before publication and its final HEAD is resolved by the external reviewer.

## 2. v0.12.0 rejected history preservation

The v0.12.0 implementation, review, evidence and state/schema snapshots remain present and are not squashed, rewritten or silently overwritten. v0.12.1 is a correction-only forward transition.

## 3. F-01 DOM XSS correction

The History command path previously joined untrusted argv text into `innerHTML`. `dashboard.js` now uses DOM construction and `textContent` for telemetry, jobs, files, state and provider values; no `innerHTML` or `outerHTML` sink remains. Dynamic classes are selected from fixed local mappings. The HTTP server sends CSP, `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.

## 4. F-02 QA fail-closed correction

`service.qa()` now uses cached canonical validation of the active schema, state-consistency rules, review-index schema, artifact SHA-256 set and evidence semantics. PASS requires tests `status=passed`, `failed=0`, `passed=count`, validation `status=passed`, `failed=0`, `passed=checks`, and a valid review index. Missing, malformed, mismatched or contradictory evidence returns GAP.

## 5. F-03 live pipeline correction

Command, job and stage events are aggregated by workload. `/api/jobs` exposes `job_id`, `parent_command_id`, command, category/type, current stage, status, timestamps, elapsed seconds, latest message and recent stages. The UI renders real stage names and elapsed time. The dashboard daemon is marked `dashboard_service` and is not selected as `active_job`. Dead process-bound RUNNING records reconcile to `ORPHANED` or `STALE`.

## 6. Resource and provider visibility

The UI and API expose UGAS PID/name/CPU/RSS, NVIDIA GPU process PID/name/GPU memory, GPU metrics, and ComfyUI endpoint/status/health/checked_at/reason. Every sample has a timestamp or age. `attack_front_v2=APPROVED_PILOT` and `observability_dashboard=REQUIRED` remain separately visible.

## 7. Stale-last-known and probe cadence

Independent GPU utilization, GPU-process and ComfyUI probes run concurrently in the collector. HTTP requests read the latest snapshot and never launch slow probes. A later timeout/error preserves the last successful sample under `stale_last_known` with age and explicit `TIMEOUT`/`DEGRADED` status; no zero value is fabricated.

## 8. File activity, stable hashes and previews

Spritesheet filename semantics are evaluated before generic image classification. Create/update records are followed by a machine-readable `stable` transition carrying SHA-256. Repository-root media is marked `previewable=false`, so the UI does not render a broken preview control. Traversal, out-of-root, secret, weight and symlink protections remain fail-closed.

## 9. Corrected v0.11.2 binding

`docs/evidence/observability-v0121/external-review-v0112-binding-correction-v0121.json` supersedes only the defective v0.12.0 binding metadata. It binds `docs/evidence/animation-runtime-v0112/attack-front-v2/attack-front-v2-preview.gif` to SHA-256 `ef02fbf99356ca07fee3ac00de8e5a7938b65175dfd16591c3bf414bd077a7b7`, retains `APPROVED_PILOT`, `production_approved=false` and `production_routing=BLOCKED`, and explains that the historical record is superseded, not rewritten.

## 10. Animation regression

The v0.11.2 GIF, spritesheet and all 12 raw frame PNGs are compared byte-for-byte against their immutable recorded hashes. Motion tracks and key bindings remain unchanged. No new generation or attack-front-v2 edit is authorized or performed.

## 11. Unit tests

The actual final command, count, passed and failed totals are recorded in `docs/evidence/observability-v0121/test-results-v0121.json` and the v0.12.1 review index. Tests cover XSS inert rendering, headers, QA-NC-01..06, stage aggregation, daemon/orphan reconciliation, resource contracts, stale samples, spritesheet classification, stable transitions, preview consistency and historical animation identity.

## 12. Validation

The actual final `python scripts/validation/run_validation.py` command, checks, passed and failed totals are recorded in `docs/evidence/observability-v0121/validation-results-v0121.json`. The active state and review index validators are run against canonical evidence.

## 13. Runtime evidence and screenshots

The v0.12.1 runtime package contains security-XSS, QA negative controls, live-stage, orphan, system/GPU process, stale-last-known, file activity, preview security, corrected external binding, animation regression, API/SSE, startup and five post-correction dashboard screenshots under `docs/evidence/observability-v0121/`.

## 14. State, checkpoint and roadmap

The active state is v0.12.1 in `LOCAL_REALTIME_OBSERVABILITY` with gate `LOCAL_REALTIME_OBSERVABILITY_DASHBOARD_MVP_TECHNICALLY_QUALIFIED`. The only actionable next gate is `external_review_observability_dashboard_v0121`. The v0.12.0 state remains a rejected historical snapshot. `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, local-only and read-only boundaries remain authoritative.

## 15. Known limitations and risks

- INFO: NVIDIA process fields depend on local `nvidia-smi`; unsupported fields are explicit.
- INFO: ComfyUI status is endpoint health, not process detection or generation qualification.
- INFO: Polling activity is bounded and can observe transitions on the next collector sample.
- INFO: External visual review of the corrected dashboard remains `REQUIRED`; local validation is not external approval.

No HIGH or CRITICAL known issue remains within the corrected observability scope.

## 16. Definition of Done

- [x] v0.12.0 rejected history and evidence are preserved.
- [x] DOM XSS sinks are removed and security headers are present.
- [x] QA validation is fail-closed with QA-NC-01..06.
- [x] Real pipeline stages, elapsed time and orphan reconciliation are exposed.
- [x] UGAS, GPU process, GPU and ComfyUI resource data are exposed with ages/reasons.
- [x] Stable file transitions, spritesheet classification and preview contract are proven.
- [x] v0.11.2 binding is corrected forward-only with exact path and SHA.
- [x] Animation regression proves zero approved-asset changes.
- [ ] Final test/validation counts, review index and post-push publication SHA are recorded after execution.

## 17. STOP

Commit and push `main`, then stop and wait for `external_review_observability_dashboard_v0121`. Do not start a new asset family, modify attack-front-v2, enable production routing or add mutating dashboard endpoints.
