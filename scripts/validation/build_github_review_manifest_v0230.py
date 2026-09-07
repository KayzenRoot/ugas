"""Build the bounded exact-head v0.23.0 VFX review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


BASE_MAIN = "b08b9c3df74ef6a23046be396289e2fd72dc336b"
EVIDENCE = "docs/evidence/vfx-asset-family-runtime-v0230"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--head-branch", required=True)
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--tests-json", required=True)
    parser.add_argument("--validation-json", required=True)
    parser.add_argument("--gates-json", required=True)
    parser.add_argument("--controls-json", required=True)
    parser.add_argument("--determinism-json", required=True)
    parser.add_argument("--production-json", required=True)
    args = parser.parse_args()
    root = Path(args.repository_root).resolve()
    state = load(root / "docs/evidence/current-state.json")
    gates = load(Path(args.gates_json)); controls = load(Path(args.controls_json)); det = load(Path(args.determinism_json)); prod = load(Path(args.production_json)); execution = load(root / f"{EVIDENCE}/execution-evidence-v0230.json")
    changed = [line for line in subprocess.run(["git", "diff", "--name-only", f"{args.base_ref}..{args.head_ref}"], cwd=root, capture_output=True, text=True, check=False).stdout.splitlines() if line]
    evidence_names = ("vfx-family-manifest-v0230.json", "effect-class-contract-v0230.json", "lifecycle-timing-v0230.json", "blend-alpha-contract-v0230.json", "spatial-anchor-contract-v0230.json", "budget-authority-v0230.json", "fallback-degradation-v0230.json", "representation-import-v0230.json", "integration-linkage-v0230.json", "cache-provenance-v0230.json", "hard-gates-v0230.json", "negative-controls-v0230.json", "full-slice-two-run-determinism-v0230.json", "production-registry-v0230.json", "test-only-fixture-manifest-v0230.json", "execution-evidence-v0230.json", "historical-immutability-v0230.json", "capability-matrix-validation-v0230.json", "state-consistency-v0230.json", "schema-validation-v0230.json", "v0.22.3-approval-transition-v0230.json", "qa-contact-timing-v0230.json", "vfx-effect-contact-sheet-v0230.png", "vfx-timing-qa-sheet-v0230.png")
    evidence = {name.removesuffix(".json").removesuffix(".png"): f"{EVIDENCE}/{name}" for name in evidence_names}
    overall = execution.get("overall_pass") is True and det.get("status") == "PASS" and prod.get("registry") == [] and len(gates.get("gates", {})) == 25 and all(item.get("status") == "PASS" and type(item.get("observed")) is bool and item.get("observed") is True for item in gates.get("gates", {}).values()) and len(controls.get("controls", {})) == 36 and all(item.get("status") == "PASS" and item.get("result") == "REJECT" and item.get("expected_rejection_class") == item.get("observed_rejection_class") for item in controls.get("controls", {}).values())
    value = {"schema_version": "0.23.0", "manifest_type": "github-ci-vfx-asset-family-v0230-review", "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"}, "pull_request": {"number": args.pr_number, "base_sha": args.base_ref, "head_sha": args.head_ref, "merge_base_sha": args.base_ref, "head_branch": args.head_branch, "base_branch": "main"}, "scope": {"version": "0.23.0", "phase": "VFX_ASSET_FAMILY", "current_gate": "VFX_ASSET_FAMILY_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED", "baseline_main_sha": BASE_MAIN, "allowed_next_actions": ["external_review_vfx_asset_family_v0230"], "next_candidate": "ORCHESTRATION_RUNTIME_HARDENING", "new_generation": 0}, "changed_files": changed, "change_statistics": {"files": len(changed)}, "current_state": {"path": "docs/evidence/current-state.json", "version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "production_approved": state.get("production_approved"), "production_routing": state.get("production_routing"), "allowed_next_actions": state.get("allowed_next_actions")}, "tests": load(Path(args.tests_json)), "validation": load(Path(args.validation_json)), "gates": gates.get("gates", {}), "negative_controls": controls, "determinism": det, "vfx_evidence": evidence, "historical_authority": {"ui_v0223_review": "REVIEW-v0.22.3.md", "ui_v0223_evidence_immutable": True, "base_main_sha": BASE_MAIN, "no_approved_authority_rewritten": True}, "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": "TEST_ONLY", "production_registry_empty": prod.get("registry") == []}, "review_boundary": {"external_review_required": True, "do_not_merge": True, "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL", "ui_started": False, "orchestration_started": False, "production_art_started": False, "provider_generation_started": False}, "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False}, "overall_status": "PASS" if overall else "FAIL"}
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True); (output / "github-review-manifest-v0230.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0230_GITHUB_REVIEW_MANIFEST_BUILT", "head_sha": args.head_ref, "pr_number": args.pr_number}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
