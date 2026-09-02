# UGAS v0.12.1 test coverage matrix

This matrix maps the correction prompt to executable coverage. The v0.12.0 matrix and results remain historical and rejected; this file describes only the active v0.12.1 correction.

| Prompt finding / gate | Implementation | Automated proof | Runtime evidence |
|---|---|---|---|
| F-01 DOM XSS and headers | `dashboard.js`, `dashboard_app.py` | `test_xss_payload_is_structured_text_and_dashboard_has_no_unsafe_sink`, `test_api_security_headers_and_read_only_method` | `security-xss.json` |
| F-02 fail-closed QA | `qa_integrity.py`, `state_consistency_v0121.py` | `test_qa_negative_controls_reject_false_green_counts`; active index/state validators | `qa-negative-controls-v0121.json` |
| F-03 live command/job/stage pipeline | `service.py`, `generation.py` | `test_stage_aggregation_has_real_metadata_and_dashboard_is_not_workload`, `test_orphan_running_job_is_not_active` | `pipeline-live-stage-v0121.json`, `orphan-reconciliation-v0121.json` |
| F-04 resource/process/provider visibility | `system_metrics.py`, `process_metrics.py`, dashboard UI | `test_process_contract_has_ugas_and_comfyui_fields` | `system-gpu-process-v0121.json` |
| F-05 file activity, stable transition, preview contract | `asset_activity.py`, dashboard UI/API | `test_spritesheet_precedes_image_and_stable_transition_is_emitted` | `file-activity-v0121.json`, `preview-security-v0121.json` |
| F-06 concurrent probes and stale-last-known | `service.py` collector | `test_stale_last_known_preserves_sample_without_zero` | `stale-last-known-v0121.json` |
| F-07 corrected v0.11.2 binding | forward-only evidence binding | exact GIF SHA and immutable old record check | `external-review-v0112-binding-correction-v0121.json` |
| F-08 governance and regression | current state/review index | full unittest and validation commands; 14 v0.11.2 visual hashes | `animation-regression-v0112-v0121.json`, review index |

Acceptance semantics are fail-closed: tests require `status=passed`, `failed=0`, `passed=count`; validation requires `status=passed`, `failed=0`, `passed=checks`. Missing, malformed, mismatched or contradictory evidence is a GAP. External dashboard review remains `REQUIRED` and production remains `BLOCKED`.
