"""Fail-closed validation of the v0.17.1 bounded review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402

EXPECTED_GATES = {"unit_tests", "official_validation", "state_consistency", "equipment_runtime", "direction_runtime", "capability_matrix", "front_compatibility", "workflow_validation", "manifest_validation", "security"}
BASELINE = "a8d2897211c4b72c2cd2fe7a7f5729c7009d8566"; BRANCH = "codex/v0.17.0-equipment-outfits-runtime-foundation"; SHA = re.compile(r"^[0-9a-f]{40}$")


def truthful(value: dict[str, Any], total_key: str) -> bool:
    total = value.get(total_key); return value.get("status") == "passed" and value.get("exit_code") == 0 and value.get("parse_status") == "parsed" and isinstance(total, int) and value.get("passed") == total and value.get("failed") == 0


def validate(manifest_path: Path, root: Path = ROOT) -> dict[str, Any]:
    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")); schema = json.loads((root / "schemas/github-review-manifest-v0171.json").read_text(encoding="utf-8")); validate_schema_document(schema); validate_instance(manifest, schema)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc: return {"status": "V0171_GITHUB_REVIEW_MANIFEST_FAILED", "failures": [f"schema:{type(exc).__name__}:{exc}"]}
    pr = manifest["pull_request"]
    if not all(SHA.fullmatch(pr.get(key, "")) for key in ("base_sha", "head_sha", "merge_base_sha")): failures.append("commit-sha-invalid")
    if pr["base_sha"] != BASELINE or pr["merge_base_sha"] != BASELINE: failures.append("base-or-merge-base-must-bind-v0162-merge")
    if pr["number"] <= 0 or pr["base_branch"] != "main" or pr["head_branch"] != BRANCH: failures.append("pull-request-binding-invalid")
    if manifest["change_statistics"]["files"] != len(manifest["changed_files"]): failures.append("change-statistics-file-count-mismatch")
    if not truthful(manifest["tests"], "count"): failures.append("unit-result-not-truthful")
    if not truthful(manifest["validation"], "checks"): failures.append("validation-result-not-truthful")
    if {item.get("id") for item in manifest["gates"]} != EXPECTED_GATES: failures.append("gate-set-invalid")
    if manifest["overall_status"] != "PASS" or any(item.get("status") != "PASS" for item in manifest["gates"]): failures.append("overall-status-not-pass")
    scope = manifest["scope"]
    if scope["version"] != "0.17.1" or scope["phase"] != "EQUIPMENT_OUTFITS" or scope["current_gate"] != "EQUIPMENT_OUTFITS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED" or scope["allowed_next_actions"] != ["external_review_equipment_outfits_v0171"] or scope["new_generation"] != 0: failures.append("active-scope-invalid")
    current = manifest["current_state"]
    if current["version"] != "0.17.1" or current["phase"] != "EQUIPMENT_OUTFITS" or current["production_approved"] is not False or current["production_routing"] != "BLOCKED" or current["allowed_next_actions"] != ["external_review_equipment_outfits_v0171"]: failures.append("current-state-boundary-invalid")
    evidence = manifest["equipment_outfits_evidence"]
    for key, relative in evidence.items():
        path = Path(relative)
        if path.is_absolute() or not (root / path).is_file(): failures.append(f"evidence-missing:{key}")
    try:
        execution = json.loads((root / evidence["execution"]).read_text(encoding="utf-8")); negative = json.loads((root / evidence["negative_controls"]).read_text(encoding="utf-8")); fixture = json.loads((root / evidence["fixture_manifest"]).read_text(encoding="utf-8")); production = json.loads((root / evidence["production_registry"]).read_text(encoding="utf-8")); rejection = json.loads((root / evidence["rejection_record"]).read_text(encoding="utf-8")); controls = negative.get("controls", {})
        strict = all(item.get("rejected") is True and item.get("passed") is True and item.get("status") == "REJECTED" and item.get("mutation") and item.get("target_gate") and item.get("expected_error_code") and item.get("expected_rejection_class") and isinstance(item.get("observed"), dict) and item["observed"].get("result") == "REJECTED" and item["observed"].get("error_code") == item["expected_error_code"] and item["observed"].get("rejection_class") == item["expected_rejection_class"] for item in controls.values())
        if execution.get("schema_version") != "0.17.1" or execution.get("status") != "EQUIPMENT_OUTFITS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED" or execution.get("failed") != 0: failures.append("equipment-execution-not-qualified")
        if negative.get("status") != "EQ_NC_01_TO_15_PASSED" or len(controls) != 15 or not negative.get("strict") or not strict: failures.append("negative-controls-invalid")
        if fixture.get("schema_version") != "0.17.1" or fixture.get("production_registry") is not False or len(fixture.get("assets", [])) != 8 or any(item.get("test_only") is not True or item.get("production_safe") is not False for item in fixture.get("assets", [])): failures.append("fixture-production-boundary-invalid")
        if production.get("production_registry") is not True or production.get("assets") != []: failures.append("production-registry-not-empty")
        if rejection.get("rejected_reviewed_head") != "1c73e6a2ff5259226afe9ca03ef10e1822a7fdf2" or rejection.get("status") != "CORRECTION_REQUIRED": failures.append("v0170-rejection-history-invalid")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc: failures.append(f"evidence-read:{type(exc).__name__}:{exc}")
    forbidden = {"creatures", "creature", "monsters", "monster", "items", "item", "environment", "maps", "ui_asset_family", "vfx_asset_family", "diffusion", "sam2"}
    for item in manifest["changed_files"]:
        path = str(item.get("path", ""))
        if forbidden.intersection(segment.casefold() for segment in re.split(r"[\\/]", path)): failures.append(f"forbidden-scope-change:{path}")
    return {"status": "V0171_GITHUB_REVIEW_MANIFEST_PASSED" if not failures else "V0171_GITHUB_REVIEW_MANIFEST_FAILED", "failures": failures, "overall_status": manifest.get("overall_status"), "base_sha": pr.get("base_sha"), "head_sha": pr.get("head_sha"), "pr_number": pr.get("number")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("manifest"); parser.add_argument("--result-output"); args = parser.parse_args(); result = validate(Path(args.manifest));
    if args.result_output: Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False)); raise SystemExit(0 if result["status"] == "V0171_GITHUB_REVIEW_MANIFEST_PASSED" else 1)
