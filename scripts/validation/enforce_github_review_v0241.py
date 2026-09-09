"""Fail closed after the bounded v0.24.1 artifact has been assembled."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-validation", required=True)
    parser.add_argument("--security", required=True)
    parser.add_argument("--state-exit", required=True, type=int)
    parser.add_argument("--orchestration-exit", required=True, type=int)
    parser.add_argument("--schema-exit", required=True, type=int)
    args = parser.parse_args()
    manifest, validation, security = [json.loads(Path(path).read_text(encoding="utf-8")) for path in (args.manifest, args.manifest_validation, args.security)]
    checks = {
        "state_exit_zero": args.state_exit == 0,
        "orchestration_exit_zero": args.orchestration_exit == 0,
        "schema_exit_zero": args.schema_exit == 0,
        "manifest_pass": manifest.get("overall_status") == "PASS",
        "manifest_validation_pass": validation.get("status") == "PASS",
        "security_pass": security.get("status") == "PASS",
    }
    passed = all(checks.values())
    result = {
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "failed_checks": [name for name, observed in checks.items() if not observed],
        "observed": {
            "manifest": {"value": manifest.get("overall_status"), "type": type(manifest.get("overall_status")).__name__},
            "manifest_validation": {"value": validation.get("status"), "type": type(validation.get("status")).__name__},
            "security": {"value": security.get("status"), "type": type(security.get("status")).__name__},
            "security_failures": security.get("failures"),
            "state_exit": {"value": args.state_exit, "type": type(args.state_exit).__name__},
            "orchestration_exit": {"value": args.orchestration_exit, "type": type(args.orchestration_exit).__name__},
            "schema_exit": {"value": args.schema_exit, "type": type(args.schema_exit).__name__},
        },
    }
    print(json.dumps(result, ensure_ascii=False))
    if not passed:
        for name in result["failed_checks"]:
            print(f"::error title=UGAS v0.24.1 final enforcement::{name} failed")
        for failure in security.get("failures", []):
            print(f"::error title=UGAS v0.24.1 final enforcement::security:{failure}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
