# UGAS Review - Prompt 04-E v0.5.3

## STATUS

BLOCKED / POSE_QA_MODEL_LICENSE_GAP. The metric calibration passed, but independent pose QA cannot be qualified until authoritative terms for the versioned MediaPipe task bundle are determined. No provider conclusion is emitted.

## VERSION

0.5.3

## PHASE

POSE_METRIC_CALIBRATION

## OBJECTIVE

Prove that pose measurement is valid before making any native or RefControl provider decision. Preserve the R4 identity anchor and keep generation, animation, and provider routing fail-closed.

## V0.5.2 AUDIT RESULT

The historical v0.5.2 report of LOCAL_POSE_CONTROL_PROVIDER_GAP is not accepted as a causal provider finding. The old additive gate used A=0.894403 and delta=0.15, requiring B=1.044403 while the score maximum is 1.0. The corrected finding is POSE_METRIC_GATE_DESIGN_GAP. REVIEW-v0.5.2.md remains immutable historical evidence.

## GATE IMPOSSIBILITY FINDING

The validator and unit test reject this configuration with INVALID_CAUSAL_GATE_CONFIGURATION. A provider gap is not inferred from a gate that can never be satisfied. The normalized headroom calculation for the historical RefControl result is retained as diagnostic evidence: (0.992258 - 0.894403) / (1 - 0.894403) = approximately 0.926684.

## STATE CONSISTENCY FIX

current-state.json, CHECKPOINT.md, and this active review identify v0.5.3 and the same current stop. The nested state status equals POSE_QA_MODEL_LICENSE_GAP. Provider change and walk remain unauthorized. The stale action claiming that RefControl still needed verification was removed because the historical RefControl model/hash/loader artifact already exists.

## POSE METRIC CALIBRATION

The primary metric is detected_joint_pose_error. It translates to the pelvis/root, scales by robust torso/shoulder/body-height evidence, preserves left/right, and reports PCK@0.10, NME, limb-angle MAE, lower-body PCK, orientation, confidence coverage, and measurability. The legacy v0.5.2 silhouette/keypoint score is diagnostic-only.

Nine deterministic non-AI fixtures were evaluated. TARGET scored 1.000. All ordinary negatives were at least 0.20 below target. The target is at least 0.90, and every negative is at most 0.80; neutral front, mirrored wrong side, and T-pose are each at most 0.65. Low visibility and ablated limbs are not accepted.

## SYNTHETIC NEGATIVE CONTROLS

The set contains TARGET, NEUTRAL_FRONT, MIRRORED_WRONG_SIDE, T_POSE, ARMS_DOWN, LEGS_WRONG, ARM_WRONG, TARGET_PLUS_LONG_VERTICAL_SWORD, and NEUTRAL_FRONT_PLUS_VERTICAL_SWORD. The sword controls demonstrate that weapon pixels do not substitute for detected limbs and do not change the primary score beyond 0.05.

## POSE QA ESTIMATOR

MediaPipe Pose Landmarker is the first candidate and is isolated to QA. It is not a ComfyUI node, generation control, ControlNet, DWPose, or provider router. The installed library is importable at 0.10.35. Detection on stylized provider outputs was not run because the task bundle license gate stopped qualification first.

## POSE QA MODEL / LICENSE / HASH

The official task URL, local byte count, SHA-256, library version, and source links are recorded in docs/evidence/pose-qa-estimator-model.json. The library repository is Apache-2.0, but the versioned task bundle terms for commercial use and open-source redistribution were not authoritatively determined. This is POSE_QA_MODEL_LICENSE_GAP. The bundle is outside Git and outside the review ZIP.

## DETECTED-JOINT METRIC

MediaPipe indices map to UGAS/COCO-compatible joints: nose, shoulders, elbows, wrists, hips, knees, ankles, with optional eyes and ears. Required core joints are shoulders, elbows, wrists, hips, knees, and ankles. A result with fewer than ten measurable body joints, low confidence, wrong orientation, PCK below 0.80, NME above 0.10, limb-angle MAE above 18 degrees, or lower-body PCK below 0.75 cannot pass.

## CAUSAL EFFECT METRIC

The fixed additive rule B >= A + delta is prohibited when A + delta exceeds the metric maximum. v0.5.3 records normalized headroom gain and requires absolute target-pose qualification before any relative improvement can be used. No causal provider decision was made because the independent estimator was not qualified.

## NATIVE LANE RECHECK

NOT AUTHORIZED. The metric calibration passed, but the estimator/model gate did not. No new seeds 53701, 53702, or 53703 were submitted and no new native lane outputs were created.

## REFCONTROL LANE RECHECK

NOT AUTHORIZED. The historical RefControl artifact is preserved and its native loader/model evidence remains historical. No new RefControl output was measured in v0.5.3.

## IDENTITY / WEAPON QA

Identity and weapon evidence remain separate from pose measurement. The R4 anchor remains bound to its existing asset, revision, and SHA-256. Synthetic sword controls are negative controls only; weapon pixels never contribute to the detected-joint score.

## FINAL POSE PROVIDER DECISION

POSE_QA_MODEL_LICENSE_GAP. The result is a measurement/QA gap, not LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED. Provider failure can only be emitted after metric calibration and estimator qualification both pass.

## EXECUTION EVIDENCE

execution-evidence-v0.5.3.json records zero new generation jobs, no previous-frame chaining, and the authorization stop. The calibration and estimator scripts are reproducible locally without generation-provider routing.

## TESTS

The v0.5.3 regression suite covers impossible gates, headroom gain, synthetic target/negative controls, sword invariance, mirrored orientation, limb ablation, low visibility, incorrect joints, MediaPipe mapping, silhouette-only rejection, provider-gap authorization, and state consistency. Historical v0.5.2 tests remain represented separately.

## VALIDATION

The final validation must pass compileall, the full unit suite, schema checks, historical evidence checks, v0.5.3 calibration/estimator/state checks, tracked snapshot, and no-Git review snapshot. The exact final counts and public commit are filled after the final validation run.

## TRACKED SNAPSHOT / GITHUB

The repository is github.com/csn1985-ship-it/ugas. Publication status is limited to the pushed commit and reproducible local validation; GitHub review, human visual approval, deployment, and production approval are not inferred.

## SECURITY

No generation weights or MediaPipe task bundle are tracked or packaged. The local model is outside Git and the review ZIP. Evidence contains hashes and public source URLs only; no secrets are included.

## VISUAL REVIEW STATUS

Technical contact sheets are materialized for calibration, negative controls, and the blocked estimator overlay. Human visual review remains required and is not an automatic approval.

## BLOCKERS / GAPS

The authoritative license and redistribution terms for the versioned Pose Landmarker task bundle remain undetermined. Therefore no stylized-character detection qualification, provider recheck, anchors v3, walk v3, spritesheet, or GIF is authorized.

## DECISIONS

1. Reclassify the impossible v0.5.2 additive gate as POSE_METRIC_GATE_DESIGN_GAP.
2. Adopt detected-joint measurement as the only v0.5.3 primary pose metric.
3. Keep the legacy silhouette score diagnostic-only.
4. Stop at POSE_QA_MODEL_LICENSE_GAP and do not promote a provider gap.

## NEXT STEP

Resolve the authoritative task-bundle license terms, rerun the independent estimator qualification on the required R4/A/pose-controlled set, and only then consider the bounded A/C/R recheck.

## DEFINITION OF DONE

State is coherent; the impossible gate is guarded; deterministic calibration passes; negative controls and sword invariance pass; the estimator/library/model/license evidence is bound; no unauthorized generation occurs; validation and snapshots reproduce; and the result is documented without claiming external approval.

## REVIEW ZIP

The final v0.5.3 review ZIP is created only after commit, push, public HEAD verification, and final validation. It is the last filesystem write of this execution.
