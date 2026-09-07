"""Fail-closed validator for the v0.22.1 corrected PR #12 binding."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Mapping


class GovernanceContractError(ValueError):
    def __init__(self, rejection_class: str, detail: str):
        self.rejection_class = rejection_class
        super().__init__(f"{rejection_class}: {detail}")


EXPECTED_BASE = "0c9b721b43d3cc12605ce009f6e0deb232b00045"
EXPECTED_APPROVED_HEAD = "a019784d2c4fcd0751f61fe70509cadc32888a0e"
EXPECTED_MERGE = "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3"
MAIN_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke")
PR_CONTEXTS = (*MAIN_CONTEXTS, "UGAS Review / evidence")


def _require(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise GovernanceContractError(rejection_class, detail)


def validate_binding(value: Mapping[str, Any]) -> dict[str, Any]:
    _require(value.get("schema_version") == "0.22.1", "GOVERNANCE_SCHEMA_INVALID", "schema")
    _require(value.get("closure_branch_base_sha") == EXPECTED_BASE, "CLOSURE_PROVENANCE_REJECTED", "closure branch base")
    _require(value.get("closure_approved_head_sha") == EXPECTED_APPROVED_HEAD, "CLOSURE_PROVENANCE_REJECTED", "approved head")
    _require(value.get("closure_merge_commit_sha") == EXPECTED_MERGE and value.get("current_ui_base_main_sha") == EXPECTED_MERGE, "CLOSURE_PROVENANCE_REJECTED", "merge/current UI base")
    pr = value.get("closure_pr", {})
    _require(pr.get("number") == 12 and pr.get("merged") is True and pr.get("state") == "CLOSED", "CLOSURE_PROVENANCE_REJECTED", "PR state")
    _require(pr.get("base_sha") == EXPECTED_BASE and pr.get("approved_head_sha") == EXPECTED_APPROVED_HEAD and pr.get("merge_commit_sha") == EXPECTED_MERGE, "CLOSURE_PROVENANCE_REJECTED", "PR identities")
    _require(pr.get("approved_head_to_merge") == {"changed_files": 0, "runtime_semantics_changed": False}, "CLOSURE_PROVENANCE_REJECTED", "approved-head to merge")
    pre = value.get("pre_merge_reproof", {})
    _require(pre.get("head_sha") == EXPECTED_APPROVED_HEAD, "CLOSURE_PROVENANCE_REJECTED", "pre-merge head")
    pre_contexts = pre.get("required_contexts", [])
    _require(tuple(item.get("name") for item in pre_contexts) == PR_CONTEXTS, "CLOSURE_CONTEXT_PROVENANCE_REJECTED", "pre-merge context names")
    expected_pre_ids = {"UGAS CI / unit-and-validation": 101598088447, "UGAS CI / docker-smoke": 101598088599, "UGAS Review / evidence": 101598088631}
    for item in pre_contexts:
        _require(item.get("head_sha") == EXPECTED_APPROVED_HEAD and item.get("status") == "completed" and item.get("conclusion") == "success" and item.get("check_run_id") == expected_pre_ids.get(item.get("name")) and type(item.get("workflow_run_id")) is int, "CLOSURE_CONTEXT_PROVENANCE_REJECTED", item.get("name", "context"))
    ci = value.get("post_merge_main_ci", {})
    _require(ci.get("commit_sha") == EXPECTED_MERGE and ci.get("workflow_run_id") == 34076307186, "MAIN_CI_PROVENANCE_REJECTED", "main workflow")
    contexts = ci.get("contexts", [])
    _require(tuple(item.get("name") for item in contexts) == MAIN_CONTEXTS and tuple(ci.get("supported_contexts", [])) == MAIN_CONTEXTS, "MAIN_CI_CONTEXT_SET_REJECTED", "main context set")
    expected_main_ids = {"UGAS CI / unit-and-validation": 101602993848, "UGAS CI / docker-smoke": 101602993941}
    for item in contexts:
        _require(item.get("head_sha") == EXPECTED_MERGE and item.get("workflow_run_id") == 34076307186 and item.get("status") == "completed" and item.get("conclusion") == "success" and item.get("check_run_id") == expected_main_ids.get(item.get("name")), "MAIN_CI_PROVENANCE_REJECTED", item.get("name", "context"))
    _require(ci.get("review_evidence_absent") is True and ci.get("unit_tests") == {"passed": 573, "failed": 0} and ci.get("official_validation") == {"passed": 2563, "failed": 0}, "MAIN_CI_PROVENANCE_REJECTED", "main counts or review absence")
    _require(value.get("historical_roots_immutable") is True and value.get("production_routing") == "BLOCKED" and value.get("production_approved") is False and value.get("new_generation") == 0, "GOVERNANCE_BOUNDARY_REJECTED", "historical/production boundary")
    return {"status": "PASS", "closure_base_sha": EXPECTED_BASE, "approved_head_sha": EXPECTED_APPROVED_HEAD, "merge_commit_sha": EXPECTED_MERGE, "pre_merge_context_count": len(pre_contexts), "post_merge_main_context_count": len(contexts), "main_review_context_fabricated": False}


def mutation_control(value: Mapping[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(value)
    mutated["post_merge_main_ci"]["contexts"][0]["check_run_id"] = 101598088447
    try:
        validate_binding(mutated)
    except GovernanceContractError as exc:
        return {"status": "REJECT", "rejection_class": exc.rejection_class, "mutated_field": "post_merge_main_ci.contexts[0].check_run_id"}
    return {"status": "ACCEPT", "rejection_class": None, "mutated_field": "post_merge_main_ci.contexts[0].check_run_id"}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("binding", type=Path); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    try:
        value = json.loads(args.binding.read_text(encoding="utf-8")); result = validate_binding(value); mutation = mutation_control(value); result["mutation_control"] = mutation; result["status"] = "PASS" if mutation.get("status") == "REJECT" else "FAIL"
    except (OSError, json.JSONDecodeError, GovernanceContractError) as exc:
        result = {"status": "FAIL", "rejection_class": getattr(exc, "rejection_class", type(exc).__name__), "detail": str(exc)}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(json.dumps(result, ensure_ascii=False)); return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
