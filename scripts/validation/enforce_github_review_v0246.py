"""Fail closed for v0.24.6 pre-upload artifact enforcement and post-upload final enforcement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def evaluate_enforcement(*, manifest: dict[str, Any], validation: dict[str, Any], security: dict[str, Any], state_exit: int, orchestration_exit: int, schema_exit: int, base_ref: str | None = None, head_ref: str | None = None, pr_number: str | None = None, stage: str = "final") -> dict[str, Any]:
    checks = {
        "state_exit_zero": state_exit == 0,
        "orchestration_exit_zero": orchestration_exit == 0,
        "schema_exit_zero": schema_exit == 0,
        "manifest_pass": manifest.get("overall_status") == "PASS",
        "manifest_validation_pass": validation.get("status") == "PASS",
        "security_pass": security.get("status") == "PASS",
    }
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
            "state_exit": {"value": state_exit, "type": type(state_exit).__name__},
            "orchestration_exit": {"value": orchestration_exit, "type": type(orchestration_exit).__name__},
            "schema_exit": {"value": schema_exit, "type": type(schema_exit).__name__},
        },
    }
    if base_ref is not None:
        result["base_ref"] = base_ref
    if head_ref is not None:
        result["head_ref"] = head_ref
    if pr_number is not None:
        result["pr_number"] = pr_number
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-validation", required=True)
    parser.add_argument("--security", required=True)
    parser.add_argument("--state-exit", required=True, type=int)
    parser.add_argument("--orchestration-exit", required=True, type=int)
    parser.add_argument("--schema-exit", required=True, type=int)
    parser.add_argument("--output")
    parser.add_argument("--stage", default="final", choices=("pre-upload", "final"))
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref")
    parser.add_argument("--pr-number")
    args = parser.parse_args()
    manifest, validation, security = [json.loads(Path(path).read_text(encoding="utf-8")) for path in (args.manifest, args.manifest_validation, args.security)]
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
    )
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "PASS":
        title = "UGAS v0.24.6 artifact preflight enforcement" if args.stage == "pre-upload" else "UGAS v0.24.6 final enforcement"
        for name in result["failed_checks"]:
            print(f"::error title={title}::{name} failed")
        for failure in security.get("failures", []):
            print(f"::error title={title}::security:{failure}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
