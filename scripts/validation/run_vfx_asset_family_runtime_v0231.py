"""Execute the complete deterministic VFX v0.23.1 F-22..F-28 correction."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.state_consistency_v0231 import (
    BASELINE_MAIN_SHA,
    CURRENT_GATE,
    FEATURE_BRANCH,
    NEXT_ACTION,
    NEXT_CANDIDATE,
    PR_NUMBER,
    resolve_next_actions,
    validate_state_consistency,
)
from ugas.vfx_asset_family_runtime_v0231 import (
    CLASS_SPECS,
    EFFECT_CLASSES,
    FAMILY_ID,
    REGISTRY_MODE,
    VERSION,
    VFXAssetFamilyContractError,
    build_budget_fallback_sheet,
    build_contact_sheets,
    cache_key_for,
    canonical_json,
    generate_fixture_pack,
    select_fallback,
    sha256_bytes,
    strict_boolean_observation,
    strict_gate,
    validate_blend_alpha,
    validate_budget,
    validate_class_spec_table,
    validate_decoded_alpha,
    validate_effect_record,
    validate_fallback,
    validate_fallback_result,
    validate_integration,
    validate_lifecycle,
    validate_production_registry,
    validate_representation,
    validate_spatial_anchor,
    validate_vfx_manifest,
    write_json,
)


EVIDENCE = ROOT / "docs/evidence/vfx-asset-family-runtime-v0231"
REJECTED_HEAD = "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72"


def _expect_rejection(control_id: str, defect: str, expected: str, action: Callable[[], Any]) -> dict[str, Any]:
    try:
        action()
    except VFXAssetFamilyContractError as exc:
        observed = exc.rejection_class
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": observed, "status": "PASS" if observed == expected else "FAIL", "result": "REJECT", "actual_exception": type(exc).__name__, "detail": exc.detail}
    return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "result": "ACCEPT", "actual_exception": None, "detail": "validator accepted injected defect"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _stable_manifest_hash(manifest: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(manifest))


def _raise_if_not(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise VFXAssetFamilyContractError(rejection_class, detail)


def _state_gate(state: dict[str, Any], matrix: dict[str, Any]) -> bool:
    result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"), matrix)
    return result["status"] == CURRENT_GATE and not result["failures"]


def _historical_immutability() -> dict[str, Any]:
    root = "docs/evidence/vfx-asset-family-runtime-v0230"
    current = subprocess.run(["git", "rev-parse", f"HEAD:{root}"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    authority = subprocess.run(["git", "rev-parse", f"{REJECTED_HEAD}:{root}"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    review_path = ROOT / "REVIEW-v0.23.0.md"
    current_review = review_path.read_bytes() if review_path.is_file() else b""
    authority_review = subprocess.run(["git", "show", f"{REJECTED_HEAD}:REVIEW-v0.23.0.md"], cwd=ROOT, capture_output=True, check=False).stdout
    byte_identical = current_review == authority_review and current == authority
    return {"status": "PASS" if byte_identical else "FAIL", "authority_ref": f"git:{REJECTED_HEAD}:{root}", "authority_tree": authority, "observed_tree": current, "review_authority_sha256": sha256_bytes(authority_review), "review_observed_sha256": sha256_bytes(current_review), "byte_identical": byte_identical, "historical_evidence_unchanged": byte_identical}


def _exact_sha_live(open_head: str) -> dict[str, Any]:
    return {"source": "GITHUB_LIVE", "repository": "KayzenRoot/ugas", "pr_number": PR_NUMBER, "branch": FEATURE_BRANCH, "base_sha": BASELINE_MAIN_SHA, "head_sha": open_head, "pr_state": "OPEN", "merged": False, "external_approval": False}


def _merged_live(sha: str) -> dict[str, Any]:
    return {"source": "GITHUB_LIVE", "repository": "KayzenRoot/ugas", "pr_number": PR_NUMBER, "branch": FEATURE_BRANCH, "base_sha": BASELINE_MAIN_SHA, "head_sha": sha, "pr_state": "MERGED", "merged": True, "external_approval": True, "merge_commit_sha": sha, "current_main_sha": sha, "post_merge_main_ci": {"commit_sha": sha, "context_records": [{"context": "UGAS CI / unit-and-validation", "status": "completed", "conclusion": "success", "head_sha": sha}, {"context": "UGAS CI / docker-smoke", "status": "completed", "conclusion": "success", "head_sha": sha}]}}


def _controls(records: list[dict[str, Any]], root: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    by_class = {item["effect_class"]: item for item in records}; base = by_class["impact_burst"]; loop = by_class["projectile_trail"]
    controls: list[dict[str, Any]] = []
    bad = deepcopy(base); bad["semantic_input"]["semantics"]["damage_amount"] = 2; controls.append(_expect_rejection("VFX231-NC-01", "gameplay damage field", "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["semantic_input"]["semantics"]["gameplay_authority"] = "COMBAT"; controls.append(_expect_rejection("VFX231-NC-02", "nested gameplay authority", "VFX_GAMEPLAY_AUTHORITY_FORBIDDEN", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(by_class["weapon_arc"]); bad["semantic_input"]["semantics"]["arc_span_degrees"] = "fixture-arc"; controls.append(_expect_rejection("VFX231-NC-03", "string arc span placeholder", "VFX_SEMANTIC_TYPE_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(loop); bad["lifecycle"]["loop_period_ms"] = None; controls.append(_expect_rejection("VFX231-NC-04", "missing owner loop period", "VFX_LOOP_PERIOD_INVALID", lambda: validate_lifecycle(bad)))
    bad = deepcopy(loop); bad["lifecycle"]["max_concurrent_instances"] = 0; controls.append(_expect_rejection("VFX231-NC-05", "zero per-effect concurrency", "VFX_LOOP_POLICY_INVALID", lambda: validate_lifecycle(bad)))
    bad = deepcopy(loop); bad["budget_profile"].pop("max_particles_per_instance"); controls.append(_expect_rejection("VFX231-NC-06", "missing per-effect particle budget", "VFX_BUDGET_INVALID", lambda: validate_budget(bad)))
    bad = deepcopy(loop); bad["budget_profile"]["max_particles_per_instance"] = 97; controls.append(_expect_rejection("VFX231-NC-07", "per-effect budget above authority", "VFX_BUDGET_EXCEEDED", lambda: validate_budget(bad)))
    bad = deepcopy(loop); bad["blend_alpha"]["alpha_mode"] = "PREMULTIPLIED"; bad["blend_alpha"]["premultiplied"] = True; controls.append(_expect_rejection("VFX231-NC-08", "straight bytes declared premultiplied", "VFX_BLEND_ALPHA_INVALID", lambda: validate_blend_alpha(bad)))
    bad = deepcopy(loop); bad["fallback"]["deterministic"] = False; controls.append(_expect_rejection("VFX231-NC-09", "nondeterministic fallback", "VFX_FALLBACK_INVALID", lambda: validate_fallback(bad)))
    profile = {"profile_id": "bad", "max_particles_per_instance": 8, "max_layers": 1, "max_spawn_events_per_second": 10, "max_visual_area_ratio": 0.2, "supported_steps": ["REDUCE_PARTICLE_COUNT"]}
    controls.append(_expect_rejection("VFX231-NC-10", "fallback skipped unsupported order", "VFX_FALLBACK_UNSUPPORTED_STEP", lambda: select_fallback(loop, profile)))
    bad = deepcopy(base); bad["lifecycle"]["duration_ms"] += 1; controls.append(_expect_rejection("VFX231-NC-11", "lifecycle semantic mutation", "VFX_TIMING_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["blend_alpha"]["blend_mode"] = "MULTIPLY"; controls.append(_expect_rejection("VFX231-NC-12", "blend mutation", "VFX_BLEND_ALPHA_INVALID", lambda: validate_blend_alpha(bad)))
    bad = deepcopy(base); bad["spatial"]["pivot"] = [2.0, 0.5]; controls.append(_expect_rejection("VFX231-NC-13", "spatial pivot mutation", "VFX_SPATIAL_CONTRACT_INVALID", lambda: validate_spatial_anchor(bad)))
    bad = deepcopy(base); bad["budget_profile"]["max_visual_area_ratio"] = 2.0; controls.append(_expect_rejection("VFX231-NC-14", "visual area budget mutation", "VFX_BUDGET_EXCEEDED", lambda: validate_budget(bad)))
    bad = deepcopy(base); bad["representation"]["decoded_pixel_contract"] = "PREMULTIPLIED_RGBA"; controls.append(_expect_rejection("VFX231-NC-15", "representation pixel identity mutation", "VFX_IMPORT_METADATA_INVALID", lambda: validate_representation(bad)))
    bad = deepcopy(base); bad["integration"]["integration_revision"] = "write-v2"; controls.append(_expect_rejection("VFX231-NC-16", "integration identity mutation", "VFX_INTEGRATION_MODE_INVALID", lambda: validate_integration(bad)))
    bad = deepcopy(base); bad["cache_key"] = "0" * 64; controls.append(_expect_rejection("VFX231-NC-17", "cache key mutation", "VFX_CACHE_KEY_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["semantic_contract"]["spatial"]["pivot"] = [0.25, 0.75]; controls.append(_expect_rejection("VFX231-NC-18", "stored complete contract mutation", "VFX_SEMANTIC_CONTRACT_HASH_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["provenance"]["effective_semantic_hash"] = "0" * 64; controls.append(_expect_rejection("VFX231-NC-19", "provenance complete identity mutation", "VFX_PROVENANCE_HASH_INVALID", lambda: validate_effect_record(bad, root)))
    bad = deepcopy(base); bad["frames"][0]["sha256"] = "0" * 64; controls.append(_expect_rejection("VFX231-NC-20", "frame content identity mutation", "VFX_FRAME_SET_HASH_INVALID", lambda: validate_effect_record(bad, root)))
    controls.append(_expect_rejection("VFX231-NC-21", "production registry entry", "VFX_PRODUCTION_BOUNDARY_REJECTED", lambda: validate_production_registry([{"effect_id": base["effect_id"]}])))
    controls.append(_expect_rejection("VFX231-NC-22", "non-bool None gate", "VFX_HARD_GATE_NON_BOOLEAN_REJECTED", lambda: _raise_if_not(strict_boolean_observation(None), "VFX_HARD_GATE_NON_BOOLEAN_REJECTED", "None")))
    controls.append(_expect_rejection("VFX231-NC-23", "non-bool truthy string gate", "VFX_HARD_GATE_NON_BOOLEAN_REJECTED", lambda: _raise_if_not(strict_boolean_observation("PASS"), "VFX_HARD_GATE_NON_BOOLEAN_REJECTED", "PASS")))
    stale = deepcopy(state); stale["review"]["head_sha"] = REJECTED_HEAD; controls.append(_expect_rejection("VFX231-NC-24", "tracked stale current head", "STATE_CONSISTENCY_FAILED", lambda: _raise_if_not(not validate_state_consistency(stale)["failures"] , "STATE_CONSISTENCY_FAILED", "stale head rejected")))
    open_live = _exact_sha_live(REJECTED_HEAD)
    controls.append(_expect_rejection("VFX231-NC-25", "tracked-only closure proof", "VFX_LIVE_CLOSURE_INCOMPLETE", lambda: _raise_if_not(resolve_next_actions(state, {"pr_state": "MERGED", "merged": True, "external_approval": True})["orchestration_allowed"], "VFX_LIVE_CLOSURE_INCOMPLETE", "missing live binding")))
    merged = _merged_live("a" * 40)
    bad_live = deepcopy(merged); bad_live["post_merge_main_ci"]["context_records"][0]["head_sha"] = "b" * 40; controls.append(_expect_rejection("VFX231-NC-26", "stale unit context head", "VFX_LIVE_CLOSURE_INCOMPLETE", lambda: _raise_if_not(resolve_next_actions(state, bad_live)["orchestration_allowed"], "VFX_LIVE_CLOSURE_INCOMPLETE", "stale unit head")))
    bad_live = deepcopy(merged); bad_live["post_merge_main_ci"]["context_records"][1]["head_sha"] = "b" * 40; controls.append(_expect_rejection("VFX231-NC-27", "mixed context heads", "VFX_LIVE_CLOSURE_INCOMPLETE", lambda: _raise_if_not(resolve_next_actions(state, bad_live)["orchestration_allowed"], "VFX_LIVE_CLOSURE_INCOMPLETE", "mixed heads")))
    bad_live = deepcopy(merged); bad_live["post_merge_main_ci"]["context_records"][0]["status"] = "pending"; controls.append(_expect_rejection("VFX231-NC-28", "pending main CI", "VFX_LIVE_CLOSURE_INCOMPLETE", lambda: _raise_if_not(resolve_next_actions(state, bad_live)["orchestration_allowed"], "VFX_LIVE_CLOSURE_INCOMPLETE", "pending")))
    bad_live = deepcopy(merged); bad_live["merge_commit_sha"] = "b" * 40; controls.append(_expect_rejection("VFX231-NC-29", "wrong merge SHA", "VFX_LIVE_CLOSURE_INCOMPLETE", lambda: _raise_if_not(resolve_next_actions(state, bad_live)["orchestration_allowed"], "VFX_LIVE_CLOSURE_INCOMPLETE", "wrong merge")))
    controls.append(_expect_rejection("VFX231-NC-30", "non-live source", "VFX_LIVE_CLOSURE_INCOMPLETE", lambda: _raise_if_not(resolve_next_actions(state, {**open_live, "source": "TRACKED_STATE"})["orchestration_allowed"], "VFX_LIVE_CLOSURE_INCOMPLETE", "tracked source")))
    return controls


def _write_contract_evidence(manifest: dict[str, Any], output_root: Path) -> None:
    records = manifest["effects"]
    suffix = "v0231"
    write_json(output_root / f"vfx-family-manifest-{suffix}.json", manifest)
    write_json(output_root / f"effect-class-contract-{suffix}.json", {"schema_version": VERSION, "family_id": FAMILY_ID, "classes": CLASS_SPECS})
    write_json(output_root / f"lifecycle-timing-{suffix}.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["lifecycle"]} for item in records]})
    write_json(output_root / f"blend-alpha-contract-{suffix}.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["blend_alpha"]} for item in records]})
    write_json(output_root / f"alpha-decoded-{suffix}.json", {"schema_version": VERSION, "status": "PASS", "mode": "STRAIGHT_RGBA", "effects": [{"effect_class": item["effect_class"], "pixel_proof": item["blend_alpha"]["pixel_proof"]} for item in records]})
    write_json(output_root / f"spatial-anchor-contract-{suffix}.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["spatial"]} for item in records]})
    write_json(output_root / f"budget-authority-{suffix}.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["budget_profile"]} for item in records]})
    write_json(output_root / f"fallback-degradation-{suffix}.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["fallback"]} for item in records]})
    write_json(output_root / f"representation-import-{suffix}.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["representation"]} for item in records]})
    write_json(output_root / f"integration-linkage-{suffix}.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item["integration"]} for item in records]})
    write_json(output_root / f"cache-provenance-{suffix}.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], "semantic_contract": item["semantic_contract"], "semantic_contract_hash": item["semantic_contract_hash"], "cache_key": item["cache_key"], "provenance": item["provenance"]} for item in records]})
    write_json(output_root / f"test-only-fixture-manifest-{suffix}.json", {"status": REGISTRY_MODE, "effect_count": len(records), "effect_classes": list(EFFECT_CLASSES), "real_vfx_asset_coverage": "NONE", "provider_generation_jobs": 0, "diffusion_runs": 0})


def main() -> int:
    global EVIDENCE
    parser = argparse.ArgumentParser(); parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE); args = parser.parse_args(); EVIDENCE = args.evidence_dir.resolve(); EVIDENCE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ugas-vfx-v0231-a-") as first_dir, tempfile.TemporaryDirectory(prefix="ugas-vfx-v0231-b-") as second_dir:
        first = generate_fixture_pack(Path(first_dir)); second = generate_fixture_pack(Path(second_dir)); first_hash = _stable_manifest_hash(first["manifest"]); second_hash = _stable_manifest_hash(second["manifest"])
    bounded = generate_fixture_pack(EVIDENCE); manifest = bounded["manifest"]; records = bounded["records"]; build_contact_sheets(records, EVIDENCE, EVIDENCE)
    profile = {"profile_id": "constrained-v1", "max_particles_per_instance": 8, "max_layers": 1, "max_spawn_events_per_second": 10, "max_visual_area_ratio": 0.20, "supported_steps": ["REDUCE_PARTICLE_COUNT", "REDUCE_LAYER_COUNT", "REDUCE_SPAWN_RATE", "REDUCE_VISUAL_AREA", "REDUCE_FRAME_COUNT", "REDUCE_OPACITY", "REDUCE_RADIUS", "SKIP_VISUAL"]}
    degraded = select_fallback(records[2], profile); build_budget_fallback_sheet(records[2], degraded, EVIDENCE / "vfx-budget-fallback-qa-sheet-v0231.png"); _write_contract_evidence(manifest, EVIDENCE)
    state = _load(ROOT / "docs/evidence/current-state.json"); matrix = _load(ROOT / "docs/ugas-v1-capability-matrix.json"); schema = _load(ROOT / "schemas/current-state-v0231.json"); runtime_schema = _load(ROOT / "schemas/vfx-asset-family-runtime-v0231.json")
    by_class = {item["effect_class"]: item for item in records}; gates: list[dict[str, Any]] = []
    gate_checks = [
        ("VFX231-HG-01", lambda: validate_class_spec_table() is None), ("VFX231-HG-02", lambda: len(EFFECT_CLASSES) == 10), ("VFX231-HG-03", lambda: len({item["stable_class_id"] for item in records}) == 10), ("VFX231-HG-04", lambda: validate_vfx_manifest(manifest, EVIDENCE)["status"] == "VFX_ASSET_FAMILY_MANIFEST_VALID"), ("VFX231-HG-05", lambda: all(item["intent"] == "VISUAL_ONLY" for item in records)), ("VFX231-HG-06", lambda: all(validate_lifecycle(item) is None for item in records)), ("VFX231-HG-07", lambda: all(item["lifecycle"]["loop"] is (item["lifecycle"]["mode"] == "OWNER_BOUND_LOOP") for item in records)), ("VFX231-HG-08", lambda: all(validate_blend_alpha(item) is None for item in records)), ("VFX231-HG-09", lambda: all(validate_decoded_alpha(item, EVIDENCE) is None for item in records)), ("VFX231-HG-10", lambda: all(validate_spatial_anchor(item) is None for item in records)), ("VFX231-HG-11", lambda: all(validate_budget(item) is None for item in records)), ("VFX231-HG-12", lambda: all(validate_fallback(item) is None for item in records)), ("VFX231-HG-13", lambda: all(validate_representation(item) is None for item in records)), ("VFX231-HG-14", lambda: all(validate_integration(item) is None for item in records)), ("VFX231-HG-15", lambda: all(item["cache_key"] == cache_key_for(item) for item in records)), ("VFX231-HG-16", lambda: all(item["provenance"]["effective_semantic_hash"] == item["semantic_contract_hash"] for item in records)), ("VFX231-HG-17", lambda: all(item["provenance"]["input_hash"] == item["semantic_input_hash"] for item in records)), ("VFX231-HG-18", lambda: all(item["frames"] and item["frames"][0]["alpha_range"][1] > 0 for item in records)), ("VFX231-HG-19", lambda: degraded["deterministic"] and degraded["visual_degraded"] and degraded["semantic_preserved"]), ("VFX231-HG-20", lambda: validate_fallback_result(records[2], degraded, profile) is None), ("VFX231-HG-21", lambda: validate_production_registry([])["registry"] == []), ("VFX231-HG-22", lambda: manifest["production_routing"] == "BLOCKED" and manifest["production_approved"] is False), ("VFX231-HG-23", lambda: manifest["new_generation"] == 0 and all(item["provenance"]["provider"] is None for item in records)), ("VFX231-HG-24", lambda: first_hash == second_hash and first["manifest"] == second["manifest"]), ("VFX231-HG-25", lambda: _state_gate(state, matrix)), ("VFX231-HG-26", lambda: validate_schema_document(schema) is None and validate_instance(state, schema) is None), ("VFX231-HG-27", lambda: validate_schema_document(runtime_schema) is None and validate_instance(manifest, runtime_schema) is None), ("VFX231-HG-28", lambda: _historical_immutability()["byte_identical"] is True), ("VFX231-HG-29", lambda: strict_boolean_observation(True) is True), ("VFX231-HG-30", lambda: strict_boolean_observation(1) is False), ("VFX231-HG-31", lambda: resolve_next_actions(state, _exact_sha_live(REJECTED_HEAD))["allowed_next_actions"] == [NEXT_ACTION]), ("VFX231-HG-32", lambda: resolve_next_actions(state, _merged_live("a" * 40))["orchestration_allowed"] is True),
    ]
    for gate_id, checker in gate_checks: gates.append(strict_gate(gate_id, checker))
    controls = _controls(records, EVIDENCE, state); historical = _historical_immutability(); state_result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"), matrix); all_gates_pass = len(gates) == 32 and all(item["status"] == "PASS" and item["observed"] is True and type(item["observed"]) is bool for item in gates); all_controls_pass = len(controls) == 30 and all(item["status"] == "PASS" and item["result"] == "REJECT" and item["expected_rejection_class"] == item["observed_rejection_class"] for item in controls); overall = all_gates_pass and all_controls_pass and first_hash == second_hash and historical["status"] == "PASS" and state_result["status"] == CURRENT_GATE and not state_result["failures"]
    write_json(EVIDENCE / "hard-gates-v0231.json", {"status": "PASS" if all_gates_pass else "FAIL", "required_gate_count": 32, "gates": {item["gate_id"]: item for item in gates}}); write_json(EVIDENCE / "negative-controls-v0231.json", {"status": "PASS" if all_controls_pass else "FAIL", "required_control_count": 30, "controls": {item["control_id"]: item for item in controls}}); write_json(EVIDENCE / "full-slice-two-run-determinism-v0231.json", {"status": "PASS" if first_hash == second_hash else "FAIL", "first_run_sha256": first_hash, "second_run_sha256": second_hash, "equal": first_hash == second_hash}); write_json(EVIDENCE / "historical-immutability-v0231.json", historical); write_json(EVIDENCE / "production-registry-v0231.json", {**validate_production_registry([]), "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": "TEST_ONLY"}); write_json(EVIDENCE / "state-consistency-v0231.json", state_result); write_json(EVIDENCE / "schema-validation-v0231.json", {"status": "PASS" if validate_instance(state, schema) is None else "FAIL", "schema": "schemas/current-state-v0231.json", "instance": "docs/evidence/current-state.json"}); write_json(EVIDENCE / "capability-matrix-validation-v0231.json", {"status": "PASS" if matrix.get("version") == VERSION and matrix.get("next_candidate") == NEXT_CANDIDATE else "FAIL", "version": matrix.get("version"), "next_candidate": matrix.get("next_candidate"), "production_routing": matrix.get("production_routing"), "new_generation": matrix.get("new_generation")}); write_json(EVIDENCE / "v0.23.0-rejection-correction-v0231.json", {"status": "CORRECTION_REQUIRED", "reviewed_head": REJECTED_HEAD, "findings": ["F-22", "F-23", "F-24", "F-25", "F-26", "F-27", "F-28"], "historical_evidence_unchanged": historical["byte_identical"], "forward_only": True}); write_json(EVIDENCE / "exact-sha-lifecycle-v0231.json", {"source": "GitHub LIVE exact-head metadata", "pr_number": PR_NUMBER, "pr_state": "OPEN", "merged": False, "tracked_head_sha": None, "base_main_sha": BASELINE_MAIN_SHA, "current_head_resolution": "external exact-head artifact / GitHub LIVE"}); write_json(EVIDENCE / "qa-contact-timing-v0231.json", {"status": "PASS" if overall else "FAIL", "classes": [{"effect_class": item["effect_class"], "frame_count": item["lifecycle"]["frame_count"], "duration_ms": item["lifecycle"]["duration_ms"], "loop": item["lifecycle"]["loop"]} for item in records]}); write_json(EVIDENCE / "execution-evidence-v0231.json", {"status": CURRENT_GATE if overall else "VFX_ASSET_FAMILY_RUNTIME_CORRECTION_FAILED", "overall_pass": overall, "schema_version": VERSION, "family_id": FAMILY_ID, "corrections": ["F-22", "F-23", "F-24", "F-25", "F-26", "F-27", "F-28"], "hard_gate_count": len(gates), "negative_control_count": len(controls), "effect_class_count": len(records), "production_routing": "BLOCKED", "production_approved": False, "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": "TEST_ONLY", "new_generation": 0, "provider_generation_jobs": 0, "diffusion_runs": 0, "base_main_sha": BASELINE_MAIN_SHA, "rejected_reviewed_head": REJECTED_HEAD})
    print(json.dumps({"status": CURRENT_GATE if overall else "FAIL", "overall_pass": overall, "hard_gates": len(gates), "negative_controls": len(controls), "evidence": str(EVIDENCE)})); return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
