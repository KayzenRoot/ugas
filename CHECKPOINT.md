# UGAS checkpoint - v0.6.1

**STATUS:** `SDXL_OPENPOSE_CONTROL_GAP`
**VERSION:** `0.6.1`
**PHASE:** `SDXL_CONTROL_POSE_PROVIDER_QUALIFICATION`

## Current state

O estado machine-authoritative está em [docs/evidence/current-state.json](docs/evidence/current-state.json). Esta correção preserva a auditoria, modelos, hashes, workflows e thresholds do v0.6.0, materializa cada PNG bruto antes do BiRefNet e torna a identidade e o sujeito único hard gates. O smoke P/I/PI usa somente a seed 61701; `provider_smoke_status`, `generation_provider_change_authorized=false`, `walk_authorized=false` e `new_generation_jobs=0` ficam explícitos neste checkpoint antes da execução.

O v0.5.5 é histórico e permanece preservado como `REVIEW_ARCHIVE_VERIFIED`; sua decisão de pose anterior também preserva `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED` do v0.5.4. Os 9 outputs A/C/R, hashes e thresholds de [v054-provider-qualification.json](docs/evidence/v054-provider-qualification.json) não são reescritos.

## Scope and gate

Este slice qualifica somente SDXL + OpenPose ControlNet + IP-Adapter para geração 2D controlada. O ControlNet recebe o PNG COCO-18 determinístico de UGAS; o IP-Adapter recebe exclusivamente o anchor R4. Não há preprocessor, FLUX replacement, walk, âncoras v3, spritesheet, GIF, animação ou 3D.

Com o gate de consistência e a auditoria aprovados, a ordem autorizada é: qualificação de fontes, licenças, bytes e SHA-256; doctor do runtime RTX 5050; workflow API; smoke factorial P/I/PI; e somente se aprovado, benchmark e confirmação 3/3. Um gap encerra a lane com seu estado exato. A animação genérica também não é autorizada por este checkpoint.

## Evidence boundary

Pesos e código do custom node ficam fora do Git e do review ZIP. O repositório registra apenas manifests, hashes, commit pinado, auditoria e evidência. `REVIEW_ARCHIVE_VERIFIED` não significa aprovação visual humana, GitHub Actions, deployment ou aprovação de produção. Walk permanece não autorizado.
