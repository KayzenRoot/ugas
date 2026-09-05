"""Enforce the v0.17.1 review result after artifact upload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def code(path: str) -> int | None:
    try: return int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError): return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", required=True); parser.add_argument("--manifest-validation", required=True); parser.add_argument("--security", required=True); parser.add_argument("--equipment-exit", required=True); parser.add_argument("--direction-exit", required=True); parser.add_argument("--front-compatibility-exit", required=True); args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8")); validation = json.loads(Path(args.manifest_validation).read_text(encoding="utf-8")); security = json.loads(Path(args.security).read_text(encoding="utf-8")); failures = []
    if manifest.get("overall_status") != "PASS": failures.append("manifest-overall-not-pass")
    failures.extend(f"gate-failed:{gate.get('id')}" for gate in manifest.get("gates", []) if gate.get("status") != "PASS")
    if validation.get("status") != "V0171_GITHUB_REVIEW_MANIFEST_PASSED": failures.append("manifest-validation-not-pass")
    if security.get("status") != "PASS": failures.append("security-not-pass")
    for name, path in (("equipment", args.equipment_exit), ("direction", args.direction_exit), ("front-compatibility", args.front_compatibility_exit)):
        if code(path) != 0: failures.append(f"{name}-not-pass")
    result = {"schema_version": "0.17.1", "status": "PASS" if not failures else "FAIL", "failures": failures}; print(json.dumps(result, indent=2, ensure_ascii=False)); raise SystemExit(0 if not failures else 1)
