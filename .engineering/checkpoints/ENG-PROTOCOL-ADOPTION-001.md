# Proposed Checkpoint Delta - ENG-PROTOCOL-ADOPTION-001

- **Status:** `PROPOSED`
- **Canonical change:** `false`
- **Work Order:** `ENG-PROTOCOL-ADOPTION-001`
- **Approval:** independent owner/reviewer confirmation required

## Before

- Canonical active state remains v0.15.0 `DEATH_ANIMATION_FRONT`.
- `CHECKPOINT.md` and `docs/evidence/current-state.json` remain authoritative and unchanged.
- Production remains `production_approved=false`, `production_routing=BLOCKED`, and `new_generation=0`.
- The active v0.15.0 PR/review gate remains outside this adoption Work Order.

## Proposed after

- The repository has a governed delivery protocol under `.engineering/`.
- Future work must use a Work Order, Context Lock, Evidence Bundle, and proposed Checkpoint Delta.
- Critical-source changes must transition a lock through `STALE` and an explicit relock.
- Cleanup candidates must be classified and independently reviewed; no broad cleanup is authorized by this delta.
- The adoption branch/PR remains `READY_FOR_REVIEW` until independent review; no canonical operational status is promoted by the executor.

## Required review decision

An independent owner/reviewer must accept or reject this delta and the protocol PR. External approval, merge, and production routing are not inferred from local validation.

## Next action

`independent_review_eng_protocol_adoption_001`; after review, create a separate cleanup Work Order only if the owner explicitly authorizes it.
