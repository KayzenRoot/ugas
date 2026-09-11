"""Build the bounded exact-head UGAS V1 final acceptance review manifest (v0.25.0)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
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


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def strict_true(value: Any) -> bool:
    return type(value) is bool and value is True


def _git_changed(root: Path, base_ref: str, head_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return sorted(item for item in result.stdout.splitlines() if item)


def _all_gate_values_pass(gates: Any) -> bool:
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
    return (
        controls.get("minimum_required") == CONTROL_FLOOR
        and type(control_count) is int
        and control_count >= CONTROL_FLOOR
        and len(records) == control_count
        and all(isinstance(item, dict) and item.get("status") == "PASS" for item in records.values())
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
        expected = "SELF_ATTESTATION" if entry.get("name") == "final-acceptance-summary.json" else "PRESENT"
        if entry.get("status") != expected:
            issues.append(f"{entry.get('name')}:{entry.get('status')}")
    return issues


def _environment_ok(environment: Any) -> bool:
    gates = environment.get("gates") if isinstance(environment, dict) and isinstance(environment.get("gates"), dict) else {}
    return environment.get("status") == "PASS" and all(gates.get(gate_id) == "PASS" for gate_id in ENVIRONMENT_GATE_IDS)


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "output-dir",
        "repository-root",
        "base-ref",
        "head-ref",
        "head-branch",
        "tests-json",
        "validation-json",
        "state-validation-json",
        "summary-json",
        "gates-json",
        "controls-json",
        "uads-json",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--pr-number", required=True, type=int)
    args = parser.parse_args()
    root = Path(args.repository_root).resolve()
    state = load(root / "docs/evidence/current-state.json")
    tests = load(Path(args.tests_json))
    validation = load(Path(args.validation_json))
    state_validation = load(Path(args.state_validation_json))
    summary = load(Path(args.summary_json))
    gates = load(Path(args.gates_json))
    controls = load(Path(args.controls_json))
    uads_handoff = load(Path(args.uads_json))
    binding = summary.get("binding") if isinstance(summary.get("binding"), dict) else {}
    acceptance = summary.get("acceptance") if isinstance(summary.get("acceptance"), dict) else {}
    determinism = summary.get("determinism") if isinstance(summary.get("determinism"), dict) else {}
    environment = summary.get("environment") if isinstance(summary.get("environment"), dict) else {}
    review = summary.get("review") if isinstance(summary.get("review"), dict) else {}
    uads_summary = summary.get("uads") if isinstance(summary.get("uads"), dict) else {}
    production = summary.get("production_boundary") if isinstance(summary.get("production_boundary"), dict) else {}
    inventory = summary.get("evidence_inventory")
    state_summary = summary.get("state_summary") if isinstance(summary.get("state_summary"), dict) else {}
    state_review = state.get("review") if isinstance(state.get("review"), dict) else {}
    handoff = uads_handoff.get("handoff") if isinstance(uads_handoff.get("handoff"), dict) else {}
    uads_validation = uads_handoff.get("validation") if isinstance(uads_handoff.get("validation"), dict) else {}
    changed = _git_changed(root, args.base_ref, args.head_ref)
    evidence_files = sorted(path.relative_to(root).as_posix() for path in (root / EVIDENCE_ROOT).rglob("*") if path.is_file())
    gate_values = gates.get("gates", {})
    inventory_issues = _inventory_issues(inventory)
    exact_refs = bool(GIT_SHA_RE.fullmatch(args.base_ref)) and bool(GIT_SHA_RE.fullmatch(args.head_ref))
    overall = (
        exact_refs
        and args.base_ref == BASE_MAIN_SHA
        and args.pr_number >= 1
        and args.head_branch == BRANCH
        and tests.get("status") == "PASS"
        and isinstance(tests.get("count"), int)
        and tests.get("count") > 0
        and validation.get("status") == "PASS"
        and validation.get("checks") == validation.get("passed")
        and validation.get("failed") == 0
        and state_validation.get("status") == CURRENT_GATE
        and binding.get("base_main_sha") == BASE_MAIN_SHA
        and binding.get("branch") == BRANCH
        and binding.get("work_order_id") == WORK_ORDER_ID
        and binding.get("repository") == "KayzenRoot/ugas"
        and binding.get("candidate_head") == args.head_ref
        and summary.get("pr_title") == PR_TITLE
        and summary.get("work_order_id") == WORK_ORDER_ID
        and state.get("version") == VERSION
        and state.get("phase") == "V1_FINAL_ACCEPTANCE"
        and state.get("current_gate") == CURRENT_GATE
        and state.get("acceptance_verdict") == "V1_ACCEPTANCE_CANDIDATE"
        and state.get("baseline_main_sha") == BASE_MAIN_SHA
        and state.get("orchestration_lifecycle") == "MERGED_CLOSED"
        and state.get("allowed_next_actions") == [NEXT_ACTION]
        and state.get("production_approved") is False
        and state.get("production_routing") == "BLOCKED"
        and state.get("real_asset_generation") == "NONE"
        and state.get("new_generation") == 0
        and state.get("provider_submit_calls") == 0
        and state_review.get("pr_state") == "OPEN"
        and state_review.get("do_not_merge") is True
        and state_review.get("merge_authorization") == MERGE_AUTHORIZATION
        and state_review.get("pr_number") in (0, args.pr_number)
        and acceptance.get("status") == "V1_ACCEPTANCE_CANDIDATE"
        and acceptance.get("acceptance_claim_allowed") is True
        and acceptance.get("critical") == 0
        and acceptance.get("high") == 0
        and acceptance.get("unresolved_high_critical") == 0
        and acceptance.get("medium_blocking_acceptance") == 0
        and acceptance.get("observability_visual_review") == "PASS"
        and _all_gate_values_pass(gate_values)
        and controls.get("status") == "PASS"
        and controls.get("minimum_required") == CONTROL_FLOOR
        and _controls_pass(controls)
        and determinism.get("status") == "PASS"
        and determinism.get("run_1") == determinism.get("run_2")
        and all(isinstance(value, str) and DIGEST_RE.fullmatch(value) for value in (determinism.get("run_1"), determinism.get("run_2")))
        and _environment_ok(environment)
        and production.get("production_approved") is False
        and production.get("production_routing") == "BLOCKED"
        and production.get("real_asset_generation") == "NONE"
        and production.get("new_generation") == 0
        and production.get("provider_submit_calls") == 0
        and production.get("v1_technical_acceptance_is_not_production_approval") is True
        and review.get("pr_number") == args.pr_number
        and review.get("pr_head_sha") == args.head_ref
        and review.get("pr_state") == "OPEN"
        and review.get("do_not_merge") is True
        and review.get("external_review_required") is True
        and review.get("merge_authorization") == MERGE_AUTHORIZATION
        and set(REQUIRED_CONTEXTS) <= set(review.get("required_contexts", []))
        and state_summary.get("acceptance_verdict") == "V1_ACCEPTANCE_CANDIDATE"
        and state_summary.get("production_approved") is False
        and state_summary.get("production_routing") == "BLOCKED"
        and handoff.get("execution_mode") == "GLOBAL_FIRST"
        and handoff.get("project_footprint") == "ZERO"
        and handoff.get("repo_local_material") == "ABSENT"
        and handoff.get("route_status") == "SELECTED"
        and handoff.get("dispatch_status") == "DISPATCHED"
        and isinstance(handoff.get("work_order_id"), str)
        and WORK_ORDER_RE.fullmatch(handoff.get("work_order_id", "")) is not None
        and isinstance(handoff.get("run_or_dispatch_id"), str)
        and DISPATCH_RE.fullmatch(handoff.get("run_or_dispatch_id", "")) is not None
        and bool(handoff.get("selected_profile_id"))
        and uads_validation.get("status") == "PASS"
        and uads_summary.get("dispatch_status") == "DISPATCHED"
        and uads_summary.get("work_order_id") == handoff.get("work_order_id")
        and ".uads" not in json.dumps(uads_handoff)
        and not inventory_issues
        and len(EVIDENCE_FILES) == 11
        and len(REQUIRED_CAPABILITY_IDS) == 16
        and bool(changed)
    )
    value = {
        "schema_version": VERSION,
        "manifest_type": MANIFEST_TYPE,
        "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"},
        "pull_request": {"number": args.pr_number, "base_sha": args.base_ref, "head_sha": args.head_ref, "merge_base_sha": args.base_ref, "head_branch": args.head_branch, "base_branch": "main"},
        "scope": {"version": VERSION, "work_order_id": WORK_ORDER_ID, "phase": "V1_FINAL_ACCEPTANCE", "current_gate": CURRENT_GATE, "baseline_main_sha": BASE_MAIN_SHA, "allowed_next_actions": [NEXT_ACTION], "next_candidate": "V1_FINAL_ACCEPTANCE", "capability_count": len(REQUIRED_CAPABILITY_IDS), "new_generation": 0, "test_only": True, "provider_neutral": True},
        "changed_files": changed,
        "change_statistics": {"files": len(changed)},
        "current_state": {"path": "docs/evidence/current-state.json", "version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "acceptance_verdict": state.get("acceptance_verdict"), "tracked_pr_number": state_review.get("pr_number"), "tracked_head_sha": state_review.get("head_sha"), "head_sha_source": state_review.get("head_sha_source"), "production_approved": state.get("production_approved"), "production_routing": state.get("production_routing"), "allowed_next_actions": state.get("allowed_next_actions")},
        "tests": tests,
        "validation": validation,
        "state_validation": state_validation,
        "gates": gate_values,
        "negative_controls": controls,
        "determinism": determinism,
        "environment": environment,
        "acceptance": acceptance,
        "final_acceptance_summary": {"schema_version": summary.get("schema_version"), "binding": binding, "generated_at": summary.get("generated_at"), "work_order_id": summary.get("work_order_id"), "pr_title": summary.get("pr_title"), "acceptance": acceptance, "state_summary": state_summary, "review": review, "production_boundary": production, "uads": uads_summary, "findings": summary.get("findings"), "evidence_inventory": inventory},
        "acceptance_evidence": evidence_files,
        "uads_handoff": uads_handoff,
        "uads_handoff_status": "PASS" if handoff.get("route_status") == "SELECTED" and handoff.get("dispatch_status") == "DISPATCHED" and uads_validation.get("status") == "PASS" else "FAIL",
        "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_asset_generation": "NONE", "synthetic_fixture": "TEST_ONLY", "provider_submit_calls": 0, "v1_technical_acceptance_is_not_production_approval": True, "production_readiness_workstream": "NOT_STARTED_REQUIRED_SEPARATELY"},
        "review_boundary": {"external_review_required": True, "do_not_merge": True, "merge_authorization": MERGE_AUTHORIZATION, "post_bookkeeping_reproof_required": True, "pr_open_required": True, "pr_merged": False, "v1_final_acceptance_started": True, "provider_generation_started": False, "required_contexts": list(REQUIRED_CONTEXTS)},
        "governance": {"work_order_id": WORK_ORDER_ID, "base_main_sha": BASE_MAIN_SHA, "branch": BRANCH, "pr_title": PR_TITLE, "current_gate": CURRENT_GATE},
        "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False},
        "overall_status": "PASS" if overall else "FAIL",
        "overall_failures": sorted(
            name
            for name, observed in {
                "exact-refs": exact_refs,
                "pr-number-positive": args.pr_number >= 1,
                "tests": tests.get("status") == "PASS",
                "validation": validation.get("status") == "PASS",
                "state-validation": state_validation.get("status") == CURRENT_GATE,
                "gates": _all_gate_values_pass(gate_values),
                "controls": _controls_pass(controls),
                "determinism": determinism.get("status") == "PASS",
                "environment": _environment_ok(environment),
                "acceptance": acceptance.get("status") == "V1_ACCEPTANCE_CANDIDATE",
                "evidence-inventory": not inventory_issues,
                "uads-handoff": handoff.get("dispatch_status") == "DISPATCHED" and uads_validation.get("status") == "PASS",
                "changed-files": bool(changed),
            }.items()
            if not observed
        ),
    }
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "github-review-manifest-v0250.json").write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "v0250_GITHUB_REVIEW_MANIFEST_BUILT", "overall_status": value["overall_status"], "overall_failures": value["overall_failures"], "head_sha": args.head_ref, "pr_number": args.pr_number}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
