# UGAS VFX Asset Family v0.23.3 - Review Handoff

STATUS: TECHNICALLY_QUALIFIED / EXTERNAL_REVIEW_REQUIRED
WORK_ORDER: UGAS-WO-0230-VFX-FND-CD3
VERSION: 0.23.3
CORRECTS: F-26S, F-29, F-30
REJECTED_HEAD: d7501177a9f4480921226b9832ffc237544a6433
PR: #14
BRANCH: `codex/v0.23.0-vfx-asset-family-runtime-foundation`
BASE_MAIN_SHA: `b08b9c3df74ef6a23046be396289e2fd72dc336b`

This is a forward-only correction on the existing PR #14. The v0.23.2
runtime/evidence remains immutable `CORRECTION_REQUIRED` history. The new
runtime validates degraded pixels against the authoritative fallback result,
replays the exact ordered fallback policy, binds frozen history to immutable
reviewed git refs, and persists a real independently-rendered second degraded
output.

The active evidence root is
`docs/evidence/vfx-asset-family-runtime-v0233/`. It is TEST_ONLY. Production
remains `BLOCKED`, `production_approved=false`, `real_vfx_asset_coverage=NONE`,
`synthetic_vfx_fixture=TEST_ONLY` and `new_generation=0`.

F-26S proof includes decoded alpha/area/frame-selection metrics, exact pixel
re-render comparison, exact fallback replay, terminal `SKIP_VISUAL` handling,
and rejection controls for copied full bytes and unrelated valid PNGs.

F-29 proof resolves v0.23.0 from reviewed ref
`c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72` and v0.23.1 from reviewed ref
`136079540f674c7467d93bd28e9834addbfce5c3`, including tree/blob/raw-byte
identity and isolated mutation rejection.

F-30 proof stores first and repeat output roots with independent frame hash
sets. Equality is reported only after validating the actual second render.

The final PR head and bounded artifact identity are resolved from GitHub LIVE
after the correction is pushed. Do not merge, do not start Orchestration, do
not enable production and do not generate real VFX. Hand back to Sol after
the exact-head contexts and bounded artifact pass.

Checkpoint Delta: v0.23.2 F-23R/F-26R/F-27R remains frozen correction history;
v0.23.3 advances only F-26S/F-29/F-30 on the same PR and branch.
