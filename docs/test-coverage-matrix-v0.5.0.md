# UGAS test coverage matrix v0.5.0

| Requirement | Coverage | Evidence |
|---|---|---|
| Identity hash and scope | `test_identity_manifest_binds_exact_r4` | `identity-manifest.json` |
| Pose guide schema/determinism | `test_pose_guides_are_explicit_and_unique` | `pose-guides/` |
| Native topology and order | `test_multiref_workflow_has_native_reference_chain` | workflow registry/API JSON |
| Fail-closed capability | `test_multiref_gate_does_not_authorize_walk` | qualification status |
| No previous-frame chaining | `test_walk_contract_forbids_previous_frame` | animation evidence |
| Candidate/retry bounds | `test_candidate_and_retry_bounds_are_bounded` | anchor/walk evidence |
| Transparent normalization | `test_normalization_keeps_pivot_and_no_stretch` | frame metrics |
| Temporal QA | `test_temporal_contract_requires_eight_unique_frames` | `walk-front-8-animation-qa.json` |
| Output pack | `test_walk_pack_contract_is_exact` | spritesheet, GIF, metadata, contact sheet |
| Review integrity | `test_v050_visual_manifest_is_hash_bound` | `review-visuals-v0.5.0.json` |
| Historical regression | existing 79 tests | v0.4.0/v0.4.2/v0.4.3 suites |

Visual approval is intentionally not an automated test result.
