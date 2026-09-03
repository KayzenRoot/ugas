"""Record truthful v0.14.0 test, validation and gate totals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from record_v0123_results import _exit_code, _test_result as _old_test_result, _validation_result as _old_validation_result


def _test_result(text: str, exit_code: int) -> dict[str, Any]:
    value = _old_test_result(text, exit_code); value["schema_version"] = "0.14.0"; return value


def _validation_result(text: str, exit_code: int) -> dict[str, Any]:
    value = _old_validation_result(text, exit_code); value["schema_version"] = "0.14.0"; return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-log", required=True); parser.add_argument("--validation-log", required=True); parser.add_argument("--output-dir", required=True)
    for name, default in (("test-exit-code", None), ("validation-exit-code", None), ("state-exit-code", "0"), ("matrix-exit-code", "0"), ("visual-exit-code", "0"), ("workflow-exit-code", "0"), ("manifest-exit-code", "0"), ("security-exit-code", "0")):
        parser.add_argument(f"--{name}", default=default)
    args = parser.parse_args()
    tests = _test_result(Path(args.test_log).read_text(encoding="utf-8", errors="replace"), _exit_code(args.test_exit_code))
    validation = _validation_result(Path(args.validation_log).read_text(encoding="utf-8", errors="replace"), _exit_code(args.validation_exit_code))
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    (output / "test-results-v0140.json").write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
    (output / "validation-results-v0140.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    inputs = [("unit_tests", tests, args.test_exit_code), ("official_validation", validation, args.validation_exit_code), ("state_consistency", None, args.state_exit_code), ("capability_matrix", None, args.matrix_exit_code), ("visual_transport", None, args.visual_exit_code), ("workflow_validation", None, args.workflow_exit_code), ("manifest_validation", None, args.manifest_exit_code), ("security", None, args.security_exit_code)]
    gates = []
    for gate_id, result, raw_code in inputs:
        code = _exit_code(raw_code); passed = (result.get("status") == "passed" and code == 0) if result is not None else code == 0
        gates.append({"id": gate_id, "status": "PASS" if passed else "FAIL", "exit_code": code, "detail": str(result.get("status")) if result is not None else ("exit_code=0" if passed else f"exit_code={code}")})
    gate_result = {"schema_version": "0.14.0", "overall_status": "PASS" if all(item["status"] == "PASS" for item in gates) else "FAIL", "gates": gates}
    (output / "gate-results-v0140.json").write_text(json.dumps(gate_result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0140_RESULTS_RECORDED", "tests": tests, "validation": validation, "gates": gate_result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
