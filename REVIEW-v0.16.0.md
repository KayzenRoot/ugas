# UGAS v0.16.0 — MULTI_DIRECTION_ANIMATION_RUNTIME foundation

## Active decision

The active phase is `MULTI_DIRECTION_ANIMATION_RUNTIME` on `codex/v0.16.0-multi-direction-runtime-foundation`, based on merged v0.15.1 main at `514a17818469b567966293db808cafbf708f8311`. The local gate is `MULTI_DIRECTION_ANIMATION_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED`. This slice adds a generic direction contract, deterministic vector quantization, aliases, direction-aware asset identity, truthful coverage, fail-closed missing-direction behavior, explicit preview fallback and explicit mirror policy.

The canonical eight are `south`, `south_east`, `east`, `north_east`, `north`, `north_west`, `west`, and `south_west`. `front` aliases `south`; screen-space +x is east/right and +y is south/down. Zero vectors never guess: they use explicit retained facing or remain unresolved. Boundary ownership is deterministic and documented.

The approved real directional coverage is `real_directional_character_asset_coverage=SOUTH_ONLY`: the existing idle, walk, run, attack, hit and death front profiles map to `south` without changing their bytes, timing, events, QA or source hashes. Runtime addressability is not real N/E/W/diagonal artwork. No equipment/outfits, creatures, items, environment, UI, VFX or new generation is started.

`production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, `multi_direction_animation_runtime=TECHNICALLY_QUALIFIED_FOUNDATION`, and `external_visual=REQUIRED` are authoritative. The deterministic asymmetric pack is `TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE` and is never in the production registry.

## Evidence and boundaries

The contract, coverage manifest, resolver QA, quantization, aliases, fallback, mirror, cache, provenance, negative controls, state consistency, execution record and synthetic contact sheet are under `docs/evidence/multi-direction-runtime-v0160/`. The production manifest contains only the six approved `south` profile bindings. Missing real directions return `DIRECTION_ASSET_UNAVAILABLE`; preview fallback and mirror are explicit and non-production. No telemetry upload occurs and the dashboard remains local/read-only.

Required external contexts for the v0.16.0 PR are exactly `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke` and `UGAS Review / evidence`, bound to the exact PR head and artifact. Merge v0.16.0 PR only after external review. Keep the PR OPEN at stop; do not merge v0.16.0 and do not start equipment/outfits.

## Stop and next action

The only allowed next action is `external_review_multi_direction_runtime_v0160`. This foundation does not claim real directional character artwork or production approval.
