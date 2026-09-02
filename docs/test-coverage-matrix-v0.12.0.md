# UGAS v0.12.0 test coverage matrix

| Contract | Automated proof | Evidence / boundary |
|---|---|---|
| Structured event model and redaction | `tests/test_observability_v0120.py` event tests | bounded fields, monotonic timestamps, secrets redacted |
| SQLite WAL store and retention | `tests/test_observability_v0120.py` store tests | restart/readback and bounded rows |
| GPU supported, missing and timeout states | `tests/test_observability_v0120.py` collector tests | explicit `GPU_AVAILABLE` or `GPU_UNAVAILABLE`, never fabricated zero |
| Allowlisted file activity and stable hashes | `tests/test_observability_v0120.py` activity tests | create/update, stable SHA-256, cleanup |
| Preview traversal and sensitive-file rejection | `tests/test_observability_v0120.py` preview tests | fail-closed safe IDs and roots |
| Canonical state/review-index malformed evidence | `tests/test_observability_v0120.py` governance tests | `GAP`/`ERROR`, no silent PASS |
| Read-only API and SSE reconnect | `tests/test_observability_v0120.py` HTTP tests | required endpoints, 405 mutations, snapshot/live stream |
| CLI startup and loopback binding | `tests/test_observability_v0120.py` CLI/security tests | ephemeral port, startup record, non-loopback rejection |
| Historical animation integrity | full suite plus v0.11.2 hash evidence | no v0.11.2 GIF/sheet/frame/motion edit |
| Full regression and validation | `python -m unittest discover -s tests -q`; `python scripts/validation/run_validation.py` | final counts recorded in `docs/evidence/observability-v0120/` |

The dashboard is local-only, read-only, has no telemetry upload, and does not grant production approval. External review of the dashboard remains `REQUIRED`.
