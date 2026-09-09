# UGAS VFX Asset Family v0.23.2 — Review Handoff

**STATUS:** `TECHNICALLY_QUALIFIED / EXTERNAL_REVIEW_REQUIRED`

**WORK ORDER:** `UGAS-WO-0230-VFX-FND-CD2` · **PR:** `#14` · **BRANCH:** `codex/v0.23.0-vfx-asset-family-runtime-foundation`

This forward-only correction is limited to F-23R, F-26R and F-27R. The rejected v0.23.1 reviewed HEAD is `136079540f674c7467d93bd28e9834addbfce5c3`; v0.23.0 and v0.23.1 evidence and review files remain historical and unchanged. The base main SHA is `b08b9c3df74ef6a23046be396289e2fd72dc336b`.

## Corrections

- **F-23R:** semantic input is validated against an exact per-class allowlist. Only class-required keys and the explicit TEST_ONLY metadata keys `fixture_index`, `fixture_seed`, `visual_only` and `gameplay_authority` are accepted. Unknown fields reject with `VFX_SEMANTIC_UNKNOWN_FIELD`; forbidden gameplay vocabulary remains a separate real rejection path; `visual_only=true` and `gameplay_authority=NONE` are required.
- **F-26R:** `select_fallback` is followed by deterministic byte-producing `render_fallback_output`. Opacity changes decoded alpha, frame reduction changes emitted sequence count, radius/visual-area reduction changes decoded bounds, and particle/layer/spawn reductions alter deterministic raster bytes. Full/degraded hashes differ, repeated degraded rendering is byte-identical, semantic identity is preserved, and terminal `SKIP_VISUAL` emits an explicit skipped-output record. The QA sheet contains actual FULL and DEGRADED imagery side by side.
- **F-27R:** `provenance.input_hash` is the complete `semantic_contract_hash`; `raw_semantic_input_hash` explicitly records the narrow raw semantic input hash; `output_hash` binds rendered content; `effective_semantic_hash` binds the complete contract. Mutation controls traverse the real validator and report actual rejection classes.

## Validation

The bounded evidence root is `docs/evidence/vfx-asset-family-runtime-v0232/`. It contains the ten-class TEST_ONLY manifest, runtime schema, semantic allowlist proofs, actual degraded-output proofs, strict boolean hard gates, real negative controls, two-run determinism, production boundary, historical immutability and the v0.23.1 correction record.

Required exact-head GitHub contexts are `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke` and `UGAS Review / evidence`. The final artifact identity is resolved only from the exact pushed HEAD and must be recorded here after GitHub completes.

## Boundary and handoff

`production_routing=BLOCKED`; `production_approved=false`; `new_generation=0`; `real_vfx_asset_coverage=NONE`; `synthetic_vfx_fixture=TEST_ONLY`; provider generation, real VFX art, UI, orchestration and production routing were not started. PR #14 must remain OPEN and unmerged. External Sol review is required; no self-merge is authorized.

**Checkpoint Delta:** advance the active state from v0.23.1 F-22..F-28 correction history to v0.23.2 F-23R/F-26R/F-27R external-review state, add the new evidence root and preserve v0.23.1 as `CORRECTION_REQUIRED` history bound to `136079...`.
