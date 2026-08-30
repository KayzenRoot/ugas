# UGAS v0.7.0 Review

## STATUS

`READY_FOR_REVIEW` with a fail-closed provider gap. The deterministic cutout-rig implementation is reproducible and locally evidenced, but provider qualification is not granted because the unchanged pose thresholds fail on Q1/Q2 and the visual review still requires human confirmation.

## VERSION

UGAS `0.7.0`; prompt `PROMPT-06-UGAS-DETERMINISTIC-CUTOUT-RIG-POSE-PROVIDER-v0.7.0`.

## PHASE

`DETERMINISTIC_CUTOUT_RIG_POSE_PROVIDER`.

## OBJECTIVE

Bind canonical R4 transparent RGBA pixels to a deterministic front-facing 2D cutout rig: MediaPipe source skeleton, one SAM2.1 Hiera Small segmentation pass, eleven part masks, hierarchy-bound manifest, CPU-friendly Pillow/NumPy transforms, Q0/Q1/Q2 outputs, seam QA, provenance QA and review evidence.

## V0.6.2 AUDIT RESULT

The v0.6.2 public baseline was `58fbb14301f31e4d27368dd5477adb8c90ecadfa`, with 161 unit tests and 550 clean snapshot checks. Its P-only SDXL/OpenPose result remains the immutable historical status `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`, recorded in `docs/evidence/sdxl-openpose-p-qualification.json`; no IP-Adapter, anchors or walk were promoted. The prior pose decision remains `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`, the prior review snapshot is `REVIEW_ARCHIVE_VERIFIED`, and the v0.6.1 visual history remains `docs/evidence/review-visuals-v0.6.1.json`.

## ARCHITECTURE PIVOT

This slice does not tune SDXL/OpenPose, redraw the character, run diffusion, or generate a full walk. The new provider moves source pixels through deterministic part transforms and remains capability-explicit; production routing is unchanged.

## SAM2 OFFICIAL SOURCE / LICENSE / PIN

The isolated segmentation runtime uses the official [facebookresearch/sam2 repository](https://github.com/facebookresearch/sam2), pinned to commit `2b90b9f5ceec907a1c18123530e92e794ad901a4`. The selected model is SAM2.1 Hiera Small, not SAM3; the source/checkpoint license record is Apache-2.0.

## SAM2 RUNTIME / CHECKPOINT

Runtime smoke passed with importable SAM2, `SAM2ImagePredictor`, CUDA on RTX 5050, 46M-parameter Hiera Small, valid 3-mask output, `image_mutated=false`, and peak VRAM `680435200` bytes. The checkpoint is external at `%LOCALAPPDATA%/UGAS/models/sam2/sam2.1_hiera_small.pt`, SHA-256 `6d1aa6f30de5c92224f8172114de081d104bbd23dd9dc5c58996f0cad5dc4d38`; it is not tracked or packaged.

## SOURCE SKELETON

Canonical R4 is asset `asset-2fec6fed1d714d0cb58ad75b56d7ba71`, revision `revision-3a425d184b1a49be9f6d6c8d52d04b96`, SHA-256 `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f579`. MediaPipe supplied 13 measurable joints, all 12 required core joints, core coverage `1.0`, and confidence approximately `0.9946`.

## PART SEGMENTATION

The exact eleven parts are `head`, `torso_pelvis`, `left_upper_arm`, `left_forearm_hand`, `right_upper_arm`, `right_forearm_hand`, `left_thigh`, `left_shin_foot`, `right_thigh`, `right_shin_foot`, and `sword`. Prompts are deterministic geometry-derived positive/negative points and corridors; no manual clicks were used.

## MASK QA

SAM2 ran once for the rig revision. Final semantic coverage is `0.957461`, unassigned fraction `0.042539`, unresolved overlap `0.0`, all parts are nonempty, and final mask purity is `1.0`. The strict alpha count and semantic threshold are both recorded; source alpha remains immutable. Fragment counts are retained for visual review.

## WEAPON MASK

The sword is a separate source-only mask and RGBA part attached at `wrist_right` to inferred `weapon_tip`; the weapon prompt and source hash are recorded in the mask and rig evidence.

## CUTOUT RIG MANIFEST

`docs/evidence/r4-cutout-rig.json` is schema-valid, hash-bound to R4, contains all eleven parts, defines pelvis as root, and records parent/z-order/pivot/source-joint contracts.

## DETERMINISTIC RENDERER

Renderer `cutout-rig-renderer-1.0.0` uses Pillow affine translation/rotation/bounded uniform scale with BICUBIC resampling. No content synthesis, inpainting, recolor, nonuniform scaling, diffusion or ComfyUI job is used.

## PIXEL PROVENANCE

Pixel provenance QA records generated pixel fraction `0.0`, source pixel provenance fraction `1.0`, recolor count `0`, nonuniform scale count `0`, and unchanged face/armor/weapon source hashes. Q0 residual source pixels are explicitly source provenance, not generated content.

## Q0 NEUTRAL RECONSTRUCTION

Q0 passed reconstruction gates: alpha IoU `1.0`, RGB MAE `0.373763`, bounding-box drift `0.0` pixels, no missing/duplicate limb, and source-only provenance.

## Q1 CONTACT-LEFT

Q1 internal rig geometry passed and seam hard gates passed. MediaPipe measured 13 joints, PCK@0.10 `0.846154`, NME `0.072054`, angle MAE `13.821105` degrees, orientation match `true`, but lower-body PCK was `0.666667` and therefore the frozen lower-body gate failed.

## Q2 PASSING-LEFT

Q2 internal rig geometry passed and seam hard gates passed. MediaPipe measured 13 joints, PCK@0.10 `0.692308`, NME `0.100930`, angle MAE `13.789934` degrees, orientation match `true`, and lower-body PCK `0.5`; PCK, NME and lower-body gates failed.

## INTERNAL RIG GEOMETRY QA

Q0, Q1 and Q2 passed deterministic root, pivot, angle, bone-length, bounded-scale and disconnect checks. All recorded member scales are uniform and within the hard range `0.92..1.08`.

## MEDIAPIPE POSE QA

The existing MediaPipe thresholds remain unchanged: at least 10 measurable joints, PCK `>=0.80`, NME `<=0.10`, angle MAE `<=18` degrees, lower-body PCK `>=0.75`, and front orientation. Q1 and Q2 remain measurable but do not qualify.

## SEAM / CONTINUITY QA

Joint gaps are `0.0` for Q0/Q1/Q2, disconnect count is `0`, gross overlap and clipping gates are false, and duplicate body component count is `0`. Small disconnected fragments remain quantified (`25` Q1 and `18` Q2) and are part of the visual-review gap rather than being silently discarded.

## FINAL PROVIDER DECISION

`CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP`. `provider_smoke_status` equals this current gate. The decision follows the PDF order: SAM2 runtime qualified, masks qualified, Q0 reconstruction passed, internal Q0/Q1/Q2 passed, seam hard gates passed, but the visual/estimator gate is not qualified. `CUTOUT_RIG_POSE_PROVIDER_QUALIFIED` is not claimed.

## NO COMFYUI GENERATION

Execution evidence records `comfyui_generation_jobs=0`, SAM2 once per rig, renderer calls for Q0/Q1/Q2, no per-frame segmentation, no SAM3 and no diffusion fallback. The v0.7.0 walk was not run and is not authorized.

## TESTS

The v0.6.2 baseline count of 161 tests is preserved as the regression floor; v0.7.0 adds deterministic cutout-rig contract coverage. The final run must report at least 161 passing tests.

## VALIDATION

Required validation is compileall, unittest discovery, repository validation, SAM2 qualification, canonical R4 build, Q0/Q1/Q2 pose pilot, and clean extracted review-archive validation. A valid provider gap is not converted into a false success.

## REVIEW ARCHIVE SELF-TEST

The review ZIP must contain the active v0.7.0 manifest, all canonical v0.7.0 evidence, immutable v0.6.2 history, no Git metadata, no credentials, no model weights, and a passing extracted self-validation.

## TRACKED SNAPSHOT / GITHUB

The final handoff records the public `main` commit and `origin/main` equality. External SAM2 source, checkpoint and runtime dependencies are intentionally outside Git.

## SECURITY / LICENSES

No credentials or model weights are committed. The official SAM2 source/checkpoint license is recorded as Apache-2.0; downstream asset/commercial review remains separate from provider qualification.

## VISUAL REVIEW STATUS

Human visual review is required for R4 part boundaries, isolated fragments, sword attachment, Q0 fidelity and Q1/Q2 silhouette quality. The contact sheets and overlays are evidence, not automatic artistic approval.

## BLOCKERS / GAPS

Q1 lower-body PCK is below `0.75`; Q2 fails PCK, NME and lower-body PCK. The visual evidence still contains small isolated fragments. These gates keep the provider unqualified and prevent walk authorization.

## DECISIONS

Keep the deterministic provider isolated and unqualified, preserve all historical artifacts, keep thresholds frozen, keep production routing unchanged, and do not execute the next animation prompt from this gap state.

## NEXT STEP

Review and repair the pose/visual gap, then rerun the exact Q0/Q1/Q2 gates. Only a fully qualified provider may authorize a later deterministic eight-frame walk prompt.

## DEFINITION OF DONE

Done for this slice means implementation, schemas, isolated SAM2 qualification, evidence, tests, docs, clean snapshot checks and review ZIP are reproducible. It does not mean external approval or provider qualification while the recorded gates fail.

## REVIEW ZIP

Final ZIP is generated only after the final GitHub commit and validation, with its exact path, SHA-256 and verifier result recorded in the final handoff.
