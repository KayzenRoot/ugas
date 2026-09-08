"""Build the bounded exact-head v0.23.4 review manifest."""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

BASE_MAIN = "b08b9c3df74ef6a23046be396289e2fd72dc336b"
EVIDENCE = "docs/evidence/vfx-asset-family-runtime-v0234"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser()
    for name in ("output-dir", "repository-root", "base-ref", "head-ref", "head-branch", "tests-json", "validation-json", "gates-json", "controls-json", "determinism-json", "production-json"):
        p.add_argument(f"--{name}", required=name not in {"repository-root"})
    p.add_argument("--pr-number", required=True, type=int)
    a = p.parse_args(); root = Path(a.repository_root).resolve()
    state = load(root / "docs/evidence/current-state.json"); gates = load(Path(a.gates_json)); controls = load(Path(a.controls_json)); det = load(Path(a.determinism_json)); prod = load(Path(a.production_json)); execution = load(root / f"{EVIDENCE}/execution-evidence-v0234.json")
    changed = [x for x in subprocess.run(["git", "diff", "--name-only", f"{a.base_ref}..{a.head_ref}"], cwd=root, capture_output=True, text=True, check=False).stdout.splitlines() if x]
    names = tuple(path.name for path in sorted((root / EVIDENCE).iterdir()) if path.is_file())
    evidence = {n.rsplit(".", 1)[0]: f"{EVIDENCE}/{n}" for n in names}
    overall = execution.get("overall_pass") is True and det.get("status") == "PASS" and prod.get("registry") == [] and len(gates.get("gates", {})) == 33 and all(x.get("status") == "PASS" and type(x.get("observed")) is bool and x.get("observed") is True for x in gates.get("gates", {}).values()) and len(controls.get("controls", {})) == 18 and all(x.get("status") == "PASS" and x.get("result") == "REJECT" and x.get("expected_rejection_class") == x.get("observed_rejection_class") for x in controls.get("controls", {}).values())
    value = {"schema_version": "0.23.4", "manifest_type": "github-ci-vfx-asset-family-v0234-review", "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"}, "pull_request": {"number": a.pr_number, "base_sha": a.base_ref, "head_sha": a.head_ref, "merge_base_sha": a.base_ref, "head_branch": a.head_branch, "base_branch": "main"}, "scope": {"version": "0.23.4", "phase": "VFX_ASSET_FAMILY", "current_gate": "VFX_ASSET_FAMILY_RUNTIME_CORRECTION_F29R_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED", "baseline_main_sha": BASE_MAIN, "allowed_next_actions": ["external_review_vfx_asset_family_v0234"], "next_candidate": "ORCHESTRATION_RUNTIME_HARDENING", "new_generation": 0, "corrections": ["F-29R"]}, "changed_files": changed, "change_statistics": {"files": len(changed)}, "current_state": {"path": "docs/evidence/current-state.json", "version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "tracked_head_sha": state.get("review", {}).get("head_sha"), "head_sha_source": state.get("review", {}).get("head_sha_source"), "production_approved": state.get("production_approved"), "production_routing": state.get("production_routing"), "allowed_next_actions": state.get("allowed_next_actions")}, "tests": load(Path(a.tests_json)), "validation": load(Path(a.validation_json)), "gates": gates.get("gates", {}), "negative_controls": controls, "determinism": det, "vfx_evidence": evidence, "historical_authority": {"v0230_reviewed_head": "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72", "v0231_reviewed_head": "136079540f674c7467d93bd28e9834addbfce5c3", "v0232_rejected_head": "d7501177a9f4480921226b9832ffc237544a6433", "v0233_rejected_head": "9eda08b25a674a5423a99d35a42711102df91b8b", "v0230_evidence_immutable": True, "v0231_evidence_immutable": True, "v0232_evidence_immutable": True, "v0233_evidence_immutable": True, "base_main_sha": BASE_MAIN}, "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": "TEST_ONLY", "production_registry_empty": prod.get("registry") == []}, "review_boundary": {"external_review_required": True, "do_not_merge": True, "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL", "pr_open_required": True, "pr_merged": False, "orchestration_started": False, "production_art_started": False, "provider_generation_started": False}, "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False}, "overall_status": "PASS" if overall else "FAIL"}
    out = Path(a.output_dir); out.mkdir(parents=True, exist_ok=True); (out / "github-review-manifest-v0234.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0233_GITHUB_REVIEW_MANIFEST_BUILT", "head_sha": a.head_ref, "pr_number": a.pr_number})); return 0


if __name__ == "__main__":
    raise SystemExit(main())

