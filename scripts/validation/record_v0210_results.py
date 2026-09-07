"""Record bounded PR-run results for the v0.21.3 review artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _code(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 99


def _test_result(log: str, exit_code: int) -> dict:
    matches = re.findall(r"Ran (\d+) tests", log)
    count = int(matches[-1]) if matches else 0
    return {"schema_version": "0.21.3", "status": "passed" if exit_code == 0 and count > 0 else "failed", "count": count, "passed": count if exit_code == 0 else 0, "failed": 0 if exit_code == 0 else 1, "exit_code": exit_code}


def _validation_result(log: str, exit_code: int) -> dict:
    matches = re.findall(r"SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)", log)
    checks, passed, failed = (map(int, matches[-1]) if matches else (0, 0, 1))
    return {"schema_version": "0.21.3", "status": "passed" if exit_code == 0 and failed == 0 else "failed", "checks": checks, "passed": passed, "failed": failed, "exit_code": exit_code}


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("output-dir", "tests-log", "validation-log"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("test-exit-code", "validation-exit-code", "environment-exit-code", "state-exit-code", "regressions-exit-code", "matrix-exit-code", "workflow-exit-code"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tests = _test_result(_text(args.tests_log), _code(args.test_exit_code))
    validation = _validation_result(_text(args.validation_log), _code(args.validation_exit_code))
    gates = {
        "unit_tests": {"status": "PASS" if tests["status"] == "passed" else "FAIL", "detail": tests},
        "official_validation": {"status": "PASS" if validation["status"] == "passed" else "FAIL", "detail": validation},
        "maps_minimap_runtime": {"status": "PASS" if _code(args.environment_exit_code) == 0 else "FAIL", "detail": "run_maps_minimap_runtime_v0210.py (v0.21.3 correction)"},
        "state_consistency": {"status": "PASS" if _code(args.state_exit_code) == 0 else "FAIL", "detail": "validate_post_merge_closure_v0213.py"},
        "frozen_regressions": {"status": "PASS" if _code(args.regressions_exit_code) == 0 else "FAIL", "detail": "historical runtime regressions"},
        "capability_matrix": {"status": "PASS" if _code(args.matrix_exit_code) == 0 else "FAIL", "detail": "validate_v1_capability_matrix.py"},
        "workflow_validation": {"status": "PASS" if _code(args.workflow_exit_code) == 0 else "FAIL", "detail": "validate_github_workflows_v0124.py"},
    }
    overall = "PASS" if all(item["status"] == "PASS" for item in gates.values()) else "FAIL"
    (args.output_dir / "test-results-v0213.json").write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "validation-results-v0213.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "gate-results-v0213.json").write_text(json.dumps({"schema_version": "0.21.3", "gates": gates, "overall_status": overall}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0213_RESULTS_RECORDED", "overall_status": overall, "test_count": tests["count"], "validation_checks": validation["checks"]}))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
