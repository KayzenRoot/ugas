# UGAS v0.8.1 test coverage matrix

| Requirement | Automated proof | Evidence | Gate |
|---|---|---|---|
| Same front/walk/8 cycle only | `test_exact_phase_contract_and_same_cycle_boundary` | `front-walk-cycle-v1-config-v081.json` | 8 exact phases, no new direction |
| Key pose immutability | `test_key_bindings_are_exact_and_all_targets_distinct` | `front-walk-targets-v081.json` | F0/F2/F4/F6 exact hashes |
| Deterministic smoothing | `test_smoothing_is_deterministic_and_image_free` | `front-walk-temporal-pre-smoothing-v081.json`, targets | no image input, bounded coordinates |
| Strict temporal limit | `test_strict_angular_gate_has_no_generic_30_degree_exception` | `front-walk-temporal-qa-v081.json` | max ≤25°/frame²; 30° fixture rejected |
| Actual alpha body stability | `test_actual_alpha_metrics_are_not_skeleton_bbox_metrics` | `front-walk-temporal-qa-v081.json` | head/torso alpha CV ≤0.04 |
| Visible sole and projected ground | `test_foot_gate_uses_visible_sole_and_projected_ground` | `front-walk-foot-contact-qa-v081.json`, foot-ground record | swing clearance ≥4 px; penetration ≤1.5 px |
| Negative foot regression | `test_foot_negative_fixture_rejects_boot_penetration_even_with_high_ankle` | in-test fail-closed fixture | ankle height cannot hide boot penetration |
| Loop integrity | `test_loop_qa_is_bound_to_frozen_z_order_boundary` | `front-walk-z-order-v081.json`, loop QA | actual F7→F0 z-order/depth boundary |
| Per-frame structure/provenance | `test_every_frame_and_all_auxiliary_gates_pass` | per-frame, structural, layer, occlusion, retention evidence | all frame gates green |
| Presentation fit | `test_package_is_rgba_and_pilot_only` | spritesheet/metadata/package | RGBA 2048×1024, 4×2, pilot-only |
| Review integrity | `test_review_visual_manifest_is_complete_and_hash_bound` | `review-visuals-v0.8.1.json` | 96 hash-bound evidence roles |
| External boundary | `test_no_generation_and_external_review_boundary` | provider/execution evidence | SAM2=0, ComfyUI=0, external review required |

The complete repository suite is executed with `python -m unittest discover -s tests -q`; the machine-readable review index records the final count and status. Full validation includes immutable v0.8.0 and earlier snapshots plus the active v0.8.1 correction.
