# UGAS v0.21.2 — Maps / Minimap Raster + Governance Integrity

## Governed handoff

- Work order: `UGAS-WO-0212-MM-RGI`
- Repository: `KayzenRoot/ugas`
- Existing PR: `#11` — keep `OPEN`; do not merge
- Branch: `codex/v0.21.0-maps-minimap-runtime-foundation`
- Base: `0bf04cb92e8619ea10cf82af8dbf2d9abe599e05`
- Reviewed corrective history: v0.21.1 at `cfde03cce2e31cc688f9d94a659b577042b8538a`, `CORRECTION_REQUIRED`
- Current state: `MAPS_MINIMAP_RASTER_GOVERNANCE_INTEGRITY_TECHNICALLY_QUALIFIED`
- Production: `production_routing=BLOCKED`, `production_approved=false`, `new_generation=0`
- Real map/minimap coverage: `NONE`; fixtures: `TEST_ONLY`

## Corrections delivered

F-06 is corrected in the runtime renderer. `minimap_cell_geometry()` computes `x_min`, `x_max`, `y_min`, and `y_max` from both projected corners, independent of orientation. The renderer validates and draws the resulting rectangle. Direct tests cover `TOP_LEFT/Y_DOWN` and `CENTER/Y_UP`; the collapsed-Y mutation is rejected as `MINIMAP_RASTER_CELL_GEOMETRY_INVALID`.

F-07 is corrected with `validate_historical_authority()`. The positive proof validates the current historical file against the immutable main authority blob. The mutation control sends mutated bytes through the same validator and records the exception's actual `HISTORICAL_EVIDENCE_MUTATION_REJECTED` class, authority ref/blob/hash, observed hash, raw-file fingerprint, and mutation fingerprint.

F-08 is corrected in `_gate()`: only `type(observed) is bool and observed is True` passes. Unit tests cover `True`, `False`, `None`, numeric values, empty/non-empty containers, and empty/non-empty strings. Evidence preserves the observed value and `observed_type`; a non-boolean negative control fails through the real helper.

## Validation evidence

- Isolated maps/minimap execution: `MAPS_MINIMAP_RASTER_GOVERNANCE_INTEGRITY_TECHNICALLY_QUALIFIED`
- Hard gates: `22/22 PASS`
- Negative controls: `29/29 PASS`
- Independent full-slice runs: deterministic, no differences
- Raster evidence: `docs/evidence/maps-minimap-runtime-v0212/raster-geometry-v0212.json`
- Historical evidence: `docs/evidence/maps-minimap-runtime-v0212/historical-immutability-v0212.json`
- v0.21.1 rejection record: `docs/evidence/maps-minimap-runtime-v0212/v0.21.1-rejection-correction-record-v0212.json`
- Active state: `docs/evidence/current-state.json`

## Required external gate

The executor must push this correction to the same branch and update PR #11 only. The handoff is complete only after the exact new HEAD has successful `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke`, and `UGAS Review / evidence` contexts, plus a bounded exact-head artifact with `PASS`. External Sol approval remains required. No merge, UI, VFX, orchestration, real maps, real minimap art, production routing, or generation is authorized.

## Checkpoint Delta proposal

Advance the active checkpoint from v0.21.1 QA contract integrity correction to v0.21.2 raster/governance integrity correction, preserving v0.21.1 as immutable `CORRECTION_REQUIRED` history. Keep `MAPS_MINIMAP` active, keep production blocked, and authorize only `external_review_maps_minimap_v0212` after exact-head evidence is green.
