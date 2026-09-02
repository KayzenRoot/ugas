"""Enforce the final v0.12.3 review result after artifact upload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-validation", required=True)
    parser.add_argument("--security", required=True)
    args = parser.parse_args()
    manifest = load(Path(args.manifest))
    validation = load(Path(args.manifest_validation))
    security = load(Path(args.security))
    failures: list[str] = []
    if manifest.get("overall_status") != "PASS":
        failures.append("manifest-overall-not-pass")
    for gate in manifest.get("gates", []):
        if gate.get("status") != "PASS":
            failures.append(f"gate-failed:{gate.get('id')}:{gate.get('detail')}")
    if validation.get("status") != "GITHUB_REVIEW_MANIFEST_PASSED":
        failures.append("manifest-validation-not-pass")
    if security.get("status") != "PASS":
        failures.append("security-not-pass")
    result = {"schema_version": "0.12.3", "status": "PASS" if not failures else "FAIL", "failures": failures}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
