"""Record truthful v0.15.1 test, validation and review-gate results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from record_v0123_results import _exit_code, _test_result as _old_test_result, _validation_result as _old_validation_result


def _test_result(text: str, exit_code: int) -> dict[str, Any]:
    value = _old_test_result(text, exit_code)
    value["schema_version"] = "0.15.1"
    return value


def _validation_result(text: str, exit_code: int) -> dict[str, Any]:
    value = _old_validation_result(text, exit_code)
    value["schema_version"] = "0.15.1"
    return value


def _file_result(path: str | None, raw_code: str | int | None) -> dict[str, Any]:
    code = _exit_code(raw_code)
    return {
        "status": "passed" if code == 0 else "failed",
        "exit_code": code,
        "log_path": path or "not-recorded",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-log", required=True)
    parser.add_argument("--validation-log", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--runtime-log")
    parser.add_argument("--runtime-exit-code", default="99")
    parser.add_argument("--recovery-exit-code", default="99")
    for name, default in (
        ("test-exit-code", None),
        ("validation-exit-code", None),
        ("state-exit-code", "99"),
        ("matrix-exit-code", "99"),
        ("visual-exit-code", "99"),
        ("workflow-exit-code", "99"),
        ("manifest-exit-code", "99"),
        ("security-exit-code", "99"),
    ):
        parser.add_argument(f"--{name}", default=default)
    args = parser.parse_args()

    tests = _test_result(
        Path(args.test_log).read_text(encoding="utf-8", errors="replace"),
        _exit_code(args.test_exit_code),
    )
    validation = _validation_result(
        Path(args.validation_log).read_text(encoding="utf-8", errors="replace"),
        _exit_code(args.validation_exit_code),
    )
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "test-results-v0151.json").write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
    (output / "validation-results-v0151.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")

    runtime = _file_result(args.runtime_log, args.runtime_exit_code)
    recovery = _file_result(None, args.recovery_exit_code)
    (output / "runtime-results-v0151.json").write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
    (output / "recovery-results-v0151.json").write_text(json.dumps(recovery, indent=2) + "\n", encoding="utf-8")

    inputs = [
        ("unit_tests", tests, args.test_exit_code),
        ("official_validation", validation, args.validation_exit_code),
        ("state_consistency", None, args.state_exit_code),
        ("capability_matrix", None, args.matrix_exit_code),
        ("death_runtime", None, args.runtime_exit_code),
        ("recovery_integrity", None, args.recovery_exit_code),
        ("visual_transport", None, args.visual_exit_code),
        ("workflow_validation", None, args.workflow_exit_code),
        ("manifest_validation", None, args.manifest_exit_code),
        ("security", None, args.security_exit_code),
    ]
    gates = []
    for gate_id, result, raw_code in inputs:
        code = _exit_code(raw_code)
        passed = (result.get("status") == "passed" and code == 0) if result is not None else code == 0
        gates.append(
            {
                "id": gate_id,
                "status": "PASS" if passed else "FAIL",
                "exit_code": code,
                "detail": str(result.get("status")) if result is not None else ("exit_code=0" if passed else f"exit_code={code}"),
            }
        )
    gate_result = {
        "schema_version": "0.15.1",
        "overall_status": "PASS" if all(item["status"] == "PASS" for item in gates) else "FAIL",
        "gates": gates,
    }
    (output / "gate-results-v0151.json").write_text(json.dumps(gate_result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0150_RESULTS_RECORDED", "tests": tests, "validation": validation, "gates": gate_result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
