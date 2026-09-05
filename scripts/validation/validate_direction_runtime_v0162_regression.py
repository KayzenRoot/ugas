"""Read-only regression check for the frozen v0.16.2 direction foundation."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/multi-direction-runtime-v0162"


def load(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def main() -> int:
    validation = load("validation-evidence-v0162.json")
    negative = load("negative-controls-v0162.json")
    cache_order = load("cache-order-negative-controls-v0162.json")
    fixture = load("synthetic-fixture-manifest-v0162.json")
    controls = negative.get("controls", {})
    order_controls = cache_order.get("controls", {})
    failures = []
    if validation.get("status") != "MULTI_DIRECTION_ANIMATION_RUNTIME_CACHE_AND_STATE_INTEGRITY_TECHNICALLY_QUALIFIED" or validation.get("failed") != 0:
        failures.append("validation")
    if negative.get("status") != "DIR_NC_01_TO_12_PASSED" or len(controls) != 12 or not all(item.get("rejected") is True and item.get("status") == "REJECTED" for item in controls.values()):
        failures.append("negative-controls")
    if cache_order.get("status") != "CACHE_NC_01_TO_05_PASSED" or len(order_controls) != 5 or not all(item.get("rejected") is True for item in order_controls.values()):
        failures.append("cache-order-controls")
    if fixture.get("schema_version") != "0.16.2" or fixture.get("direction_count") != 8 or fixture.get("production_registry") is not False:
        failures.append("fixture")
    result = {"status": "V0162_REGRESSION_PASSED" if not failures else "V0162_REGRESSION_FAILED", "failures": failures, "read_only": True}
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
