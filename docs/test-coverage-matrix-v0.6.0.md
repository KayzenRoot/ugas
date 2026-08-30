# UGAS v0.6.0 test coverage matrix

| Prompt requirement | Implementation/evidence | Validation |
|---|---|---|
| Preserve v0.5.4/v0.5.5 history | `docs/evidence/current-state.json`, `REVIEW-v0.6.0.md` | `v060:historical-separation` |
| Pin and audit IP-Adapter custom node | `providers/custom-nodes/registry.json`, `scripts/providers/audit_ipadapter_custom_node.py` | `v060:custom-node-audit` |
| Record exact model source/license/bytes/SHA-256 | `scripts/providers/qualify_sdxl_models.py`, four artifact records | `v060:model-stack`, `v060:artifact:*` |
| Verify RTX 5050/ComfyUI/native nodes | `scripts/providers/run_sdxl_runtime_doctor.py` | `v060:runtime-doctor`, `v060:native-nodes` |
| Separate deterministic API graphs | `providers/workflows/sdxl-*.api.json` and workflow registry | `v060:workflow-qualification`, `v060:workflow-separation` |
| Execute P/I/PI factorial smoke | `scripts/validation/run_sdxl_provider_qualification.py` | `v060:factorial` |
| Reuse frozen MediaPipe detected-joint thresholds | `docs/evidence/pose-thresholds-v054.json` | `v060:provider-status`, provider threshold record |
| Enforce identity/weapon and causal gates | provider qualification JSON | provider `paired.causal`, `confirmation.green` |
| Keep walk/animation blocked | current state and review docs | `v060:scope-boundary`, `v060:review-boundary` |
| Preserve external-only weights/source boundary | model/custom-node evidence and archive verifier | `v060:model-boundary`, `v060:execution` |
| Regression and extracted snapshot validation | `scripts/validation/run_validation.py` | unit tests, compileall, full validation, ZIP self-validation |

The status is fail-closed. A hardware, model, node, pose, identity, weapon or causal failure leaves the SDXL capability unqualified and does not authorize walk or animation.
