"""Record truthful v0.18.1 unit, validation and gate totals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from record_v0123_results import _exit_code, _test_result as parse_tests, _validation_result as parse_validation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-log", required=True)
    parser.add_argument("--validation-log", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--test-exit-code", default="99")
    parser.add_argument("--validation-exit-code", default="99")
    for name in ("state", "creatures", "direction", "matrix", "front-compatibility", "workflow", "manifest", "security"):
        parser.add_argument(f"--{name}-exit-code", default="99")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    tests = parse_tests(Path(args.test_log).read_text(encoding="utf-8", errors="replace"), _exit_code(args.test_exit_code))
    validation = parse_validation(Path(args.validation_log).read_text(encoding="utf-8", errors="replace"), _exit_code(args.validation_exit_code))
    tests["schema_version"] = validation["schema_version"] = "0.18.1"
    (output / "test-results-v0181.json").write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
    (output / "validation-results-v0181.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    inputs = {
        "unit_tests": (tests, args.test_exit_code), "official_validation": (validation, args.validation_exit_code),
        "state_consistency": (None, args.state_exit_code), "creatures_runtime": (None, args.creatures_exit_code),
        "direction_runtime": (None, args.direction_exit_code), "capability_matrix": (None, args.matrix_exit_code),
        "front_compatibility": (None, args.front_compatibility_exit_code), "workflow_validation": (None, args.workflow_exit_code),
        "manifest_validation": (None, args.manifest_exit_code), "security": (None, args.security_exit_code),
    }
    gates = []
    for gate_id, (result, raw_code) in inputs.items():
        code = _exit_code(raw_code)
        passed = (result.get("status") == "passed" and code == 0) if result else code == 0
        gates.append({"id": gate_id, "status": "PASS" if passed else "FAIL", "exit_code": code, "detail": str(result.get("status")) if result else ("exit_code=0" if passed else f"exit_code={code}")})
    value = {"schema_version": "0.18.1", "overall_status": "PASS" if all(item["status"] == "PASS" for item in gates) else "FAIL", "gates": gates}
    (output / "gate-results-v0181.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0181_RESULTS_RECORDED", "tests": tests, "validation": validation, "gates": value}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
