"""Validate the active UGAS V1 capability order without executing a capability."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document


def main() -> int:
    matrix_path = ROOT / "docs/ugas-v1-capability-matrix.json"
    schema_path = ROOT / "schemas/ugas-v1-capability-matrix-v1.json"
    value = json.loads(matrix_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validate_schema_document(schema)
    validate_instance(value, schema)
    failures: list[str] = []
    capabilities = value["capabilities"]
    ids = [item["id"] for item in capabilities]
    if len(ids) != len(set(ids)):
        failures.append("duplicate-capability-id")
    if ids.index("github_native_review_infrastructure") >= ids.index("run_front_v1"):
        failures.append("run-front-must-follow-review-infrastructure")
    run_front = next(item for item in capabilities if item["id"] == "run_front_v1")
    hit_reaction = next(item for item in capabilities if item["id"] == "hit_reaction_front")
    death = next(item for item in capabilities if item["id"] == "death_animation_front")
    if run_front["status"] != "APPROVED_PILOT":
        failures.append("run-front-must-be-approved-pilot")
    if hit_reaction["status"] != "APPROVED_PILOT":
        failures.append("hit-reaction-front-must-be-approved-pilot")
    direction = next(item for item in capabilities if item["id"] == "multi_direction_animation_runtime")
    equipment = next(item for item in capabilities if item["id"] == "equipment_outfits")
    creatures = next(item for item in capabilities if item["id"] == "creatures_monsters")
    items = next(item for item in capabilities if item["id"] == "items_props")
    if value["version"] != "0.19.1":
        failures.append("active-matrix-version-must-be-v0191")
    if death["status"] != "APPROVED_PILOT" or direction["status"] != "APPROVED_FOUNDATION" or equipment["status"] != "APPROVED_FOUNDATION" or creatures["status"] != "APPROVED_FOUNDATION" or items["status"] != "TECHNICALLY QUALIFIED; EXTERNAL REVIEW REQUIRED" or value["next_candidate"] != "ITEMS_PROPS":
        failures.append("next-candidate-is-not-items-props")
    if value["production_routing"] != "BLOCKED" or value["new_generation"] != 0:
        failures.append("matrix-crosses-production-or-generation-boundary")
    result = {"status": "V1_CAPABILITY_MATRIX_PASSED" if not failures else "V1_CAPABILITY_MATRIX_FAILED", "failures": failures, "version": value["version"], "capability_count": len(capabilities), "ids": ids, "next_candidate": value["next_candidate"], "items_props_status": items["status"], "production_routing": value["production_routing"], "new_generation": value["new_generation"]}
    output = ROOT / "docs/evidence/items-props-runtime-v0191/capability-matrix-validation-v0191.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
