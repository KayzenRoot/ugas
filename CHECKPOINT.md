# UGAS checkpoint - v0.7.0

**STATUS:** `CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP`
**VERSION:** `0.7.0`
**PHASE:** `DETERMINISTIC_CUTOUT_RIG_POSE_PROVIDER`

## Current state

O estado machine-authoritative está em [docs/evidence/current-state.json](docs/evidence/current-state.json). O cutout-rig R4 foi construído com SAM2.1 Hiera Small isolado, onze máscaras, manifest de hierarquia, Q0/Q1/Q2 estáticos e proveniência source-only. O resultado corrente é `CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP`; o review v0.6.2 permanece imutável.

O escopo atual não é geração: `deterministic-cutout-rig-2d` recebe somente o R4 RGBA canônico. Não houve job ComfyUI, fallback diffusion, SAM3 ou segmentação por frame. O provider não é roteado para produção enquanto Q1/Q2 não qualificarem.

## Scope and gate

SAM2 passou runtime/import/checkpoint/inference smoke. A segmentação alcançou cobertura semântica `0.957461`, overlap não resolvido `0.0` e pureza `1.0`. Q0 passou alpha IoU `1.0`, RGB MAE `0.373763` e drift de bbox `0.0` px.

Q1 passou a geometria interna e seam, mas falhou lower-body PCK (`0.666667`). Q2 falhou PCK (`0.692308`), NME (`0.100930`) e lower-body PCK (`0.5`). Os outputs e overlays estão hash-bound em `docs/evidence/`.

## Evidence boundary

Pesos, bundle MediaPipe, source SAM2 e checkpoint continuam fora do Git e do review ZIP. A aprovação de produção e a aprovação externa não são inferidas. `walk_authorized=false` e `generation_provider_change_authorized=false` permanecem obrigatórios.

Animação genérica não autoriza execução nesta fase; walk, spritesheet e GIF continuam fora do escopo e não foram executados. O próximo passo autorizado é revisão/reparo dos gates Q1/Q2, não um walk.
