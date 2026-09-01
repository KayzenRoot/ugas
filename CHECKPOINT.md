# UGAS checkpoint - v0.8.1

**STATUS:** `CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED`
**VERSION:** `0.8.1`
**PHASE:** `DETERMINISTIC_FRONT_WALK_8FRAME_PILOT`

## Current state

O estado machine-authoritative está em [docs/evidence/current-state.json](docs/evidence/current-state.json). O piloto v0.8.1 corrige a integridade QA do mesmo cutout-rig R4 v0.7.1, core estrutural v0.7.3 e hashes K1–K4 imutáveis para oito frames front-walk. O v0.8.0 está preservado em snapshots versionados.

O escopo é somente o piloto determinístico front/walk/8: `deterministic-cutout-rig-2d` recebe o R4 RGBA canônico e as partes v0.7.1; intermediários são skeletons Hermite projetados, não pixels interpolados. `sam2_runs=0`, `comfyui_generation_jobs=0` e `production_routing=BLOCKED`.

## Scope and gate

O baseline SAM2/runtime/checkpoint é histórico e hash-bound. Os oito frames passam core estrutural, integridade de camadas, pairwise, topologia, retenção, MediaPipe, temporal estrito, sola visível/solo projetado, half-cycle e loop; sprite/metadata/GIF foram produzidos somente após os gates.

O plano pairwise distingue sobreposição de junta, oclusão esperada, oclusão inesperada e colisão crítica, sempre contra regiões geométricas explícitas. As quatro poses preservam hips distintos, arma no punho anatômico direito, overlays target/detected e evidência hash-bound em `docs/evidence/`. Os buracos cintura/cinto/pelve rejeitados na auditoria v0.7.2 não reaparecem.

## Evidence boundary

Pesos, bundle MediaPipe, source SAM2 e checkpoint continuam fora do Git e do review ZIP. A aprovação de produção e a aprovação externa não são inferidas: `walk_authorized=pilot_only`, `production_walk_authorized=false`, `external_approval=not-claimed`. O próximo passo único é `external_review_front_walk_cycle`.

Animação genérica não autoriza execução: somente `WALK FRONT` neste piloto foi executado. Direções e animações diferentes continuam fora do escopo; o próximo passo autorizado é revisão visual externa, não promoção para produção.
## v0.9.0 current checkpoint

UGAS v0.9.0 is in `REUSABLE_DETERMINISTIC_ANIMATION_RUNTIME` with current gate `CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED`. The v0.8.1 walk decision `FRONT_WALK_V081_PILOT_VISUAL_APPROVED` is `APPROVED_PILOT` for pipeline/pilot only; production routing is `BLOCKED`, and external idle review is `REQUIRED`.

`sam2_runs=0` and `comfyui_generation_jobs=0`; no-claim status is `not-claimed` for production. The generic runtime may only proceed to `external_review_idle_front`; no other animation or direction is authorized.
