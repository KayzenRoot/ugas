# UGAS v0.6.1 test coverage matrix

| Area | Required proof | Test/evidence |
| --- | --- | --- |
| Generation evidence | Postprocess failure cannot erase a completed ComfyUI job | `test_postprocess_exception_preserves_generation_evidence` |
| Raw output | PNG is materialized and hash-bound before BiRefNet | `test_raw_output_materialized_before_postprocess` |
| Raw pose | P/PI score the raw PNG with a fixed policy | `test_p_raw_pose_runs_before_postprocess` |
| Execution validator | Three attempted jobs require completed generation, prompt, exact history and raw SHA-256 | `test_execution_validator_requires_all_completed_bindings` |
| Identity | Aggregate score cannot compensate for regional hard failures | `test_identity_hard_gates_are_fail_closed` |
| Failure reasons | Head, armor, black cloth and body drift are explicit hard failures | `test_identity_failure_reasons_include_hard_components` |
| Single subject | Body-sized second component fails; small detached sword passes | `test_single_subject_connected_components` |
| Historical fixture | v0.6.0 I image with two figures fails the single-subject gate | `test_historical_smoke_i_fixture_fails_single_subject` |
| Smoke scope | Exactly seed 61701 and three lanes; no later phases | `test_v061_smoke_scope_and_seed` |
| Regression boundary | v0.6.0 evidence, thresholds, model hashes and custom-node pin remain unchanged | `test_v060_history_and_boundaries_preserved` |
| Distribution | No weights, MediaPipe bundle or GPL source in Git/ZIP | `test_no_weights_or_vendored_source` |

The frozen pose gates remain: at least 10 measurable joints, PCK@.10 >= 0.80, NME <= 0.10, limb-angle MAE <= 18 degrees, lower-body PCK >= 0.75 and orientation match. Benchmark, confirmation, walk and anchors are intentionally NOT_RUN in v0.6.1.
