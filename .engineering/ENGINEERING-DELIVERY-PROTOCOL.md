# Engineering Delivery Protocol

## Purpose

This protocol governs small, reviewable changes in an existing UGAS checkout. It establishes a reproducible baseline, a bounded Work Order, a locked execution context, evidence, and a proposed checkpoint delta without replacing the project's canonical status documents.

## Source hierarchy

1. The current user-approved Work Order and its explicit scope.
2. Repository `AGENTS.md` and other executor instructions.
3. `CHECKPOINT.md` and `docs/evidence/current-state.json` as canonical operational truth.
4. Canonical architecture, release, roadmap, and GitHub review documents.
5. Source code, schemas, workflows, tests, and package metadata.
6. Inferences, which must be marked `PROPOSED`, `UNKNOWN`, or `NEEDS OWNER CONFIRMATION`.

Conflicting sources are not silently reconciled. The higher source wins and the conflict is recorded in the Work Order or evidence.

## Required delivery sequence

1. Inspect the repository and Git/GitHub state before modifying files.
2. Record the exact baseline commit, worktree state, toolchain, architecture, scope, and known gaps.
3. Create one Work Order with a stable `work_order_id`.
4. Create a Context Lock with deterministic SHA-256 fingerprints for critical sources.
5. Implement only the approved Work Order on a short-lived branch.
6. If a critical source changes, mark the prior lock `STALE`, record why, and create a fresh after-change lock.
7. Run the same applicable validation as the baseline and compare results.
8. Correct only regressions introduced by this Work Order.
9. Commit, push, open or update the PR, and produce a bounded Evidence Bundle.
10. Propose a Checkpoint Delta; do not promote canonical truth or merge without the required independent review.

## Scope and safety

This protocol does not authorize product features, broad cleanup, architecture rewrites, unrelated dependency upgrades, migrations, public contract changes, or production enablement. Existing production, dependencies, migrations, endpoints, jobs, configuration, flags, and public contracts are presumed used until independently disproven.

Potential use through reflection, dependency injection, plugins, dynamic imports, dynamic routes/configuration, events, serialization, CLI, cron/jobs, migrations, feature flags, callbacks, or webhooks is treated as usage.

Cleanup candidates use exactly one of:

- `VERIFIED_DEAD`
- `PROBABLY_DEAD`
- `DUPLICATE_OR_OBSOLETE`
- `GENERATED_OR_VENDORED`
- `UNKNOWN`

Only `VERIFIED_DEAD` may be proposed for automatic removal in a later, independently reviewed Work Order. This adoption Work Order performs no cleanup.

## GitHub policy

Use a feature branch and PR. Preserve branch protection, existing CI, and exact required-check names. The executor does not self-merge. A local green result is not external approval and does not authorize production routing.

## Evidence and status vocabulary

Evidence must identify the command, actual result, baseline or head context, and limitations. Use `BLOCKED` for a hard stop, `READY_FOR_REVIEW` for a technically complete handoff, `APPROVED` only for an explicit external decision, and `UNKNOWN` or `NEEDS OWNER CONFIRMATION` where proof is absent.

## Stop conditions

Stop as `BLOCKED` instead of improvising when the baseline cannot be determined, canonical sources conflict without a resolvable hierarchy, unrelated work cannot be isolated, the baseline is too broken to distinguish regressions, GitHub required for the delivery is unavailable, the change requires an architectural rewrite, cleanup safety cannot be proved, a destructive operation is required, or an unresolved HIGH/CRITICAL issue prevents safe continuation.

After this adoption PR, stop and wait for independent review. Do not begin the first cleanup increment automatically.

## Final review

The final review is written in Brazilian Portuguese and reports repository, branch, base/head SHA, PR, baseline versus after validation, pre-existing and introduced failures, changed files, classified cleanup inventory, risks, evidence, proposed checkpoint delta, GitHub links, and the ordered low-risk cleanup roadmap.
