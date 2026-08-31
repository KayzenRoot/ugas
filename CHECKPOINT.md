# UGAS checkpoint - v0.7.2

**STATUS:** `CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED`
**VERSION:** `0.7.2`
**PHASE:** `DETERMINISTIC_CUTOUT_RIG_POSE_PROVIDER`

## Current state

O estado machine-authoritative está em [docs/evidence/current-state.json](docs/evidence/current-state.json). O cutout-rig R4 v0.7.1 é reutilizado como input imutável para o plano v0.7.2 de oclusão, dez conexões topológicas, retenção por profundidade e quatro poses key. O review v0.7.1 e o review v0.6.2 permanecem imutáveis.

O escopo atual não é geração: `deterministic-cutout-rig-2d` recebe somente o R4 RGBA canônico e as partes v0.7.1. Não houve job ComfyUI, fallback diffusion, nova execução SAM2, SAM3 ou segmentação por frame. O provider continua fora do routing de produção até revisão visual externa.

## Scope and gate

O baseline SAM2/runtime/checkpoint é histórico e hash-bound; a execução v0.7.2 fez `sam2_runs=0`. Q0 passa alpha IoU `1.0`, RGB MAE `1.147443` e drift de bbox `0.0` px; K1–K4 passam QA affine, pairwise, topológica, retenção e MediaPipe.

O plano pairwise distingue sobreposição de junta, oclusão esperada, oclusão inesperada e colisão crítica. As quatro poses preservam hips distintos, arma no punho anatômico direito, margem segura de 24 px, overlays target/detected e evidência hash-bound em `docs/evidence/`.

## Evidence boundary

Pesos, bundle MediaPipe, source SAM2 e checkpoint continuam fora do Git e do review ZIP. A aprovação de produção e a aprovação externa não são inferidas. `walk_authorized=false` e `generation_provider_change_authorized=false` permanecem obrigatórios. O achado de falso positivo do v0.7.0 foi corrigido: métricas antes constantes agora são calculadas do output.

Animação genérica não autoriza execução nesta fase; walk, spritesheet e GIF continuam fora do escopo e não foram executados. O próximo passo autorizado é revisão visual externa, não um walk automático.
