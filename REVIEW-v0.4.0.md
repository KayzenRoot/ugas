# UGAS Prompt 03 v0.4.0 Review

## STATUS
READY_FOR_EXTERNAL_REVIEW — implementation and real local qualification completed; human visual approval and production approval are not claimed.

## VERSION
0.4.0

## PHASE
2D master sprite, native transparency and reference-edit qualification

## OBJECTIVE
Turn the v0.3.1 technical MVP into a reproducible 2D master pipeline with Art DNA, candidate generation/ranking, native BiRefNet transparency, reference edit, revision provenance and explicit visual gates.

## SCOPE
Only 2D master assets, reference editing, background removal, alpha QA, evidence, documentation and safe review packaging. Full animation, grid greater than 1, 3D, Blender, audio, paid providers, cloud inference and custom nodes remain excluded.

## BASELINE v0.3.1
The v0.3.1 tracked snapshot was published on `main` with 23 unit tests, 143 repository checks and an honest 1x1 Sprite Pilot. Its visual approval and production approval were pending.

## FILES CREATED/CHANGED
Added `src/ugas/master_assets.py`, the four v0.4.0 schemas, official API workflows, candidate/reference/transparency evidence and `docs/2d-master-pipeline.md`. Updated runtime version surfaces, CLI, routing, registries, validation, README, INSTALL, ComfyUI documentation, roadmap, checkpoint and tests.

## MASTER-ASSET SPEC / ART DNA
`master-asset-spec.json` persists category, view/orientation, Art DNA, palette, silhouette/outline, lighting, detail density, occupancy, margins, pivot, transparency requirement, negative constraints, candidate count and deterministic seeds. `compile_prompt()` is stable and its SHA-256 is recorded.

## REFERENCE-EDIT WORKFLOW
`flux2-klein-4b-image-edit` is the Comfy-Org official FLUX.2 Klein 4B image-edit blueprint flattened to API format. It uses `LoadImage`, `VAEEncode`, `ReferenceLatent`, native FLUX.2 sampling and `SaveImage`, with zero custom nodes. Live graph validation passed and the real smoke produced `reference-edit-3.png` with source SHA-256 `61a7e5b...`, output SHA-256 `1aeb7f4...`, instruction-bound provenance and runtime 34,598 ms.

## BACKGROUND-REMOVAL / BIREFNET
`birefnet-background-removal` uses native `LoadBackgroundRemovalModel`, `RemoveBackground`, `InvertMask`, `JoinImageWithAlpha`, `MaskToImage` and two `SaveImage` nodes. Live validation passed; the final smoke produced RGBA 384x384 output with transparent pixels, preserved mask, no detected border halo and output SHA-256 `7df6435...`. No RGB-to-RGBA conversion was used as proof.

## MODEL REGISTRY / LICENSES / HASHES
FLUX.2 Klein 4B NVFP4 is registered as Apache-2.0 with exact local hashes. Comfy-Org BiRefNet is registered as MIT with exact file SHA-256 `9AB37426BF4DE0567AF6B5D21B16151357149139362E6E8992021B8CE356A154`. Weights remain outside Git and the review ZIP.

## CAPABILITY EVIDENCE
`docs/evidence/comfyui-smoke.json` covers the existing 2D path. `docs/evidence/reference-edit.json` qualifies `reference-edit`. `docs/evidence/birefnet.json` qualifies `background-removal` and `transparent-sprite-master`. Declarations and transport health are never treated as asset qualification.

## RTX 5050 REAL RUN
ComfyUI 0.34.0 ran locally on NVIDIA GeForce RTX 5050 with 8,546,484,224 bytes total VRAM. The run recorded model/workflow IDs, exact hashes, seeds, source/output hashes, timing, native-node validation and QA evidence. Candidate generation used 384x384 and three independent seeds because 512 was not assumed.

## CANDIDATE RESULTS
Three candidates were generated with seeds 4301, 4302 and 4303. Candidate-1 is the deterministic best technical rank with objective score 5 and SHA-256 `9eeea7e...`; candidate-2 and candidate-3 scored 4. The contact sheet and complete metrics are in `docs/evidence/candidates.json`. Edge clipping/occupancy findings are disclosed and remain subject to human visual review.

## TRANSPARENCY QA
The final transparent master is RGBA, 384x384, has an alpha channel and transparent pixels, has a preserved native BiRefNet mask, passes technical QA and reports `halo_detected=false`. The final transparent asset revision is `VISUAL_REVIEW_REQUIRED`, not production-ready.

## REFERENCE-EDIT RESULT
The real edit requested preservation of identity/silhouette while changing armor toward blue steel and shortening the sword slightly. The output is persisted as a new revision with `derived_from`, source SHA-256, instruction, seed, workflow SHA-256, model ID and technical QA. A subsequent native BiRefNet pass created the current transparent revision.

## VISUAL REVIEW STATUS
`VISUAL_REVIEW_REQUIRED`; no human approval is inferred from technical QA, alpha QA, contact-sheet ranking or this report. Use `ugas visual approve <asset-id>` only after an actual human review of the packaged visuals.

## TESTS / VALIDATION / COMPILE
Final results are recorded below after the last code/documentation changes. The suite includes unit tests, compileall, schema/registry checks, routing and capability-gap checks, no-Git snapshot regression, exact `git archive HEAD` install/test/validation and safe review-visual manifest checks.

## TRACKED SNAPSHOT / GITHUB
The final commit and `main` remote synchronization are recorded after validation. The repository remains free of model weights, caches, tokens and environment files.

## SECURITY / SECRETS CHECK
The review generator excludes weights, caches, `.env`, credentials, private keys, generated `tmp`, `node_modules`, `.git` and itself. Visual evidence is injected only from the explicit safe manifest and the archive is integrity-validated.

## PENDING / RISKS
Human visual approval, production approval and any real animation/grid >1 capability remain pending or out of scope. Candidate-1 has an edge-clipping metric finding; this is disclosed rather than silently promoted to artistic approval.

## CHECKPOINT UPDATED
`CHECKPOINT.md` was rewritten to a single v0.4.0 checkpoint and preserves the explicit visual/production gate.

## NEXT STEP
Review the four packaged visuals. If accepted, explicitly approve the same current revision; if rejected, create another derived revision and repeat the required QA.

## DEFINITION OF DONE
All in-scope Prompt 03 v0.4.0 implementation, real capability smoke, evidence, tests, tracked publication and safe packaging requirements are satisfied without claiming human approval or production readiness.

## REVIEW ZIP PATH
Final path is appended here only after the ZIP is generated as the last filesystem action.
