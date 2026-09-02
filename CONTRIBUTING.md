# Contributing to UGAS

UGAS uses a PR-first review protocol. Start from the verified `main` baseline, work on a feature branch, publish a Pull Request, wait for `UGAS CI / unit-and-validation` and `UGAS CI / docker-smoke`, and provide the bounded GitHub review artifact. Do not merge your own PR.

Every PR must use the repository template and state its objective, exact base/head, scope and out-of-scope work, changed files, architecture decisions, tests, validation, Docker/dashboard status, evidence/visuals, risks, known gaps, production boundary and STOP condition. The active `CHECKPOINT.md` and `docs/evidence/current-state.json` are authoritative for the current gate.

Do not upload secrets, model weights, telemetry databases, local credentials or large generation directories. Preserve rejected historical evidence. Local technical qualification is not external approval, and `production_routing=BLOCKED` remains the default until a separately authorized gate changes it.

See [docs/github-review-protocol.md](docs/github-review-protocol.md) for workflow names and artifact details.
