# UGAS v0.8.0 test coverage matrix

| Gate | Implementation/evidence | Regression coverage |
|---|---|---|
| Exact F0/F2/F4/F6 baseline binding | `front-walk-targets-v080.json` | `test_key_pose_hash_binding_is_exact` |
| Frozen configuration before render | `front-walk-cycle-v1-config.json` | `test_config_is_frozen_before_render`, `test_config_sha_is_bound_to_targets` |
| Hermite skeleton intermediates and bone projection | `src/ugas/cutout_temporal.py`, `front-walk-bone-projection-v080.json` | `test_all_targets_are_distinct`, `test_bone_projection_passes` |
| Eight per-frame hard gates | `front-walk-per-frame-qa-v080.json` | `test_each_frame_passes_all_hard_gates` |
| Source-derived structural coverage | `front-walk-structural-coverage-v080.json` | `test_structural_coverage_passes_every_frame` |
| 11-part layer integrity | `front-walk-layer-integrity-v080.json` | `test_layer_integrity_passes_every_frame` |
| Topology, occlusion and retention | `front-walk-occlusion-v080.json`, `front-walk-retention-v080.json` | `test_occlusion_and_retention_pass_every_frame` |
| Feet, ground and planted slip | `front-walk-foot-contact-qa-v080.json` | `test_foot_contact_passes` |
| Temporal spikes, uniqueness and loop | `front-walk-temporal-qa-v080.json`, `front-walk-loop-qa-v080.json` | `test_temporal_qa_passes`, `test_loop_passes` |
| Half-cycle reflection | `front-walk-half-cycle-qa-v080.json` | `test_half_cycle_passes` |
| Sword/right-hand invariant | per-frame QA and package manifest | `test_each_frame_passes_all_hard_gates`, `test_package_is_pilot_only` |
| Sprite order/dimensions and metadata hashes | `walk-front-v080/walk-front-spritesheet-v080.png`, metadata | `test_sprite_is_rgba_2048_by_1024`, `test_metadata_has_row_major_order_and_hashes` |
| No SAM2/ComfyUI/new generation | execution/provider evidence | `test_no_generation_provider_calls` |
| Review evidence completeness | `review-visuals-v0.8.0.json` | `test_all_visual_evidence_sets_have_eight_frames` |
| Historical v0.7.3 preservation | v0.7.3 snapshots and review | `test_historical_v073_snapshot_exists` |

The complete suite includes all historical v0.7.3 regressions plus these v0.8.0 tests. A failed frame, temporal, loop, or packaging gate is fail-closed and cannot authorize production routing. External visual review remains required.
