# UGAS v0.24.4 — Orchestration Runtime Hardening F-38/F-37R/F-39/F-40 correction

Work Order: `UGAS-WO-0244-ORCHESTRATION-RUNTIME-CI-HISTORY-CLOSURE-CORRECTION-UADS`
Repository: `KayzenRoot/ugas`
PR: `#15`
Branch: `codex/v0.24.0-orchestration-runtime-hardening-foundation`
Base main: `dee98f8cd89ebd83a36ead7a22a184700d6e916f`
Rejected reviewed v0.24.3 HEAD: `5a619c0b98ced7e4c09afd9ca117a039f0d5d068`

## Status and boundary

This is a narrow forward-only CI / snapshot / history closure correction on the same PR #15. v0.24.0, v0.24.1, v0.24.2 and v0.24.3 implementation/evidence remain immutable `CORRECTION_REQUIRED` history. Accepted v0.24.3 runtime semantics are preserved. The v0.24.4 runtime remains provider-neutral and `TEST_ONLY`; no real provider submission, production routing, merge authorization or V1 Final Acceptance is started.

The active state is `ORCHESTRATION_RUNTIME_HARDENING_F38_F37R_F39_F40_CORRECTION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED`. The sole allowed next action is `external_review_orchestration_runtime_v0244`.

## Corrections

- F-38: dual-mode approved authority witness. Git-backed executions keep exact `approved_commit` verification (`GIT_COMMIT_WITNESS`). Official snapshots without `.git` use frozen registry hashes (`FROZEN_REGISTRY_WITNESS`). Both modes produce the same `authority_binding_hash` for identical authority bytes. A failed `git show` never selects no-git fallback.
- F-37R: historical mutation controls call the same public `compare_historical_evidence_tree` validator and reject deleted, extra (`EXTRA-UNAUTHORIZED.txt`) and byte-mutated trees with `HISTORICAL_TREE_MISMATCH`.
- F-39: active manifest/state truth comes from canonical v0.24.4 `current_gate` / version / `allowed_next_actions`. Stale F31-F36 gates fail.
- F-40: required GitHub context names stay exact; step labels and commands point to v0.24.4.
- Preserved: F-31R, F-32RR, F-33, F-34, F-35RR, F-35RC, F-36.

## Evidence

The v0.24.4 evidence root is `docs/evidence/orchestration-runtime-v0244/`. v0.24.1, v0.24.2 and v0.24.3 evidence roots remain preserved byte-for-byte as correction history.

## Production boundary

`production_routing=BLOCKED`; `production_approved=false`; `real_asset_generation=NONE`; `new_generation=0`; provider submission count is required to be zero. PR #15 remains OPEN/unmerged pending external Sol review.

## UADS global execution handoff

UADS GLOBAL-FIRST / ZERO PROJECT FOOTPRINT. Repository GitHub exact-head contexts and bounded artifact remain authoritative and are not self-approved here.
