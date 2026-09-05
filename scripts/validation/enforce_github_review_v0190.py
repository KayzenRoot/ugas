"""Enforce the v0.19.0 review result after artifact upload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _code(path: str) -> int | None:
    try: return int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError): return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", required=True); parser.add_argument("--manifest-validation", required=True); parser.add_argument("--security", required=True); parser.add_argument("--state-exit", required=True); parser.add_argument("--items-props-exit", required=True); parser.add_argument("--direction-exit", required=True); parser.add_argument("--equipment-exit", required=True); parser.add_argument("--front-exit", required=True); args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8")); validation = json.loads(Path(args.manifest_validation).read_text(encoding="utf-8")); security = json.loads(Path(args.security).read_text(encoding="utf-8")); failures: list[str] = []
    if manifest.get("overall_status") != "PASS": failures.append("manifest-overall-not-pass")
    failures.extend(f"gate-failed:{item.get('id')}" for item in manifest.get("gates", []) if item.get("status") != "PASS")
    if validation.get("status") != "V0190_GITHUB_REVIEW_MANIFEST_PASSED": failures.append("manifest-validation-not-pass")
    if security.get("status") != "PASS": failures.append("security-not-pass")
    for name, path in (("state", args.state_exit), ("items-props", args.items_props_exit), ("direction", args.direction_exit), ("equipment", args.equipment_exit), ("front", args.front_exit)):
        if _code(path) != 0: failures.append(f"{name}-not-pass")
    boundary = manifest.get("production_boundary", {})
    if boundary.get("approved") is not False or boundary.get("routing") != "BLOCKED" or boundary.get("new_generation") != 0 or boundary.get("real_item_prop_asset_coverage") != "NONE": failures.append("production-boundary-invalid")
    result = {"schema_version": "0.19.0", "status": "PASS" if not failures else "FAIL", "failures": failures, "external_review_required": True, "do_not_merge": True}; print(json.dumps(result, indent=2, ensure_ascii=False)); raise SystemExit(0 if not failures else 1)
