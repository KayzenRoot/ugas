"""Record bounded v0.24.7 test and official-validation results from CI logs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


CANONICAL_SUMMARY_RE = re.compile(r"^SUMMARY checks=(\d+) passed=(\d+) failed=(\d+)$")


def classify_summary_prefixed_lines(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_index, line in enumerate((text or "").splitlines()):
        if not line.startswith("SUMMARY"):
            continue
        match = CANONICAL_SUMMARY_RE.fullmatch(line)
        records.append({
            "line_index": line_index,
            "text": line,
            "canonical": match is not None,
            "checks": int(match.group(1)) if match else None,
            "passed": int(match.group(2)) if match else None,
            "failed": int(match.group(3)) if match else None,
        })
    return records


def select_final_validation_summary(text: str) -> dict[str, Any]:
    prefixed = classify_summary_prefixed_lines(text)
    canonical = [item for item in prefixed if item["canonical"]]
    base = {
        "summary_prefixed_count": len(prefixed),
        "canonical_summary_count": len(canonical),
        "summary_count": len(prefixed),
        "selected_summary_index": None,
        "selected_terminal_line": None,
        "checks": None,
        "passed": None,
        "failed": None,
        "summaries": [{"checks": item["checks"], "passed": item["passed"], "failed": item["failed"], "canonical": item["canonical"], "line_index": item["line_index"]} for item in prefixed],
    }
    if not prefixed:
        return {**base, "status": "FAIL", "reason": "NO_FINAL_SUMMARY"}
    selected_index = len(prefixed) - 1
    selected = prefixed[selected_index]
    base["selected_summary_index"] = selected_index
    base["selected_terminal_line"] = selected["line_index"]
    if not selected["canonical"]:
        return {
            **base,
            "status": "FAIL",
            "reason": "MALFORMED_TERMINAL_SUMMARY",
        }
    status = "PASS" if selected["checks"] == selected["passed"] and selected["failed"] == 0 else "FAIL"
    return {
        **base,
        "status": status,
        "checks": selected["checks"],
        "passed": selected["passed"],
        "failed": selected["failed"],
        "reason": None if status == "PASS" else "FINAL_SUMMARY_NOT_CLEAN",
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
        "summary_prefixed_count": summary.get("summary_prefixed_count"),
        "canonical_summary_count": summary.get("canonical_summary_count"),
        "selected_summary_index": summary.get("selected_summary_index"),
        "selected_terminal_line": summary.get("selected_terminal_line"),
        "reason": summary.get("reason"),
    }
    if args.validation_exit != 0:
        validation_record["status"] = "FAIL"
        validation_record["reason"] = validation_record.get("reason") or "VALIDATION_EXIT_NONZERO"
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "test-results-v0247.json").write_text(json.dumps(test_record, indent=2) + "\n", encoding="utf-8")
    (output / "validation-results-v0247.json").write_text(json.dumps(validation_record, indent=2) + "\n", encoding="utf-8")
    statuses = [args.tests_exit, args.validation_exit, args.state_exit, args.matrix_exit, args.orchestration_exit, args.workflow_exit, args.schema_exit]
    passed = all(code == 0 for code in statuses) and test_record["status"] == "PASS" and validation_record["status"] == "PASS"
    print(json.dumps({"status": "PASS" if passed else "FAIL", "tests": test_record, "validation": validation_record, "exit_codes": statuses}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
