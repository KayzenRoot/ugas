# UGAS v0.12.3 review - GitHub-native review infrastructure

## Active decision boundary

The active phase is `GITHUB_NATIVE_REVIEW_INFRASTRUCTURE` and the active increment is `GITHUB_NATIVE_REVIEW_READY_TECHNICALLY_QUALIFIED`. It makes GitHub the canonical review surface for the repository while preserving the local Docker always-on dashboard. `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, `ALWAYS_ON_DASHBOARD_POLICY=ENABLED` and `runtime_mode=DOCKER_ALWAYS_ON_LOCAL` remain authoritative.

The only allowed next action is `external_review_github_native_v0123_and_dashboard_v0122`. The next functional candidate after external approval is `RUN_FRONT_V1`; this round does not implement it.

## Scope implemented

- `.github/workflows/ugas-ci.yml` exposes stable `UGAS CI / unit-and-validation` and `UGAS CI / docker-smoke` checks with read-only contents permissions and PR-keyed concurrency.
- `.github/workflows/ugas-review.yml` builds a schema-valid machine manifest and a provenance-bound visual transport manifest, then always assembles and uploads one bounded review artifact, including when a gate fails; final enforcement runs after upload.
- The historical v0.12.2 dashboard files remain byte-identical JPEG/JFIF sources. Dedicated true-PNG transport copies live under `docs/evidence/github-review-v0123/visuals/`; their decoded pixels are hash-bound to the historical sources and their PNG signatures are checked from bytes.
- `scripts/validation/build_github_review_manifest.py` is the reproducible builder; `schemas/github-review-manifest-v1.json` and `schemas/review-visual-transport-v1.json` are the contracts and the workflow regenerates the manifest from the PR base/head.
- Test and validation records preserve the actual exit code, parsed totals or explicit null totals on parse failure. Review gaps are contextual: a PR-create gap remains in preflight evidence and is never placed in a positive-number PR manifest.
- Review Actions are pinned to immutable SHAs: checkout v4.2.2, setup-python v5.6.0 and upload-artifact v4.6.2.
- The PR template, `CONTRIBUTING.md`, `docs/github-review-protocol.md` and `docs/release-policy.md` define review discipline, evidence boundaries and the no-self-merge stop condition.
- The autostart installer tries the existing per-user Task Scheduler route first and falls back to one UGAS-owned signed-in-user Startup entry on access denial. Both install and uninstall are scoped and reversible.
- `docs/roadmap.md`, `CHECKPOINT.md` and `docs/evidence/current-state.json` now navigate the active v0.12.3 gate; v0.12.2, v0.12.1 and older evidence remain historical.
- `docs/ugas-v1-capability-matrix.md` and `.json` freeze `RUN_FRONT_V1` as the next functional candidate without executing a new asset capability.

## Explicit out of scope

No new asset family, animation pixel, rig, mask, `attack-front-v2` binding, provider, ComfyUI migration, production routing, historical release/tag or fake GitHub approval was created. The v0.12.2 review index is preserved as historical baseline evidence and is not rewritten.

## Validation and evidence

Local evidence is recorded under `docs/evidence/github-review-v0123/`: `github-preflight.json`, `github-review-manifest-local.json`, `visual-manifest.json`, the two true-PNG files under `visuals/`, `gate-results-v0123.json`, `autostart-v0123.json`, `governance-consistency-v0123.json`, `v1-capability-matrix-validation.json`, `test-results-v0123.json` and `validation-results-v0123.json`. The local dashboard must remain reachable at `http://127.0.0.1:8765/` at executor STOP.

The PR description links the GitHub Actions review workflow/artifact transport. It contains no absolute user-home paths, secrets or local credentials. If authentication or repository-plan permissions prevent PR/ruleset configuration, the evidence records `GITHUB_PR_CREATE_GAP` or `GITHUB_RULESET_GAP` with exact remediation; no fake success is written.

## External review handoff

The external reviewer resolves the PR base/head directly from GitHub, inspects the diff and checks, downloads the `ugas-review-evidence-pr-<N>-<SHA>` artifact, and reviews both v0.12.2 dashboard PNGs plus the machine manifests. Only that reviewer may produce an approval decision or authorize `RUN_FRONT_V1`.

## STOP

Stop with the PR open, checks green or with explicit infrastructure permission gaps, dashboard online, production blocked and no merge to `main`.
