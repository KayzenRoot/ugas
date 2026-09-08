"""Fail closed after the v0.23.3 bounded artifact upload."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--manifest", type=Path, required=True); p.add_argument("--manifest-validation", type=Path, required=True); p.add_argument("--security", type=Path, required=True); p.add_argument("--vfx-exit", type=Path, required=True); p.add_argument("--state-exit", type=Path, required=True); a = p.parse_args(); failures = []
    for path in (a.manifest, a.manifest_validation, a.security):
        if not path.is_file(): failures.append(f"missing:{path}")
    if a.manifest.is_file() and json.loads(a.manifest.read_text(encoding="utf-8")).get("overall_status") != "PASS": failures.append("manifest-not-pass")
    if a.manifest_validation.is_file() and json.loads(a.manifest_validation.read_text(encoding="utf-8")).get("status") != "PASS": failures.append("manifest-validation-failed")
    if a.security.is_file() and json.loads(a.security.read_text(encoding="utf-8")).get("status") != "PASS": failures.append("security-validation-failed")
    for path in (a.vfx_exit, a.state_exit):
        if not path.is_file() or path.read_text(encoding="utf-8").strip() != "0": failures.append(f"gate-failed:{path.name}")
    result = {"status": "PASS" if not failures else "FAIL", "failures": failures, "stop": "PR_OPEN_UNMERGED" if not failures else "REVIEW_BLOCKED"}; print(json.dumps(result)); return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
