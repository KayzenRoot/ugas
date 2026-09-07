"""Fail closed after the v0.23.0 bounded artifact upload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--manifest-validation", type=Path, required=True); parser.add_argument("--security", type=Path, required=True); parser.add_argument("--vfx-exit", type=Path, required=True); parser.add_argument("--state-exit", type=Path, required=True); args = parser.parse_args(); failures: list[str] = []
    for path in (args.manifest, args.manifest_validation, args.security):
        if not path.is_file(): failures.append(f"missing:{path}")
    if args.manifest.is_file() and json.loads(args.manifest.read_text(encoding="utf-8")).get("overall_status") != "PASS": failures.append("manifest-not-pass")
    if args.manifest_validation.is_file() and json.loads(args.manifest_validation.read_text(encoding="utf-8")).get("status") != "PASS": failures.append("manifest-validation-failed")
    if args.security.is_file() and json.loads(args.security.read_text(encoding="utf-8")).get("status") != "PASS": failures.append("security-validation-failed")
    for path in (args.vfx_exit, args.state_exit):
        if not path.is_file() or path.read_text(encoding="utf-8").strip() != "0": failures.append(f"gate-failed:{path.name}")
    result = {"status": "PASS" if not failures else "FAIL", "failures": failures, "stop": "PR_OPEN_UNMERGED" if not failures else "REVIEW_BLOCKED"}
    print(json.dumps(result)); return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
