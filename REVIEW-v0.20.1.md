# UGAS v0.20.1 review boundary - ENVIRONMENT_TILESETS

The direct user request accompanying the attached corrective PDF is empty. The PDF is the governing executable prompt and is kept distinct from that empty request. This correction continues PR #10 and its existing feature branch; no duplicate PR is authorized.

## STATUS

`ENVIRONMENT_TILESETS_AUTOTILE_WORLD_METRIC_VARIANT_INTEGRITY_TECHNICALLY_QUALIFIED`, pending new exact-head GitHub review and Sol re-review. v0.20.0 is preserved as rejected candidate history and is not approved to merge.

## CORRECTION BOUNDARY

The rejected reviewed head is `ae335ba198bb7f23210873e30948e8a19bc71cbd`, based on main `93293d21f301e6d64232a992eb92533db9741118`. The correction is forward-only on `codex/v0.20.0-environment-tilesets-runtime-foundation`. Maps/Minimap, production environment art, UI, VFX and orchestration remain forbidden.

## F-01 CLASS/LAYER-SAFE AUTOTILE ROUTING

`EnvironmentTileResolver` now requires an explicit requested class, binds the request tile to its terrain family and primary layer, requires every mask variant to declare target class/layer, materializes only same-class/same-layer effective tiles, exposes requested/resolved identity fields, and rejects cross-family, cross-class, cross-layer and stale cache reuse.

## F-01B MASK-SPECIFIC BYTE IDENTITIES

Every supported class/mask pair has a deterministic TEST_ONLY standalone tile, exact file hash, decoded pixel hash, atlas rectangle and atlas revision. Mask QA is rebuilt from those actual files. Shared visual identity is false for the generated transition representations; no unrelated class is used as a stand-in.

## F-02 WORLD METRICS

Pixel metrics are canonicalized as `tile_width_px` and `tile_height_px`; `world_units_per_tile` is positive and independent. Grid conversion uses world units and orientation, while atlas binding uses pixel dimensions. Round-trip evidence covers 16px, 32px and 64px representations with identical world positions.

## F-03 EFFECTIVE VARIANTS

`materialize_tile_variant` and `validate_effective_tile_variant` apply and validate effective binding, edge and collision semantics before resolver output/cache. Visual identity, atlas bounds, byte-derived edges, collision contradictions, lineage, parent, revision and forbidden override controls are executable.

## F-04 GATE-SPECIFIC PROOF

The v0.20.1 runner creates each named hard gate from an explicit checker result. No gate is prefilled as PASS; missing or raised proof is FAIL. ET-NC-01..18 are preserved read-only from the immutable v0.20.0 candidate and AT-NC-01..05, WM-NC-01..04 and TV-NC-01..06 inject real semantic defects.

## EVIDENCE

All new evidence is under `docs/evidence/environment-tilesets-runtime-v0201/`. It includes explicit contract, class/layer matrix, mask byte bindings, resolution matrix, mask/seam QA, world metric round-trip and controls, effective variant validation, atlas/edge/cache integrity, gate-specific proof, deterministic two-run output, TEST_ONLY production boundary and execution evidence. `docs/evidence/environment-tilesets-runtime-v0200/` is not overwritten.

## STATE AND PRODUCTION BOUNDARY

The active state is v0.20.1 in phase `ENVIRONMENT_TILESETS`, with `items_props=APPROVED_FOUNDATION`, `environment_tilesets_runtime_external_review=REQUIRED`, `v0200_external_review=CORRECTION_REQUIRED`, `real_environment_asset_coverage=NONE`, `synthetic_environment_fixture=TEST_ONLY`, `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, `allowed_next_actions=[external_review_environment_tilesets_v0201]`, and `next_capability_started=false`.

## GITHUB STOP

Continue on PR #10 and the existing branch. Push corrections automatically to `KayzenRoot/ugas`. Require exact contexts `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke`, and `UGAS Review / evidence`, with failure-safe artifact upload before enforcement. Stop with PR #10 OPEN after a new corrected head and exact-head v0.20.1 artifact pass. Do not merge and do not start Maps/Minimap. Hand off to Sol for code, evidence and TEST_ONLY tileset review.
