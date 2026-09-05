# UGAS v0.16.2 - MULTI_DIRECTION_ANIMATION_RUNTIME cache and state truth correction

This is a correction-only slice for `KayzenRoot/ugas` on branch `codex/v0.16.0-multi-direction-runtime-foundation`, based on approved v0.15.1 main commit `514a17818469b567966293db808cafbf708f8311`. PR #6 remains `OPEN`; the rejected reviewed head corrected by this slice is `2513d9f6f8a55345e74d9c0afb5dab22f9d84705`.

## Findings corrected

The v0.16.1 runtime cached all unresolved normalization classes under one `UNRESOLVED` direction identity. v0.16.2 puts the normalization outcome in the key, so `UNKNOWN_DIRECTION_UNRESOLVED`, `ZERO_VECTOR_UNRESOLVED`, and `INVALID_VECTOR_UNRESOLVED` cannot contaminate one another through request order. The resolver exposes cache hit/miss counters for QA evidence.

The cache key now separates `request_mode` (`direct` or explicit preview options) from `registry_mode` (`production` or `test`). A test-only resolver therefore records `registry_mode=test` and never implies production. `production_safe=false` remains true for test-only and preview/mirror resolutions.

The active state now points `previous_release` to the last approved release/pilot-bearing merged state, v0.15.1. v0.16.0 and v0.16.1 are represented separately as `CORRECTION_REQUIRED` history; their source evidence is not rewritten. The forward-only v0.16.1 rejection record is `docs/evidence/multi-direction-runtime-v0162/v0161-rejection-correction-record-v0162.json`.

## Preserved boundary

The canonical directions remain `south`, `south_east`, `east`, `north_east`, `north`, `north_west`, `west`, and `south_west`, with deterministic aliases and vector quantization. The six approved front profiles remain byte/hash-compatible and real directional artwork remains `SOUTH_ONLY`. Missing directions fail closed; preview fallback and mirror require explicit non-production options. `TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE` remains review-only.

No equipment, outfits, creatures, items, environment, UI asset family, VFX asset family, SAM2, ComfyUI generation, diffusion, or new generation was started. `production_approved=false`, `production_routing=BLOCKED`, and `new_generation=0` remain authoritative.

## Evidence and validation

Forward evidence is under `docs/evidence/multi-direction-runtime-v0162/`, including:

- `cache-unresolved-class-qa-v0162.json` and `cache-order-negative-controls-v0162.json` for CACHE-NC-01 through CACHE-NC-05;
- `test-only-cache-mode-qa-v0162.json` for truthful test/production registry context;
- `corrected state-consistency-v0162.json` as `state-consistency-v0162.json` plus the active `current-state.json`;
- v0.16.2 contract, carried-forward coverage/fallback/mirror/provenance bindings, real DIR-NC-01 through DIR-NC-12 records, and validation totals.

Required exact GitHub contexts are `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke`, and `UGAS Review / evidence`. The reviewed runtime head `2864b8ca392725b6da0616916ef3a3c38ce0a0d6` was externally recorded as `APPROVED_FOUNDATION / APPROVED_TO_MERGE`; after the bookkeeping-only state correction and exact post-bookkeeping reproof, the active state records `real_pr_checks_green=true` and `merge_authorization=APPROVED_TO_MERGE`. The approval covers runtime identity/cache/fallback/mirror/test-only/SOUTH_ONLY evidence, not real north/east/west/diagonal character artwork. `next_candidate=EQUIPMENT_OUTFITS`, but the next capability remains unstarted until the governed merge.

## Governed merge and handoff

The technical gate is `MULTI_DIRECTION_ANIMATION_RUNTIME_CACHE_AND_STATE_INTEGRITY_TECHNICALLY_QUALIFIED`. With the exact-head artifact and 3/3 contexts green after bookkeeping, PR #6 is authorized for the protected merge path. Merge only after recorded external approval and exact post-bookkeeping reproof; do not push directly to `main`. After the merge, create the v0.17.0 equipment/outfits branch from merged main and begin only the equipment/outfits foundation. Do not start creatures/monsters or any other downstream capability.
