"""Fail-closed validation for the v0.16.0 review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/validation"))

from ugas.schema_validation import validate_instance, validate_schema_document
from validate_github_review_manifest import validate_visual_manifest

EXPECTED_GATES = {"unit_tests", "official_validation", "state_consistency", "direction_runtime", "capability_matrix", "front_compatibility", "visual_transport", "workflow_validation", "manifest_validation", "security"}
BASELINE = "514a17818469b567966293db808cafbf708f8311"


def _truthful(value: dict[str, Any], total_key: str) -> bool:
    total = value.get(total_key)
    return value.get("status") == "passed" and value.get("exit_code") == 0 and value.get("parse_status") == "parsed" and isinstance(total, int) and value.get("passed") == total and value.get("failed") == 0


def _exists(root: Path, relative: str) -> bool:
    path = Path(relative)
    return not path.is_absolute() and (root / path).is_file()


def validate(manifest_path: Path, visual_path: Path, root: Path = ROOT) -> dict[str, Any]:
    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = json.loads((root / "schemas/github-review-manifest-v0160.json").read_text(encoding="utf-8"))
        validate_schema_document(schema)
        validate_instance(manifest, schema)
        visual = json.loads(visual_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return {"status": "V0160_GITHUB_REVIEW_MANIFEST_FAILED", "failures": [f"schema:{type(exc).__name__}:{exc}"]}
    pr = manifest["pull_request"]
    if pr["base_sha"] != BASELINE:
        failures.append("base-sha-must-bind-v0151-merge-commit")
    if pr["merge_base_sha"] != pr["base_sha"]:
        failures.append("merge-base-must-equal-pr-base")
    if manifest["change_statistics"]["files"] != len(manifest["changed_files"]):
        failures.append("change-statistics-file-count-mismatch")
    if not _truthful(manifest["tests"], "count"):
        failures.append("unit-result-not-truthful")
    if not _truthful(manifest["validation"], "checks"):
        failures.append("validation-result-not-truthful")
    gate_ids = {item.get("id") for item in manifest["gates"]}
    if gate_ids != EXPECTED_GATES:
        failures.append("gate-set-invalid")
    expected_overall = "PASS" if all(item.get("status") == "PASS" for item in manifest["gates"]) else "FAIL"
    if manifest["overall_status"] != expected_overall:
        failures.append("overall-status-does-not-match-gates")
    scope = manifest["scope"]
    if scope["version"] != "0.16.0" or scope["phase"] != "MULTI_DIRECTION_ANIMATION_RUNTIME" or scope["current_gate"] != "MULTI_DIRECTION_ANIMATION_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED":
        failures.append("active-scope-invalid")
    if manifest["current_state"]["version"] != "0.16.0" or manifest["current_state"]["production_approved"] is not False or manifest["current_state"]["production_routing"] != "BLOCKED":
        failures.append("current-state-production-boundary-invalid")
    historical = manifest["historical_release"]
    if historical["version"] != "0.15.1" or historical["merge_commit"] != BASELINE or historical["approved_head"] != "f89184cd2dd317cbba584ddcf6115301d90666ab" or historical["rejected_v0150_preserved"] is not True:
        failures.append("historical-v0151-v0150-binding-invalid")
    evidence = manifest["direction_runtime_evidence"]
    for key, relative in evidence.items():
        if not _exists(root, relative):
            failures.append(f"direction-evidence-missing:{key}")
    try:
        coverage = json.loads((root / evidence["coverage_manifest"]).read_text(encoding="utf-8"))
        fixture = json.loads((root / evidence["fixture_manifest"]).read_text(encoding="utf-8"))
        if coverage.get("production_registry") is not True or {item.get("direction") for item in coverage.get("assets", [])} != {"south"}:
            failures.append("production-coverage-must-be-south-only")
        if any(item.get("test_only") for item in coverage.get("assets", [])):
            failures.append("test-only-fixture-in-production-registry")
        if fixture.get("production_registry") is not False or fixture.get("unique_identity_count") != 8:
            failures.append("synthetic-fixture-boundary-invalid")
    except (OSError, json.JSONDecodeError, TypeError, AttributeError) as exc:
        failures.append(f"direction-evidence-read:{type(exc).__name__}:{exc}")
    if not _exists(root, manifest["front_compatibility_evidence"]["runtime_log"]):
        # The log is produced in the transient artifact, not in the checked-out repo.
        if manifest["front_compatibility_evidence"]["runtime_exit_code"] != 0:
            failures.append("front-compatibility-runtime-failed")
    forbidden = ("equipment", "outfit", "creature", "item", "environment", "ui/", "vfx", "visual-effects")
    for item in manifest["changed_files"]:
        path = str(item.get("path", "")).casefold()
        if any(token in path for token in forbidden):
            failures.append(f"forbidden-scope-change:{item.get('path')}")
    visual_result = validate_visual_manifest(visual, root)
    failures.extend(f"visual:{item}" for item in visual_result.get("failures", []))
    return {"status": "V0160_GITHUB_REVIEW_MANIFEST_PASSED" if not failures else "V0160_GITHUB_REVIEW_MANIFEST_FAILED", "failures": failures, "overall_status": manifest.get("overall_status"), "base_sha": pr.get("base_sha"), "head_sha": pr.get("head_sha"), "visual_count": visual_result.get("visual_count", 0)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("visual")
    parser.add_argument("--result-output")
    args = parser.parse_args()
    result = validate(Path(args.manifest), Path(args.visual))
    if args.result_output:
        Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "V0160_GITHUB_REVIEW_MANIFEST_PASSED" else 1)
