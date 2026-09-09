"""Record bounded v0.24.1 test and official-validation results from CI logs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--tests-log", required=True)
    parser.add_argument("--validation-log", required=True)
    parser.add_argument("--tests-exit", required=True, type=int)
    parser.add_argument("--validation-exit", required=True, type=int)
    parser.add_argument("--state-exit", required=True, type=int)
    parser.add_argument("--matrix-exit", required=True, type=int)
    parser.add_argument("--orchestration-exit", required=True, type=int)
    parser.add_argument("--workflow-exit", required=True, type=int)
    parser.add_argument("--schema-exit", required=True, type=int)
    args = parser.parse_args()
    tests_text = _read(Path(args.tests_log))
    validation_text = _read(Path(args.validation_log))
    tests_match = list(re.finditer(r"Ran\s+(\d+)\s+tests.*?\n\s*(OK|FAILED)(?:\s*\(skipped=(\d+)\))?", tests_text, re.S))
    tests = tests_match[-1] if tests_match else None
    validation_match = re.search(r"SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)", validation_text)
    test_record = {"status": "PASS" if args.tests_exit == 0 and tests and tests.group(2) == "OK" else "FAIL", "count": int(tests.group(1)) if tests else None, "skipped": int(tests.group(3) or 0) if tests else None, "exit_code": args.tests_exit}
    validation_record = {"status": "PASS" if args.validation_exit == 0 and validation_match and validation_match.group(3) == "0" else "FAIL", "checks": int(validation_match.group(1)) if validation_match else None, "passed": int(validation_match.group(2)) if validation_match else None, "failed": int(validation_match.group(3)) if validation_match else None, "exit_code": args.validation_exit}
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "test-results-v0241.json").write_text(json.dumps(test_record, indent=2) + "\n", encoding="utf-8")
    (output / "validation-results-v0241.json").write_text(json.dumps(validation_record, indent=2) + "\n", encoding="utf-8")
    statuses = [args.tests_exit, args.validation_exit, args.state_exit, args.matrix_exit, args.orchestration_exit, args.workflow_exit, args.schema_exit]
    passed = all(code == 0 for code in statuses) and test_record["status"] == "PASS" and validation_record["status"] == "PASS"
    print(json.dumps({"status": "PASS" if passed else "FAIL", "tests": test_record, "validation": validation_record, "exit_codes": statuses}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
