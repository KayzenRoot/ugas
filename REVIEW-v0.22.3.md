# UGAS v0.22.3 — UI Asset Family Correction Review

Status: TECHNICALLY_QUALIFIED / EXTERNAL_REVIEW_REQUIRED

This forward-only correction is scoped to F-15, F-16, F-18 and F-21. The v0.22.0, v0.22.1 and v0.22.2 evidence roots remain immutable historical records. F-20 remains covered by regression evidence and is not reopened.

## State and governance

- schema/version: 0.22.3
- phase: UI_ASSET_FAMILY
- current gate: UI_ASSET_FAMILY_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED
- baseline_main_sha: 1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3
- GitHub LIVE is the authority for PR #13 state and exact head.
- allowed action: external_review_ui_asset_family_v0223
- production_routing=BLOCKED; production_approved=false; real_ui_asset_coverage=NONE; synthetic_ui_fixture=TEST_ONLY; new_generation=0
- maps_minimap_lifecycle=MERGED_CLOSED
- vfx_start_gate=BLOCKED until UI approval, governed merge and exact post-merge main CI success are observed from GitHub LIVE.

## Corrections

- F-15 binds active closure truth to `docs/evidence/github-governance-v0221/v0213-closure-completion-binding-v2.json`. The historical PR #11-only binding remains superseded and is rejected when injected into the active pointer.
- F-16 uses an explicit reject policy: `clamp=false`, `out_of_range=REJECT`, `FLOOR_LINEAR` mapping. Values -0.1 and 1.1 reject; 0.0, 0.5 and 1.0 are directly proven.
- F-18 keeps independent decoded nine-slice verification for two non-native sizes and verifies corners, top/bottom edges, left/right vertical edges and center. Patterned synthetic evidence prevents a flat-source false positive.
- F-21 requires merge commit SHA, current main SHA, post-merge CI commit SHA and every supported main context head SHA to be identical, with both contexts completed/success, before VFX becomes allowed.

## Review boundary

PR #13 remains open and unmerged. No self-merge is authorized. No VFX, orchestration, production routing, real UI art or generation was started. The next capability remains UI_ASSET_FAMILY; the sole current action is external_review_ui_asset_family_v0223.

## Evidence

The bounded v0.22.3 evidence root is `docs/evidence/ui-asset-family-runtime-v0223/`. The governance binding is `docs/evidence/github-governance-v0223/v0223-ui-closure-binding.json`. Exact-head CI and the bounded artifact are required before handoff to Sol.
