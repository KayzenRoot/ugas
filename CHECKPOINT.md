# UGAS checkpoint - v0.4.2

**STATUS:** READY_FOR_REVIEW / VISUAL_REVIEW_REQUIRED. Technical implementation, fresh pilot and integrity evidence are complete; human visual approval remains separate.
**VERSION:** 0.4.2
**FASE:** Revision integrity and evidence correctness
**OBJECTIVE:** Make every asset revision immutable, independently addressable and hash-verifiable while preserving the v0.4.1 model lanes.
**SCOPE:** Revision storage/auditing, safe margins, alpha/RGB QA, immutable reference structural QA, review evidence and regression coverage. No animation authorization.

## COMPLETED

- Implemented unique revision directories with output, mask, checkerboard and metadata ownership.
- Added derived-from/hash/current/approval integrity auditing and the `asset verify-integrity` CLI command.
- Added safe-margin hard gates, near-opaque alpha metrics and RGB-preservation QA.
- Restored the v0.4.0 behavioral test/validation intents with a 26-row coverage matrix.
- Completed a fresh real RTX 5050 + ComfyUI pilot and immutable R1-R4 evidence chain.
- Validated distinct master/reference review roles and generated the final review package after publication.

## IN PROGRESS

- Human visual review of the cobalt/navy reference edit.

## PENDING

- External audit of v0.4.2.
- Human visual approval or rejection bound to an exact revision ID and SHA-256.

## BLOCKERS

No implementation or validation blocker. The release decision remains gated by human visual review because R3/R4 changed facial lighting in addition to the requested armor-color direction.

## DECISIONS

Keep Distilled at 4/1.0 and Base at 50/4.0. Keep original RGB during BiRefNet alpha joining. Never overwrite an earlier revision. Do not authorize animation in this checkpoint.

## TEST EVIDENCE

The full suite has 58 passing tests. R1-R4 hashes, safe-margin results, RGB-preservation results, structural QA and integrity results are recorded in `REVIEW-v0.4.2.md` and `docs/evidence/`.

## NEXT STEP

A human reviewer should inspect the archived evidence and decide whether R4 is acceptable, using the exact revision/hash binding. No automatic approval is performed.

## DEFINITION OF DONE

Historical coverage mapped; no relevant test silently deleted; integrity tests green; unique immutable outputs; safe margins and RGB preservation pass; fresh pilot and structural QA pass; distinct review roles are hash-verifiable; exact snapshot and GitHub are verified; final ZIP is validated; visual approval remains explicitly pending.

## BACKLOG

Animation, multi-frame generation, production LoRAs, 3D/Blender, audio, cloud and paid providers remain backlog/out of scope.
