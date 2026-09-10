"""Build the bounded exact-head v0.24.3 review manifest."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


VERSION = "0.24.3"
BASE_MAIN = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
REJECTED_HEAD = "cd3345db7c0e587915e56eb9314879c4a9cf98a3"
EVIDENCE = "docs/evidence/orchestration-runtime-v0243"
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
    return isinstance(gates, dict) and len(gates) >= 40 and all(
        isinstance(item, dict)
        and item.get("status") == "PASS"
        and type(item.get("observed")) is bool
        and item.get("observed") is True
        and item.get("observed_type") == "bool"
        for item in gates.values()
    )


def _all_controls_reject(controls: dict[str, Any]) -> bool:
    if len(controls) < 8:
        return False
    for item in controls.values():
        if not isinstance(item, dict) or item.get("status") != "PASS" or item.get("result") != "REJECT":
            return False
        observed = item.get("observed_rejection_class")
        expected = item.get("expected_rejection_class")
        if item.get("control_id") == "NC-GATE-01":
            if item.get("observed_type") != "str" or item.get("observed_value") != "true" or item.get("observed_gate_status") != "FAIL":
                return False
        elif not expected or observed != expected or not item.get("actual_exception"):
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
    execution = load(root / f"{EVIDENCE}/execution-evidence-v0243.json")
    authority = load(root / f"{EVIDENCE}/dependency-authority-v0243.json")
    changed = _git_changed(root, args.base_ref, args.head_ref)
    evidence_files = sorted(path.relative_to(root).as_posix() for path in (root / EVIDENCE).rglob("*") if path.is_file())
    gate_values = gates.get("gates", {})
    control_values = controls.get("controls", {})
    exact_refs = bool(GIT_SHA_RE.fullmatch(args.base_ref)) and bool(GIT_SHA_RE.fullmatch(args.head_ref))
    overall = (
        exact_refs
        and args.base_ref == BASE_MAIN
        and args.pr_number == 15
        and args.head_branch == "codex/v0.24.0-orchestration-runtime-hardening-foundation"
        and execution.get("overall_pass") is True
        and tests.get("status") == "PASS"
        and isinstance(tests.get("count"), int)
        and tests.get("count") > 0
        and validation.get("status") == "PASS"
        and validation.get("checks") == validation.get("passed")
        and validation.get("failed") == 0
        and state_validation.get("status") == "ORCHESTRATION_RUNTIME_HARDENING_F31R_F36_CORRECTION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED"
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
        and state.get("review", {}).get("pr_state") == "OPEN"
        and state.get("review", {}).get("do_not_merge") is True
        and state.get("review", {}).get("merge_authorization") == "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL"
    )
    value = {
        "schema_version": VERSION,
        "manifest_type": "github-ci-orchestration-runtime-v0243-review",
        "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"},
        "pull_request": {"number": args.pr_number, "base_sha": args.base_ref, "head_sha": args.head_ref, "merge_base_sha": args.base_ref, "head_branch": args.head_branch, "base_branch": "main"},
        "scope": {"version": VERSION, "phase": "ORCHESTRATION_RUNTIME_HARDENING", "current_gate": "ORCHESTRATION_RUNTIME_HARDENING_F31R_F36_CORRECTION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED", "baseline_main_sha": BASE_MAIN, "rejected_reviewed_head": REJECTED_HEAD, "allowed_next_actions": ["external_review_orchestration_runtime_v0243"], "next_candidate": "V1_FINAL_ACCEPTANCE", "new_generation": 0, "test_only": True, "provider_neutral": True},
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
        "correction_history": {"status": "CORRECTION_REQUIRED", "rejected_reviewed_head": REJECTED_HEAD, "findings": ["F-31R", "F-32", "F-33", "F-34", "F-35", "F-36"], "historical_evidence_unchanged": True},
        "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_asset_generation": "NONE", "synthetic_fixture": "TEST_ONLY", "provider_submit_calls": 0},
        "review_boundary": {"external_review_required": True, "do_not_merge": True, "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL", "pr_open_required": True, "pr_merged": False, "v1_final_acceptance_started": False, "provider_generation_started": False},
        "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False},
        "overall_status": "PASS" if overall else "FAIL",
    }
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "github-review-manifest-v0243.json").write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "v0243_GITHUB_REVIEW_MANIFEST_BUILT", "overall_status": value["overall_status"], "head_sha": args.head_ref, "pr_number": args.pr_number}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
