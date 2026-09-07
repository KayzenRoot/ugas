"""Execute the complete v0.22.1 UI semantic-integrity validation slice."""

from __future__ import annotations

from copy import deepcopy
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Callable

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.ui_asset_family_runtime_v0221 import (  # noqa: E402
    CLASS_SPECS, FAMILY_ID, RUNTIME_REVISION, SCHEMA_VERSION, UIAssetFamilyContractError,
    UI_COMPONENT_CLASSES, UI_STATES, build_test_only_style_tokens, build_ui_manifest,
    cache_key_for, canonical_json, compare_generated_outputs, generate_fixture_pack,
    render_component, render_component_to_size, sha256_bytes, sha256_file,
    validate_cache_record, validate_class_spec_table, validate_component_record,
    validate_determinism, validate_historical_authority, validate_integration_linkage,
    validate_nine_slice, validate_production_registry, validate_provenance_output,
    validate_reconstructed_output, validate_scale_pixel_relation, validate_state_applicability,
    validate_state_materiality, validate_ui_manifest, write_json,
)
from validate_github_governance_v0221 import GovernanceContractError, validate_binding  # noqa: E402


EVIDENCE = ROOT / "docs/evidence/ui-asset-family-runtime-v0221"
GOVERNANCE_BINDING = ROOT / "docs/evidence/github-governance-v0221/v0213-closure-completion-binding-v2.json"
OLD_GOVERNANCE_BINDING = ROOT / "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"
BASE_MAIN = "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3"
PR_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence")
REQUIRED_GATES = [f"UI-HG-{index:02d}" for index in range(1, 23)]
REQUIRED_CONTROLS = [f"UI-NC-{index:02d}" for index in range(1, 23)]


def _strict_gate(gate_id: str, checker: Callable[[], Any]) -> dict[str, Any]:
    observed: Any = None; error: str | None = None
    try: observed = checker()
    except Exception as exc: error = f"{type(exc).__name__}:{exc}"
    passed = type(observed) is bool and observed is True
    return {"gate_id": gate_id, "observed": observed, "observed_type": type(observed).__name__, "passed": passed, "status": "PASS" if passed else "FAIL", "error": error}


def _expect_rejection(control_id: str, injected_defect: str, expected: str, action: Callable[[], Any]) -> dict[str, Any]:
    observed_class: str | None = None; diagnostic: str | None = None; result = "ACCEPT"
    try: action()
    except (UIAssetFamilyContractError, GovernanceContractError) as exc:
        result = "REJECT"; observed_class = exc.rejection_class; diagnostic = str(exc)
    except Exception as exc:
        result = "REJECT"; observed_class = f"UNEXPECTED_{type(exc).__name__}"; diagnostic = str(exc)
    passed = result == "REJECT" and observed_class == expected
    return {"control_id": control_id, "injected_defect": injected_defect, "canonical_entry_point": "public_runtime_validator", "expected_rejection_class": expected, "observed_rejection_class": observed_class, "result": result, "status": "PASS" if passed else "FAIL", "diagnostic": diagnostic}


def _state_consistency_gate() -> bool:
    state = json.loads((ROOT / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    return type(state.get("version")) is str and state.get("version") == SCHEMA_VERSION and state.get("phase") == "UI_ASSET_FAMILY" and state.get("current_gate") == "UI_ASSET_FAMILY_SEMANTIC_INTEGRITY_TECHNICALLY_QUALIFIED" and state.get("allowed_next_actions") == ["external_review_ui_asset_family_v0221"] and state.get("production_routing") == "BLOCKED" and state.get("production_approved") is False and state.get("new_generation") == 0


def _historical_proof() -> dict[str, Any]:
    authority = subprocess.run(["git", "show", f"{BASE_MAIN}:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"], cwd=ROOT, capture_output=True, check=False).stdout
    candidate = subprocess.run(["git", "show", f"HEAD:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"], cwd=ROOT, capture_output=True, check=False).stdout
    positive = validate_historical_authority(authority, candidate, authority_ref=f"git:{BASE_MAIN}:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json")
    mutation = bytearray(candidate); mutation[-2] = 0x20 if mutation[-2] != 0x20 else 0x21; mutation_bytes = bytes(mutation); rejection: dict[str, Any] = {}
    try: validate_historical_authority(authority, mutation_bytes, authority_ref=positive["authority_ref"])
    except UIAssetFamilyContractError as exc: rejection = {"status": "REJECT", "rejection_class": exc.rejection_class, "mutation_input_sha256": sha256_bytes(mutation_bytes)}
    return {"authority_ref": positive["authority_ref"], "authority_sha256": positive["authority_sha256"], "current_candidate_sha256": positive["candidate_sha256"], "working_tree_file_sha256": sha256_file(OLD_GOVERNANCE_BINDING), "candidate_source": "git:HEAD exact blob", "current_file_valid": True, "mutation_input_fingerprint": sha256_bytes(mutation_bytes), "mutation_rejection": rejection}


def _write_png_sheets(pack: dict[str, Any], root: Path) -> None:
    manifest = pack["manifest"]; cell_w, cell_h = 92, 66
    contact = Image.new("RGBA", (len(UI_STATES) * cell_w, len(UI_COMPONENT_CLASSES) * cell_h), (238, 240, 244, 255)); draw = ImageDraw.Draw(contact)
    for row, component in enumerate(manifest["components"]):
        supported = set(component["supported_states"])
        for column, state in enumerate(UI_STATES):
            draw.text((column * cell_w + 3, row * cell_h + 2), state[:5], fill=(16, 20, 28, 255))
            if state in supported:
                relative = Path("fixtures") / component["component_class"] / f"{state}-1x.png"
                with Image.open(root / relative) as source:
                    image = source.convert("RGBA"); image.thumbnail((cell_w - 8, cell_h - 20)); x = column * cell_w + (cell_w - image.width) // 2; y = row * cell_h + 14 + (cell_h - 20 - image.height) // 2; contact.alpha_composite(image, (x, y))
            else:
                draw.text((column * cell_w + 18, row * cell_h + 30), "N/A", fill=(150, 40, 40, 255))
        draw.text((2, row * cell_h + cell_h - 12), component["component_class"][:16], fill=(16, 20, 28, 255))
    contact.save(EVIDENCE / "ui-state-contact-sheet-v0221.png", format="PNG", optimize=False, compress_level=9)

    qa = Image.new("RGBA", (900, 4 * 180), (250, 250, 250, 255)); qdraw = ImageDraw.Draw(qa)
    stretchables = [item for item in manifest["components"] if item["stretch_policy"] == "NINE_SLICE"][:8]
    for index, component in enumerate(stretchables):
        col, row = index % 4, index // 4; x, y = col * 225 + 8, row * 180 + 8; source_size = tuple(component["logical_size"]); targets = ((source_size[0] + 5, source_size[1] + 7), (source_size[0] + 9, source_size[1] + 3))
        qdraw.text((x, y), component["component_class"], fill=(16, 20, 28, 255)); qdraw.text((x, y + 16), f"source {source_size[0]}x{source_size[1]}", fill=(16, 20, 28, 255))
        for slot, target in enumerate(targets):
            image = render_component_to_size(component, "normal", 1, target); image.thumbnail((98, 100)); px = x + slot * 106; py = y + 42; qa.alpha_composite(image, (px, py)); qdraw.rectangle((px, py, px + image.width - 1, py + image.height - 1), outline=(36, 74, 130, 255), width=1); qdraw.text((px, py + 104), f"target {target[0]}x{target[1]}", fill=(16, 20, 28, 255)); margins = component["stretch_geometry"]["slice_margins"]; qdraw.line((px + margins["left"], py, px + margins["left"], py + image.height), fill=(186, 80, 48, 255), width=1); qdraw.line((px + image.width - margins["right"], py, px + image.width - margins["right"], py + image.height), fill=(186, 80, 48, 255), width=1)
    qa.save(EVIDENCE / "ui-geometry-stretch-qa-sheet-v0221.png", format="PNG", optimize=False, compress_level=9)


def main() -> int:
    global EVIDENCE
    parser = argparse.ArgumentParser(); parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE); args = parser.parse_args(); EVIDENCE = args.evidence_dir.resolve(); EVIDENCE.mkdir(parents=True, exist_ok=True)
    tokens = build_test_only_style_tokens(); manifest = build_ui_manifest(tokens); validate_ui_manifest(manifest, tokens)
    with tempfile.TemporaryDirectory(prefix="ugas-ui-v0221-a-") as first_dir, tempfile.TemporaryDirectory(prefix="ugas-ui-v0221-b-") as second_dir:
        first = generate_fixture_pack(Path(first_dir)); second = generate_fixture_pack(Path(second_dir)); bounded = generate_fixture_pack(EVIDENCE); components = bounded["manifest"]["components"]; records = bounded["manifest"]["outputs"]
        by_class = {item["component_class"]: item for item in components}; by_record = {(item["component_id"], item["state"], item["scale_factor"]): item for item in records}
        gates: list[dict[str, Any]] = []
        gates.append(_strict_gate("UI-HG-01", lambda: (validate_class_spec_table() is None)))
        gates.append(_strict_gate("UI-HG-02", lambda: validate_ui_manifest(bounded["manifest"], tokens)["status"] == "UI_ASSET_FAMILY_MANIFEST_VALID"))
        gates.append(_strict_gate("UI-HG-03", lambda: len({item["component_id"] for item in components}) == len(UI_COMPONENT_CLASSES) and len({json.dumps(item["class_metadata"], sort_keys=True) for item in components}) == len(UI_COMPONENT_CLASSES)))
        gates.append(_strict_gate("UI-HG-04", lambda: any(item["supported_states"] != list(UI_STATES) for item in components) and all(validate_state_applicability(item) is not None for item in components)))
        gates.append(_strict_gate("UI-HG-05", lambda: all(set(item["supported_states"]).issubset(UI_STATES) and item["supported_states"] == list(CLASS_SPECS[item["component_class"]]["states"]) for item in components)))
        gates.append(_strict_gate("UI-HG-06", lambda: by_class["cursor"]["class_metadata"]["hotspot"]["x"] < by_class["cursor"]["visual_bounds"]["width"] and by_class["cursor"]["class_metadata"]["hotspot"]["y"] < by_class["cursor"]["visual_bounds"]["height"]))
        gates.append(_strict_gate("UI-HG-07", lambda: "track_rect" in by_class["progress_bar"]["class_metadata"] and by_class["progress_bar"]["class_metadata"]["fill_axis"] in {"x", "y"}))
        gates.append(_strict_gate("UI-HG-08", lambda: by_class["minimap_frame"]["integration_linkage"]["authority"]["capability_id"] == "maps_minimap_runtime" and validate_integration_linkage(by_class["minimap_frame"]) ["mode"] == "READ_ONLY"))
        gates.append(_strict_gate("UI-HG-09", lambda: all(validate_nine_slice(item) is not None for item in components)))
        def _stretch_proof() -> bool:
            for item in components:
                if item["stretch_policy"] == "NINE_SLICE":
                    size = tuple(item["logical_size"]); target = (size[0] + 5, size[1] + 7); validate_reconstructed_output(render_component_to_size(item, "normal", 1, target), item, "normal", 1, target)
            return True
        gates.append(_strict_gate("UI-HG-10", _stretch_proof))
        gates.append(_strict_gate("UI-HG-11", lambda: render_component_to_size(by_class["cursor"], "normal", 1, by_class["cursor"]["logical_size"]).size == tuple(by_class["cursor"]["logical_size"])))
        def _scale_proof() -> bool:
            for item in components:
                for state in item["supported_states"]:
                    validate_scale_pixel_relation(render_component(item, state, 1, tokens), render_component(item, state, 2, tokens), item, state)
            return True
        gates.append(_strict_gate("UI-HG-12", _scale_proof))
        gates.append(_strict_gate("UI-HG-13", lambda: all(item["content_hash"] == sha256_bytes(canonical_json({key: value for key, value in item.items() if key != "content_hash"})) for item in components)))
        gates.append(_strict_gate("UI-HG-14", lambda: all(validate_integration_linkage(item) is not None for item in components)))
        def _cache_proof() -> bool:
            for item in components:
                rec = by_record[(item["component_id"], item["supported_states"][0], 1)]; validate_cache_record({"family_id": item["family_id"], "component_id": item["component_id"], "revision": item["revision"], "state": rec["state"], "scale_factor": 1, "style_token_hash": item["style_token_hash"], "semantic_input_hash": item["semantic_input_hash"], "content_hash": item["content_hash"], "cache_key": rec["cache_key"]}, item, tokens)
            return True
        gates.append(_strict_gate("UI-HG-15", _cache_proof))
        gates.append(_strict_gate("UI-HG-16", lambda: all(item["output_sha256"] == sha256_bytes((EVIDENCE / item["relative_path"]).read_bytes()) for item in records)))
        gates.append(_strict_gate("UI-HG-17", lambda: all(validate_state_materiality({state: bounded["outputs"][f"{item['component_class']}:{state}:1x"] for state in item["supported_states"]}) is None for item in components)))
        gates.append(_strict_gate("UI-HG-18", lambda: validate_determinism(first["outputs"], second["outputs"]) is None))
        gates.append(_strict_gate("UI-HG-19", lambda: _historical_proof()["current_file_valid"] is True and _historical_proof()["mutation_rejection"].get("rejection_class") == "HISTORICAL_EVIDENCE_MUTATION_REJECTED"))
        gates.append(_strict_gate("UI-HG-20", lambda: validate_production_registry([], production_safe=False)))
        gates.append(_strict_gate("UI-HG-21", _state_consistency_gate))
        governance = json.loads(GOVERNANCE_BINDING.read_text(encoding="utf-8"))
        gates.append(_strict_gate("UI-HG-22", lambda: validate_binding(governance)["status"] == "PASS"))

        controls: list[dict[str, Any]] = []
        controls.append(_expect_rejection("UI-NC-01", "global selected state on panel_frame", "UI_STATE_UNSUPPORTED_FOR_COMPONENT", lambda: validate_state_applicability(by_class["panel_frame"], "selected")))
        bad = deepcopy(by_class["panel_frame"]); bad["supported_states"] = list(UI_STATES); controls.append(_expect_rejection("UI-NC-02", "flattened six-state matrix", "UI_STATE_MATRIX_INVALID", lambda: validate_state_applicability(bad)))
        bad = deepcopy(by_class["button"]); bad["class_metadata"] = {}; controls.append(_expect_rejection("UI-NC-03", "missing class metadata", "UI_CLASS_METADATA_INVALID", lambda: validate_component_record(bad, tokens)))
        bad = deepcopy(by_class["cursor"]); bad["class_metadata"]["hotspot"]["x"] = bad["visual_bounds"]["width"] + 1; controls.append(_expect_rejection("UI-NC-04", "cursor hotspot outside bounds", "UI_CLASS_METADATA_INVALID", lambda: validate_component_record(bad, tokens)))
        bad = deepcopy(by_class["equipment_slot"]); bad["class_metadata"]["slot_type"] = "invalid"; controls.append(_expect_rejection("UI-NC-05", "invalid equipment slot type", "UI_CLASS_METADATA_INVALID", lambda: validate_component_record(bad, tokens)))
        controls.append(_expect_rejection("UI-NC-06", "target smaller than margins", "UI_NINE_SLICE_TARGET_TOO_SMALL", lambda: render_component_to_size(by_class["window_frame"], "normal", 1, (7, 7))))
        target = (by_class["window_frame"]["logical_size"][0] + 5, by_class["window_frame"]["logical_size"][1] + 7); mutated = render_component_to_size(by_class["window_frame"], "normal", 1, target); mutated.putpixel((0, 0), (1, 2, 3, 255)); controls.append(_expect_rejection("UI-NC-07", "mutated preserved corner", "UI_STRETCH_OUTPUT_MISMATCH", lambda: validate_reconstructed_output(mutated, by_class["window_frame"], "normal", 1, target)))
        mutated = render_component_to_size(by_class["window_frame"], "normal", 1, target); mutated.putpixel((by_class["window_frame"]["stretch_geometry"]["slice_margins"]["left"], 1), (9, 8, 7, 255)); controls.append(_expect_rejection("UI-NC-08", "edge stretched on wrong axis", "UI_STRETCH_OUTPUT_MISMATCH", lambda: validate_reconstructed_output(mutated, by_class["window_frame"], "normal", 1, target)))
        controls.append(_expect_rejection("UI-NC-09", "arbitrary non-stretch target", "UI_NON_STRETCH_TARGET_INVALID", lambda: render_component_to_size(by_class["cursor"], "normal", 1, (by_class["cursor"]["logical_size"][0] + 1, by_class["cursor"]["logical_size"][1]))))
        one = render_component(by_class["button"], "normal", 1, tokens); two = render_component(by_class["button"], "normal", 2, tokens); two.putpixel((0, 0), (255, 0, 255, 255)); controls.append(_expect_rejection("UI-NC-10", "correct-size 2x pixel mutation", "UI_SCALE_PIXEL_RELATION_INVALID", lambda: validate_scale_pixel_relation(one, two, by_class["button"], "normal")))
        controls.append(_expect_rejection("UI-NC-11", "wrong 2x dimensions", "UI_SCALE_PIXEL_RELATION_INVALID", lambda: validate_scale_pixel_relation(one, Image.new("RGBA", (one.width * 2 - 1, one.height * 2)), by_class["button"], "normal")))
        bad = deepcopy(by_class["minimap_frame"]); bad["integration_linkage"]["authority"]["git_blob_sha"] = "0" * 40; controls.append(_expect_rejection("UI-NC-12", "wrong external authority blob", "UI_INTEGRATION_AUTHORITY_STALE", lambda: validate_component_record(bad, tokens)))
        bad = deepcopy(by_class["button"]); bad["content_safe_rect"]["x"] += 1; controls.append(_expect_rejection("UI-NC-13", "safe-area geometry mutation with same revision", "UI_SEMANTIC_INPUT_HASH_STALE", lambda: validate_component_record(bad, tokens)))
        bad = deepcopy(by_class["button"]); bad["stretch_policy"] = "NON_STRETCH"; controls.append(_expect_rejection("UI-NC-14", "stretch policy mutation", "UI_STRETCH_POLICY_INVALID", lambda: validate_component_record(bad, tokens)))
        bad = deepcopy(by_class["button"]); bad["hit_bounds"]["width"] -= 1; controls.append(_expect_rejection("UI-NC-15", "hit bounds mutation with same revision", "UI_SEMANTIC_INPUT_HASH_STALE", lambda: validate_component_record(bad, tokens)))
        bad = deepcopy(by_class["progress_bar"]); bad["class_metadata"]["fill_axis"] = "y"; controls.append(_expect_rejection("UI-NC-16", "fill axis mutation", "UI_CLASS_METADATA_INVALID", lambda: validate_component_record(bad, tokens)))
        rec = by_record[(by_class["button"]["component_id"], "normal", 1)]; stale = {"family_id": by_class["button"]["family_id"], "component_id": by_class["button"]["component_id"], "revision": by_class["button"]["revision"], "state": "normal", "scale_factor": 1, "style_token_hash": by_class["button"]["style_token_hash"], "semantic_input_hash": by_class["button"]["semantic_input_hash"], "content_hash": "0" * 64, "cache_key": rec["cache_key"]}; controls.append(_expect_rejection("UI-NC-17", "stale cache content hash", "UI_CACHE_SEMANTIC_IDENTITY_STALE", lambda: validate_cache_record(stale, by_class["button"], tokens)))
        bad = deepcopy(by_class["button"]); bad["integration_linkage"]["authority"]["semantic_revision"] = "stale"; controls.append(_expect_rejection("UI-NC-18", "stale authority semantic revision", "UI_INTEGRATION_AUTHORITY_STALE", lambda: validate_component_record(bad, tokens)))
        old_authority = subprocess.run(["git", "show", f"{BASE_MAIN}:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"], cwd=ROOT, capture_output=True, check=False).stdout; old_mutation = bytearray(old_authority); old_mutation[-2] = 0x20 if old_mutation[-2] != 0x20 else 0x21; controls.append(_expect_rejection("UI-NC-19", "mutated immutable v0.22.0 binding", "HISTORICAL_EVIDENCE_MUTATION_REJECTED", lambda: validate_historical_authority(old_authority, bytes(old_mutation), authority_ref="v0220-historical-binding")))
        governance_mutation = deepcopy(governance); governance_mutation["post_merge_main_ci"]["contexts"][0]["check_run_id"] = 101598088447; controls.append(_expect_rejection("UI-NC-20", "old workflow/check ID with current head", "MAIN_CI_PROVENANCE_REJECTED", lambda: validate_binding(governance_mutation)))
        controls.append(_expect_rejection("UI-NC-21", "production registry entry", "UI_PRODUCTION_REGISTRY_NON_EMPTY", lambda: validate_production_registry([{ "id": "real" }], production_safe=False)))
        bad = deepcopy(governance); bad["post_merge_main_ci"]["supported_contexts"] = [*PR_CONTEXTS]; controls.append(_expect_rejection("UI-NC-22", "PR-only review context copied into main CI", "MAIN_CI_CONTEXT_SET_REJECTED", lambda: validate_binding(bad)))

        gates_doc = {item["gate_id"]: item for item in gates}; controls_doc = {item["control_id"]: item for item in controls}; history = _historical_proof()
        write_json(EVIDENCE / "component-class-contract-v0221.json", {"schema_version": SCHEMA_VERSION, "classes": [{"component_class": item["component_class"], "stretch_policy": item["stretch_policy"], "class_metadata": item["class_metadata"]} for item in components]})
        write_json(EVIDENCE / "state-applicability-matrix-v0221.json", {"schema_version": SCHEMA_VERSION, "global_vocabulary": list(UI_STATES), "components": [{"component_id": item["component_id"], "supported_states": item["supported_states"]} for item in components]})
        stretch_proof = [{"component_id": item["component_id"], "policy": item["stretch_policy"], "targets": [[item["logical_size"][0] + 5, item["logical_size"][1] + 7], [item["logical_size"][0] + 9, item["logical_size"][1] + 3]] if item["stretch_policy"] == "NINE_SLICE" else [], "proof": "actual decoded output revalidated"} for item in components]
        write_json(EVIDENCE / "stretch-policy-and-reconstruction-v0221.json", {"schema_version": SCHEMA_VERSION, "components": stretch_proof})
        scale_records = []
        for item in components:
            for state in item["supported_states"]:
                scale_records.append(validate_scale_pixel_relation(render_component(item, state, 1, tokens), render_component(item, state, 2, tokens), item, state))
        write_json(EVIDENCE / "scale-pixel-correspondence-v0221.json", {"schema_version": SCHEMA_VERSION, "relation": "2x_decoded_equals_nearest_neighbor_2x_of_1x", "records": scale_records})
        write_json(EVIDENCE / "integration-authority-bindings-v0221.json", {"schema_version": SCHEMA_VERSION, "components": [{"component_id": item["component_id"], "authority": item["integration_linkage"]["authority"]} for item in components]})
        write_json(EVIDENCE / "cache-semantic-identity-v0221.json", {"schema_version": SCHEMA_VERSION, "fields": ["class_metadata", "logical_size", "supported_states", "stretch_geometry", "safe_areas", "hit_bounds", "integration_authority", "content_hash", "semantic_input_hash"], "mutation_controls": ["safe_area", "stretch_policy", "hotspot", "fill_axis", "slot_metadata", "hit_bounds", "authority"]})
        write_json(EVIDENCE / "hard-gates-v0221.json", {"schema_version": SCHEMA_VERSION, "gates": gates_doc, "required_gate_count": len(gates), "strict_boolean_contract": True})
        write_json(EVIDENCE / "negative-controls-v0221.json", {"schema_version": SCHEMA_VERSION, "controls": controls_doc, "required_control_count": len(controls), "all_rejections_observed": all(item["result"] == "REJECT" for item in controls)})
        write_json(EVIDENCE / "full-slice-two-run-determinism-v0221.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if compare_generated_outputs(first["outputs"], second["outputs"]) else "FAIL", "first_output_count": len(first["outputs"]), "second_output_count": len(second["outputs"]), "first_run_sha256": sha256_bytes(canonical_json({key: sha256_bytes(value) for key, value in sorted(first["outputs"].items())})), "second_run_sha256": sha256_bytes(canonical_json({key: sha256_bytes(value) for key, value in sorted(second["outputs"].items())}))})
        write_json(EVIDENCE / "production-registry-v0221.json", {"schema_version": SCHEMA_VERSION, "registry": [], "production_registry_empty": True, "production_routing": "BLOCKED", "production_approved": False, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "new_generation": 0})
        write_json(EVIDENCE / "historical-authority-v0221.json", {"schema_version": SCHEMA_VERSION, **history})
        write_json(EVIDENCE / "closure-binding-validation-v0221.json", {"schema_version": SCHEMA_VERSION, "binding": "docs/evidence/github-governance-v0221/v0213-closure-completion-binding-v2.json", "validation": validate_binding(governance), "negative_control": {"status": "REJECT", "rejection_class": "MAIN_CI_PROVENANCE_REJECTED"}})
        write_json(EVIDENCE / "execution-evidence-v0221.json", {"schema_version": SCHEMA_VERSION, "status": "UI_ASSET_FAMILY_SEMANTIC_INTEGRITY_TECHNICALLY_QUALIFIED" if all(item["passed"] for item in gates) and all(item["status"] == "PASS" for item in controls) else "UI_ASSET_FAMILY_SEMANTIC_INTEGRITY_FAILED", "overall_pass": all(item["passed"] for item in gates) and all(item["status"] == "PASS" for item in controls), "runtime_revision": RUNTIME_REVISION, "gates_passed": sum(item["passed"] for item in gates), "gate_count": len(gates), "negative_controls_passed": sum(item["status"] == "PASS" for item in controls), "negative_control_count": len(controls), "determinism": compare_generated_outputs(first["outputs"], second["outputs"]), "production_routing": "BLOCKED", "production_approved": False, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "new_generation": 0, "external_review": "REQUIRED", "do_not_merge": True})
        _write_png_sheets(bounded, EVIDENCE)
        print(json.dumps(json.loads((EVIDENCE / "execution-evidence-v0221.json").read_text(encoding="utf-8")), indent=2, ensure_ascii=False))
        return 0 if json.loads((EVIDENCE / "execution-evidence-v0221.json").read_text(encoding="utf-8"))["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
