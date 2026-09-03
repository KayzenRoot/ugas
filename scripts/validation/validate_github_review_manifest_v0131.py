"""Fail-closed validation for the active v0.13.1 review manifest."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts/validation"))
from ugas.schema_validation import validate_instance, validate_schema_document
from validate_github_review_manifest import validate_visual_manifest

EXPECTED_GATES = {"unit_tests", "official_validation", "state_consistency", "capability_matrix", "visual_transport", "workflow_validation", "manifest_validation", "security"}


def _truthful(value: dict[str, Any], key: str) -> bool:
    total = value.get(key)
    return ((value.get("status") == "passed" and value.get("exit_code") == 0 and value.get("parse_status") == "parsed" and isinstance(total, int) and value.get("passed") == total and value.get("failed") == 0) or (value.get("status") in {"failed", "parse_failed", "not_run"} and isinstance(value.get("exit_code"), int)))


def validate(manifest_path: Path, visual_path: Path, root: Path = ROOT) -> dict[str, Any]:
    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")); schema = json.loads((root / "schemas/github-review-manifest-v0131.json").read_text(encoding="utf-8")); validate_schema_document(schema); validate_instance(manifest, schema); visual = json.loads(visual_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return {"status": "V0131_GITHUB_REVIEW_MANIFEST_FAILED", "failures": [f"schema:{type(exc).__name__}:{exc}"]}
    pr = manifest["pull_request"]; gaps = set(manifest.get("known_gaps", [])); context = manifest.get("gap_context", {})
    if pr["number"] > 0 and "GITHUB_PR_CREATE_GAP" in gaps: failures.append("pr-number-positive-cannot-have-github-pr-create-gap")
    if pr["number"] == 0 and context.get("source") == "local_rehearsal" and "LOCAL_REHEARSAL_PR_NOT_AVAILABLE" not in gaps: failures.append("local-rehearsal-gap-description-missing")
    if manifest.get("change_statistics", {}).get("files") != len(manifest.get("changed_files", [])): failures.append("change-statistics-file-count-mismatch")
    if not _truthful(manifest.get("tests", {}), "count"): failures.append("unit-result-not-truthful")
    if not _truthful(manifest.get("validation", {}), "checks"): failures.append("validation-result-not-truthful")
    gate_ids = {item.get("id") for item in manifest.get("gates", []) if isinstance(item, dict)}
    if gate_ids != EXPECTED_GATES: failures.append("gate-set-invalid")
    if manifest.get("overall_status") != ("PASS" if manifest.get("gates") and all(item.get("status") == "PASS" for item in manifest["gates"]) else "FAIL"): failures.append("overall-status-does-not-match-gates")
    if manifest.get("scope", {}).get("version") != "0.13.1" or manifest.get("scope", {}).get("phase") != "RUN_FRONT_V1": failures.append("active-scope-invalid")
    if manifest.get("current_state", {}).get("production_approved") is not False or manifest.get("current_state", {}).get("production_routing") != "BLOCKED": failures.append("production-boundary-invalid")
    visual_result = validate_visual_manifest(visual, root); failures.extend(f"visual:{item}" for item in visual_result.get("failures", []))
    return {"status": "V0131_GITHUB_REVIEW_MANIFEST_PASSED" if not failures else "V0131_GITHUB_REVIEW_MANIFEST_FAILED", "failures": failures, "overall_status": manifest.get("overall_status"), "base_sha": pr.get("base_sha"), "head_sha": pr.get("head_sha"), "visual_count": visual_result.get("visual_count", 0)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument("manifest"); parser.add_argument("visual"); parser.add_argument("--result-output"); args = parser.parse_args(); result = validate(Path(args.manifest), Path(args.visual))
    if args.result_output: Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False)); raise SystemExit(0 if result["status"] == "V0131_GITHUB_REVIEW_MANIFEST_PASSED" else 1)
