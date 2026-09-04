"""Fail-closed bounded-artifact security validation for v0.15.0."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate_github_review_security_v0124 import validate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--artifact-dir", required=True); parser.add_argument("--manifest"); parser.add_argument("--output"); args = parser.parse_args()
    result = validate(Path(args.artifact_dir), Path(args.manifest) if args.manifest else None); result["schema_version"] = "0.15.0"
    if args.output: Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False)); raise SystemExit(0 if result["status"] == "PASS" else 1)
