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
    passed = (
        args.state_exit == 0
        and args.orchestration_exit == 0
        and args.schema_exit == 0
        and manifest.get("overall_status") == "PASS"
        and validation.get("status") == "PASS"
        and security.get("status") == "PASS"
    )
    result = {"status": "PASS" if passed else "FAIL", "manifest": manifest.get("overall_status"), "manifest_validation": validation.get("status"), "security": security.get("status"), "state_exit": args.state_exit, "orchestration_exit": args.orchestration_exit, "schema_exit": args.schema_exit}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
