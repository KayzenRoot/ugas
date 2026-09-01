# UGAS v0.11.0 test coverage matrix

| Requirement | Evidence | Automated proof | Negative control |
|---|---|---|---|
| Generic motion-track contract | `generic-motion-curve-contract-v0110.json` | Opaque IDs, scalar/vec2, three interpolations, deterministic Hermite, exact keyframes and hash mutation | Duplicate IDs, unsorted/out-of-range/nonfinite/unknown interpolation, and missing clamp reject |
| Motion binding | v2 compiled manifest, QA, metadata and package | `motion_tracks_sha256` and normalized tracks are propagated and schema-bound | Unexpected or mismatched motion fields are rejected |
| Historical integrity | `historical-replay-v0110.json` | v1 frames/spritesheet/GIF replay byte-identically; walk/idle canonical fixtures match baseline SHA | Any byte drift produces `HISTORICAL_ANIMATION_REPLAY_DRIFT` |
| Attack v2 mechanics | `attack-v2-body-mechanics-qa.json` | Root path, torso range, arm-v1 comparison, left counter and head counter are measured | Zero/non-mechanical trajectory fails closed |
| Temporal quality | `attack-v2-temporal-qa.json` | Angle delta, acceleration, jerk, root/head/torso bounds and lifecycle | Threshold violation enters `ATTACK_V2_TEMPORAL_GAP` |
| Weapon arc and markers | `attack-v2-weapon-arc-qa.json`, `attack-v2-event-marker-qa.json` | Pivot, tip path, peak active, pre-hit acceleration, follow-through, collision and frozen hit frame | Collision, wrong active window or marker drift fails |
| Foot grounding | `attack-v2-foot-ground-qa.json` | Sole, penetration, sequential drift, ankle drift and balance corridor | Foot slide or root-moving-feet fails |
| Structural and pose QA | v2 `qa-result.json` and visual manifest | Source hashes, scale, alpha margin, coverage, occlusion, retention, MediaPipe PCK/NME/MAE | Duplicate, clipping, unexpected overlap, pose or provenance gap fails |
| Publication boundary | `execution-evidence-v0.11.0.json`, current state and review index | GitHub-first tracked evidence, external review required, production blocked | No self-asserted external approval or production routing |
