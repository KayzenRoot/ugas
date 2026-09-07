# UGAS v0.22.2 UI Asset Family Correction Delta

## STATUS

`TECHNICALLY_QUALIFIED / NOT SELF-APPROVED`; external Sol review remains REQUIRED and PR #13 remains OPEN/unmerged.

## SCOPE

Forward-only correction of reviewed v0.22.1 HEAD `9afcf52143f27db3bfbb88fa4394e0e77f9c404a` over base `1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3`, limited to F-15/F-16/F-18/F-20/F-21. No VFX, orchestration, production routing or real UI art was started.

## CORRECTION MAP

- F-15: the active canonical pointer now names the immutable v0.21.3 `v0213-post-merge-binding.json`; the stale v0.22.0 closure-completion record is explicitly superseded and rejected by governance/state validation.
- F-16: progress bars now carry frame, track and fill geometry plus normalized domain, axis, origin, direction, clipping and deterministic `FLOOR_LINEAR` mapping. Values `0.0`, `0.5` and `1.0` are directly proved.
- F-18: `verify_nine_slice_invariants` derives corners, edges and center from decoded source bytes and margins, independent of the renderer, at two non-native target sizes; corner, edge-axis and center mutations reject.
- F-20: inventory/equipment/minimap keep their genuine external authorities; generic UI classes use local immutable `LOCAL_UI_STYLE_ART_DNA` identity. Authority type, capability, path, blob and raw hashes participate in semantic and cache identity.
- F-21: UI is an active foundation capability. The tracked action remains external review; VFX is exposed only by a GitHub LIVE resolver after PR #13 approval, governed merge and successful post-merge main CI. Advancing `main` cannot create a self-referential UI loop.

## EVIDENCE / TESTS

The active root is `docs/evidence/ui-asset-family-runtime-v0222/`. It contains the forward-only rejection record, complete progress contract, independent 9-slice proof, authority/cache identity, lifecycle scenarios, strict hard gates, real negative controls, historical mutation proof, two-run determinism and production boundary. The prior v0.22.0/v0.22.1 roots remain unchanged. Full unit tests, official validation, frozen regressions, state/capability/governance validation, Docker smoke and exact-head artifact checks are required before handoff.

## PRODUCTION / REVIEW BOUNDARY

`production_routing=BLOCKED`; `production_approved=false`; `real_ui_asset_coverage=NONE`; `synthetic_ui_fixture=TEST_ONLY`; `new_generation=0`. Merge authorization is `NOT_AUTHORIZED_UNTIL_SOL_APPROVAL`; CI green is not external approval.

## HANDOFF

Return the exact pushed HEAD, base, 3/3 required contexts, bounded artifact id/name/digest, F-15/F-16/F-18/F-20/F-21 proof, production boundary and Checkpoint Delta to Sol. Do not merge and do not start VFX.
