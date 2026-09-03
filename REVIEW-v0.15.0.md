# UGAS v0.15.0 — DEATH_ANIMATION_FRONT review

## Active decision

The active capability is `DEATH_ANIMATION_FRONT` on `codex/v0.15.0-death-animation-front`, based on main merge commit `98ebd95564216fbbee222aab630b73b5ff6f298d`. The technical gate is `CUTOUT_ANIMATION_RUNTIME_V1_DEATH_ANIMATION_FRONT_TECHNICALLY_QUALIFIED`. The eight-frame front pilot is source-only, deterministic, 12 fps and non-looping. `CAPABILITY_COUNT=16`, `next_candidate=DEATH_ANIMATION_FRONT`, and `death_animation_front=REQUIRED` for external visual review; this document does not grant approval.

PR #4 for `HIT_REACTION_FRONT` is `MERGED` at `98ebd95564216fbbee222aab630b73b5ff6f298d`, with merged head `761ed5296e05571fdfbed1da04cfb7815049fa87` and technical-approved head `a3e37865f260c5a6cd56743e1d4b9131fcb12cda`. `HIT_REACTION_FRONT=APPROVED_PILOT` and `RUN_FRONT_V1=APPROVED_PILOT` remain historical pilot decisions; the approved RUN head is `f3d68faa5524392e66aee2fc2a450b9da8fa734b`.

The v0.14.1 frozen technical evidence was restored byte-identically from approved head `a3e37865f260c5a6cd56743e1d4b9131fcb12cda`. The post-merge bookkeeping mutation is recorded, not hidden, in `docs/evidence/github-governance-v0141/hit-front-v0141-post-merge-integrity-repair.json`; Git history was not rewritten.

## Death contract

The canonical contract is `docs/evidence/animation-runtime-v0150/death-front-contract-v0150.json`. D0 is an immediate lethal response, D1 destabilizes support, D2 buckles, D3 descends, D4 changes contact regime, D5 settles, D6 establishes the terminal pose and D7 holds the corpse. The required markers are `lethal_impact_onset`, `collapse_start`, `ground_contact` and `final_pose`.

The candidate passed frame, temporal, collapse, support/contact, continuity, weapon, package, provenance, determinism and negative-control gates. The death-vs-HIT comparison uses the approved HIT recovery target as immutable authority. The package has no NETSCAPE repeat extension because `loop=false`.

`new_generation=0`, `production_approved=false` and `production_routing=BLOCKED` remain authoritative. The approved R4 cutout pixels are reused without SAM2, ComfyUI, diffusion, ControlNet, IP-Adapter or manual replacement pixels.

## GitHub review policy

GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED, USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY, GITHUB_REVIEW_MODE=PR_FIRST, NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true, ALWAYS_ON_DASHBOARD_POLICY=ENABLED and `DOCKER_ALWAYS_ON_LOCAL` remain binding. The v0.15.0 PR must be opened automatically, run the required contexts `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke` and `UGAS Review / evidence`, and remain OPEN for Sol review.

Do not merge v0.15.0. Do not start `MULTI_DIRECTION_ANIMATION_RUNTIME`. The only allowed next action is `external_visual_review_death_animation_front`.
