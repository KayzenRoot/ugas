# UGAS v0.21.0 — MAPS_MINIMAP runtime foundation

## Boundary and direct-request distinction

The direct user request accompanying the attached PDF was empty. The PDF is therefore treated as the governing executable specification under the standing project rule for attached `.pdf` and `.md` prompts. Its instructions are not presented as a separate user message; they define this work package only within the explicit v0.21.0 boundary.

## Baseline and execution mode

The v0.20.3 environment/tilesets foundation was approved and merged through protected PR #10 at main commit `0bf04cb92e8619ea10cf82af8dbf2d9abe599e05`. This slice starts from that exact commit on `codex/v0.21.0-maps-minimap-runtime-foundation` and uses GitHub PR first. The v0.20.3 reviewed evidence and hashes remain historical authority and are not regenerated or overwritten.

## Implemented scope

This increment implements a deterministic TEST_ONLY maps/minimap runtime foundation:

- map identity, schema, dimensions, world metrics, origin and orientation;
- environment authority bindings and layer ownership;
- typed Items/Props world-capable references;
- cell bounds, exact chunk partitioning and chunk round trips;
- regions, zones, POI, portal and spawn marker identity;
- aspect-fit minimap projection and inverse projection;
- visibility-state masks and derived-output identity;
- provenance, complete map/minimap cache identity and stale-context rejection;
- deterministic semantic PNG QA outputs and isolated two-run comparison;
- an empty production registry with production routing blocked.

The fixture contains two maps with different dimensions and aspect ratios, multiple chunks, all primary layers, a typed world prop, regions/zones, and all required marker classes. No real map or minimap asset was created or approved.

## Acceptance evidence

Evidence is under `docs/evidence/maps-minimap-runtime-v0210/`. The executable runner records 21 named hard gates and 20 semantic negative controls. Every control must inject a real defect and observe the exact rejection class, including stale cross-map cache/projection rejection and nondeterministic-output rejection. The isolated output comparison must be byte-identical on the second independent subprocess run and must reject a mutation.

The active state is `version=0.21.0`, `phase=MAPS_MINIMAP`, `current_gate=MAPS_MINIMAP_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED`, `environment_tilesets=APPROVED_FOUNDATION`, `maps_minimap_runtime=TECHNICALLY_QUALIFIED_FOUNDATION`, `real_map_asset_coverage=NONE`, `real_minimap_asset_coverage=NONE`, `synthetic_map_fixture=TEST_ONLY`, `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, and `allowed_next_actions=[external_review_maps_minimap_v0210]`.

## Stop and handoff

After the final exact-head GitHub checks and bounded artifact pass, leave the v0.21.0 PR OPEN and unmerged for external review. Do not enable production routing, generate real map/minimap assets, start UI/VFX/orchestration work, or merge this PR. External approval is not inferred from local tests, CI success, or artifact existence.
