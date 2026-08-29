# UGAS Review v0.4.3 — PROMPT-03E

## STATUS

`READY_FOR_REVIEW / VISUAL_REVIEW_REQUIRED`. The correction is implemented and technically validated. Human visual approval and external audit are not inferred.

## VERSION

`0.4.3`

## FASE

Reference-edit fidelity, fresh execution evidence and revision-integrity correction.

## OBJETIVO

Prevent the v0.4.2 failure where a color-only request changed whole-character lighting/appearance. The new gate distinguishes silhouette preservation from photometric and protected-region fidelity.

## ESCOPO

Capability-specific native ComfyUI image-edit qualification; fresh anti-stale evidence; machine-readable color-only contract; two-configuration benchmark; four generative candidates; deterministic armor recolour; appearance/head/protected-region QA; immutable R1-R4 chain; transparency/RGB QA; tests, documentation, GitHub snapshot and review evidence. Animation is excluded.

## PREVIOUS AUDIT FINDINGS

The v0.4.2 R3/R4 edit was rejected by visual audit: R2/R4 structural IoU was high, but the face, skin exposure and global lighting became dramatically darker. This historical darkening is explicitly a failing fixture for the v0.4.3 appearance gate. Its recorded runtime of approximately 620 ms was also not plausible against same-machine quality jobs without fresh binding evidence. The historical review and evidence remain immutable.

## WORKFLOW UPSTREAM QUALIFICATION

The Base image-edit lane is independently qualified from the Comfy-Org native Image Edit workflow. Upstream source is `Comfy-Org/workflow_templates`, `templates/image_flux2_klein_image_edit_4b_base.json`, commit `d3b4a9e89573162b005961865164c18c8ae2206b`, SHA-256 `346cd9a63bfe34a5a9207f50c34a87feaf4e70806d13c9d2738fd521133670d0`. The ComfyUI blueprint reference is recorded with repository/path/commit/hash. Materialized sources are under `docs/evidence/upstream/`; runtime qualification is in `docs/evidence/reference-edit-workflow-qualification.json`.

## IMAGE-EDIT PARAMETERS

Current Base image-edit: Euler, Flux2Scheduler, 20 steps, CFG 5. Text-to-image is unchanged: Base 50/4 and Distilled 4/1.0. Legacy image-edit 50/4 was run only as a labeled comparison and is not current qualification. Native nodes only; no custom node was introduced.

## FRESH EXECUTION EVIDENCE

The real pilot used a fresh cloned asset `asset-2fec6fed1d714d0cb58ad75b56d7ba71` from the v0.4.2 R2 source, with new R1/R2 IDs and no mutation of the historical asset. Eight image-edit submissions used benchmark seeds `10001–10004` and candidate seeds `10501–10504`; each has a unique UGAS client job ID, ComfyUI `prompt_id`, exact history key, output filename/subfolder/type/hash, model-file hashes, workflow hash and timestamps. All eight bindings are exact, all target paths were absent before submit, and runtime plausibility passed at same-machine scale. BiRefNet comparison jobs are also recorded. No stale or wrong-history result was accepted.

## EDIT CONTRACT

`docs/evidence/reference-edit-contract.json` is schema `0.4.3`, contract SHA-256 `7782899561be4e7de6f78864658cc7e2af55e8fa3b3f0d41e56f925204124bf1`. Allowed change is only blue-steel armor to deep cobalt/navy steel. Protected properties include face identity, skin tone, facial exposure/lighting, hair, proportions, exact pose, camera, silhouette, sword shape/position, black cloth, non-target foreground and the pre-removal composition. Identity, pose, camera, silhouette and exposure preservation are mandatory.

## DETERMINISTIC COLOR ROUTE

The source R2 target mask uses documented HSV hue/saturation/blue-dominance rules, foreground alpha restriction and an 8-connected sword-like component exclusion. Confidence was `0.4662`, above the `0.40` threshold. Recolour moves hue near 220 degrees while preserving luminance/texture; outside-target RGB is bit-for-bit unchanged before BiRefNet. Deterministic output remains subject to native transparency QA and human visual review.

## GENERATIVE CANDIDATE SET

The official and legacy benchmark groups each had zero eligible candidates. Four fresh generative candidates were executed with the official 20/5 lane and retained as temporary evidence. All four were rejected by the appearance gate for global/head/protected-region changes and/or target-direction failure; none was promoted to a revision. The selected candidate is `deterministic-recolor`, not a hidden generative candidate. Candidate JSON preserves every failure and records that temporary candidates are not revisions.

## REFERENCE EDIT FIDELITY QA

The historical darkening pattern fails the new global luminance, head luminance and protected RGB/change gates despite high IoU. The selected deterministic result passed `REFERENCE_EDIT_FIDELITY_PASSED`: silhouette IoU `0.998102`, centroid drift `0.000180`, bbox delta `0.0`, foreground luminance ratio `0.996128`, head luminance ratio `1.0`, head MAE `0.0`, protected RGB MAE `0.0`, global change fraction `0.0`, target hue destination near 220 degrees and target-direction score positive. Thresholds are stored in the contract and fidelity JSON.

## SELECTED CANDIDATE

Selected route: `deterministic-recolor`; selected candidate ID: `deterministic-recolor`. R3 is `revision-112e881cc787478abb713b0b52b2165c`, SHA-256 `d8d66a20b2b15b9c5218703e85062918d999a4bf9ef27f9d8fcafe6bcadd2d3c`. The visual preview preserves the face and sword while changing armor toward cobalt/navy.

## REVISION CHAIN

The current v0.4.3 asset is `asset-2fec6fed1d714d0cb58ad75b56d7ba71`:

`R1 RGB -> R2 transparent -> R3 selected RGB -> R4 transparent`

R1 `revision-ae8c4267462947f5bc529a4cab95d883` — `6a69069f25d5b9b2ad0d1f8a05a648d4047163e84b789e9a0328eba21385f8c7`

R2 `revision-2c67bd7917a04fb39d49a9b9e0eefcc3` — `1045c76fd1fb97632e2eb69f99244326c0acba837372a7afb2a531cca9388488`

R3 `revision-112e881cc787478abb713b0b52b2165c` — `d8d66a20b2b15b9c5218703e85062918d999a4bf9ef27f9d8fcafe6bcadd2d3c`

R4 `revision-3a425d184b1a49be9f6d6c8d52d04b96` — `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`

## TRANSPARENCY / RGB PRESERVATION

R4 was created by native BiRefNet after the selected RGB edit. The original selected RGB was joined with the native alpha; transparency QA is `TECHNICAL_VALID`, RGB MAE is `0.0`, no border contact or halo was detected, and revision integrity passed. The comparison run used `promote=false`, so only selected R3/R4 entered the revision chain.

## REAL RTX 5050 PILOT

The fresh pilot ran against local ComfyUI `0.34.0` on `NVIDIA GeForce RTX 5050`, with the registered Base model and BiRefNet model. It used unique seeds, fresh job directories, exact prompt/history/output binding and the documented official/legacy benchmark plus four-candidate set. The historical ~620 ms result was not reused; current image-edit runtimes were approximately 49–70 seconds and were plausible against the same-machine benchmark.

## VISUAL REVIEW STATUS

Local visual inspection covered the before/after, selected checkerboard, generative candidate sheet, target/protected masks and diff heatmap. The selected deterministic preview is coherent and preserves the face and sword visually. This inspection is evidence for review, not approval. Explicit human approval remains pending for R4 and its SHA-256.

## TESTS

The new `tests/test_reference_edit_fidelity_v043.py` adds 21 regression tests for exact binding, stale output, unique seeds, runtime plausibility, capability parameters, contract fields, photometric/head/protected failures, valid recolour, candidate selection, controlled zero-eligible behavior, temporary revisions, manifest hashes, version and historical mapping. The full suite must remain a superset of the prior coverage.

## VALIDATION

The canonical validator is updated for v0.4.3 and checks schemas, registries, official image-edit parameters, source hashes, contract, fresh evidence, candidate count/status, fidelity rejection of darkening, selected R1-R4 integrity, review roles, version surfaces, docs, security, compileall, unit tests, exact Git snapshot and no-Git snapshot. Final numerical results are recorded after the final tracked commit.

## TRACKED SNAPSHOT / GITHUB

Only source, docs, schemas, registries, tests and safe review evidence are tracked. Weights, secrets, caches, `tmp/`, `review/` and the local ZIP helper remain excluded. Publication target is [csn1985-ship-it/ugas](https://github.com/csn1985-ship-it/ugas). External GitHub state is reported only after matching local commit and remote `origin/main` verification.

## SECURITY / SECRETS CHECK

No model weights, `.env` files, credentials or local caches are included in the tracked snapshot or review package. Upstream evidence contains public repository metadata and hashes only. The review ZIP must be generated from the final published snapshot and inspected for forbidden paths.

## PENDENCIAS

Human visual approval/rejection bound to R4 and its SHA-256; external audit of the corrected image-edit behavior.

## BLOQUEIOS

No local engineering blocker remains. Production readiness is blocked only by the explicit human visual review gate and any subsequent external audit decision.

## DECISOES

Preserve v0.4.2 text-to-image semantics. Qualify image-edit separately at official Base 20/5. Keep legacy 50/4 as comparison only. Prefer deterministic armor recolour when target-mask confidence is sufficient; always retain and test generative candidates. Never overwrite historical revisions, infer approval or authorize animation.

## PROXIMO PASSO

A human reviewer should inspect the archived evidence and approve or reject the exact R4 revision/hash. If rejected, run another bounded reference-edit correction; do not begin animation.

## DEFINITION OF DONE

The 03E contract, capability-specific workflow, upstream evidence, fresh binding, benchmark, four generative candidates, deterministic route, appearance/protected-region gates, selected R1-R4 chain, transparency/integrity evidence, tests, docs, validation, tracked snapshot, GitHub publication and final review ZIP are complete. Human approval remains explicitly separate.

## REVIEW ZIP

The final `UGAS-v0.4.3-review.zip` is generated only after final validation and remote commit verification, as the last filesystem action. Its exact path, SHA-256 and contents are reported in the final handoff.
