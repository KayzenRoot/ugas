# UGAS v0.5.3 test coverage matrix

| Contract | Automated evidence | Gate |
|---|---|---|
| Impossible causal gate | A=0.894403 plus delta 0.15 yields INVALID_CAUSAL_GATE_CONFIGURATION | fatal |
| State correction | current-state schema, nested status, checkpoint/review scan, stale RefControl action scan | fatal before jobs |
| Detected-joint metric | root/scale normalization, PCK, NME, limb angles, lower body, orientation, visibility | required |
| Synthetic calibration | target, neutral, mirror, T-pose, arms/legs ablations, weapon distractors | target/negative thresholds |
| Legacy score boundary | silhouette/keypoint score is diagnostic-only; identity overlap cannot authorize pose | required |
| MediaPipe mapping | 33-index mapping to UGAS/COCO-compatible joints with confidence flags | required |
| Independent estimator | library version, task URL, bytes/SHA-256, license evidence, QA-only isolation | qualify or measurement gap |
| Provider recheck gate | provider gap only after metric and estimator qualification | fatal |
| Generation boundary | no new seeds 53701–53703, no walk, anchors, spritesheet, GIF | fatal |
| Historical evidence | v0.5.2 report remains unchanged and separate from current state | required |
| Publication | tests, compileall, validation, tracked/no-Git snapshot, review ZIP audit | required |

The current execution stops at POSE_QA_MODEL_LICENSE_GAP. No provider or production approval is inferred.
