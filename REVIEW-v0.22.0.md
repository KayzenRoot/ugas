# UGAS v0.22.0 UI Asset Family Runtime Foundation

## Review boundary

This is a TEST_ONLY runtime foundation. It does not start a UI, VFX, orchestration, production routing, real UI art, or generation lane. The production boundary is `production_routing=BLOCKED`, `production_approved=false`, `real_ui_asset_coverage=NONE`, `synthetic_ui_fixture=TEST_ONLY`, and `new_generation=0`.

The exact base is `1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3`, the branch is `codex/v0.22.0-ui-asset-family-runtime-foundation`, and the required PR title is `v0.22.0 UI Asset Family runtime foundation`. GitHub LIVE is authoritative for current PR/head/checks; the recorded `baseline_main_sha` is historical branch context. The prior v0.21.3 Maps/Minimap evidence remains immutable.

## Technical qualification

The runtime defines the 14 required component classes, the exact six-state vocabulary, deterministic semantic style tokens (`TEST_ONLY_UI_STYLE_V0220`), state materiality, 9-slice margins and center reconstruction, content/icon/text safe rectangles, separate visual and hit bounds, 1x/2x RGBA outputs, read-only Items/Props, Equipment/Outfits and Maps/Minimap linkage, complete cache identity, raw output provenance and an empty production registry.

The bounded evidence root is `docs/evidence/ui-asset-family-runtime-v0220/`. It contains the manifest, class/state/style/geometry/scale/integration/cache/provenance records, strict `UI-HG-01..22`, real `UI-NC-01..22`, two-run determinism, TEST_ONLY fixture manifest, production boundary, execution evidence and contact/geometry QA sheets.

## Required final executor report

The final handoff must state, from exact live evidence:

- exact HEAD SHA, base SHA, branch, PR number/state and required context conclusions;
- changed files and explicit corrections for the UI contract/runtime slice;
- unit-test total, official-validation total and frozen regression results;
- all 22 hard gates with strict boolean observed values;
- all 22 negative controls with actual observed rejection classes;
- raster/geometry, safe-area, scale, cache, provenance, linkage and determinism proof;
- bounded artifact name and digest, manifest/security result and exact-head binding;
- production boundary, risks, Checkpoint Delta and external-review handoff.

## Stop condition

Stop only with the exact new HEAD on the single authorized PR, `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke` and `UGAS Review / evidence` green for that exact HEAD, bounded artifact PASS, production still blocked, PR OPEN/unmerged, and external GPT-5.6 Sol review required. Do not merge.
