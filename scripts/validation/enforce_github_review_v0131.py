"""Enforce active v0.13.1 review gates after artifact upload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", required=True); parser.add_argument("--manifest-validation", required=True); parser.add_argument("--security", required=True); parser.add_argument("--runtime-exit", required=True); args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8")); validation = json.loads(Path(args.manifest_validation).read_text(encoding="utf-8")); security = json.loads(Path(args.security).read_text(encoding="utf-8")); failures: list[str] = []
    if manifest.get("overall_status") != "PASS": failures.append("manifest-overall-not-pass")
    failures.extend(f"gate-failed:{gate.get('id')}:{gate.get('detail')}" for gate in manifest.get("gates", []) if gate.get("status") != "PASS")
    if validation.get("status") != "V0131_GITHUB_REVIEW_MANIFEST_PASSED": failures.append("manifest-validation-not-pass")
    if security.get("status") != "PASS": failures.append("security-not-pass")
    try:
        if int(Path(args.runtime_exit).read_text(encoding="utf-8").strip()) != 0: failures.append("run-front-runtime-not-pass")
    except (OSError, ValueError): failures.append("run-front-runtime-exit-unavailable")
    result = {"schema_version": "0.13.1", "status": "PASS" if not failures else "FAIL", "failures": failures}; print(json.dumps(result, indent=2, ensure_ascii=False)); return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
