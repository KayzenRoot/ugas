# UGAS checkpoint - v0.12.0

## v0.12.0 local realtime observability dashboard

The active increment is `LOCAL_REALTIME_OBSERVABILITY_DASHBOARD_MVP_TECHNICALLY_QUALIFIED`. The v0.11.2 external visual result is recorded as `APPROVED_PILOT` for pilot/pipeline only; it is not production approval. The local dashboard is read-only, local-only and near-real-time, with `production_approved=false` and `production_routing=BLOCKED`. It exposes canonical state, QA, system/GPU/process telemetry, jobs, allowlisted file activity, safe previews, bounded SQLite events and SSE. The next action is `external_review_observability_dashboard_v0120`; no new asset family or animation is authorized.

**STATUS:** `LOCAL_REALTIME_OBSERVABILITY_DASHBOARD_MVP_TECHNICALLY_QUALIFIED`
**VERSION:** `0.12.0`
**PHASE:** `LOCAL_REALTIME_OBSERVABILITY`

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

## v0.9.1 current checkpoint

UGAS v0.9.1 is the generic-runtime QA integrity correction over the immutable v0.9.0 implementation base `16c60c9ff934a55adefc82a99d81dafb52d1047c`, with parent baseline `46ba3ae87558ff26055e14aa8d9c6f3ee147333c`. The current gate remains `CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED`; `decision=QUALIFIED` is the package gate and profile-specific `status` is informational.

The timing schema accepts exactly one of `fps` or `per_frame_duration_ms`. The generic dummy two-key profile, v0.8.1 walk replay, and idle canonical replay pass. Idle QA measures dual-foot sole error, penetration, cyclic sole drift including I11→I0, ankle drift, head_bbox, torso_bbox, and measured occlusion policy. `sam2_runs=0`, `comfyui_generation_jobs=0`, `new_generation=0`, and `diffusion_runs=0`.

Production remains `production_routing=BLOCKED`; external idle review is `REQUIRED` and not-claimed. The only allowed next action is `external_review_idle_front`. The v0.9.1 review index v2 records baseline/base separately and requires the external reviewer to resolve final HEAD; the executor cannot self-assert that final HEAD.

## v0.10.0 current checkpoint

UGAS v0.10.0 is the generic action-runtime attack-front slice from the approved public v0.9.1 SHA `d914d09d35ebfc5658d6c08e3502288c537fbf20`. It adds optional hash-bound `event_markers[]`, generic loop/non-loop lifecycle rules, and only `attack-front-v1`: front, 10 frames, 12 fps, non-loop, sword, source-R4 skeleton targets, deterministic Pillow/source pixels, and frozen A0–A9 phases.

The attack pilot is locally `CUTOUT_ANIMATION_RUNTIME_V1_ATTACK_FRONT_TECHNICALLY_QUALIFIED` with `decision=QUALIFIED`. All 10 target hashes are distinct; temporal, weapon sweep, hit frame 5, active window 3–6, sequential foot-ground, structural/occlusion, retention, alpha-margin, source-hash, and independent MediaPipe gates pass. The package is 5x2 at 512x512 cells, RGBA, and carries event markers through manifest, QA, metadata, and package.

Historical `walk_front_v081_external_visual=APPROVED_PILOT` and `idle_front_v1_external_visual=APPROVED_PILOT` are recorded without changing their pixels. Attack external visual review is `REQUIRED`; `production_approved=false`, `production_routing=BLOCKED`, `sam2_runs=0`, `comfyui_generation_jobs=0`, `diffusion_runs=0`, and `new_generation=0`. The only allowed next action is `external_review_attack_front`; run/hit/death, other directions, new providers, rig/mask changes, and production routing remain forbidden.

## v0.11.0 current checkpoint

UGAS v0.11.0 adds the generic `motion_tracks[]` quality layer between Animation Spec and adapter, with deterministic scalar/vec2 sampling, linear/smoothstep/cubic-Hermite interpolation, finite-value validation, explicit clamp-only out-of-range policy, and hash binding through compiled manifest, QA, metadata and package. The only newly executed subject is `attack-front-v2`: front, 12 frames, 12 fps, non-loop, sword, source-only R4 targets, frozen markers `windup_peak=3`, `active_start=4`, `hit_event=6`, `active_end=7`, and `recovery_complete=11`.

The v2 technical gate is `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED`; all 12 frames, temporal mechanics, weapon arc, planted feet, structural/occlusion, retention, alpha margin, source hashes and independent MediaPipe metrics pass. The v0.10.0 attack-front-v1 spritesheet/GIF/frames and the canonical v0.8.1 walk and v0.9.0 idle fixtures replay byte-identically. `motion_tracks_sha256` is bound in all v2 artifacts. `attack_front_v2_external_visual=REQUIRED`, `production_approved=false`, `production_routing=BLOCKED`, `sam2_runs=0`, `comfyui_generation_jobs=0`, `diffusion_runs=0`, and `new_generation=0`. The only allowed next action is `external_review_attack_front_v2`; no run/hit/death, other direction, provider, rig/mask, manual-pixel or production changes are authorized.

## v0.11.1 rejected history

UGAS v0.11.1 is the corrective slice over the immutable public v0.11.0 implementation base `9401c31f994e968149292b2993d960d3aafc37c4`. It corrects only the false-green weapon follow-through/recovery of the same `attack-front-v2`; the generic motion curve layer, R4 rig, masks, body mechanics, foot balance, historical fixtures and thresholds remain unchanged.

The pre-render weapon proxy passes before the first PNG: post-hit follow-through is `17.030469 px`, follow ratio is `0.151858`, velocity retention is `0.367714`, and maximum absolute weapon acceleration is `9.655555 deg/frame²`. Post-render recomputation agrees within `0.001`; V11 sword angle delta is `4.0°`, tip distance is `12.811845 px`, and all recovery gates pass. All required negative controls reject, including the v0.11.0 false-green shape. The package remains source-only, front, 12 frames, non-loop, RGBA, and technically qualified.

The v0.11.1 externally rejected state is preserved unchanged in `current-state-v0.11.1.json`, `REVIEW-v0.11.1.md` and `docs/evidence/animation-runtime-v0111/`. It is not the active status.

## v0.11.2 current checkpoint

UGAS v0.11.2 is the QA integrity and scope recovery correction over HEAD `f386c490a6d7289befc1c8a34c84eff1d2b1cc96`. It restores `motion_tracks` and `key_pose_bindings` exactly from v0.11.0, migrates the unchanged body-mechanics literals into semantic declared thresholds, and makes the attack-v1 comparison fail-closed with a known path, authority commit and immutable SHA-256. The v0.11.1 rejected history is preserved and not rewritten.

The weapon QA uses one unwrapped angular reference for every continuity delta, relational active-vs-pre-active speed, coherent pre-hit acceleration and immediate post-hit same-sign follow-through. NC-01..NC-10 all pass as negative controls. No animation, markers, rig, masks, source skeleton, z-order, pixels or provider was changed; `new_generation=0`, `sam2_runs=0`, `comfyui_generation_jobs=0`, and `diffusion_runs=0`.

The active state is `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED` with `decision=QUALIFIED`, `attack_front_v2_external_visual=REQUIRED`, `production_approved=false`, and `production_routing=BLOCKED`. Historical `walk_front_v081_external_visual=APPROVED_PILOT`, `idle_front_v1_external_visual=APPROVED_PILOT`, and `attack_front_v1_external_visual=APPROVED_PILOT` remain historical decisions. `REVIEW_INDEX_VERIFIED` is local evidence only, not external approval. The only allowed next action is `external_review_attack_front_v2_v0112`; no run, hit, death, other direction, provider, rig/mask, manual-pixel or production change is authorized.
