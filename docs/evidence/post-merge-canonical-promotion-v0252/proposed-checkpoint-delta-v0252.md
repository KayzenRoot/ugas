# Proposed checkpoint delta - UGAS-WO-0255 (v0.25.2 post-merge canonical-state promotion)

Promote the active tracked state from the pre-merge v0.25.1 review semantics to the exact post-merge truth of PR #18:

- `version=0.25.2`, `phase=V1_FINAL_ACCEPTANCE`, `current_gate=V1_CANONICAL_STATE_POST_MERGE_PROMOTION_EXTERNAL_REVIEW_REQUIRED`.
- `baseline_main_sha=38606625d5b59b09c407f9cc903bd748d91e6b35` is historical closure-branch context; current main remains a GitHub LIVE fact, not a future tracked invariant.
- PR #18 is `MERGED` at `38606625d5b59b09c407f9cc903bd748d91e6b35`, reviewed head `5f4a56bf019cc10994ee2974430c3ffca3090a50`, base `02fa44f2173aca46b4484209abccf218fe688a63`, merged_at `2026-09-12T11:21:46Z`, ordered parents `02fa44f2173aca46b4484209abccf218fe688a63` then `5f4a56bf019cc10994ee2974430c3ffca3090a50`.
- Post-merge main CI is run `34690855982` with jobs `103545700293` and `103545700226` only; PR-only review/evidence is not presented as a main check.
- Closure comment `5645638986` and Sol approval comment `5646607566` are bound as GitHub LIVE authority.
- `next_candidate=PRODUCTION_READINESS`, but the sole current action is `external_review_post_merge_canonical_state_promotion_pr`; Production Readiness remains separately unauthorized and not started.
- `production_routing=BLOCKED`, `production_approved=false`, `real_asset_generation=NONE`, `new_generation=0`, `provider_submit_calls=0`, `synthetic_fixture=TEST_ONLY`.
- v0.25.1 evidence remains append-only and byte-guarded under `docs/evidence/canonical-state-reconciliation-v0251/`; no historical evidence root is rewritten.
