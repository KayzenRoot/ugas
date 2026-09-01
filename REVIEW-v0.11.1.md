# UGAS v0.11.1 review

## STATUS

`CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED` with `decision=QUALIFIED`. This is a local technical qualification of the corrective pilot; it is not external visual approval.

## VERSION

Active release: `0.11.1`. Previous release: `0.11.0`.

## PHASE

`REUSABLE_DETERMINISTIC_ANIMATION_RUNTIME`.

## OBJECTIVE

Correct the v0.11.0 false-green weapon follow-through/recovery finding for the same 12-frame, front-facing `attack-front-v2`, while preserving the generic motion-quality layer, R4 rig, masks, body mechanics, foot balance, historical lanes, and production boundaries.

## HISTORICAL EXTERNAL DECISIONS

The historical provider records remain `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS` and `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`; `REVIEW_INDEX_VERIFIED` is a local integrity state, not an approval.

## V0.11.0 EXTERNAL AUDIT FINDING

The v0.11.0 audit identified insufficient weapon continuity after `hit_event=6`: the measured post-hit path was approximately `6.515050 px`, the follow ratio was approximately `0.06488`, and the recovery endpoint did not return closely enough to V0. This was recorded as a false-green baseline and is not overwritten.

## BASELINE IMMUTABILITY

The implementation base is the public v0.11.0 commit `9401c31f994e968149292b2993d960d3aafc37c4`; its parent v0.10.0 commit is `c11196e5e854a0fbc6ec62e959de5ecc28d492ce`. The v0.11.0 profile, state, review, and evidence remain available as immutable historical records, including `docs/evidence/current-state-v0.11.0.json` and `docs/evidence/state-consistency-v0110.json`. The canonical R4 source remains hash-bound to `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`.

## GENERIC MOTION CURVE REGRESSION

The generic `motion_tracks[]` contract is unchanged. Linear, smoothstep, cubic-Hermite, explicit clamp, finite-value, ascending-keyframe, duplicate-ID, out-of-range, and mutation-hash controls pass in `docs/evidence/animation-runtime-v0111/generic-motion-curve-regression-v0111.json`. `src/ugas/motion_curves.py` was not changed.

## FOLLOW-THROUGH CONTINUITY CONTRACT

The same `attack-front-v2` track set now requires post-hit follow-through path `>=12 px`, follow ratio `0.15..0.60`, immediate velocity retention `0.25..0.85`, bounded angular acceleration `<=10 deg/frame²`, no reversal on `6->7` or `7->8`, and the first reversal exactly at `8->9`. The pre-render result is `17.030469 px`, ratio `0.151858`, retention `0.367714`, and maximum absolute weapon acceleration `9.655555 deg/frame²`.

## WEAPON ACCELERATION / REVERSAL QA

All required negative controls reject: zero follow-through, 1 px follow-through, ratio `0.10`, retention `0.10`, retention above `0.90`, acceleration `12`, early reversals at `6->7` and `7->8`, excessive `8->9` reversal acceleration, V11 sword angle `20°`, V11 tip displacement above `40 px`, and displaced wrist/elbow controls. The near-ready positive control passes. The runner stops before rendering when the pre-render proxy fails.

## RECOVERY-COMPLETE CONTRACT

At V11, the sword angle delta to V0 is `4.0°`, tip distance is `12.811845 px`, wrist and elbow distances are `0.045 px`, pelvis distance is `0.045 px`, head/nose distance is `0.045 px`, and torso rotation delta is `0°`. The endpoint is therefore within the v0.11.1 recovery bounds.

## PRE-RENDER WEAPON PROXY

`weapon_continuity_pre_render_qa()` evaluates source targets and tracks before rasterization and before the first PNG. Its hash is `be9ca4a1b9958370fb138a2effa27547dd49dea549465708a66fad08b1510e1d`; all hard gates pass and `render_allowed=true`. Evidence: `docs/evidence/animation-runtime-v0111/weapon-continuity-pre-render-v0111.json`.

## POST-RENDER WEAPON QA

The post-render recomputation passes the same continuity gates and matches pre-render metrics within tolerance `0.001`. Sword/head collision is zero, sword/torso forbidden collision is zero, alpha safe margin is at least `24 px`, clipping is absent, and provenance is source-only. Evidence: `docs/evidence/animation-runtime-v0111/weapon-continuity-post-render-v0111.json` and `docs/evidence/animation-runtime-v0111/attack-v2-weapon-arc-qa-v0111.json`.

## ATTACK V2 MOTION TRACK CORRECTION

Only the existing `attack-front-v2` track values were corrected. The package remains front, 12 frames, 12 fps, non-loop, sword, 6x2 RGBA at 512x512 cells, with frozen markers `windup_peak=3`, `active_start=4`, `hit_event=6`, `active_end=7`, and `recovery_complete=11`. No new animation, direction, provider, character, or generation job was introduced.

## BODY MECHANICS REGRESSION

Root motion, torso motion, counter-motion, shoulder-to-wrist path, head counter-rotation, temporal limits, structural coverage, occlusion, seams, retention, and independent pose QA pass for all 12 frames. Evidence is split into `attack-v2-body-mechanics-qa-v0111.json`, `attack-v2-temporal-qa-v0111.json`, and the per-frame `qa-result.json`.

## FOOT / BALANCE REGRESSION

Both feet remain planted with no penetration, bounded sole drift, zero ankle drift from A0, and a valid pelvis support corridor. Evidence: `docs/evidence/animation-runtime-v0111/attack-v2-foot-ground-qa-v0111.json`.

## STRUCTURAL / OCCLUSION / POSE

All 12 frames pass layer integrity, expected occlusion, seam, retention, alpha margin, source-hash, duplicate-body, clipping, frozen z-order, and independent MediaPipe pose gates. The visual manifest binds 12 target/detected overlays plus the final spritesheet and GIF.

## HISTORICAL REPLAY

The v0.10.0 `attack-front-v1` replay is byte-identical, and the canonical v0.8.1 walk and v0.9.0 idle fixtures remain byte-identical. The v0.11.0 JSON evidence is retained and content-checked across Windows line-ending normalization. Evidence: `docs/evidence/animation-runtime-v0111/historical-replay-v0111.json`.

## NO SAM2 / NO COMFYUI / NO GENERATION

This correction is deterministic and source-only. `sam2_runs=0`, `comfyui_generation_jobs=0`, `diffusion_runs=0`, and `new_generation=0`. No SAM2 rerun, ComfyUI generation, diffusion, inpainting, or manual pixel edit occurred.

## TESTS

The complete test command is `python -m unittest discover -s tests -q`. The v0.11.1 continuity tests cover positive margins, every required negative control, near-ready pass, and fail-closed pre-render behavior. The final test count is recorded in the v0.11.1 review index.

## VALIDATION

The required compile, unit, profile, runner, state-consistency, review-index build, review-index validation, and repository checks are executed before publication. All required hard gates must pass with zero failures before this local qualification is reported.

## REVIEW INDEX

`docs/evidence/review-index-v0.11.1.json` is a GitHub-first, SHA-256 path index for source, governance, runtime, QA, and visual evidence. It excludes the self-referential index, forbids model-weight binaries and ZIPs, and records the build head separately from the final publication head.

## EXTERNAL VISUAL REVIEW STATUS

`attack_front_v2_external_visual=REQUIRED`. No external visual approval is claimed. The only allowed next action is `external_review_attack_front_v2_v0111`.

## BLOCKERS / GAPS

Production routing is intentionally `production_routing=BLOCKED`. The remaining gap is external visual review of attack-front-v2 and independent resolution of the final GitHub HEAD. MediaPipe/TFLite informational warnings do not alter the measured QA result.

## DECISIONS

`decision=QUALIFIED` applies to the local deterministic technical pilot only. It does not authorize production, generation, another direction, or another animation.

## NEXT STEP

`external_review_attack_front_v2_v0111`.

## DEFINITION OF DONE

Done for this slice means: the v0.11.0 false-green continuity finding is corrected; pre-render and post-render weapon gates pass; the generic curve contract remains green; all negative controls reject; historical evidence is preserved; the 12-frame source-only package is reproducible and hash-bound; no generation occurred; review evidence is indexed; external visual review remains required; and `production_routing=BLOCKED`.
