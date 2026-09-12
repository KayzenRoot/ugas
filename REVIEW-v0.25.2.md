# UGAS-WO-0255 - V1 post-merge canonical-state promotion

**STATUS:** `REVIEW_READY_PENDING_SOL`
**WORK_ORDER:** `UGAS-WO-0255`
**ISSUE:** `#19`
**BASE_SHA:** `38606625d5b59b09c407f9cc903bd748d91e6b35`
**HEAD_SHA:** resolved from GitHub LIVE after push
**CONTEXT_LOCK:** main `38606625d5b59b09c407f9cc903bd748d91e6b35`; PR #18 `MERGED`; source reviewed head `5f4a56bf019cc10994ee2974430c3ffca3090a50`
**PR_NUMBER:** `19` (GitHub LIVE PR metadata)

## Active-state promotion

Active tracked state is v0.25.2 in `V1_FINAL_ACCEPTANCE`, with gate `V1_CANONICAL_STATE_POST_MERGE_PROMOTION_EXTERNAL_REVIEW_REQUIRED`. The recorded `baseline_main_sha=38606625d5b59b09c407f9cc903bd748d91e6b35` is historical branch context, not a self-referential invariant for future live `main`; current `main` must be resolved from GitHub LIVE.

## Post-merge binding

PR #18 is bound as `MERGED` at merge SHA `38606625d5b59b09c407f9cc903bd748d91e6b35`, merged at `2026-09-12T11:21:46Z`, with ordered parents `02fa44f2173aca46b4484209abccf218fe688a63` and `5f4a56bf019cc10994ee2974430c3ffca3090a50`. Post-merge run `34690855982` is `SUCCESS`; main CI contains exactly unit job `103545700293` and docker job `103545700226`. Closure comment `5645638986` and Sol approval comment `5646607566` are bound as live authority. PR-only `UGAS Review / evidence` is not represented as a main check.

## Tests and validation

- Unit suite: required full repository suite.
- Official validation: required full repository validation.
- State/schema validation: v0.25.2 active state and split binding.
- Negative controls: stale PR state, stale merge flag, wrong merge identity, wrong closure ID, production drift, premature readiness and fabricated main context.
- Historical immutability: v0.25.1 evidence root remains Git-guarded and unchanged.
- Snapshot/no-git and Docker: required by repository CI.
- Determinism: three identical v0.25.2 promotion evidence computations.

## Production boundary

`production_routing=BLOCKED`; `production_approved=false`; `real_asset_generation=NONE`; `new_generation=0`; `provider_submit_calls=0`; `synthetic_fixture=TEST_ONLY`; `production_readiness_workstream=NOT_STARTED_REQUIRED_SEPARATELY`. No Production Readiness, provider, generation, deployment, release, UI, VFX or orchestration work is started.

## UADS and footprint

`UADS_MODE=GLOBAL_FIRST`; `PROJECT_FOOTPRINT=ZERO`; routing is `SELECTED`; dispatch is `DISPATCHED`; no UADS material is stored in the repository.

## Proposed Checkpoint Delta

See `docs/evidence/post-merge-canonical-promotion-v0252/proposed-checkpoint-delta-v0252.md`.

## Stop condition

Keep PR #19 OPEN and unmerged after the exact-head required contexts and bounded evidence artifact are green. Return to Sol for independent external review. Do not merge and do not begin Production Readiness.
