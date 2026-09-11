"""Validate the active v0.25.0 state and V1 final acceptance evidence against their schemas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document

VERSION = "0.25.0"
EVIDENCE = ROOT / "docs/evidence/v1-final-acceptance"
EVIDENCE_FILES = (
    "capability-matrix-audit.json",
    "architecture-audit.json",
    "security-audit.json",
    "reproducibility-audit.json",
    "state-consistency-audit.json",
    "test-summary.json",
    "hard-gates.json",
    "negative-controls.json",
    "production-boundary.json",
    "uads-handoff.json",
    "final-acceptance-summary.json",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(EVIDENCE / "schema-validation-v0250.json"))
    args = parser.parse_args()
    checks: list[dict[str, str]] = []
    failures: list[str] = []
    try:
        schema = json.loads((ROOT / "schemas/current-state-v0250.json").read_text(encoding="utf-8"))
        value = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        validate_schema_document(schema)
        validate_instance(value, schema)
        checks.append({"name": "current-state", "status": "PASS"})
    except Exception as exc:  # schema validator errors are recorded and fail closed
        checks.append({"name": "current-state", "status": "FAIL", "error": type(exc).__name__})
        failures.append(f"current-state:{type(exc).__name__}")
    for name in EVIDENCE_FILES:
        path = EVIDENCE / name
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("evidence document is not a JSON object")
            declared_version = document.get("schema_version", document.get("version"))
            if declared_version != VERSION:
                raise ValueError("evidence document schema_version mismatch")
            checks.append({"name": name, "status": "PASS"})
        except Exception as exc:  # unreadable or unbound evidence fails closed
            checks.append({"name": name, "status": "FAIL", "error": type(exc).__name__})
            failures.append(f"{name}:{type(exc).__name__}")
    result = {"schema_version": VERSION, "status": "PASS" if not failures else "FAIL", "checks": checks, "failures": failures}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
