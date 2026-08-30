# ComfyUI v0.5.0

O alvo local testado é ComfyUI `0.34.0` com GPU NVIDIA GeForce RTX 5050. O template oficial materializado é `Comfy-Org/workflow_templates/templates/image_flux2_klein_image_edit_4b_base.json`, commit `04f33569dad7a1d277429bda9f35209dfa4d91cf`, SHA-256 `346cd9a63bfe34a5a9207f50c34a87feaf4e70806d13c9d2738fd521133670d0`.

O nó nativo `ReferenceLatent` está presente em `/object_info/ReferenceLatent` e permite encadear múltiplas referências. A implementação v0.5 usa somente API-format nodes registrados, sem custom nodes. A ordem é explícita e não deve ser invertida:

- `reference[0]`: anchor R4, identidade, estilo, material e propriedades protegidas.
- `reference[1]`: guia determinístico, pose e vista.

O A/B e os jobs do piloto estão em `docs/evidence/multiref-qualification.json`, `directional-anchor-set.json` e `walk-front-8-animation-qa.json`. Health, disponibilidade de GPU ou cache não substituem prova end-to-end de prompt/history/output.
