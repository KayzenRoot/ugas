"""Validate the active v0.24.6 state and runtime evidence against their schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document


def main() -> int:
    checks: list[dict[str, str]] = []
    failures: list[str] = []
    pairs = (
        ("current-state", ROOT / "docs/evidence/current-state.json", ROOT / "schemas/current-state-v0246.json"),
        ("orchestration-evidence", ROOT / "docs/evidence/orchestration-runtime-v0246/execution-evidence-v0246.json", ROOT / "schemas/orchestration-runtime-v0246.json"),
    )
    for name, value_path, schema_path in pairs:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            value = json.loads(value_path.read_text(encoding="utf-8"))
            validate_schema_document(schema)
            validate_instance(value, schema)
            checks.append({"name": name, "status": "PASS"})
        except Exception as exc:  # schema validator errors are recorded and fail closed
            checks.append({"name": name, "status": "FAIL", "error": type(exc).__name__})
            failures.append(f"{name}:{type(exc).__name__}")
    result = {"schema_version": "0.24.6", "status": "PASS" if not failures else "FAIL", "checks": checks, "failures": failures}
    output = ROOT / "docs/evidence/orchestration-runtime-v0246/schema-validation-v0246.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
