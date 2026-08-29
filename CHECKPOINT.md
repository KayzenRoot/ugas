# UGAS checkpoint - v0.4.3

**STATUS:** READY_FOR_REVIEW / VISUAL_REVIEW_REQUIRED. The 03E implementation, fresh RTX 5050 pilot, fidelity QA, transparency QA, revision integrity and regression evidence are complete; human visual approval remains separate.
**VERSION:** 0.4.3
**FASE:** Reference-edit fidelity and revision-integrity evidence
**OBJECTIVE:** Prevent the v0.4.2 whole-character darkening failure by independently qualifying image-edit parameters, binding fresh execution evidence, measuring appearance/protected regions and using deterministic recolour when safe.
**SCOPE:** Capability-specific Base image-edit 20/CFG5, legacy comparison 50/CFG4, machine-readable edit contract, four fresh generative candidates, deterministic HSV route, photometric/head/protected-region QA, immutable R1-R4 output chain, documentation, validation and GitHub publication. No animation authorization.

## COMPLETED

- Preserved the v0.4.2 text-to-image semantics: Distilled 4/1.0 and Base 50/4.
- Qualified the native Base image-edit graph separately at 20 steps, CFG 5, Euler and Flux2Scheduler, with upstream source/commit/hash and installed ComfyUI evidence.
- Added exact `job_id -> prompt_id -> history -> output` evidence, unique seeds/job folders and stale-output rejection.
- Added the v0.4.3 edit contract protecting identity, face/skin/exposure, pose, camera, silhouette, sword, black cloth and non-target pixels.
- Ran the real RTX 5050 pilot with a two-configuration benchmark and four fresh generative candidates. All generative candidates were retained and rejected by appearance gates; the legacy and official benchmark groups had zero eligible generative candidates.
- Selected deterministic armor-only recolour after confidence/mask QA. It preserves luminance and leaves the sword outside the target mask. The new asset has immutable R1 RGB, R2 transparent source, R3 selected RGB and R4 transparent result.
- R4 passed native BiRefNet transparency/RGB QA, structural QA and revision integrity. Human approval is still pending.

## EVIDENCE

Current pilot asset: `asset-2fec6fed1d714d0cb58ad75b56d7ba71`.

The authoritative v0.4.3 review material is in `docs/evidence/`: contract, upstream qualification, configuration benchmark, candidate set, execution evidence, fidelity JSON, selected RGB/transparent/checkerboard, target/protected masks, diff, transparency QA and `revision-chain.json`. The historical `REVIEW-v0.4.2.md` and its evidence remain unchanged.

## PENDING

- Human visual approval or rejection bound to selected R4 revision ID and SHA-256.
- External audit of the corrected reference-edit behavior.

## BLOCKERS

No implementation, local ComfyUI, GPU, integrity or validation blocker remains. The release gate is human visual review because automation cannot certify identity or artistic acceptability.

## DECISIONS

Keep text-to-image lanes unchanged. Use Base image-edit 20/5 only for the independently qualified image-edit capability. Treat 50/4 image-edit as a labeled legacy benchmark, never as current qualification. Prefer deterministic recolour for a confident armor mask; retain generative testing as a required fallback/diagnostic. Never overwrite a revision or infer human approval. Do not authorize animation.

## TEST EVIDENCE

The suite contains the historical v0.4.0/v0.4.2 coverage plus 21 v0.4.3 reference-edit fidelity/evidence regressions. The 03E validation requires at least 76 tests, including synthetic darkening/head/protected-region failures and valid recolour passes.

## NEXT STEP

Inspect the archived visual evidence and decide human approval using the selected R4 revision ID/hash. If rejected, create a new bounded correction; do not proceed to animation.

## DEFINITION OF DONE

03E contract and capability qualification are versioned; upstream and runtime sources are hash-recorded; fresh execution binding is complete; four generative candidates and deterministic route are evidenced; photometric/protected-region gates reject the historical dark failure; only selected R3/R4 are revisions; technical/transparency/integrity checks pass; docs, tests, tracked snapshot and GitHub are verified; final ZIP is validated; human visual approval remains explicit.
