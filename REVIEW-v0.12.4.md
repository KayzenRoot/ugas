# UGAS v0.12.4 review - GitHub CI and governance recovery

## STATUS

The corrective slice is `GITHUB_CI_GOVERNANCE_RECOVERY` with gate `GITHUB_CI_GOVERNANCE_RECOVERY_TECHNICALLY_QUALIFIED`. The branch is `codex/v0.12.4-github-ci-governance-recovery`, based on the verified remote `main` merge commit `877ede34afadd631764887ad6c5fb941ca4371a8`. PR #2 is OPEN at the exact reviewed head with all three required GitHub checks green; the PR remains open for external Sol review and is not merged. `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, and `RUN_FRONT_V1` remains the next necessary functional candidate after this gate; it was not executed.

## PR #1 INCIDENT

PR #1 remains intact as historical governance evidence. It merged head `2f8d04f03a6f4de0ead7683899f945cd60d5000f` into merge commit `877ede34afadd631764887ad6c5fb941ca4371a8` at `2026-09-02T21:17:00Z`. Review workflow run `33684049540` later concluded `FAILURE`; artifact `9867524286`, named `ugas-review-evidence-pr-1-2f8d04f03a6f4de0ead7683899f945cd60d5000f`, was uploaded with digest `sha256:6ffe21738ed7960aabb5cd874cc44c4030a3b5fee0463f58c004805637a4d6d2` at approximately `2026-09-02T21:19:27Z`. The real validation was `1670` checks, `1667` passed, `3` failed, exit code `1`; unit/state/matrix/visual/manifest/security passed and official validation failed. The factual classification is `GOVERNANCE_ORDER_VIOLATION_AND_FAILED_CHECK_MERGE`; no blame or unproven causality is assigned.

The immutable machine-readable incident is [docs/evidence/github-governance-v0124/pr1-premature-merge.json](docs/evidence/github-governance-v0124/pr1-premature-merge.json). The v0.12.3 state is preserved at [docs/evidence/current-state-v0.12.3.json](docs/evidence/current-state-v0.12.3.json); its historical review and evidence are not rewritten.

## EXTERNAL DASHBOARD VISUAL DECISION

`observability_dashboard_external_visual=APPROVED_PILOT` is a new forward-only decision bound to artifact `9867524286`, its name and digest, and the two existing visual-manifest source/transport SHA-256 pairs. Both true-PNG transport images were directly reviewed as coherent, professional and readable. Degraded and QA-gap states remain visible. This is visual/pilot approval only; it does not approve v0.12.3 GitHub infrastructure, production routing or PR #1 validation. The historical v0.12.2 source evidence remains byte-preserved. The binding is [docs/evidence/github-governance-v0124/dashboard-external-visual-approval.json](docs/evidence/github-governance-v0124/dashboard-external-visual-approval.json).

The only noted non-blocking visual debt is awkward wrapping of long phase/gate identifiers in narrow cards; it is deferred and does not reopen this gate.

## ROOT CAUSE CORRECTIONS

- GitHub-review integrity tests now create and inject a tiny isolated temporary Git repository. Builders remain strict and Git-bound for live PR execution, while tests no longer call `git rev-parse` against a developer worktree when running from an extracted no-git snapshot.
- The historical v0.11.2 index validator resolves the immutable index-build Git object in a normal checkout and uses bundled historical `CHECKPOINT.md` bytes in a no-git snapshot. It never validates an old hash against the current mutable checkpoint and never turns an exception into a PASS.
- Snapshot validation no longer accepts known historical failures. The isolated archive and no-git checks must return zero, including the three defects exposed by the previous red GitHub run.
- UGAS CI keeps stable `UGAS CI / unit-and-validation` and `UGAS CI / docker-smoke` jobs, immutable Action pins, PR triggers, and runner-only Docker cleanup. A repository-side workflow validator rejects missing triggers, unstable job identities, mutable Action references, or unsafe Docker teardown.

## GITHUB AUTOMATION POLICY

`GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY`

`GITHUB_REVIEW_MODE=PR_FIRST NO_SELF_MERGE_UNTIL_EXTERNAL_APPROVAL=true ALWAYS_ON_DASHBOARD_POLICY=ENABLED`

Sol performs external review from GitHub whenever connector permissions allow. Codex performs branch, push, PR, check-wait, log inspection, correction and ruleset operations automatically in its authenticated environment. User intervention is limited to irreducible account consent or authentication. A merge is a separate later operation bound to an exact PR number and expected head SHA after explicit Sol approval; this executor does not merge.

## VALIDATION AND GOVERNANCE

The active state/schema are v0.12.4. The real corrective PR exists and all required GitHub checks are green, so the gate is `GITHUB_CI_GOVERNANCE_RECOVERY_TECHNICALLY_QUALIFIED`. The current state keeps `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, `ALWAYS_ON_DASHBOARD_POLICY=ENABLED` and `DOCKER_ALWAYS_ON_LOCAL`.

Required negative controls are `GOV-NC-01`, `GOV-NC-02`, `CI-NC-01`, `CI-NC-02`, `HIST-NC-01`, `WF-NC-01`, `ART-NC-01` and `STATE-NC-01`. Local test/validation results and the workflow/ruleset readback are under `docs/evidence/github-governance-v0124/`. Historical v0.12.1/v0.12.2/v0.12.3 facts remain separated from current status.

## DASHBOARD BOUNDARY

At start and stop, the persistent host dashboard must be reachable at `http://127.0.0.1:8765/`. The Docker service remains always-on, loopback-only, read-only and is never stopped by this slice. ComfyUI may remain unavailable when it is genuinely down; provider health is not faked.

## SCOPE AND STOP

No asset, animation pixel, provider, model, production route or generated game capability was created. `RUN_FRONT_V1` was not executed. `main` was not directly modified, and PR #1 history was not reset, rewritten, squashed away, reverted or force-pushed.

The corrective PR must be opened automatically and left OPEN, with `UGAS Review / evidence`, `UGAS CI / unit-and-validation` and `UGAS CI / docker-smoke` green, a successful evidence artifact, and effective main protection read back or an exact `RULESET_CAPABILITY_GAP`. The only allowed next action at STOP is `external_review_github_ci_governance_v0124`. The executor must not merge and must not begin v0.13.0.
