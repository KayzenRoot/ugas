# UGAS test coverage matrix v0.4.3

The historical [v0.4.2 matrix](test-coverage-matrix-v0.4.2.md) remains immutable. This addendum maps the 03E correction tests; all current tests are run together.

| Requirement | Regression test | Evidence |
|---|---|---|
| Exact job/history binding | `test_history_binding_requires_exact_prompt_and_job` | `reference-edit-execution-evidence.json` |
| Stale output rejection | `test_stale_output_is_rejected` | execution evidence `target_existed_before_submission=false` |
| Unique seeds | `test_unique_seed_is_required` | candidate and execution JSON |
| Runtime plausibility | `test_runtime_plausibility_flags_suspicious_execution` | runtime status |
| Capability-specific image-edit params | `test_capability_specific_parameters_are_separate` | workflow qualification |
| Machine-readable edit contract | `test_edit_contract_has_protected_identity_and_exact_target` | `reference-edit-contract.json` |
| Global darkening failure | `test_photometric_blackening_fails` | fidelity JSON |
| Head darkening failure | `test_head_darkening_fails` | fidelity JSON |
| Valid recolour | `test_valid_recolor_passes` | selected fidelity JSON |
| No target change | `test_no_target_change_fails` | fidelity failure reason |
| Protected-region change | `test_protected_region_excessive_change_fails` | fidelity failure reason |
| Only eligible candidate selected | `test_multiple_candidates_only_eligible_is_selected` | candidate set |
| Controlled zero-eligible outcome | `test_zero_eligible_candidates_has_controlled_failure` | `NO_ACCEPTABLE_REFERENCE_EDIT` contract |
| Temporary candidates not revisions | `test_temporary_candidates_are_not_revisions` | revision chain |
| R1-R4 order | `test_r1_r4_chain_is_ordered` | `revision-chain.json` |
| Manifest hashes | `test_new_manifest_role_requires_hash` | `review-visuals.json` |
| Version 0.4.3 | `test_version_is_043` | version surfaces |
| Historical mapping | `test_historical_matrix_is_preserved` | v0.4.2 matrix |
| Target-mask confidence | `test_target_mask_confidence_is_recorded` | target-mask metadata |
| Contract hash stability | `test_contract_hash_is_stable_for_same_payload` | contract hash |

The v0.4.3 suite adds 21 tests and requires the historical suite to remain a strict superset; it does not authorize animation.
