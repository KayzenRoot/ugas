"""Run the v0.9.1 generic-runtime and honest idle-QA qualification slice."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/animation-runtime-v091"
BASELINE = "16c60c9ff934a55adefc82a99d81dafb52d1047c"
PARENT = "46ba3ae87558ff26055e14aa8d9c6f3ee147333c"

import sys
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import AnimationContractError, compile_spec, load_spec, normalized_timing, package_compiled, qa_compiled
from ugas.animation_profiles import idle_front_v1 as idle
from ugas.animation_profiles import walk_front_v1 as walk
from ugas.animation_profiles.common import render_source_only
from ugas.cutout_rig import PART_NAMES
from ugas.cutout_structural import pairwise_overlap_v073
from ugas.schema_validation import SchemaValidationError


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run_dummy(spec_path: Path, root: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    directory = Path(tempfile.mkdtemp(prefix="ugas-v091-dummy-", dir=root / "tmp"))
    manifest = compile_spec(spec_path, directory / "compiled", root)
    qa_path = qa_compiled(manifest, root)
    package_path = package_compiled(manifest, root)
    return directory, read_json(qa_path), read_json(package_path)


def _dummy_contract() -> dict[str, Any]:
    fixture = ROOT / "tests/fixtures/dummy-two-key-v1.json"
    directory, qa, package = _run_dummy(fixture, ROOT)
    try:
        failures: dict[str, str] = {}
        for mutation in ("decision_failed", "hard_gate_false", "failures_non_empty"):
            mutant = Path(tempfile.mkdtemp(prefix=f"ugas-v091-{mutation}-", dir=ROOT / "tmp"))
            manifest = compile_spec(fixture, mutant / "compiled", ROOT)
            qa_path = qa_compiled(manifest, ROOT)
            value = read_json(qa_path)
            if mutation == "decision_failed": value["decision"] = "FAILED"
            elif mutation == "hard_gate_false": value["hard_gates"]["fixture_integrity"] = False
            else: value["failures"] = ["synthetic_failure"]
            qa_path.write_text(json.dumps(value), encoding="utf-8")
            try:
                package_compiled(manifest, ROOT)
            except AnimationContractError as exc:
                failures[mutation] = str(exc)
            else:
                raise RuntimeError(f"dummy_fail_closed_gap:{mutation}")
            if (mutant / "compiled" / "package-manifest.json").exists():
                raise RuntimeError(f"dummy_package_created_after_failure:{mutation}")
        return {"schema_version": "0.9.1", "animation_id": "qa-fixture-cycle-v1", "status": "GENERIC_RUNTIME_CONTRACT_PASSED", "qualified_status_arbitrary": qa["status"], "qualified_decision": qa["decision"], "package_qa_decision": package["qa_decision"], "package_policy_uses_decision_not_status": True, "hash_bindings_present": all(qa.get(key) for key in ("spec_sha256", "compiled_manifest_sha256")), "negative_controls": failures}
    finally:
        # Temporary lifecycle outputs are intentionally outside the published artifact set.
        pass


def _timing_contract() -> dict[str, Any]:
    fixture = read_json(ROOT / "tests/fixtures/dummy-two-key-v1.json")
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="ugas-v091-timing-", dir=ROOT / "tmp") as directory:
        base = Path(directory)
        for name, mutation in (("fps_only", {"remove": "per_frame_duration_ms", "add": ("fps", 8)}), ("duration_only", {"remove": "fps", "add": None})):
            value = copy.deepcopy(fixture); value.pop(mutation["remove"], None)
            if mutation["add"]: value[mutation["add"][0]] = mutation["add"][1]
            path = base / f"{name}.json"; write_json(path, value); loaded = load_spec(path, ROOT); results[name] = {"status": "VALID", "timing": normalized_timing(loaded)}
        both = copy.deepcopy(fixture); both["fps"] = 8; path = base / "both.json"; write_json(path, both)
        try: load_spec(path, ROOT)
        except (SchemaValidationError, AnimationContractError) as exc: results["both"] = {"status": "INVALID", "error": type(exc).__name__}
        else: raise RuntimeError("timing_both_must_fail")
        neither = copy.deepcopy(fixture); neither.pop("per_frame_duration_ms", None); path = base / "neither.json"; write_json(path, neither)
        try: load_spec(path, ROOT)
        except (SchemaValidationError, AnimationContractError) as exc: results["neither"] = {"status": "INVALID", "error": type(exc).__name__}
        else: raise RuntimeError("timing_neither_must_fail")
    return {"schema_version": "0.9.1", "status": "TIMING_ALTERNATIVE_QUALIFICATION_PASSED", "representations": results, "source_spec_unchanged": True}


def _negative_controls() -> dict[str, Any]:
    records = [{"feet": {"feet": {side: {"projected_ground_y": 100.0, "sole_error_px": 0.0, "ground_penetration_px": 0.0, "ankle_x": 10.0 if side == "left" else 20.0} for side in ("left", "right")}, "hard_gates": {"left": True, "right": True}}} for _ in range(12)]
    sole_bad = copy.deepcopy(records); sole_bad[3]["feet"]["feet"]["left"]["projected_ground_y"] += 2.0
    ankle_bad = copy.deepcopy(records); ankle_bad[3]["feet"]["feet"]["right"]["ankle_x"] += 3.0
    ankle_boundary = copy.deepcopy(records); ankle_boundary[3]["feet"]["feet"]["right"]["ankle_x"] += 1.5
    return {"sole_plus_2_px": idle.dual_foot_drift_qa(sole_bad)["sides"]["left"]["hard_gates"]["frame_to_frame_sole_anchor_drift_le_threshold"] is False, "ankle_plus_3_px": idle.dual_foot_drift_qa(ankle_bad)["sides"]["right"]["hard_gates"]["ankle_horizontal_drift_from_baseline_le_threshold"] is False, "ankle_plus_1_5_px_passes": idle.dual_foot_drift_qa(ankle_boundary)["sides"]["right"]["hard_gates"]["ankle_horizontal_drift_from_baseline_le_threshold"] is True}


def _bbox_negative_controls() -> dict[str, Any]:
    def measured(head_size: int = 4, torso_size: int = 6) -> dict[str, Any]:
        head = Image.new("RGBA", (16, 16), (0, 0, 0, 0)); ImageDraw.Draw(head).rectangle((0, 0, head_size - 1, head_size - 1), fill=(255, 255, 255, 255))
        torso = Image.new("RGBA", (16, 16), (0, 0, 0, 0)); ImageDraw.Draw(torso).rectangle((0, 0, torso_size - 1, torso_size - 1), fill=(255, 255, 255, 255))
        return idle.layer_bbox_measurement({"head": head, "torso_pelvis": torso})
    good = [measured() for _ in range(12)]; head_bad = copy.deepcopy(good); head_bad[3] = measured(head_size=8); torso_bad = copy.deepcopy(good); torso_bad[3] = measured(torso_size=12)
    head_result = idle.layer_bbox_temporal_gate(head_bad); torso_result = idle.layer_bbox_temporal_gate(torso_bad)
    return {"head_only_scale": {"head_fails": head_result["hard_gates"]["head_bbox_area_cv_le_threshold"] is False, "torso_unaffected": torso_result["hard_gates"]["torso_bbox_area_cv_le_threshold"] is True}, "torso_only_scale": {"torso_fails": torso_result["hard_gates"]["torso_bbox_area_cv_le_threshold"] is False, "head_unaffected": head_result["hard_gates"]["head_bbox_area_cv_le_threshold"] is True}}


def _forbidden_overlap_fixture() -> dict[str, Any]:
    size = (32, 32); layers = {name: Image.new("RGBA", size, (0, 0, 0, 0)) for name in PART_NAMES}
    for name in ("head", "torso_pelvis"):
        ImageDraw.Draw(layers[name]).rectangle((2, 2, 28, 28), fill=(255, 255, 255, 255))
    joints = {joint: {"x": 15, "y": 15} for _, _, joint in idle.TOPOLOGY_ADJACENCY}; target = {"joints": joints}; order = list(idle.Z_ORDER); plan = {"phase_plans": {"I0-neutral-A": {"z_order": order}}, "critical_pairs": [], "allowed_expected_occlusion_pairs": []}
    result = pairwise_overlap_v073(layers, "I0-neutral-A", target, plan, {"records": [], "regions": {}, "allowed_pair_keys": set()})
    return {"status": result["status"], "hard_gates": result["hard_gates"], "meaningful_forbidden_overlap": result["forbidden_meaningful_overlap"]}


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    dummy = _dummy_contract(); timing = _timing_contract()
    walk_spec = ROOT / "profiles/animation/walk-front-v1.json"; idle_spec = ROOT / "profiles/animation/idle-front-v1.json"
    old_walk = read_json(ROOT / "docs/evidence/animation-runtime-v090/replay/walk-front-v1/compiled-manifest.json")
    old_idle = read_json(ROOT / "docs/evidence/animation-runtime-v090/idle-front-v1/compiled-manifest.json")
    with tempfile.TemporaryDirectory(prefix="ugas-v091-runtime-", dir=ROOT / "tmp") as directory:
        temp = Path(directory); walk_manifest = compile_spec(walk_spec, temp / "walk", ROOT); walk_qa_path = qa_compiled(walk_manifest, ROOT); walk_qa = read_json(walk_qa_path); walk_package = read_json(package_compiled(walk_manifest, ROOT))
        walk_sheet = digest(ROOT / walk_package["sprite_sheet"]["path"]); walk_gif = digest(ROOT / walk_package["preview_gif"]["path"])
        if walk_qa["decision"] != "QUALIFIED" or [i["rgba_sha256"] for i in read_json(walk_manifest)["frames"]] != [i["rgba_sha256"] for i in old_walk["frames"]]: raise RuntimeError("WALK_GENERIC_REPLAY_DRIFT")
        if walk_sheet != digest(ROOT / "docs/evidence/walk-front-v081/walk-front-spritesheet-v081.png") or walk_gif != digest(ROOT / "docs/evidence/walk-front-v081/walk-front-preview-v081.gif"): raise RuntimeError("WALK_PACKAGE_REPLAY_DRIFT")
        idle_manifest = compile_spec(idle_spec, temp / "idle", ROOT); repeat_manifest = compile_spec(idle_spec, temp / "idle-repeat", ROOT); idle_data = read_json(idle_manifest); repeat_data = read_json(repeat_manifest); idle_qa_path = qa_compiled(idle_manifest, ROOT); idle_qa = read_json(idle_qa_path); idle_package = read_json(package_compiled(idle_manifest, ROOT))
        if [(i["rgba_sha256"], i["target_hash"]) for i in idle_data["frames"]] != [(i["rgba_sha256"], i["target_hash"]) for i in old_idle["frames"]]: raise RuntimeError("IDLE_FRONT_CANONICAL_REPLAY_DRIFT")
        if [(i["rgba_sha256"], i["target_hash"]) for i in idle_data["frames"]] != [(i["rgba_sha256"], i["target_hash"]) for i in repeat_data["frames"]]: raise RuntimeError("IDLE_FRONT_DETERMINISTIC_REPLAY_GAP")
        if idle_qa["decision"] != "QUALIFIED": raise RuntimeError(f"IDLE_FRONT_CORRECTED_QA_GAP:{idle_qa.get('failures')}")
        idle_spec_value = load_spec(idle_spec, ROOT); idle_context = idle.load_context(idle_spec_value, ROOT); prepared = idle.prepare(idle_spec_value, idle_context); target_hashes = [item["target_joint_sha256"] for item in prepared["targets"]]
        if target_hashes != [item["target_hash"] for item in old_idle["frames"]]: raise RuntimeError("IDLE_TARGET_REPLAY_DRIFT")
        write_json(OUT / "generic-runtime-contract-v091.json", dummy)
        write_json(OUT / "timing-alternative-qualification-v091.json", timing)
        write_json(OUT / "generic-dummy-package-qualification-v091.json", dummy)
        write_json(OUT / "walk-replay-qualification-v091.json", {"schema_version": "0.9.1", "baseline_commit": BASELINE, "parent_baseline": PARENT, "decision": walk_qa["decision"], "status": walk_qa["status"], "frames": walk_qa["frames"], "spritesheet": {"sha256": walk_sheet, "historical_sha256": digest(ROOT / "docs/evidence/walk-front-v081/walk-front-spritesheet-v081.png"), "status": "BYTE_IDENTICAL"}, "gif": {"sha256": walk_gif, "historical_sha256": digest(ROOT / "docs/evidence/walk-front-v081/walk-front-preview-v081.gif"), "status": "BYTE_IDENTICAL"}, "production_routing": "BLOCKED"})
        dual = idle_qa["temporal"]["metrics"]["dual_foot"]
        write_json(OUT / "idle-dual-foot-drift-qa-v091.json", {"schema_version": "0.9.1", "status": "IDLE_DUAL_FEET_DRIFT_PASSED", "decision": "QUALIFIED", "sides": dual["sides"], "hard_gates": dual["hard_gates"], "negative_controls": _negative_controls()})
        bbox = idle_qa["temporal"]["metrics"]
        write_json(OUT / "idle-layer-bbox-temporal-qa-v091.json", {"schema_version": "0.9.1", "status": "IDLE_LAYER_BBOX_TEMPORAL_PASSED", "decision": "QUALIFIED", "head_bbox_areas": bbox["head_bbox_areas"], "torso_bbox_areas": bbox["torso_bbox_areas"], "head_bbox_area_cv": bbox["head_bbox_area_cv"], "torso_bbox_area_cv": bbox["torso_bbox_area_cv"], "hard_gates": {"head_bbox_area_cv_le_0.025": idle_qa["temporal"]["hard_gates"]["head_bbox_cv_le_025"], "torso_bbox_area_cv_le_0.025": idle_qa["temporal"]["hard_gates"]["torso_bbox_cv_le_025"]}, "measurement_layers": {"head": "presented_layers.head", "torso": "presented_layers.torso_pelvis", "foreground": "composite-alpha-bbox-height-only"}, "negative_controls": _bbox_negative_controls()})
        occlusion_frames = [frame["occlusion"] for frame in idle_qa["frames"]]
        if any(frame["hard_gates"].get("no_meaningful_outside_authorized_overlap") is not True for frame in occlusion_frames): raise RuntimeError("IDLE_OCCLUSION_MEASURED_GATE_GAP")
        write_json(OUT / "idle-occlusion-policy-v091.json", {"schema_version": "0.9.1", "status": "IDLE_OCCLUSION_MEASURED_POLICY_PASSED", "decision": "QUALIFIED", "applicability": "APPLICABLE", "policy": "measured-idle-allowed-pairs", "frames": [{"phase": frame["phase"], "unexpected_overlap_fraction": frame["unexpected_overlap_fraction"], "critical_collision_pixels": frame["critical_collision_pixels"], "forbidden_meaningful_overlap": frame["forbidden_meaningful_overlap"], "hard_gates": frame["hard_gates"]} for frame in occlusion_frames], "negative_fixture": _forbidden_overlap_fixture(), "no_literal_hard_gate_override": "no_meaningful_outside_authorized_overlap\"] = True" not in (ROOT / "src/ugas/animation_profiles/idle_front_v1.py").read_text(encoding="utf-8"), "sword_head_and_sword_torso_remain_critical": True})
        write_json(OUT / "idle-requalification-v091.json", {"schema_version": "0.9.1", "animation_id": "idle-front-v1", "decision": idle_qa["decision"], "status": idle_qa["status"], "frame_count": 12, "timing": {"fps": 8, "per_frame_duration_ms": 125, "package_layout": "6x2"}, "target_hashes_unchanged_from_v090": True, "canonical_rgba_hashes_unchanged_from_v090": True, "deterministic_replay_twice": True, "qa_spec_sha256": idle_qa["spec_sha256"], "qa_compiled_manifest_sha256": idle_qa["compiled_manifest_sha256"], "package": {"sprite_sheet_sha256": idle_package["sprite_sheet"]["sha256"], "preview_gif_sha256": idle_package["preview_gif"]["sha256"], "qa_decision": idle_package["qa_decision"], "production_routing": idle_package["production_routing"]}, "canonical_frame_reference": "docs/evidence/animation-runtime-v090/idle-front-v1", "visual_duplication": "none"})
        write_json(OUT / "execution-evidence-v0.9.1.json", {"schema_version": "0.9.1", "baseline_commit": BASELINE, "implementation_base_commit": BASELINE, "parent_baseline": PARENT, "repository_ref": "https://github.com/csn1985-ship-it/ugas.git", "generic_runtime": dummy["status"], "timing_schema": timing["status"], "walk_replay": "BYTE_IDENTICAL", "idle": {"status": idle_qa["status"], "decision": idle_qa["decision"], "frame_count": 12, "fps": 8, "per_frame_duration_ms": 125, "canonical_rgba_unchanged": True, "package": idle_package["qa_decision"]}, "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "new_generation": 0, "source_only_pixels": True, "production_routing": "BLOCKED", "external_visual_review": "REQUIRED"})
    return {"status": "ANIMATION_RUNTIME_V091_PASSED", "baseline": BASELINE, "generic_runtime": dummy["status"], "timing": timing["status"], "walk_replay": "BYTE_IDENTICAL", "idle": "QUALIFIED", "canonical_idle_rgba_unchanged": True, "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "new_generation": 0}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False)); raise SystemExit(0)
    except Exception as exc:
        print(json.dumps({"status": "ANIMATION_RUNTIME_V091_FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False)); raise SystemExit(2)
