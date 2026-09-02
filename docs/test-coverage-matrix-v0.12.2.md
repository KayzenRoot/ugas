# UGAS v0.12.2 coverage matrix

| Requirement | Test/evidence | Status |
|---|---|---|
| F-09 HEAD/worktree/artifact cache binding | `QaCacheBindingTests`, `qa-cache-invalidation-v0122.json` | required |
| QA-NC-01 malformed current-state | API fixture | required |
| QA-NC-02 schema-invalid current-state | API fixture | required |
| QA-NC-03/04 contradictory counts | semantic fixtures | required |
| QA-NC-05 tampered review index | API fixture | required |
| QA-NC-06 production contradiction | state consistency fixture | required |
| QA-NC-07 source mutation after PASS | real cache collector fixture | required |
| QA-NC-08 descendant HEAD with old index | local clone and real Git commit | required |
| F-11 collector/API stale-last-known | `test_stale_last_known_flows_through_refresh_and_http_api` | required |
| F-12 generation instrumentation | fake provider through `_run_job` | required |
| Docker bind/security/persistence | Compose normalized/runtime evidence | required |
| Host command and file watcher | shared SQLite/API evidence | required |
| Existing and historical regressions | `python -m unittest discover -s tests -q` and `run_validation.py` | required |
