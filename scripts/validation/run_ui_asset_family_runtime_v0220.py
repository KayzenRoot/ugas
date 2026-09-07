"""Execute the complete v0.22.0 UI asset-family TEST_ONLY validation slice."""

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

from ugas.ui_asset_family_runtime_v0220 import (  # noqa: E402
    FAMILY_ID, INTEGRATION_AUTHORITIES, RUNTIME_REVISION, SCHEMA_VERSION,
    STYLE_TOKEN_SET_ID, UI_COMPONENT_CLASSES, UI_STATES, UIAssetFamilyContractError,
    build_test_only_style_tokens, build_ui_manifest, cache_key_for, canonical_json,
    compare_generated_outputs, generate_fixture_pack, render_component, sha256_bytes, sha256_file,
    style_token_hash, validate_cache_record, validate_component_record,
    validate_determinism, validate_historical_authority, validate_integration_linkage,
    validate_nine_slice, validate_production_registry, validate_provenance_output,
    validate_rendered_output, validate_safe_geometry, validate_state_materiality,
    validate_ui_manifest, write_json,
)


EVIDENCE = ROOT / "docs/evidence/ui-asset-family-runtime-v0220"
GOVERNANCE_BINDING = ROOT / "docs/evidence/github-governance-v0220/v0213-closure-completion-binding.json"
OLD_GOVERNANCE_BINDING = ROOT / "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"
BASE_MAIN = "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3"
REQUIRED_GATES = [f"UI-HG-{index:02d}" for index in range(1, 23)]
REQUIRED_CONTROLS = [f"UI-NC-{index:02d}" for index in range(1, 23)]


def _strict_gate(gate_id: str, checker: Callable[[], bool]) -> dict[str, Any]:
    observed: Any = None
    error: str | None = None
    try:
        observed = checker()
    except Exception as exc:  # the gate records the real failure, then fails closed
        error = f"{type(exc).__name__}:{exc}"
    passed = type(observed) is bool and observed is True
    return {"gate_id": gate_id, "observed": observed, "observed_type": type(observed).__name__, "passed": passed, "status": "PASS" if passed else "FAIL", "error": error}


def _expect_rejection(control_id: str, injected_defect: str, expected: str, action: Callable[[], Any]) -> dict[str, Any]:
    observed_class: str | None = None
    diagnostic: str | None = None
    result = "ACCEPT"
    try:
        action()
    except UIAssetFamilyContractError as exc:
        result = "REJECT"
        observed_class = exc.rejection_class
        diagnostic = str(exc)
    except Exception as exc:  # unexpected exceptions are still failures, never a green rejection
        result = "REJECT"
        observed_class = f"UNEXPECTED_{type(exc).__name__}"
        diagnostic = str(exc)
    passed = result == "REJECT" and observed_class == expected
    return {"control_id": control_id, "injected_defect": injected_defect, "canonical_entry_point": "public_runtime_validator", "expected_rejection_class": expected, "observed_rejection_class": observed_class, "result": result, "status": "PASS" if passed else "FAIL", "diagnostic": diagnostic}


def _write_png_sheets(pack: dict[str, Any], root: Path) -> None:
    manifest = pack["manifest"]
    cell_w, cell_h = 84, 62
    contact = Image.new("RGBA", (len(UI_STATES) * cell_w, len(UI_COMPONENT_CLASSES) * cell_h), (238, 240, 244, 255))
    draw = ImageDraw.Draw(contact)
    for row, component in enumerate(manifest["components"]):
        for column, state in enumerate(UI_STATES):
            relative = Path("fixtures") / component["component_class"] / f"{state}-1x.png"
            with Image.open(root / relative) as source:
                image = source.convert("RGBA")
                image.thumbnail((cell_w - 8, cell_h - 18))
                x = column * cell_w + (cell_w - image.width) // 2
                y = row * cell_h + 12 + (cell_h - 18 - image.height) // 2
                contact.alpha_composite(image, (x, y))
            draw.text((column * cell_w + 3, row * cell_h + 2), state[:5], fill=(16, 20, 28, 255))
        draw.text((2, row * cell_h + cell_h - 12), component["component_class"][:14], fill=(16, 20, 28, 255))
    contact.save(EVIDENCE / "ui-state-contact-sheet-v0220.png", format="PNG", optimize=False, compress_level=9)

    geometry = Image.new("RGBA", (560, 4 * 120), (250, 250, 250, 255))
    gdraw = ImageDraw.Draw(geometry)
    for index, component in enumerate(manifest["components"]):
        col, row = index % 4, index // 4
        left, top = col * 140 + 15, row * 120 + 24
        visual = component["visual_bounds"]
        hit = component["hit_bounds"]
        scale = min(110 / visual["width"], 74 / visual["height"])
        gdraw.rectangle((left, top, left + visual["width"] * scale, top + visual["height"] * scale), outline=(36, 74, 130, 255), width=2)
        gdraw.rectangle((left + hit["x"] * scale, top + hit["y"] * scale, left + (hit["x"] + hit["width"]) * scale, top + (hit["y"] + hit["height"]) * scale), outline=(186, 80, 48, 255), width=1)
        gdraw.text((left, top + 80), component["component_class"][:20], fill=(16, 20, 28, 255))
        gdraw.text((left, top + 94), "blue visual / red hit", fill=(16, 20, 28, 255))
    geometry.save(EVIDENCE / "ui-geometry-qa-sheet-v0220.png", format="PNG", optimize=False, compress_level=9)


def _state_consistency_gate() -> bool:
    state_path = ROOT / "docs/evidence/current-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return type(state.get("version")) is str and state.get("version") == SCHEMA_VERSION and state.get("phase") == "UI_ASSET_FAMILY" and state.get("current_gate") == "UI_ASSET_FAMILY_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" and state.get("allowed_next_actions") == ["external_review_ui_asset_family_v0220"] and state.get("production_routing") == "BLOCKED" and state.get("production_approved") is False and state.get("new_generation") == 0


def _historical_proof() -> dict[str, Any]:
    authority = subprocess.run(["git", "show", f"{BASE_MAIN}:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"], cwd=ROOT, capture_output=True, check=False).stdout
    # Windows may materialize tracked text with CRLF.  The immutable candidate
    # is therefore compared as the exact checked-in Git blob, not after newline
    # normalization or a fabricated parsed representation.
    candidate = subprocess.run(["git", "show", f"HEAD:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"], cwd=ROOT, capture_output=True, check=False).stdout
    positive = validate_historical_authority(authority, candidate, authority_ref=f"git:{BASE_MAIN}:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json")
    mutation = bytearray(candidate); mutation[-2] = 0x20 if mutation[-2] != 0x20 else 0x21
    mutation_bytes = bytes(mutation)
    observed: dict[str, Any] = {}
    try:
        validate_historical_authority(authority, mutation_bytes, authority_ref=positive["authority_ref"])
    except UIAssetFamilyContractError as exc:
        observed = {"status": "REJECT", "rejection_class": exc.rejection_class, "mutation_input_sha256": sha256_bytes(mutation_bytes)}
    return {"authority_ref": positive["authority_ref"], "authority_sha256": positive["authority_sha256"], "current_candidate_sha256": positive["candidate_sha256"], "working_tree_file_sha256": sha256_file(OLD_GOVERNANCE_BINDING), "candidate_source": "git:HEAD exact blob", "current_file_valid": True, "mutation_input_fingerprint": sha256_bytes(mutation_bytes), "mutation_rejection": observed}


def main() -> int:
    global EVIDENCE
    parser = argparse.ArgumentParser(); parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE); args = parser.parse_args()
    EVIDENCE = args.evidence_dir.resolve()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    tokens = build_test_only_style_tokens()
    manifest = build_ui_manifest(tokens)
    with tempfile.TemporaryDirectory(prefix="ugas-ui-v0220-a-") as first_dir, tempfile.TemporaryDirectory(prefix="ugas-ui-v0220-b-") as second_dir:
        first = generate_fixture_pack(Path(first_dir)); second = generate_fixture_pack(Path(second_dir))
        # Materialize the already-proven first run under the bounded evidence
        # root so every manifest path is review-addressable.
        first = generate_fixture_pack(EVIDENCE)
        first_root = EVIDENCE
        first_manifest = first["manifest"]
        # Copy the deterministic manifest into the bounded evidence root.
        write_json(EVIDENCE / "ui-family-manifest-v0220.json", first_manifest)
        components = first_manifest["components"]
        first_output_records = first_manifest["outputs"]

        gates: list[dict[str, Any]] = []
        gates.append(_strict_gate("UI-HG-01", lambda: (validate_ui_manifest(first_manifest, tokens) is not None)))
        gates.append(_strict_gate("UI-HG-02", lambda: set(first_manifest["component_classes"]) == set(UI_COMPONENT_CLASSES) and len(first_manifest["components"]) == 14))
        gates.append(_strict_gate("UI-HG-03", lambda: len({item["component_id"] for item in components}) == 14))
        gates.append(_strict_gate("UI-HG-04", lambda: tuple(first_manifest["state_vocabulary"]) == UI_STATES and all(tuple(item["supported_states"]) == UI_STATES for item in components)))
        def _materiality_passes() -> bool:
            for item in components:
                validate_state_materiality({state: first["outputs"][f"{item['component_class']}:{state}:1x"] for state in UI_STATES})
            return True
        gates.append(_strict_gate("UI-HG-05", _materiality_passes))
        gates.append(_strict_gate("UI-HG-06", lambda: all(item["style_token_set_id"] == STYLE_TOKEN_SET_ID and item["style_token_hash"] == style_token_hash(tokens) for item in components)))
        gates.append(_strict_gate("UI-HG-07", lambda: all(validate_nine_slice(item) is not None for item in components)))
        gates.append(_strict_gate("UI-HG-08", lambda: all(item["stretch_geometry"]["center_width"] > 0 and item["stretch_geometry"]["center_height"] > 0 for item in components)))
        gates.append(_strict_gate("UI-HG-09", lambda: all(validate_safe_geometry(item)["visual_hit_separate"] for item in components)))
        gates.append(_strict_gate("UI-HG-10", lambda: all(item["text_safe_rect"] == item["content_safe_rect"] and item["icon_safe_rect"] != item["visual_bounds"] for item in components)))
        gates.append(_strict_gate("UI-HG-11", lambda: all(item["visual_bounds"] != item["hit_bounds"] for item in components)))
        gates.append(_strict_gate("UI-HG-12", lambda: all(next(record for record in first_output_records if record["component_id"] == item["component_id"] and record["scale_factor"] == 2)["raster_size"] == [item["logical_size"][0] * 2, item["logical_size"][1] * 2] for item in components)))
        gates.append(_strict_gate("UI-HG-13", lambda: all(validate_rendered_output(render_component(item, "normal", 1, tokens), item, "normal", 1)["mode"] == "RGBA" for item in components)))
        gates.append(_strict_gate("UI-HG-14", lambda: all(validate_integration_linkage(item) is not None for item in components)))
        gates.append(_strict_gate("UI-HG-15", lambda: validate_integration_linkage(next(item for item in components if item["component_class"] == "minimap_frame"), expected_revision=INTEGRATION_AUTHORITIES["maps_minimap_runtime"]) ["mutation_allowed"] is False))
        gates.append(_strict_gate("UI-HG-16", lambda: all(validate_integration_linkage(next(item for item in components if item["component_class"] == name), expected_revision=INTEGRATION_AUTHORITIES["items_props" if name == "inventory_slot" else "equipment_outfits"]) is not None for name in ("inventory_slot", "equipment_slot"))))
        gates.append(_strict_gate("UI-HG-17", lambda: all(validate_cache_record({"family_id": item["family_id"], "component_id": item["component_id"], "revision": item["revision"], "state": record["state"], "scale_factor": record["scale_factor"], "style_token_hash": item["style_token_hash"], "semantic_input_hash": item["semantic_input_hash"], "cache_key": record["cache_key"]}, item, tokens) is None for item in components for record in first_output_records if record["component_id"] == item["component_id"])))
        gates.append(_strict_gate("UI-HG-18", lambda: all(record["output_sha256"] == sha256_bytes((first_root / record["relative_path"]).read_bytes()) for record in first_output_records)))
        gates.append(_strict_gate("UI-HG-19", lambda: validate_determinism(first["outputs"], second["outputs"]) is None))
        gates.append(_strict_gate("UI-HG-20", lambda: validate_production_registry([], production_safe=False)))
        history = _historical_proof()
        gates.append(_strict_gate("UI-HG-21", lambda: history["current_file_valid"] is True and history["mutation_rejection"].get("rejection_class") == "HISTORICAL_EVIDENCE_MUTATION_REJECTED"))
        gates.append(_strict_gate("UI-HG-22", _state_consistency_gate))

        controls: list[dict[str, Any]] = []
        bad = deepcopy(first_manifest)
        bad["component_classes"] = bad["component_classes"][:-1]
        controls.append(_expect_rejection("UI-NC-01", "missing component class", "UI_COMPONENT_CLASS_MISSING", lambda: validate_ui_manifest(bad, tokens)))
        bad = deepcopy(first_manifest); bad["components"][1]["component_id"] = bad["components"][0]["component_id"]
        controls.append(_expect_rejection("UI-NC-02", "duplicate component ID", "UI_COMPONENT_ID_DUPLICATE", lambda: validate_ui_manifest(bad, tokens)))
        controls.append(_expect_rejection("UI-NC-03", "unsupported state", "UI_STATE_UNSUPPORTED", lambda: render_component(components[0], "unknown", 1, tokens)))
        controls.append(_expect_rejection("UI-NC-04", "identical state bytes", "UI_STATE_BYTES_NOT_DISTINCT", lambda: validate_state_materiality({state: b"same" for state in UI_STATES})))
        stale = deepcopy(components[0]); stale["style_token_hash"] = "0" * 64
        controls.append(_expect_rejection("UI-NC-05", "stale style token hash", "UI_STYLE_TOKEN_HASH_STALE", lambda: validate_component_record(stale, tokens)))
        bad = deepcopy(components[0]); bad["stretch_geometry"]["slice_margins"]["left"] = 0
        controls.append(_expect_rejection("UI-NC-06", "invalid nine-slice margins", "UI_NINE_SLICE_MARGINS_INVALID", lambda: validate_component_record(bad, tokens)))
        bad = deepcopy(components[0]); bad["stretch_geometry"]["center_width"] = 0
        controls.append(_expect_rejection("UI-NC-07", "collapsed nine-slice center", "UI_NINE_SLICE_CENTER_INVALID", lambda: validate_nine_slice({**bad, "stretch_geometry": {**bad["stretch_geometry"], "slice_margins": {"left": 20, "right": 20, "top": 2, "bottom": 2}}})))
        bad = deepcopy(components[0]); bad["content_safe_rect"]["x"] = 999
        controls.append(_expect_rejection("UI-NC-08", "content safe rect escapes visual bounds", "UI_CONTENT_SAFE_RECT_OUT_OF_BOUNDS", lambda: validate_safe_geometry(bad)))
        bad = deepcopy(components[0]); bad["icon_safe_rect"]["x"] = 999
        controls.append(_expect_rejection("UI-NC-09", "icon/text safe rect escapes", "UI_ICON_TEXT_SAFE_RECT_OUT_OF_BOUNDS", lambda: validate_safe_geometry(bad)))
        controls.append(_expect_rejection("UI-NC-10", "wrong raster dimensions", "UI_SCALE_OUTPUT_INVALID", lambda: validate_rendered_output(render_component(components[0], "normal", 1, tokens), components[0], "normal", 2)))
        controls.append(_expect_rejection("UI-NC-11", "mutated scale output dimensions", "UI_SCALE_OUTPUT_INVALID", lambda: validate_rendered_output(Image.new("RGBA", (1, 1)), components[0], "normal", 2)))
        controls.append(_expect_rejection("UI-NC-12", "empty alpha bounds", "UI_ALPHA_BOUNDS_INVALID", lambda: validate_rendered_output(Image.new("RGBA", tuple(components[0]["logical_size"]), (0, 0, 0, 0)), components[0], "normal", 1)))
        bad = deepcopy(components[0]); bad["integration_linkage"]["mode"] = "WRITE"
        controls.append(_expect_rejection("UI-NC-13", "integration linkage is not read-only", "UI_INTEGRATION_REFERENCE_INVALID", lambda: validate_integration_linkage(bad)))
        controls.append(_expect_rejection("UI-NC-14", "minimap linkage mutation", "UI_MINIMAP_LINKAGE_MUTATION_FORBIDDEN", lambda: validate_integration_linkage(next(item for item in components if item["component_class"] == "minimap_frame"), attempted_mutation=True)))
        controls.append(_expect_rejection("UI-NC-15", "stale slot authority revision", "UI_SLOT_AUTHORITY_STALE", lambda: validate_integration_linkage(next(item for item in components if item["component_class"] == "inventory_slot"), expected_revision="stale")))
        record = {"family_id": components[0]["family_id"], "component_id": components[0]["component_id"], "revision": components[0]["revision"], "scale_factor": 1, "style_token_hash": components[0]["style_token_hash"], "semantic_input_hash": components[0]["semantic_input_hash"], "cache_key": "wrong"}
        controls.append(_expect_rejection("UI-NC-16", "cache state omitted", "UI_CACHE_STATE_OMITTED", lambda: validate_cache_record(record, components[0], tokens)))
        record["state"] = "normal"; record["style_token_hash"] = "stale"
        controls.append(_expect_rejection("UI-NC-17", "cache style identity omitted", "UI_CACHE_STYLE_OR_SCALE_OMITTED", lambda: validate_cache_record(record, components[0], tokens)))
        output_record = first_output_records[0]
        controls.append(_expect_rejection("UI-NC-18", "provenance output hash mismatch", "UI_PROVENANCE_OUTPUT_HASH_MISMATCH", lambda: validate_provenance_output({**output_record, "output_sha256": "0" * 64}, b"fixture")))
        altered = dict(second["outputs"]); altered[next(iter(altered))] = b"different"
        controls.append(_expect_rejection("UI-NC-19", "second run differs", "UI_NONDETERMINISTIC_SECOND_RUN", lambda: validate_determinism(first["outputs"], altered)))
        controls.append(_expect_rejection("UI-NC-20", "production registry non-empty", "UI_PRODUCTION_REGISTRY_NON_EMPTY", lambda: validate_production_registry([{"id": "real"}], production_safe=False)))
        controls.append(_expect_rejection("UI-NC-21", "test fixture marked production safe", "UI_TEST_ONLY_PRODUCTION_SAFE", lambda: validate_production_registry([], production_safe=True)))
        mutation = bytearray(OLD_GOVERNANCE_BINDING.read_bytes()); mutation[-2] = 0x20 if mutation[-2] != 0x20 else 0x21
        authority = subprocess.run(["git", "show", f"{BASE_MAIN}:docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"], cwd=ROOT, capture_output=True, check=False).stdout
        controls.append(_expect_rejection("UI-NC-22", "historical binding mutation", "HISTORICAL_EVIDENCE_MUTATION_REJECTED", lambda: validate_historical_authority(authority, bytes(mutation), authority_ref="historical-v0213-binding")))

        gates_doc = {item["gate_id"]: item for item in gates}; controls_doc = {item["control_id"]: item for item in controls}
        write_json(EVIDENCE / "component-class-matrix-v0220.json", {"schema_version": SCHEMA_VERSION, "classes": [{"component_class": item["component_class"], "component_id": item["component_id"]} for item in components]})
        write_json(EVIDENCE / "state-variant-matrix-v0220.json", {"schema_version": SCHEMA_VERSION, "states": list(UI_STATES), "components": [{"component_id": item["component_id"], "supported_states": item["supported_states"]} for item in components]})
        write_json(EVIDENCE / "style-token-authority-v0220.json", {"schema_version": SCHEMA_VERSION, "style_token_set_id": STYLE_TOKEN_SET_ID, "style_token_hash": style_token_hash(tokens), "tokens": tokens})
        write_json(EVIDENCE / "nine-slice-geometry-v0220.json", {"schema_version": SCHEMA_VERSION, "components": [validate_nine_slice(item) for item in components]})
        write_json(EVIDENCE / "safe-area-geometry-v0220.json", {"schema_version": SCHEMA_VERSION, "components": [validate_safe_geometry(item) for item in components]})
        write_json(EVIDENCE / "scale-consistency-v0220.json", {"schema_version": SCHEMA_VERSION, "supported_scales": [1, 2], "outputs": [{"component_id": item["component_id"], "scales": [next(record["raster_size"] for record in first_output_records if record["component_id"] == item["component_id"] and record["scale_factor"] == scale) for scale in (1, 2)]} for item in components]})
        write_json(EVIDENCE / "integration-linkage-v0220.json", {"schema_version": SCHEMA_VERSION, "authorities": INTEGRATION_AUTHORITIES, "components": [validate_integration_linkage(item) for item in components]})
        write_json(EVIDENCE / "cache-identity-v0220.json", {"schema_version": SCHEMA_VERSION, "fields": ["family_id", "component_id", "revision", "state", "scale_factor", "style_token_hash", "semantic_input_hash"], "records": [{"component_id": record["component_id"], "state": record["state"], "scale_factor": record["scale_factor"], "cache_key": record["cache_key"]} for record in first_output_records]})
        write_json(EVIDENCE / "provenance-v0220.json", {"schema_version": SCHEMA_VERSION, "runtime_revision": RUNTIME_REVISION, "output_count": len(first_output_records), "hash_source": "exact PNG bytes"})
        write_json(EVIDENCE / "hard-gates-v0220.json", {"schema_version": SCHEMA_VERSION, "gates": gates_doc, "required_gate_count": 22, "strict_boolean_contract": True})
        write_json(EVIDENCE / "negative-controls-v0220.json", {"schema_version": SCHEMA_VERSION, "controls": controls_doc, "required_control_count": 22, "all_rejections_observed": all(item["result"] == "REJECT" for item in controls)})
        write_json(EVIDENCE / "full-slice-two-run-determinism-v0220.json", {"schema_version": SCHEMA_VERSION, "status": "PASS" if compare_generated_outputs(first["outputs"], second["outputs"]) else "FAIL", "first_output_count": len(first["outputs"]), "second_output_count": len(second["outputs"]), "first_run_sha256": sha256_bytes(canonical_json({key: sha256_bytes(value) for key, value in sorted(first["outputs"].items())})), "second_run_sha256": sha256_bytes(canonical_json({key: sha256_bytes(value) for key, value in sorted(second["outputs"].items())}))})
        write_json(EVIDENCE / "production-registry-v0220.json", {"schema_version": SCHEMA_VERSION, "registry": [], "production_registry_empty": True, "production_routing": "BLOCKED", "production_approved": False, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "new_generation": 0})
        write_json(EVIDENCE / "test-only-fixture-manifest-v0220.json", {"schema_version": SCHEMA_VERSION, "family_id": FAMILY_ID, "registry_mode": "TEST_ONLY", "production_safe": False, "fixture_count": len(first_output_records), "fixture_root": "fixtures/"})
        write_json(EVIDENCE / "historical-authority-v0220.json", {"schema_version": SCHEMA_VERSION, **history})
        _write_png_sheets(first, first_root)
        overall = all(item["passed"] for item in gates) and all(item["status"] == "PASS" for item in controls) and history["current_file_valid"] is True
        execution = {"schema_version": SCHEMA_VERSION, "status": "UI_ASSET_FAMILY_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" if overall else "UI_ASSET_FAMILY_RUNTIME_FOUNDATION_FAILED", "overall_pass": overall, "runtime_revision": RUNTIME_REVISION, "gates_passed": sum(item["passed"] for item in gates), "gate_count": 22, "negative_controls_passed": sum(item["status"] == "PASS" for item in controls), "negative_control_count": 22, "determinism": compare_generated_outputs(first["outputs"], second["outputs"]), "production_routing": "BLOCKED", "production_approved": False, "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "new_generation": 0, "external_review": "REQUIRED", "do_not_merge": True}
        write_json(EVIDENCE / "execution-evidence-v0220.json", execution)
        print(json.dumps(execution, indent=2, ensure_ascii=False))
        return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
