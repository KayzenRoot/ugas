# UGAS checkpoint - v0.6.2

**STATUS:** `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`
**VERSION:** `0.6.2`
**PHASE:** `SDXL_OPENPOSE_MODEL_CARD_CALIBRATION`

## Current state

O estado machine-authoritative está em [docs/evidence/current-state.json](docs/evidence/current-state.json). A calibração P-only foi concluída: P0, P1 e P2 executaram com geração fresca, sem OOM, e nenhum passou o Stage A. O resultado corrente é `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`. O review v0.6.1 permanece imutável; os modelos, hashes, pin do IP-Adapter, R4, MediaPipe QA e thresholds permanecem preservados.

O escopo de geração é somente P-only: SDXL Base 1.0 + xinsir OpenPose ControlNet. A matriz autorizada é P0/P1/P2 com a seed 62701. IP-Adapter, I/PI, benchmark, anchors, walk, spritesheet, GIF e novo provider permanecem proibidos.

## Scope and gate

P0 reproduz o baseline 512x512, 20 steps, Euler/normal e strength 0.9. P1 usa 768x768, 30 steps, Euler Ancestral semanticamente mapeado para os valores válidos do `object_info` real e strength 1.0. P2 usa 1024x1024, 30 steps, a mesma equivalência e strength 1.0.

O PNG de controle é renderizado diretamente do JSON COCO-18 em cada resolução, sem upscale raster. Raw pose QA ocorreu antes de qualquer diagnóstico opcional de pós-processamento. P2 completou normalmente e não exigiu retry. Os três outputs e overlays estão hash-bound em `docs/evidence/sdxl-openpose-calibration/`.

## Evidence boundary

Pesos, bundle MediaPipe e source GPL continuam fora do Git e do review ZIP. A aprovação de produção e a aprovação externa não são inferidas. `walk_authorized=false` e `generation_provider_change_authorized=false` permanecem obrigatórios.

Animação genérica não autoriza execução nesta fase; walk, spritesheet e GIF continuam fora do escopo e não foram executados. Confirmation também permaneceu `NOT_RUN`, pois nenhuma configuração passou Stage A.
