# UGAS v0.20.3 review boundary - ENVIRONMENT_TILESETS

The direct user request accompanying the attached corrective PDF is empty. The five-page PDF was read and rendered completely and is treated as the governing executable specification, distinct from that empty request. This is a forward-only correction on existing PR #10 and branch `codex/v0.20.0-environment-tilesets-runtime-foundation`; no duplicate PR is authorized.

## STATUS

`ENVIRONMENT_TILESETS_QA_GOVERNANCE_INTEGRITY_TECHNICALLY_QUALIFIED`, pending exact-head GitHub validation and Sol re-review. v0.20.2 is preserved as `CORRECTION_REQUIRED` history at rejected reviewed head `6022cf3c6158ebb762519a04e79ed42378438ccc` and is not approved to merge.

## CORRECTION BOUNDARY

The v0.20.2 semantic runtime remains the shared TEST_ONLY fixture core. v0.20.3 corrects governance and QA integrity only: production candidates use a reusable complete semantic validator; system production routing remains `BLOCKED`; PB-NC-01..05 traverse real rejection paths; the dedicated mask-matrix validator powers both the hard gate and MC-NC-05; OR-NC-02 and OR-NC-03 inject broken origin behavior; fixed Git authority binds historical preservation; and summaries are derived fail-closed from underlying results.

Maps/Minimap, production environment art, UI, VFX, orchestration and new generation remain forbidden. Real environment coverage is `NONE`; all generated visual fixtures are synthetic `TEST_ONLY`; the production registry remains empty; `production_approved=false`; `new_generation=0`.

## F-01 PRODUCTION SEMANTIC CONTRACT

`validate_production_tileset_candidate(root, manifest, system_policy)` requires system policy `ENABLED`, candidate routing `ENABLED`, `production_approved=true`, `production_safe=true`, `test_only=false`, a filesystem root, manifest provenance and complete v0.20.2 semantics. The public registry rejects system `BLOCKED` with `PRODUCTION_ROUTING_BLOCKED`, rejects TEST_ONLY promotion with `TEST_FIXTURE_IN_PRODUCTION_REGISTRY`, and invokes the same semantic core for enabled candidates. PB-NC-01..05 and the separately labeled isolated positive candidate proof are recorded in `production-boundary-qa-v0203.json`.

## F-02 MASK AND ORIGIN CONTROLS

`validate_autotile_matrix` is the dedicated authority for exact `TILE_CLASSES x supported_masks` coverage and is consumed by both the hard gate and MC-NC-05. MC-NC-05 mutates the actual matrix/evidence authority and must observe `AUTOTILE_MATRIX_INCOMPLETE`. Positive origin proofs are separate from negative controls. OR-NC-02 injects a transform that ignores origin and must observe `ORIGIN_SEMANTICS_IGNORED`; OR-NC-03 injects a broken inverse/offset and must observe `GRID_ORIGIN_ROUNDTRIP_FAILED`. Every negative control is PASS only on the exact expected observed class.

## F-03 HISTORICAL AUTHORITY

Historical checks are bound to fixed Git authorities: v0.20.0 to `ae335ba198bb7f23210873e30948e8a19bc71cbd`, v0.20.1 to `0353e6785017c08db6e55c9448d9fa60e5908802` and rejected v0.20.2 to `6022cf3c6158ebb762519a04e79ed42378438ccc`. A mutation of any bound historical file fails the preservation gate. The v0.20.2 evidence root is frozen and the forward-only rejection/correction record is `docs/evidence/environment-tilesets-runtime-v0203/v0202-rejection-correction-record-v0203.json`.

## EVIDENCE

Current evidence is under `docs/evidence/environment-tilesets-runtime-v0203/`, including `production-semantic-contract-v0203.json`, `production-boundary-qa-v0203.json`, `mask-matrix-validator-v0203.json`, separate `origin-positive-proofs-v0203.json` and `origin-negative-controls-v0203.json`, `historical-authority-manifest-v0203.json`, `historical-preservation-v0203.json`, `gate-specific-proof-v0203.json`, `summary-integrity-v0203.json`, canonical ET current-runtime evidence, exact hashes, deterministic fixture output, empty production registry and execution evidence. The v0.20.2 and all earlier evidence roots are not overwritten.

## STATE AND PRODUCTION BOUNDARY

`version=0.20.3`; `phase=ENVIRONMENT_TILESETS`; `current_gate=ENVIRONMENT_TILESETS_QA_GOVERNANCE_INTEGRITY_TECHNICALLY_QUALIFIED`; `items_props=APPROVED_FOUNDATION`; `environment_tilesets_runtime_external_review=REQUIRED`; `v0202_external_review=CORRECTION_REQUIRED`; `real_environment_asset_coverage=NONE`; `synthetic_environment_fixture=TEST_ONLY`; `production_approved=false`; `production_routing=BLOCKED`; `new_generation=0`; `allowed_next_actions=[external_review_environment_tilesets_v0203]`; `next_capability_started=false`.

## GITHUB STOP

Continue on PR #10 and the existing branch. Push corrections automatically to `KayzenRoot/ugas`. Require exact contexts `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke` and `UGAS Review / evidence`, with failure-safe artifact upload before enforcement. Stop with PR #10 OPEN and unmerged after a new corrected head and exact-head v0.20.3 bounded artifact pass. Do not merge or start Maps/Minimap. Hand off to Sol for code, evidence and TEST_ONLY tileset review.
