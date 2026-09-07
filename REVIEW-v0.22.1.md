# UGAS v0.22.1 UI Asset Family Semantic Integrity Correction

## STATUS

`UI_ASSET_FAMILY_SEMANTIC_INTEGRITY_TECHNICALLY_QUALIFIED`; external Sol review REQUIRED; PR #13 remains OPEN and unmerged.

## VERSION / SCOPE

Forward-only correction of rejected v0.22.0 HEAD `0fad4721c0bfd52822cb3f1e952f306b5c50a151`, on branch `codex/v0.22.0-ui-asset-family-runtime-foundation`, over base `1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3`. Only F-15 through F-20 were corrected. No VFX, orchestration, production routing or real UI art was started.

## F-15..F-20 CORRECTION MAP

- F-15: corrected PR #12 closure provenance in `docs/evidence/github-governance-v0221/v0213-closure-completion-binding-v2.json`; pre-merge PR contexts and post-merge main CI are distinct and validated by IDs, heads, workflow runs and conclusions.
- F-16/F-17: `CLASS_SPECS` is authoritative for class metadata and per-class applicable states; renderer rejects a globally known but class-unsupported state.
- F-18: `render_component_to_size` performs actual decoded 9-slice reconstruction and rejects undersized targets, corner mutations, wrong-axis mutations and arbitrary NON_STRETCH targets.
- F-19: v0.22.1 uses exact decoded RGBA nearest-neighbor 2x expansion and rejects correctly-sized pixel mutations.
- F-20: integration authorities resolve immutable Git bytes/blob IDs independently; `content_hash`, `semantic_input_hash` and cache keys include render-affecting semantics and reject stale mutations.

## EVIDENCE

The active forward-only root is `docs/evidence/ui-asset-family-runtime-v0221/`. The v0.22.0 root remains unchanged as `CORRECTION_REQUIRED` history. It contains the class contract, applicability matrix, reconstruction, scale correspondence, authority, cache, hard-gate, negative-control, determinism, production boundary, governance, execution and visual QA records.

## TESTS / VALIDATION

The focused v0.22.1 tests exercise all six findings and public negative paths. The CI workflow runs the full unit suite, official validation, frozen regressions, capability/state/workflow/governance validators and two isolated fixture generations. Exact-head artifact security, manifest and enforcement remain fail-closed.

## PRODUCTION / REVIEW BOUNDARY

`production_routing=BLOCKED`; `production_approved=false`; `real_ui_asset_coverage=NONE`; `synthetic_ui_fixture=TEST_ONLY`; `new_generation=0`. Merge authorization is `NOT_AUTHORIZED_UNTIL_SOL_APPROVAL`; CI green is not external approval.

## HANDOFF

Return the exact pushed HEAD, 3/3 required contexts, bounded artifact id/name/digest and visual QA paths to Sol. Do not merge.
