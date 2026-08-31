# UGAS review v0.7.2 — cutout occlusion and gait qualification

## STATUS

`CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED`. This is a local technical qualification only. External visual approval is still required.

## VERSION

UGAS v0.7.2. Previous release: v0.7.1. Baseline commit: `d42c34f8140c27428e21d21ffabeb4b7ca778577`.

## PHASE

`DETERMINISTIC_CUTOUT_RIG_POSE_PROVIDER`, with `front-walk-cutout-gait-v2` used only to derive four structural key-pose targets. `provider_smoke_status` is synchronized with the current gate.

## OBJECTIVE

Correct the v0.7.1 seam false-positive path by measuring pairwise occlusion, topological joint continuity, retention provenance, and a bounded four-pose front-walk structure using the immutable R4/v0.7.1 rig and masks.

## V0.7.1 EXTERNAL AUDIT RESULT

The historical v0.7.1 result remains immutable: Q0 passed, MediaPipe Q1/Q2 passed, but the final state was `CUTOUT_RIG_SEAM_GAP` because the prior global overlap heuristic reported false-positive seam excess. The v0.7.1 review ZIP and evidence are preserved unchanged. Historical v0.6.2 evidence remains `sdxl-openpose-p-qualification.json`, and the v0.6.1 review manifest remains `review-visuals-v0.6.1.json`; the historical smoke status is `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS` and the prior pose lane is `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`.

## SEAM FALSE-NEGATIVE FINDING

The former heuristic treated every overlap outside a small disk as a seam error. v0.7.2 replaces that measurement with alpha-to-alpha distance in a joint corridor, union connectivity, and composite-hole measurement. The old v0.7.1 result is retained as history, not rewritten.

## OCCLUSION MODEL

The hash-bound plan is `docs/evidence/cutout-occlusion-plan-v072.json`. It defines `JOINT_OVERLAP`, `EXPECTED_OCCLUSION`, `UNEXPECTED_OVERLAP`, and `CRITICAL_COLLISION`. Topology includes head/torso, torso/arms, torso/thighs, upper-arm/forearm, thigh/shin, and right forearm/sword. Render order and QA consume the same plan hash.

## PAIRWISE OVERLAP QA

`docs/evidence/cutout-pairwise-overlap-matrix-v072.json` measures every pair before compositing. Critical collision pixels are gated at zero; unexpected overlap is gated at 0.015 of the foreground union; meaningful forbidden overlap is fail-closed. Expected blade-over-trail-thigh depth occlusion is explicit, while sword/torso and sword/head remain critical collisions.

## TOPOLOGICAL JOINT CONTINUITY

`docs/evidence/cutout-seam-topology-qa-v072.json` records all ten topology edges for K1–K4. Passing requires a connected path, alpha-to-alpha distance no greater than 1.5 px, and a composite alpha-hole area within the calibrated limit. A physical three-pixel gap is a failure fixture.

## RETENTION / OCCLUSION PROVENANCE

`docs/evidence/cutout-retention-occlusion-v072.json` records expected transformed pixels, visible/hidden pixels, the expected occluder, unexpected occluder, clipping, and unexplained loss per part and pose. Required source integrity is at least 0.97, unexplained loss is at most 0.02, clipping is zero, and back-limb visibility may use the documented 0.55 threshold only when explained occlusion and joint continuity pass.

## FRONT-WALK GAIT TARGET V2

`docs/evidence/cutout-front-walk-gait-v2.json` records the deterministic adapter. Hip width ratio is 1.0, contact ankle separation is bounded by 1.35× source separation, passing feet approach the centerline, root bob and pelvis sway are bounded, and jumping-jack motion is disabled. Historical guides supply phase semantics only; their coordinates are not copied.

## Z-ORDER / DEPTH PLAN

K1/K2 use left lead/swing and right trail/support; K3/K4 mirror lower-body roles. The counter-swing arm changes front/back role by half-cycle. Sword remains attached to anatomical `wrist_right` and is rendered in its protected final corridor. Each plan contains all eleven parts and depth roles.

## Q0 REGRESSION

`docs/evidence/cutout-q0-regression-v072-qa.json` reproduces the canonical R4 image from v0.7.1 parts: alpha IoU `1.0`, RGB MAE `1.147443`, and bounding-box drift `0`. No source residual fallback, patch copy, SAM2 rerun, or generated pixel is used.

## K1 CONTACT-LEFT

`docs/evidence/cutout-k1-contact-left-v072.png` and the qualification JSON record target/detected skeletons, affine transforms, pairwise classes, topology seams, retention, margins, and weapon corridor.

## K2 PASSING-LEFT

`docs/evidence/cutout-k2-passing-left-v072.png` records the left passing foot approaching the centerline with the right support leg behind it.

## K3 CONTACT-RIGHT

`docs/evidence/cutout-k3-contact-right-v072.png` records the mirrored contact phase and mirrored z-order/depth roles.

## K4 PASSING-RIGHT

`docs/evidence/cutout-k4-passing-right-v072.png` records the mirrored passing phase with the right foot approaching the centerline.

## MEDIAPIPE POSE QA

MediaPipe is used only as the existing QA estimator with the v0.5.4–v0.6.x thresholds unchanged. K1–K4 have target/detected overlays and measurable core-joint records. It is not a generation provider.

## HALF-CYCLE STRUCTURE

`docs/evidence/cutout-half-cycle-structure-v072.json` checks K1↔K3 and K2↔K4 reflection within a normalized 40 px structural tolerance, arm-swing inversion, stable head/torso height, and sword/punho-right attachment. This is structural prequalification, not temporal animation approval.

## FINAL PROVIDER DECISION

`CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED`. The current state is fail-closed for production: `walk_authorized=false`, `generation_provider_change_authorized=false`, and external visual review is required.

## NO SAM2 RERUN / NO COMFYUI / NO WALK

SAM2 runs: `0`; ComfyUI generation jobs: `0`; eight-frame walk: `NOT_RUN`; spritesheet: `NOT_RUN`; GIF: `NOT_RUN`. The v0.7.1 SAM2 masks/checkpoint remain external historical inputs and are not copied to GitHub or the review ZIP.

## TESTS

All historical v0.7.1 tests remain present. New tests cover plan/hash binding, allowed/expected/unexpected/critical overlap, 1 px versus 3 px seam fixtures, connectivity, expected hidden pixels versus unexplained loss, clipping, back-limb retention, gait constraints, half-cycle structure, sword attachment, archive security, and no-Git validation.

## VALIDATION

Required commands are `python -m compileall -q src scripts tests`, `python -m unittest discover -s tests`, `python scripts/validation/run_validation.py`, the v0.7.2 qualifier with `--json`, and the review archive verifier. Results are recorded in the machine evidence and the final review ZIP.

## REVIEW ARCHIVE SELF-TEST

The final ZIP must pass CRC/traversal/hash checks and self-validate after clean extraction. The local historical status is `REVIEW_ARCHIVE_VERIFIED` when that self-test passes. The ZIP is generated only after source validation and Git publication; no filesystem modification is made after successful final packaging.

## TRACKED SNAPSHOT / GITHUB

The published tracked snapshot is `main` at the v0.7.2 commit. `origin/main` must equal `HEAD` before packaging. Local ignored runtime models, temporary renders, and historical ZIPs are excluded from the tracked source and final package.

## SECURITY / LICENSES

No credentials, tokens, model checkpoints, `.venv`, or runtime caches are included. The repository remains MIT licensed. MediaPipe and historical SAM2 provenance are documented without bundling their external model files.

## VISUAL REVIEW STATUS

Technical evidence is complete and hash-bound. Human visual review is `REQUIRED`; production approval is `not-granted`; external approval is `not-claimed`.

## BLOCKERS / GAPS

The v0.7.2 technical gate is green. The remaining gate is external visual review. Eight-frame temporal walk execution remains intentionally blocked until that review step is completed.

## DECISIONS

Keep v0.7.1 historical evidence immutable. Reuse its R4 revision, refined masks, and deterministic parts. Add no diffusion provider, ComfyUI job, segmentation rerun, or temporal walk in this slice. Keep the renderer and QA bound to one occlusion-plan hash.

## NEXT STEP

The only allowed next action is `external_review_then_run_8_frame_walk_prompt` after the external visual review decision is recorded.

## DEFINITION OF DONE

Done for this slice means historical regression coverage is preserved, Q0 passes, K1–K4 pass internal affine/MediaPipe/seam/pairwise/retention/margin/weapon gates, gait and half-cycle structure pass, SAM2/ComfyUI/walk remain zero/not-run, the main branch is published cleanly, and the review ZIP self-test passes. It does not mean external visual approval.

## REVIEW ZIP

Final artifact: `review/UGAS-REVIEW-v0.7.2-final-<timestamp>.zip`, with its SHA-256 recorded in the handoff. The historical `review/UGAS-REVIEW-v0.7.1-final-20260830-215552.zip` remains a separate immutable audit artifact.
