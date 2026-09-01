# UGAS checkpoint - v0.8.1 / v0.9.1 historical snapshot

**STATUS:** `CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED`
**VERSION:** `0.8.1`
**PHASE:** `DETERMINISTIC_FRONT_WALK_8FRAME_PILOT`

## Historical current state

O estado machine-authoritative está em `docs/evidence/current-state.json`. O piloto v0.8.1 corrige a integridade QA do mesmo cutout-rig R4 v0.7.1, core estrutural v0.7.3 e hashes K1–K4 imutáveis para oito frames front-walk. O v0.8.0 está preservado em snapshots versionados.

O escopo histórico é somente o piloto determinístico front/walk/8: `deterministic-cutout-rig-2d` recebe o R4 RGBA canônico e as partes v0.7.1; intermediários são skeletons Hermite projetados, não pixels interpolados. `sam2_runs=0`, `comfyui_generation_jobs=0` e `production_routing=BLOCKED`.

## Historical evidence boundary

Pesos, bundle MediaPipe, source SAM2 e checkpoint continuam fora do Git e do review ZIP. A aprovação de produção e a aprovação externa não são inferidas: `walk_authorized=pilot_only`, `production_walk_authorized=false`, `external_approval=not-claimed`. O próximo passo único foi `external_review_front_walk_cycle`.

Animação genérica não autorizava execução: somente `WALK FRONT` no piloto foi executado. Direções e animações diferentes permaneciam fora do escopo.

## v0.9.0 historical current checkpoint

UGAS v0.9.0 estava em `REUSABLE_DETERMINISTIC_ANIMATION_RUNTIME` com current gate `CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED`. A decisão v0.8.1 era `APPROVED_PILOT` para pipeline/piloto; production routing era `BLOCKED`, e external idle review era `REQUIRED`.

`sam2_runs=0` e `comfyui_generation_jobs=0`; o status de produção era `not-claimed`. O runtime genérico só podia prosseguir para `external_review_idle_front`; nenhuma outra animação ou direção era autorizada.

## v0.9.1 historical current checkpoint

UGAS v0.9.1 era a correção de integridade QA do generic runtime sobre a base imutável v0.9.0. O current gate permanecia `CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED`; `decision=QUALIFIED` era o package gate e o `status` específico do perfil era informativo.

O timing aceitava exatamente um de `fps` ou `per_frame_duration_ms`. O generic dummy de duas chaves, o replay v0.8.1 walk e o replay idle canônico passavam. Idle QA media sole error dual-foot, penetration, cyclic sole drift, ankle drift, `head_bbox`, `torso_bbox` e measured occlusion policy. `sam2_runs=0`, `comfyui_generation_jobs=0`, `new_generation=0` e `diffusion_runs=0`.

Production permanecia `production_routing=BLOCKED`; external idle review era `REQUIRED` e não reivindicado. A única ação seguinte permitida era `external_review_idle_front`.
