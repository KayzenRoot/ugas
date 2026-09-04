# Work Order ENG-PROTOCOL-ADOPTION-001

- **Title:** Adopt governed engineering delivery protocol
- **Repository:** `universal-game-asset-studio` / configured remote `csn1985-ship-it/ugas`; GitHub currently resolves the public repository to `KayzenRoot/ugas` (`NEEDS OWNER CONFIRMATION`)
- **Baseline SHA:** `c573ab020106ee89a36e1edb9bfae8b526d5057e`
- **Branch:** `chore/eng-protocol-adoption-001`
- **PR title:** `chore: adopt governed engineering delivery protocol`
- **Status:** `APPROVED_FOR_EXECUTION` from the explicit user request; final handoff is `READY_FOR_REVIEW`
- **Work order ID used by all artifacts:** `ENG-PROTOCOL-ADOPTION-001`

## Objective

Adopt a rigorous existing-project delivery protocol, establish a verifiable baseline, add minimal governance contracts/templates, integrate executor instructions and compatible GitHub templates/validation, and produce a classified cleanup inventory without changing product behavior or performing cleanup.

## In scope

- Add `.engineering/ENGINEERING-DELIVERY-PROTOCOL.md`.
- Add Work Order, Context Lock, Evidence Bundle, Correction Delta, and Checkpoint Delta schemas/templates.
- Add this adoption Work Order, baseline report, Context Locks, Evidence Bundle, cleanup inventory, and proposed Checkpoint Delta.
- Add the protocol to `AGENTS.md` while preserving existing UGAS rules.
- Adapt the existing PR template and add implementation/defect issue templates.
- Add fail-closed validation of the protocol artifacts to the existing `UGAS CI / unit-and-validation` job without inventing a required-check name.
- Run the same applicable baseline validations after adoption.
- Commit, push, and open a PR with the exact work-order identity in the body and evidence.

## Out of scope

- New product functionality or behavior changes.
- Architecture rewrite or framework/dependency upgrade.
- Product migration, CI/CD replacement, or branch-protection weakening.
- Broad cleanup, deletion of suspected code, renames, or removal of historical evidence.
- Production enablement, asset generation, SAM2, ComfyUI, diffusion, or animation work.
- Canonical `CHECKPOINT.md` or `docs/evidence/current-state.json` promotion.

## Execution plan

1. Inspect repository, Git, canonical documents, architecture, package/build system, tests, CI, deployment, runtime database, and GitHub rules.
2. Freeze the baseline at the exact SHA above and record pre-existing warnings/gaps.
3. Create the initial Context Lock with deterministic SHA-256 fingerprints.
4. Add protocol/governance artifacts and integrations only.
5. Mark the initial lock `STALE` for intentional critical-source changes and create the after-change relock.
6. Run protocol validation, compileall, unit tests, official validation, Docker config/build, and dashboard API checks as applicable.
7. Compare before/after results and correct only adoption regressions.
8. Commit and push the branch, open the GitHub PR, and record exact PR/check status.
9. Produce the final Evidence Bundle and proposed Checkpoint Delta.
10. Stop at independent review; do not begin cleanup.

## Deliverables

- Engineering Delivery Protocol.
- Five contract schemas and five templates.
- Adoption Work Order and Context Locks.
- Baseline report.
- Classified Cleanup Inventory.
- Agent instruction and GitHub template/validation integrations.
- Evidence Bundle.
- Proposed Checkpoint Delta.

## Required validation

- `python -m compileall -q src scripts tests`
- `$env:PYTHONPATH='src'; python -m unittest discover -s tests -q`
- `$env:PYTHONPATH='src'; python scripts/validation/run_validation.py`
- `python scripts/validation/validate_engineering_protocol.py`
- `docker compose -f compose.yaml config`
- `docker compose -f compose.yaml build dashboard`
- Existing dashboard `/api/status` and `/api/health` checks when the always-on service is available.
- No lint/typecheck command exists in the repository; record as `NOT_CONFIGURED`, not as a fabricated pass.

## Stop conditions

- Baseline cannot be determined or source hierarchy cannot resolve a contradiction.
- Required GitHub operations are unavailable.
- Any unrelated work cannot be isolated from the adoption diff.
- The change requires a product/architecture rewrite or destructive operation.
- A critical source changes without a stale mark and relock.
- An unresolved HIGH/CRITICAL issue prevents safe continuation.

## Acceptance

The adoption is technically complete only when the protocol artifacts validate, the after results do not regress the baseline, the diff is limited to the approved paths, the branch is pushed, and the PR is open for independent review. The status must remain `READY_FOR_REVIEW`; it is not external approval or production approval.
