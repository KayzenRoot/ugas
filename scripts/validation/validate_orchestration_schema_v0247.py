"""Validate the frozen v0.24.7 state and runtime evidence against their schemas."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document

FROZEN_ROOT = ROOT / "docs/evidence/orchestration-runtime-v0247"
FROZEN_AUTHORITY_COMMIT = "6c6d53dab5a95226bf9578a6099d755d51327d8e"


def _normalized_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def validate_frozen_snapshots() -> list[str]:
    """Prove the frozen v0.24.7 state snapshot still equals its authority-commit source when Git is present.

    In an isolated no-git snapshot the historical Git authority is intentionally absent; the
    committed snapshot bytes remain the frozen authority and are re-bound by the acceptance run.
    """

    failures: list[str] = []
    if not (ROOT / ".git").exists():
        return failures
    result = subprocess.run(["git", "show", f"{FROZEN_AUTHORITY_COMMIT}:docs/evidence/current-state.json"], cwd=ROOT, capture_output=True, check=False)
    if result.returncode != 0:
        failures.append("current-state:git-source-unavailable")
    elif _normalized_bytes(result.stdout) != _normalized_bytes((FROZEN_ROOT / "state-snapshot-v0247.json").read_bytes()):
        failures.append("current-state:snapshot-mutated")
    return failures


def main() -> int:
    checks: list[dict[str, str]] = []
    failures: list[str] = []
    pairs = (
        ("current-state", FROZEN_ROOT / "state-snapshot-v0247.json", ROOT / "schemas/current-state-v0247.json"),
        ("orchestration-evidence", FROZEN_ROOT / "execution-evidence-v0247.json", ROOT / "schemas/orchestration-runtime-v0247.json"),
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
    failures.extend(validate_frozen_snapshots())
    result = {"schema_version": "0.24.7", "status": "PASS" if not failures else "FAIL", "checks": checks, "failures": failures}
    output = ROOT / "docs/evidence/orchestration-runtime-v0247/schema-validation-v0247.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
