"""Fail closed for v0.25.0 V1 final acceptance pre-upload artifact enforcement and post-upload final enforcement."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ugas.acceptance_v0250 import BASE_MAIN_SHA, BRANCH

REQUIRED_BASE_SHA = BASE_MAIN_SHA
REQUIRED_BRANCH = BRANCH
REQUIRED_PR_NUMBER: int | None = None


def _repository_head(root: Path) -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    head = result.stdout.strip()
    return head or None


def evaluate_enforcement(*, manifest: dict[str, Any], validation: dict[str, Any], security: dict[str, Any], state_exit: int, acceptance_exit: int, schema_exit: int, base_ref: str | None = None, head_ref: str | None = None, pr_number: str | None = None, stage: str = "final", require_security: bool = True, require_inventory: bool = True, repository_head: str | None = None) -> dict[str, Any]:
    pull_request = manifest.get("pull_request", {}) if isinstance(manifest.get("pull_request"), dict) else {}
    supplied_pr = None if pr_number is None else str(pr_number)
    manifest_pr = pull_request.get("number")
    checks = {
        "state_exit_zero": state_exit == 0,
        "acceptance_exit_zero": acceptance_exit == 0,
        "schema_exit_zero": schema_exit == 0,
        "manifest_pass": manifest.get("overall_status") == "PASS",
        "manifest_validation_pass": validation.get("status") == "PASS",
        "base_ref_matches_required": base_ref == REQUIRED_BASE_SHA,
        "manifest_pr_matches": str(manifest_pr) == supplied_pr and type(manifest_pr) is int and manifest_pr >= 1 and (REQUIRED_PR_NUMBER is None or manifest_pr == REQUIRED_PR_NUMBER),
        "manifest_head_matches": pull_request.get("head_sha") == head_ref and bool(head_ref),
        "manifest_base_matches": pull_request.get("base_sha") == base_ref == REQUIRED_BASE_SHA,
        "manifest_branch_matches": pull_request.get("head_branch") == REQUIRED_BRANCH,
        "repository_head_matches": bool(repository_head) and repository_head == head_ref,
    }
    if require_security:
        checks["security_pass"] = security.get("status") == "PASS"
    if require_inventory:
        checks["inventory_consistency"] = security.get("inventory_consistency") == "PASS"
        checks["inventory_digest_present"] = bool(security.get("inventory_digest"))
        checks["scanned_file_count_present"] = isinstance(security.get("scanned_file_count"), int) and security.get("scanned_file_count", 0) > 0
        checks["final_staged_file_count_present"] = isinstance(security.get("final_staged_file_count"), int) and security.get("final_staged_file_count", 0) > 0
    passed = all(checks.values())
    result = {
        "schema_version": "0.25.0",
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
            "final_staged_file_count": security.get("final_staged_file_count"),
            "state_exit": {"value": state_exit, "type": type(state_exit).__name__},
            "acceptance_exit": {"value": acceptance_exit, "type": type(acceptance_exit).__name__},
            "schema_exit": {"value": schema_exit, "type": type(schema_exit).__name__},
            "manifest_base_sha": pull_request.get("base_sha"),
            "manifest_head_sha": pull_request.get("head_sha"),
            "manifest_pr_number": manifest_pr,
            "manifest_head_branch": pull_request.get("head_branch"),
            "repository_head": repository_head,
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
    parser.add_argument("--acceptance-exit", required=True, type=int)
    parser.add_argument("--schema-exit", required=True, type=int)
    parser.add_argument("--repository-root", default=str(ROOT))
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
        acceptance_exit=args.acceptance_exit,
        schema_exit=args.schema_exit,
        base_ref=args.base_ref,
        head_ref=args.head_ref,
        pr_number=args.pr_number,
        stage=args.stage,
        require_security=require_security,
        require_inventory=require_inventory,
        repository_head=_repository_head(Path(args.repository_root)),
    )
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "PASS":
        title = "UGAS V1 final acceptance artifact preflight enforcement" if args.stage == "pre-upload" else "UGAS V1 final acceptance final enforcement"
        for name in result["failed_checks"]:
            print(f"::error title={title}::{name} failed")
        for failure in security.get("failures", []):
            print(f"::error title={title}::security:{failure}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
