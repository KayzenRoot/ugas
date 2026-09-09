"""Fail closed after the bounded v0.24.0 artifact upload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", required=True); parser.add_argument("--manifest-validation", required=True); parser.add_argument("--security", required=True); parser.add_argument("--state-exit", required=True, type=int); parser.add_argument("--orchestration-exit", required=True, type=int); args = parser.parse_args()
    values = [json.loads(Path(path).read_text(encoding="utf-8")) for path in (args.manifest, args.manifest_validation, args.security)]
    passed = args.state_exit == 0 and args.orchestration_exit == 0 and values[0].get("overall_status") == "PASS" and all(value.get("status") == "PASS" for value in values[1:])
    print(json.dumps({"status": "PASS" if passed else "FAIL", "manifest": values[0].get("overall_status"), "manifest_validation": values[1].get("status"), "security": values[2].get("status"), "state_exit": args.state_exit, "orchestration_exit": args.orchestration_exit}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
