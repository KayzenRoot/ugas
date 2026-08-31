# UGAS checkpoint - v0.7.1

**STATUS:** `CUTOUT_RIG_SEAM_GAP`
**VERSION:** `0.7.1`
**PHASE:** `DETERMINISTIC_CUTOUT_RIG_POSE_PROVIDER`

## Current state

O estado machine-authoritative está em [docs/evidence/current-state.json](docs/evidence/current-state.json). O cutout-rig R4 foi corrigido com SAM2.1 Hiera Small isolado, onze máscaras raw/refined, manifest de hierarquia, Q0/Q1/Q2 estáticos, matrizes affine forward e proveniência source-only. O resultado corrente é `CUTOUT_RIG_SEAM_GAP`; o review v0.7.0 e o review v0.6.2 permanecem imutáveis.

O escopo atual não é geração: `deterministic-cutout-rig-2d` recebe somente o R4 RGBA canônico. Não houve job ComfyUI, fallback diffusion, SAM3 ou segmentação por frame. O provider não é roteado para produção enquanto Q1/Q2 não qualificarem.

## Scope and gate

SAM2 passou runtime/import/checkpoint/inference smoke. A segmentação final usa ownership semântico completo, sem fallback residual. Q0 passa alpha IoU `1.0`, RGB MAE `1.147443` e drift de bbox `0.0` px; a QA interna affine passa.

Q1/Q2 têm hips distintos, arma lateral dentro do corredor protegido e overlays target/detected reais, mas a seam QA registra overlap fora das juntas (`2222` Q1; `4477` Q2) e Q2 tem retenção total `0.854145` com coxa direita `0.710917`. Os outputs e overlays estão hash-bound em `docs/evidence/`.

## Evidence boundary

Pesos, bundle MediaPipe, source SAM2 e checkpoint continuam fora do Git e do review ZIP. A aprovação de produção e a aprovação externa não são inferidas. `walk_authorized=false` e `generation_provider_change_authorized=false` permanecem obrigatórios. O achado de falso positivo do v0.7.0 foi corrigido: métricas antes constantes agora são calculadas do output.

Animação genérica não autoriza execução nesta fase; walk, spritesheet e GIF continuam fora do escopo e não foram executados. O próximo passo autorizado é revisão/reparo dos gates Q1/Q2, não um walk.
