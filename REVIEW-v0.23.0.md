# UGAS v0.23.0 — VFX Asset Family Runtime Foundation

## Status

`VFX_ASSET_FAMILY_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED`

This is a GitHub-first, PR-only foundation slice from approved/merged UI v0.22.3 main `b08b9c3df74ef6a23046be396289e2fd72dc336b`. The branch is `codex/v0.23.0-vfx-asset-family-runtime-foundation`. The PR must remain OPEN and unmerged until the external Sol review is complete.

The runtime is engine/provider neutral and executes only deterministic TEST_ONLY fixtures. It does not generate real VFX, invoke ComfyUI/diffusion/audio/camera-shake providers, mutate gameplay authority, harden orchestration, or enable production routing.

## Implemented contract

The runtime defines ten stable classes:

`impact_burst`, `weapon_arc`, `projectile_trail`, `projectile_impact`, `cast_charge`, `persistent_aura`, `area_telegraph`, `status_loop`, `buff_heal_burst`, and `environment_ambient`.

Each record binds visual-only intent, class-specific semantics, lifecycle/timing and termination, blend/alpha policy, explicit space/anchor/pivot, bounded performance budgets, deterministic fallback/degradation, representation/import metadata, read-only integration, cache identity, frame/content hashes and provider-free provenance.

The bounded evidence contains 25 strict boolean hard gates and 36 negative controls. Negative controls call the same validators used by positive proofs and record observed rejection classes. Two isolated fixture runs are compared by canonical manifest and output hashes. Contact/timing sheets are synthetic QA aids, not production artwork.

## Evidence and boundaries

Evidence root: `docs/evidence/vfx-asset-family-runtime-v0230/`.

Production remains `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, `real_vfx_asset_coverage=NONE`, and `synthetic_vfx_fixture=TEST_ONLY`. The UI v0.22.3 approval transition is recorded forward-only; its historical review and evidence are not rewritten.

The sole allowed next action is `external_review_vfx_asset_family_v0230`. After external approval, governed merge and exact post-merge main CI, a future chat may resolve the orchestration gate from GitHub LIVE. No UI, VFX production generation or orchestration work is authorized in this stop state.

## Reproduction

```powershell
$env:PYTHONPATH='src'
python scripts/validation/run_vfx_asset_family_runtime_v0230.py
python scripts/validation/validate_state_consistency_v0230.py
python scripts/validation/validate_v1_capability_matrix.py
python -m unittest tests.test_vfx_asset_family_runtime_v0230 -q
python scripts/validation/run_validation.py
```

The final exact-head GitHub contexts required by the work order are `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke`, and `UGAS Review / evidence`. The bounded exact-head artifact must pass manifest and security validation before handoff to Sol.
