"""Fail-closed validation of the bounded v0.19.0 review manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402

BASELINE = "52938a04016352d50ad54621a4df981a9c36b058"; BRANCH = "codex/v0.19.0-items-props-runtime-foundation"; SHA = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_GATES = {"unit_tests", "official_validation", "state_consistency", "items_props_runtime", "direction_runtime", "equipment_runtime", "front_compatibility", "capability_matrix", "workflow_validation", "manifest_validation", "security"}


def _truthful(value: dict[str, Any], total_key: str) -> bool:
    return value.get("status") == "passed" and value.get("exit_code") == 0 and value.get("parse_status") == "parsed" and isinstance(value.get(total_key), int) and value.get("passed") == value.get(total_key) and value.get("failed") == 0


def validate(path: Path, root: Path = ROOT) -> dict[str, Any]:
    failures: list[str] = []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8")); schema = json.loads((root / "schemas/github-review-manifest-v0190.json").read_text(encoding="utf-8")); validate_schema_document(schema); validate_instance(manifest, schema)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return {"status": "V0190_GITHUB_REVIEW_MANIFEST_FAILED", "failures": [f"schema:{type(exc).__name__}:{exc}"]}
    pr = manifest["pull_request"]
    if not all(SHA.fullmatch(pr.get(key, "")) for key in ("base_sha", "head_sha", "merge_base_sha")): failures.append("commit-sha-invalid")
    if pr["base_sha"] != BASELINE or pr["merge_base_sha"] != BASELINE: failures.append("base-or-merge-base-must-bind-v0182-merge")
    if pr["number"] <= 0 or pr["base_branch"] != "main" or pr["head_branch"] != BRANCH: failures.append("pull-request-binding-invalid")
    if manifest["change_statistics"]["files"] != len(manifest["changed_files"]): failures.append("change-statistics-file-count-mismatch")
    if not _truthful(manifest["tests"], "count"): failures.append("unit-result-not-truthful")
    if not _truthful(manifest["validation"], "checks"): failures.append("validation-result-not-truthful")
    gates = manifest["gates"]
    if {item.get("id") for item in gates} != EXPECTED_GATES: failures.append("gate-set-invalid")
    if manifest["overall_status"] != "PASS" or any(item.get("status") != "PASS" for item in gates): failures.append("overall-status-not-pass")
    scope = manifest["scope"]
    if scope["version"] != "0.19.0" or scope["phase"] != "ITEMS_PROPS" or scope["current_gate"] != "ITEMS_PROPS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" or scope["allowed_next_actions"] != ["external_review_items_props_v0190"] or scope["new_generation"] != 0: failures.append("active-scope-invalid")
    current = manifest["current_state"]
    if current["version"] != "0.19.0" or current["phase"] != "ITEMS_PROPS" or current["production_approved"] is not False or current["production_routing"] != "BLOCKED" or current["allowed_next_actions"] != ["external_review_items_props_v0190"]: failures.append("current-state-boundary-invalid")
    evidence = manifest["items_props_evidence"]
    for key, relative in evidence.items():
        candidate = Path(relative)
        if candidate.is_absolute() or not (root / candidate).is_file(): failures.append(f"evidence-missing:{key}")
    execution = _load(root / evidence["execution"]); negative = _load(root / evidence["negative_controls"]); fixture = _load(root / evidence["fixtures"]); production = _load(root / evidence["production_registry"]); determinism = _load(root / evidence["determinism"])
    if execution.get("status") != "ITEMS_PROPS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" or execution.get("failed") != 0: failures.append("item-prop-execution-not-qualified")
    controls = negative.get("controls", {})
    strict = len(controls) == 17 and all(item.get("rejected") is True and item.get("passed") is True and item.get("status") == "REJECTED" and item.get("observed", {}).get("result") == "REJECTED" and item["observed"].get("error_code") == item.get("expected_error_code") and item["observed"].get("rejection_class") == item.get("expected_rejection_class") for item in controls.values())
    if negative.get("status") != "ITEM_PROP_NEGATIVE_CONTROLS_01_TO_17_PASSED" or not strict: failures.append("negative-controls-invalid")
    if fixture.get("fixture_count") != 6 or fixture.get("unique_hash_count") != 6 or fixture.get("production_registry") is not False: failures.append("fixture-boundary-invalid")
    if production.get("production_registry") is not True or production.get("items") != [] or production.get("variants") != [] or production.get("production_routing") != "BLOCKED": failures.append("production-registry-invalid")
    if determinism.get("status") != "TWO_RUN_DETERMINISM_PASSED" or determinism.get("second_run_reads_first_run") is not False: failures.append("determinism-invalid")
    forbidden = {"environment", "maps", "ui_asset_family", "vfx_asset_family", "diffusion", "sam2"}
    for item in manifest["changed_files"]:
        if forbidden.intersection(segment.casefold() for segment in re.split(r"[\\/]", str(item.get("path", "")))): failures.append(f"forbidden-scope-change:{item.get('path')}")
    return {"status": "V0190_GITHUB_REVIEW_MANIFEST_PASSED" if not failures else "V0190_GITHUB_REVIEW_MANIFEST_FAILED", "failures": failures, "overall_status": manifest.get("overall_status"), "base_sha": pr.get("base_sha"), "head_sha": pr.get("head_sha"), "pr_number": pr.get("number")}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("manifest"); parser.add_argument("--result-output"); args = parser.parse_args(); result = validate(Path(args.manifest));
    if args.result_output: Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False)); raise SystemExit(0 if result["status"] == "V0190_GITHUB_REVIEW_MANIFEST_PASSED" else 1)
