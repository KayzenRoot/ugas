"""Build the bounded exact-head v0.24.0 review manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


BASE_MAIN = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
EVIDENCE = "docs/evidence/orchestration-runtime-v0240"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("output-dir", "repository-root", "base-ref", "head-ref", "head-branch", "tests-json", "validation-json", "gates-json", "controls-json", "determinism-json", "production-json"):
        parser.add_argument(f"--{name}", required=name != "repository-root")
    parser.add_argument("--pr-number", required=True, type=int)
    args = parser.parse_args(); root = Path(args.repository_root).resolve()
    state = load(root / "docs/evidence/current-state.json"); tests = load(Path(args.tests_json)); validation = load(Path(args.validation_json)); gates = load(Path(args.gates_json)); controls = load(Path(args.controls_json)); determinism = load(Path(args.determinism_json)); production = load(Path(args.production_json)); execution = load(root / f"{EVIDENCE}/execution-evidence-v0240.json")
    changed = [item for item in subprocess.run(["git", "diff", "--name-only", f"{args.base_ref}..{args.head_ref}"], cwd=root, capture_output=True, text=True, check=False).stdout.splitlines() if item]
    evidence_files = sorted(path.relative_to(root).as_posix() for path in (root / EVIDENCE).rglob("*") if path.is_file())
    overall = (
        execution.get("overall_pass") is True and tests.get("status") == "PASS" and validation.get("status") == "PASS"
        and gates.get("overall_pass") is True and len(gates.get("gates", {})) >= 30
        and all(item.get("status") == "PASS" and type(item.get("observed")) is bool and item.get("observed") is True for item in gates.get("gates", {}).values())
        and controls.get("status") == "PASS" and len(controls.get("controls", {})) >= 30
        and all(item.get("status") == "PASS" and item.get("result") == "REJECT" and item.get("expected_rejection_class") == item.get("observed_rejection_class") for item in controls.get("controls", {}).values())
        and determinism.get("status") == "PASS" and determinism.get("run_1") == determinism.get("run_2")
        and production.get("production_routing") == "BLOCKED" and production.get("production_approved") is False and production.get("new_generation") == 0 and production.get("provider_submit_calls") == 0
    )
    value = {
        "schema_version": "0.24.0", "manifest_type": "github-ci-orchestration-runtime-v0240-review", "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"},
        "pull_request": {"number": args.pr_number, "base_sha": args.base_ref, "head_sha": args.head_ref, "merge_base_sha": args.base_ref, "head_branch": args.head_branch, "base_branch": "main"},
        "scope": {"version": "0.24.0", "phase": "ORCHESTRATION_RUNTIME_HARDENING", "current_gate": "ORCHESTRATION_RUNTIME_HARDENING_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED", "baseline_main_sha": BASE_MAIN, "allowed_next_actions": ["external_review_orchestration_runtime_v0240"], "next_candidate": "V1_FINAL_ACCEPTANCE", "new_generation": 0, "test_only": True},
        "changed_files": changed, "change_statistics": {"files": len(changed)}, "current_state": {"path": "docs/evidence/current-state.json", "version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "tracked_head_sha": state.get("review", {}).get("head_sha"), "head_sha_source": state.get("review", {}).get("head_sha_source"), "production_approved": state.get("production_approved"), "production_routing": state.get("production_routing"), "allowed_next_actions": state.get("allowed_next_actions")},
        "tests": tests, "validation": validation, "gates": gates.get("gates", {}), "negative_controls": controls, "determinism": determinism, "orchestration_evidence": evidence_files,
        "historical_authority": {"v0234_semantic_head": "9f8030d2c0ee0e00d10d64a9331899e21ebd5842", "v0234_bookkeeping_head": "025805306784dee7e97ee70d4309aa671500eb2d", "v0234_merge_main_sha": BASE_MAIN, "v0234_post_merge_ci_run": 34300109485, "v0234_closure_comment_id": 5594761528, "v0234_evidence_immutable": True},
        "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_asset_generation": "NONE", "synthetic_fixture": "TEST_ONLY", "provider_submit_calls": 0},
        "review_boundary": {"external_review_required": True, "do_not_merge": True, "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL", "pr_open_required": True, "pr_merged": False, "v1_final_acceptance_started": False, "provider_generation_started": False},
        "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False},
        "overall_status": "PASS" if overall else "FAIL",
    }
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True); (output / "github-review-manifest-v0240.json").write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0240_GITHUB_REVIEW_MANIFEST_BUILT", "overall_status": value["overall_status"], "head_sha": args.head_ref, "pr_number": args.pr_number}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
