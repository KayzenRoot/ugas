# Cleanup Inventory - ENG-PROTOCOL-ADOPTION-001

Status: `INVENTORY_ONLY`; no cleanup was executed.

## Method and limits

The inventory used tracked-file enumeration, `rg` searches, package/import inspection, existing validation references, GitHub workflow/configuration inspection, and the existing test/validation suite. `ruff`, `pyflakes`, and `mypy` are not installed and no repository lint/typecheck configuration exists; therefore absence of a static finding is not proof of dead code. Dynamic use through imports, historical snapshots, contracts, plugins, CLI, serialization, and validation is treated as potential use.

## Classified candidates

| Candidate | Classification | Evidence | Safe action in this increment |
| --- | --- | --- | --- |
| `src/ugas/state_consistency_v*.py` and matching `scripts/validation/*v*.py` | `UNKNOWN` | `run_validation.py` imports or invokes multiple historical validators; dedicated versioned tests and preserved evidence reference them. | Preserve; characterize each historical boundary before any removal. |
| `REVIEW-v*.md` and `docs/evidence/**` historical records | `UNKNOWN` | Current validators require historical paths, hashes, snapshots, and negative controls. | Preserve; never delete as documentation duplication. |
| `profiles/animation/**.json` `feature_flags` blocks | `UNKNOWN` | Flags are part of versioned QA contracts and are consumed by animation/runtime validators. | Preserve; verify ownership and lifecycle in a future Work Order. |
| `compose.yaml` image `ugas-dashboard:0.13.0` versus runtime/package `0.15.0` | `DUPLICATE_OR_OBSOLETE` | Static configuration/version mismatch observed; changing it could alter the always-on dashboard deployment. | Owner review and a dedicated config Work Order; do not change here. |
| `docs/2d-master-pipeline.md` mixed active/history wording | `DUPLICATE_OR_OBSOLETE` | The file contains a v0.15 active paragraph and older v0.12.3 active-release wording. | Resolve narrative authority in a documentation-only Work Order; do not rewrite history here. |
| `tmp/**`, `.ugas/runtime/**`, `__pycache__/**` | `GENERATED_OR_VENDORED` | Runtime/cache outputs are ignored or mounted operational data, not product source. | Preserve; no broad local deletion was authorized. |
| `_smoke_decoded.txt`, `tmp_explore*.py/json`, `tmp_explore_death_v151.out.json` | `UNKNOWN` | Existing untracked user artifacts were present before adoption and may contain investigation context. | Preserve; do not delete user work. |
| Unused imports/exports | `UNKNOWN` | No configured ruff/pyflakes analyzer; manual scan cannot prove absence under dynamic Python usage. | Add/approve a static-audit Work Order before removal. |
| Unused dependencies | `UNKNOWN` | Pillow and psutil have observed imports; no lock/audit tool is configured for a complete transitive-use decision. | Keep dependencies; perform a separate dependency audit. |
| Test helpers/fixtures and provider/workflow registries | `UNKNOWN` | Dynamic registry loading, CLI routing, historical replay, and tests make reachability non-local. | Preserve; build an import/registry characterization map first. |

## No `VERIFIED_DEAD` findings

No candidate met the proof threshold for `VERIFIED_DEAD`. Suspicion, naming, age, duplicated version suffixes, or lack of a direct static import is insufficient under this project's historical-evidence and dynamic-registry contracts.

No candidate is currently classified `PROBABLY_DEAD`; that classification remains available for a future review when evidence is stronger than the current dynamic-use uncertainty.

## Recommended future increments, lowest risk first

1. Resolve documentation ownership for the mixed active/history language in `docs/2d-master-pipeline.md` without deleting historical records.
2. Confirm the Compose image tag/runtime version relationship and update it only under a dedicated operational Work Order with Docker reproof.
3. Add an approved static lint/import analysis tool and characterize dynamic registry/CLI paths.
4. Audit historical validators and state-consistency modules one version at a time against `run_validation.py`, tests, and snapshot evidence.
5. Audit dependency declarations and test fixtures with a reproducible dependency graph.
6. Remove only individually proven `VERIFIED_DEAD` items in small PRs with independent review and before/after validation.

## Safety conclusion

The inventory is evidence for future work, not authorization to clean. The adoption PR must stop after handoff and independent review; it must not start item 1 automatically.
