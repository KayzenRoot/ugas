# UGAS test coverage matrix v0.5.1

The existing 89 tests remain in the suite. The v0.5.1 corrective layer adds 10 tests below without deleting or weakening historical coverage; the full suite contains 99 tests.

| Requirement | Test coverage | Evidence |
|---|---|---|
| 89-test regression baseline | Full existing `tests/test_*.py` suite | unittest result |
| Real walk reference call per frame | `test_generate_walk_pilot_calls_real_reference_path_for_each_frame_in_fake_runtime` | fake ComfyUI prompt/output bindings |
| B without causal pose gain does not qualify | qualification rule and fail-closed status checks | `multiref-v2-qualification.json` |
| Pose is not bbox-only | `test_pose_metric_uses_keypoints_segments_and_silhouette`, `test_bbox_ratio_alone_cannot_qualify` | pose component metrics |
| Candidate selection | `test_candidate_selection_uses_quality_before_seed` | ranking key |
| Identity drift | `test_identity_descriptor_rejects_face_armor_weapon_drift` | component rejection reasons |
| Static gait failure | `test_temporal_qa_rejects_nearly_static_cycle` | lower-body motion gate |
| Last/first outlier | `test_temporal_qa_rejects_last_first_outlier` | robust loop closure gate |
| Half-cycle symmetry evidence | `test_half_cycle_mirror_is_recorded` | mirrored phase metrics |
| Mannequin control separation | `test_pose_guide_v2_is_filled_control_and_separate_review_overlay` | renderer/control hashes |
| Uniform tall-frame normalization | `test_normalization_uniformly_scales_tall_candidate_without_stretching` | scale, bbox and baseline evidence |
| Frame-level gates and no chaining | generator records and schema validation | `walk-v2-temporal-qa.json` / execution evidence |
| Snapshot reproducibility | validation script exact `git archive HEAD` and no-Git checks | validation output |

Historical matrices `docs/test-coverage-matrix-v0.4.2.md`, `docs/test-coverage-matrix-v0.4.3.md` and `docs/test-coverage-matrix-v0.5.0.md` remain unchanged.
