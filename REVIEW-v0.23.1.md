# UGAS v0.23.1 — VFX Asset Family F-22..F-28 correction

STATUS: TECHNICALLY_QUALIFIED / EXTERNAL_REVIEW_REQUIRED  
WORK_ORDER: UGAS-WO-0230-VFX-FND-CD1  
VERSION: 0.23.1  
CORRECTS: F-22, F-23, F-24, F-25, F-26, F-27, F-28  
REPOSITORY: KayzenRoot/ugas  
PR_NUMBER: 14  
BRANCH: codex/v0.23.0-vfx-asset-family-runtime-foundation  
BASE_MAIN_SHA: b08b9c3df74ef6a23046be396289e2fd72dc336b  
REJECTED_HEAD: c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72  

## Scope and truth boundary

This is a forward-only correction on the existing PR #14. The v0.23.0 module, review, and evidence root remain immutable history. The active current-head field is intentionally `null`; GitHub LIVE and the bounded exact-head artifact resolve the current PR head. Production routing remains `BLOCKED`, `production_approved=false`, `real_vfx_asset_coverage=NONE`, `synthetic_vfx_fixture=TEST_ONLY`, and `new_generation=0`. No real VFX generation or Orchestration was started.

## Corrections

- F-22: removed the stale tracked current PR head and validated the historical baseline against the branch/base binding.
- F-23: replaced semantic placeholders with typed, class-specific visual-only values and reject gameplay vocabulary/authority before identity hashing.
- F-24: added explicit owner-loop period, owner/safety termination, per-effect concurrency and budget ceilings with mutation controls.
- F-25: made all fixture bytes truthfully `STRAIGHT` alpha and validated decoded RGBA pixels, including metadata mutation rejection.
- F-26: added deterministic constrained-profile selection/application, actual visual degradation and a full/degraded budget/fallback QA sheet.
- F-27: canonicalized lifecycle, blend, spatial, budget, fallback, representation, integration, authority and frame/content identity into one complete semantic contract used by cache/provenance.
- F-28: Orchestration is allowed only for GitHub LIVE merged state whose merge SHA, current main SHA, post-merge CI SHA and both completed successful context heads are identical.

## Evidence and validation

Evidence is under `docs/evidence/vfx-asset-family-runtime-v0231/`. The runtime produced 32 strict boolean hard gates, 30 real negative controls, two deterministic independent fixture executions, typed semantic proofs, decoded-alpha proof, constrained fallback proof, complete cache/provenance proof and exact live-SHA lifecycle controls. The v0.23.0 rejection/correction record is bound to reviewed head `c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72` and reports F-22 through F-28 without rewriting prior evidence.

## Handoff

`PR_STATE: OPEN`; `PR_HEAD_SHA` must be read from GitHub LIVE at review time; `MERGED: false`; `EXTERNAL_REVIEW_REQUIRED: true`; `DO_NOT_MERGE: true`. Required contexts are `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke`, and `UGAS Review / evidence`. Stop with PR #14 OPEN and unmerged for Sol review. Do not start Orchestration, production routing, provider generation or real VFX art.
