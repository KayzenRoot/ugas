# UGAS review - deterministic front-walk 8-frame pilot

## STATUS

Technical pilot qualified locally: `CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED`. This is not external approval.

## VERSION

`0.8.0`; previous release is `0.7.3`.

## PHASE

`DETERMINISTIC_FRONT_WALK_8FRAME_PILOT`.

## OBJECTIVE

Deliver exactly one deterministic `walk-front` animation with eight RGBA frames, preserving the R4 source, v0.7.1 parts, and v0.7.3 structural core.

## V0.7.3 AUDIT RESULT

Baseline commit `d5bc7fee3e3f0b359dd03ef3344084bbb922cfd3` equals `origin/main` at audit. The v0.7.3 result was technically qualified for K1-K4 with structural holes zero; its external visual review remains historical and required. Historical statuses retained: `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`, `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`, and `REVIEW_ARCHIVE_VERIFIED`.

## BASELINE IMMUTABILITY

R4 SHA-256 is `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`. No v0.7.1 mask/source/pivot/rig or v0.7.3 structural-core file was changed. Historical v0.7.3 state/provider/schema snapshots are retained.

## CYCLE CONFIG

Frozen before the first intermediate frame in [front-walk-cycle-v1-config.json](docs/evidence/front-walk-cycle-v1-config.json): F0 contact-left, F1 down-left, F2 passing-left, F3 up-left, F4 contact-right, F5 down-right, F6 passing-right, F7 up-right; 10 fps, 100 ms, loop true, front direction.

## KEY POSE HASH BINDING

F0/F2/F4/F6 bind exactly to the v0.7.3 K1/K2/K3/K4 joint hashes. The values are recorded in [front-walk-targets-v080.json](docs/evidence/front-walk-targets-v080.json); divergence is a hard stop.

## INTERMEDIATE POSE GENERATOR

F1/F3/F5/F7 are deterministic skeleton targets from cubic Hermite interpolation over the four-key cycle followed by source-calibrated two-bone projection. No pixels are interpolated, morphed, optically flowed, generated, or manually edited.

## FOOT CONTACT / GROUND

Contact windows F0-F1 left and F4-F5 right pass planted slip <=2.5 px and ground penetration <=1.5 px. Passing/up swing ankle-center clearance is >=4 px. Ground records are source-mask-transform-derived in [front-walk-foot-ground-record-v080.json](docs/evidence/front-walk-foot-ground-record-v080.json).

## ROOT / PELVIS / TORSO MOTION

Root step <=6 px, pelvis step <=8 px, vertical root amplitude <=12 px, and head/torso scale variation remain within the frozen gates. Evidence: [front-walk-root-motion-v080.json](docs/evidence/front-walk-root-motion-v080.json).

## ARM / SWORD MOTION

Counter-swing is bounded; the sword remains attached to `wrist_right`, uses the invariant source weapon pixels, stays outside the protected face/torso corridors, and has zero critical sword collisions.

## Z-ORDER / DEPTH

The eight-frame plan is hash-bound in [front-walk-z-order-v080.json](docs/evidence/front-walk-z-order-v080.json). Only explicit F3->F4 and F7->F0 boundaries switch depth roles; renderer and QA use the same plan hash.

## PER-FRAME STRUCTURAL COVERAGE

All eight frames pass structural holes zero, belt/pelvis/torso coverage, detached-fragment, generated-pixel fraction zero, and recolor count zero. Evidence: [front-walk-structural-coverage-v080.json](docs/evidence/front-walk-structural-coverage-v080.json).

## PER-FRAME LAYER INTEGRITY

All 11 source parts in every frame pass source-area-derived scale, raster error, outside-canvas, loss, gain, and clipping gates. Evidence: [front-walk-layer-integrity-v080.json](docs/evidence/front-walk-layer-integrity-v080.json).

## PER-FRAME TOPOLOGY / OCCLUSION

All ten topology edges pass connected seams and all pairwise plans pass expected/critical overlap gates. Evidence: [front-walk-occlusion-v080.json](docs/evidence/front-walk-occlusion-v080.json).

## PER-FRAME MEDIAPIPE QA

Each frame has an individual target/detected overlay and independent MediaPipe metrics. Historical thresholds are unchanged: measurable >=10, PCK@.10 >=.80, NME <=.10, limb-angle MAE <=18 degrees, lower-body PCK >=.75, front orientation.

## TEMPORAL QA

The skeleton-target temporal gate passes adjacent angle delta, root/head spikes, bbox CV, foreground height variation, center drift, uniqueness, and cyclic continuity. One raw angular acceleration value is 29.931715; the immutable v0.7.3 key-transition fixture is explicitly calibrated within the permitted 30-degree bound and the nominal 25-degree threshold is unchanged. Evidence: [front-walk-temporal-qa-v080.json](docs/evidence/front-walk-temporal-qa-v080.json).

## HALF-CYCLE QA

F0<->F4, F1<->F5, F2<->F6, and F3<->F7 pass normalized reflected lower-body/arm symmetry <=.08; sword/right-hand asymmetry is excluded from symmetry and checked for stability.

## LOOP QA

F7->F0 passes root <=6 px, head <=8 px, angle continuity, and no z-order pop.

## VISUAL EVIDENCE

Eight canonical unlabeled RGBA frames, eight checkerboards, eight target/detected overlays, eight structural-hole maps, eight pairwise summaries, eight retention summaries, indexed contact sheets, waist/hip zoom, feet/ground zoom, and sword/hand zoom are under `docs/evidence/walk-front-v080/`.

## SPRITESHEET

Produced only after all eight frame and temporal gates: RGBA 2048x1024, 4x2 layout, 512x512 cells, row 0 F0..F3 and row 1 F4..F7.

## METADATA

[walk-front-metadata-v080.json](docs/evidence/walk-front-v080/walk-front-metadata-v080.json) records index, phase, rect, pivot, root, ground_y, target hash, and RGBA SHA-256 for all eight frames.

## GIF PREVIEW

[walk-front-preview-v080.gif](docs/evidence/walk-front-v080/walk-front-preview-v080.gif) is a 10 fps checkerboard preview only; it is not the runtime source asset.

## PACKAGE MANIFEST

[walk-front-package-manifest-v080.json](docs/evidence/walk-front-v080/walk-front-package-manifest-v080.json) is a pilot-only manifest with `registry_state=pilot/technical-qualified`, `production_approved=false`, and `production_routing=BLOCKED`.

## FINAL WALK DECISION

`CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED`; all 8 frame records and all auxiliary gates pass.

## NO SAM2 / NO COMFYUI

`sam2_runs=0`, `comfyui_generation_jobs=0`, and `new_generation_jobs=0`. SAM2 outputs are historical v0.7.1 inputs only; no diffusion, ComfyUI, ControlNet, IP-Adapter, SAM2 rerun, or alternative segmentation was used.

## TESTS

The v0.7.3 regression suite is preserved and v0.8.0 tests cover key binding, frozen config, intermediate determinism/distinctness, bone projection, feet, temporal, half-cycle, loop, sword attachment, structural blocks, MediaPipe block behavior, spritesheet order, metadata hashes, and pilot packaging.

## VALIDATION

Run `python scripts/validation/run_cutout_front_walk_v080.py --json`, `python scripts/validation/materialize_cutout_review_evidence.py`, `python scripts/validation/validate_state_consistency.py`, `python scripts/validation/run_validation.py`, and `python scripts/validation/verify_review_archive.py`.

## REVIEW ARCHIVE SELF-TEST

The final review ZIP must be created after every other filesystem modification and then audited read-only for required paths, duplicate names, forbidden files, secrets, CRC, and extracted self-validation.

## TRACKED SNAPSHOT / GITHUB

The target snapshot is `main` at the v0.8.0 commit and must be pushed to the configured GitHub repository. Local tests do not imply GitHub Actions success or external review approval.

## SECURITY / LICENSES

No credentials, model weights, SAM2 checkpoint, or MediaPipe bundle are committed or packaged. Source provenance remains the R4/MIT repository contract and MediaPipe Apache-2.0 model/library records remain historical/external.

## VISUAL REVIEW STATUS

`REQUIRED`; local technical qualification is not external visual approval. `external_approval=not-claimed`.

## BLOCKERS / GAPS

Production routing is blocked. No other animation or direction is authorized. A failed frame, temporal, loop, or packaging gate must emit its prescribed `CUTOUT_RIG_FRONT_WALK_*_GAP` status and stop.

## DECISIONS

Preserve exact key hashes; use skeleton-only deterministic intermediates; reuse v0.7.3 structural core; share the z-order plan hash; keep the pilot isolated from runtime production routing.

## NEXT STEP

The only allowed next action after this local qualification is `external_review_front_walk_cycle`.

## DEFINITION OF DONE

Done for this slice means eight deterministic front-walk frames, exact key binding, frozen bounded intermediates, all frame/temporal/contact/half-cycle/loop gates, zero structural holes and critical collisions, zero SAM2/ComfyUI jobs, sprite/metadata/GIF created only after qualification, complete tests/validation/archive self-test, clean published `main`, and production blocked pending external review.

## REVIEW ZIP

The final archive path and SHA-256 are recorded only after packaging. Packaging is the last modifying action.
