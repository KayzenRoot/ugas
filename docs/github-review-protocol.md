# UGAS GitHub-native review protocol

## Canonical flow

All v0.12.4+ implementation rounds follow:

`feature branch from verified baseline -> Pull Request -> GitHub Actions -> external review -> approval -> merge`

The executor never merges its own PR. Direct commits to `main` are an emergency-only documented exception.

## Stable checks

The repository exposes these stable check identities:

- `UGAS CI / unit-and-validation`: Python 3.12 install, full unit tests, official validation, active state consistency and active GitHub review-manifest validation.
- `UGAS CI / docker-smoke`: Compose normalization, dashboard image build, local runner startup and `/api/status` plus `/api/health` reachability.

The workflows use read-only `contents` permissions, PR-keyed concurrency and cancellation of stale runs. The Docker smoke job removes only its CI runner container.

## Review artifact

`UGAS Review Evidence` creates `github-review-manifest.json` and `visual-manifest.json`, then uploads a bounded artifact named `ugas-review-evidence-pr-<N>-<SHA>`. It contains PR base/head/merge-base, changed-file statistics, current gate, production boundary, actual test and validation totals, historical review-index status, known gaps, and SHA-256/size metadata for the two v0.12.2 dashboard PNGs.

The artifact is a transport surface, not a source of truth. Evidence assembly and upload use `always()` so failed gates remain inspectable; final enforcement occurs after upload. It must not contain secrets, model weights, telemetry databases, local credentials, ZIPs or large generation directories. Retention is 21 days; the tracked repository remains canonical.

The two historical v0.12.2 dashboard files are preserved as immutable JPEG/JFIF sources. The review artifact transports dedicated true-PNG copies with source/transport byte hashes, magic-byte MIME detection, dimensions and decoded-pixel hashes. A renamed JPEG is a negative-control failure, not valid PNG evidence. Test and validation results carry actual exit codes and null totals when parsing is not possible.

The review workflow pins checkout, setup-python and upload-artifact to immutable release SHAs. Repository/ruleset gaps must be explicitly evidenced; a local rehearsal records that a PR is unavailable, while a real positive-number PR cannot carry `GITHUB_PR_CREATE_GAP`.

## Governance boundaries

The active state is v0.12.4 `GITHUB_CI_GOVERNANCE_RECOVERY_READY_FOR_PR` until a real corrective PR is green, with `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, `DOCKER_ALWAYS_ON_LOCAL` and `ALWAYS_ON_DASHBOARD_POLICY=ENABLED`. The only allowed next action is `external_review_github_ci_governance_v0124`. `RUN_FRONT_V1` remains the next candidate after this gate, not an action in this increment.

`GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED` and `USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY` are permanent policy. Codex handles routine branch, push, PR, check, log, correction and ruleset operations when authenticated; user interaction is reserved for irreducible account consent/authentication. `NO_SELF_MERGE_UNTIL_EXTERNAL_APPROVAL=true` is fail-closed: red or pending required checks, missing exact-head external approval, or a changed PR head are absolute merge blockers.

Historical v0.12.2/v0.12.1 evidence is preserved and is not rewritten. External review and production approval are never inferred from local green tests, a healthy container or an uploaded artifact.

## Permissions gaps

If GitHub authentication or plan permissions prevent PR creation, emit `GITHUB_PR_CREATE_GAP` with the compare URL and the remediation: authenticate a GitHub CLI/token with pull-request write permission for `csn1985-ship-it/ugas`. If branch ruleset configuration is denied, emit `GITHUB_RULESET_GAP` with the exact repository Settings/API remediation; do not weaken repository visibility or security.
