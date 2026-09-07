"""Build the bounded exact-head v0.22.3 review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


BASE_MAIN = "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3"
EVIDENCE = "docs/evidence/ui-asset-family-runtime-v0223"


def load(path: Path) -> dict: return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", required=True); parser.add_argument("--repository-root", default="."); parser.add_argument("--base-ref", required=True); parser.add_argument("--head-ref", required=True); parser.add_argument("--head-branch", required=True); parser.add_argument("--pr-number", required=True, type=int); parser.add_argument("--tests-json", required=True); parser.add_argument("--validation-json", required=True); parser.add_argument("--gates-json", required=True); parser.add_argument("--controls-json", required=True); parser.add_argument("--determinism-json", required=True); parser.add_argument("--production-json", required=True); args = parser.parse_args()
    root = Path(args.repository_root).resolve(); state = load(root / "docs/evidence/current-state.json"); gates = load(Path(args.gates_json)); controls = load(Path(args.controls_json)); det = load(Path(args.determinism_json)); prod = load(Path(args.production_json)); execution = load(root / f"{EVIDENCE}/execution-evidence-v0223.json"); governance = load(root / f"{EVIDENCE}/governance-binding-validation-v0223.json")
    changed = [line for line in subprocess.run(["git", "diff", "--name-only", f"{args.base_ref}..{args.head_ref}"], cwd=root, capture_output=True, text=True, check=False).stdout.splitlines() if line]
    evidence_names = ("ui-family-manifest-v0223.json", "ui-style-authority-v0223.json", "component-class-contract-v0223.json", "progress-bar-contract-v0223.json", "nine-slice-independent-verification-v0223.json", "integration-authority-bindings-v0223.json", "cache-semantic-identity-v0223.json", "hard-gates-v0223.json", "negative-controls-v0223.json", "full-slice-two-run-determinism-v0223.json", "historical-authority-v0223.json", "governance-binding-validation-v0223.json", "production-registry-v0223.json", "capability-matrix-validation-v0223.json", "execution-evidence-v0223.json", "v0.22.1-rejection-correction-record-v0223.json")
    evidence = {name.removesuffix(".json"): f"{EVIDENCE}/{name}" for name in evidence_names}
    overall = execution.get("overall_pass") is True and det.get("status") == "PASS" and prod.get("registry") == [] and governance.get("validation", {}).get("status") == "PASS" and all(item.get("status") == "PASS" and type(item.get("observed")) is bool and item.get("observed") is True for item in gates.get("gates", {}).values()) and all(item.get("status") == "PASS" and item.get("result") == "REJECT" for item in controls.get("controls", {}).values())
    value = {"schema_version": "0.22.3", "manifest_type": "github-ci-ui-asset-family-v0223-review", "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"}, "pull_request": {"number": args.pr_number, "base_sha": args.base_ref, "head_sha": args.head_ref, "merge_base_sha": args.base_ref, "head_branch": args.head_branch, "base_branch": "main"}, "scope": {"version": "0.22.3", "phase": "UI_ASSET_FAMILY", "current_gate": "UI_ASSET_FAMILY_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED", "baseline_main_sha": BASE_MAIN, "allowed_next_actions": ["external_review_ui_asset_family_v0223"], "next_candidate": "UI_ASSET_FAMILY", "new_generation": 0}, "changed_files": changed, "change_statistics": {"files": len(changed)}, "current_state": {"path": "docs/evidence/current-state.json", "version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "production_approved": state.get("production_approved"), "production_routing": state.get("production_routing"), "allowed_next_actions": state.get("allowed_next_actions")}, "tests": load(Path(args.tests_json)), "validation": load(Path(args.validation_json)), "gates": gates.get("gates", {}), "negative_controls": controls, "determinism": det, "ui_evidence": evidence, "historical_authority": {"canonical_v0213": "docs/evidence/github-governance-v0221/v0213-closure-completion-binding-v2.json", "historical_prerequisite": "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json", "superseded_stale_pointer": "docs/evidence/github-governance-v0220/v0213-closure-completion-binding.json", "v0220_evidence_immutable": True, "v0221_evidence_immutable": True, "v0222_evidence_immutable": True}, "governance": governance, "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "production_registry_empty": prod.get("registry") == []}, "review_boundary": {"external_review_required": True, "do_not_merge": True, "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL", "vfx_started": False, "orchestration_started": False, "production_art_started": False}, "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False}, "overall_status": "PASS" if overall else "FAIL"}
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True); (output / "github-review-manifest-v0223.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(json.dumps({"status": "V0222_GITHUB_REVIEW_MANIFEST_BUILT", "head_sha": args.head_ref, "pr_number": args.pr_number})); return 0


if __name__ == "__main__": raise SystemExit(main())
