"""Record bounded v0.24.6 test and official-validation results from CI logs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SUMMARY_RE = re.compile(r"SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)")


def parse_official_validation_summaries(text: str) -> list[dict[str, int]]:
    records = []
    for match in SUMMARY_RE.finditer(text or ""):
        records.append({
            "checks": int(match.group(1)),
            "passed": int(match.group(2)),
            "failed": int(match.group(3)),
            "start": match.start(),
            "end": match.end(),
            "text": match.group(0),
        })
    return records


def select_final_validation_summary(text: str) -> dict[str, Any]:
    records = parse_official_validation_summaries(text)
    if not records:
        return {
            "status": "FAIL",
            "checks": None,
            "passed": None,
            "failed": None,
            "summary_count": 0,
            "selected_summary_index": None,
            "reason": "NO_FINAL_SUMMARY",
        }
    selected_index = len(records) - 1
    selected = records[selected_index]
    malformed = selected["checks"] < 0 or selected["passed"] < 0 or selected["failed"] < 0
    if malformed:
        return {
            "status": "FAIL",
            "checks": selected["checks"],
            "passed": selected["passed"],
            "failed": selected["failed"],
            "summary_count": len(records),
            "selected_summary_index": selected_index,
            "reason": "MALFORMED_FINAL_SUMMARY",
            "summaries": [{"checks": item["checks"], "passed": item["passed"], "failed": item["failed"]} for item in records],
        }
    status = "PASS" if selected["checks"] == selected["passed"] and selected["failed"] == 0 else "FAIL"
    return {
        "status": status,
        "checks": selected["checks"],
        "passed": selected["passed"],
        "failed": selected["failed"],
        "summary_count": len(records),
        "selected_summary_index": selected_index,
        "reason": None if status == "PASS" else "FINAL_SUMMARY_NOT_CLEAN",
        "summaries": [{"checks": item["checks"], "passed": item["passed"], "failed": item["failed"]} for item in records],
    }


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
    summary = select_final_validation_summary(validation_text)
    test_record = {"status": "PASS" if args.tests_exit == 0 and tests and tests.group(2) == "OK" else "FAIL", "count": int(tests.group(1)) if tests else None, "skipped": int(tests.group(3) or 0) if tests else None, "exit_code": args.tests_exit}
    validation_record = {
        "status": "PASS" if args.validation_exit == 0 and summary.get("status") == "PASS" else "FAIL",
        "checks": summary.get("checks"),
        "passed": summary.get("passed"),
        "failed": summary.get("failed"),
        "exit_code": args.validation_exit,
        "summary_count": summary.get("summary_count"),
        "selected_summary_index": summary.get("selected_summary_index"),
        "reason": summary.get("reason"),
    }
    if args.validation_exit != 0:
        validation_record["status"] = "FAIL"
        validation_record["reason"] = validation_record.get("reason") or "VALIDATION_EXIT_NONZERO"
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "test-results-v0246.json").write_text(json.dumps(test_record, indent=2) + "\n", encoding="utf-8")
    (output / "validation-results-v0246.json").write_text(json.dumps(validation_record, indent=2) + "\n", encoding="utf-8")
    statuses = [args.tests_exit, args.validation_exit, args.state_exit, args.matrix_exit, args.orchestration_exit, args.workflow_exit, args.schema_exit]
    passed = all(code == 0 for code in statuses) and test_record["status"] == "PASS" and validation_record["status"] == "PASS"
    print(json.dumps({"status": "PASS" if passed else "FAIL", "tests": test_record, "validation": validation_record, "exit_codes": statuses}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
