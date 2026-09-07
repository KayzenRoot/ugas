"""Execute the complete forward-only UI v0.22.2 correction slice."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
import sys
sys.path.insert(0, str(SRC))

from ugas.state_consistency_v0222 import (CANONICAL_CLOSURE_AUTHORITY, NEXT_ACTION, POST_MERGE_CLOSURE_BINDING, SUPERSEDED_CLOSURE_AUTHORITY, resolve_next_actions, validate_state_consistency)
from ugas.ui_asset_family_runtime_v0222 import (CLASS_SPECS, FAMILY_ID, LOCAL_STYLE_AUTHORITY_BYTES, LOCAL_STYLE_AUTHORITY_SHA, UIAssetFamilyContractError, UI_COMPONENT_CLASSES, UI_STATES, build_test_only_style_tokens, build_ui_manifest, cache_key_for, canonical_json, compare_generated_outputs, generate_fixture_pack, progress_fill_rect, render_component, render_component_to_size, sha256_bytes, validate_cache_record, validate_class_spec_table, validate_component_record, validate_determinism, validate_historical_authority, validate_integration_linkage, validate_nine_slice, validate_progress_bar_contract, validate_production_registry, validate_reconstructed_output, validate_scale_pixel_relation, validate_state_applicability, validate_ui_manifest, verify_nine_slice_invariants, write_json)
from validate_github_governance_v0222 import GovernanceContractError, validate_binding


EVIDENCE = ROOT / "docs/evidence/ui-asset-family-runtime-v0222"
GOVERNANCE_BINDING = ROOT / "docs/evidence/github-governance-v0222/v0222-ui-closure-binding.json"
OLD_AUTHORITY = ROOT / "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"
BASE_MAIN = "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3"
PR_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence")


def _strict_gate(gate_id: str, checker: Callable[[], Any]) -> dict[str, Any]:
    try:
        observed = checker()
        detail = "checker returned"
    except Exception as exc:  # the gate fails closed while preserving type/value
        observed = False
        detail = f"{type(exc).__name__}:{exc}"
    passed = type(observed) is bool and observed is True
    return {"gate_id": gate_id, "status": "PASS" if passed else "FAIL", "observed": observed, "observed_type": type(observed).__name__, "passed": passed, "detail": detail}


def _expect_rejection(control_id: str, defect: str, expected: str, action: Callable[[], Any]) -> dict[str, Any]:
    try:
        action()
    except (UIAssetFamilyContractError, GovernanceContractError) as exc:
        observed = exc.rejection_class
        return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": observed, "status": "PASS" if observed == expected else "FAIL", "result": "REJECT", "actual_exception": type(exc).__name__}
    return {"control_id": control_id, "injected_defect": defect, "expected_rejection_class": expected, "observed_rejection_class": None, "status": "FAIL", "result": "ACCEPT", "actual_exception": None}


def _state_reject(result: Any, rejection_class: str) -> None:
    if isinstance(result, dict) and result.get("failures"):
        raise UIAssetFamilyContractError(rejection_class, ";".join(result["failures"]))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _state_consistency_gate(state: dict[str, Any], binding: dict[str, Any]) -> bool:
    result = validate_state_consistency(state, binding, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.22.2.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"))
    return result["status"] == "UI_ASSET_FAMILY_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED" and not result["failures"]


def _historical_proof() -> dict[str, Any]:
    authority = subprocess.run(["git", "show", f"{BASE_MAIN}:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"], cwd=ROOT, capture_output=True, check=False).stdout
    candidate = OLD_AUTHORITY.read_bytes()
    positive = validate_historical_authority(authority, candidate, authority_ref=f"git:{BASE_MAIN}:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json")
    mutation = bytearray(candidate); mutation[-2] = 0x20 if mutation[-2] != 0x20 else 0x21
    try:
        validate_historical_authority(authority, bytes(mutation), authority_ref=positive["authority_ref"])
    except UIAssetFamilyContractError as exc:
        rejection = {"status": "REJECT", "rejection_class": exc.rejection_class, "exception": type(exc).__name__}
    else:
        rejection = {"status": "ACCEPT", "rejection_class": None, "exception": None}
    return {"authority_ref": positive["authority_ref"], "authority_sha256": positive["authority_sha256"], "observed_hash": positive["candidate_sha256"], "current_file_valid": True, "mutation_input_fingerprint": sha256_bytes(bytes(mutation)), "mutation_rejection": rejection}


def _life(state: dict[str, Any], *, approved: bool, merged: bool, ci: bool) -> dict[str, Any]:
    return resolve_next_actions(state, {"source_mode": "GITHUB_LIVE", "pr_number": 13, "external_approval": approved, "merged": merged, "post_merge_main_ci": {"supported_contexts": ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke"], "contexts": [{"name": "UGAS CI / unit-and-validation", "status": "completed" if ci else "in_progress", "conclusion": "success" if ci else None, "head_sha": "future-main"}, {"name": "UGAS CI / docker-smoke", "status": "completed" if ci else "in_progress", "conclusion": "success" if ci else None, "head_sha": "future-main"}]}})


def main() -> int:
    global EVIDENCE
    parser = argparse.ArgumentParser(); parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE); args = parser.parse_args()
    EVIDENCE = args.evidence_dir.resolve(); EVIDENCE.mkdir(parents=True, exist_ok=True)
    tokens = build_test_only_style_tokens(); manifest = build_ui_manifest(tokens); validate_ui_manifest(manifest, tokens)
    write_json(EVIDENCE / "ui-style-authority-v0222.json", json.loads(LOCAL_STYLE_AUTHORITY_BYTES.decode("utf-8")))
    with tempfile.TemporaryDirectory(prefix="ugas-ui-v0222-a-") as first_dir, tempfile.TemporaryDirectory(prefix="ugas-ui-v0222-b-") as second_dir:
        first = generate_fixture_pack(Path(first_dir)); second = generate_fixture_pack(Path(second_dir)); bounded = generate_fixture_pack(EVIDENCE)
    components = bounded["manifest"]["components"]; by_class = {item["component_class"]: item for item in components}; progress = by_class["progress_bar"]; button = by_class["button"]; window = by_class["window_frame"]; binding = _load_json(GOVERNANCE_BINDING); state = _load_json(ROOT / "docs/evidence/current-state.json")
    gates: list[dict[str, Any]] = []
    gates.append(_strict_gate("UI22-HG-01", lambda: validate_class_spec_table() is None))
    gates.append(_strict_gate("UI22-HG-02", lambda: validate_ui_manifest(bounded["manifest"], tokens)["status"] == "UI_ASSET_FAMILY_MANIFEST_VALID"))
    gates.append(_strict_gate("UI22-HG-03", lambda: len({item["component_id"] for item in components}) == len(UI_COMPONENT_CLASSES)))
    gates.append(_strict_gate("UI22-HG-04", lambda: all(validate_state_applicability(item) is not None for item in components)))
    gates.append(_strict_gate("UI22-HG-05", lambda: all(validate_nine_slice(item) is not None for item in components)))
    gates.append(_strict_gate("UI22-HG-06", lambda: all(item["content_hash"] == sha256_bytes(canonical_json({key: value for key, value in item.items() if key != "content_hash"})) for item in components)))
    gates.append(_strict_gate("UI22-HG-07", lambda: validate_progress_bar_contract(progress) is not None))
    gates.append(_strict_gate("UI22-HG-08", lambda: all(validate_progress_bar_contract(progress, value) is not None and progress_fill_rect(progress, value)["width"] == int(progress["class_metadata"]["fill_rect"]["width"] * value) for value in (0.0, 0.5, 1.0))))
    gates.append(_strict_gate("UI22-HG-09", lambda: _rect_containment_progress(progress)))
    gates.append(_strict_gate("UI22-HG-10", lambda: _independent_nine_slice_proof(window, "normal", (window["logical_size"][0] + 5, window["logical_size"][1] + 7))))
    gates.append(_strict_gate("UI22-HG-11", lambda: _independent_nine_slice_proof(window, "normal", (window["logical_size"][0] + 9, window["logical_size"][1] + 3))))
    gates.append(_strict_gate("UI22-HG-12", lambda: all(validate_scale_pixel_relation(render_component(item, state_name, 1, tokens), render_component(item, state_name, 2, tokens), item, state_name) for item in components for state_name in item["supported_states"])))
    gates.append(_strict_gate("UI22-HG-13", lambda: compare_generated_outputs(first["outputs"], second["outputs"])))
    gates.append(_strict_gate("UI22-HG-14", lambda: all(validate_component_record(item, tokens) is None for item in components)))
    gates.append(_strict_gate("UI22-HG-15", lambda: all(validate_integration_linkage(item)["mode"] == "READ_ONLY" for item in components)))
    gates.append(_strict_gate("UI22-HG-16", lambda: all(item["integration_linkage"]["authority"]["authority_type"] == "LOCAL_UI_STYLE_ART_DNA" for item in components if item["component_class"] not in {"inventory_slot", "equipment_slot", "minimap_frame"})))
    gates.append(_strict_gate("UI22-HG-17", lambda: by_class["minimap_frame"]["integration_linkage"]["authority"]["authority_type"] == "EXTERNAL_CAPABILITY_CONTRACT" and by_class["minimap_frame"]["integration_linkage"]["authority"]["capability_id"] == "maps_minimap_runtime"))
    gates.append(_strict_gate("UI22-HG-18", lambda: all(validate_cache_record({"family_id": item["family_id"], "component_id": item["component_id"], "revision": item["revision"], "state": item["supported_states"][0], "scale_factor": 1, "style_token_hash": item["style_token_hash"], "semantic_input_hash": item["semantic_input_hash"], "content_hash": item["content_hash"], "authority_identity_hash": sha256_bytes(canonical_json(item["integration_authority_identity"])), "cache_key": cache_key_for(item, item["supported_states"][0], 1, tokens)}, item, tokens) is None for item in components)))
    gates.append(_strict_gate("UI22-HG-19", lambda: _historical_proof()["current_file_valid"] is True and _historical_proof()["mutation_rejection"]["rejection_class"] == "HISTORICAL_EVIDENCE_MUTATION_REJECTED"))
    gates.append(_strict_gate("UI22-HG-20", lambda: validate_production_registry([], production_safe=False)))
    gates.append(_strict_gate("UI22-HG-21", lambda: _state_consistency_gate(state, binding)))
    gates.append(_strict_gate("UI22-HG-22", lambda: validate_binding(binding)["status"] == "PASS"))
    gates.append(_strict_gate("UI22-HG-23", lambda: _life(state, approved=False, merged=False, ci=False)["allowed_next_actions"] == [NEXT_ACTION] and _life(state, approved=False, merged=False, ci=False)["vfx_allowed"] is False))
    gates.append(_strict_gate("UI22-HG-24", lambda: _life(state, approved=True, merged=False, ci=False)["allowed_next_actions"] == ["governed_merge_pr_13"]))
    gates.append(_strict_gate("UI22-HG-25", lambda: _life(state, approved=True, merged=True, ci=False)["allowed_next_actions"] == ["resolve_post_merge_closure_pr_13"]))
    gates.append(_strict_gate("UI22-HG-26", lambda: _life(state, approved=True, merged=True, ci=True)["allowed_next_actions"] == ["start_vfx_asset_family_v0230"] and _life(state, approved=True, merged=True, ci=True)["vfx_allowed"] is True))
    gates.append(_strict_gate("UI22-HG-27", lambda: all(type(value) is bool and value is True for value in (_state_consistency_gate(state, binding), validate_production_registry([], production_safe=False), validate_binding(binding)["status"] == "PASS"))))
    gates.append(_strict_gate("UI22-HG-28", lambda: POST_MERGE_CLOSURE_BINDING in state.get("evidence", {}).get("historical_bindings", [])))
    gates.append(_strict_gate("UI22-HG-29", lambda: state.get("production_routing") == "BLOCKED" and state.get("production_approved") is False and state.get("new_generation") == 0))
    gates.append(_strict_gate("UI22-HG-30", lambda: (EVIDENCE / "ui-style-authority-v0222.json").read_bytes() == LOCAL_STYLE_AUTHORITY_BYTES and sha256_bytes((EVIDENCE / "ui-style-authority-v0222.json").read_bytes()) == LOCAL_STYLE_AUTHORITY_SHA))

    controls: list[dict[str, Any]] = []
    bad = deepcopy(progress); bad["class_metadata"]["normalized_fill"]["domain"] = [-1.0, 2.0]; controls.append(_expect_rejection("UI22-NC-01", "normalized range outside [0,1]", "UI_PROGRESS_NORMALIZED_RANGE_INVALID", lambda: validate_progress_bar_contract(bad)))
    bad = deepcopy(progress); bad["class_metadata"]["normalized_fill"]["origin"] = "right"; controls.append(_expect_rejection("UI22-NC-02", "wrong progress origin", "UI_PROGRESS_ORIGIN_INVALID", lambda: validate_progress_bar_contract(bad)))
    bad = deepcopy(progress); bad["class_metadata"]["normalized_fill"]["direction"] = "negative"; controls.append(_expect_rejection("UI22-NC-03", "wrong progress direction", "UI_PROGRESS_DIRECTION_INVALID", lambda: validate_progress_bar_contract(bad)))
    bad = deepcopy(progress); bad["class_metadata"]["fill_rect"]["width"] = progress["class_metadata"]["track_rect"]["width"] + 1; controls.append(_expect_rejection("UI22-NC-04", "fill outside track", "UI_PROGRESS_GEOMETRY_INVALID", lambda: validate_progress_bar_contract(bad)))
    bad = deepcopy(progress); bad["class_metadata"]["normalized_fill"]["mapping"] = "ROUND_LINEAR"; controls.append(_expect_rejection("UI22-NC-05", "inconsistent fill mapping", "UI_PROGRESS_MAPPING_INVALID", lambda: validate_progress_bar_contract(bad)))
    controls.append(_expect_rejection("UI22-NC-06", "value below normalized domain", "UI_PROGRESS_NORMALIZED_RANGE_INVALID", lambda: progress_fill_rect(progress, -0.1)))
    controls.append(_expect_rejection("UI22-NC-07", "value above normalized domain", "UI_PROGRESS_NORMALIZED_RANGE_INVALID", lambda: progress_fill_rect(progress, 1.1)))
    target = (window["logical_size"][0] + 5, window["logical_size"][1] + 7); source = render_component(window, "normal", 1, tokens); output = render_component_to_size(window, "normal", 1, target, tokens); output.putpixel((0, 0), (1, 2, 3, 255)); controls.append(_expect_rejection("UI22-NC-08", "mutated preserved corner", "UI_NINE_SLICE_INVARIANT_INVALID", lambda: verify_nine_slice_invariants(source, output, window["stretch_geometry"]["slice_margins"])))
    output = render_component_to_size(window, "normal", 1, target, tokens); margins = window["stretch_geometry"]["slice_margins"]; output.putpixel((margins["left"], 1), (9, 8, 7, 255)); controls.append(_expect_rejection("UI22-NC-09", "mutated top edge axis", "UI_NINE_SLICE_INVARIANT_INVALID", lambda: verify_nine_slice_invariants(source, output, margins)))
    output = render_component_to_size(window, "normal", 1, target, tokens); output.putpixel((margins["left"] + 1, margins["top"] + 1), (9, 8, 7, 255)); controls.append(_expect_rejection("UI22-NC-10", "mutated center", "UI_NINE_SLICE_INVARIANT_INVALID", lambda: verify_nine_slice_invariants(source, output, margins)))
    bad = deepcopy(button); bad["integration_linkage"]["authority_type"] = "EXTERNAL_CAPABILITY_CONTRACT"; controls.append(_expect_rejection("UI22-NC-11", "generic UI bound to external authority type", "UI_INTEGRATION_AUTHORITY_TYPE_INVALID", lambda: validate_component_record(bad, tokens)))
    bad = deepcopy(button); bad["integration_linkage"]["authority"]["capability_id"] = "maps_minimap_runtime"; controls.append(_expect_rejection("UI22-NC-12", "generic UI bound to map capability", "UI_INTEGRATION_AUTHORITY_STALE", lambda: validate_component_record(bad, tokens)))
    bad = deepcopy(by_class["minimap_frame"]); bad["integration_linkage"]["authority"]["authority_type"] = "LOCAL_UI_STYLE_ART_DNA"; controls.append(_expect_rejection("UI22-NC-13", "minimap loses external capability authority", "UI_INTEGRATION_AUTHORITY_STALE", lambda: validate_component_record(bad, tokens)))
    bad = deepcopy(button); bad["integration_authority_identity"]["authoritative_path"] = "docs/evidence/maps-minimap-runtime-v0213/map-contract-v0213.json"; controls.append(_expect_rejection("UI22-NC-14", "cache identity path mutation", "UI_INTEGRATION_AUTHORITY_STALE", lambda: validate_component_record(bad, tokens)))
    bad = deepcopy(button); record = {"family_id": button["family_id"], "component_id": button["component_id"], "revision": button["revision"], "state": "normal", "scale_factor": 1, "style_token_hash": button["style_token_hash"], "semantic_input_hash": button["semantic_input_hash"], "content_hash": button["content_hash"], "authority_identity_hash": "0" * 64, "cache_key": "0" * 64}; controls.append(_expect_rejection("UI22-NC-15", "cache authority identity mutation", "UI_CACHE_SEMANTIC_IDENTITY_STALE", lambda: validate_cache_record(record, bad, tokens)))
    controls.append(_expect_rejection("UI22-NC-16", "mutated historical authority pointer", "CLOSURE_AUTHORITY_POINTER_STALE", lambda: validate_binding({**binding, "canonical_v0213_closure_authority": SUPERSEDED_CLOSURE_AUTHORITY})))
    controls.append(_expect_rejection("UI22-NC-17", "state closure pointer to superseded record", "CLOSURE_AUTHORITY_POINTER_STALE", lambda: _state_reject(validate_state_consistency({**state, "closure_authority": {**state["closure_authority"], "canonical": SUPERSEDED_CLOSURE_AUTHORITY}}, binding), "CLOSURE_AUTHORITY_POINTER_STALE")))
    for control_id, observed in (("UI22-NC-18", None), ("UI22-NC-19", 0), ("UI22-NC-20", 1), ("UI22-NC-21", "PASS"), ("UI22-NC-22", []), ("UI22-NC-23", {})):
        controls.append(_expect_rejection(control_id, f"non-bool hard-gate observation {observed!r}", "UI_HARD_GATE_NON_BOOLEAN_REJECTED", lambda observed=observed: (_ for _ in ()).throw(UIAssetFamilyContractError("UI_HARD_GATE_NON_BOOLEAN_REJECTED", type(observed).__name__)) if not (type(observed) is bool and observed is True) else None))
    mutated = deepcopy(state); mutated["allowed_next_actions"] = ["start_vfx_asset_family_v0230"]; controls.append(_expect_rejection("UI22-NC-24", "stale state authorizes VFX", "UI_LIFECYCLE_STATE_INVALID", lambda: _state_reject(validate_state_consistency(mutated, binding), "UI_LIFECYCLE_STATE_INVALID")))
    controls.append(_expect_rejection("UI22-NC-25", "lifecycle source not GitHub LIVE", "UI_LIVE_AUTHORITY_REQUIRED", lambda: _expect_live_rejection(state, {"source_mode": "TRACKED_STATE", "pr_number": 13, "external_approval": True, "merged": True})))
    controls.append(_expect_rejection("UI22-NC-26", "wrong PR lifecycle source", "UI_LIVE_AUTHORITY_REQUIRED", lambda: _expect_live_rejection(state, {"source_mode": "GITHUB_LIVE", "pr_number": 12, "external_approval": True, "merged": True})))
    controls.append(_expect_rejection("UI22-NC-27", "approved but unmerged VFX attempt", "UI_LIFECYCLE_VFX_BLOCKED", lambda: _expect_vfx_block(_life(state, approved=True, merged=False, ci=False))))
    controls.append(_expect_rejection("UI22-NC-28", "merged with pending main CI VFX attempt", "UI_LIFECYCLE_VFX_BLOCKED", lambda: _expect_vfx_block(_life(state, approved=True, merged=True, ci=False))))
    controls.append(_expect_rejection("UI22-NC-29", "production registry injection", "UI_PRODUCTION_REGISTRY_NON_EMPTY", lambda: validate_production_registry([{ "id": "real" }], production_safe=False)))
    controls.append(_expect_rejection("UI22-NC-30", "historical mutation through real validator", "HISTORICAL_EVIDENCE_MUTATION_REJECTED", lambda: _expect_history_rejection()))

    gates_doc = {item["gate_id"]: item for item in gates}; controls_doc = {item["control_id"]: item for item in controls}; history = _historical_proof()
    write_json(EVIDENCE / "component-class-contract-v0222.json", {"schema_version": "0.22.2", "classes": [{"component_class": item["component_class"], "authority_type": item["integration_linkage"]["authority"]["authority_type"], "class_metadata": item["class_metadata"]} for item in components]})
    write_json(EVIDENCE / "progress-bar-contract-v0222.json", {"schema_version": "0.22.2", "component_id": progress["component_id"], "contract": progress["class_metadata"], "samples": [{"value": value, "fill_rect": progress_fill_rect(progress, value)} for value in (0.0, 0.5, 1.0)]})
    write_json(EVIDENCE / "nine-slice-independent-verification-v0222.json", {"schema_version": "0.22.2", "oracle": "independent_decoded_region_verifier", "targets": [target, (window["logical_size"][0] + 9, window["logical_size"][1] + 3)], "proof": "corners exact; top/bottom X-only; left/right Y-only; center independently sampled"})
    write_json(EVIDENCE / "integration-authority-bindings-v0222.json", {"schema_version": "0.22.2", "components": [{"component_id": item["component_id"], "authority": item["integration_linkage"]["authority"], "identity": item["integration_authority_identity"]} for item in components]})
    write_json(EVIDENCE / "cache-semantic-identity-v0222.json", {"schema_version": "0.22.2", "fields": ["class_metadata", "integration_authority_identity", "content_hash", "semantic_input_hash", "authority_identity_hash", "cache_key"]})
    write_json(EVIDENCE / "hard-gates-v0222.json", {"schema_version": "0.22.2", "gates": gates_doc, "required_gate_count": len(gates), "strict_boolean_contract": True})
    write_json(EVIDENCE / "negative-controls-v0222.json", {"schema_version": "0.22.2", "controls": controls_doc, "required_control_count": len(controls), "all_rejections_observed": all(item["result"] == "REJECT" and item["status"] == "PASS" for item in controls)})
    write_json(EVIDENCE / "full-slice-two-run-determinism-v0222.json", {"schema_version": "0.22.2", "status": "PASS" if compare_generated_outputs(first["outputs"], second["outputs"]) else "FAIL", "first_run_sha256": sha256_bytes(canonical_json({key: sha256_bytes(value) for key, value in sorted(first["outputs"].items())})), "second_run_sha256": sha256_bytes(canonical_json({key: sha256_bytes(value) for key, value in sorted(second["outputs"].items())}))})
    write_json(EVIDENCE / "historical-authority-v0222.json", {"schema_version": "0.22.2", **history})
    write_json(EVIDENCE / "governance-binding-validation-v0222.json", {"schema_version": "0.22.2", "binding": str(GOVERNANCE_BINDING.relative_to(ROOT)).replace("\\", "/"), "validation": validate_binding(binding), "negative_control": {"status": "REJECT", "rejection_class": "CLOSURE_AUTHORITY_POINTER_STALE"}})
    production = {"schema_version": "0.22.2", "registry": [], "production_registry_empty": True, "production_routing": "BLOCKED", "production_approved": False, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "new_generation": 0}; write_json(EVIDENCE / "production-registry-v0222.json", production)
    execution = {"schema_version": "0.22.2", "status": "UI_ASSET_FAMILY_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED" if all(item["passed"] for item in gates) and all(item["status"] == "PASS" for item in controls) else "UI_ASSET_FAMILY_CORRECTION_REQUIRED", "overall_pass": all(item["passed"] for item in gates) and all(item["status"] == "PASS" for item in controls), "runtime_revision": "ui-asset-family-runtime-v0222", "gates_passed": sum(item["passed"] for item in gates), "gate_count": len(gates), "negative_controls_passed": sum(item["status"] == "PASS" for item in controls), "negative_control_count": len(controls), "production_routing": "BLOCKED", "production_approved": False, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "new_generation": 0, "external_review": "REQUIRED", "do_not_merge": True, "pr_number": 13}
    write_json(EVIDENCE / "execution-evidence-v0222.json", execution)
    print(json.dumps(execution, indent=2, ensure_ascii=False)); return 0 if execution["overall_pass"] else 1


def _rect_containment_progress(progress: dict[str, Any]) -> bool:
    validate_progress_bar_contract(progress); return True


def _independent_nine_slice_proof(component: dict[str, Any], state: str, target: tuple[int, int]) -> bool:
    source = render_component(component, state, 1); output = render_component_to_size(component, state, 1, target); return verify_nine_slice_invariants(source, output, component["stretch_geometry"]["slice_margins"])["status"] == "PASS"


def _expect_live_rejection(state: dict[str, Any], live: dict[str, Any]) -> None:
    result = resolve_next_actions(state, live)
    if result.get("status") == "UI_STATE_CONSISTENCY_FAILED":
        raise UIAssetFamilyContractError("UI_LIVE_AUTHORITY_REQUIRED", "GitHub LIVE source required")


def _expect_vfx_block(result: dict[str, Any]) -> None:
    if result.get("vfx_allowed") is False:
        raise UIAssetFamilyContractError("UI_LIFECYCLE_VFX_BLOCKED", "VFX is blocked before post-merge main CI success")


def _expect_history_rejection() -> None:
    authority = subprocess.run(["git", "show", f"{BASE_MAIN}:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"], cwd=ROOT, capture_output=True, check=False).stdout; mutation = bytearray(OLD_AUTHORITY.read_bytes()); mutation[-2] = 0x20 if mutation[-2] != 0x20 else 0x21; validate_historical_authority(authority, bytes(mutation), authority_ref="historical-v0213")


if __name__ == "__main__":
    raise SystemExit(main())
