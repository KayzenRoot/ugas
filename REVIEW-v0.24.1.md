# UGAS v0.24.1 — Orchestration Runtime Hardening F31-F36 correction

Work Order: `UGAS-WO-0241-ORCH-RUNTIME-CD1`
Repository: `KayzenRoot/ugas`
PR: `#15`
Branch: `codex/v0.24.0-orchestration-runtime-hardening-foundation`
Base main: `dee98f8cd89ebd83a36ead7a22a184700d6e916f`
Rejected reviewed v0.24.0 HEAD: `36064a215bf3e7bff06ac22e750a242c6556f83e`

## Status and boundary

This is a forward-only correction of F-31 through F-36. The v0.24.0 implementation and evidence remain historical `CORRECTION_REQUIRED` data and are not rewritten. The v0.24.1 runtime is provider-neutral and `TEST_ONLY`; no real provider submission, real asset generation, UI/VFX implementation, Maps redesign, production routing or V1 Final Acceptance is started.

The active state is `ORCHESTRATION_RUNTIME_HARDENING_F31_F36_CORRECTION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED`. The sole allowed next action is `external_review_orchestration_runtime_v0241`. PR #15 must remain OPEN and unmerged with `merge_authorization=NOT_AUTHORIZED_UNTIL_SOL_APPROVAL`; external Sol review is mandatory.

## Corrections

- F-31: deterministic request deadlines and parent-bounded node deadlines use an injectable/fake clock, typed request/node timeout outcomes, and retry attempts consume the same parent budget. A timed-out node blocks later dependent nodes and records the deadline boundary in the event/state evidence.
- F-32: `resume_from_checkpoint` is public and validates request/DAG/execution identity, exact node set, event chain, state/result pairs and checkpoint hash. PARTIAL checkpoints resume without re-executing completed nodes; terminal results are immutable; cross-runtime and tampered checkpoints reject.
- F-33: the bounded idempotency store/coordinator binds project, idempotency key, request hash, DAG hash and policy identity. Successful reuse names the source execution and result hashes; failed/cancelled/blocked records are not reused as success; semantic conflicts reject.
- F-34: circuit-breaker admission is integrated with dispatch. CLOSED/OPEN/HALF_OPEN transitions are isolated, retryable failures can open the breaker, and HALF_OPEN admits one probe while actual dispatch remains blocked for additional probes.
- F-35: dependency references have an exact schema, read-only approved authority status, byte/content SHA-256 and semantic SHA-256. Authorities are resolved from the repository, canonical runtime payloads carry the resolved binding hash, and missing/stale/wrong-family/rejected references fail closed.
- F-36: the runtime does not import provider clients. The validation patches the actual `ugas.comfyui_client.ComfyUIClient.submit_workflow` and `ugas.generation.ComfyUIClient.submit_workflow` entrypoints and requires zero calls. Global and per-family limits plus deterministic multi-family admission are exercised with independent work admitted when the global limit is greater than one.

## Evidence

The v0.24.1 evidence root is `docs/evidence/orchestration-runtime-v0241/`. It contains request/DAG contracts, execution state, deadline/timeout, checkpoint/resume, idempotency, circuit-breaker, dependency authority, provider boundary, family concurrency, strict gates, negative controls, two-run determinism, production boundary, schema validation and the forward-only correction record.

The local focused runtime suite passes 15 tests. The deterministic full-slice runner reports 53 strict boolean hard gates and 8 real negative controls as PASS. Exact-head GitHub CI and the bounded artifact remain authoritative for the pushed HEAD and must not be inferred from this local record.

## Validation handoff

- Unit suite: local `707` tests, `2` skips, exit `0`; exact-head CI required
- Official validation: local `2824/2824` checks passed, `0` failed; exact-head CI required
- State/checkpoint/roadmap consistency: local PASS; exact-head CI required
- Capability matrix: local PASS; exact-head CI required
- Runtime schema validation: local PASS; exact-head CI required
- Negative controls: 8 local PASS, including actual non-bool hard-gate value/type preservation
- Raster/Maps/VFX/UI history: read-only regressions required; no historical evidence root is rewritten
- Determinism: two independent v0.24.1 executions must be byte/structure equal
- Required contexts: `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke`, `UGAS Review / evidence`
- Bounded artifact: generated and validated only by the matching exact-head GitHub review workflow; final name/digest are recorded in the handoff report

## Production boundary

`production_routing=BLOCKED`; `production_approved=false`; `real_asset_generation=NONE`; `new_generation=0`; synthetic fixtures are `TEST_ONLY`; provider submission count is required to be zero. No merge is authorized by this executor.

## Checkpoint Delta

1. v0.24.0 remains frozen as `CORRECTION_REQUIRED` at exact rejected reviewed HEAD `36064a215bf3e7bff06ac22e750a242c6556f83e`.
2. v0.24.1 is a forward-only F31-F36 correction on the same PR #15 and branch, with base historical main `dee98f8cd89ebd83a36ead7a22a184700d6e916f`.
3. The current gate advances only to technical qualification pending external Sol review; it does not authorize UI, VFX, Maps redesign, provider generation, production routing or merge.
4. Stop only after a new exact HEAD on PR #15 has 3/3 required contexts green and the bounded exact-head artifact passes manifest/security validation. Leave PR #15 OPEN/unmerged and hand it to Sol.

## Risks

The remaining material risk is governance truth at the exact pushed HEAD: local execution cannot establish GitHub check-run completion, artifact upload integrity or external Sol approval. Any mismatch in base/head, required context, bounded manifest, provider spy count, authority hash or production boundary is a fail-closed blocker.

## UADS global execution handoff

The global UADS plan was reconciled to the complete authorized file boundary after the repository index was refreshed. The active Work Order is `wo_cb9535b1945f1b11` and the dispatched execution run is `er_686f018649cca498`, with no project-local UADS footprint. UADS execution verification is separate from the repository's GitHub exact-head gates and does not constitute independent Sol approval.
