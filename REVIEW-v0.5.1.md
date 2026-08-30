# UGAS REVIEW v0.5.1

## STATUS

MULTI_REFERENCE_POSE_CONTROL_GAP - walk blocked. The final local result is fail-closed and is based on fresh v0.5.1 RTX 5050 evidence.

## VERSION

0.5.1.

## PHASE

Animation fidelity and reproducibility correction over the published v0.5.0 pilot. Execution stopped at the mandatory multi-reference causal gate; directional anchors and walk were not run.

## OBJECTIVE

Correct the undefined `generated` walk bug, prove causal multi-reference pose control, preserve R4 identity, and only then run walk/front/8 with strict frame and temporal QA.

## BASELINE / V0.5.0 FINDINGS

Baseline commit: `10d201f39c23386fdd5e4aae3daebe88ec6e07fa`. The v0.5.0 visual review is retained as a negative baseline. Its engineering evidence is historical and is not reused as v0.5.1 success.

The immutable identity anchor remains asset `asset-2fec6fed1d714d0cb58ad75b56d7ba71`, revision `revision-3a425d184b1a49be9f6d6c8d52d04b96`, SHA-256 `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`.

## REPRODUCIBILITY FIX

`generate_walk_frame_candidate()` calls `_run_reference()` explicitly for every frame and attempt, then calls BiRefNet, normalization and scoring. There is no residual `generated` variable and no previous-frame input. The fake end-to-end smoke exercises `generate_walk_pilot()` through the real reference path.

Uniform scale is applied only when a generated alpha bbox cannot fit the declared safe margins with the fixed centerline/baseline. The scale, pre/post bbox, root/feet translation and delta are recorded; there is no non-uniform stretch.

## POSE GUIDE V2

JSON keypoints remain authoritative. Pillow renderer `2.0.0` produces a filled neutral mannequin at 512x512 without labels or watermark for model control. A separate review overlay includes labels and reference axes. Left/right views declare strict profile geometry. Guide JSON hash, control-image hash, renderer version and render parameters are recorded.

## MULTI-REFERENCE V2 QUALIFICATION

Three paired seeds use the same model, workflow parameters and prompt: A is canonical R4 only; B is canonical R4 plus the strong left-profile, raised-arm, advanced-leg mannequin. `MULTI_REFERENCE_QUALIFIED` is allowed only when every B is valid, B pose mean is at least A plus 0.15, B pose mean is at least 0.70, no B is below 0.60, identity/weapon gates pass, and fresh prompt/history/output evidence passes. Otherwise the status is `MULTI_REFERENCE_POSE_CONTROL_GAP`.

Fresh real run on the local RTX 5050 used paired seeds `51701`, `51702`, and `51703`. All six jobs have prompt/history/output bindings and no stale targets. A scored `3/3` with mean pose `0.757982`; B scored `3/3`, all B records were valid, with mean pose `0.898232` and minimum identity descriptor `0.830673`. The causal gain was `0.140250`, below the required `0.150000`; therefore the final status is `MULTI_REFERENCE_POSE_CONTROL_GAP`.

## IDENTITY FIDELITY V2

Identity is scored separately from pose using regional armor palette/material, head/face, black cloth, body proportions and weapon presence descriptors. Rejection reasons and component scores are recorded for every candidate.

## DIRECTIONAL ANCHOR V2

Only runs after multi-reference v2 qualification. Front is copied byte-for-byte from R4. Generated directional candidates are ranked by pose, identity, margin and scale stability; seed is used only as a deterministic exact tie-breaker. Technical selection is not visual approval.

## WALK FRONT 8 V2

Only runs after the multi-reference and directional technical gates. Every frame uses R4 as reference[0] and its own mannequin as reference[1]. At most two attempts are normal and a third is allowed only for a frame that failed the first two. A failed frame produces `NO_ACCEPTABLE_FRAME` and no approved spritesheet.

## FRAME QA

Each selected frame must pass PNG/RGBA/transparency/BiRefNet, safe-margin normalization without non-uniform stretch, pose threshold, identity threshold, weapon presence, drift limits, correct anchor/guide hashes and fresh execution binding. No v0.5.1 walk frame was selected because the causal multi-reference gate stopped the pipeline first.

## TEMPORAL QA V2

The gate records pose phase, lower-body motion, mirrored half-cycle IoU, robust adjacent-difference statistics, last-to-first closure factor, height/root stability, identity descriptor stability, weapon presence and no previous-frame chaining. Height variance is limited to 5%; last-to-first is compared with the robust median rather than an absolute permissive ceiling.

## PACKING

Spritesheet and GIF are created only after temporal QA v2 passes. Diagnostic candidate/overlay/drift evidence may exist on a failed run, but a failed run never uses the approved pack paths.

## EXECUTION EVIDENCE

`docs/evidence/execution-evidence-v0.5.1.json` binds six fresh client job IDs, prompt IDs, exact history keys, output hashes, seeds `51701–51703`, workflow/model hashes, R4 hash, guide JSON/image hashes, stale-target checks and no-chain policy. `all_prompt_ids_present`, `all_history_bindings_exact` and `stale_output_rejected` are true.

## TESTS

The 89 existing tests are preserved and 10 v0.5.1 tests were added; the full suite runs 99 tests. New coverage includes the real reference path with a fake ComfyUI runtime, pose metrics, bbox-only rejection, quality ranking, identity drift, static/incoherent temporal failure, half-cycle evidence, mannequin/control separation and uniform normalization.

## VALIDATION

Compileall passed and the complete suite passed with 99 tests. `scripts/validation/run_validation.py` passed with 248/248 checks, including the exact `git archive HEAD` snapshot and the no-Git snapshot; each snapshot also passed compileall and all 99 tests.

## TRACKED SNAPSHOT / GITHUB

Baseline is `10d201f39c23386fdd5e4aae3daebe88ec6e07fa`. The v0.5.1 implementation/evidence commit is `5e16706`; final publication must prove clean working tree, `main` pushed, and `origin/main == HEAD`. No external approval is inferred from local readiness.

## SECURITY / LICENSES

Weights and model caches remain outside Git and the review ZIP. Existing license manifests and historical governance are preserved. No secrets, credentials or paid/cloud provider were added.

## VISUAL REVIEW STATUS

Human visual review is required for every v0.5.1 selected visual artifact. This document never sets `VISUALLY_APPROVED` or `PRODUCTION_READY` automatically.

## PENDING

Fresh RTX 5050 results are recorded above. External visual review and any explicit production approval remain pending; local technical evidence never grants either approval.

## BLOCKERS / GAPS

The measured blocker is `MULTI_REFERENCE_POSE_CONTROL_GAP`: B is technically valid, but the causal pose gain is `0.140250`, below `0.15`. This blocks directional anchors, walk generation, temporal QA and v0.5.1 packing. The missing gain must be solved by a future controlled correction; thresholds are not relaxed.

## DECISIONS

Do not loosen thresholds, use seed-based selection, reuse v0.5.0 outputs as success, add forbidden control methods, or fabricate a spritesheet after a failed gate.

## NEXT STEP

Push the tracked implementation, verify `origin/main == HEAD` and a clean working tree, then create `review/UGAS-REVIEW-v0.5.1.zip` as the final filesystem write.

## DEFINITION OF DONE

v0.5.1 is done only when code, tests, docs, evidence, version surfaces, snapshot/no-Git checks, clean GitHub publication and final review ZIP are complete. Technical readiness remains distinct from human visual approval.

## REVIEW ZIP

The final archive is `review/UGAS-REVIEW-v0.5.1.zip`; its SHA-256 is computed after creation and reported with the read-only archive verification. The ZIP is not created before all other filesystem changes finish.
