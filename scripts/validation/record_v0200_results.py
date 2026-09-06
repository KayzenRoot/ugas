"""Record bounded PR-run results for the v0.20.0 review artifact."""

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
    match = re.search(r"Ran (\d+) tests", log)
    count = int(match.group(1)) if match else 0
    return {"schema_version": "0.20.0", "status": "passed" if exit_code == 0 and count > 0 else "failed", "count": count, "passed": count if exit_code == 0 else 0, "failed": 0 if exit_code == 0 else 1, "exit_code": exit_code}


def _validation_result(log: str, exit_code: int) -> dict:
    match = re.search(r"SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)", log)
    checks, passed, failed = (map(int, match.groups()) if match else (0, 0, 1))
    return {"schema_version": "0.20.0", "status": "passed" if exit_code == 0 and failed == 0 else "failed", "checks": checks, "passed": passed, "failed": failed, "exit_code": exit_code}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tests-log", type=Path, required=True)
    parser.add_argument("--validation-log", type=Path, required=True)
    parser.add_argument("--test-exit-code", required=True)
    parser.add_argument("--validation-exit-code", required=True)
    parser.add_argument("--environment-exit-code", required=True)
    parser.add_argument("--state-exit-code", required=True)
    parser.add_argument("--regressions-exit-code", required=True)
    parser.add_argument("--matrix-exit-code", required=True)
    parser.add_argument("--workflow-exit-code", required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tests = _test_result(_text(args.tests_log), _code(args.test_exit_code))
    validation = _validation_result(_text(args.validation_log), _code(args.validation_exit_code))
    environment = _code(args.environment_exit_code) == 0
    state = _code(args.state_exit_code) == 0
    regressions = _code(args.regressions_exit_code) == 0
    matrix = _code(args.matrix_exit_code) == 0
    workflow = _code(args.workflow_exit_code) == 0
    gates = {
        "unit_tests": {"status": "PASS" if tests["status"] == "passed" else "FAIL", "detail": tests},
        "official_validation": {"status": "PASS" if validation["status"] == "passed" else "FAIL", "detail": validation},
        "environment_tilesets_runtime": {"status": "PASS" if environment else "FAIL", "detail": "run_environment_tilesets_runtime_v0200.py"},
        "state_consistency": {"status": "PASS" if state else "FAIL", "detail": "validate_state_consistency_v0200.py"},
        "frozen_regressions": {"status": "PASS" if regressions else "FAIL", "detail": "v0.19.1/v0.18.2/v0.17.1/v0.16.2"},
        "capability_matrix": {"status": "PASS" if matrix else "FAIL", "detail": "validate_v1_capability_matrix.py"},
        "workflow_validation": {"status": "PASS" if workflow else "FAIL", "detail": "validate_github_workflows_v0124.py"},
    }
    (args.output_dir / "test-results-v0200.json").write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "validation-results-v0200.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "gate-results-v0200.json").write_text(json.dumps({"schema_version": "0.20.0", "gates": gates, "overall_status": "PASS" if all(item["status"] == "PASS" for item in gates.values()) else "FAIL"}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0200_RESULTS_RECORDED", "overall_status": "PASS" if all(item["status"] == "PASS" for item in gates.values()) else "FAIL"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
