# Baseline Report - ENG-PROTOCOL-ADOPTION-001

## Identity and repository state

- Project: `universal-game-asset-studio` (UGAS), package version `0.15.0`.
- Configured remote: `csn1985-ship-it/ugas`.
- GitHub UI observed a public repository redirected to `KayzenRoot/ugas`; this identity relationship is `NEEDS OWNER CONFIRMATION` and is retained as a governance risk.
- Default branch: `main` (`origin/HEAD -> origin/main`).
- Baseline branch before adoption: `codex/v0.15.0-death-animation-front`.
- Baseline HEAD: `c573ab020106ee89a36e1edb9bfae8b526d5057e`.
- Adoption branch: `chore/eng-protocol-adoption-001`.
- Baseline tracked worktree: clean; pre-existing untracked files were preserved and are outside this Work Order: `.cursor/`, `_smoke_decoded.txt`, `tmp_explore2.py`, `tmp_explore2_out.json`, `tmp_explore2_result.json`, `tmp_explore2_stderr.txt`, and `tmp_explore_death_v151.out.json`.

## Technology and architecture

- Language/runtime: Python 3.12.10 system interpreter, with PowerShell operational scripts.
- Packaging: `pyproject.toml`, setuptools backend, package data for the dashboard; `package.json` exposes command aliases but has no Node dependencies.
- Runtime dependencies: Pillow and psutil; both are imported by the implementation and validation paths.
- Architecture: request -> classifier/profile/Art DNA -> capability evidence -> provider router -> qualified workflow/model -> ComfyUI/history -> technical QA -> provenance -> asset registry, with a local read-only observability dashboard.
- Persistence/deployment: SQLite WAL telemetry in `.ugas/runtime`; Docker Compose dashboard is loopback-only, read-only repository mount, writable runtime mount, non-root, and restart-unless-stopped. No product migrations directory or hosted deployment configuration was found.
- Canonical documents: `AGENTS.md`, `CHECKPOINT.md`, `docs/evidence/current-state.json`, `README.md`, `docs/architecture.md`, `docs/2d-master-pipeline.md`, `docs/release-policy.md`, `docs/github-review-protocol.md`, `docs/roadmap.md`, and versioned `REVIEW-*.md` evidence.

## Current scope and Definition of Done

The canonical active state is v0.15.0 `DEATH_ANIMATION_FRONT`, technically qualified locally, with PR #5 open for external visual review; production remains blocked and the only next action is external visual review. This adoption is independent of that asset slice and must not alter it. The adoption DoD is protocol artifacts, baseline/after proof, classified inventory, instruction/GitHub integration, a bounded Evidence Bundle, a proposed Checkpoint Delta, and a PR open for independent review.

## CI and GitHub

- Workflows: `.github/workflows/ugas-ci.yml` and `.github/workflows/ugas-review.yml`.
- Existing stable required checks observed in the active ruleset for `main`: `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke`, and `UGAS Review / evidence`.
- Ruleset: `UGAS main PR protection v0.12.4`, active on `main`, requires pull requests, required status checks, up-to-date branches, and blocks force pushes; bypass list is empty.
- Existing PR template was present. The issue-template directory existed but had no templates.
- GitHub CLI was not installed; authenticated browser inspection was available. GitHub operations are recorded separately in the Evidence Bundle.

## Baseline validation

| Area | Command or observation | Result |
| --- | --- | --- |
| Syntax | `python -m compileall -q src scripts tests` | PASS |
| Unit tests | `$env:PYTHONPATH='src'; python -m unittest discover -s tests -q` | PASS, 404 tests, 2 skipped, 0 failures, 262.519 s |
| Official validation | `$env:PYTHONPATH='src'; python scripts/validation/run_validation.py` | PASS, 1,918/1,918 checks |
| Lint | Repository has no configured lint command or lint dependency | NOT_CONFIGURED |
| Typecheck | Repository has no configured typecheck command or typecheck dependency | NOT_CONFIGURED |
| Package/build | `docker compose -f compose.yaml build dashboard` | PASS; image build and package installation completed |
| Docker config | `docker compose -f compose.yaml config` | PASS |
| Dashboard integration | Existing `ugas-dashboard` healthy; `/api/status` HTTP 200; `/api/health` HTTP 200 | PASS with declared degraded capabilities |

## Pre-existing gaps and warnings

- Dashboard `/api/health` was `DEGRADED` because `nvidia-smi` was unavailable, the local ComfyUI endpoint was down, stale-last-known data was present, and canonical QA reported `QA_GAP`. These are existing environment/canonical-state observations, not adoption failures.
- Test output included existing Pillow deprecation/resource warnings; no test failed.
- The Compose image label remains `ugas-dashboard:0.13.0` while the package/runtime state is `0.15.0`; this is a cleanup/configuration candidate, not changed here.
- No dedicated lint, typecheck, dependency-audit, or product integration/E2E command is configured beyond the existing Docker smoke surface.

## Baseline conclusion

The baseline is determinable and technically healthy enough to distinguish adoption regressions. Proceeding is safe within the documented non-product scope. The initial Context Lock is intentionally marked `STALE` after authorized governance files change; the after-change lock is the required authority for post-adoption validation.
