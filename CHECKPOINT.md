# UGAS checkpoint - v0.5.3

**STATUS:** POSE_QA_MODEL_LICENSE_GAP. A calibração de métrica passou, a biblioteca MediaPipe foi importada localmente, mas o bundle Pose Landmarker .task não possui termos autoritativos determinados para uso comercial e redistribuição. O processo parou fail-closed antes de qualquer novo job de geração.
**VERSION:** 0.5.3
**PHASE:** PROMPT-04E / POSE_METRIC_CALIBRATION

## Current state

O estado machine-authoritative é [docs/evidence/current-state.json](docs/evidence/current-state.json). O resultado reportado no v0.5.2 como POSE CONTROL PROVIDER GAP foi reclassificado no v0.5.3 como POSE_METRIC_GATE_DESIGN_GAP: a baseline histórica A=0.894403 somada ao delta fixo 0.15 exigia B=1.044403, acima do máximo do score [0,1]. O v0.5.2 permanece histórico e não foi reescrito.

## State consistency correction

- O gate ativo é POSE_QA_MODEL_LICENSE_GAP e o nested state_consistency.status é exatamente igual ao stop reason.
- generation_provider_change_authorized e walk_authorized permanecem falsos.
- O checkpoint não afirma que RefControl está pendente: o artifact histórico já contém hash, licença e loader nativo qualificados.
- Âncoras direcionais v3, walk v3, spritesheet e GIF não foram promovidos.

## Pose metric calibration

A métrica primária detected_joint_pose_error foi calibrada com nove fixtures determinísticos, sem IA: alvo, neutral frontal, lado espelhado, T-pose, braços para baixo, pernas erradas, braço errado e dois controles com espada vertical longa. Ela usa raiz/pelve, escala de torso/corpo, PCK@0.10, NME, erro angular de membros, PCK de lower body e orientação esquerda/direita. A métrica antiga de silhueta/keypoint ficou somente diagnóstica.

O alvo obteve 1.000; os negativos ficaram entre 0.278 e 0.714; neutral, mirror e T-pose ficaram abaixo de 0.65; a espada não alterou o score; a ablação de membro foi detectada. A evidência está em [docs/evidence/pose-metric-calibration.json](docs/evidence/pose-metric-calibration.json).

## Estimator boundary

MediaPipe Pose Landmarker foi selecionado apenas como estimador independente QA. A versão local importável é registrada, o bundle foi baixado somente fora do repositório, e sua hash/bytes estão registradas. Como os termos do bundle não foram determinados de fonte autoritativa, nenhuma detecção em outputs estilizados foi usada para qualificação e nenhum provider foi medido nesta execução.

## Execution and publication

Não houve novo job ComfyUI, mudança de provider, âncora, walk ou spritesheet no v0.5.3. Animação genérica permanece fora deste slice e não autoriza promoção de walk. O review ativo é [REVIEW-v0.5.3.md](REVIEW-v0.5.3.md); reviews v0.5.2 e anteriores são históricos. A aprovação visual humana e qualquer aprovação de produção continuam separadas.
