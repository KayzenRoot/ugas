"""Record bounded v0.23.4 test and official-validation totals."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--tests-log", type=Path, required=True)
    p.add_argument("--validation-log", type=Path, required=True)
    for name in ("tests-exit", "validation-exit", "vfx-exit", "state-exit", "matrix-exit", "workflow-exit"):
        p.add_argument(f"--{name}", required=True)
    a = p.parse_args()
    test_matches = re.findall(r"Ran (\d+) tests", _read(a.tests_log))
    count = int(test_matches[-1]) if test_matches else 0
    checks = re.findall(r"SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)", _read(a.validation_log))
    validation = {"schema_version": "0.23.4", "status": "failed", "checks": 0, "passed": 0, "failed": 1, "exit_code": int(a.validation_exit)}
    if checks:
        total, passed, failed = map(int, checks[-1])
        validation.update({"status": "passed" if a.validation_exit == "0" and failed == 0 else "failed", "checks": total, "passed": passed, "failed": failed})
    tests = {"schema_version": "0.23.4", "status": "passed" if a.tests_exit == "0" and count > 0 else "failed", "count": count, "passed": count if a.tests_exit == "0" else 0, "failed": 0 if a.tests_exit == "0" else 1, "exit_code": int(a.tests_exit)}
    gates = {name: getattr(a, name.replace("-", "_")) == "0" for name in ("tests-exit", "validation-exit", "vfx-exit", "state-exit", "matrix-exit", "workflow-exit")}
    overall = all(gates.values()) and tests["status"] == "passed" and validation["status"] == "passed"
    a.output_dir.mkdir(parents=True, exist_ok=True)
    (a.output_dir / "test-results-v0234.json").write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
    (a.output_dir / "validation-results-v0234.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    (a.output_dir / "gate-results-v0234.json").write_text(json.dumps({"schema_version": "0.23.4", "gates": {k: {"status": "PASS" if v else "FAIL"} for k, v in gates.items()}, "overall_status": "PASS" if overall else "FAIL"}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "V0234_RESULTS_RECORDED", "overall_status": "PASS" if overall else "FAIL", "test_count": count, "validation_checks": validation["checks"]}))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())

