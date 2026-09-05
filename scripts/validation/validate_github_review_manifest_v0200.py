"""Fail-closed validation of the bounded v0.20.0 review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("manifest", type=Path); parser.add_argument("--result-output", type=Path, required=True); args = parser.parse_args()
    failures: list[str] = []
    try:
        value = json.loads(args.manifest.read_text(encoding="utf-8"))
        required = ("schema_version", "manifest_type", "pull_request", "scope", "tests", "validation", "gates", "environment_tilesets_evidence", "production_boundary", "review_boundary")
        failures.extend(f"missing:{name}" for name in required if name not in value)
        if value.get("schema_version") != "0.20.0" or value.get("manifest_type") != "github-ci-environment-tilesets-v0200-review": failures.append("manifest-identity-invalid")
        if value.get("scope", {}).get("version") != "0.20.0" or value.get("scope", {}).get("phase") != "ENVIRONMENT_TILESETS" or value.get("scope", {}).get("current_gate") != "ENVIRONMENT_TILESETS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED": failures.append("active-scope-invalid")
        if value.get("production_boundary") != {"approved": False, "routing": "BLOCKED", "new_generation": 0, "real_environment_asset_coverage": "NONE", "synthetic_environment_fixture": "TEST_ONLY"}: failures.append("production-boundary-invalid")
        if value.get("review_boundary", {}).get("external_review_required") is not True or value.get("review_boundary", {}).get("do_not_merge") is not True or value.get("review_boundary", {}).get("merge_authorization") != "NOT_AUTHORIZED": failures.append("review-boundary-invalid")
        if value.get("tests", {}).get("status") != "passed" or value.get("tests", {}).get("failed") != 0: failures.append("unit-tests-not-pass")
        if value.get("validation", {}).get("status") != "passed" or value.get("validation", {}).get("failed") != 0: failures.append("official-validation-not-pass")
        gates = value.get("gates", {})
        if not gates or any(item.get("status") != "PASS" for item in gates.values()): failures.append("gates-not-pass")
        if value.get("overall_status") != "PASS": failures.append("overall-status-not-pass")
        evidence = value.get("environment_tilesets_evidence", {})
        for relative in evidence.values():
            if not Path(relative).is_file(): failures.append(f"evidence-missing:{relative}")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        failures.append(f"manifest-read:{type(exc).__name__}:{exc}")
    result = {"schema_version": "0.20.0", "status": "PASS" if not failures else "FAIL", "failures": failures, "checked_manifest": str(args.manifest)}
    args.result_output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
