"""Build the bounded exact-head v0.22.0 UI review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


EVIDENCE = "docs/evidence/ui-asset-family-runtime-v0220"
BASE_MAIN = "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(args: list[str], root: Path) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False).stdout.strip()


def build(args: argparse.Namespace) -> dict:
    root = Path(args.repository_root).resolve(); state = _load(root / "docs/evidence/current-state.json")
    gates = _load(Path(args.gates_json)); controls = _load(Path(args.controls_json)); determinism = _load(Path(args.determinism_json)); production = _load(Path(args.production_json)); execution = _load(root / f"{EVIDENCE}/execution-evidence-v0220.json")
    changed = [line for line in _git(["diff", "--name-only", f"{args.base_ref}..{args.head_ref}"], root).splitlines() if line]
    evidence = {name.removesuffix("-v0220.json"): f"{EVIDENCE}/{name}" for name in ("ui-family-manifest-v0220.json", "component-class-matrix-v0220.json", "state-variant-matrix-v0220.json", "style-token-authority-v0220.json", "nine-slice-geometry-v0220.json", "safe-area-geometry-v0220.json", "scale-consistency-v0220.json", "integration-linkage-v0220.json", "cache-identity-v0220.json", "provenance-v0220.json", "hard-gates-v0220.json", "negative-controls-v0220.json", "full-slice-two-run-determinism-v0220.json", "production-registry-v0220.json", "test-only-fixture-manifest-v0220.json", "execution-evidence-v0220.json", "ui-state-contact-sheet-v0220.png", "ui-geometry-qa-sheet-v0220.png")}
    all_gates_pass = all(item.get("status") == "PASS" and type(item.get("observed")) is bool and item.get("observed") is True for item in gates.get("gates", {}).values())
    all_controls_pass = len(controls.get("controls", {})) == 22 and all(item.get("status") == "PASS" and item.get("result") == "REJECT" and item.get("expected_rejection_class") == item.get("observed_rejection_class") for item in controls.get("controls", {}).values())
    overall = execution.get("overall_pass") is True and all_gates_pass and all_controls_pass and determinism.get("status") == "PASS" and production.get("registry") == []
    return {"schema_version": "0.22.0", "manifest_type": "github-ci-ui-asset-family-v0220-review", "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"}, "pull_request": {"number": int(args.pr_number), "base_sha": args.base_ref, "head_sha": args.head_ref, "merge_base_sha": args.base_ref, "head_branch": args.head_branch, "base_branch": "main"}, "scope": {"version": "0.22.0", "phase": "UI_ASSET_FAMILY", "current_gate": "UI_ASSET_FAMILY_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED", "baseline_main_sha": BASE_MAIN, "allowed_next_actions": ["external_review_ui_asset_family_v0220"], "next_candidate": "UI_ASSET_FAMILY", "new_generation": 0}, "changed_files": changed, "change_statistics": {"files": len(changed)}, "current_state": {"path": "docs/evidence/current-state.json", "version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "production_approved": state.get("production_approved"), "production_routing": state.get("production_routing"), "allowed_next_actions": state.get("allowed_next_actions")}, "tests": _load(Path(args.tests_json)), "validation": _load(Path(args.validation_json)), "gates": gates.get("gates", {}), "negative_controls": controls, "determinism": determinism, "ui_evidence": evidence, "historical_authority": {"closure_completion_binding": "docs/evidence/github-governance-v0220/v0213-closure-completion-binding.json", "v0213_roots_immutable": True}, "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "production_registry_empty": production.get("registry") == []}, "review_boundary": {"external_review_required": True, "do_not_merge": True, "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL", "vfx_started": False, "orchestration_started": False, "production_art_started": False}, "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False}, "overall_status": "PASS" if overall else "FAIL"}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", required=True); parser.add_argument("--repository-root", default="."); parser.add_argument("--base-ref", required=True); parser.add_argument("--head-ref", required=True); parser.add_argument("--head-branch", required=True); parser.add_argument("--pr-number", required=True, type=int); parser.add_argument("--tests-json", required=True); parser.add_argument("--validation-json", required=True); parser.add_argument("--gates-json", required=True); parser.add_argument("--controls-json", required=True); parser.add_argument("--determinism-json", required=True); parser.add_argument("--production-json", required=True); args = parser.parse_args()
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True); value = build(args); (output / "github-review-manifest-v0220.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(json.dumps({"status": "V0220_GITHUB_REVIEW_MANIFEST_BUILT", "head_sha": args.head_ref, "pr_number": args.pr_number})); return 0


if __name__ == "__main__": raise SystemExit(main())
