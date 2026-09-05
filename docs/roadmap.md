# UGAS roadmap

## v0.19.0 - ITEMS_PROPS runtime foundation / external review required

The active phase is `ITEMS_PROPS` and the gate is `ITEMS_PROPS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED`. The v0.18.2 creatures/monsters runtime foundation is `APPROVED_FOUNDATION` at merge `52938a04016352d50ad54621a4df981a9c36b058`; the v0.19.0 branch is `codex/v0.19.0-items-props-runtime-foundation`, based on that exact main head, with PR #9 open. `creatures_monsters=APPROVED_FOUNDATION`; `items_props_runtime=TECHNICALLY_QUALIFIED_FOUNDATION`; `real_item_prop_asset_coverage=NONE`; `synthetic_item_prop_fixture=TEST_ONLY`; `production_approved=false`; `production_routing=BLOCKED`; `new_generation=0`; `allowed_next_actions=[external_review_items_props_v0190]`; `next_capability_started=false`. The six item/prop classes, explicit representation contract, geometry/anchors, stack identity, derived variant lineage, equipment identity, cache isolation, provenance, negative controls, TEST_ONLY fixtures and isolated determinism are validated locally. The only next action is external review of PR #9; do not merge it and do not start environment/tilesets, maps/minimap, UI, VFX or orchestration hardening.

Historical v0.16.2 governance remains immutable and explicitly bound: `multi_direction_animation_runtime=APPROVED_FOUNDATION`, `real_directional_character_asset_coverage=SOUTH_ONLY`, `pr_number=6`, `pr_state=OPEN`, `governed_merge_pr_6`, `previous_release=0.15.1`, and `Merge after recorded external approval and exact post-bookkeeping reproof`.

## Historical v0.18.2 - CREATURES_MONSTERS derived variant + state contract integrity / external review required

The active phase is `CREATURES_MONSTERS` and the gate is `CREATURES_MONSTERS_DERIVED_VARIANT_AND_STATE_CONTRACT_TECHNICALLY_QUALIFIED`. This forward-only correction stays on PR #8 and branch `codex/v0.18.0-creatures-monsters-runtime-foundation`, based on `39e148bef50c8f04db194048dbe9fbb15d8ff3d4`; rejected v0.18.1 head `b52dc26d935fd84b25a991ae81c5d508b0a39807` remains frozen history. Effective derived variants are validated after materialization; `variant_revision` is separate from inherited directional `asset_revision`; mixed direction revisions reject; moving archetypes require locomotion and stationary structures reject it. `equipment_outfits=APPROVED_FOUNDATION`, `v0181_external_review=CORRECTION_REQUIRED`, `real_creature_asset_coverage=NONE`, `synthetic_creature_fixture=TEST_ONLY`, `production_approved=false`, `production_routing=BLOCKED`, and `new_generation=0`. The only next action is `external_review_creatures_monsters_v0182`; Items/Props remains forbidden and PR #8 must stay open/unmerged.

## Historical v0.18.0 - CREATURES_MONSTERS runtime foundation / correction required

## v0.18.1 - CREATURES_MONSTERS runtime QA integrity correction / external review required

The active phase is `CREATURES_MONSTERS` and the gate is `CREATURES_MONSTERS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED`. This forward-only correction remains on PR #8 and branch `codex/v0.18.0-creatures-monsters-runtime-foundation`, based on `39e148bef50c8f04db194048dbe9fbb15d8ff3d4`, while reviewed v0.18.0 head `bed13772bef984727e9b38037f59b61f1ba05080` remains immutable `CORRECTION_REQUIRED` history. Direction bindings now carry unique 8-way asset IDs/content hashes, state routes carry exact route IDs and timing/phase metadata, derived variants are operational, collision geometry is strict, CR-NC-01..15 are semantic fail-closed controls, and determinism uses isolated runs. `equipment_outfits=APPROVED_FOUNDATION`, `v0180_external_review=CORRECTION_REQUIRED`, `real_creature_asset_coverage=NONE`, `synthetic_creature_fixture=TEST_ONLY`, `production_approved=false`, `production_routing=BLOCKED`, and `new_generation=0`. The only next action is `external_review_creatures_monsters_v0181`; Items/Props remains forbidden and the PR must stay open/unmerged.

The active phase is `CREATURES_MONSTERS` and the gate is `CREATURES_MONSTERS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED`. It is based on merged v0.17.1 main commit `39e148bef50c8f04db194048dbe9fbb15d8ff3d4`, on branch `codex/v0.18.0-creatures-monsters-runtime-foundation`. The implementation is generic and separate from equipment/direction: six archetypes have explicit topology, locomotion, support, rig family, scale, footprint, collision, pivot, bounds, anchors, canonical states, provenance and TEST_ONLY boundaries. Direction IDs reuse v0.16.2; no real creature direction coverage is claimed. `real_creature_asset_coverage=NONE`, `synthetic_creature_fixture=TEST_ONLY`, `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, and `items_props` remains forbidden. The only next action is `external_review_creatures_monsters_v0180`; the PR remains open and must not be merged before external review.

## v0.17.1 - EQUIPMENT_OUTFITS approved foundation / governed merge authorized

The active gate is `EQUIPMENT_OUTFITS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED`, based on merged v0.16.2 commit `a8d2897211c4b72c2cd2fe7a7f5729c7009d8566`. Sol recorded `APPROVED_FOUNDATION / APPROVED_TO_MERGE` for exact head `98ea74e91e18dfee32c583df005e151e13d6e9f7`; the forward-only record is `docs/evidence/github-governance-v0180/v0171-external-approval.json`, and the only allowed next action is `governed_merge_pr_7` after post-bookkeeping exact-head reproof. The v0.17.0 candidate was rejected at reviewed head `1c73e6a2ff5259226afe9ca03ef10e1822a7fdf2` and remains frozen history. This correction implements deterministic modular wearable composition over the approved R4 rig and front animation frames, including executed replacement winner/hide semantics, actual hashed asset-bound masks, strict negative controls and non-destructive determinism. Missing directions, mirror without implemented pixel operation, and declared secondary anchors fail closed. `equipment_outfits=APPROVED_FOUNDATION`, `multi_direction_animation_runtime=APPROVED_FOUNDATION`, `real_directional_character_asset_coverage=SOUTH_ONLY`, `real_equipment_asset_coverage=NONE_OR_EXPLICITLY_APPROVED_ONLY`, `synthetic_equipment_fixture=TEST_ONLY`, `production_approved=false`, `production_routing=BLOCKED`, and `new_generation=0`. The production registry is empty. Do not start creatures/monsters or downstream capabilities before the governed merge.

## v0.16.2 - MULTI_DIRECTION_ANIMATION_RUNTIME cache and state integrity correction approved foundation / governed merge (active: MULTI_DIRECTION_ANIMATION_RUNTIME)

The active phase is MULTI_DIRECTION_ANIMATION_RUNTIME and the gate is MULTI_DIRECTION_ANIMATION_RUNTIME_CACHE_AND_STATE_INTEGRITY_TECHNICALLY_QUALIFIED. The correction preserves the canonical eight directions, deterministic aliases/vector sectors, direction-aware identity, strict invalid-vector outcomes and truthful resolver evidence while adding unresolved-class cache isolation and truthful request/registry cache modes. multi_direction_animation_runtime=APPROVED_FOUNDATION; real_directional_character_asset_coverage=SOUTH_ONLY; death_animation_front=APPROVED_PILOT; hit_reaction_front=APPROVED_PILOT; run_front_v1=APPROVED_PILOT. The six approved front profiles map `front` to `south` without byte or source-hash changes. Missing directions fail closed; preview fallback and mirror are explicit non-production modes. TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE is review-only. The v0.16.0 and v0.16.1 records are CORRECTION_REQUIRED, while previous_release=0.15.1 remains the last approved release. production_routing=BLOCKED, new_generation=0, production_approved=false. GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED, USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY, GITHUB_REVIEW_MODE=PR_FIRST, NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true, ALWAYS_ON_DASHBOARD_POLICY=ENABLED and DOCKER_ALWAYS_ON_LOCAL remain binding. Sol recorded APPROVED_FOUNDATION / APPROVED_TO_MERGE for reviewed head 2864b8ca392725b6da0616916ef3a3c38ce0a0d6. The active repository is KayzenRoot/ugas and PR #6 has pr_number=6, pr_state=OPEN, real_pr_checks_green=true, merge_authorization=APPROVED_TO_MERGE. The only next action is governed_merge_pr_6; next_candidate=EQUIPMENT_OUTFITS and next_capability_started=false. Merge after recorded external approval and exact post-bookkeeping reproof. Do not start equipment/outfits before the governed merge.

## Historical v0.15.1 - DEATH_ANIMATION_FRONT approved pilot / merged

Sol approved exact reviewed head 1ddcdf3b9bf44b390af549c00a0553b850c71976 as APPROVED_PILOT / APPROVED_TO_MERGE. PR #5 merged through the protected GitHub path at 514a17818469b567966293db808cafbf708f8311. The rejected v0.15.0 history remains immutable.

## Historical v0.15.0 - rejected reviewed DEATH_ANIMATION_FRONT

The v0.15.0 death slice and its rejected reviewed head remain frozen under `REVIEW-v0.15.0.md` and `docs/evidence/animation-runtime-v0150/`. The v0.15.1 correction is forward-only.

## Historical v0.14.1 - HIT_REACTION_FRONT package integrity

## Historical v0.14.0 - HIT_REACTION_FRONT technically qualified

Execute only HIT_REACTION_FRONT after the governed 0.13.1 merge. The active gate is CUTOUT_ANIMATION_RUNTIME_V1_HIT_REACTION_FRONT_TECHNICALLY_QUALIFIED. Six source-only front frames at 12 fps, non-looping, dual-foot planted, unique recoil peak at H2, recovery at H5. run_front_v1=APPROVED_PILOT remains bound to f3d68faa5524392e66aee2fc2a450b9da8fa734b. hit_reaction_front=REQUIRED. CAPABILITY_COUNT=16, next_candidate=HIT_REACTION_FRONT, production_routing=BLOCKED, new_generation=0, production_approved=false. The branch codex/v0.14.0-hit-reaction-front is GitHub-first: open a PR from post-merge main, require exact-head success for UGAS CI / unit-and-validation, UGAS CI / docker-smoke and UGAS Review / evidence, then leave the PR OPEN for external_visual_review_hit_reaction_front. GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED, USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY, NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true, ALWAYS_ON_DASHBOARD_POLICY=ENABLED and DOCKER_ALWAYS_ON_LOCAL remain binding. Do not merge. No production enablement or DEATH_ANIMATION_FRONT is authorized.

## Historical v0.13.1 - RUN_FRONT_V1 approved pilot / APPROVED_TO_MERGE

Sol external review recorded run_front_v1=APPROVED_PILOT and APPROVED_TO_MERGE for PR #3 at exact head f3d68faa5524392e66aee2fc2a450b9da8fa734b. The technical gate remains CUTOUT_ANIMATION_RUNTIME_V1_RUN_FRONT_TECHNICALLY_QUALIFIED. The last approved release is 0.12.4; v0.13.0 is a rejected historical attempt. CAPABILITY_COUNT=16, next_candidate=HIT_REACTION_FRONT, production_routing=BLOCKED, new_generation=0, production_approved=false. GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED, USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY, NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true, ALWAYS_ON_DASHBOARD_POLICY=ENABLED and DOCKER_ALWAYS_ON_LOCAL remain binding. After the governed merge of PR #3 the only allowed next action is hit_reaction_front. No production enablement or DEATH_ANIMATION_FRONT is authorized.

## Historical v0.13.1 - RUN_FRONT_V1 flight/QA visual integrity

Correct the rejected v0.13.0 front run without merging PR #3. The active gate is CUTOUT_ANIMATION_RUNTIME_V1_RUN_FRONT_TECHNICALLY_QUALIFIED. Keep RUN_FRONT_V1 as eight source-only front frames at 12 fps with twelve declarative motion tracks, real airborne frames 3 and 7, immutable-base approved-asset identity, and decoded GIF timing. CAPABILITY_COUNT=16, production_routing=BLOCKED, new_generation=0, production_approved=false, and external_visual=REQUIRED. The branch codex/v0.13.0-run-front-v1 remains GitHub-first: update PR #3 from post-merge main 0beb4c23604f1e45736c3082f99d2e08fa1ac308, require exact-head success for UGAS CI / unit-and-validation, UGAS CI / docker-smoke and UGAS Review / evidence, then leave the PR OPEN for external_visual_review_run_front_v1. GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED, USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY, NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true, ALWAYS_ON_DASHBOARD_POLICY=ENABLED and DOCKER_ALWAYS_ON_LOCAL remain binding. No production enablement or next capability is authorized.

## Historical v0.13.0 - RUN_FRONT_V1

After merge PR #2 at exact approved head, reread the canonical matrix and execute only its next_candidate RUN_FRONT_V1. The source-only deterministic increment is eight front-facing frames at 12 fps with twelve declarative motion tracks and explicit contact/support/passing/flight phases. CAPABILITY_COUNT=16, production_routing=BLOCKED, new_generation=0, production_approved=false, and external_visual=REQUIRED. The branch codex/v0.13.0-run-front-v1 is GitHub-first: create a PR from post-merge main, require exact-head success for UGAS CI / unit-and-validation, UGAS CI / docker-smoke and UGAS Review / evidence, then leave the PR OPEN for external visual review. GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED, USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY, NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true, ALWAYS_ON_DASHBOARD_POLICY=ENABLED and DOCKER_ALWAYS_ON_LOCAL remain binding. No production enablement or next capability is authorized. External review rejected this slice; it remains frozen historical evidence.

## Historical v0.12.4 - GitHub CI and governance recovery

Recover GitHub-first development after the premature v0.12.3 merge. Start from remote main `877ede34afadd631764887ad6c5fb941ca4371a8` on a new corrective branch, fix the three real historical snapshot/no-git validation defects, prove stable PR-triggered `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke` and `UGAS Review / evidence` checks, and leave corrective PR #2 open without merge. Record the immutable PR #1 incident, record `observability_dashboard_external_visual=APPROVED_PILOT` bound to the existing artifact/visual hashes, configure and read back the active main protection ruleset, and keep the local Docker dashboard online under `DOCKER_ALWAYS_ON_LOCAL`. `GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED`, `USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY`, `NO_SELF_MERGE_UNTIL_EXTERNAL_APPROVAL=true`, `ALWAYS_ON_DASHBOARD_POLICY=ENABLED`, `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, and `RUN_FRONT_V1` remain outside this slice. The gate is technically qualified; the only next action is `external_review_github_ci_governance_v0124`.

## Historical v0.12.2 - QA cache integrity and Docker always-on local observability

Correct the rejected v0.12.1 QA cache false-green path, execute exact QA-NC-01..08 fixtures, prove stale-last-known through the service/API collector path and bind generation stages to real instrumentation with a fake provider. Operationalize only the dashboard observer in Docker: read-only repository mount, writable shared SQLite runtime, loopback-only publication, restart policy, optional GPU override, host ComfyUI endpoint, persistence, file watching, cross-process telemetry and reversible per-user autostart. Keep production blocked, no new asset family, no animation changes, no real generation and no remote telemetry; stop for external visual review at `external_review_observability_dashboard_v0122`. `ALWAYS_ON_DASHBOARD_POLICY=ENABLED` applies to future executor rounds.

## Historical v0.12.1 - observability integrity, security and live pipeline correction (rejected history)

Correct only the rejected v0.12.0 dashboard: remove unsafe HTML sinks, make QA fail-closed, expose real workload stages and elapsed time, reconcile orphan jobs, show UGAS/GPU-process/ComfyUI state, preserve stale-last-known samples, emit stable file transitions, correct preview semantics and supersede the defective v0.11.2 binding forward-only. Preserve v0.12.0 evidence, keep the dashboard local-only/read-only, keep `production_approved=false` and `production_routing=BLOCKED`, and wait for `external_review_observability_dashboard_v0121`. No new asset family, animation edit, generation job or remote telemetry is authorized.

## Historical v0.12.0 - local realtime observability dashboard MVP (rejected history)

Add a local-only, read-only, near-real-time operations dashboard launched by `ugas dashboard`. Keep SQLite telemetry bounded, stream events with SSE, sample CPU/RAM/disk/GPU/process state with explicit unsupported fallbacks, watch only approved UGAS roots, and surface canonical state/QA/review evidence without replacing it. Record the v0.11.2 external decision as `APPROVED_PILOT`, keep `production_approved=false` and `production_routing=BLOCKED`, and wait for `external_review_observability_dashboard_v0120`. No new asset family, animation edit, generation job or remote telemetry is authorized.

## v0.11.2 - QA integrity and scope recovery correction

Recover the active QA scope after the rejected v0.11.1 correction. Restore v0.11.0 `motion_tracks` and `key_pose_bindings` exactly, bind body gates to declared semantic thresholds, require fail-closed attack-v1 comparison, use relational weapon-arc gates, and qualify NC-01..NC-10. Preserve rejected v0.11.1 history, prove byte-identical pixels/package to v0.11.0, require external visual review, and keep production routing blocked.

## v0.11.1 - rejected weapon continuity recovery correction (historical)

The v0.11.1 implementation and review evidence are preserved as rejected history. v0.11.2 does not rewrite, squash, delete or treat that correction as the active scope.

## v0.11.0 - generic motion quality layer and attack-front-v2 (historical)

Add optional opaque `motion_tracks[]` between the animation spec and adapter, deterministic scalar/vec2 interpolation, curve hashing, pre-render temporal/body mechanics, and a 12-frame source-only frontal sword attack. Preserve v0.10.0 attack-front-v1 plus v0.8.1 walk and v0.9.0 idle byte-identically. Technical qualification is local; external visual review is required and production routing remains blocked. The v0.11.0 result is preserved as the immutable restoration baseline.

## v0.8.1 - front-walk QA integrity correction

The same v0.8.0 front-walk cycle now has strict visible-sole/ground, actual-alpha, pre-render smoothing, temporal, z-order, and hash-bound review gates. Technical qualification is local and pilot-only; production routing remains blocked pending external visual review.

## v0.8.0 - deterministic front-walk 8-frame pilot (historical)

The active slice is a single front-facing walk cycle with exactly eight deterministic frames. F0/F2/F4/F6 bind to the immutable v0.7.3 K1-K4 joint hashes; intermediate targets use frozen cubic Hermite skeleton interpolation and source-calibrated bone projection. Pillow transforms source pixels only. The technical result is `CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED`; external visual review is required, `walk_authorized=pilot_only`, and `production_routing=BLOCKED`.

No other animation or direction is authorized. `sam2_runs=0`, `comfyui_generation_jobs=0`, and `new_generation_jobs=0`. The next action is `external_review_front_walk_cycle`; external approval is `not-claimed`.

## v0.7.3 - deterministic cutout-rig structural coverage correction

Correct the v0.7.2 externally rejected transparent waist/belt/pelvis holes with a source-derived structural core, independent layer-integrity area, explicit phase geometry, pairwise overlap V3, owner displacement diagnostics and Q0/K1–K4 requalification. The technical gate is `CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED`; external visual review remains required and walk is not authorized.

## v0.7.2 - historical deterministic cutout-rig occlusion/gait qualification

Qualified the v0.7.1 correction with a hash-bound pairwise occlusion plan, topological seam continuity, retention/occlusion provenance, four front-walk key poses, MediaPipe QA and half-cycle structure. External visual review later rejected real structural transparency holes; that result is immutable history and v0.7.3 corrects it.

## v0.7.1 - historical deterministic cutout-rig fidelity QA correction

Corrected the v0.7.0 false-green anatomy, segmentation, residual fallback, component, affine-geometry and seam QA paths. Its measured `CUTOUT_RIG_SEAM_GAP` result is preserved as immutable history.

## v0.6.2 - historical SDXL OpenPose model-card calibration

Preserve raw generation evidence before BiRefNet, render the model-card guides directly at 512/768/1024, and run raw pose QA for P0/P1/P2. The completed calibration stopped at `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`; confirmation, identity R4, benchmark, walk and anchors were not run.

## v0.6.0 - SDXL ControlNet/IP-Adapter provider qualification

O operating point xinsir foi testado somente na lane P: P0 512/20/Euler/0.9, P1 768/30/Euler Ancestral/1.0 e P2 1024/30/Euler Ancestral/1.0. O resultado atual é `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`; IP-Adapter, I/PI, benchmark, confirmation, walk e routing SDXL permanecem bloqueados.

## v0.5.5 - review snapshot integrity

Corrige o falso positivo de `seed` no empacotador local, adiciona regras de filename ancoradas e um verificador tracked que executa a suíte dentro da extração limpa. Os 9 outputs A/C/R e a decisão de pose v0.5.4 permanecem intactos. Nenhum job GPU foi executado.

## v0.5.4 - historical provider lane recheck

O estimador MediaPipe foi qualificado de modo independente com uma política global, license evidence oficial para QA local, detectabilidade histórica e sanity visual. O recheck autorizado executou A/C/R em 9 outputs frescos. O estado final é `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`: C/R não passaram pose por junta, embora identidade/arma tenham passado.

## v0.5.3 - historical corrective slice

Calibrou detected-joint pose error, corrigiu o gate causal impossível e parou em `POSE_QA_MODEL_LICENSE_GAP`. O documento e as evidências v0.5.3 não são reescritos.

## v0.5.2 and earlier - historical slices

Incluem a escalada OpenPose/RefControl, multi-reference nativo, âncoras e o piloto walk. Seus resultados são históricos e não autorizam promoção atual.

## Historical navigation note

The older navigation text below is retained as history only. The sole active next gate is the v0.12.4 GitHub CI/governance recovery recorded at the top of this file; historical v0.12.3, walk/front/8, new providers, custom nodes and older dashboard gates are not actionable.
## v0.10.0

Reusable deterministic action runtime and the 10-frame front sword attack pilot are technically qualified after event-marker, lifecycle, temporal, weapon-sweep, foot-ground, structural, occlusion, retention, and independent MediaPipe QA. External attack-front visual review is the only allowed next action; run/hit/death, other directions, provider changes, and production enablement remain blocked. `production_routing=BLOCKED`.
