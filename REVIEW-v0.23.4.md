# UGAS VFX Asset Family v0.23.4 - Review Handoff

STATUS: TECHNICALLY_QUALIFIED / EXTERNAL_REVIEW_REQUIRED
WORK_ORDER: UGAS-WO-0230-VFX-FND-CD4
VERSION: 0.23.4
CORRECTS: F-29R
REJECTED_HEAD: 9eda08b25a674a5423a99d35a42711102df91b8b
PR: #14
BRANCH: `codex/v0.23.0-vfx-asset-family-runtime-foundation`
BASE_MAIN_SHA: `b08b9c3df74ef6a23046be396289e2fd72dc336b`

This is a forward-only correction on the existing PR #14. The v0.23.0,
v0.23.1, v0.23.2 and v0.23.3 runtime/evidence remain immutable history.
The v0.23.4 correction preserves the validated VFX runtime behavior and
corrects F-29R by deriving the current candidate tracked tree from Git
objects, comparing the exact path/mode/type/blob/raw-byte set to both
historical authorities, and exercising real extra-file and byte-mutation
rejection paths.

The active evidence root is
`docs/evidence/vfx-asset-family-runtime-v0234/`. It is TEST_ONLY. Production
remains `BLOCKED`, `production_approved=false`, `real_vfx_asset_coverage=NONE`,
`synthetic_vfx_fixture=TEST_ONLY` and `new_generation=0`.

F-29R positive proof validates the live candidate `HEAD` tree against the
v0.23.0 authority `c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72` and the v0.23.1
authority `136079540f674c7467d93bd28e9834addbfce5c3`. The same reusable
validator rejects an unauthorized extra file, a byte mutation in each root,
and byte mutations in `REVIEW-v0.23.0.md` and `REVIEW-v0.23.1.md` with the
stable class `VFX_HISTORICAL_IMMUTABILITY_REJECTED`. The focused tests also
prove that an extra entry committed to an observed Git `HEAD` is rejected;
the implementation does not substitute an expected path list for observed
tree enumeration.

The generated v0.23.4 evidence records 33 strict boolean hard gates, 18
runtime negative controls, exact historical tree/file fingerprints, two-run
determinism, production boundary and the forward-only correction record bound
to rejected head `9eda08b25a674a5423a99d35a42711102df91b8b`.

UADS governance is GLOBAL-FIRST: executor work orders are routed and
dispatched through the global UADS runtime; operational state remains external
with zero repository footprint. Hive and additional orchestration harnesses
remain disabled until an explicitly authorized later work order.

The final PR head and bounded artifact identity are resolved from GitHub LIVE
after the correction is pushed. Do not merge, do not start Orchestration, do
not enable production and do not generate real VFX. Hand back to Sol after
the exact-head contexts and bounded artifact pass.

Checkpoint Delta: v0.23.3 F-26S/F-29/F-30 remains frozen correction history;
v0.23.4 advances only F-29R on the same PR and branch. Historical roots and
review files remain unchanged.
