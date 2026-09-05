"""Build the bounded GitHub-native v0.19.1 review manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "52938a04016352d50ad54621a4df981a9c36b058"
BRANCH = "codex/v0.19.0-items-props-runtime-foundation"
EVIDENCE = "docs/evidence/items-props-runtime-v0191"


def _git(args: list[str], root: Path) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False).stdout.strip()


def _changed_files(base: str, head: str, root: Path) -> list[dict[str, Any]]:
    paths = _git(["diff", "--name-status", f"{base}...{head}"], root).splitlines()
    return [{"status": item.split("\t", 1)[0], "path": item.split("\t", 1)[-1]} for item in paths if item.strip()]


def _load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.repository_root or ROOT).resolve(); base = args.base_ref or BASELINE; head = args.head_ref or _git(["rev-parse", "HEAD"], root); branch = args.head_branch or _git(["branch", "--show-current"], root) or BRANCH
    changed = _changed_files(base, head, root); state = _load(root / "docs/evidence/current-state.json"); gates = _load(args.gates_json)["gates"]
    evidence = {
        "manifest": f"{EVIDENCE}/item-prop-runtime-manifest-v0191.json", "contract": f"{EVIDENCE}/item-prop-contract-v0191.json", "class_representation": f"{EVIDENCE}/class-representation-matrix-v0191.json", "representation": f"{EVIDENCE}/representation-binding-v0191.json", "representation_bytes": f"{EVIDENCE}/representation-byte-manifest-v0191.json", "geometry": f"{EVIDENCE}/world-geometry-v0191.json", "anchors": f"{EVIDENCE}/interaction-anchors-v0191.json", "stack_identity": f"{EVIDENCE}/stack-identity-v0191.json", "derived_variant_state": f"{EVIDENCE}/derived-variant-state-v0191.json", "equipment_authority_linkage": f"{EVIDENCE}/equipment-authority-linkage-v0191.json", "cache": f"{EVIDENCE}/cache-identity-v0191.json", "provenance": f"{EVIDENCE}/provenance-qa-v0191.json", "determinism": f"{EVIDENCE}/full-slice-two-run-determinism-v0191.json", "negative_controls": f"{EVIDENCE}/negative-controls-v0191.json", "production_registry": f"{EVIDENCE}/production-registry-v0191.json", "fixtures": f"{EVIDENCE}/synthetic-fixture-manifest-v0191.json", "contact_sheet": f"{EVIDENCE}/synthetic-item-prop-contact-sheet-v0191.png", "geometry_sheet": f"{EVIDENCE}/world-geometry-sheet-v0191.png", "execution": f"{EVIDENCE}/execution-evidence-v0191.json",
    }
    return {"schema_version": "0.19.1", "manifest_type": "github-ci-items-props-v0191-review", "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"}, "pull_request": {"number": int(args.pr_number), "base_sha": base, "head_sha": head, "merge_base_sha": base, "head_branch": branch, "base_branch": "main"}, "scope": {"version": state["version"], "phase": state["phase"], "current_gate": state["current_gate"], "allowed_next_actions": state["allowed_next_actions"], "new_generation": state["new_generation"]}, "changed_files": changed, "change_statistics": {"files": len(changed)}, "current_state": {"path": "docs/evidence/current-state.json", "version": state["version"], "phase": state["phase"], "current_gate": state["current_gate"], "production_approved": state["production_approved"], "production_routing": state["production_routing"], "allowed_next_actions": state["allowed_next_actions"], "review": state["review"]}, "tests": _load(args.tests_json), "validation": _load(args.validation_json), "overall_status": "PASS" if all(item.get("status") == "PASS" for item in gates) else "FAIL", "gates": gates, "items_props_evidence": evidence, "historical_regressions": {"creatures_v0182": "docs/evidence/creatures-monsters-runtime-v0182/", "equipment_v0171": "docs/evidence/equipment-outfits-runtime-v0171/", "direction_v0162": "docs/evidence/multi-direction-runtime-v0162/", "front_v0151": "docs/evidence/animation-runtime-v0151/"}, "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_item_prop_asset_coverage": "NONE", "synthetic_item_prop_fixture": "TEST_ONLY"}, "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False}, "review_boundary": {"external_review_required": True, "do_not_merge": True, "environment_tilesets_started": False}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", required=True); parser.add_argument("--repository-root"); parser.add_argument("--base-ref"); parser.add_argument("--head-ref"); parser.add_argument("--head-branch"); parser.add_argument("--pr-number", required=True, type=int); parser.add_argument("--tests-json", required=True); parser.add_argument("--validation-json", required=True); parser.add_argument("--gates-json", required=True); args = parser.parse_args(); output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True); value = build(args); (output / "github-review-manifest-v0191.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(json.dumps({"status": "V0191_GITHUB_REVIEW_MANIFEST_BUILT", "base_sha": value["pull_request"]["base_sha"], "head_sha": value["pull_request"]["head_sha"], "pr_number": value["pull_request"]["number"]}, ensure_ascii=False))
