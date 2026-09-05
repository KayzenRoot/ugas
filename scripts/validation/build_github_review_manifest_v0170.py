"""Build the bounded GitHub-native v0.17.0 equipment review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_github_review_manifest import _changed_files, _event_values, _known_gaps, _load_result, _resolve, _run

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "a8d2897211c4b72c2cd2fe7a7f5729c7009d8566"
BRANCH = "codex/v0.17.0-equipment-outfits-runtime-foundation"
EVIDENCE = "docs/evidence/equipment-outfits-runtime-v0170"


def build(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(getattr(args, "repository_root", None) or ROOT).resolve()
    event = _event_values()
    base = _resolve(getattr(args, "base_ref", None) or event.get("base_ref") or BASELINE, root)
    head = _resolve(getattr(args, "head_ref", None) or event.get("head_ref") or "HEAD", root)
    merge_base = _resolve(_run(["git", "merge-base", base, head], root), root)
    changed, additions, deletions = _changed_files(base, head, root)
    state = json.loads((root / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    tests = _load_result(Path(args.tests_json))
    validation = _load_result(Path(args.validation_json), validation=True)
    gates = json.loads(Path(args.gates_json).read_text(encoding="utf-8"))["gates"]
    branch = getattr(args, "head_branch", None) or event.get("head_branch") or _run(["git", "branch", "--show-current"], root) or BRANCH
    pr_number = getattr(args, "pr_number", None) if getattr(args, "pr_number", None) is not None else int(event.get("number") or 0)
    known_gaps, gap_context = _known_gaps(args, event, pr_number)
    return {
        "schema_version": "0.17.0",
        "manifest_type": "github-ci-equipment-outfits-review",
        "repository": {"name": "KayzenRoot/ugas", "url": "https://github.com/KayzenRoot/ugas", "default_branch": "main"},
        "pull_request": {"number": pr_number, "base_sha": base, "head_sha": head, "merge_base_sha": merge_base, "head_branch": branch, "base_branch": "main"},
        "scope": {"version": state["version"], "phase": state["phase"], "current_gate": state["current_gate"], "allowed_next_actions": state["allowed_next_actions"], "new_generation": state.get("new_generation", 0)},
        "changed_files": changed,
        "change_statistics": {"files": len(changed), "additions": additions, "deletions": deletions},
        "current_state": {"path": "docs/evidence/current-state.json", "version": state["version"], "phase": state["phase"], "current_gate": state["current_gate"], "production_approved": state["production_approved"], "production_routing": state["production_routing"], "external_visual_review": state["external_visual_review"], "allowed_next_actions": state["allowed_next_actions"], "review": state["review"]},
        "tests": tests,
        "validation": validation,
        "overall_status": "PASS" if gates and all(item.get("status") == "PASS" for item in gates) else "FAIL",
        "gates": gates,
        "equipment_outfits_evidence": {"contract": f"{EVIDENCE}/equipment-contract-v0170.json", "slot_layer_graph": f"{EVIDENCE}/slot-layer-graph-v0170.json", "anchor_qa": f"{EVIDENCE}/anchor-qa-v0170.json", "replacement_hide_qa": f"{EVIDENCE}/replacement-hide-qa-v0170.json", "occlusion_qa": f"{EVIDENCE}/occlusion-qa-v0170.json", "direction_animation_qa": f"{EVIDENCE}/direction-animation-qa-v0170.json", "cache_qa": f"{EVIDENCE}/cache-qa-v0170.json", "provenance_qa": f"{EVIDENCE}/provenance-qa-v0170.json", "determinism_qa": f"{EVIDENCE}/two-run-determinism-v0170.json", "negative_controls": f"{EVIDENCE}/negative-controls-v0170.json", "fixture_manifest": f"{EVIDENCE}/synthetic-fixture-manifest-v0170.json", "production_registry": f"{EVIDENCE}/equipment-registry-v0170.json", "contact_sheet": f"{EVIDENCE}/outfit-contact-sheet-v0170.png", "execution": f"{EVIDENCE}/execution-evidence-v0170.json"},
        "historical_release": {"version": "0.16.2", "merge_commit": BASELINE, "direction_runtime_evidence": "docs/evidence/multi-direction-runtime-v0162/", "history_preserved": True},
        "front_compatibility_evidence": {"runtime_log": "front-compatibility-v0151.log", "runtime_exit_code": int(Path(args.front_compatibility_exit).read_text(encoding="utf-8").strip())},
        "known_gaps": known_gaps,
        "gap_context": gap_context,
        "dashboard_policy": {"always_on": True, "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL", "local_only": True, "telemetry_upload": False},
        "production_boundary": {"approved": False, "routing": "BLOCKED", "new_generation": 0},
        "security_boundary": {"secrets_included": False, "model_weights_included": False, "telemetry_db_included": False, "local_credentials_included": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref")
    parser.add_argument("--head-branch")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--tests-json", required=True)
    parser.add_argument("--validation-json", required=True)
    parser.add_argument("--gates-json", required=True)
    parser.add_argument("--front-compatibility-exit", required=True)
    parser.add_argument("--preflight-json")
    parser.add_argument("--known-gap", action="append")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = build(args)
    (output / "github-review-manifest-v0170.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0170_GITHUB_REVIEW_MANIFEST_BUILT", "base_sha": manifest["pull_request"]["base_sha"], "head_sha": manifest["pull_request"]["head_sha"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
