"""Fail-closed validation for the v0.15.1 review manifest and artifact bindings."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/validation"))

from ugas.schema_validation import validate_instance, validate_schema_document
from validate_github_review_manifest import validate_visual_manifest

EXPECTED_GATES = {
    "unit_tests",
    "official_validation",
    "state_consistency",
    "capability_matrix",
    "death_runtime",
    "recovery_integrity",
    "visual_transport",
    "workflow_validation",
    "manifest_validation",
    "security",
}
BRANCH_BASE = "98ebd95564216fbbee222aab630b73b5ff6f298d"
DEATH_EVIDENCE_ROOT = "docs/evidence/animation-runtime-v0151"


def _truthful(value: dict[str, Any], key: str) -> bool:
    total = value.get(key)
    if value.get("status") == "passed":
        return (
            value.get("exit_code") == 0
            and value.get("parse_status") == "parsed"
            and isinstance(total, int)
            and value.get("passed") == total
            and value.get("failed") == 0
        )
    return value.get("status") in {"failed", "parse_failed", "not_run"} and isinstance(value.get("exit_code"), int)


def _relative_file_exists(root: Path, relative: str) -> bool:
    path = Path(relative)
    return not path.is_absolute() and (root / path).is_file()


def validate(manifest_path: Path, visual_path: Path, root: Path = ROOT) -> dict[str, Any]:
    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = json.loads((root / "schemas/github-review-manifest-v0151.json").read_text(encoding="utf-8"))
        validate_schema_document(schema)
        validate_instance(manifest, schema)
        visual = json.loads(visual_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return {"status": "V0151_GITHUB_REVIEW_MANIFEST_FAILED", "failures": [f"schema:{type(exc).__name__}:{exc}"]}

    pull_request = manifest["pull_request"]
    scope = manifest["scope"]
    current_state = manifest["current_state"]
    context = manifest.get("gap_context", {})
    gaps = set(manifest.get("known_gaps", []))
    if pull_request["base_sha"] != BRANCH_BASE:
        failures.append("base-sha-must-bind-exact-branch-base")
    if pull_request["merge_base_sha"] != pull_request["base_sha"]:
        failures.append("merge-base-must-equal-pr-base")
    if pull_request["number"] > 0 and "GITHUB_PR_CREATE_GAP" in gaps:
        failures.append("pr-number-positive-cannot-have-github-pr-create-gap")
    if pull_request["number"] == 0 and context.get("source") == "local_rehearsal" and "LOCAL_REHEARSAL_PR_NOT_AVAILABLE" not in gaps:
        failures.append("local-rehearsal-gap-description-missing")
    if manifest.get("change_statistics", {}).get("files") != len(manifest.get("changed_files", [])):
        failures.append("change-statistics-file-count-mismatch")
    if not _truthful(manifest.get("tests", {}), "count"):
        failures.append("unit-result-not-truthful")
    if not _truthful(manifest.get("validation", {}), "checks"):
        failures.append("validation-result-not-truthful")

    gate_ids = {item.get("id") for item in manifest.get("gates", []) if isinstance(item, dict)}
    if gate_ids != EXPECTED_GATES:
        failures.append("gate-set-invalid")
    expected_overall = "PASS" if manifest.get("gates") and all(item.get("status") == "PASS" for item in manifest["gates"]) else "FAIL"
    if manifest.get("overall_status") != expected_overall:
        failures.append("overall-status-does-not-match-gates")

    if scope.get("version") != "0.15.1" or scope.get("phase") != "DEATH_ANIMATION_FRONT":
        failures.append("active-scope-invalid")
    if scope.get("current_gate") != "DEATH_ANIMATION_FRONT_GROUND_CONTACT_AND_VISUAL_INTEGRITY_TECHNICALLY_QUALIFIED":
        failures.append("active-gate-invalid")
    if current_state.get("version") != "0.15.1" or current_state.get("phase") != "DEATH_ANIMATION_FRONT":
        failures.append("current-state-scope-invalid")
    if current_state.get("current_gate") != "DEATH_ANIMATION_FRONT_GROUND_CONTACT_AND_VISUAL_INTEGRITY_TECHNICALLY_QUALIFIED":
        failures.append("current-state-gate-invalid")
    if current_state.get("production_approved") is not False or current_state.get("production_routing") != "BLOCKED":
        failures.append("production-boundary-invalid")
    if current_state.get("external_visual_review", {}).get("death_animation_front") != "APPROVED_PILOT":
        failures.append("death-external-review-must-be-approved-pilot")

    for key, relative in manifest["death_front_evidence"].items():
        if key == "phase_marker_sheet" or key != "approved_head":
            if not _relative_file_exists(root, relative):
                failures.append(f"death-evidence-missing:{key}")
    for key in ("repair_provenance", "frozen_state_consistency"):
        relative = manifest["recovery_evidence"][key]
        if not _relative_file_exists(root, relative):
            failures.append(f"recovery-evidence-missing:{key}")
    if manifest["recovery_evidence"]["approved_head"] != "a3e37865f260c5a6cd56743e1d4b9131fcb12cda":
        failures.append("recovery-approved-head-invalid")
    if manifest["recovery_evidence"]["merge_commit"] != BRANCH_BASE:
        failures.append("recovery-merge-commit-invalid")

    if manifest.get("incident", {}).get("classification") != "GOVERNANCE_ORDER_VIOLATION_AND_FAILED_CHECK_MERGE":
        failures.append("incident-binding-invalid")
    visual_result = validate_visual_manifest(visual, root)
    failures.extend(f"visual:{item}" for item in visual_result.get("failures", []))

    return {
        "status": "V0151_GITHUB_REVIEW_MANIFEST_PASSED" if not failures else "V0151_GITHUB_REVIEW_MANIFEST_FAILED",
        "failures": failures,
        "overall_status": manifest.get("overall_status"),
        "base_sha": pull_request.get("base_sha"),
        "head_sha": pull_request.get("head_sha"),
        "visual_count": visual_result.get("visual_count", 0),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("visual")
    parser.add_argument("--result-output")
    args = parser.parse_args()
    result = validate(Path(args.manifest), Path(args.visual))
    if args.result_output:
        Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "V0151_GITHUB_REVIEW_MANIFEST_PASSED" else 1)
