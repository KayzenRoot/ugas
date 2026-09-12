"""Validate v0.25.2 evidence, historical immutability and real negative controls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document  # noqa: E402
from ugas.state_consistency_v0252 import (  # noqa: E402
    PROMOTION_BINDING,
    PROMOTION_IMMUTABILITY,
    PROMOTION_NEGATIVE_CONTROLS,
    PROMOTION_UADS,
    VERSION,
    historical_immutability_failures,
    negative_control_failures,
    validate_post_merge_binding,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    checks: list[dict[str, object]] = []
    failures: list[str] = []
    try:
        schema = json.loads((ROOT / "schemas/current-state-v0252.json").read_text(encoding="utf-8"))
        state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
        validate_schema_document(schema)
        validate_instance(state, schema)
        checks.append({"name": "current-state-v0252-schema", "status": "PASS"})
    except Exception as exc:  # fail closed on schema/instance errors
        checks.append({"name": "current-state-v0252-schema", "status": "FAIL", "error": type(exc).__name__})
        failures.append(f"current-state-v0252-schema:{type(exc).__name__}")
    try:
        binding = json.loads((ROOT / PROMOTION_BINDING).read_text(encoding="utf-8"))
        problems = validate_post_merge_binding(binding)
        checks.append({"name": "post-merge-binding-v0252", "status": "PASS" if not problems else "FAIL", "failures": problems})
        failures.extend(f"post-merge-binding-v0252:{item}" for item in problems)
    except Exception as exc:
        checks.append({"name": "post-merge-binding-v0252", "status": "FAIL", "error": type(exc).__name__})
        failures.append(f"post-merge-binding-v0252:{type(exc).__name__}")
    for relative, validator, name in (
        (PROMOTION_IMMUTABILITY, lambda value: historical_immutability_failures(value, ROOT), "historical-v0251-immutability-v0252"),
        (PROMOTION_NEGATIVE_CONTROLS, negative_control_failures, "negative-controls-v0252"),
    ):
        try:
            value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            problems = validator(value)
            checks.append({"name": name, "status": "PASS" if not problems else "FAIL", "failures": problems})
            failures.extend(f"{name}:{item}" for item in problems)
        except Exception as exc:
            checks.append({"name": name, "status": "FAIL", "error": type(exc).__name__})
            failures.append(f"{name}:{type(exc).__name__}")
    try:
        handoff = json.loads((ROOT / PROMOTION_UADS).read_text(encoding="utf-8"))
        valid = handoff.get("status") == "PASS" and handoff.get("version") == VERSION and handoff.get("handoff", {}).get("execution_mode") == "GLOBAL_FIRST" and handoff.get("handoff", {}).get("project_footprint") == "ZERO" and handoff.get("handoff", {}).get("repo_local_material") == "ABSENT" and ".uads" not in json.dumps(handoff).casefold()
        checks.append({"name": "uads-handoff-v0252", "status": "PASS" if valid else "FAIL"})
        if not valid:
            failures.append("uads-handoff-v0252:invalid")
    except Exception as exc:
        checks.append({"name": "uads-handoff-v0252", "status": "FAIL", "error": type(exc).__name__})
        failures.append(f"uads-handoff-v0252:{type(exc).__name__}")
    result = {"schema_version": VERSION, "version": VERSION, "status": "PASS" if not failures else "FAIL", "checks": checks, "failures": failures}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
