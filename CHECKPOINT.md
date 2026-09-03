# UGAS checkpoint - v0.13.0

## v0.13.0 RUN_FRONT_V1

The active phase is RUN_FRONT_V1 and the gate is CUTOUT_ANIMATION_RUNTIME_V1_RUN_FRONT_TECHNICALLY_QUALIFIED. PR #2 was merged at the exact approved head and merge commit 0beb4c23604f1e45736c3082f99d2e08fa1ac308; the v0.12.4 completion remains immutable in docs/evidence/current-state-v0.12.4.json. The canonical capability matrix has CAPABILITY_COUNT=16 and next_candidate=RUN_FRONT_V1.

The only executed capability is the deterministic source-only front run: eight frames at 12 fps, looping, using the approved R4 cutout source, twelve declarative motion tracks, explicit contact/support/passing/flight markers, source-alpha foot grounding, root/body participation, arm-leg opposition, continuity and loop closure gates. All local gates and NC_01_TO_NC_08 passed; evidence is under docs/evidence/animation-runtime-v0130/. new_generation=0, production_approved=false, production_routing=BLOCKED, and external_visual=REQUIRED.

GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED, USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY, GITHUB_REVIEW_MODE=PR_FIRST, NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true, ALWAYS_ON_DASHBOARD_POLICY=ENABLED, and DOCKER_ALWAYS_ON_LOCAL are authoritative. The branch is codex/v0.13.0-run-front-v1 from post-merge main. The only allowed next action is external_visual_review_run_front_v1. Create a PR, wait for exact-head GitHub checks, leave it OPEN, and do not merge, enable production or start the next capability.

## Historical v0.12.4 GitHub CI and governance recovery

The active phase is `GITHUB_CI_GOVERNANCE_RECOVERY` and the gate is `GITHUB_CI_GOVERNANCE_RECOVERY_TECHNICALLY_QUALIFIED`: PR #2 is open at the reviewed head with all required GitHub checks green. It remains open for external Sol review and is not merged. The branch is `codex/v0.12.4-github-ci-governance-recovery` from remote main baseline `877ede34afadd631764887ad6c5fb941ca4371a8`. `GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED`, `USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY`, `GITHUB_REVIEW_MODE=PR_FIRST`, `NO_SELF_MERGE_UNTIL_EXTERNAL_APPROVAL=true`, `ALWAYS_ON_DASHBOARD_POLICY=ENABLED`, and `DOCKER_ALWAYS_ON_LOCAL` are authoritative.

PR #1 remains an immutable governance incident: v0.12.3 was merged before external approval while the real review workflow was red. The machine record is `docs/evidence/github-governance-v0124/pr1-premature-merge.json`. The dashboard decision is forward-only `observability_dashboard_external_visual=APPROVED_PILOT`, bound to the PR #1 artifact and the existing v0.12.2 source/transport hashes; it is visual/pilot approval only.

The only allowed next action is `external_review_github_ci_governance_v0124`; `RUN_FRONT_V1` remains the next necessary functional candidate but is not executed here. `production_approved=false`, `production_routing=BLOCKED` and `new_generation=0` remain authoritative. Do not directly modify `main`, rewrite PR #1 history, merge before explicit Sol approval, create assets, execute animation, enable production or migrate ComfyUI.

## Historical v0.12.2 QA cache integrity + Docker always-on local observability

## v0.12.2 QA cache integrity + Docker always-on local observability

The active increment is `LOCAL_ALWAYS_ON_OBSERVABILITY_DASHBOARD_TECHNICALLY_QUALIFIED`. It corrects the rejected v0.12.1 QA false-green path by binding each cache generation to the current HEAD, full worktree state and review artifact-set fingerprint; dirty/unreview-bound worktrees are GAP. Exact QA-NC-01..08 fixtures are executed, stale-last-known is proven through service/API collection, and generation stage telemetry is emitted through the production instrumentation boundary with a fake provider and no real generation. The dashboard observer runs in Docker with a read-only repository mount, writable shared `.ugas/runtime`, loopback-only host publication, bounded log rotation, non-root/no-socket security, restart policy, optional GPU override and host ComfyUI probing. `ALWAYS_ON_DASHBOARD_POLICY=ENABLED` is now mandatory for future executor rounds. The v0.11.2 external visual result remains `APPROVED_PILOT` for pilot/pipeline only; it is not production approval. `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, and external dashboard review remains `REQUIRED`. The only next action is `external_review_observability_dashboard_v0122`.

**STATUS:** `LOCAL_ALWAYS_ON_OBSERVABILITY_DASHBOARD_TECHNICALLY_QUALIFIED`
**VERSION:** `0.12.2`
**PHASE:** `LOCAL_REALTIME_OBSERVABILITY`
**RUNTIME_MODE:** `DOCKER_ALWAYS_ON_LOCAL`
**ALWAYS_ON_DASHBOARD_POLICY:** `ENABLED`

## Historical v0.12.1 rejected history

The v0.12.1 dashboard implementation and its evidence remain preserved as rejected history in `REVIEW-v0.12.1.md`, `docs/evidence/observability-v0121/`, `docs/evidence/current-state-v0.12.1.json` and `docs/evidence/review-index-v0.12.1.json`. The v0.12.2 correction does not rewrite those records.

## v0.12.1 observability integrity, security and live pipeline correction (rejected history)

The active increment is `LOCAL_REALTIME_OBSERVABILITY_DASHBOARD_MVP_TECHNICALLY_QUALIFIED`. It corrects only the rejected v0.12.0 local dashboard: unsafe HTML sinks are removed, QA is fail-closed, live workload stages and elapsed time are real, orphan jobs are reconciled, resource/process probes expose stale-last-known data honestly, file activity has a stable transition, and the v0.11.2 binding defect is superseded forward-only. The v0.11.2 external visual result remains `APPROVED_PILOT` for pilot/pipeline only; it is not production approval. The local dashboard remains read-only/local-only, with `production_approved=false` and `production_routing=BLOCKED`. The only next action is `external_review_observability_dashboard_v0121`; no new asset family, animation, generation job or remote telemetry is authorized.

**STATUS:** `LOCAL_REALTIME_OBSERVABILITY_DASHBOARD_MVP_TECHNICALLY_QUALIFIED`
**VERSION:** `0.12.1`
**PHASE:** `LOCAL_REALTIME_OBSERVABILITY`

## Historical v0.12.0 rejected history

The v0.12.0 dashboard implementation and its evidence remain preserved as rejected history. Its active state is retained in `docs/evidence/current-state-v0.12.0.json` with schema `schemas/current-state-v0.12.0.json`; the historical external binding `docs/evidence/observability-v0120/external-review-v0112.json` is not rewritten.

## Current state

The machine-authoritative active state is [docs/evidence/current-state.json](docs/evidence/current-state.json), and the v0.12.1 correction evidence is hash-bound by `docs/evidence/review-index-v0.12.1.json`.

### Historical v0.12.0 state record

**STATUS:** `LOCAL_REALTIME_OBSERVABILITY_DASHBOARD_MVP_TECHNICALLY_QUALIFIED`
**VERSION:** `0.12.0`
**PHASE:** `LOCAL_REALTIME_OBSERVABILITY`

O registro acima é histórico do v0.12.0 e não substitui o estado ativo v0.12.1. O piloto v0.8.1 corrige a integridade QA do mesmo cutout-rig R4 v0.7.1, core estrutural v0.7.3 e hashes K1–K4 imutáveis para oito frames front-walk. O v0.8.0 está preservado em snapshots versionados.

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
