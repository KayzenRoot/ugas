# UGAS Checkpoint

## STATUS
READY_FOR_EXTERNAL_REVIEW — Prompt 03 v0.4.0 is implemented, tested, published and qualified on the local RTX 5050 path. Human visual approval and production approval are not claimed.

## VERSION
0.4.0

## PHASE
2D master sprite, native transparency and reference-edit qualification

## OBJECTIVE
Provide a reproducible 2D master-asset pipeline with deterministic Art DNA/spec compilation, multi-candidate ranking, native BiRefNet alpha, official FLUX.2 Klein reference editing, revision provenance and explicit visual gates.

## SCOPE
Only 2D master assets, reference edit, background removal, alpha QA, provenance, documentation and safe review packaging. Full animation, grids greater than 1, 3D/Blender, audio, cloud inference, paid providers and arbitrary custom nodes remain excluded.

## COMPLETED
- Master-asset spec, Art DNA compiler, candidate-set, visual-assessment and asset-revision contracts are implemented.
- Three real 384x384 candidates were generated with deterministic seeds 4301-4303; contact sheet and objective ranking are recorded.
- Official FLUX.2 Klein 4B image-edit workflow passed live native-node validation and a real reference-edit smoke on ComfyUI 0.34.0.
- Native BiRefNet passed live validation and a real RTX 5050 smoke with RGBA output, mask, transparent pixels and no detected border halo.
- Revision history preserves the original candidate, transparent master, reference edit and final transparent revision; no master is overwritten.
- CLI commands are available for `generate master-sprite`, `refine master-sprite`, `background remove`, `candidates show`, `visual approve` and `asset status`.
- Validation distinguishes missing `.git` from missing distributable files and reports `SKIP_EXTERNAL_GIT_CONTEXT` in review snapshots.

## REAL EVIDENCE
- Asset: `asset-b5a3a5e1368c44a4a40ba1ec338fbb37`.
- GPU/server: NVIDIA GeForce RTX 5050, ComfyUI 0.34.0; model registry hashes and licenses are tracked.
- Reference edit: `reference-edit-3.png`, source SHA-256 `61a7e5b...`, output SHA-256 `1aeb7f4...`, runtime 34,598 ms.
- BiRefNet final output SHA-256 `7df6435...`, RGBA 384x384, mask SHA-256 `606bd28...`, runtime 1,460 ms, halo detector false.
- Full values are in `docs/evidence/candidates.json`, `docs/evidence/reference-edit.json` and `docs/evidence/birefnet.json`.

## GATES
Technical QA and transparency QA are machine checks. Visual review remains required. Approval must be explicit, same-revision and actor/date/hash-bound; refinement invalidates any prior approval. The current asset remains `VISUAL_REVIEW_REQUIRED` and `production_ready=false`.

## BLOCKERS
No in-scope native capability blocker remains. Candidate-1 has a disclosed edge-clipping metric finding and candidates 2-3 are objectively weaker; a human reviewer may reject the visuals and request another refinement.

## DECISIONS
- Model weights stay outside Git and review ZIPs; exact source, license and SHA-256 metadata is tracked.
- The BiRefNet and image-edit workflows use native ComfyUI nodes only and no custom nodes.
- The official sources and licenses used are documented in `docs/comfyui.md`.
- Animation and `sprite-grid > 1` remain explicit capability gaps.

## TEST EVIDENCE
`python -m compileall -q src scripts tests` passed; unit suite passed `26/26`; repository validation passed `165/165`, including the exact `git archive HEAD` install/test/validation and the nested no-Git regression. The checks include schemas, routing, fake `/upload/image`, workflow injection, model/workflow registry, real evidence presence and controlled unavailable capability.

## NEXT STEP
Perform the human visual review from the final ZIP. If approved, use the explicit `ugas visual approve <asset-id>` command; otherwise create a new revision and repeat transparency QA.

## DEFINITION OF DONE
Prompt 03 v0.4.0 is implemented and published with real qualified capabilities, safe review evidence and no production-ready claim without explicit same-revision visual approval. Prompt 04 and excluded slices were not started.

## REVIEW ZIP PATH
Recorded in `REVIEW-v0.4.0.md`; the exact absolute path is returned in the final handoff after ZIP validation.
