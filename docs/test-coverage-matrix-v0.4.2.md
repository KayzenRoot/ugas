# UGAS v0.4.2 test coverage matrix

This matrix preserves the behavioral intent of the published v0.4.0 suite while adapting identifiers and contracts to v0.4.2. Historical review files remain unchanged.

## Historical unit-test intents

| v0.4.0 intent | v0.4.2 coverage | disposition |
| --- | --- | --- |
| repository directories and documents | `RepositoryContractRegressionTests.test_expected_directories_and_documents_exist` | adapted |
| all Agent Skills frontmatter | `test_every_skill_has_valid_agent_skills_frontmatter` | retained |
| profiles and schemas | `test_profiles_and_schema_documents_validate` | retained |
| templates, providers and workflow manifests | `test_templates_provider_and_workflow_instances_validate` | retained |
| Unity/Godot/Unreal/Web engine markers | `test_engine_markers_and_dimension_evidence` | retained |
| bounded context scan and heavy-directory skips | `test_context_scan_is_bounded_and_skips_heavy_directories` | retained |
| installer selection and safe refresh history | `test_installer_auto_selection_and_refresh_preserve_history` | retained |
| unknown provider availability | `test_default_availability_is_unknown` | retained |
| asset/non-asset classification | `test_asset_and_non_asset_classification` | retained |
| no 3D-to-2D fallback | `test_3d_final_never_falls_back_to_2d_provider` | retained |
| paid-disabled self-hosted routing | `test_paid_disabled_keeps_self_hosted_remote_eligible` | retained |
| qualified 2D routing | `test_qualified_2d_evidence_selects_comfyui_for_master_sprite` | retained |
| partial MMORPG animation gap | `test_partial_mmorpg_plan_exposes_animation_gap` | retained |
| capable fallback routing | `test_capability_gap_skips_preferred_provider_and_uses_capable_fallback` | retained |
| local/remote readiness separation | `test_local_and_remote_dry_runs_are_separate` | retained |
| version surfaces | `test_version_surfaces_are_consistent` | adapted to 0.4.2 |
| RGB/RGBA and transparency distinction | `test_alpha_and_transparency_stats_distinguish_rgb_and_rgba` | retained with valid non-border fixture |
| Comfy client API flow | `test_client_api_flow_and_output_retrieval` | retained |
| reference upload and workflow injection | `test_reference_upload_and_official_workflow_injection` | adapted to explicit Base edit workflow |
| Comfy execution error and route evidence | `test_client_error_and_route_evidence` | retained |
| structured Comfy timeout | `test_client_timeout_is_structured` | retained |
| capability state and image pipeline | `test_capability_state_and_image_pipeline` | retained |
| bounded durable job transitions | `test_job_transitions_are_bounded` | retained |
| qualified 1x1 sprite pilot and grid block | `test_sprite_pilot_allows_only_qualified_1x1_master` | adapted to 0.4.2 |
| reproducible prompt compiler | `test_prompt_compiler_is_reproducible` | retained |
| technical candidate gate separate from visual approval | `test_candidate_metrics_and_visual_gate_are_distinct` | retained |

## Historical validation intents

| v0.4.0 validation intent | v0.4.2 validation coverage | disposition |
| --- | --- | --- |
| tracked paths and repository structure | required-path and tracked-snapshot checks | retained/adapted |
| Agent Skills contract | restored unit test plus validation check | retained |
| schema documents and profile instances | schema and instance validation | retained |
| provider manifests and scope limits | provider validation and scope tests | retained |
| workflow manifests and API graphs | workflow registry validation | retained/adapted |
| explicit model registry/hash/license gates | model registry validation and lane tests | retained/adapted |
| ComfyUI smoke/capability evidence | real pilot evidence and capability validation | superseded by fresh pilot |
| candidate set and PNG QA | safe-margin candidate and transparency/RGB QA | superseded by stronger gates |
| sprite pilot evidence | 1x1 scope regression; no multi-frame work | retained |
| review visual evidence | v0.4.2 manifest role/path/hash validator | superseded by stronger contract |
| request routing and capability gaps | restored routing tests and validation | retained |
| installation docs and consumer bootstrap | restored installer tests and validation | retained |
| version consistency | 0.4.2 runtime/package/docs checks | adapted |
| Git/no-Git snapshot behavior | exact archive and no-Git review snapshot runs | retained/adapted |
| historical v0.4.0 evidence | review history preserved; new evidence generated | intentionally historical |

The final review reports the canonical unit-test count, validation count and exact tracked-snapshot result. The suite is expected to be a superset of the 26 historical unit-test intents plus the v0.4.1 and v0.4.2 contracts.
