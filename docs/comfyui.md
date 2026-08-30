# ComfyUI v0.5.3

O alvo local testado é ComfyUI `0.34.0` com GPU NVIDIA GeForce RTX 5050. O template oficial materializado é `Comfy-Org/workflow_templates/templates/image_flux2_klein_image_edit_4b_base.json`, commit `04f33569dad7a1d277429bda9f35209dfa4d91cf`, SHA-256 `346cd9a63bfe34a5a9207f50c34a87feaf4e70806d13c9d2738fd521133670d0`.

O nó nativo `ReferenceLatent` está presente em `/object_info/ReferenceLatent` e permite encadear múltiplas referências. A implementação v0.5 usa somente API-format nodes registrados, sem custom nodes. A ordem é explícita e não deve ser invertida:

- `reference[0]`: anchor R4, identidade, estilo, material e propriedades protegidas.
- `reference[1]`: guia determinístico, pose e vista.

Os artifacts históricos do benchmark nativo A/B/C e RefControl estão em `docs/evidence/native-reference-order-qualification.json`, `docs/evidence/refcontrol-pose-qualification.json` e `docs/evidence/execution-evidence-v0.5.2.json`. O v0.5.3 não iniciou jobs: primeiro calibra a métrica de joints e qualifica um estimador QA independente. Health, GPU ou cache não substituem prova end-to-end de prompt/history/output.

O multi-reference só poderá ser reavaliado após `METRIC_CALIBRATION_PASSED` e `POSE_QA_ESTIMATOR_QUALIFIED`. O resultado atual `POSE_QA_MODEL_LICENSE_GAP` bloqueia a rechecagem, o walk e qualquer provider gap. Os arquivos de modelo permanecem fora do Git.
