"""Fail-closed validation of the v0.18.0 bounded review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_GATES = {"unit_tests", "official_validation", "state_consistency", "creatures_runtime", "direction_runtime", "capability_matrix", "front_compatibility", "workflow_validation", "manifest_validation", "security"}
BASELINE = "39e148bef50c8f04db194048dbe9fbb15d8ff3d4"; BRANCH = "codex/v0.18.0-creatures-monsters-runtime-foundation"; SHA = re.compile(r"^[0-9a-f]{40}$")


def truthful(value: dict[str, Any], total_key: str) -> bool:
    total = value.get(total_key); return value.get("status") == "passed" and value.get("exit_code") == 0 and value.get("parse_status") == "parsed" and isinstance(total, int) and value.get("passed") == total and value.get("failed") == 0


def validate(manifest_path: Path, root: Path = ROOT) -> dict[str, Any]:
    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")); schema = json.loads((root / "schemas/github-review-manifest-v0180.json").read_text(encoding="utf-8"))
        from ugas.schema_validation import validate_instance, validate_schema_document
        validate_schema_document(schema); validate_instance(manifest, schema)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return {"status": "V0180_GITHUB_REVIEW_MANIFEST_FAILED", "failures": [f"schema:{type(exc).__name__}:{exc}"]}
    pr = manifest["pull_request"]
    if not all(SHA.fullmatch(pr.get(key, "")) for key in ("base_sha", "head_sha", "merge_base_sha")): failures.append("commit-sha-invalid")
    if pr["base_sha"] != BASELINE or pr["merge_base_sha"] != BASELINE: failures.append("base-or-merge-base-must-bind-v0171-merge")
    if pr["number"] <= 0 or pr["base_branch"] != "main" or pr["head_branch"] != BRANCH: failures.append("pull-request-binding-invalid")
    if manifest["change_statistics"]["files"] != len(manifest["changed_files"]): failures.append("change-statistics-file-count-mismatch")
    if not truthful(manifest["tests"], "count"): failures.append("unit-result-not-truthful")
    if not truthful(manifest["validation"], "checks"): failures.append("validation-result-not-truthful")
    if {item.get("id") for item in manifest["gates"]} != EXPECTED_GATES: failures.append("gate-set-invalid")
    if manifest["overall_status"] != "PASS" or any(item.get("status") != "PASS" for item in manifest["gates"]): failures.append("overall-status-not-pass")
    scope = manifest["scope"]
    if scope["version"] != "0.18.0" or scope["phase"] != "CREATURES_MONSTERS" or scope["current_gate"] != "CREATURES_MONSTERS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" or scope["allowed_next_actions"] != ["external_review_creatures_monsters_v0180"] or scope["new_generation"] != 0: failures.append("active-scope-invalid")
    current = manifest["current_state"]
    if current["version"] != "0.18.0" or current["phase"] != "CREATURES_MONSTERS" or current["production_approved"] is not False or current["production_routing"] != "BLOCKED" or current["allowed_next_actions"] != ["external_review_creatures_monsters_v0180"]: failures.append("current-state-boundary-invalid")
    evidence = manifest["creatures_monsters_evidence"]
    for key, relative in evidence.items():
        if key == "manifest":
            pass
        path = Path(relative)
        if path.is_absolute() or not (root / path).is_file(): failures.append(f"evidence-missing:{key}")
    try:
        execution = json.loads((root / evidence["execution"]).read_text(encoding="utf-8")); negative = json.loads((root / evidence["negative_controls"]).read_text(encoding="utf-8")); fixture = json.loads((root / evidence["fixture_manifest"]).read_text(encoding="utf-8")); production = json.loads((root / evidence["production_registry"]).read_text(encoding="utf-8")); controls = negative.get("controls", {})
        strict = all(item.get("rejected") is True and item.get("passed") is True and item.get("status") == "REJECTED" and item.get("mutation") and item.get("target_gate") and item.get("expected_error_code") and item.get("expected_rejection_class") and isinstance(item.get("observed"), dict) and item["observed"].get("result") == "REJECTED" and item["observed"].get("error_code") == item["expected_error_code"] and item["observed"].get("rejection_class") == item["expected_rejection_class"] for item in controls.values())
        if execution.get("schema_version") != "0.18.0" or execution.get("status") != "CREATURES_MONSTERS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" or execution.get("failed") != 0: failures.append("creature-execution-not-qualified")
        if negative.get("status") != "CR_NC_01_TO_15_PASSED" or len(controls) != 15 or not negative.get("strict") or not strict: failures.append("negative-controls-invalid")
        if fixture.get("schema_version") != "0.18.0" or fixture.get("production_registry") is not False or fixture.get("fixture_count") != 6 or fixture.get("unique_hash_count") != 6 or any(item.get("test_only") is not True or item.get("production_safe") is not False for item in fixture.get("fixtures", [])): failures.append("fixture-production-boundary-invalid")
        if production.get("production_registry") is not True or production.get("assets") != [] or production.get("production_routing") != "BLOCKED": failures.append("production-registry-not-empty-or-blocked")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc: failures.append(f"evidence-read:{type(exc).__name__}:{exc}")
    forbidden = {"items", "item", "environment", "maps", "ui_asset_family", "vfx_asset_family", "diffusion", "sam2"}
    for item in manifest["changed_files"]:
        path = str(item.get("path", ""))
        if forbidden.intersection(segment.casefold() for segment in re.split(r"[\\/]", path)): failures.append(f"forbidden-scope-change:{path}")
    return {"status": "V0180_GITHUB_REVIEW_MANIFEST_PASSED" if not failures else "V0180_GITHUB_REVIEW_MANIFEST_FAILED", "failures": failures, "overall_status": manifest.get("overall_status"), "base_sha": pr.get("base_sha"), "head_sha": pr.get("head_sha"), "pr_number": pr.get("number")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("manifest"); parser.add_argument("--result-output"); args = parser.parse_args(); result = validate(Path(args.manifest));
    if args.result_output: Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False)); raise SystemExit(0 if result["status"] == "V0180_GITHUB_REVIEW_MANIFEST_PASSED" else 1)
