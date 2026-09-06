# UGAS v0.20.2 review boundary - ENVIRONMENT_TILESETS

The direct user request accompanying the attached corrective PDF is empty. The six-page PDF was read and rendered completely and is treated as the governing executable specification, distinct from that empty request. This is a forward-only correction on existing PR #10 and branch `codex/v0.20.0-environment-tilesets-runtime-foundation`; no duplicate PR is authorized.

## STATUS

`ENVIRONMENT_TILESETS_PRODUCTION_MASK_ORIGIN_VARIANT_INTEGRITY_TECHNICALLY_QUALIFIED`, pending exact-head GitHub validation and Sol re-review. v0.20.1 is preserved as rejected candidate history and is not approved to merge.

## CORRECTION BOUNDARY

Rejected reviewed head: `0353e6785017c08db6e55c9448d9fa60e5908802`; base main: `93293d21f301e6d64232a992eb92533db9741118`. The v0.20.1 evidence root remains immutable. Maps/Minimap, production environment art, UI, VFX and orchestration remain forbidden.

## F-01 PRODUCTION REGISTRY BOUNDARY

`EnvironmentTileRegistry` now has an explicit `ProductionRoutingPolicy`. Production registration rejects while system routing is `BLOCKED`, rejects TEST_ONLY fixtures in production mode, and requires a filesystem-backed semantic candidate validation path before any enabled production registration. PB-NC-01..04 and current ET-NC-17 exercise this public boundary.

## F-02 SUPPORTED MASK CROSS-PRODUCT

Each family validates the exact product `TILE_CLASSES x supported_masks`: every pair exists once, no undeclared or duplicate pair is accepted, every target layer is class-derived, and every resolution record carries exact bound file/pixel/atlas identity. MC-NC-01..05 prove fail-closed missing, undeclared, duplicate, invalid-policy and incomplete-matrix cases.

## F-03 ORIGIN CONTRACT

`TOP_LEFT` resolves `(x*unit, y*unit*direction)` and `CENTER` resolves `((x+0.5)*unit, (y+0.5)*unit*direction)`, with `Y_DOWN=1` and `Y_UP=-1`. Both conventions have exact inverse round-trips for zero, positive and negative coordinates. Unknown or inert origin behavior is rejected by OR-NC-01..03.

## F-04 VARIANT IDENTITY AUTHORITY

Retained top-level `content_hash` and `atlas_revision` are authoritative: they must match the effective binding, `effective_binding` must equal `overrides.atlas_binding`, and both must equal the resolved tile binding. VI-NC-01..04 reject hash, revision, authority and resolved visual identity tampering before resolver/cache use.

## F-05/F-06 CURRENT CONTROLS AND BOOLEAN GATES

ET-NC-01..18 are re-executed against the current v0.20.2 runtime; historical v0.20.0 preservation is recorded separately. Every named gate consumes an explicit boolean-aware result; no tuple/literal-True shortcut can force a false checker green.

## EVIDENCE

Current evidence is under `docs/evidence/environment-tilesets-runtime-v0202/`, including production boundary, exact mask cross-product, origin contract, variant identity, current ET controls, historical preservation, gate-specific proof, deterministic two-run output, byte/atlas/seam/cache evidence, production registry, state consistency and execution evidence. `docs/evidence/environment-tilesets-runtime-v0201/` and all prior approved evidence are not overwritten.

## STATE AND PRODUCTION BOUNDARY

`version=0.20.2`; `phase=ENVIRONMENT_TILESETS`; `current_gate=ENVIRONMENT_TILESETS_PRODUCTION_MASK_ORIGIN_VARIANT_INTEGRITY_TECHNICALLY_QUALIFIED`; `items_props=APPROVED_FOUNDATION`; `environment_tilesets_runtime_external_review=REQUIRED`; `v0201_external_review=CORRECTION_REQUIRED`; `real_environment_asset_coverage=NONE`; `synthetic_environment_fixture=TEST_ONLY`; `production_approved=false`; `production_routing=BLOCKED`; `new_generation=0`; `allowed_next_actions=[external_review_environment_tilesets_v0202]`; `next_capability_started=false`.

## GITHUB STOP

Continue on PR #10 and the existing branch. Push corrections automatically to `KayzenRoot/ugas`. Require exact contexts `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke`, and `UGAS Review / evidence`, with failure-safe artifact upload before enforcement. Stop with PR #10 OPEN and unmerged after a new corrected head and exact-head v0.20.2 bounded artifact pass. Do not merge or start Maps/Minimap. Hand off to Sol for code, evidence and TEST_ONLY tileset review.
