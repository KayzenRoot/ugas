"""Build the bounded exact-head v0.24.7 review manifest."""

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
from ugas.state_consistency_v0247 import APPROVAL_AUTHORIZATION, APPROVAL_COMMENT_ID, APPROVAL_RECORD, APPROVED_SEMANTIC_HEAD, CURRENT_GATE, NEXT_ACTION, REJECTED_REVIEWED_HEAD, VERSION as STATE_VERSION

VERSION = STATE_VERSION
BASE_MAIN = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
REJECTED_HEAD = REJECTED_REVIEWED_HEAD
EVIDENCE = "docs/evidence/orchestration-runtime-v0247"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _all_gate_values_pass(gates: dict[str, Any]) -> bool:
    return isinstance(gates, dict) and len(gates) >= 62 and all(
        isinstance(item, dict)
        and item.get("status") == "PASS"
        and type(item.get("observed")) is bool
        and item.get("observed") is True
        and item.get("observed_type") == "bool"
        for item in gates.values()
    )


def _all_controls_reject(controls: dict[str, Any]) -> bool:
    if len(controls) < 69:
        return False
    for item in controls.values():
        if not isinstance(item, dict) or item.get("status") != "PASS":
            return False
        expected = item.get("expected_rejection_class")
        if expected is None:
            if item.get("result") not in {None, "REJECT"}:
                return False
            continue
        if item.get("result") != "REJECT":
            return False
        observed = item.get("observed_rejection_class")
        if item.get("control_id") == "NC-GATE-01":
            if item.get("observed_type") != "str" or item.get("observed_value") != "true" or item.get("observed_gate_status") != "FAIL":
                return False
        elif observed != expected or not item.get("actual_exception"):
            return False
    return True


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
        "gates-json",
        "controls-json",
        "determinism-json",
        "production-json",
        "provider-json",
        "family-json",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--pr-number", required=True, type=int)
    args = parser.parse_args()
    root = Path(args.repository_root).resolve()
    state = load(root / "docs/evidence/current-state.json")
    tests = load(Path(args.tests_json))
    validation = load(Path(args.validation_json))
    state_validation = load(Path(args.state_validation_json))
    gates = load(Path(args.gates_json))
    controls = load(Path(args.controls_json))
    determinism = load(Path(args.determinism_json))
    production = load(Path(args.production_json))
    provider = load(Path(args.provider_json))
    family = load(Path(args.family_json))
    execution = load(root / f"{EVIDENCE}/execution-evidence-v0247.json")
    authority = load(root / f"{EVIDENCE}/dependency-authority-v0247.json")
    uads_handoff = load(root / f"{EVIDENCE}/uads-handoff-v0247.json")
    canonical_path = root / f"{EVIDENCE}/correction-history-v0247.json"
    try:
        canonical_history = load(canonical_path)
        history_ok = isinstance(canonical_history, dict) and bool(canonical_history)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        canonical_history = {}
        history_ok = False
    changed = _git_changed(root, args.base_ref, args.head_ref)
    evidence_files = sorted(path.relative_to(root).as_posix() for path in (root / EVIDENCE).rglob("*") if path.is_file())
    gate_values = gates.get("gates", {})
    control_values = controls.get("controls", {})
    exact_refs = bool(GIT_SHA_RE.fullmatch(args.base_ref)) and bool(GIT_SHA_RE.fullmatch(args.head_ref))
    legacy_v0247_identity = args.base_ref == BASE_MAIN and args.pr_number == 15 and args.head_branch == REQUIRED_BRANCH
    overall = (
        exact_refs
        and (legacy_v0247_identity or (state.get("version") == "0.25.2" and args.pr_number > 0 and bool(args.head_branch)))
        and execution.get("overall_pass") is True
        and tests.get("status") == "PASS"
        and isinstance(tests.get("count"), int)
        and tests.get("count") > 0
        and validation.get("status") == "PASS"
        and validation.get("checks") == validation.get("passed")
        and validation.get("failed") == 0
        and state_validation.get("status") == CURRENT_GATE
        and _all_gate_values_pass(gate_values)
        and controls.get("status") == "PASS"
        and _all_controls_reject(control_values)
        and determinism.get("status") == "PASS"
        and determinism.get("run_1") == determinism.get("run_2")
        and production.get("production_routing") == "BLOCKED"
        and production.get("production_approved") is False
        and production.get("new_generation") == 0
        and production.get("provider_submit_calls") == 0
        and provider.get("boundary", {}).get("status") == "PASS"
        and provider.get("snapshot", {}).get("provider_submit_calls") == 0
        and family.get("peak_global", 0) <= 3
        and state.get("production_approved") is False
        and state.get("production_routing") == "BLOCKED"
        and state.get("new_generation") == 0
        and history_ok
        and uads_handoff.get("execution_mode") == "GLOBAL_FIRST"
        and uads_handoff.get("project_footprint") == "ZERO"
        and uads_handoff.get("route_status") == "SELECTED"
        and uads_handoff.get("dispatch_status") == "DISPATCHED"
        and bool(uads_handoff.get("selected_profile_id"))
    )
    value = {
        "schema_version": VERSION,
        "manifest_type": "github-ci-orchestration-runtime-v0247-review",
        "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"},
        "pull_request": {"number": args.pr_number, "base_sha": args.base_ref, "head_sha": args.head_ref, "merge_base_sha": args.base_ref, "head_branch": args.head_branch, "base_branch": "main"},
        "scope": {"version": VERSION, "phase": "ORCHESTRATION_RUNTIME_HARDENING", "current_gate": CURRENT_GATE, "baseline_main_sha": BASE_MAIN, "rejected_reviewed_head": REJECTED_HEAD, "allowed_next_actions": [NEXT_ACTION], "next_candidate": "V1_FINAL_ACCEPTANCE", "new_generation": 0, "test_only": True, "provider_neutral": True},
        "changed_files": changed,
        "change_statistics": {"files": len(changed)},
        "current_state": {"path": "docs/evidence/current-state.json", "version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "tracked_head_sha": state.get("review", {}).get("head_sha"), "head_sha_source": state.get("review", {}).get("head_sha_source"), "production_approved": state.get("production_approved"), "production_routing": state.get("production_routing"), "allowed_next_actions": state.get("allowed_next_actions")},
        "tests": tests,
        "validation": validation,
        "state_validation": state_validation,
        "gates": gate_values,
        "negative_controls": controls,
        "determinism": determinism,
        "orchestration_evidence": evidence_files,
        "dependency_authority": authority,
        "provider_boundary": provider,
        "family_concurrency": family,
        "correction_history": canonical_history,
        "correction_history_source": f"{EVIDENCE}/correction-history-v0247.json",
        "uads_handoff": uads_handoff,
        "uads_handoff_status": "PASS" if uads_handoff.get("route_status") == "SELECTED" and uads_handoff.get("dispatch_status") == "DISPATCHED" else "FAIL",
        "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_asset_generation": "NONE", "synthetic_fixture": "TEST_ONLY", "provider_submit_calls": 0},
        "review_boundary": {"external_review_required": True, "do_not_merge": True, "merge_authorization": APPROVAL_AUTHORIZATION, "approved_semantic_head": APPROVED_SEMANTIC_HEAD, "approval_comment_id": APPROVAL_COMMENT_ID, "approval_record": APPROVAL_RECORD, "post_bookkeeping_reproof_required": True, "pr_open_required": True, "pr_merged": False, "v1_final_acceptance_started": False, "provider_generation_started": False},
        "governance": {"approval_record": APPROVAL_RECORD, "approved_semantic_head": APPROVED_SEMANTIC_HEAD, "approval_comment_id": APPROVAL_COMMENT_ID},
        "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False},
        "overall_status": "PASS" if overall else "FAIL",
    }
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "github-review-manifest-v0247.json").write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "v0247_GITHUB_REVIEW_MANIFEST_BUILT", "overall_status": value["overall_status"], "head_sha": args.head_ref, "pr_number": args.pr_number}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
