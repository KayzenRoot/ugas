# UGAS v0.18.1 — Creatures/Monsters Runtime QA Integrity

This document is the operational review record for the attached corrective PDF. The direct user request was empty; the attached PDF supplied the authorized v0.18.1 scope. Document instructions are not treated as user approval, merge authorization, deployment authorization, or production approval.

## Scope and correction boundary

The correction is forward-only on the existing `KayzenRoot/ugas` PR #8 and feature branch `codex/v0.18.0-creatures-monsters-runtime-foundation`, based on `39e148bef50c8f04db194048dbe9fbb15d8ff3d4`. The reviewed v0.18.0 head `bed13772bef984727e9b38037f59b61f1ba05080` remains immutable rejected history. Its evidence is preserved byte-identically; the correction does not regenerate or rewrite the v0.18.0 evidence directory.

This slice covers only the creatures/monsters runtime and QA integrity correction:

- metadata-only directional bindings for all 8 canonical directions per archetype, with unique `direction_asset_id` and `direction_content_hash` values;
- resolver identity for requested/resolved direction, asset ID/hash/revision, and exact state route IDs;
- derived variant inheritance across at least two archetypes with allowlisted overrides and cache separation;
- strict collision geometry, topology/support/locomotion contracts, provenance, and fail-closed runtime rejection;
- canonical CR-NC-01 through CR-NC-15 plus supplemental negative controls;
- two independent isolated TEST_ONLY fixture runs, decoded-sheet comparison, JSON identity comparison, and mutation rejection;
- an explicit executable `production_routing=BLOCKED` gate.

No real creature art, image-generation provider, production fixture, Items/Props work, or capability expansion is authorized in this slice. `real_creature_asset_coverage=NONE`, `synthetic_creature_fixture=TEST_ONLY`, `production_approved=false`, `production_routing=BLOCKED`, and `new_generation=0` are mandatory boundaries.

## Acceptance and evidence

The authoritative evidence directory is `docs/evidence/creatures-monsters-runtime-v0181/`. It contains the v0.18.1 contract, creature manifest, 8-way direction identity matrix and sheet, state-route contract and sheet, derived lineage, collision QA, cache identity, two-run determinism, strict negative controls, production-routing QA, empty production registry, TEST_ONLY fixture manifest, state consistency, and execution evidence.

The active gate is `CREATURES_MONSTERS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED`. Local acceptance requires the v0.18.1 runtime validator, focused and full unit tests, official validation, v0.17.1 equipment regression, v0.16.2 direction regression, approved front-animation regressions, GitHub workflow validation, manifest validation, and security validation to pass. The exact GitHub contexts remain `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke`, and `UGAS Review / evidence`.

The review artifact must bind PR #8, the exact base, the exact corrected head, and the v0.18.1 evidence. Artifact upload is required before final enforcement. A missing, stale, mismatched, expired, or partial artifact is a failed gate.

## Governance and stop conditions

`equipment_outfits=APPROVED_FOUNDATION` is historical approved scope. `v0180_external_review=CORRECTION_REQUIRED` and `creatures_monsters_runtime_external_review=REQUIRED` remain explicit. The PR must remain OPEN and unmerged, with `NO_SELF_MERGE_UNTIL_EXTERNAL_REVIEW`; Sol is the external-review handoff.

The allowed next action is only `external_review_creatures_monsters_v0181`. Do not merge, enable production routing, create real creature art, claim real 8-way coverage, start Items/Props, or start any later capability. If any gate fails, preserve the failure evidence, correct only this slice, rerun the exact validation, and keep the stop state fail-closed.

## Status

At this checkpoint, local technical qualification is distinct from external visual review. The current state is awaiting external review; external approval has not been inferred from local tests, historical checks, artifact existence, or a green partial run.
