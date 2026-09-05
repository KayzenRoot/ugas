# UGAS v0.17.0 — EQUIPMENT_OUTFITS runtime foundation

## 1. Scope and starting point

This governed slice starts from merged v0.16.2 at `a8d2897211c4b72c2cd2fe7a7f5729c7009d8566` on branch `codex/v0.17.0-equipment-outfits-runtime-foundation`. The v0.16.2 multi-direction animation runtime is `APPROVED_FOUNDATION`; real directional character artwork remains `SOUTH_ONLY`. This document is the executable review contract for v0.17.0 and must be read completely before implementation or validation.

Only `EQUIPMENT_OUTFITS` is authorized. The slice is a deterministic runtime foundation for modular wearable layers over the approved R4 cutout rig and already approved front animation frames. It does not create production-ready art, run SAM2, ComfyUI, diffusion or new generation, alter the base animation, or start creatures/monsters, items/props, environments/maps, UI, VFX or another asset family.

The authoritative state is `docs/evidence/current-state.json`: `version=0.17.0`, `phase=EQUIPMENT_OUTFITS`, `current_gate=EQUIPMENT_OUTFITS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED`, `multi_direction_animation_runtime=APPROVED_FOUNDATION`, `real_directional_character_asset_coverage=SOUTH_ONLY`, `real_equipment_asset_coverage=NONE_OR_EXPLICITLY_APPROVED_ONLY`, `synthetic_equipment_fixture=TEST_ONLY`, `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, and `allowed_next_actions=[external_review_equipment_outfits_v0170]`.

## 2. Contract

Every wearable must declare `equipment_id`, `slot`, `variant`, deterministic `layer_group`, explicit R4 `anchors`, canonical `direction_coverage`, `animation_compatibility`, `rig_revision_compatibility`, `replacement_rules`, explicit asset-bound `occlusion_masks`, `provenance_hash`, `asset_revision`, `test_only`, `production_safe`, `mirror_safe` and `asymmetry_flags`. The permitted slot/layer families are:

- head: `behind_head`, `head`, `front_head`;
- torso: `behind_torso`, `torso_replace_or_overlay`, `front_torso`;
- arms: explicit `arm_left`/`arm_right` anchors and layers;
- legs: `behind_legs` and `leg_overlays`;
- feet: `feet` with optional explicit base-foot hide;
- back: `back` with explicit front-crossing exceptions;
- accessories: `accessory`, manifest-defined only.

Anchors bind to existing R4 joints/parts and declare offsets, rotation inheritance, uniform scale policy and optional secondary anchor. Composition is overlay or replacement/hide; replacement conflicts use the deterministic `highest_priority_then_equipment_id` policy. Occlusion is never inferred: every mask is asset-bound and names its target part. Base pixels are copied before composition and are never mutated.

The resolver cache key must contain `equipment_id`, `slot`, `variant`, `rig_revision`, canonical direction, animation capability/profile, `asset_revision`, request mode and registry mode. South-only assets resolve only `south`/`front` (`front` canonicalizes to `south`). Missing directions fail closed. Preview fallback is an explicit TEST_ONLY option; mirroring is allowed only when the manifest grants permission, and asymmetric fixtures are unsafe to mirror. Cache entries must distinguish outfit, direction, animation and registry context.

Attachment cannot change base animation timing, event markers or approved frame hashes. Composition is deterministic RGBA; two identical runs with the same base, outfit, direction, animation profile, rig revision and registry context must have identical bytes and hashes. Synthetic fixtures are never production assets. The production registry must remain empty until real equipment assets are separately approved.

## 3. Hard gates

The validator must pass every gate below:

`equipment_schema_valid`, `slot_identity_valid`, `anchor_binding_valid`, `layer_order_deterministic`, `replacement_hide_rules_consistent`, `occlusion_mask_binding_valid`, `direction_coverage_truthful`, `animation_compatibility_truthful`, `mirror_requires_equipment_permission`, `test_only_never_production_safe`, `cache_key_contains_equipment_direction_animation_variant`, `base_asset_immutability_preserved`, `composition_is_non_destructive`, `two_run_composition_deterministic`, `synthetic_fixture_not_in_production_registry`, `production_routing_blocked`.

The required negative controls are real input mutations, not booleans copied from a positive result:

`EQ-NC-01` unknown slot; `EQ-NC-02` missing anchor; `EQ-NC-03` duplicate replace conflict without policy; `EQ-NC-04` layer cycle; `EQ-NC-05` south asset requested north; `EQ-NC-06` silent mirror; `EQ-NC-07` asymmetric fixture mirror; `EQ-NC-08` stale cache for wrong outfit/direction; `EQ-NC-09` provenance mutation; `EQ-NC-10` TEST_ONLY fixture in production; `EQ-NC-11` destructive base-pixel mutation; `EQ-NC-12` nondeterministic second composition; `EQ-NC-13` incompatible rig; `EQ-NC-14` incompatible animation profile; `EQ-NC-15` production routing enabled. Each must record `mutation`, target gate, observed result/error code, `rejected=true` and `status=REJECTED`.

## 4. Evidence and validation order

Create `docs/evidence/equipment-outfits-runtime-v0170/` with the contract, slot/layer graph, anchor QA, replacement/hide QA, occlusion QA, direction/animation QA, cache QA, provenance QA, two-run determinism, negative controls, TEST_ONLY fixture manifest, contact sheet, state consistency and execution evidence. The contact sheet must use the same approved SOUTH base and label synthetic outfits `TEST_ONLY`; it must not imply real approved equipment artwork.

Run system Python 3.12 unit tests, the official validation, active v0.17.0 state consistency, equipment runtime validation, approved front animation regressions and the v0.16.2 direction/cache regression. Run Docker dashboard smoke. The exact GitHub contexts are `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke` and `UGAS Review / evidence`. The bounded artifact must bind the v0.17.0 PR, base SHA, head SHA, tests, validation, every gate, contact sheet, state and evidence. No secrets, weights, telemetry database, credentials or generation directories may enter it.

## 5. Stop condition and handoff

When every hard gate, all 15 negative controls, full tests, official validation, approved front regressions, v0.16.2 regressions, Docker smoke, exact 3/3 GitHub contexts and the exact artifact are green, set the technical state to `EQUIPMENT_OUTFITS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED`, keep `production_routing=BLOCKED`, `production_approved=false`, `new_generation=0`, and STOP with the v0.17.0 PR OPEN. Do not merge v0.17.0, do not claim external equipment/outfits approval, and do not start creatures/monsters. Handoff only for `external_review_equipment_outfits_v0170`.
