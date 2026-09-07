"""Record bounded test/validation results for the v0.22.0 review artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _int(value: str) -> int:
    try: return int(value)
    except (TypeError, ValueError): return 99


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--tests-log", type=Path, required=True); parser.add_argument("--validation-log", type=Path, required=True); parser.add_argument("--tests-exit", required=True); parser.add_argument("--validation-exit", required=True); parser.add_argument("--ui-exit", required=True); parser.add_argument("--state-exit", required=True); parser.add_argument("--matrix-exit", required=True); parser.add_argument("--workflow-exit", required=True); args = parser.parse_args()
    tests_log = _read(args.tests_log); validation_log = _read(args.validation_log)
    matches = re.findall(r"Ran (\d+) tests", tests_log); test_count = int(matches[-1]) if matches else 0
    checks = re.findall(r"SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)", validation_log)
    validation = {"schema_version": "0.22.0", "status": "failed", "checks": 0, "passed": 0, "failed": 1, "exit_code": _int(args.validation_exit)}
    if checks:
        total, passed, failed = map(int, checks[-1]); validation.update({"status": "passed" if validation["exit_code"] == 0 and failed == 0 else "failed", "checks": total, "passed": passed, "failed": failed})
    tests = {"schema_version": "0.22.0", "status": "passed" if _int(args.tests_exit) == 0 and test_count > 0 else "failed", "count": test_count, "passed": test_count if _int(args.tests_exit) == 0 else 0, "failed": 0 if _int(args.tests_exit) == 0 else 1, "exit_code": _int(args.tests_exit)}
    gates = {"unit_tests": tests["status"] == "passed", "official_validation": validation["status"] == "passed", "ui_runtime": _int(args.ui_exit) == 0, "state_consistency": _int(args.state_exit) == 0, "capability_matrix": _int(args.matrix_exit) == 0, "workflow_validation": _int(args.workflow_exit) == 0}
    overall = all(gates.values())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "test-results-v0220.json").write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "validation-results-v0220.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "gate-results-v0220.json").write_text(json.dumps({"schema_version": "0.22.0", "gates": {key: {"status": "PASS" if value else "FAIL"} for key, value in gates.items()}, "overall_status": "PASS" if overall else "FAIL"}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0220_RESULTS_RECORDED", "overall_status": "PASS" if overall else "FAIL", "test_count": test_count, "validation_checks": validation["checks"]}))
    return 0 if overall else 1


if __name__ == "__main__": raise SystemExit(main())
