# UGAS v0.11.0 review

## STATUS

`CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED` with `decision=QUALIFIED`. This is a local technical qualification and pilot artifact; it is not an external visual approval.

## VERSION

Active release: `0.11.0`. Previous release: `0.10.0`.

## PHASE

`REUSABLE_DETERMINISTIC_ANIMATION_RUNTIME`.

## OBJECTIVE

Add a reusable, deterministic motion-quality layer between Animation Spec and adapter, then qualify only the source-only frontal sword pilot `attack-front-v2`.

## BASELINE AND IMMUTABILITY

The implementation starts at baseline `c11196e5e854a0fbc6ec62e959de5ecc28d492ce`. The canonical R4 source remains byte- and hash-bound. Historical v0.10.0 attack-front-v1, v0.8.1 walk, and v0.9.0 idle fixtures are replayed and preserved; no historical artifact is reclassified as a new output.

## HISTORICAL EXTERNAL DECISIONS

The recorded historical decisions are `APPROVED_PILOT` for walk-front-v0.8.1, idle-front-v1, and attack-front-v1. The historical provider gaps remain `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS` and `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`. These are historical records, not new approvals.

## GENERIC MOTION-CURVE CONTRACT

`motion_tracks[]` is optional. Each track has an opaque `track_id`, `scalar` or `vec2` values, strictly ascending in-timeline keyframes, finite numbers, and `linear`, `smoothstep`, or `cubic_hermite` interpolation. Exact keyframes are returned exactly; deterministic Hermite tangents are one-sided at endpoints and centered at interior keys. Out-of-range samples fail closed unless the explicit `clamp` policy is declared. Curves do not round values; rounding occurs only at the target-skeleton boundary. Contract evidence: `docs/evidence/animation-runtime-v0110/generic-motion-curve-contract-v0110.json`.

## MOTION-TRACK BINDING

The core validates, samples, normalizes, and hashes tracks. The adapter interprets channel semantics. `motion_tracks_sha256` is propagated through compiled manifest, QA, metadata, package, execution evidence, and the review index. Unknown channels remain opaque to the core.

## ATTACK-FRONT-V2 SCOPE

Only `attack-front-v2` is newly executed: front, sword, 12 frames, 12 fps, non-loop, 6x2 RGBA package at 512x512 cells. Frozen markers are `windup_peak=3`, `active_start=4`, `hit_event=6`, `active_end=7`, and `recovery_complete=11`. No run, hit, death, other direction, provider, rig, mask, or production lane is in scope.

## SOURCE-ONLY TARGET DERIVATION

All targets derive from the approved R4 source skeleton and source pixels through deterministic adapter transforms. No diffusion, ComfyUI generation, SAM2 rerun, inpainting, or manual pixel editing was used. `source_only_pixels=true` and the source hash is bound in the artifacts.

## TEMPORAL QUALITY QA

The v2 temporal QA passes strict bounds for root excursion, head adjacency, torso range, joint delta, acceleration, jerk, and non-loop lifecycle. Evidence is `docs/evidence/animation-runtime-v0110/attack-front-v2/attack-v2-temporal-qa.json`.

## WEAPON ARC AND HIT TIMELINE

The sword remains attached to the right-hand pivot. The active window is frames 4–7, the hit is frame 6, the weapon path has a measured active peak, pre-hit acceleration, collision-free sweep, and post-hit follow-through. Evidence is `attack-v2-weapon-arc-qa.json` and `attack-v2-event-marker-qa.json` in the v0.11.0 evidence directory.

## FOOT-GROUND AND BALANCE QA

Both feet remain grounded with bounded sole error, no penetration, bounded sequential drift, stable ankle displacement, and a valid balance corridor. Evidence is `attack-v2-foot-ground-qa.json`.

## STRUCTURAL OCCLUSION AND POSE QA

Structural coverage, belt/pelvis/torso corridors, pairwise occlusion, seam continuity, retention, alpha margin, duplicate/clipping checks, source provenance, and independent MediaPipe pose metrics pass for all 12 frames. Target/detected overlays are hash-bound in `attack-v2-visual-manifest.json`.

## HISTORICAL REPLAY

The historical replay is byte-identical for v0.10.0 attack-front-v1 frames, spritesheet, GIF and event markers, and for the canonical v0.8.1 walk and v0.9.0 idle fixtures. Evidence: `docs/evidence/animation-runtime-v0110/historical-replay-v0110.json`.

## PACKAGE AND REVIEW EVIDENCE

The package manifest is `docs/evidence/animation-runtime-v0110/attack-front-v2/package-manifest.json`; the execution record is `docs/evidence/animation-runtime-v0110/execution-evidence-v0.11.0.json`; the review index is `docs/evidence/review-index-v0.11.0.json`. `REVIEW_INDEX_VERIFIED` is a local integrity result, not external approval.

## NO NEW GENERATION

`sam2_runs=0`, `comfyui_generation_jobs=0`, `diffusion_runs=0`, `new_generation=0`. No forbidden generation operation was used.

## TESTS

Run with `$env:PYTHONPATH='src'; python -m unittest discover -s tests -q`. The v0.11.0 motion-curve tests cover positive and negative contract cases, exact/no-rounding behavior, deterministic sampling, hash mutation, legacy no-track compatibility, and attack-v2 mechanics. The final count is recorded in the review index.

## VALIDATION

Run `python scripts/validation/validate_state_consistency.py`, `python scripts/validation/run_animation_runtime_v0110.py`, `python scripts/validation/run_validation.py`, and `python scripts/validation/validate_review_index_v0110.py`. All required hard gates must pass with zero failures before this local qualification is reported.

## TRACKED SNAPSHOT / GITHUB

Repository: `https://github.com/csn1985-ship-it/ugas.git`. The v0.11.0 review index is GitHub-first, hash-bound, and records the build head separately from the final publication head. The final HEAD must be resolved from the pushed repository by an external reviewer; the executor cannot self-assert it.

## EXTERNAL VISUAL REVIEW STATUS

`attack_front_v2_external_visual=REQUIRED`. No external visual approval is claimed. The only allowed next action is `external_review_attack_front_v2`.

## BLOCKERS / GAPS

Production routing is intentionally `production_routing=BLOCKED`. The remaining gap is external visual review of attack-front-v2 and independent resolution of the final GitHub HEAD. The historical SDXL/OpenPose provider gap is not reopened by this source-only slice.

## DECISIONS

`decision=QUALIFIED` for the local technical pilot only. The active state is `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED`; it does not authorize production.

## NEXT STEP

`external_review_attack_front_v2`.

## DEFINITION OF DONE

Done for this slice means: generic motion-track contract implemented and tested; v2 artifacts schema-valid and hash-bound; all v2 hard gates pass; historical replay remains byte-identical; no new generation occurred; review evidence is tracked and index-verified; external visual review remains explicitly required; `production_routing=BLOCKED`.
