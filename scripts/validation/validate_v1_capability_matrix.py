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
    environment = next(item for item in capabilities if item["id"] == "environment_tilesets")
    maps = next(item for item in capabilities if item["id"] == "maps_minimap_assets")
    if value["version"] not in {"0.20.3", "0.21.0", "0.21.1", "0.21.2", "0.21.3", "0.22.0", "0.22.1", "0.22.2", "0.22.3", "0.23.0", "0.23.1", "0.23.2", "0.23.3", "0.23.4", "0.24.0", "0.24.1", "0.24.2", "0.24.3", "0.24.4", "0.24.5", "0.24.6", "0.24.7"}:
        failures.append("active-matrix-version-must-be-v0203-through-v0247")
    ui = next(item for item in capabilities if item["id"] == "ui_asset_family")
    if death["status"] != "APPROVED_PILOT" or direction["status"] != "APPROVED_FOUNDATION" or equipment["status"] != "APPROVED_FOUNDATION" or creatures["status"] != "APPROVED_FOUNDATION" or items["status"] != "APPROVED_FOUNDATION" or environment["status"] not in {"APPROVED_FOUNDATION", "TECHNICALLY_QUALIFIED_FOUNDATION; QA GOVERNANCE INTEGRITY CORRECTION; EXTERNAL REVIEW REQUIRED"} or value["next_candidate"] not in {"ENVIRONMENT_TILESETS", "MAPS_MINIMAP", "UI_ASSET_FAMILY", "ORCHESTRATION_RUNTIME_HARDENING", "V1_FINAL_ACCEPTANCE"}:
        failures.append("items-props-closure-or-environment-active-state-invalid")
    if value["version"] in {"0.21.0", "0.21.1", "0.21.2"} and (maps["status"] != "TECHNICALLY_QUALIFIED_FOUNDATION" or value["next_candidate"] != "MAPS_MINIMAP"):
        failures.append("maps-minimap-active-state-invalid")
    if value["version"] == "0.21.3" and (maps["status"] != "APPROVED_FOUNDATION" or value["next_candidate"] != "UI_ASSET_FAMILY"):
        failures.append("maps-minimap-approval-transition-invalid")
    if value["version"] == "0.22.0" and (maps["status"] != "APPROVED_FOUNDATION" or ui["status"] != "TECHNICALLY_QUALIFIED_FOUNDATION" or value["next_candidate"] != "UI_ASSET_FAMILY"):
        failures.append("ui-asset-family-active-state-invalid")
    if value["version"] == "0.22.1" and (maps["status"] != "APPROVED_FOUNDATION" or not ui["status"].startswith("TECHNICALLY_QUALIFIED_FOUNDATION; SEMANTIC INTEGRITY CORRECTION") or value["next_candidate"] != "UI_ASSET_FAMILY"):
        failures.append("ui-asset-family-v0221-active-state-invalid")
    if value["version"] == "0.22.2" and (maps["status"] != "APPROVED_FOUNDATION" or not ui["status"].startswith("TECHNICALLY_QUALIFIED_FOUNDATION; F15/F16/F18/F20/F21 CORRECTION") or value["next_candidate"] != "UI_ASSET_FAMILY"):
        failures.append("ui-asset-family-v0222-active-state-invalid")
    if value["version"] == "0.22.3" and (maps["status"] != "APPROVED_FOUNDATION" or not ui["status"].startswith("TECHNICALLY_QUALIFIED_FOUNDATION; F15/F16/F18/F21 CORRECTION") or value["next_candidate"] != "UI_ASSET_FAMILY"):
        failures.append("ui-asset-family-v0223-active-state-invalid")
    if value["version"] in {"0.23.0", "0.23.1", "0.23.2", "0.23.3", "0.23.4"}:
        vfx = next(item for item in capabilities if item["id"] == "vfx_asset_family")
        orchestration = next(item for item in capabilities if item["id"] == "orchestration_runtime_hardening")
        if maps["status"] != "APPROVED_FOUNDATION" or ui["status"] != "APPROVED_FOUNDATION; MERGED_CLOSED" or not (vfx["status"].startswith("TECHNICALLY_QUALIFIED_FOUNDATION") or vfx["status"].startswith("APPROVED_FOUNDATION")) or orchestration["status"] != "Blocked until VFX merged closed and post-merge main CI succeeds" or value["next_candidate"] != "ORCHESTRATION_RUNTIME_HARDENING":
            failures.append("vfx-asset-family-active-state-invalid")
    if value["version"] in {"0.24.0", "0.24.1", "0.24.2", "0.24.3", "0.24.4", "0.24.5", "0.24.6", "0.24.7"}:
        vfx = next(item for item in capabilities if item["id"] == "vfx_asset_family")
        orchestration = next(item for item in capabilities if item["id"] == "orchestration_runtime_hardening")
        if maps["status"] != "APPROVED_FOUNDATION" or ui["status"] != "APPROVED_FOUNDATION; MERGED_CLOSED" or vfx["status"] != "APPROVED_FOUNDATION; MERGED_CLOSED" or orchestration["status"] not in {"TECHNICALLY_QUALIFIED_FOUNDATION; EXTERNAL REVIEW REQUIRED", "APPROVED_FOUNDATION; GOVERNED_MERGE_PENDING"} or value["next_candidate"] != "V1_FINAL_ACCEPTANCE":
            failures.append("orchestration-runtime-active-state-invalid")
    if value["production_routing"] != "BLOCKED" or value["new_generation"] != 0:
        failures.append("matrix-crosses-production-or-generation-boundary")
    result = {"status": "V1_CAPABILITY_MATRIX_PASSED" if not failures else "V1_CAPABILITY_MATRIX_FAILED", "failures": failures, "version": value["version"], "capability_count": len(capabilities), "ids": ids, "next_candidate": value["next_candidate"], "items_props_status": items["status"], "environment_tilesets_status": environment["status"], "production_routing": value["production_routing"], "new_generation": value["new_generation"]}
    output = ROOT / "docs/evidence/orchestration-runtime-v0240/capability-matrix-validation-v0240.json" if value["version"] == "0.24.0" else (ROOT / "docs/evidence/vfx-asset-family-runtime-v0234/capability-matrix-validation-v0234.json" if value["version"] == "0.23.4" else (ROOT / "docs/evidence/vfx-asset-family-runtime-v0233/capability-matrix-validation-v0233.json" if value["version"] == "0.23.3" else (ROOT / "docs/evidence/vfx-asset-family-runtime-v0232/capability-matrix-validation-v0232.json" if value["version"] == "0.23.2" else (ROOT / "docs/evidence/vfx-asset-family-runtime-v0231/capability-matrix-validation-v0231.json" if value["version"] == "0.23.1" else (ROOT / "docs/evidence/vfx-asset-family-runtime-v0230/capability-matrix-validation-v0230.json" if value["version"] == "0.23.0" else (ROOT / "docs/evidence/ui-asset-family-runtime-v0223/capability-matrix-validation-v0223.json" if value["version"] == "0.22.3" else (ROOT / "docs/evidence/ui-asset-family-runtime-v0222/capability-matrix-validation-v0222.json" if value["version"] == "0.22.2" else (ROOT / "docs/evidence/ui-asset-family-runtime-v0221/capability-matrix-validation-v0221.json" if value["version"] == "0.22.1" else (ROOT / "docs/evidence/ui-asset-family-runtime-v0220/capability-matrix-validation-v0220.json" if value["version"] == "0.22.0" else (ROOT / "docs/evidence/maps-minimap-runtime-v0213/capability-matrix-validation-v0213.json" if value["version"] == "0.21.3" else (ROOT / "docs/evidence/maps-minimap-runtime-v0212/capability-matrix-validation-v0212.json" if value["version"] == "0.21.2" else (ROOT / "docs/evidence/maps-minimap-runtime-v0211/capability-matrix-validation-v0211.json" if value["version"] == "0.21.1" else ROOT / "docs/evidence/maps-minimap-runtime-v0210/capability-matrix-validation-v0210.json"))))))))))))
    if value["version"] == "0.24.1":
        output = ROOT / "docs/evidence/orchestration-runtime-v0241/capability-matrix-validation-v0241.json"
    if value["version"] == "0.24.2":
        output = ROOT / "docs/evidence/orchestration-runtime-v0242/capability-matrix-validation-v0242.json"
    if value["version"] == "0.24.3":
        output = ROOT / "docs/evidence/orchestration-runtime-v0243/capability-matrix-validation-v0243.json"
    if value["version"] == "0.24.4":
        output = ROOT / "docs/evidence/orchestration-runtime-v0244/capability-matrix-validation-v0244.json"
    if value["version"] == "0.24.5":
        output = ROOT / "docs/evidence/orchestration-runtime-v0245/capability-matrix-validation-v0245.json"
    if value["version"] == "0.24.6":
        output = ROOT / "docs/evidence/orchestration-runtime-v0246/capability-matrix-validation-v0246.json"
    if value["version"] == "0.24.7":
        output = ROOT / "docs/evidence/orchestration-runtime-v0247/capability-matrix-validation-v0247.json"
    if value["version"] == "0.21.3":
        # The v0.21.3 file is immutable technical history. The active matrix
        # is validated above and printed, while the runner restores this exact
        # historical record after its deterministic evidence generation.
        historical_result = dict(result)
        historical_result["next_candidate"] = "MAPS_MINIMAP"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(historical_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
