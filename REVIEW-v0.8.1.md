# UGAS v0.8.1 review

## STATUS

`CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED`; technical local qualification passed. `production_routing=BLOCKED`, `production_approved=false`, and external approval remains `not-claimed`.

## VERSION

`0.8.1` — correction of the deterministic front-walk QA integrity lane.

## PHASE

`DETERMINISTIC_FRONT_WALK_8FRAME_PILOT`; only the same `walk-front` / `front` / 8-frame cycle was executed.

## OBJECTIVE

Correct the v0.8.0 false-green QA paths without regenerating the animation: measure visible boot soles and projected ground, use actual alpha-layer extents, smooth skeleton targets before render, enforce strict temporal limits, bind loop z-order to the frozen plan, and publish hash-bound evidence.

## V0.8.0 EXTERNAL AUDIT FINDINGS

The historical v0.8.0 evidence remains immutable. Its audit findings were ankle-center foot QA instead of visible soles, a generic 30-degree temporal exception, skeleton-distance proxies for head/torso stability, hardcoded loop z-order, ignored swing bias, and a zero-valued root step field. v0.8.1 corrects these paths and keeps v0.8.0 snapshots separate.

## BASELINE IMMUTABILITY

Baseline commit: `d634d69d3cceac239d8eb5fe8623c764eb6c6b53`. R4 anchor: asset `asset-2fec6fed1d714d0cb58ad75b56d7ba71`, revision `revision-3a425d184b1a49be9f6d6c8d52d04b96`, SHA-256 `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`. v0.8.0 state/provider/config/schema are preserved in versioned snapshots. Historical boundaries remain `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`, `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`, and `REVIEW_ARCHIVE_VERIFIED`.

## FOOT / PROJECTED GROUND MODEL

The model derives each source sole anchor from the last active alpha row of the source shin/foot part, projects it through the per-part affine, and records canonical and presented coordinates. F2 uses a frozen support calibration of 3 source pixels plus its explicit swing depth proxy; this does not edit the immutable key target.

## VISIBLE SOLE QA

Actual sole is the bottom of the transformed shin/foot alpha layer. The final gate is `visible_clearance_px >= 4.0` for swing feet, `ground_penetration_px <= 1.5`, and planted expected-sole error within 1.5 px. F2 clearance is `11.074226` px; all swing and planted gates pass.

## ACTUAL ALPHA SAFE MARGIN

Every final RGBA frame is measured from its actual alpha bbox; minimum margin is 39 px, above the 24 px gate. No skeleton bbox is used as a substitute.

## PRESENTATION TRANSFORM

One global uniform transform is frozen before rendering: scale `0.90`, canvas anchor `(256,256)`, translation `(0,0)`, predicted from all eight v0.8.0 baseline extents. Frame-specific transforms are forbidden.

## SKELETON TEMPORAL SMOOTHING

Intermediate targets use deterministic cubic-Hermite interpolation followed by bounded coordinate descent over knee/elbow x/y only. The objective and bounds are frozen before render; smoothing consumes no image inputs and leaves F0/F2/F4/F6 key targets exact.

## ANGULAR ACCELERATION QA

The strict maximum is 25 degrees/frame² with no generic 30-degree fallback. Pre-smoothing maximum was `29.931715`; post-smoothing maximum is `22.793701`. The 30-degree fixture is explicitly disallowed.

## HEAD / TORSO LAYER BBOX QA

Head and torso stability uses actual alpha-layer areas. Head CV is `0.006035` and torso/pelvis CV is `0.004570`, both below the `0.04` gate.

## LOOP Z-ORDER QA

The F3→F4 and F7→F0 z-order/depth-role boundaries are frozen in `front-walk-z-order-v081.json` and checked against the actual plan. Sword remains last; loop QA passes.

## HARD-GATE PROOF SOURCES

Proof records identify source RGBA hashes, source-only affine operations, zero generated pixels, zero recolor operations, and the 8-connected alpha-component duplicate-body method. No AI output is used.

## PER-FRAME QA

All eight frame reports are `CUTOUT_RIG_FRONT_WALK_FRAME_PASSED`, including target binding, transform bounds, alpha margin, structure, layer integrity, occlusion/retention, MediaPipe measurability, foot/sole, weapon corridor, provenance, and duplicate-body gates.

## TEMPORAL / HALF-CYCLE / LOOP

Temporal, root-motion, half-cycle, and loop reports all pass. Root motion is bounded at 2.828462 px maximum step and 4 px vertical amplitude.

## VISUAL EVIDENCE

The review manifest `docs/evidence/review-visuals-v0.8.1.json` lists 96 distinct hash-bound evidence items, including RGBA frames, checkerboards, target overlays, ground-line overlays, alpha-bbox overlays, structural maps, pairwise/retention records, and zoom/contact sheets.

## SPRITESHEET / METADATA / GIF

The qualified package contains an RGBA 2048×1024 4×2 sheet, 8-frame metadata at 10 FPS / 100 ms, and a looping GIF preview. Packaging runs only after all hard gates pass.

## FINAL WALK DECISION

Technical local decision: `CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED`. Operational decision: pilot-only; `production_routing=BLOCKED`; production approval is false; external visual review is required and not claimed.

## NO SAM2 / NO COMFYUI

`sam2_runs=0`, `comfyui_generation_jobs=0`, `new_generation_jobs=0`. No SAM2 rerun, ComfyUI generation, diffusion, ControlNet, IP-Adapter, or new animation/direction was used.

## TESTS

The v0.8.1 regression suite covers strict temporal thresholds, actual alpha CV, visible-sole negative fixtures, key immutability, deterministic smoothing, frozen z-order, provenance, package bounds, and review-manifest hashes. Final command/result is recorded in the review index.

## VALIDATION

Run `python scripts/validation/run_validation.py` after the active v0.8.1 state, schemas, evidence, review manifest, and review index are committed. The validator must pass the immutable historical snapshots and the active correction gates.

## GITHUB-FIRST REVIEW INDEX

`docs/evidence/review-index-v0.8.1.json` is the machine-readable index for GitHub-first review. It binds the review, current state, test/validation results, evidence hashes, required visual sets, forbidden artifacts, external-review boundary, and production routing.

## TRACKED SNAPSHOT / GITHUB

All required source, machine-readable evidence, visuals, schemas, and documentation are tracked in the repository. GitHub publication means the pushed commit is available for review; it does not imply external visual approval or production enablement.

## SECURITY / LICENSES

No credentials, model weights, checkpoints, or private runtime paths are included. The repository remains MIT-licensed; external SAM2/MediaPipe runtime inputs remain outside the repository boundary.

## VISUAL REVIEW STATUS

Local visual evidence is present and hash-bound. External visual review is `REQUIRED`; external approval is `not-claimed`.

## BLOCKERS / GAPS

Production routing remains blocked. External human review of the 8-frame cycle is still pending. No claim is made about CI success, deployment, or production readiness until independently verified.

## DECISIONS

Preserve v0.8.0 as historical evidence; qualify only this corrected cycle; keep no-AI/no-new-generation boundaries; retain one global presentation transform; fail closed on any future frame, temporal, foot, loop, schema, or evidence-hash gap.

## NEXT STEP

The only authorized next action is `external_review_front_walk_cycle`.

## DEFINITION OF DONE

Done for v0.8.1 technical scope means the same 8-frame front walk passes all gates, evidence is hash-bound, package metadata is valid, no forbidden artifacts are present, and production remains blocked pending external visual review.
