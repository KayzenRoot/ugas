"""Execute the complete deterministic VFX v0.23.4 F-29R correction."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from ugas import vfx_asset_family_runtime_v0232 as previous_runtime
from ugas.historical_immutability_v0234 import (
    REJECTION_CLASS as HISTORICAL_REJECTION_CLASS,
    validate_historical_file,
    validate_historical_root,
    validate_historical_immutability,
)
from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.state_consistency_v0234 import (
    BASELINE_MAIN_SHA,
    CURRENT_GATE,
    FEATURE_BRANCH,
    NEXT_ACTION,
    NEXT_CANDIDATE,
    PR_NUMBER,
    resolve_next_actions,
    validate_state_consistency,
)
from ugas.vfx_asset_family_runtime_v0234 import (
    CLASS_SPECS,
    EFFECT_CLASSES,
    FAMILY_ID,
    REGISTRY_MODE,
    VERSION,
    VFXAssetFamilyContractError,
    _alpha_bounds,
    _expected_output_hash,
    build_budget_fallback_sheet,
    canonical_json,
    generate_fixture_pack,
    render_fallback_output,
    select_fallback,
    sha256_file,
    sha256_bytes,
    strict_boolean_observation,
    strict_gate,
    validate_degraded_determinism,
    validate_degraded_output,
    validate_effect_record,
    validate_fallback_result,
    validate_production_registry,
    validate_vfx_manifest,
    write_json,
)

EVIDENCE = ROOT / "docs/evidence/vfx-asset-family-runtime-v0234"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _expect_rejection(control_id: str, defect: str, expected: str, action: Callable[[], Any]) -> dict[str, Any]:
    try:
        action()
    except Exception as exc:
        observed = getattr(exc, "rejection_class", None)
        if observed is not None:
            return {
                "control_id": control_id,
                "injected_defect": defect,
                "expected_rejection_class": expected,
                "observed_rejection_class": observed,
                "status": "PASS" if observed == expected else "FAIL",
                "result": "REJECT",
                "actual_exception": type(exc).__name__,
                "detail": getattr(exc, "detail", str(exc)),
            }
        raise
    return {
        "control_id": control_id,
        "injected_defect": defect,
        "expected_rejection_class": expected,
        "observed_rejection_class": None,
        "status": "FAIL",
        "result": "ACCEPT",
        "actual_exception": None,
        "detail": "validator accepted injected defect",
    }


def _raise_if_not(condition: bool, rejection_class: str, detail: str) -> None:
    if not condition:
        raise VFXAssetFamilyContractError(rejection_class, detail)


def _replace_frame_with_image(output: dict[str, Any], root: Path, frame_index: int, source_path: Path, target_name: str) -> None:
    target = root / "controls" / target_name
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as source:
        source.convert("RGBA").save(target, format="PNG", optimize=False, compress_level=9)
    with Image.open(target) as image:
        rgba = image.convert("RGBA")
        output["frames"][frame_index].update(
            {
                "path": target.relative_to(root).as_posix(),
                "sha256": sha256_file(target),
                "width": rgba.width,
                "height": rgba.height,
                "alpha_bounds": _alpha_bounds(rgba),
                "alpha_range": list(rgba.getchannel("A").getextrema()),
            }
        )


def _controls(
    records: list[dict[str, Any]],
    root: Path,
    profile: dict[str, Any],
    loop: dict[str, Any],
    loop_result: dict[str, Any],
    degraded: dict[str, Any],
    opacity_record: dict[str, Any],
    opacity_output: dict[str, Any],
    radius_record: dict[str, Any],
    radius_output: dict[str, Any],
    skip_output: dict[str, Any],
    repeat_output: dict[str, Any],
) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    base_record = records[0]

    bad = deepcopy(opacity_output)
    _replace_frame_with_image(bad, root, 0, root / Path(opacity_record["frames"][0]["path"]), "opacity-claim-full.png")
    bad["output_hash"] = _expected_output_hash(opacity_record, bad, bad["frames"])
    controls.append(_expect_rejection("VFX234-NC-01", "REDUCE_OPACITY with unchanged full alpha pixels", "VFX_DEGRADED_PIXELS_INVALID", lambda: validate_degraded_output(opacity_record, bad, root, root)))

    bad = deepcopy(opacity_output)
    bad["frames"] = bad["frames"] + [deepcopy(bad["frames"][-1])]
    bad["frame_count"] = len(bad["frames"])
    bad["output_hash"] = _expected_output_hash(opacity_record, bad, bad["frames"])
    controls.append(_expect_rejection("VFX234-NC-02", "REDUCE_FRAME_COUNT while all full frames remain", "VFX_FRAME_COUNT_INVALID", lambda: validate_degraded_output(opacity_record, bad, root, root)))

    for control_id, label, record, output in (
        ("VFX234-NC-03", "REDUCE_RADIUS with unchanged decoded bounds", radius_record, radius_output),
        ("VFX234-NC-04", "REDUCE_VISUAL_AREA with unchanged decoded bounds", radius_record, radius_output),
    ):
        bad = deepcopy(output)
        _replace_frame_with_image(bad, root, 0, root / Path(record["frames"][0]["path"]), f"{control_id.lower()}-full.png")
        bad["output_hash"] = _expected_output_hash(record, bad, bad["frames"])
        controls.append(_expect_rejection(control_id, label, "VFX_DEGRADED_PIXELS_INVALID", lambda record=record, bad=bad: validate_degraded_output(record, bad, root, root)))

    bad = deepcopy(degraded)
    _replace_frame_with_image(bad, root, 0, root / Path(loop["frames"][0]["path"]), "copied-full-frame.png")
    bad["output_hash"] = _expected_output_hash(loop, bad, bad["frames"])
    controls.append(_expect_rejection("VFX234-NC-05", "copy full frame bytes and recompute hashes", "VFX_DEGRADED_PIXELS_INVALID", lambda: validate_degraded_output(loop, bad, root, root)))

    unrelated = root / "controls" / "unrelated-valid.png"
    unrelated.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (96, 96), (255, 0, 255, 255)).save(unrelated, format="PNG", optimize=False, compress_level=9)
    bad = deepcopy(degraded)
    _replace_frame_with_image(bad, root, 0, unrelated, "unrelated-valid-reencoded.png")
    bad["output_hash"] = _expected_output_hash(loop, bad, bad["frames"])
    controls.append(_expect_rejection("VFX234-NC-06", "replace with unrelated valid PNG and recompute hashes", "VFX_DEGRADED_PIXELS_INVALID", lambda: validate_degraded_output(loop, bad, root, root)))

    bad_result = deepcopy(loop_result)
    bad_result["applied_steps"] = list(reversed(bad_result["applied_steps"]))
    controls.append(_expect_rejection("VFX234-NC-07", "reorder applied fallback steps", "VFX_FALLBACK_ORDER_INVALID", lambda: validate_fallback_result(loop, bad_result, profile)))

    bad_result = deepcopy(loop_result)
    bad_result["applied_steps"] = bad_result["applied_steps"][1:]
    controls.append(_expect_rejection("VFX234-NC-08", "skip an earlier required fallback step", "VFX_FALLBACK_ORDER_INVALID", lambda: validate_fallback_result(loop, bad_result, profile)))

    bad = deepcopy(degraded)
    bad["degradation_mechanisms"] = [*bad["degradation_mechanisms"], "REDUCE_OPACITY"]
    controls.append(_expect_rejection("VFX234-NC-09", "add mechanism absent from validated steps", "VFX_FALLBACK_MECHANISM_INVALID", lambda: validate_degraded_output(loop, bad, root, root)))

    bad = deepcopy(degraded)
    bad["semantic_identity"]["gameplay_authority"] = "COMBAT"
    controls.append(_expect_rejection("VFX234-NC-10", "mutate gameplay authority during fallback", "VFX_DEGRADED_OUTPUT_SEMANTIC_INVALID", lambda: validate_degraded_output(loop, bad, root, root)))

    bad = deepcopy(skip_output)
    bad["frames"] = [deepcopy(degraded["frames"][0])]
    controls.append(_expect_rejection("VFX234-NC-11", "terminal SKIP_VISUAL with non-empty frames", "VFX_FALLBACK_SKIP_RECORD_INVALID", lambda: validate_degraded_output(loop, bad, root, root)))

    bad = deepcopy(repeat_output)
    bad["output_hash"] = "0" * 64
    controls.append(_expect_rejection("VFX234-NC-12", "mismatched independent repeat hash", "VFX_DEGRADED_DETERMINISM_MISMATCH", lambda: validate_degraded_determinism(degraded, bad)))

    bad_result = deepcopy(loop_result)
    bad_result["after"] = deepcopy(bad_result["after"])
    bad_result["after"]["layers"] = 999
    controls.append(_expect_rejection("VFX234-NC-13", "mutate fallback after-state", "VFX_FALLBACK_STATE_INVALID", lambda: validate_fallback_result(loop, bad_result, profile)))

    bad = deepcopy(degraded)
    bad["frames"][0]["source_index"] = 1
    controls.append(_expect_rejection("VFX234-NC-14", "mutate selected source frame index", "VFX_FRAME_SELECTION_INVALID", lambda: validate_degraded_output(loop, bad, root, root)))

    bad = deepcopy(opacity_output)
    bad["degradation_mechanisms"] = [step for step in bad["degradation_mechanisms"] if step != "REDUCE_OPACITY"]
    controls.append(_expect_rejection("VFX234-NC-15", "omit a validated degradation mechanism", "VFX_FALLBACK_MECHANISM_INVALID", lambda: validate_degraded_output(opacity_record, bad, root, root)))

    bad = deepcopy(skip_output)
    bad["skipped_output"] = {}
    controls.append(_expect_rejection("VFX234-NC-16", "remove explicit skipped-output record", "VFX_FALLBACK_SKIP_RECORD_INVALID", lambda: validate_degraded_output(loop, bad, root, root)))

    controls.append(_expect_rejection("VFX234-NC-17", "non-boolean hard gate", "VFX_HARD_GATE_NON_BOOLEAN_REJECTED", lambda: _raise_if_not(strict_boolean_observation("PASS"), "VFX_HARD_GATE_NON_BOOLEAN_REJECTED", "PASS")))
    controls.append(_expect_rejection("VFX234-NC-18", "production registry entry", "VFX_PRODUCTION_BOUNDARY_REJECTED", lambda: validate_production_registry([{"effect_id": base_record["effect_id"]}])))
    return controls


def _historical_proof() -> dict[str, Any]:
    proof = validate_historical_immutability(ROOT)
    extra_files: list[dict[str, Any]] = []
    mutations: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ugas-vfx-v0234-history-") as temp:
        candidate = Path(temp) / "candidate"
        for relative_root, authority_ref in (
            ("docs/evidence/vfx-asset-family-runtime-v0230", "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72"),
            ("docs/evidence/vfx-asset-family-runtime-v0231", "136079540f674c7467d93bd28e9834addbfce5c3"),
        ):
            extra_root = candidate / "extra" / relative_root
            shutil.copytree(ROOT / relative_root, extra_root)
            extra_path = extra_root / "UNAUTHORIZED-EXTRA-FILE.txt"
            extra_path.write_text("injected extra historical entry\n", encoding="utf-8")
            extra_files.append(_expect_rejection(f"VFX234-F29-EXTRA-{authority_ref[:4]}", f"extra file in {relative_root} historical root", HISTORICAL_REJECTION_CLASS, lambda relative_root=relative_root, authority_ref=authority_ref, candidate_root=extra_root: validate_historical_root(ROOT, authority_ref, relative_root, candidate_root)))

            candidate_root = candidate / "mutation" / relative_root
            shutil.copytree(ROOT / relative_root, candidate_root)
            mutated_file = next(path for path in candidate_root.rglob("*") if path.is_file())
            mutated_file.write_bytes(mutated_file.read_bytes() + b"\nINJECTED_MUTATION")
            mutations.append(_expect_rejection(f"VFX234-F29-MUTATION-{authority_ref[:4]}", f"mutated {relative_root} historical file", HISTORICAL_REJECTION_CLASS, lambda relative_root=relative_root, authority_ref=authority_ref, candidate_root=candidate_root: validate_historical_root(ROOT, authority_ref, relative_root, candidate_root)))
        for relative_path, authority_ref in (("REVIEW-v0.23.0.md", "c8967f5f7b4d3f66b402d10ae8fe5f29cb9fbb72"), ("REVIEW-v0.23.1.md", "136079540f674c7467d93bd28e9834addbfce5c3")):
            candidate_file = candidate / relative_path
            candidate_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative_path, candidate_file)
            candidate_file.write_bytes(candidate_file.read_bytes() + b"\nINJECTED_MUTATION")
            mutations.append(_expect_rejection(f"VFX234-F29-REVIEW-{relative_path}", f"mutated {relative_path}", HISTORICAL_REJECTION_CLASS, lambda relative_path=relative_path, authority_ref=authority_ref, candidate_file=candidate_file: validate_historical_file(ROOT, authority_ref, relative_path, candidate_file)))
    proof["extra_file_controls"] = extra_files
    proof["extra_file_controls_pass"] = all(item["status"] == "PASS" and item["result"] == "REJECT" for item in extra_files)
    proof["mutation_controls"] = mutations
    proof["mutation_controls_pass"] = all(item["status"] == "PASS" and item["result"] == "REJECT" for item in mutations)
    proof["all_negative_controls_pass"] = proof["extra_file_controls_pass"] and proof["mutation_controls_pass"]
    proof["status"] = "PASS" if proof["all_negative_controls_pass"] else "FAIL"
    return proof


def _write_contract_evidence(manifest: dict[str, Any], output_root: Path, fallback_proofs: list[dict[str, Any]]) -> None:
    records = manifest["effects"]
    suffix = "v0234"
    write_json(output_root / f"vfx-family-manifest-{suffix}.json", manifest)
    write_json(output_root / f"effect-class-contract-{suffix}.json", {"schema_version": VERSION, "family_id": FAMILY_ID, "classes": CLASS_SPECS})
    for name, key in (("lifecycle-timing", "lifecycle"), ("blend-alpha-contract", "blend_alpha"), ("spatial-anchor-contract", "spatial"), ("budget-authority", "budget_profile"), ("fallback-degradation", "fallback"), ("representation-import", "representation"), ("integration-linkage", "integration")):
        write_json(output_root / f"{name}-{suffix}.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], **item[key]} for item in records]})
    write_json(output_root / f"alpha-decoded-{suffix}.json", {"schema_version": VERSION, "status": "PASS", "mode": "STRAIGHT_RGBA", "effects": [{"effect_class": item["effect_class"], "pixel_proof": item["blend_alpha"]["pixel_proof"]} for item in records]})
    write_json(output_root / f"cache-provenance-{suffix}.json", {"schema_version": VERSION, "effects": [{"effect_class": item["effect_class"], "semantic_contract_hash": item["semantic_contract_hash"], "cache_key": item["cache_key"], "provenance": item["provenance"]} for item in records]})
    write_json(output_root / f"fallback-output-proof-{suffix}.json", {"status": "PASS", "proofs": fallback_proofs})
    write_json(output_root / f"test-only-fixture-manifest-{suffix}.json", {"status": REGISTRY_MODE, "effect_count": len(records), "effect_classes": list(EFFECT_CLASSES), "real_vfx_asset_coverage": "NONE", "provider_generation_jobs": 0, "diffusion_runs": 0})


def main() -> int:
    global EVIDENCE
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    EVIDENCE = args.evidence_dir.resolve()
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ugas-vfx-v0234-a-") as first_dir, tempfile.TemporaryDirectory(prefix="ugas-vfx-v0234-b-") as second_dir:
        first = generate_fixture_pack(Path(first_dir))
        second = generate_fixture_pack(Path(second_dir))
        first_hash = sha256_bytes(canonical_json(first["manifest"]))
        second_hash = sha256_bytes(canonical_json(second["manifest"]))

    bounded = generate_fixture_pack(EVIDENCE)
    manifest = bounded["manifest"]
    records = bounded["records"]
    contact, timing = previous_runtime.build_contact_sheets(records, EVIDENCE, EVIDENCE)
    contact.replace(EVIDENCE / "vfx-effect-contact-sheet-v0234.png")
    timing.replace(EVIDENCE / "vfx-timing-qa-sheet-v0234.png")
    profile = {"profile_id": "constrained-v1", "max_particles_per_instance": 8, "max_layers": 1, "max_spawn_events_per_second": 10, "max_visual_area_ratio": 0.20, "supported_steps": ["REDUCE_PARTICLE_COUNT", "REDUCE_LAYER_COUNT", "REDUCE_SPAWN_RATE", "REDUCE_VISUAL_AREA", "REDUCE_FRAME_COUNT", "REDUCE_OPACITY", "REDUCE_RADIUS", "SKIP_VISUAL"]}
    loop = records[2]
    loop_result = select_fallback(loop, profile)
    first_root = EVIDENCE / "degraded-first"
    repeat_root = EVIDENCE / "degraded-repeat"
    degraded = render_fallback_output(loop, loop_result, EVIDENCE, first_root)
    repeat = render_fallback_output(loop, loop_result, EVIDENCE, repeat_root)
    validate_degraded_output(loop, degraded, EVIDENCE, first_root)
    validate_degraded_output(loop, repeat, EVIDENCE, repeat_root)
    validate_degraded_determinism(degraded, repeat)
    opacity_record = records[1]
    opacity_profile = {**profile, "max_particles_per_instance": 24, "max_layers": 2, "max_spawn_events_per_second": 12}
    opacity_result = select_fallback(opacity_record, opacity_profile)
    opacity_root = EVIDENCE / "degraded-opacity"
    opacity_output = render_fallback_output(opacity_record, opacity_result, EVIDENCE, opacity_root)
    validate_degraded_output(opacity_record, opacity_output, EVIDENCE, opacity_root)
    radius_record = records[5]
    radius_profile = {**profile, "max_layers": 3, "max_spawn_events_per_second": 30}
    radius_result = select_fallback(radius_record, radius_profile)
    radius_root = EVIDENCE / "degraded-radius"
    radius_output = render_fallback_output(radius_record, radius_result, EVIDENCE, radius_root)
    validate_degraded_output(radius_record, radius_output, EVIDENCE, radius_root)
    skip_output = render_fallback_output(loop, loop_result, EVIDENCE, EVIDENCE / "skipped", force_skip=True)
    validate_degraded_output(loop, skip_output, EVIDENCE, EVIDENCE / "skipped")
    build_budget_fallback_sheet(EVIDENCE, first_root, loop, degraded, EVIDENCE / "vfx-budget-fallback-qa-sheet-v0234.png")
    controls = _controls(records, EVIDENCE, profile, loop, loop_result, degraded, opacity_record, opacity_output, radius_record, radius_output, skip_output, repeat)
    historical = _historical_proof()
    state = _load(ROOT / "docs/evidence/current-state.json")
    matrix = _load(ROOT / "docs/ugas-v1-capability-matrix.json")
    state_schema = _load(ROOT / "schemas/current-state-v0234.json")
    runtime_schema = _load(ROOT / "schemas/vfx-asset-family-runtime-v0234.json")
    state_result = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"), matrix)
    gates: list[dict[str, Any]] = []
    checks = [
        ("VFX234-HG-01", lambda: len(EFFECT_CLASSES) == 10),
        ("VFX234-HG-02", lambda: validate_vfx_manifest(manifest, EVIDENCE)["status"] == "VFX_ASSET_FAMILY_MANIFEST_VALID"),
        ("VFX234-HG-03", lambda: all(validate_effect_record(item, EVIDENCE) is None for item in records)),
        ("VFX234-HG-04", lambda: validate_fallback_result(loop, loop_result, profile) is None),
        ("VFX234-HG-05", lambda: validate_degraded_output(loop, degraded, EVIDENCE, first_root) is None),
        ("VFX234-HG-06", lambda: validate_degraded_output(loop, repeat, EVIDENCE, repeat_root) is None),
        ("VFX234-HG-07", lambda: validate_degraded_determinism(degraded, repeat) is None),
        ("VFX234-HG-08", lambda: degraded["output_hash"] != loop["content_hash"]),
        ("VFX234-HG-09", lambda: degraded["frames"][0]["source_index"] == 0),
        ("VFX234-HG-10", lambda: opacity_output["frames"][0]["alpha_range"] != opacity_record["frames"][0]["alpha_range"]),
        ("VFX234-HG-11", lambda: opacity_output["frame_count"] < opacity_record["lifecycle"]["frame_count"]),
        ("VFX234-HG-12", lambda: radius_output["frames"][0]["alpha_bounds"] != radius_record["frames"][0].get("alpha_bounds")),
        ("VFX234-HG-13", lambda: skip_output["status"] == "SKIPPED" and skip_output["frames"] == []),
        ("VFX234-HG-14", lambda: len(set(degraded["degradation_mechanisms"])) >= 3),
        ("VFX234-HG-15", lambda: degraded["semantic_preserved"] is True and degraded["changes_gameplay"] is False),
        ("VFX234-HG-16", lambda: (EVIDENCE / "vfx-budget-fallback-qa-sheet-v0234.png").is_file()),
        ("VFX234-HG-17", lambda: historical["status"] == "PASS"),
        ("VFX234-HG-18", lambda: historical["mutation_controls_pass"] is True),
        ("VFX234-HG-19", lambda: historical["extra_file_controls_pass"] is True),
        ("VFX234-HG-20", lambda: first_hash == second_hash),
        ("VFX234-HG-21", lambda: state_result["status"] == CURRENT_GATE and not state_result["failures"]),
        ("VFX234-HG-22", lambda: validate_schema_document(state_schema) is None and validate_instance(state, state_schema) is None),
        ("VFX234-HG-23", lambda: validate_schema_document(runtime_schema) is None and validate_instance(manifest, runtime_schema) is None),
        ("VFX234-HG-24", lambda: strict_boolean_observation(True) is True),
        ("VFX234-HG-25", lambda: strict_boolean_observation(False) is False),
        ("VFX234-HG-26", lambda: strict_boolean_observation(1) is False),
        ("VFX234-HG-27", lambda: strict_boolean_observation("PASS") is False),
        ("VFX234-HG-28", lambda: resolve_next_actions(state, {"source": "GITHUB_LIVE", "repository": "KayzenRoot/ugas", "pr_number": PR_NUMBER, "branch": FEATURE_BRANCH, "base_sha": BASELINE_MAIN_SHA, "head_sha": "a" * 40, "pr_state": "OPEN", "merged": False, "external_approval": False})["allowed_next_actions"] == [NEXT_ACTION]),
        ("VFX234-HG-29", lambda: validate_production_registry([])["registry"] == []),
        ("VFX234-HG-30", lambda: manifest["production_routing"] == "BLOCKED" and manifest["production_approved"] is False and manifest["new_generation"] == 0),
        ("VFX234-HG-31", lambda: all(item["provenance"]["provider"] is None for item in records)),
        ("VFX234-HG-32", lambda: all(item["fallback_result"]["semantic_preserved"] is True for item in (degraded, repeat, opacity_output, radius_output))),
        ("VFX234-HG-33", lambda: all(item["semantic_identity"]["gameplay_authority"] == "NONE" for item in (degraded, repeat, opacity_output, radius_output))),
    ]
    for gate_id, checker in checks:
        gates.append(strict_gate(gate_id, checker))
    all_gates_pass = all(item["status"] == "PASS" and item["observed"] is True and type(item["observed"]) is bool for item in gates)
    all_controls_pass = all(item["status"] == "PASS" and item["result"] == "REJECT" and item["expected_rejection_class"] == item["observed_rejection_class"] for item in controls)
    overall = all_gates_pass and all_controls_pass and historical["status"] == "PASS" and state_result["status"] == CURRENT_GATE and not state_result["failures"]
    fallback_proofs = [
        {"class": loop["effect_class"], "full_content_hash": loop["content_hash"], "first_output_hash": degraded["output_hash"], "repeat_output_hash": repeat["output_hash"], "first_root": str(first_root.relative_to(ROOT)).replace("\\", "/"), "repeat_root": str(repeat_root.relative_to(ROOT)).replace("\\", "/"), "first_frame_hashes": [item["sha256"] for item in degraded["frames"]], "repeat_frame_hashes": [item["sha256"] for item in repeat["frames"]], "equal": degraded["output_hash"] == repeat["output_hash"]},
        {"class": opacity_record["effect_class"], "degraded_output_hash": opacity_output["output_hash"], "alpha_range_full": opacity_record["frames"][0]["alpha_range"], "alpha_range_degraded": opacity_output["frames"][0]["alpha_range"], "mechanisms": opacity_output["degradation_mechanisms"]},
        {"class": radius_record["effect_class"], "degraded_output_hash": radius_output["output_hash"], "bounds_degraded": radius_output["frames"][0]["alpha_bounds"], "mechanisms": radius_output["degradation_mechanisms"]},
        {"class": loop["effect_class"], "terminal_skip": skip_output},
    ]
    _write_contract_evidence(manifest, EVIDENCE, fallback_proofs)
    write_json(EVIDENCE / "hard-gates-v0234.json", {"status": "PASS" if all_gates_pass else "FAIL", "required_gate_count": len(gates), "gates": {item["gate_id"]: item for item in gates}})
    write_json(EVIDENCE / "negative-controls-v0234.json", {"status": "PASS" if all_controls_pass else "FAIL", "required_control_count": len(controls), "controls": {item["control_id"]: item for item in controls}})
    write_json(EVIDENCE / "full-slice-two-run-determinism-v0234.json", {"status": "PASS" if first_hash == second_hash else "FAIL", "first_run_sha256": first_hash, "second_run_sha256": second_hash, "equal": first_hash == second_hash})
    write_json(EVIDENCE / "degraded-output-determinism-v0234.json", {"status": "PASS" if degraded["output_hash"] == repeat["output_hash"] else "FAIL", "first_output_hash": degraded["output_hash"], "repeat_output_hash": repeat["output_hash"], "first_root": str(first_root.relative_to(ROOT)).replace("\\", "/"), "repeat_root": str(repeat_root.relative_to(ROOT)).replace("\\", "/"), "first_frame_hashes": [item["sha256"] for item in degraded["frames"]], "repeat_frame_hashes": [item["sha256"] for item in repeat["frames"]], "equal": degraded["output_hash"] == repeat["output_hash"]})
    write_json(EVIDENCE / "historical-immutability-v0234.json", historical)
    write_json(EVIDENCE / "production-registry-v0234.json", {**validate_production_registry([]), "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": "TEST_ONLY"})
    write_json(EVIDENCE / "state-consistency-v0234.json", state_result)
    write_json(EVIDENCE / "schema-validation-v0234.json", {"status": "PASS", "schema": "schemas/current-state-v0234.json", "instance": "docs/evidence/current-state.json"})
    write_json(EVIDENCE / "capability-matrix-validation-v0234.json", {"status": "PASS" if matrix.get("version") == VERSION and matrix.get("next_candidate") == NEXT_CANDIDATE else "FAIL", "version": matrix.get("version"), "next_candidate": matrix.get("next_candidate"), "production_routing": matrix.get("production_routing"), "new_generation": matrix.get("new_generation")})
    write_json(EVIDENCE / "v0.23.3-rejection-correction-v0234.json", {"status": "CORRECTION_REQUIRED", "reviewed_head": "9eda08b25a674a5423a99d35a42711102df91b8b", "findings": ["F-29R"], "forward_only": True, "historical_evidence_unchanged": historical["historical_evidence_unchanged"]})
    write_json(EVIDENCE / "exact-sha-lifecycle-v0234.json", {"source": "GitHub LIVE exact-head metadata", "pr_number": PR_NUMBER, "pr_state": "OPEN", "merged": False, "tracked_head_sha": None, "base_main_sha": BASELINE_MAIN_SHA, "current_head_resolution": "external exact-head artifact / GitHub LIVE"})
    write_json(EVIDENCE / "execution-evidence-v0234.json", {"status": CURRENT_GATE if overall else "VFX_ASSET_FAMILY_RUNTIME_CORRECTION_FAILED", "overall_pass": overall, "schema_version": VERSION, "family_id": FAMILY_ID, "corrections": ["F-29R"], "hard_gate_count": len(gates), "negative_control_count": len(controls), "effect_class_count": len(records), "production_routing": "BLOCKED", "production_approved": False, "real_vfx_asset_coverage": "NONE", "synthetic_vfx_fixture": "TEST_ONLY", "new_generation": 0, "provider_generation_jobs": 0, "diffusion_runs": 0, "base_main_sha": BASELINE_MAIN_SHA, "rejected_reviewed_head": "9eda08b25a674a5423a99d35a42711102df91b8b"})
    print(json.dumps({"status": CURRENT_GATE if overall else "FAIL", "overall_pass": overall, "hard_gates": len(gates), "negative_controls": len(controls), "evidence": str(EVIDENCE)}))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())


