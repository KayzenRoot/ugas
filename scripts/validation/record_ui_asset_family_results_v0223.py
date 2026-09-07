"""Record bounded v0.22.3 test and official-validation totals."""

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
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--tests-log", type=Path, required=True); parser.add_argument("--validation-log", type=Path, required=True); parser.add_argument("--tests-exit", required=True); parser.add_argument("--validation-exit", required=True); parser.add_argument("--ui-exit", required=True); parser.add_argument("--state-exit", required=True); parser.add_argument("--matrix-exit", required=True); parser.add_argument("--workflow-exit", required=True); parser.add_argument("--governance-exit", required=True); args = parser.parse_args()
    tests_text = _read(args.tests_log); validation_text = _read(args.validation_log); matches = re.findall(r"Ran (\d+) tests", tests_text); test_count = int(matches[-1]) if matches else 0; checks = re.findall(r"SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)", validation_text)
    validation = {"schema_version": "0.22.3", "status": "failed", "checks": 0, "passed": 0, "failed": 1, "exit_code": _int(args.validation_exit)}
    if checks:
        total, passed, failed = map(int, checks[-1]); validation.update({"status": "passed" if validation["exit_code"] == 0 and failed == 0 else "failed", "checks": total, "passed": passed, "failed": failed})
    tests = {"schema_version": "0.22.3", "status": "passed" if _int(args.tests_exit) == 0 and test_count > 0 else "failed", "count": test_count, "passed": test_count if _int(args.tests_exit) == 0 else 0, "failed": 0 if _int(args.tests_exit) == 0 else 1, "exit_code": _int(args.tests_exit)}
    gates = {key: _int(value) == 0 for key, value in (("unit_tests", args.tests_exit), ("official_validation", args.validation_exit), ("ui_runtime", args.ui_exit), ("state_consistency", args.state_exit), ("capability_matrix", args.matrix_exit), ("workflow_validation", args.workflow_exit), ("governance", args.governance_exit))}; overall = all(gates.values()) and tests["status"] == "passed" and validation["status"] == "passed"
    args.output_dir.mkdir(parents=True, exist_ok=True); (args.output_dir / "test-results-v0223.json").write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8"); (args.output_dir / "validation-results-v0223.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8"); (args.output_dir / "gate-results-v0223.json").write_text(json.dumps({"schema_version": "0.22.3", "gates": {key: {"status": "PASS" if value else "FAIL"} for key, value in gates.items()}, "overall_status": "PASS" if overall else "FAIL"}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0223_RESULTS_RECORDED", "overall_status": "PASS" if overall else "FAIL", "test_count": test_count, "validation_checks": validation["checks"]})); return 0 if overall else 1


if __name__ == "__main__": raise SystemExit(main())
