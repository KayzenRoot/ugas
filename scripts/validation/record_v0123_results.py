"""Record actual v0.12.3 test/validation totals from foreground command logs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


def _exit_code(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"invalid exit code: {value}") from exc


def _test_result(text: str, exit_code: int) -> dict[str, Any]:
    matches = re.findall(r"Ran\s+(\d+)\s+tests?", text)
    count = int(matches[-1]) if matches else None
    failure_match = re.search(r"FAILED\s*\(([^)]*)\)", text)
    failure_count = None
    if failure_match:
        values = [int(item) for item in re.findall(r"(?:failures|errors)=(\d+)", failure_match.group(1))]
        failure_count = sum(values) if values else None
    parsed = count is not None and ("OK" in text or failure_match is not None)
    status = "passed" if exit_code == 0 and count is not None and "OK" in text else ("failed" if exit_code != 0 and parsed else "parse_failed")
    return {
        "schema_version": "0.12.3",
        "command": "python -m unittest discover -s tests -q",
        "log_path": "ugas-tests.log",
        "exit_code": exit_code,
        "parse_status": "parsed" if parsed else "failed",
        "count": count,
        "passed": count if status == "passed" else None,
        "failed": 0 if status == "passed" else failure_count,
        "status": status,
    }


def _validation_result(text: str, exit_code: int) -> dict[str, Any]:
    matches = re.findall(r"SUMMARY\s+checks=(\d+)\s+passed=(\d+)\s+failed=(\d+)", text)
    checks = passed = failed = None
    if matches:
        checks, passed, failed = (int(item) for item in matches[-1])
    parsed = checks is not None
    status = "passed" if exit_code == 0 and parsed and failed == 0 and passed == checks else ("failed" if exit_code != 0 and parsed else "parse_failed")
    return {
        "schema_version": "0.12.3",
        "command": "python scripts/validation/run_validation.py",
        "log_path": "ugas-validation.log",
        "exit_code": exit_code,
        "parse_status": "parsed" if parsed else "failed",
        "checks": checks,
        "passed": passed,
        "failed": failed,
        "status": status,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-log", required=True)
    parser.add_argument("--validation-log", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--test-exit-code")
    parser.add_argument("--validation-exit-code")
    parser.add_argument("--state-exit-code", default="0")
    parser.add_argument("--matrix-exit-code", default="0")
    parser.add_argument("--visual-exit-code", default="0")
    parser.add_argument("--manifest-exit-code", default="0")
    parser.add_argument("--security-exit-code", default="0")
    args = parser.parse_args()
    tests_text = Path(args.test_log).read_text(encoding="utf-8", errors="replace")
    validation_text = Path(args.validation_log).read_text(encoding="utf-8", errors="replace")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    test_result = _test_result(tests_text, _exit_code(args.test_exit_code))
    validation_result = _validation_result(validation_text, _exit_code(args.validation_exit_code))
    (output / "test-results-v0123.json").write_text(json.dumps(test_result, indent=2) + "\n", encoding="utf-8")
    (output / "validation-results-v0123.json").write_text(json.dumps(validation_result, indent=2) + "\n", encoding="utf-8")
    gate_inputs = {
        "unit_tests": (test_result, _exit_code(args.test_exit_code)),
        "official_validation": (validation_result, _exit_code(args.validation_exit_code)),
        "state_consistency": (None, _exit_code(args.state_exit_code)),
        "capability_matrix": (None, _exit_code(args.matrix_exit_code)),
        "visual_transport": (None, _exit_code(args.visual_exit_code)),
        "manifest_validation": (None, _exit_code(args.manifest_exit_code)),
        "security": (None, _exit_code(args.security_exit_code)),
    }
    gates = []
    for gate_id, (result, code) in gate_inputs.items():
        if result is not None:
            passed_gate = result.get("status") == "passed" and code == 0
            detail = str(result.get("status"))
        else:
            passed_gate = code == 0
            detail = "exit_code=0" if passed_gate else f"exit_code={code}"
        gates.append({"id": gate_id, "status": "PASS" if passed_gate else "FAIL", "exit_code": code, "detail": detail})
    gate_result = {"schema_version": "0.12.3", "overall_status": "PASS" if all(item["status"] == "PASS" for item in gates) else "FAIL", "gates": gates}
    (output / "gate-results-v0123.json").write_text(json.dumps(gate_result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0123_RESULTS_RECORDED", "tests": test_result, "validation": validation_result, "gates": gate_result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
