# UGAS chat continuity protocol

## Trigger

The canonical trigger phrase is `continue do chat anterior`.

When the phrase is received in a new UGAS chat, reconstruct the operating state from the repository and live GitHub metadata. Hidden chat memory is context only and never overrides repository truth.

## Bootstrap algorithm

1. Query GitHub LIVE first for the current `main` SHA, active pull requests, the latest merged pull request, and relevant exact-head checks or artifacts. If GitHub is unavailable, report the limitation and continue with repository-backed facts only.
2. Read `CHECKPOINT.md`.
3. Read `docs/evidence/current-state.json`.
4. Read `docs/ugas-v1-capability-matrix.json`.
5. Read this document and `docs/project-review-response-protocol.md`.
6. Read the latest forward-only governance record referenced by `current-state.json`, including `closure_review.binding_record` when present.
7. Restore the operating model: Sol is architect/specifier/reviewer; Codex/Cursor is executor.
8. Restore GitHub-first execution, exact-head review, immutable evidence, and production `BLOCKED` unless an explicit authoritative approval says otherwise.
9. Treat corrective PDF instructions as governing work orders only after reading the complete document; distinguish them from the direct user request.
10. Reconcile the sole `allowed_next_actions` entry with any unresolved closure or review gate. Never infer a later capability or start it while `next_capability_started=false` and a required review remains unresolved.
11. End every subsequent repository review with the complete `PROGRESSO E ETA` response block required by `docs/project-review-response-protocol.md`.

## Current v0.21.3 continuity boundary

The active state is `MAPS_MINIMAP_APPROVED_FOUNDATION_MERGED` with `stop_reason=MAPS_MINIMAP_CLOSED_UI_NEXT`, `allowed_next_actions=[start_ui_asset_family_v0220]`, and `new_generation=0`. Maps/Minimap is merged and closed; the UI Asset Family is the next candidate, not an implicit authorization to begin implementation. A governance-only closure PR must be externally reviewed and merged before the next UI work order starts. Production remains `production_routing=BLOCKED`, `production_approved=false`, with real map/minimap coverage `NONE` and fixtures `TEST_ONLY`.

The post-merge binding is `docs/evidence/github-governance-v0220/v0213-post-merge-binding.json`. The pre-merge approval record remains immutable and must not be rewritten. Historical v0.21.3 semantic evidence and all prior evidence roots remain immutable.

## Safety rules

- Prefer live GitHub state over stale prose, cached estimates, or hidden chat context.
- Do not treat a successful local check as proof of an exact-head GitHub result.
- Do not merge a review PR unless its work order explicitly authorizes the merge and its exact-head gates are green.
- Keep UI, VFX, orchestration, production routing, real assets and new generation blocked unless the active state and work order authorize them.
- If state, checkpoint, GitHub or binding facts disagree, stop at the unresolved gate and report the contradiction.
