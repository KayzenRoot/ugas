# UGAS review v0.10.0

## STATUS

`TECHNICALLY_QUALIFIED_LOCALLY`; attack-front external visual review remains `REQUIRED`. Production remains `BLOCKED`.

## VERSION

UGAS v0.10.0, generic action runtime with deterministic front sword attack pilot.

## PHASE

`REUSABLE_DETERMINISTIC_ANIMATION_RUNTIME`.

## OBJECTIVE

Add a generic event-marker and lifecycle contract, then qualify only `attack-front-v1` from the immutable public v0.9.1 baseline. Preserve the R4 rig, masks, structural core, walk replay, idle record, and no-generation boundary.

## BASELINE AND IMMUTABILITY

The implementation starts from public `main` SHA `d914d09d35ebfc5658d6c08e3502288c537fbf20`, the v0.9.1 final SHA. The canonical R4 anchor remains revision `revision-3a425d184b1a49be9f6d6c8d52d04b96` with SHA-256 `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`. No R4 rig, mask, structural-core, walk, or idle pixels were regenerated or edited.

## HISTORICAL EXTERNAL DECISIONS

`walk_front_v081_external_visual=APPROVED_PILOT` and `idle_front_v1_external_visual=APPROVED_PILOT` are recorded as historical pilot decisions required by this slice. They are not inferred from the new local attack result. The attack decision is separate and remains `REQUIRED` for external visual review.

The prior records `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`, `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`, and `REVIEW_ARCHIVE_VERIFIED` remain historical governance facts and are not reinterpreted as current provider or production approval.

## GENERIC EVENT-MARKER CONTRACT

Animation specifications may omit `event_markers[]`. When present, every marker has `event_id`, `frame`, `kind`, and optional object `payload`; event IDs are unique, frames are within `0..frame_count-1`, and the source order is canonical by `(frame,event_id)`. The marker list and SHA-256 are preserved in compiled manifest, QA result, metadata, and package manifest. Duplicate IDs, out-of-range frames, and non-canonical order fail closed.

## NON-LOOP LIFECYCLE

The generic helper evaluates the last-to-first transition for `loop=true`. For `loop=false`, the closing transition is omitted and the final frame must be valid; markers must remain inside the timeline. Dummy loop and non-loop fixtures, including an invalid final-frame fixture, are recorded in `docs/evidence/animation-runtime-v0100/non-loop-runtime-contract-v0100.json`.

## ATTACK-FRONT-V1 SCOPE

Only `attack-front-v1` is new: front-facing, 10 frames, 12 fps, non-looping, sword, phases A0-ready through A9-ready-end. The frozen combat timeline is windup peak frame 2, active window frames 3–6, hit frame 5, active end frame 6, and recovery complete frame 9. No run, hit, death, alternate direction, new character, new provider, or production route is included.

## SOURCE-ONLY TARGET DERIVATION

Targets are deterministic skeleton derivations from the R4 source skeleton with frozen right forearm/sword angle arrays. The presented renderer applies one frozen uniform transform and source cutout pixels only. All ten target hashes are distinct; no duplicate padding, AI generation, inpainting, manual pixel edit, or per-frame transform tuning was used.

## TEMPORAL POSE QA

All ten frames pass source-part hashes, target binding, uniform bone-scale bounds, zero nonuniform operations, alpha margin ≥24 px, structural holes, layer integrity, occlusion, seams, retention, source-only pixels, frozen z-order, and independent MediaPipe QA. Temporal gates pass joint angle delta ≤30°/frame, angular acceleration ≤28°/frame², root x/y excursion ≤8 px, adjacent head center delta ≤6 px, and ten distinct target hashes.

## WEAPON SWEEP AND HIT TIMELINE

The sword pivot is attached to the right wrist in every frame. The measured tip path is nonzero; the peak tip motion is in or adjacent to the active window. Active frames are exactly 3, 4, 5, 6; hit is exactly frame 5; sword/head critical collisions and sword/torso forbidden penetration are zero. Tip x/y, angular velocity, transition data, peak motion, and collision counts are recorded in `attack-weapon-sweep-qa-v0100.json`.

## FOOT-GROUND QA

Both feet are planted against source sole anchors. Sequential A0→A1 through A8→A9 measurements pass sole error, ground penetration, projected sole drift ≤1.5 px, and ankle horizontal drift from A0 ≤2 px. No A9→A0 closing pair is evaluated because this attack is non-looping. A positive slide fixture is covered by the test contract.

## STRUCTURAL AND OCCLUSION QA

Structural coverage, layer retention, seams, constant z-order, and measured pairwise occlusion pass for all ten frames. Sword/head and sword/torso remain critical/forbidden pairs. Grip and trail-thigh corridors are explicit allowed pairs only; no unconditional hard-gate override is used.

## INDEPENDENT MEDIAPIPE QA

MediaPipe Pose Landmarker is an independent QA estimator, not a generator. Each frame records a target/detected overlay and measured joints. The strict gate requires at least 10 measurable joints, PCK@0.10 ≥0.80, NME ≤0.10, limb-angle MAE ≤18°, and front orientation; all ten frames pass. The local model bundle remains outside Git.

## PACKAGE AND REVIEW EVIDENCE

The qualified package is `docs/evidence/animation-runtime-v0100/attack-front-v1/`: 5×2 cells, each 512×512, total 2560×1024, RGBA, and GIF review-only. Event markers, active window, and hit frame are present in the package metadata. Ten target/detected overlays, attack temporal/weapon/foot/event evidence, execution evidence, and the v0.10.0 review index are hash-bound. Historical walk/idle visuals are referenced through their existing v0.9.0 review manifest without duplicating PNGs.

## NO NEW GENERATION

This slice performs no new generation: `sam2_runs=0`, `comfyui_generation_jobs=0`, `diffusion_runs=0`, and `new_generation=0`. `production_approved=false` and `production_routing=BLOCKED` remain explicit.

## TESTS

The complete suite is `python -m unittest discover -s tests -q`. The v0.10.0 additions cover marker omission/validation/order/hash preservation, loop versus non-loop lifecycle, invalid final-frame handling, and frozen attack specification semantics.

## VALIDATION

The required gate sequence is compileall, complete unittest suite, `python scripts/validation/run_animation_runtime_v091.py`, `python scripts/validation/run_animation_runtime_v0100.py`, `python scripts/validation/validate_review_index_v0100.py`, and the full historical-plus-active `python scripts/validation/run_validation.py`. The review index records final local counts and requires the external reviewer to resolve final HEAD.

## TRACKED SNAPSHOT / GITHUB

The target is `main` in `https://github.com/csn1985-ship-it/ugas.git`. Source, schemas, tests, evidence, review, and validators are tracked; weights and review ZIPs are excluded. The index records build provenance and `executor_cannot_self_assert_final_head=true`; local evidence does not infer remote CI success or external approval.

## EXTERNAL VISUAL REVIEW STATUS

Historical walk and idle pilot statuses are `APPROVED_PILOT`. Attack front is `REQUIRED` and `not-claimed`. Local technical qualification is not external attack approval.

## BLOCKERS / GAPS

The remaining blocker is external visual review of `attack-front-v1`. Production routing is `BLOCKED`. Run/hit/death expansion, other directions, provider changes, rig/mask changes, and production promotion remain outside this slice.

## DECISIONS

Use the generic decision-based package gate with all hard gates literally true and `failures=[]`; preserve optional markers by hash; enforce non-loop final-frame semantics; derive attack targets from the R4 skeleton; measure weapon, feet, structural, occlusion, and independent pose QA; and preserve historical visuals by reference.

## NEXT STEP

The only allowed next action is `external_review_attack_front`.

## DEFINITION OF DONE

Done locally when all v0.10.0 tests, runtime evidence, schema checks, state consistency, full validation, and review-index hash checks pass, with the implementation published on `main`. The phase is complete for external handoff, not production: attack external visual review is `REQUIRED`, `production_approved=false`, `production_routing=BLOCKED`, and final HEAD must be resolved by the external reviewer.
