"""Fail-closed validator for the v0.22.2 active UI governance binding."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.state_consistency_v0222 import (BASELINE_MAIN_SHA, CANONICAL_CLOSURE_AUTHORITY,
    SUPERSEDED_CLOSURE_AUTHORITY)


class GovernanceContractError(ValueError):
    def __init__(self, rejection_class: str, detail: str):
        self.rejection_class = rejection_class
        super().__init__(f"{rejection_class}: {detail}")


def _require(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise GovernanceContractError(rejection_class, detail)


def validate_binding(value: Mapping[str, Any]) -> dict[str, Any]:
    _require(value.get("schema_version") == "0.22.2", "GOVERNANCE_SCHEMA_INVALID", "schema")
    _require(value.get("baseline_main_sha") == BASELINE_MAIN_SHA, "CLOSURE_PROVENANCE_REJECTED", "historical baseline")
    _require(value.get("canonical_v0213_closure_authority") == CANONICAL_CLOSURE_AUTHORITY, "CLOSURE_AUTHORITY_POINTER_STALE", "canonical authority")
    _require(SUPERSEDED_CLOSURE_AUTHORITY in value.get("superseded_authorities", []), "CLOSURE_AUTHORITY_POINTER_STALE", "superseded authority")
    _require(CANONICAL_CLOSURE_AUTHORITY not in value.get("superseded_authorities", []), "CLOSURE_AUTHORITY_POINTER_STALE", "canonical authority was superseded")
    pr = value.get("pr", {})
    _require(pr.get("number") == 13 and pr.get("state") == "OPEN" and pr.get("merged") is False and pr.get("base_sha") == BASELINE_MAIN_SHA, "PR_BOUNDARY_REJECTED", "PR #13 open/unmerged")
    _require(value.get("historical_roots_immutable") is True, "HISTORICAL_ROOT_MUTATION_REJECTED", "historical roots")
    boundary = value.get("production_boundary", {})
    _require(boundary == {"production_routing": "BLOCKED", "production_approved": False, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "new_generation": 0}, "GOVERNANCE_BOUNDARY_REJECTED", "production boundary")
    scenarios = value.get("lifecycle_scenarios", {})
    _require(tuple(scenarios) == ("review_unresolved", "approved_unmerged", "merged_main_ci_pending_or_failed", "merged_main_ci_success"), "LIFECYCLE_SCENARIO_SET_REJECTED", "four lifecycle scenarios required")
    _require(scenarios["review_unresolved"]["vfx_allowed"] is False and scenarios["approved_unmerged"]["vfx_allowed"] is False and scenarios["merged_main_ci_pending_or_failed"]["vfx_allowed"] is False and scenarios["merged_main_ci_success"]["vfx_allowed"] is True, "LIFECYCLE_GATING_REJECTED", "VFX lifecycle")
    return {"status": "PASS", "canonical_v0213_closure_authority": CANONICAL_CLOSURE_AUTHORITY, "historical_pointer_is_unambiguous": True, "pr_number": 13}


def mutation_control(value: Mapping[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(value)
    mutated["canonical_v0213_closure_authority"] = SUPERSEDED_CLOSURE_AUTHORITY
    try:
        validate_binding(mutated)
    except GovernanceContractError as exc:
        return {"status": "REJECT", "rejection_class": exc.rejection_class, "mutated_field": "canonical_v0213_closure_authority"}
    return {"status": "ACCEPT", "rejection_class": None, "mutated_field": "canonical_v0213_closure_authority"}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("binding", type=Path); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    try:
        value = json.loads(args.binding.read_text(encoding="utf-8")); result = validate_binding(value); result["mutation_control"] = mutation_control(value); result["status"] = "PASS" if result["mutation_control"]["status"] == "REJECT" else "FAIL"
    except (OSError, json.JSONDecodeError, GovernanceContractError) as exc:
        result = {"status": "FAIL", "rejection_class": getattr(exc, "rejection_class", type(exc).__name__), "detail": str(exc)}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(json.dumps(result, ensure_ascii=False)); return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
