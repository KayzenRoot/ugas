# UGAS v0.17.1 — EQUIPMENT_OUTFITS runtime and QA integrity correction

This is a correction-only execution for the existing PR #7 and branch `codex/v0.17.0-equipment-outfits-runtime-foundation`, based on approved v0.16.2 commit `a8d2897211c4b72c2cd2fe7a7f5729c7009d8566`. The reviewed v0.17.0 head `1c73e6a2ff5259226afe9ca03ef10e1822a7fdf2` is preserved as `CORRECTION_REQUIRED`; its evidence directory is historical and must not be overwritten.

## Direct request and document instructions

The direct user request supplied no additional implementation text. The attached corrective PDF is therefore the governing executable document for this turn. It requires the v0.17.1 correction to remain inside `EQUIPMENT_OUTFITS`; creatures and monsters are forbidden. The v0.17.0 candidate remains rejected history, and PR #7 remains open and unmerged for external review.

## Integrity corrections

The negative-control harness records an expected error code and rejection class and passes only on an observed `REJECTED` result. A normal return is `ACCEPTED_UNEXPECTEDLY`, and an unexpected exception is `ERROR`. EQ-NC-08 poisons the real runtime cache in both request orders. EQ-NC-11 mutates an after-image through the shared base comparator. EQ-NC-12 mutates one pixel in the second equivalent composition through the shared comparator.

Replacement arbitration now selects exactly one winner by `highest_priority_then_equipment_id`, records candidates/winner/hidden parts/loser suppression, clears named base parts before the winner renders, and proves the result in pixels. Asset-bound occlusion masks have deterministic rectangle geometry, content hashes, application policy, affected pixel counts and layer traces. Mirror is explicitly fail-closed as `MIRROR_RUNTIME_NOT_IMPLEMENTED`; no `HORIZONTAL_EXPLICIT` result is emitted without actual pixel mirroring. Declared `secondary_anchor` is explicitly rejected until a runtime effect is implemented.

The v0.17.1 TEST_ONLY registry contains synthetic fixtures only. The separate production registry contains zero assets. Real directional character coverage remains `SOUTH_ONLY`; real equipment coverage remains `NONE_OR_EXPLICITLY_APPROVED_ONLY`; `production_approved=false`, `production_routing=BLOCKED`, and `new_generation=0` remain authoritative.

## Required validation and gates

Run system Python 3.12 compile/tests, the v0.17.1 state validator, v0.17.1 equipment runtime validator, official validation, v0.16.2 direction/cache regression, approved front animation regression, workflow validation, Docker dashboard smoke, and the GitHub review workflow. The exact GitHub contexts remain `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke`, and `UGAS Review / evidence`. The bounded artifact must bind PR #7, exact base/head SHAs, all gate results, the TEST_ONLY contact sheet, corrected evidence, state and security boundaries.

The acceptance gate is `EQUIPMENT_OUTFITS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED`. After the corrected head completes all required actions and the exact-head artifact exists, keep PR #7 OPEN, do not merge, do not start creatures/monsters, and hand off to Sol for external equipment/outfits review. External approval is not inferred from local or GitHub green checks.
