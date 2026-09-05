# UGAS v0.18.0 — CREATURES_MONSTERS runtime foundation

## Request/document boundary

The direct user request supplied no additional prose beyond the attached PDF. This review file executes the attached `UGAS-v0.18.0-CREATURES-MONSTERS-RUNTIME-FOUNDATION.pdf` as the governing work package. Instructions in that PDF are document instructions, not user claims or approvals; external review and merge remain separate gates.

## Scope and precondition

The v0.17.1 Equipment/Outfits foundation was merged through protected GitHub after exact-head checks. The resulting baseline is `39e148bef50c8f04db194048dbe9fbb15d8ff3d4`. This increment is limited to the Creatures/Monsters runtime foundation. It does not create production creature art, run generation, alter gameplay balance, start Items/Props, or rewrite historical v0.17.1/v0.16.2 evidence.

## Implemented contract

- Six archetypes: `humanoid_biped`, `quadruped`, `flying_winged`, `serpentine`, `amorphous`, and `stationary_structure`.
- Explicit topology, locomotion, support model, rig family, base scale, footprint, collision profile, pivot, bounds, anchors, provenance and production safety.
- Canonical states are `idle`, `locomotion`, `attack_primary`, `hit_reaction`, and `death`, each declared `REQUIRED`, `OPTIONAL`, or `UNSUPPORTED`; unsupported requests return `CREATURE_STATE_UNSUPPORTED`.
- Direction IDs and normalization reuse v0.16.2. Synthetic 8-way coverage is QA-only; real creature asset coverage remains `NONE`, with no inferred side/back views.
- Variant lineage is acyclic and overrides are allowlisted; gameplay balance is outside the contract.
- Cache identity binds creature, archetype, variant, normalized direction, state, topology revision, asset revision, normalization, request mode and registry mode. Stale cross-creature entries are rejected.
- `CreatureRegistry` is generic and separate from equipment/direction. Production registry is empty; TEST_ONLY records cannot enter production. Preview fallback is explicit and TEST_ONLY.

## Evidence and hard gates

The executable runner is `scripts/validation/run_creatures_monsters_runtime_v0180.py`. It writes only the bounded v0.18.0 evidence directory and deterministic synthetic PNG fixtures. The exact gate IDs are:

`creature_schema_valid`, `archetype_topology_valid`, `support_model_matches_archetype`, `scale_and_footprint_explicit`, `collision_profile_explicit`, `pivot_and_bounds_valid`, `required_animation_states_declared`, `unsupported_state_fails_closed`, `direction_coverage_truthful`, `variant_lineage_acyclic`, `variant_override_allowlist_enforced`, `cache_identity_contains_creature_variant_direction_state`, `stale_cache_cross_creature_rejected`, `provenance_hash_matches_manifest`, `synthetic_fixture_not_in_production_registry`, `production_registry_empty`, `production_routing_blocked`, and `two_run_fixture_generation_deterministic`.

CR-NC-01 through CR-NC-15 are real semantic mutations. Each must record the observed rejection result, stable error code and rejection class. The fixture manifest records six unique hashes, an asymmetric orientation marker, `TEST_ONLY`, and `production_safe=false`. Contact and state-routing sheets are QA evidence, not production art.

## Validation order

Run with system Python 3.12 and `PYTHONPATH=src`:

```powershell
python scripts/validation/validate_state_consistency_v0180.py
python scripts/validation/run_creatures_monsters_runtime_v0180.py
python scripts/validation/validate_v1_capability_matrix.py
python -m unittest discover -s tests -q
python scripts/validation/run_validation.py
python scripts/validation/validate_github_workflows_v0124.py --root .
```

The official CI matrix also checks frozen v0.17.1 equipment regression, v0.16.2 direction/cache regression, approved front animation compatibility, and the Docker dashboard smoke. Review evidence is captured and uploaded before final enforcement, including failure evidence.

## Stop condition and handoff

Expected qualified state is `version=0.18.0`, `phase=CREATURES_MONSTERS`, `current_gate=CREATURES_MONSTERS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED`, `equipment_outfits=APPROVED_FOUNDATION`, `creatures_monsters_runtime=TECHNICALLY_QUALIFIED_FOUNDATION`, `real_creature_asset_coverage=NONE`, `synthetic_creature_fixture=TEST_ONLY`, `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, `allowed_next_actions=[external_review_creatures_monsters_v0180]`, and `next_capability_started=false`.

Final stop is an open v0.18.0 PR with exact-head GitHub Actions and bounded artifact evidence. Do not merge v0.18.0, do not start Items/Props, do not enable production, and do not claim production creature art. Handoff is to Sol for external review of the Creatures/Monsters foundation.
