"""Validate the bounded v0.25.0 V1 final acceptance exact-head review manifest fail-closed."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ugas.acceptance_v0250 import BASE_MAIN_SHA, BRANCH, ENVIRONMENT_GATE_IDS, EVIDENCE_ROOT, HARD_GATE_IDS, PR_TITLE, REQUIRED_CAPABILITY_IDS, WORK_ORDER_ID
from ugas.state_consistency_v0250 import CURRENT_GATE, MERGE_AUTHORIZATION, NEXT_ACTION, REQUIRED_CONTEXTS, VERSION

MANIFEST_TYPE = "github-ci-v1-final-acceptance-v0250-review"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
WORK_ORDER_RE = re.compile(r"^wo_[0-9a-f]{16}$")
DISPATCH_RE = re.compile(r"^er_[0-9a-f]{16}$")
GATE_COUNT = len(HARD_GATE_IDS)
CONTROL_FLOOR = 25
CAPABILITY_COUNT = len(REQUIRED_CAPABILITY_IDS)
SUMMARY_EVIDENCE_FILE = "final-acceptance-summary.json"
EVIDENCE_FILES = (
    "capability-matrix-audit.json",
    "architecture-audit.json",
    "security-audit.json",
    "reproducibility-audit.json",
    "state-consistency-audit.json",
    "test-summary.json",
    "hard-gates.json",
    "negative-controls.json",
    "production-boundary.json",
    "uads-handoff.json",
    "final-acceptance-summary.json",
)


def strict_true(value: Any) -> bool:
    return type(value) is bool and value is True


def strict_zero(value: Any) -> bool:
    return type(value) is int and value == 0


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _gate_values_pass(gates: Any) -> bool:
    return (
        isinstance(gates, dict)
        and set(gates) == set(HARD_GATE_IDS)
        and all(
            isinstance(item, dict)
            and item.get("status") == "PASS"
            and strict_true(item.get("observed"))
            and item.get("observed_type") == "bool"
            for item in gates.values()
        )
    )


def _controls_pass(controls: Any) -> bool:
    if not isinstance(controls, dict) or controls.get("status") != "PASS" or controls.get("failures"):
        return False
    records = controls.get("controls") if isinstance(controls.get("controls"), dict) else {}
    control_count = controls.get("control_count")
    if (
        controls.get("minimum_required") != CONTROL_FLOOR
        or type(control_count) is not int
        or control_count < CONTROL_FLOOR
        or len(records) != control_count
        or not all(isinstance(item, dict) and item.get("status") == "PASS" for item in records.values())
    ):
        return False
    strict_gate = records.get("NC-GATE-01") if isinstance(records.get("NC-GATE-01"), dict) else {}
    return (
        strict_gate.get("observed_type") == "str"
        and strict_gate.get("observed_value") == "true"
        and strict_gate.get("observed_gate_status") == "FAIL"
    )

def _inventory_issues(inventory: Any) -> list[str]:
    if not isinstance(inventory, list):
        return ["inventory-not-a-list"]
    issues: list[str] = []
    names = sorted(entry.get("name") for entry in inventory if isinstance(entry, dict))
    if names != sorted(EVIDENCE_FILES):
        issues.append("inventory-names")
    for entry in inventory:
        if not isinstance(entry, dict):
            issues.append("inventory-entry")
            continue
        expected = "SELF_ATTESTATION" if entry.get("name") == SUMMARY_EVIDENCE_FILE else "PRESENT"
        if entry.get("status") != expected:
            issues.append(f"{entry.get('name')}:{entry.get('status')}")
            continue
        if expected == "PRESENT" and (not isinstance(entry.get("sha256"), str) or not DIGEST_RE.fullmatch(entry.get("sha256", ""))):
            issues.append(f"{entry.get('name')}:sha256")
    return issues


def _environment_ok(environment: Any) -> bool:
    gates = environment.get("gates") if isinstance(environment, dict) and isinstance(environment.get("gates"), dict) else {}
    return (
        isinstance(environment, dict)
        and environment.get("status") == "PASS"
        and set(gates) == set(ENVIRONMENT_GATE_IDS)
        and all(gates.get(gate_id) == "PASS" for gate_id in ENVIRONMENT_GATE_IDS)
    )


def _canonical_failures(value: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    evidence_root = ROOT / EVIDENCE_ROOT
    try:
        canonical_gates = load(evidence_root / "hard-gates.json")
        canonical_controls = load(evidence_root / "negative-controls.json")
        canonical_summary = load(evidence_root / SUMMARY_EVIDENCE_FILE)
    except (OSError, json.JSONDecodeError):
        return ["canonical-evidence-unreadable"]
    if canonical_gates.get("gates") != value.get("gates"):
        failures.append("canonical-gates")
    if canonical_controls != value.get("negative_controls"):
        failures.append("canonical-negative-controls")
    summary = value.get("final_acceptance_summary", {})
    for key in ("schema_version", "binding", "work_order_id", "pr_title", "acceptance", "review", "production_boundary", "uads", "evidence_inventory"):
        if summary.get(key) != canonical_summary.get(key):
            failures.append(f"canonical-summary:{key}")
    if summary.get("state_summary") != canonical_summary.get("state_summary"):
        failures.append("canonical-summary:state_summary")
    if value.get("determinism") != canonical_summary.get("determinism"):
        failures.append("canonical-summary:determinism")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--result-output", required=True)
    args = parser.parse_args()
    value = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    failures: list[str] = []
    if value.get("schema_version") != VERSION or value.get("manifest_type") != MANIFEST_TYPE:
        failures.append("identity")
    scope = value.get("scope", {}) if isinstance(value.get("scope"), dict) else {}
    expected_scope = {
        "version": VERSION,
        "work_order_id": WORK_ORDER_ID,
        "phase": "V1_FINAL_ACCEPTANCE",
        "current_gate": CURRENT_GATE,
        "baseline_main_sha": BASE_MAIN_SHA,
        "allowed_next_actions": [NEXT_ACTION],
        "next_candidate": "V1_FINAL_ACCEPTANCE",
        "capability_count": CAPABILITY_COUNT,
        "new_generation": 0,
        "test_only": True,
        "provider_neutral": True,
    }
    failures.extend(f"scope:{key}" for key, expected in expected_scope.items() if scope.get(key) != expected)
    pr = value.get("pull_request", {}) if isinstance(value.get("pull_request"), dict) else {}
    if (
        type(pr.get("number")) is not int
        or pr.get("number", 0) < 1
        or pr.get("base_sha") != BASE_MAIN_SHA
        or not GIT_SHA_RE.fullmatch(str(pr.get("head_sha", "")))
        or pr.get("head_branch") != BRANCH
        or pr.get("base_branch") != "main"
    ):
        failures.append("pull-request")
    if not _gate_values_pass(value.get("gates")):
        failures.append("gates")
    controls = value.get("negative_controls", {}) if isinstance(value.get("negative_controls"), dict) else {}
    if not _controls_pass(controls):
        failures.append("negative-controls")
    determinism = value.get("determinism", {}) if isinstance(value.get("determinism"), dict) else {}
    if determinism.get("status") != "PASS" or determinism.get("run_1") != determinism.get("run_2") or not DIGEST_RE.fullmatch(str(determinism.get("run_1", ""))):
        failures.append("determinism")
    if not _environment_ok(value.get("environment")):
        failures.append("environment")
    acceptance = value.get("acceptance", {}) if isinstance(value.get("acceptance"), dict) else {}
    if (
        acceptance.get("status") != "V1_ACCEPTANCE_CANDIDATE"
        or not strict_true(acceptance.get("acceptance_claim_allowed"))
        or not strict_zero(acceptance.get("critical"))
        or not strict_zero(acceptance.get("high"))
        or not strict_zero(acceptance.get("unresolved_high_critical"))
        or not strict_zero(acceptance.get("medium_blocking_acceptance"))
        or acceptance.get("observability_visual_review") != "PASS"
    ):
        failures.append("acceptance")
    state_validation = value.get("state_validation", {}) if isinstance(value.get("state_validation"), dict) else {}
    if state_validation.get("status") != CURRENT_GATE:
        failures.append("state-validation")
    tests = value.get("tests", {}) if isinstance(value.get("tests"), dict) else {}
    if tests.get("status") != "PASS" or type(tests.get("count")) is not int or tests.get("count", 0) <= 0:
        failures.append("tests")
    validation = value.get("validation", {}) if isinstance(value.get("validation"), dict) else {}
    if validation.get("status") != "PASS" or validation.get("checks") != validation.get("passed") or not strict_zero(validation.get("failed")):
        failures.append("validation")
    changed = value.get("changed_files")
    if not isinstance(changed, list) or not changed or not all(isinstance(item, str) and item for item in changed):
        failures.append("changed-files")
    summary = value.get("final_acceptance_summary", {}) if isinstance(value.get("final_acceptance_summary"), dict) else {}
    binding = summary.get("binding") if isinstance(summary.get("binding"), dict) else {}
    if (
        binding.get("base_main_sha") != BASE_MAIN_SHA
        or binding.get("branch") != BRANCH
        or binding.get("candidate_head") != pr.get("head_sha")
        or binding.get("work_order_id") != WORK_ORDER_ID
        or binding.get("repository") != "KayzenRoot/ugas"
    ):
        failures.append("summary-binding")
    if summary.get("work_order_id") != WORK_ORDER_ID or summary.get("pr_title") != PR_TITLE:
        failures.append("summary-identity")
    inventory_issues = _inventory_issues(summary.get("evidence_inventory"))
    failures.extend(f"summary-inventory:{issue}" for issue in inventory_issues)
    summary_acceptance = summary.get("acceptance") if isinstance(summary.get("acceptance"), dict) else {}
    if summary_acceptance != acceptance:
        failures.append("summary-acceptance")
    summary_review = summary.get("review") if isinstance(summary.get("review"), dict) else {}
    if summary_review.get("pr_number") != pr.get("number") or summary_review.get("pr_head_sha") != pr.get("head_sha") or summary_review.get("pr_state") != "OPEN":
        failures.append("summary-review-binding")
    evidence = value.get("acceptance_evidence")
    if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item.startswith(EVIDENCE_ROOT + "/") for item in evidence):
        failures.append("acceptance-evidence")
    else:
        missing = [item for item in evidence if not (ROOT / item).is_file()]
        if missing:
            failures.append("acceptance-evidence-missing")
    if value.get("uads_handoff_status") != "PASS":
        failures.append("uads-handoff-status")
    uads = value.get("uads_handoff", {}) if isinstance(value.get("uads_handoff"), dict) else {}
    handoff = uads.get("handoff") if isinstance(uads.get("handoff"), dict) else {}
    uads_validation = uads.get("validation") if isinstance(uads.get("validation"), dict) else {}
    if (
        handoff.get("execution_mode") != "GLOBAL_FIRST"
        or handoff.get("project_footprint") != "ZERO"
        or handoff.get("repo_local_material") != "ABSENT"
        or handoff.get("route_status") != "SELECTED"
        or handoff.get("dispatch_status") != "DISPATCHED"
        or not isinstance(handoff.get("selected_profile_id"), str)
        or not handoff.get("selected_profile_id")
        or not WORK_ORDER_RE.fullmatch(str(handoff.get("work_order_id", "")))
        or not DISPATCH_RE.fullmatch(str(handoff.get("run_or_dispatch_id", "")))
        or uads_validation.get("status") != "PASS"
    ):
        failures.append("uads-handoff-semantics")
    if ".uads" in json.dumps(uads):
        failures.append("uads-runtime-path")
    production = value.get("production_boundary", {}) if isinstance(value.get("production_boundary"), dict) else {}
    if (
        production.get("approved") is not False
        or production.get("routing") != "BLOCKED"
        or production.get("real_asset_generation") != "NONE"
        or not strict_zero(production.get("new_generation"))
        or not strict_zero(production.get("provider_submit_calls"))
        or production.get("v1_technical_acceptance_is_not_production_approval") is not True
    ):
        failures.append("production-boundary")
    review = value.get("review_boundary", {}) if isinstance(value.get("review_boundary"), dict) else {}
    if (
        review.get("external_review_required") is not True
        or review.get("do_not_merge") is not True
        or review.get("merge_authorization") != MERGE_AUTHORIZATION
        or review.get("post_bookkeeping_reproof_required") is not True
        or review.get("pr_open_required") is not True
        or review.get("pr_merged") is not False
        or review.get("v1_final_acceptance_started") is not True
        or review.get("provider_generation_started") is not False
        or not set(REQUIRED_CONTEXTS) <= set(review.get("required_contexts", []) if isinstance(review.get("required_contexts"), list) else [])
    ):
        failures.append("review-boundary")
    security = value.get("security_boundary", {}) if isinstance(value.get("security_boundary"), dict) else {}
    if not security or any(security_value is not False for security_value in security.values()):
        failures.append("security-boundary")
    governance = value.get("governance", {}) if isinstance(value.get("governance"), dict) else {}
    if (
        governance.get("work_order_id") != WORK_ORDER_ID
        or governance.get("base_main_sha") != BASE_MAIN_SHA
        or governance.get("branch") != BRANCH
        or governance.get("pr_title") != PR_TITLE
        or governance.get("current_gate") != CURRENT_GATE
    ):
        failures.append("governance")
    failures.extend(_canonical_failures(value))
    if value.get("overall_status") != "PASS":
        failures.append("overall-status")
    result = {"schema_version": VERSION, "status": "PASS" if not failures else "FAIL", "failures": failures, "manifest": str(args.manifest)}
    Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
