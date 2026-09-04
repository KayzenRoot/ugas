# UGAS v0.15.1 — DEATH_ANIMATION_FRONT corrective review

## Active decision

The active capability is `DEATH_ANIMATION_FRONT` on the existing `codex/v0.15.0-death-animation-front` branch and PR #5, based on main merge commit `98ebd95564216fbbee222aab630b73b5ff6f298d`. The v0.15.1 gate is `DEATH_ANIMATION_FRONT_GROUND_CONTACT_AND_VISUAL_INTEGRITY_TECHNICALLY_QUALIFIED`. The correction is source-only, eight frames, 12 fps and non-looping; external visual review remains REQUIRED. `CAPABILITY_COUNT=16`, `new_generation=0`, `production_approved=false` and `production_routing=BLOCKED` remain authoritative. The active repository is `KayzenRoot/ugas`.

The v0.15.0 reviewed head `c573ab020106ee89a36e1edb9bfae8b526d5057e` remains immutable rejected history: `external_visual=FAILED` and `technical_semantic_qa=REJECTED_BY_EXTERNAL_REVIEW` despite green CI. The forward-only record is `docs/evidence/animation-runtime-v0151/v0150-rejection-record-v0151.json`. The corrected runtime uses `profiles/animation/death-front-v151.json`, the measured body-contact contract and true two-run decoded-pixel determinism. Ground contact is not inferred from root-y alone: D4 is the first measured named-body contact, and D6-D7 require grounded terminal body contact with both feet lifted.

PR #4 for `HIT_REACTION_FRONT` is `MERGED` at `98ebd95564216fbbee222aab630b73b5ff6f298d`, with merged head `761ed5296e05571fdfbed1da04cfb7815049fa87` and technical-approved head `a3e37865f260c5a6cd56743e1d4b9131fcb12cda`. `HIT_REACTION_FRONT=APPROVED_PILOT` and `RUN_FRONT_V1=APPROVED_PILOT` remain historical pilot decisions; the approved RUN head is `f3d68faa5524392e66aee2fc2a450b9da8fa734b`.

## Evidence and boundaries

The canonical contract is `docs/evidence/animation-runtime-v0151/death-front-contract-v0151.json`. The complete v0.15.1 evidence is under `docs/evidence/animation-runtime-v0151/`, including fixed ground reference, per-frame contact/support state, terminal support, death-vs-HIT semantics, planted-foot world truthfulness, decoded GIF timing, true two-run determinism, NC-01 through NC-16 plus NC-GC-01 through NC-GC-06, provenance-hash correction and repository-transfer provenance. The approved R4 source pixels and prior HIT/RUN evidence remain immutable; SAM2, ComfyUI, diffusion, ControlNet, IP-Adapter, manual replacement pixels, multi-direction runtime and production routing are forbidden.

`GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED`, `USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY`, `GITHUB_REVIEW_MODE=PR_FIRST`, `NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true`, `ALWAYS_ON_DASHBOARD_POLICY=ENABLED` and `DOCKER_ALWAYS_ON_LOCAL` remain binding. Required checks are exactly `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke` and `UGAS Review / evidence`; active main protection requires `current_user_can_bypass=never`. `CODEOWNERS_GAP` remains explicit until resolved.

## Stop and next action

PR #5 must remain OPEN. Do not merge v0.15.1, do not start `MULTI_DIRECTION_ANIMATION_RUNTIME`, and do not enable production. The only allowed next action is `external_visual_review_death_animation_front_v0151`. This document does not grant external visual approval.
