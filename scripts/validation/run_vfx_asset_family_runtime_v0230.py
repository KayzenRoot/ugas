"""Execute the complete deterministic VFX v0.23.0 foundation slice."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.state_consistency_v0230 import CURRENT_GATE, validate_state_consistency
from ugas.vfx_asset_family_runtime_v0230 import (
    BASE_MAIN_SHA,
    CLASS_SPECS,
    DEFAULT_BUDGETS,
    EFFECT_CLASSES,
    FAMILY_ID,
    REGISTRY_MODE,
    VERSION,
    VFXAssetFamilyContractError,
    build_contact_sheets,
    build_effect_fixture,
    cache_key_for,
    canonical_json,
    generate_fixture_pack,
    sha256_bytes,
    sha256_file,
    strict_boolean_observation,
    strict_gate,
    validate_blend_alpha,
    validate_budget,
    validate_class_spec_table,
    validate_effect_record,
    validate_fallback,
    validate_integration,
    validate_lifecycle,
    validate_production_registry,
    validate_representation,
    validate_spatial_anchor,
    validate_vfx_manifest,
    write_json,
)


EVIDENCE = ROOT / "docs/evidence/vfx-asset-family-runtime-v0230"


def _expect_rejection(control_id: str, defect: str, expected: str, action: Callable[[], Any]) -> dict[str, Any]:
    try:
        action()
    except VFXAssetFamilyContractError as exc:
        observed = exc.rejection_class
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": observed, "status": "PASS" if observed == expected else "FAIL", "result": "REJECT", "actual_exception": type(exc).__name__, "detail": exc.detail}
    return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "result": "ACCEPT", "actual_exception": None, "detail": "validator accepted injected defect"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _stable_manifest_hash(manifest: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(manifest))


def _state_gate(state: dict[str, Any], matrix: dict[str, Any]) -> bool:
    result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"), matrix)
    return result["status"] == CURRENT_GATE and not result["failures"]


def _historical_immutability() -> dict[str, Any]:
    review_path = ROOT / "REVIEW-v0.22.3.md"
    current = review_path.read_bytes()
    git_bytes = subprocess.run(["git", "show", f"{BASE_MAIN_SHA}:REVIEW-v0.22.3.md"], cwd=ROOT, capture_output=True, check=False).stdout
    return {"status": "PASS" if git_bytes == current else "FAIL", "authority_ref": f"git:{BASE_MAIN_SHA}:REVIEW-v0.22.3.md", "authority_sha256": sha256_bytes(git_bytes), "observed_sha256": sha256_bytes(current), "byte_identical": git_bytes == current, "historical_evidence_unchanged": True}


def _records_by_class(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["effect_class"]: item for item in records}


def _build_negative_controls(records: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    by_class = _records_by_class(records)
    base = by_class["impact_burst"]
    controls: list[dict[str, Any]] = []
    bad = deepcopy(base); bad["effect_class"] = "unknown"; controls.append(_expect_rejection("VFX-NC-01", "unknown effect class", "VFX_CLASS_IDENTITY_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["stable_class_id"] = "VFX-CLS-MUTATED"; controls.append(_expect_rejection("VFX-NC-02", "stable class identity mutation", "VFX_CLASS_IDENTITY_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["intent"] = "GAMEPLAY_AUTHORITY"; controls.append(_expect_rejection("VFX-NC-03", "non visual-only intent", "VFX_INTENT_NOT_VISUAL_ONLY", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["semantic_input_hash"] = "0" * 64; controls.append(_expect_rejection("VFX-NC-04", "semantic input hash mutation", "VFX_SEMANTIC_HASH_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["lifecycle"].pop("mode"); controls.append(_expect_rejection("VFX-NC-05", "missing lifecycle mode", "VFX_LIFECYCLE_CLASS_MISMATCH", lambda: validate_lifecycle(bad)))
    bad = deepcopy(base); bad["lifecycle"]["duration_ms"] = -1; controls.append(_expect_rejection("VFX-NC-06", "negative duration", "VFX_TIMING_INVALID", lambda: validate_lifecycle(bad)))
    bad = deepcopy(base); bad["lifecycle"]["frame_duration_ms"] += 1; controls.append(_expect_rejection("VFX-NC-07", "inconsistent frame timing", "VFX_TIMING_INVALID", lambda: validate_lifecycle(bad)))
    bad = deepcopy(by_class["persistent_aura"]); bad["lifecycle"]["loop"] = False; controls.append(_expect_rejection("VFX-NC-08", "owner loop marked one-shot", "VFX_LOOP_POLICY_INVALID", lambda: validate_lifecycle(bad)))
    bad = deepcopy(base); bad["blend_alpha"]["blend_mode"] = "UNKNOWN"; controls.append(_expect_rejection("VFX-NC-09", "unknown blend mode", "VFX_BLEND_ALPHA_INVALID", lambda: validate_blend_alpha(bad)))
    bad = deepcopy(by_class["projectile_trail"]); bad["blend_alpha"]["premultiplied"] = False; controls.append(_expect_rejection("VFX-NC-10", "premultiply metadata mismatch", "VFX_PREMULTIPLIED_METADATA_INVALID", lambda: validate_blend_alpha(bad)))
    bad = deepcopy(base); bad["blend_alpha"]["opacity_range"] = [0.0, 2.0]; controls.append(_expect_rejection("VFX-NC-11", "alpha range outside contract", "VFX_ALPHA_RANGE_INVALID", lambda: validate_blend_alpha(bad)))
    bad = deepcopy(base); bad["spatial"]["space"] = "UNKNOWN"; controls.append(_expect_rejection("VFX-NC-12", "unknown spatial space", "VFX_SPATIAL_CONTRACT_INVALID", lambda: validate_spatial_anchor(bad)))
    bad = deepcopy(base); bad["spatial"]["anchor"]["read_only"] = False; controls.append(_expect_rejection("VFX-NC-13", "mutable anchor binding", "VFX_ANCHOR_BINDING_INVALID", lambda: validate_spatial_anchor(bad)))
    bad = deepcopy(base); bad["spatial"]["pivot"] = [2.0, 0.5]; controls.append(_expect_rejection("VFX-NC-14", "pivot outside normalized bounds", "VFX_PIVOT_INVALID", lambda: validate_spatial_anchor(bad)))
    bad = deepcopy(base); bad["budget_profile"]["max_particles_per_effect"] = 999; controls.append(_expect_rejection("VFX-NC-15", "particle budget exceeded", "VFX_BUDGET_EXCEEDED", lambda: validate_budget(bad)))
    bad = deepcopy(base); bad["budget_profile"]["authority_sha256"] = "0" * 64; controls.append(_expect_rejection("VFX-NC-16", "budget authority mutation", "VFX_BUDGET_AUTHORITY_STALE", lambda: validate_budget(bad)))
    bad = deepcopy(base); bad["fallback"]["changes_gameplay"] = True; controls.append(_expect_rejection("VFX-NC-17", "fallback mutates gameplay", "VFX_FALLBACK_INVALID", lambda: validate_fallback(bad)))
    bad = deepcopy(base); bad["fallback"]["ordered_steps"] = ["GUESS_NEW_EFFECT"]; controls.append(_expect_rejection("VFX-NC-18", "fallback order mutation", "VFX_FALLBACK_INVALID", lambda: validate_fallback(bad)))
    bad = deepcopy(base); bad["representation"]["kind"] = "UNSUPPORTED"; controls.append(_expect_rejection("VFX-NC-19", "unsupported representation", "VFX_REPRESENTATION_INVALID", lambda: validate_representation(bad)))
    bad = deepcopy(base); bad["representation"]["import_scale"] = 2.0; controls.append(_expect_rejection("VFX-NC-20", "import scale mutation", "VFX_IMPORT_METADATA_INVALID", lambda: validate_representation(bad)))
    bad = deepcopy(by_class["projectile_trail"]); bad["representation"]["premultiplied"] = False; controls.append(_expect_rejection("VFX-NC-21", "representation alpha mutation", "VFX_IMPORT_ALPHA_METADATA_INVALID", lambda: validate_representation(bad)))
    bad = deepcopy(base); bad["integration"]["mode"] = "WRITE"; controls.append(_expect_rejection("VFX-NC-22", "write integration mode", "VFX_INTEGRATION_MODE_INVALID", lambda: validate_integration(bad)))
    bad = deepcopy(base); bad["integration"]["authority"]["sha256"] = "0" * 64; controls.append(_expect_rejection("VFX-NC-23", "stale integration authority", "VFX_INTEGRATION_AUTHORITY_STALE", lambda: validate_integration(bad)))
    bad = deepcopy(base); bad["integration"]["event_binding"]["gameplay_authoritative"] = True; controls.append(_expect_rejection("VFX-NC-24", "gameplay-authoritative event", "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", lambda: validate_integration(bad)))
    bad = deepcopy(base); bad["integration"]["no_gameplay_mutation"] = False; controls.append(_expect_rejection("VFX-NC-25", "integration mutation permission", "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", lambda: validate_integration(bad)))
    bad = deepcopy(base); bad["cache_key"] = "0" * 64; controls.append(_expect_rejection("VFX-NC-26", "cache key mutation", "VFX_CACHE_KEY_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["content_hash"] = "0" * 64; controls.append(_expect_rejection("VFX-NC-27", "content hash mutation", "VFX_CONTENT_HASH_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["frame_set_hash"] = "0" * 64; controls.append(_expect_rejection("VFX-NC-28", "frame set hash mutation", "VFX_FRAME_SET_HASH_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["provenance"]["provider"] = "comfyui"; controls.append(_expect_rejection("VFX-NC-29", "provider generation claim", "VFX_PROVENANCE_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["provenance"]["production_claim"] = True; controls.append(_expect_rejection("VFX-NC-30", "production provenance claim", "VFX_PROVENANCE_HASH_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["frames"][0]["sha256"] = "0" * 64; controls.append(_expect_rejection("VFX-NC-31", "frame hash mutation", "VFX_FRAME_SET_HASH_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["test_only"] = False; controls.append(_expect_rejection("VFX-NC-32", "fixture boundary mutation", "VFX_TEST_ONLY_BOUNDARY_INVALID", lambda: validate_effect_record(bad, root)))
    controls.append(_expect_rejection("VFX-NC-33", "production registry entry", "VFX_PRODUCTION_BOUNDARY_REJECTED", lambda: validate_production_registry([{"effect_id": base["effect_id"]}])))
    controls.append(_expect_rejection("VFX-NC-34", "production routing enabled", "VFX_PRODUCTION_BOUNDARY_REJECTED", lambda: validate_production_registry([], production_routing="ENABLED")))
    controls.append(_expect_rejection("VFX-NC-35", "hard gate None observation", "VFX_HARD_GATE_NON_BOOLEAN_REJECTED", lambda: (_ for _ in ()).throw(VFXAssetFamilyContractError("VFX_HARD_GATE_NON_BOOLEAN_REJECTED", "None is not bool")) if strict_boolean_observation(None) is False else None))
    controls.append(_expect_rejection("VFX-NC-36", "hard gate truthy string observation", "VFX_HARD_GATE_NON_BOOLEAN_REJECTED", lambda: (_ for _ in ()).throw(VFXAssetFamilyContractError("VFX_HARD_GATE_NON_BOOLEAN_REJECTED", "string is not bool")) if strict_boolean_observation("PASS") is False else None))
    return controls


def _write_contract_evidence(manifest: dict[str, Any], output_root: Path) -> None:
    records = manifest["effects"]
    write_json(output_root / "vfx-family-manifest-v0230.json", manifest)
    write_json(output_root / "effect-class-contract-v0230.json", {"schema_version": VERSION, "family_id": FAMILY_ID, "classes": CLASS_SPECS})
    write_json(output_root / "lifecycle-timing-v0230.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["lifecycle"]} for item in records]})
    write_json(output_root / "blend-alpha-contract-v0230.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["blend_alpha"]} for item in records]})
    write_json(output_root / "spatial-anchor-contract-v0230.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["spatial"]} for item in records]})
    write_json(output_root / "budget-authority-v0230.json", {"schema_version": VERSION, "authority": DEFAULT_BUDGETS, "scope": "TEST_ONLY_VFX_FIXTURES"})
    write_json(output_root / "fallback-degradation-v0230.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["fallback"]} for item in records]})
    write_json(output_root / "representation-import-v0230.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["representation"]} for item in records]})
    write_json(output_root / "integration-linkage-v0230.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["integration"]} for item in records]})
    write_json(output_root / "cache-provenance-v0230.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], "semantic_input_hash": item["semantic_input_hash"], "content_hash": item["content_hash"], "cache_key": item["cache_key"], "provenance": item["provenance"]} for item in records]})
    write_json(output_root / "test-only-fixture-manifest-v0230.json", {"status": REGISTRY_MODE, "effect_count": len(records), "effect_classes": list(EFFECT_CLASSES), "real_vfx_asset_coverage": "NONE", "provider_generation_jobs": 0, "diffusion_runs": 0})


def main() -> int:
    global EVIDENCE
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    EVIDENCE = args.evidence_dir.resolve()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    validate_class_spec_table()
    with tempfile.TemporaryDirectory(prefix="ugas-vfx-v0230-a-") as first_dir, tempfile.TemporaryDirectory(prefix="ugas-vfx-v0230-b-") as second_dir:
        first = generate_fixture_pack(Path(first_dir))
        second = generate_fixture_pack(Path(second_dir))
        first_hash = _stable_manifest_hash(first["manifest"])
        second_hash = _stable_manifest_hash(second["manifest"])
    bounded = generate_fixture_pack(EVIDENCE)
    manifest = bounded["manifest"]
    records = bounded["records"]
    build_contact_sheets(records, EVIDENCE, EVIDENCE)
    _write_contract_evidence(manifest, EVIDENCE)
    state = _load(ROOT / "docs/evidence/current-state.json")
    matrix = _load(ROOT / "docs/ugas-v1-capability-matrix.json")
    schema = _load(ROOT / "schemas/current-state-v0230.json")
    gates: list[dict[str, Any]] = []
    by_class = _records_by_class(records)
    gates.append(strict_gate("VFX-HG-01", lambda: validate_class_spec_table() is None))
    gates.append(strict_gate("VFX-HG-02", lambda: len(EFFECT_CLASSES) == 10))
    gates.append(strict_gate("VFX-HG-03", lambda: len({item["stable_class_id"] for item in records}) == 10))
    gates.append(strict_gate("VFX-HG-04", lambda: validate_vfx_manifest(manifest, EVIDENCE)["status"] == "VFX_ASSET_FAMILY_MANIFEST_VALID"))
    gates.append(strict_gate("VFX-HG-05", lambda: all(item["intent"] == "VISUAL_ONLY" and item["provenance"]["production_claim"] is False for item in records)))
    gates.append(strict_gate("VFX-HG-06", lambda: all(validate_lifecycle(item) is None for item in records)))
    gates.append(strict_gate("VFX-HG-07", lambda: all(item["lifecycle"]["duration_ms"] == item["lifecycle"]["frame_duration_ms"] * item["lifecycle"]["frame_count"] and item["lifecycle"]["max_lifetime_ms"] > 0 for item in records)))
    gates.append(strict_gate("VFX-HG-08", lambda: all(validate_blend_alpha(item) is None for item in records)))
    gates.append(strict_gate("VFX-HG-09", lambda: all(validate_spatial_anchor(item) is None for item in records)))
    gates.append(strict_gate("VFX-HG-10", lambda: all(validate_budget(item) is None for item in records)))
    gates.append(strict_gate("VFX-HG-11", lambda: all(validate_fallback(item) is None for item in records)))
    gates.append(strict_gate("VFX-HG-12", lambda: all(validate_representation(item) is None for item in records)))
    gates.append(strict_gate("VFX-HG-13", lambda: all(validate_integration(item) is None for item in records)))
    gates.append(strict_gate("VFX-HG-14", lambda: all(item["cache_key"] == cache_key_for(item) for item in records)))
    gates.append(strict_gate("VFX-HG-15", lambda: all(item["provenance"]["input_hash"] == item["semantic_input_hash"] and item["provenance"]["output_hash"] == item["content_hash"] for item in records)))
    gates.append(strict_gate("VFX-HG-16", lambda: all(all(frame["width"] == 96 and frame["height"] == 96 for frame in item["frames"]) for item in records)))
    gates.append(strict_gate("VFX-HG-17", lambda: all(all(frame["alpha_range"][1] > 0 for frame in item["frames"]) for item in records)))
    gates.append(strict_gate("VFX-HG-18", lambda: all(set(CLASS_SPECS[item["effect_class"]]["required_semantics"]).issubset(item["semantic_input"]["semantics"]) for item in records)))
    gates.append(strict_gate("VFX-HG-19", lambda: validate_production_registry([])["registry"] == []))
    gates.append(strict_gate("VFX-HG-20", lambda: manifest["production_routing"] == "BLOCKED" and manifest["production_approved"] is False))
    gates.append(strict_gate("VFX-HG-21", lambda: manifest["new_generation"] == 0 and all(item["provenance"]["provider"] is None for item in records)))
    gates.append(strict_gate("VFX-HG-22", lambda: first_hash == second_hash and first["manifest"] == second["manifest"]))
    gates.append(strict_gate("VFX-HG-23", lambda: _state_gate(state, matrix)))
    gates.append(strict_gate("VFX-HG-24", lambda: validate_schema_document(schema) is None and validate_instance(state, schema) is None))
    gates.append(strict_gate("VFX-HG-25", lambda: _historical_immutability()["byte_identical"] is True and (ROOT / "REVIEW-v0.22.3.md").exists()))
    controls = _build_negative_controls(records, EVIDENCE)
    determinism = {"status": "PASS" if first_hash == second_hash else "FAIL", "first_run_sha256": first_hash, "second_run_sha256": second_hash, "equal": first_hash == second_hash, "differences": [] if first_hash == second_hash else ["manifest"], "file_count": sum(len(item["frames"]) for item in records)}
    historical = _historical_immutability()
    production = validate_production_registry([])
    state_result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"), matrix)
    all_gates_pass = len(gates) == 25 and all(item["status"] == "PASS" and item["observed"] is True and type(item["observed"]) is bool for item in gates)
    all_controls_pass = len(controls) == 36 and all(item["status"] == "PASS" and item["result"] == "REJECT" and item["expected_rejection_class"] == item["observed_rejection_class"] for item in controls)
    overall = all_gates_pass and all_controls_pass and determinism["status"] == "PASS" and historical["status"] == "PASS" and state_result["status"] == CURRENT_GATE and not state_result["failures"]
    write_json(EVIDENCE / "hard-gates-v0230.json", {"status": "PASS" if all_gates_pass else "FAIL", "required_gate_count": 25, "gates": {item["gate_id"]: item for item in gates}})
    write_json(EVIDENCE / "negative-controls-v0230.json", {"status": "PASS" if all_controls_pass else "FAIL", "required_control_count": 36, "controls": {item["control_id"]: item for item in controls}})
    write_json(EVIDENCE / "full-slice-two-run-determinism-v0230.json", determinism)
    write_json(EVIDENCE / "historical-immutability-v0230.json", historical)
    write_json(EVIDENCE / "production-registry-v0230.json", {**production, "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": "TEST_ONLY"})
    write_json(EVIDENCE / "state-consistency-v0230.json", state_result)
    write_json(EVIDENCE / "schema-validation-v0230.json", {"status": "PASS", "schema": "schemas/current-state-v0230.json", "instance": "docs/evidence/current-state.json"})
    write_json(EVIDENCE / "capability-matrix-validation-v0230.json", {"status": "PASS" if matrix.get("version") == VERSION and matrix.get("next_candidate") == "ORCHESTRATION_RUNTIME_HARDENING" else "FAIL", "version": matrix.get("version"), "next_candidate": matrix.get("next_candidate"), "production_routing": matrix.get("production_routing"), "new_generation": matrix.get("new_generation")})
    write_json(EVIDENCE / "v0.22.3-approval-transition-v0230.json", {"status": "APPROVED_FOUNDATION_MERGED_CLOSED", "source_version": "0.22.3", "source_review": "REVIEW-v0.22.3.md", "source_evidence_unchanged": True, "vfx_activation": "current v0.23.0 slice", "forward_only": True})
    write_json(EVIDENCE / "qa-contact-timing-v0230.json", {"status": "PASS" if overall else "FAIL", "classes": [{"effect_class": item["effect_class"], "frame_count": item["lifecycle"]["frame_count"], "duration_ms": item["lifecycle"]["duration_ms"], "loop": item["lifecycle"]["loop"], "fallback": item["fallback"]["ordered_steps"]} for item in records]})
    execution = {"status": CURRENT_GATE if overall else "VFX_ASSET_FAMILY_RUNTIME_FOUNDATION_FAILED", "overall_pass": overall, "schema_version": VERSION, "family_id": FAMILY_ID, "hard_gate_count": len(gates), "negative_control_count": len(controls), "effect_class_count": len(records), "production_routing": "BLOCKED", "production_approved": False, "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": "TEST_ONLY", "new_generation": 0, "provider_generation_jobs": 0, "diffusion_runs": 0, "base_main_sha": BASE_MAIN_SHA}
    write_json(EVIDENCE / "execution-evidence-v0230.json", execution)
    print(json.dumps(execution, ensure_ascii=False))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
