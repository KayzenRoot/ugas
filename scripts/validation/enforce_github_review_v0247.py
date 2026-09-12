"""Fail closed for v0.24.7 pre-upload artifact enforcement and post-upload final enforcement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_BASE_SHA = "dee98f8cd89ebd83a36ead7a22a184700d6e916f"
REQUIRED_BRANCH = "codex/v0.24.0-orchestration-runtime-hardening-foundation"
REQUIRED_PR_NUMBER = 15


def evaluate_enforcement(*, manifest: dict[str, Any], validation: dict[str, Any], security: dict[str, Any], state_exit: int, orchestration_exit: int, schema_exit: int, base_ref: str | None = None, head_ref: str | None = None, pr_number: str | None = None, stage: str = "final", require_security: bool = True, require_inventory: bool = True) -> dict[str, Any]:
    pull_request = manifest.get("pull_request", {}) if isinstance(manifest.get("pull_request"), dict) else {}
    supplied_pr = None if pr_number is None else str(pr_number)
    manifest_pr = pull_request.get("number")
    legacy_v0247_identity = supplied_pr == str(REQUIRED_PR_NUMBER) and base_ref == REQUIRED_BASE_SHA and manifest.get("schema_version") == "0.24.7"
    checks = {
        "state_exit_zero": state_exit == 0,
        "orchestration_exit_zero": orchestration_exit == 0,
        "schema_exit_zero": schema_exit == 0,
        "manifest_pass": manifest.get("overall_status") == "PASS",
        "manifest_validation_pass": validation.get("status") == "PASS",
        "base_ref_matches_required": (base_ref == REQUIRED_BASE_SHA) if legacy_v0247_identity else bool(base_ref),
        "manifest_pr_matches": str(manifest_pr) == supplied_pr and (str(manifest_pr) == str(REQUIRED_PR_NUMBER) if legacy_v0247_identity else str(manifest_pr).isdigit() and int(manifest_pr) > 0),
        "manifest_head_matches": pull_request.get("head_sha") == head_ref and bool(head_ref),
        "manifest_base_matches": pull_request.get("base_sha") == base_ref == REQUIRED_BASE_SHA,
        "manifest_branch_matches": (pull_request.get("head_branch") == REQUIRED_BRANCH) if legacy_v0247_identity else bool(pull_request.get("head_branch")),
    }
    if require_security:
        checks["security_pass"] = security.get("status") == "PASS"
    if require_inventory:
        checks["inventory_consistency"] = security.get("inventory_consistency") == "PASS"
        checks["inventory_digest_present"] = bool(security.get("inventory_digest"))
        checks["scanned_file_count_present"] = isinstance(security.get("scanned_file_count"), int) and security.get("scanned_file_count", 0) > 0
    passed = all(checks.values())
    result = {
        "status": "PASS" if passed else "FAIL",
        "stage": stage,
        "checks": checks,
        "failed_checks": [name for name, observed in checks.items() if not observed],
        "observed": {
            "manifest": {"value": manifest.get("overall_status"), "type": type(manifest.get("overall_status")).__name__},
            "manifest_validation": {"value": validation.get("status"), "type": type(validation.get("status")).__name__},
            "security": {"value": security.get("status"), "type": type(security.get("status")).__name__},
            "security_failures": security.get("failures"),
            "inventory_digest": security.get("inventory_digest"),
            "scanned_file_count": security.get("scanned_file_count"),
            "state_exit": {"value": state_exit, "type": type(state_exit).__name__},
            "orchestration_exit": {"value": orchestration_exit, "type": type(orchestration_exit).__name__},
            "schema_exit": {"value": schema_exit, "type": type(schema_exit).__name__},
            "manifest_base_sha": pull_request.get("base_sha"),
            "manifest_head_sha": pull_request.get("head_sha"),
            "manifest_pr_number": manifest_pr,
            "manifest_head_branch": pull_request.get("head_branch"),
        },
        "base_ref": base_ref,
        "head_ref": head_ref,
        "pr_number": pr_number,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-validation", required=True)
    parser.add_argument("--security")
    parser.add_argument("--state-exit", required=True, type=int)
    parser.add_argument("--orchestration-exit", required=True, type=int)
    parser.add_argument("--schema-exit", required=True, type=int)
    parser.add_argument("--output")
    parser.add_argument("--stage", default="final", choices=("pre-upload", "final"))
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref")
    parser.add_argument("--pr-number")
    parser.add_argument("--require-security", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--require-inventory", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    validation = json.loads(Path(args.manifest_validation).read_text(encoding="utf-8"))
    security = json.loads(Path(args.security).read_text(encoding="utf-8")) if args.security and Path(args.security).is_file() else {}
    require_security = args.require_security if args.require_security is not None else args.stage != "pre-upload"
    require_inventory = args.require_inventory if args.require_inventory is not None else args.stage != "pre-upload"
    result = evaluate_enforcement(
        manifest=manifest,
        validation=validation,
        security=security,
        state_exit=args.state_exit,
        orchestration_exit=args.orchestration_exit,
        schema_exit=args.schema_exit,
        base_ref=args.base_ref,
        head_ref=args.head_ref,
        pr_number=args.pr_number,
        stage=args.stage,
        require_security=require_security,
        require_inventory=require_inventory,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "PASS":
        title = "UGAS v0.24.7 artifact preflight enforcement" if args.stage == "pre-upload" else "UGAS v0.24.7 final enforcement"
        for name in result["failed_checks"]:
            print(f"::error title={title}::{name} failed")
        for failure in security.get("failures", []):
            print(f"::error title={title}::security:{failure}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
