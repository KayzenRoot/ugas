# UGAS checkpoint - v0.5.1

**STATUS:** READY_FOR_REVIEW / ANIMATION_PILOT_VISUAL_REVIEW_REQUIRED. O piloto técnico de multi-reference, conjunto direcional e walk/front/8 passou; falta revisão visual humana.
**VERSION:** 0.5.1
**PHASE:** PROMPT-04 / MULTIVIEW-POSE-WALK-PILOT

## Canonical anchor

Asset `asset-2fec6fed1d714d0cb58ad75b56d7ba71`, revisão R4 `revision-3a425d184b1a49be9f6d6c8d52d04b96`, SHA-256 `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`. A aprovação recebida é registrada somente como `external-pipeline-anchor`; `PRODUCTION_READY` continua falso até aprovação de produção separada.

## Completed

- Topologia oficial materializada e conferida contra `Comfy-Org/workflow_templates`; `ReferenceLatent` local presente no ComfyUI 0.34.0.
- Manifesto de identidade, quatro guias de vista e oito guias walk source-controlled, sem conteúdo AI.
- A/B real: canonical-only versus canonical+guide, seeds 50501/50502, workflow Base 20 steps / CFG 5 / Euler.
- Âncoras front/left/right/back: front é cópia byte-identical do R4; demais têm 2 candidatos preservados, BiRefNet, normalização e QA.
- Walk/front/8: oito frames 512, PNG RGBA, pivot/ground compartilhados, spritesheet, metadata, GIF e diff contact.
- `python -m unittest discover -s tests -q` e `python scripts/validation/run_validation.py` são gates de publicação.

## Boundaries

Não autoriza animação genérica, outros ciclos, todas as vistas, 3D, áudio, engine integration, DWPose/OpenPose/ControlNet/custom nodes, cloud, pagos ou aprovação automática.

## Evidence

O review técnico é `REVIEW-v0.5.1.md`; a evidência visual e machine-readable está em `docs/evidence/`. O ZIP `review/UGAS-review-v0.5.1-*.zip` só pode ser criado depois de commit, push e verificação pública do `main`, e deve ser a última escrita do processo. `REVIEW-v0.5.0.md` permanece histórico e imutável.

## Corrective gate

O walk v2 só pode existir depois de três pares A/B demonstrarem ganho causal de pose de pelo menos 0.15 sobre o baseline A. A razão do bounding box é diagnóstico, nunca critério de qualificação. Se o gate falhar, o estado correto é `MULTI_REFERENCE_POSE_CONTROL_GAP` e nenhum spritesheet v2 aprovado é fabricado.
