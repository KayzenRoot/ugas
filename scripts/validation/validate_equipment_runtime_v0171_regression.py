"""Read-only regression check for the frozen v0.17.1 equipment foundation."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/equipment-outfits-runtime-v0171"


def load(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def main() -> int:
    execution = load("execution-evidence-v0171.json")
    fixture = load("synthetic-fixture-manifest-v0171.json")
    production = load("equipment-registry-v0171.json")
    negative = load("negative-controls-v0171.json")
    controls = negative.get("controls", {})
    strict = all(
        item.get("rejected") is True
        and item.get("passed") is True
        and item.get("status") == "REJECTED"
        and item.get("observed", {}).get("result") == "REJECTED"
        and item["observed"].get("error_code") == item.get("expected_error_code")
        and item["observed"].get("rejection_class") == item.get("expected_rejection_class")
        for item in controls.values()
    )
    failures = []
    if execution.get("status") != "EQUIPMENT_OUTFITS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED" or execution.get("failed") != 0:
        failures.append("execution")
    if fixture.get("schema_version") != "0.17.1" or len(fixture.get("assets", [])) != 8 or fixture.get("production_registry") is not False:
        failures.append("fixture")
    if production.get("production_registry") is not True or production.get("assets") != []:
        failures.append("production-registry")
    if negative.get("status") != "EQ_NC_01_TO_15_PASSED" or len(controls) != 15 or not strict:
        failures.append("negative-controls")
    result = {"status": "V0171_REGRESSION_PASSED" if not failures else "V0171_REGRESSION_FAILED", "failures": failures, "read_only": True}
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
