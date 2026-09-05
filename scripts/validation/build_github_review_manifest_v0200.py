"""Build the bounded GitHub-native v0.20.0 review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


EVIDENCE = "docs/evidence/environment-tilesets-runtime-v0200"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(args: list[str], root: Path) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False).stdout.strip()


def build(args: argparse.Namespace) -> dict:
    root = Path(args.repository_root).resolve()
    state = _load(root / "docs/evidence/current-state.json")
    gates = _load(Path(args.gates_json)).get("gates", {})
    changed = [line for line in _git(["diff", "--name-only", f"{args.base_ref}..{args.head_ref}"], root).splitlines() if line]
    evidence = {name: f"{EVIDENCE}/{name}" for name in ("tileset-manifest-v0200.json", "hard-gates-v0200.json", "negative-controls-v0200.json", "full-slice-two-run-determinism-v0200.json", "production-registry-v0200.json", "test-only-qa-board-v0200.json", "execution-evidence-v0200.json")}
    return {"schema_version": "0.20.0", "manifest_type": "github-ci-environment-tilesets-v0200-review", "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"}, "pull_request": {"number": int(args.pr_number), "base_sha": args.base_ref, "head_sha": args.head_ref, "merge_base_sha": args.base_ref, "head_branch": args.head_branch, "base_branch": "main"}, "scope": {"version": state["version"], "phase": state["phase"], "current_gate": state["current_gate"], "allowed_next_actions": state["allowed_next_actions"], "new_generation": state["new_generation"]}, "changed_files": changed, "change_statistics": {"files": len(changed)}, "current_state": {"path": "docs/evidence/current-state.json", "version": state["version"], "phase": state["phase"], "current_gate": state["current_gate"], "production_approved": state["production_approved"], "production_routing": state["production_routing"], "allowed_next_actions": state["allowed_next_actions"]}, "tests": _load(Path(args.tests_json)), "validation": _load(Path(args.validation_json)), "gates": gates, "overall_status": "PASS" if all(item.get("status") == "PASS" for item in gates.values()) else "FAIL", "environment_tilesets_evidence": evidence, "historical_regressions": {"items_props_v0191": "docs/evidence/items-props-runtime-v0191/", "creatures_v0182": "docs/evidence/creatures-monsters-runtime-v0182/", "equipment_v0171": "docs/evidence/equipment-outfits-runtime-v0171/", "direction_v0162": "docs/evidence/multi-direction-runtime-v0162/"}, "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_environment_asset_coverage": "NONE", "synthetic_environment_fixture": "TEST_ONLY"}, "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False}, "review_boundary": {"external_review_required": True, "do_not_merge": True, "merge_authorization": "NOT_AUTHORIZED", "maps_minimap_started": False, "production_environment_art_started": False}}


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
    args = parser.parse_args()
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    value = build(args)
    (output / "github-review-manifest-v0200.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0200_GITHUB_REVIEW_MANIFEST_BUILT", "base_sha": args.base_ref, "head_sha": args.head_ref, "pr_number": args.pr_number}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
