# UGAS v0.21.1 — MAPS_MINIMAP QA contract integrity correction

## Boundary and direct-request distinction

The direct user request accompanying the attached PDF was empty. The PDF is treated as the governing executable specification under the standing project rule for attached `.pdf` and `.md` prompts. Its instructions are distinct from the direct request and define this correction work package only within the authorized v0.21.x Maps/Minimap scope.

## Baseline, rejection and same-PR handoff

The correction preserves base `0bf04cb92e8619ea10cf82af8dbf2d9abe599e05`, branch `codex/v0.21.0-maps-minimap-runtime-foundation`, and existing PR #11. The reviewed v0.21.0 head `185e03d057779f7f3ffea4ef5a14f891d518b61f` remains `CORRECTION_REQUIRED` history. No duplicate PR, merge, force-push, production routing or external approval is inferred. The v0.20.3 approval file remains historical authority; its forward binding is recorded separately.

## Corrections F-01 through F-05

- F-01: the production hard gate observes the actual empty `MapRegistry` snapshot; a TEST_ONLY non-empty mutation rejects as `PRODUCTION_REGISTRY_NOT_EMPTY`.
- F-02: canonical map chunk and minimap keys bind the real map content hash, projection, marker, visibility and renderer context. Same map ID/revision with changed content cannot reuse the old identity.
- F-03: a canonical coordinate transform applies `TOP_LEFT`/`CENTER` origin and `Y_DOWN`/`Y_UP` orientation, with inverse round trips and exact broken-origin/inverse rejection classes. Alpha and beta fixtures are intentionally distinct.
- F-04: `docs/evidence/github-governance-v0210/v0203-external-approval.json` is byte-identical to the protected-main authority. New facts use forward-only `record_type=baseline_binding` evidence.
- F-05: item/prop coordinates are finite, inside the logical map domain and owned by `floor(x), floor(y)`; off-map and wrong-cell mutations reject exactly.

## Acceptance evidence and production boundary

The new evidence root is `docs/evidence/maps-minimap-runtime-v0211/`. It contains 21/21 semantic hard gates, 26/26 negative controls, exact projection/cache/placement proofs, historical immutability proof and isolated two-run determinism. Both maps remain TEST_ONLY; real map/minimap coverage is `NONE`; `production_approved=false`, `production_routing=BLOCKED`, and `new_generation=0`.

The active state is `version=0.21.1`, `phase=MAPS_MINIMAP`, `current_gate=MAPS_MINIMAP_QA_CONTRACT_INTEGRITY_TECHNICALLY_QUALIFIED`, `allowed_next_actions=[external_review_maps_minimap_v0211]`. UI, VFX, orchestration, production maps/minimaps and new generation remain out of scope.

## Stop condition

After the new exact-head GitHub checks and bounded review artifact pass, leave PR #11 OPEN and unmerged for external Sol review. A local pass, CI success or artifact existence is not external approval and cannot authorize merge, production routing or downstream capability.
