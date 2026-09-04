"""Build the bounded v0.15.1 DEATH_ANIMATION_FRONT review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_github_review_manifest import _changed_files, _event_values, _known_gaps, _load_result, _resolve, _run

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "98ebd95564216fbbee222aab630b73b5ff6f298d"
BRANCH = "codex/v0.15.1-death-animation-front"
INCIDENT_PATH = "docs/evidence/github-governance-v0124/pr1-premature-merge.json"
REPAIR_PATH = "docs/evidence/github-governance-v0141/hit-front-v0141-post-merge-integrity-repair.json"
FROZEN_STATE_PATH = "docs/evidence/animation-runtime-v0141/state-consistency-v0141.json"
DEATH_EVIDENCE = "docs/evidence/animation-runtime-v0151"


def build(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(getattr(args, "repository_root", None) or ROOT).resolve()
    event = _event_values()
    base = _resolve(getattr(args, "base_ref", None) or event.get("base_ref") or BASELINE, root)
    head = _resolve(getattr(args, "head_ref", None) or event.get("head_ref") or "HEAD", root)
    merge_base = _resolve(_run(["git", "merge-base", base, head], root), root)
    changed, additions, deletions = _changed_files(base, head, root)
    state = json.loads((root / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    incident = json.loads((root / INCIDENT_PATH).read_text(encoding="utf-8"))
    tests = _load_result(Path(args.tests_json)) if getattr(args, "tests_json", None) else {
        "schema_version": "0.15.1",
        "status": "not_run",
        "exit_code": 99,
        "count": None,
        "passed": None,
        "failed": None,
        "parse_status": "not_run",
    }
    validation = _load_result(Path(args.validation_json), validation=True) if getattr(args, "validation_json", None) else {
        "schema_version": "0.15.1",
        "status": "not_run",
        "exit_code": 99,
        "checks": None,
        "passed": None,
        "failed": None,
        "parse_status": "not_run",
    }
    visual = json.loads(Path(args.visual_manifest).read_text(encoding="utf-8"))
    branch = getattr(args, "head_branch", None) or event.get("head_branch") or _run(["git", "branch", "--show-current"], root) or BRANCH
    pr_number = getattr(args, "pr_number", None) if getattr(args, "pr_number", None) is not None else int(event.get("number") or 0)
    gate_result = json.loads(Path(args.gates_json).read_text(encoding="utf-8"))
    gates = gate_result.get("gates", [])
    overall = "PASS" if gate_result.get("overall_status") == "PASS" and all(item.get("status") == "PASS" for item in gates) else "FAIL"
    known_gaps, gap_context = _known_gaps(args, event, pr_number)

    return {
        "schema_version": "1.3",
        "manifest_type": "github-ci-capability-review",
        "repository": {
            "name": "KayzenRoot/ugas",
            "url": "https://github.com/KayzenRoot/ugas",
            "default_branch": "main",
        },
        "pull_request": {
            "number": pr_number,
            "base_sha": base,
            "head_sha": head,
            "merge_base_sha": merge_base,
            "head_branch": branch,
            "base_branch": "main",
        },
        "scope": {
            "version": state["version"],
            "phase": state["phase"],
            "current_gate": state["current_gate"],
            "allowed_next_actions": state["allowed_next_actions"],
            "new_generation": state.get("new_generation", 0),
        },
        "changed_files": changed,
        "change_statistics": {"files": len(changed), "additions": additions, "deletions": deletions},
        "current_state": {
            "path": "docs/evidence/current-state.json",
            "version": state["version"],
            "phase": state["phase"],
            "current_gate": state["current_gate"],
            "production_approved": state["production_approved"],
            "production_routing": state["production_routing"],
            "external_visual_review": state["external_visual_review"],
            "allowed_next_actions": state["allowed_next_actions"],
        },
        "incident": {
            "pr_number": incident["pr"]["number"],
            "classification": incident["classification"],
            "artifact_id": incident["review_artifact"]["id"],
            "artifact_digest": incident["review_artifact"]["digest"],
        },
        "tests": tests,
        "validation": validation,
        "overall_status": overall,
        "gates": gates,
        "review_index": {
            "historical_path": "docs/evidence/review-index-v0.12.2.json",
            "historical_version": "0.12.2",
            "status": "PRESERVED_BASELINE_REHEARSAL" if pr_number == 0 else "PRESERVED_BASELINE_VALIDATED",
            "active_manifest_path": "github-review-manifest-v0151.json",
        },
        "visual_manifest": "visual-manifest.json",
        "death_front_evidence": {
            "contract": f"{DEATH_EVIDENCE}/death-front-contract-v0151.json",
            "execution": f"{DEATH_EVIDENCE}/execution-evidence-v0.15.1.json",
            "visual_manifest": f"{DEATH_EVIDENCE}/death-front-visual-manifest-v0151.json",
            "targets": f"{DEATH_EVIDENCE}/death-front-targets-v0151.json",
            "frame_qa": f"{DEATH_EVIDENCE}/death-front-frame-qa-v0151.json",
            "temporal_qa": f"{DEATH_EVIDENCE}/death-front-temporal-qa-v0151.json",
            "negative_controls": f"{DEATH_EVIDENCE}/death-front-gate-negative-controls-v0151.json",
            "preview_gif": f"{DEATH_EVIDENCE}/death-front-v1/death-front-preview-v0151.gif",
            "spritesheet": f"{DEATH_EVIDENCE}/death-front-v1/death-front-spritesheet-v0151.png",
            "phase_marker_sheet": f"{DEATH_EVIDENCE}/death-front-phase-markers-v0151.png",
        },
        "recovery_evidence": {
            "repair_provenance": REPAIR_PATH,
            "frozen_state_consistency": FROZEN_STATE_PATH,
            "approved_head": "a3e37865f260c5a6cd56743e1d4b9131fcb12cda",
            "merge_commit": "98ebd95564216fbbee222aab630b73b5ff6f298d",
        },
        "known_gaps": known_gaps,
        "gap_context": gap_context,
        "dashboard_policy": {
            "always_on": True,
            "runtime_mode": "DOCKER_ALWAYS_ON_LOCAL",
            "local_only": True,
            "url": "http://127.0.0.1:8765/",
            "must_remain_online_at_stop": True,
        },
        "production_boundary": {"approved": False, "routing": "BLOCKED"},
        "security_boundary": {
            "secrets_included": False,
            "model_weights_included": False,
            "telemetry_db_included": False,
            "local_credentials_included": False,
        },
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
    parser.add_argument("--visual-manifest", required=True)
    parser.add_argument("--preflight-json")
    parser.add_argument("--known-gap", action="append")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = build(args)
    (output / "github-review-manifest-v0151.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output / "visual-manifest.json").write_text(
        json.dumps(json.loads(Path(args.visual_manifest).read_text(encoding="utf-8")), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "V0150_GITHUB_REVIEW_MANIFEST_BUILT",
                "head_sha": manifest["pull_request"]["head_sha"],
                "base_sha": manifest["pull_request"]["base_sha"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
