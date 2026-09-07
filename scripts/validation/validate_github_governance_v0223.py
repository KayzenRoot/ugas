"""Fail-closed validator for the v0.22.3 active UI governance binding."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.state_consistency_v0223 import (BASELINE_MAIN_SHA, CANONICAL_CLOSURE_AUTHORITY,
    FINAL_CLOSURE_APPROVED_HEAD, FINAL_CLOSURE_MERGE_SHA, HISTORICAL_PR11_AUTHORITY,
    SUPERSEDED_CLOSURE_AUTHORITY)

FINAL_CLOSURE_PATH = ROOT / CANONICAL_CLOSURE_AUTHORITY
FINAL_CLOSURE_BRANCH_BASE = "0c9b721b43d3cc12605ce009f6e0deb232b00045"
FINAL_CLOSURE_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke")


class GovernanceContractError(ValueError):
    def __init__(self, rejection_class: str, detail: str):
        self.rejection_class = rejection_class
        super().__init__(f"{rejection_class}: {detail}")


def _require(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise GovernanceContractError(rejection_class, detail)


def validate_final_closure_record(record: Mapping[str, Any]) -> dict[str, Any]:
    _require(record.get("schema_version") == "0.22.1", "FINAL_CLOSURE_RECORD_INVALID", "schema")
    _require(record.get("record_type") == "post_merge_closure_completion_binding_v2", "FINAL_CLOSURE_RECORD_INVALID", "record type")
    _require(record.get("repository") == "KayzenRoot/ugas" and record.get("source_mode") == "GITHUB_LIVE", "FINAL_CLOSURE_RECORD_INVALID", "repository/source")
    _require(record.get("closure_branch_base_sha") == FINAL_CLOSURE_BRANCH_BASE, "FINAL_CLOSURE_RECORD_INVALID", "closure branch base")
    _require(record.get("closure_approved_head_sha") == FINAL_CLOSURE_APPROVED_HEAD, "FINAL_CLOSURE_RECORD_INVALID", "approved head")
    _require(record.get("closure_merge_commit_sha") == FINAL_CLOSURE_MERGE_SHA and record.get("current_ui_base_main_sha") == FINAL_CLOSURE_MERGE_SHA, "FINAL_CLOSURE_RECORD_INVALID", "merge/current main")
    pr = record.get("closure_pr", {})
    _require(pr.get("number") == 12 and pr.get("state") == "CLOSED" and pr.get("merged") is True and pr.get("approved_head_sha") == FINAL_CLOSURE_APPROVED_HEAD and pr.get("merge_commit_sha") == FINAL_CLOSURE_MERGE_SHA, "FINAL_CLOSURE_RECORD_INVALID", "PR #12 lifecycle")
    pre = record.get("pre_merge_reproof", {})
    pre_contexts = pre.get("required_contexts", [])
    _require(pre.get("pr_number") == 12 and pre.get("head_sha") == FINAL_CLOSURE_APPROVED_HEAD and tuple(item.get("name") for item in pre_contexts) == ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence") and all(item.get("status") == "completed" and item.get("conclusion") == "success" and item.get("head_sha") == FINAL_CLOSURE_APPROVED_HEAD for item in pre_contexts), "FINAL_CLOSURE_RECORD_INVALID", "pre-merge provenance")
    main_ci = record.get("post_merge_main_ci", {})
    main_contexts = main_ci.get("contexts", [])
    _require(main_ci.get("commit_sha") == FINAL_CLOSURE_MERGE_SHA and tuple(main_ci.get("supported_contexts", [])) == FINAL_CLOSURE_CONTEXTS and tuple(item.get("name") for item in main_contexts) == FINAL_CLOSURE_CONTEXTS and all(item.get("status") == "completed" and item.get("conclusion") == "success" and item.get("head_sha") == FINAL_CLOSURE_MERGE_SHA and isinstance(item.get("workflow_run_id"), int) and isinstance(item.get("check_run_id"), int) for item in main_contexts), "FINAL_CLOSURE_RECORD_INVALID", "post-merge main provenance")
    _require(record.get("post_merge_main_ci", {}).get("review_evidence_absent") is True and all(item.get("name") != "UGAS Review / evidence" for item in main_contexts), "FINAL_CLOSURE_RECORD_INVALID", "main review context")
    return {"status": "PASS", "closure_pr_number": 12, "closure_pr_state": "CLOSED", "closure_merged": True, "closure_approved_head_sha": FINAL_CLOSURE_APPROVED_HEAD, "closure_merge_commit_sha": FINAL_CLOSURE_MERGE_SHA, "post_merge_main_commit_sha": FINAL_CLOSURE_MERGE_SHA, "review_evidence_absent": True}


def validate_binding(value: Mapping[str, Any], final_record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _require(value.get("schema_version") == "0.22.3", "GOVERNANCE_SCHEMA_INVALID", "schema")
    _require(value.get("baseline_main_sha") == BASELINE_MAIN_SHA, "CLOSURE_PROVENANCE_REJECTED", "historical baseline")
    _require(value.get("canonical_v0213_closure_authority") == CANONICAL_CLOSURE_AUTHORITY, "CLOSURE_AUTHORITY_POINTER_STALE", "canonical authority")
    _require(value.get("historical_prerequisite") == HISTORICAL_PR11_AUTHORITY, "CLOSURE_AUTHORITY_POINTER_STALE", "historical prerequisite")
    _require(HISTORICAL_PR11_AUTHORITY in value.get("superseded_authorities", []), "CLOSURE_AUTHORITY_POINTER_STALE", "PR #11 authority must be historical")
    _require(SUPERSEDED_CLOSURE_AUTHORITY in value.get("superseded_authorities", []), "CLOSURE_AUTHORITY_POINTER_STALE", "superseded authority")
    _require(CANONICAL_CLOSURE_AUTHORITY not in value.get("superseded_authorities", []), "CLOSURE_AUTHORITY_POINTER_STALE", "canonical authority was superseded")
    final = value.get("final_closure_authority", {})
    _require(final.get("path") == CANONICAL_CLOSURE_AUTHORITY and final.get("record_type") == "post_merge_closure_completion_binding_v2", "CLOSURE_AUTHORITY_POINTER_STALE", "final closure authority path")
    record = dict(final_record) if final_record is not None else json.loads(FINAL_CLOSURE_PATH.read_text(encoding="utf-8"))
    final_result = validate_final_closure_record(record)
    _require(final.get("closure_pr_number") == final_result["closure_pr_number"] and final.get("closure_pr_state") == final_result["closure_pr_state"] and final.get("closure_merged") is final_result["closure_merged"] and final.get("closure_merge_commit_sha") == final_result["closure_merge_commit_sha"], "CLOSURE_AUTHORITY_CONTENT_REJECTED", "wrapper does not bind final lifecycle")
    pr = value.get("pr", {})
    _require(pr.get("number") == 13 and pr.get("state") == "OPEN" and pr.get("merged") is False and pr.get("base_sha") == BASELINE_MAIN_SHA, "PR_BOUNDARY_REJECTED", "PR #13 open/unmerged")
    _require(value.get("historical_roots_immutable") is True, "HISTORICAL_ROOT_MUTATION_REJECTED", "historical roots")
    boundary = value.get("production_boundary", {})
    _require(boundary == {"production_routing": "BLOCKED", "production_approved": False, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "new_generation": 0}, "GOVERNANCE_BOUNDARY_REJECTED", "production boundary")
    scenarios = value.get("lifecycle_scenarios", {})
    _require(tuple(scenarios) == ("review_unresolved", "approved_unmerged", "merged_main_ci_pending_or_failed", "merged_main_ci_success"), "LIFECYCLE_SCENARIO_SET_REJECTED", "four lifecycle scenarios required")
    _require(scenarios["review_unresolved"]["vfx_allowed"] is False and scenarios["approved_unmerged"]["vfx_allowed"] is False and scenarios["merged_main_ci_pending_or_failed"]["vfx_allowed"] is False and scenarios["merged_main_ci_success"]["vfx_allowed"] is True, "LIFECYCLE_GATING_REJECTED", "VFX lifecycle")
    return {"status": "PASS", "canonical_v0213_closure_authority": CANONICAL_CLOSURE_AUTHORITY, "historical_pointer_is_unambiguous": True, "final_closure": final_result, "pr_number": 13}


def mutation_control(value: Mapping[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(value)
    mutated["canonical_v0213_closure_authority"] = HISTORICAL_PR11_AUTHORITY
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
