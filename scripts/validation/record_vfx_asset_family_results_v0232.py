"""Record bounded v0.23.2 test and official-validation totals."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
def _int(value: str) -> int:
    try: return int(value)
    except (TypeError, ValueError): return 99
def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--output-dir", type=Path, required=True); p.add_argument("--tests-log", type=Path, required=True); p.add_argument("--validation-log", type=Path, required=True); p.add_argument("--tests-exit", required=True); p.add_argument("--validation-exit", required=True); p.add_argument("--vfx-exit", required=True); p.add_argument("--state-exit", required=True); p.add_argument("--matrix-exit", required=True); p.add_argument("--workflow-exit", required=True); a = p.parse_args()
    test_matches = re.findall(r"Ran (\d+) tests", _read(a.tests_log)); count = int(test_matches[-1]) if test_matches else 0
    checks = re.findall(r"SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)", _read(a.validation_log)); validation = {"schema_version":"0.23.2", "status":"failed", "checks":0, "passed":0, "failed":1, "exit_code":_int(a.validation_exit)}
    if checks:
        total, passed, failed = map(int, checks[-1]); validation.update({"status":"passed" if validation["exit_code"] == 0 and failed == 0 else "failed", "checks":total, "passed":passed, "failed":failed})
    tests = {"schema_version":"0.23.2", "status":"passed" if _int(a.tests_exit) == 0 and count > 0 else "failed", "count":count, "passed":count if _int(a.tests_exit) == 0 else 0, "failed":0 if _int(a.tests_exit) == 0 else 1, "exit_code":_int(a.tests_exit)}
    gates = {k:_int(v) == 0 for k,v in (("unit_tests",a.tests_exit),("official_validation",a.validation_exit),("vfx_runtime",a.vfx_exit),("state_consistency",a.state_exit),("capability_matrix",a.matrix_exit),("workflow_validation",a.workflow_exit))}; overall = all(gates.values()) and tests["status"] == "passed" and validation["status"] == "passed"
    a.output_dir.mkdir(parents=True, exist_ok=True); (a.output_dir/"test-results-v0232.json").write_text(json.dumps(tests, indent=2)+"\n"); (a.output_dir/"validation-results-v0232.json").write_text(json.dumps(validation, indent=2)+"\n"); (a.output_dir/"gate-results-v0232.json").write_text(json.dumps({"schema_version":"0.23.2","gates":{k:{"status":"PASS" if v else "FAIL"} for k,v in gates.items()},"overall_status":"PASS" if overall else "FAIL"}, indent=2)+"\n"); print(json.dumps({"status":"V0232_RESULTS_RECORDED","overall_status":"PASS" if overall else "FAIL","test_count":count,"validation_checks":validation["checks"]})); return 0 if overall else 1
if __name__ == "__main__": raise SystemExit(main())
