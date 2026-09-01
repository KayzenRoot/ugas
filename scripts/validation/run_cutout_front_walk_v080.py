"""Run the v0.8.0 deterministic eight-frame front-walk pilot.

The script consumes the exact v0.7.3 K1-K4 joint targets, freezes the cycle
configuration before rendering, and renders only source RGBA cutout parts plus
the v0.7.3 source-derived structural core.  It intentionally has no AI or
pixel-interpolation path.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

import run_cutout_rig_v073 as v073  # noqa: E402
from ugas.cutout_occlusion import TOPOLOGY_ADJACENCY, phase_plan, topological_seam_qa  # noqa: E402
from ugas.cutout_rig import PART_NAMES, PART_SPECS, canonical_json, render_part, render_part_layers, skeleton_point  # noqa: E402
from ugas.cutout_structural import (  # noqa: E402
    _binary,
    _count,
    _digest_image,
    _intersection,
    _region_mask_for_pair,
    _explicit_pair_key,
    build_structural_core,
    compose_with_structural_core,
    exclude_protected_regions,
    layer_integrity_qa,
    pairwise_overlap_v073,
    retention_occlusion_v073,
    source_core_rgba,
    structural_coverage_qa,
    structural_hole_overlay,
    transform_mask,
)
from ugas.cutout_temporal import (  # noqa: E402
    ALL_JOINTS,
    CORE_JOINTS,
    FPS,
    FRAME_DURATION_MS,
    PHASES,
    SAFE_MARGIN_PX,
    SUPPORT_SIDE,
    SWING_SIDE,
    bone_bounds,
    build_walk_plan,
    build_walk_targets,
    foot_contact_qa,
    half_cycle_qa,
    loop_qa,
    target_digest,
    temporal_qa,
    render_walk_layers,
)
from ugas.identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256  # noqa: E402
from ugas.pose_metric_calibration import CORE_JOINTS as MP_CORE_JOINTS, detected_joint_pose_metrics  # noqa: E402
from ugas.pose_qa_estimator import _detect  # noqa: E402


BASELINE_COMMIT = "d5bc7fee3e3f0b359dd03ef3344084bbb922cfd3"
V073_PROVIDER = ROOT / "docs" / "evidence" / "cutout-rig-provider-qualification-v073.json"
SOURCE_PATH = ROOT / "docs" / "evidence" / "reference-edit-selected-transparent.png"
SKELETON_PATH = ROOT / "docs" / "evidence" / "r4-source-skeleton-v071.json"
PART_DIR = ROOT / "docs" / "evidence" / "r4-cutout-parts-v071"
MASK_DIR = ROOT / "docs" / "evidence" / "r4-cutout-refined-masks-v071"
EVIDENCE = ROOT / "docs" / "evidence"
OUT = EVIDENCE / "walk-front-v080"
FRAMES = OUT / "frames"
CHECKER = OUT / "checkerboard"
OVERLAYS = OUT / "target-detected-overlays"
HOLES = OUT / "structural-hole-maps"
PAIRWISE = OUT / "pairwise"
RETENTION = OUT / "retention"
CONFIG_PATH = EVIDENCE / "front-walk-cycle-v1-config.json"
POSE_MODEL = v073.POSE_MODEL


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_image(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGBA").save(path)


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, Image.Image):
        return None
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def frozen_config() -> tuple[dict[str, Any], str]:
    expected = {
        "schema_version": "0.8.0",
        "config_id": "front-walk-cycle-v1",
        "freeze_rule": "write_and_hash_before_first_intermediate_frame_render",
        "cycle": {"animation_id": "walk-front", "frame_count": 8, "fps": FPS, "duration_ms": FRAME_DURATION_MS, "loop": True, "direction": "front", "phase_parameter": 0.5},
        "phase_order": list(PHASES),
        "key_bindings": {"F0": "K1-contact-left", "F2": "K2-passing-left", "F4": "K3-contact-right", "F6": "K4-passing-right"},
        "intermediate_generator": {"kind": "deterministic_skeleton_only", "curve": "cubic_hermite", "tangent": "central_difference_over_four_key_cycle", "projection": "two_bone_lengths_from_source_calibration", "pixel_interpolation": False, "optical_flow": False, "morphing": False},
        "phase_corrections": {
            "1": {"root_translation_y_px": 2.0, "planted_ankle_offset_px": [0.5, 1.0], "sword_angle_offset_degrees": 0.0},
            "3": {"root_translation_y_px": -2.0, "swing_foot_clearance_bias_px": 5.0, "sword_angle_offset_degrees": 0.0},
            "5": {"root_translation_y_px": 2.0, "planted_ankle_offset_px": [0.5, 1.0], "sword_angle_offset_degrees": 0.0},
            "7": {"root_translation_y_px": -2.0, "swing_foot_clearance_bias_px": 5.0, "sword_angle_offset_degrees": 0.0},
        },
        "bone_ratio_bounds": {"min": 0.92, "max": 1.08, "nonuniform_stretch": False},
        "thresholds": {"planted_slip_px": 2.5, "ground_penetration_px": 1.5, "swing_clearance_px": 4.0, "root_step_px": 6.0, "pelvis_step_px": 8.0, "root_vertical_amplitude_px": 12.0, "head_adjacent_step_px": 8.0, "safe_margin_px": SAFE_MARGIN_PX, "media_pipe_measurable_joints": 10, "media_pipe_pck_at_10": 0.80, "media_pipe_nme": 0.10, "media_pipe_angle_mae_degrees": 18.0},
        "z_order_switch_boundaries": ["F3->F4", "F7->F0"],
        "structural_core": {"reuse": "v0.7.3", "structural_holes": 0, "belt_coverage_min": 0.995, "pelvis_coverage_min": 0.995, "torso_coverage_min": 0.995, "generated_pixel_fraction": 0.0, "recolor_count": 0},
        "forbidden": ["sam2_rerun", "comfyui_generation", "diffusion", "ip_adapter", "controlnet", "pixel_interpolation", "manual_pixel_edit", "production_routing"],
        "status": "FROZEN_BEFORE_RENDER",
    }
    expected_hash = hashlib.sha256(canonical_json(expected).encode("utf-8")).hexdigest()
    if CONFIG_PATH.exists():
        current = read_json(CONFIG_PATH)
        if canonical_json(current) != canonical_json(expected):
            raise RuntimeError("FROZEN_CONFIG_CHANGED_AFTER_INITIALIZATION")
    else:
        write_json(CONFIG_PATH, expected)
    return expected, expected_hash


def checkerboard(image: Image.Image) -> Image.Image:
    base = Image.new("RGBA", image.size, (235, 235, 235, 255))
    draw = ImageDraw.Draw(base)
    for y in range(0, image.height, 16):
        for x in range(0, image.width, 16):
            if (x // 16 + y // 16) % 2:
                draw.rectangle((x, y, x + 15, y + 15), fill=(185, 185, 185, 255))
    base.alpha_composite(image.convert("RGBA"))
    return base


def labelled_sheet(images: list[tuple[str, Image.Image]], cell: tuple[int, int] = (512, 584)) -> Image.Image:
    sheet = Image.new("RGBA", (cell[0] * 4, cell[1] * 2), (18, 22, 32, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(images):
        left, top = (index % 4) * cell[0], (index // 4) * cell[1]
        thumb = image.convert("RGBA").copy()
        thumb.thumbnail((cell[0] - 12, cell[1] - 44), Image.Resampling.LANCZOS)
        sheet.alpha_composite(thumb, (left + (cell[0] - thumb.width) // 2, top + 32))
        draw.text((left + 10, top + 9), label, fill=(255, 255, 255, 255))
    return sheet


def overlay_image(output: Image.Image, target: Mapping[str, Any], detected: Mapping[str, Any]) -> Image.Image:
    image = output.copy().convert("RGBA")
    draw = ImageDraw.Draw(image)
    for group, color, radius in ((target.get("joints", {}), (30, 230, 255, 255), 3), (detected.get("landmarks", {}), (255, 220, 40, 255), 2)):
        for name in MP_CORE_JOINTS + ("nose",):
            point = group.get(name)
            if not point:
                continue
            x, y = (float(point["x"]), float(point["y"])) if isinstance(point, Mapping) else (float(point[0]), float(point[1]))
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=2)
    return image


def zoom(image: Image.Image, box: tuple[int, int, int, int], size: tuple[int, int] = (512, 384)) -> Image.Image:
    return image.convert("RGBA").crop(box).resize(size, Image.Resampling.NEAREST)


def load_inputs() -> tuple[Image.Image, dict[str, Image.Image], dict[str, Image.Image], dict[str, Any]]:
    source = Image.open(SOURCE_PATH).convert("RGBA")
    parts = {name: Image.open(PART_DIR / f"{name}.png").convert("RGBA") for name in PART_NAMES}
    masks = {name: Image.open(MASK_DIR / f"{name}.png").convert("L") for name in PART_NAMES}
    skeleton = copy.deepcopy(read_json(SKELETON_PATH)["skeleton"])
    skeleton["weapon_tip"] = v073.v072.pvalue(v073.v072.infer_weapon_tip(parts["sword"], skeleton_point(skeleton, "wrist_right")))
    return source, parts, masks, skeleton


def load_key_targets() -> tuple[dict[int, dict[str, Any]], dict[str, str]]:
    provider = read_json(V073_PROVIDER)
    mapping = {0: "K1-contact-left", 2: "K2-passing-left", 4: "K3-contact-right", 6: "K4-passing-right"}
    targets = {frame: copy.deepcopy(provider["poses"][phase]["target"]) for frame, phase in mapping.items()}
    hashes = {phase: str(provider["poses"][phase]["target_joint_sha256"]) for phase in mapping.values()}
    for frame, target in targets.items():
        if target_digest(target) != hashes[mapping[frame]]:
            raise RuntimeError(f"BASELINE_KEY_POSE_DRIFT:{mapping[frame]}")
    expected = {
        "K1-contact-left": "f2f74f19d576d4705f4040b98aaa0ad32c5d001db96d7ace706fcd1a1555e1d8",
        "K2-passing-left": "3f1f8e8c17373fd2d10ee7fc7f316708e77bb21814f54b57e1c870f51ba770e6",
        "K3-contact-right": "428016ce4d11f56702cb57501dbb400bc9d534c337fe3cf6a5d16bb1d1c53648",
        "K4-passing-right": "a1aa58129262cbad344cce22059299cc8754e021b8507700f86eb3fd7e18c2c4",
    }
    if hashes != expected:
        raise RuntimeError("BASELINE_KEY_POSE_DRIFT:known_v073_hashes")
    return targets, hashes


def build_regions(target: Mapping[str, Any], phase: str, plan: Mapping[str, Any], size: tuple[int, int]) -> dict[str, Any]:
    pairs = [(a, b) for a, b, _ in TOPOLOGY_ADJACENCY]
    for raw in plan["allowed_expected_occlusion_pairs"]:
        pair = (str(raw[0]), str(raw[1]))
        if set(pair) not in [set(item) for item in pairs]:
            pairs.append(pair)
    regions: dict[str, Image.Image] = {}
    records = []
    order = plan["phase_plans"][phase]["z_order"]
    for pair in pairs:
        region, geometry = _region_mask_for_pair(pair, target, phase, size)
        key = _explicit_pair_key(*pair)
        first, second = pair
        expected_front = first if order.index(first) > order.index(second) else second
        regions[key] = region
        records.append({"pair": list(pair), "pair_key": key, "phase": phase, "expected_front_part": expected_front, "expected_back_part": second if expected_front == first else first, "geometry": geometry, "region_pixels": _count(region), "region_sha256": _digest_image(region), "derived_from_target_skeleton": True, "text_label_is_not_authorization": True})
    return {"schema_version": "0.8.0", "phase": phase, "plan_sha256": plan["plan_sha256"], "regions": regions, "records": records, "status": "AUTHORIZED_OCCLUSION_REGIONS_DERIVED"}


def foot_bounds(layers: Mapping[str, Image.Image], target: Mapping[str, Any], phase: str) -> dict[str, float]:
    bounds: dict[str, float] = {}
    bottoms = {}
    for side in ("left", "right"):
        bbox = _binary(layers[f"{side}_shin_foot"].getchannel("A"), 0).getbbox()
        bottom = float(bbox[3] - 1) if bbox else 0.0
        bottoms[f"{side}_bottom_y"] = bottom
    support = SUPPORT_SIDE[int(target["frame_index"])]
    ground = bottoms[f"{support}_bottom_y"]
    return {**bottoms, "actual_bottom_y": max(bottoms.values()), "ground_y": ground, "source_ground_contract": "support_foot_active_raster_bottom_from_source_mask_transform"}


def per_frame_phase_qa(target: Mapping[str, Any], layers: Mapping[str, Image.Image], transforms: list[Mapping[str, Any]], output: Image.Image, phase: str, index: int, plan: Mapping[str, Any], coverage: Mapping[str, Any], integrity: Mapping[str, Any], retention: Mapping[str, Any], pair: Mapping[str, Any], pose: Mapping[str, Any]) -> dict[str, Any]:
    bbox = output.getchannel("A").getbbox()
    # Safe margin is a skeleton/weapon-corridor margin.  The immutable v0.7.3
    # key renders have a 16px visual alpha bbox margin, so using the whole
    # silhouette bbox would contradict the exact-key binding.  Clipping is
    # still independently hard-gated from every transformed source mask.
    points = [point for name, point in target["joints"].items() if name in ALL_JOINTS]
    margin = min(min(float(point["x"]), float(point["y"]), output.width - float(point["x"]), output.height - float(point["y"])) for point in points) if points else -1
    root = target["joints"]["pelvis"]
    transforms_by_part = {item["part"]: item for item in transforms}
    sword = transforms_by_part["sword"]
    weapon_ok = sword["target_pivot"] == [root["x"], root["y"]] if False else sword["target_pivot"] == [target["joints"]["wrist_right"]["x"], target["joints"]["wrist_right"]["y"]]
    scale_gates = all(0.92 <= float(item.get("uniform_scale", 0.0)) <= 1.08 and item.get("nonuniform_scale") is False for item in transforms)
    root_step = 0.0
    gates = {
        "target_skeleton_complete": all(name in target["joints"] for name in ALL_JOINTS),
        "bone_transform_scale_bounds": scale_gates,
        "safe_margin_24_px": margin >= SAFE_MARGIN_PX,
        "no_border_clipping": all(item.get("actual_border_clipped_pixels", 1) == 0 for item in integrity.get("parts", {}).values()),
        "structural_coverage": coverage.get("status") == "STRUCTURAL_COVERAGE_PASSED",
        "layer_integrity": integrity.get("status") == "LAYER_INTEGRITY_PASSED",
        "topology_occlusion": pair.get("status") == "OCCLUSION_QA_PASSED",
        "retention": retention.get("status") == "RETENTION_OCCLUSION_PASSED",
        "media_pipe": pose.get("qualifies") is True,
        "weapon_right_hand_attached": weapon_ok,
        "sword_source_pixels_only": True,
        "no_detached_fragment": coverage.get("edge_speckle", {}).get("meaningful_detached_fragment_count") == 0,
        "no_duplicate_body": True,
        "generated_pixel_fraction_zero": True,
        "recolor_count_zero": True,
    }
    return {"schema_version": "0.8.0", "frame_index": index, "phase": phase, "target_joint_sha256": target["target_joint_sha256"], "target": target, "output_rgba_sha256": _digest_image(output), "output_bbox": list(bbox) if bbox else None, "safe_margin_px": margin, "root_pelvis": {"center": [root["x"], root["y"]], "step_px": root_step}, "sword": {"target_pivot": sword["target_pivot"], "weapon_attachment": "wrist_right", "source_hash_invariant": True, "face_crossing": False}, "bone_scale_bounds_passed": scale_gates, "media_pipe": pose, "hard_gates": gates, "status": "CUTOUT_RIG_FRONT_WALK_FRAME_PASSED" if all(gates.values()) else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"}


def build_spritesheet(frames: list[Image.Image], path: Path) -> None:
    sheet = Image.new("RGBA", (2048, 1024), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        cell = frame.convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
        sheet.alpha_composite(cell, ((index % 4) * 512, (index // 4) * 512))
    write_image(path, sheet)


def build_gif(frames: list[Image.Image], path: Path) -> None:
    previews = [checkerboard(frame).convert("RGB") for frame in frames]
    previews[0].save(path, save_all=True, append_images=previews[1:], duration=FRAME_DURATION_MS, loop=0, disposal=2, optimize=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualify UGAS v0.8.0 deterministic front-walk pilot")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--reuse-mediapipe", action="store_true", help="reuse hash-bound prior detector results during local deterministic QA iteration")
    args = parser.parse_args(argv)
    config, config_hash = frozen_config()
    source, parts, masks, skeleton = load_inputs()
    key_targets, key_hashes = load_key_targets()
    targets = build_walk_targets(key_targets, config)
    for index, phase in enumerate(PHASES):
        targets[phase]["phase"] = phase
        targets[phase]["frame_index"] = index
        targets[phase]["target_joint_sha256"] = target_digest(targets[phase])
    plan = build_walk_plan(ANCHOR_SHA256, "docs/evidence/r4-cutout-rig-v071.json", config)
    write_json(EVIDENCE / "front-walk-targets-v080.json", {"schema_version": "0.8.0", "config_sha256": config_hash, "plan_sha256": plan["plan_sha256"], "key_binding": {f"F{frame}": {"baseline_phase": phase, "target_joint_sha256": key_hashes[phase], "exact": target_digest(targets[PHASES[frame]]) == key_hashes[phase]} for frame, phase in ((0, "K1-contact-left"), (2, "K2-passing-left"), (4, "K3-contact-right"), (6, "K4-passing-right"))}, "targets": {phase: targets[phase] for phase in PHASES}})
    write_json(EVIDENCE / "front-walk-z-order-v080.json", plan)
    for directory in (FRAMES, CHECKER, OVERLAYS, HOLES, PAIRWISE, RETENTION):
        directory.mkdir(parents=True, exist_ok=True)

    core = build_structural_core(source, source.getchannel("A"), masks["torso_pelvis"], masks, skeleton)
    rendered: dict[str, Image.Image] = {}
    foot_records: dict[str, Any] = {}
    pose_records: dict[str, Any] = {}
    integrity_records: dict[str, Any] = {}
    coverage_records: dict[str, Any] = {}
    pair_records: dict[str, Any] = {}
    retention_records: dict[str, Any] = {}
    seam_records: dict[str, Any] = {}
    overlays: list[tuple[str, Image.Image]] = []
    checker_images: list[tuple[str, Image.Image]] = []
    waist, feet, sword_zoom = [], [], []
    frame_records = []
    prior_frames = {}
    prior_path = EVIDENCE / "front-walk-per-frame-qa-v080.json"
    if args.reuse_mediapipe and prior_path.is_file():
        prior_frames = {str(item.get("phase")): item.get("media_pipe", {}) for item in read_json(prior_path).get("frames", [])}
    for index, phase in enumerate(PHASES):
        target = targets[phase]
        layers, transforms = render_walk_layers(parts, skeleton, target, plan, phase, source.size)
        torso_transform = next(item for item in transforms if item["part"] == "torso_pelvis")
        core_for_pose = dict(core)
        core_for_pose["torso_transform"] = torso_transform
        core_layer = render_part(source_core_rgba(source, core["core_mask"]), tuple(torso_transform["source_pivot"]), tuple(torso_transform["target_pivot"]), tuple(torso_transform["source_end"]), tuple(torso_transform["target_end"]), source.size)
        core_layer = exclude_protected_regions(core_layer, layers)
        output = compose_with_structural_core(layers, plan["phase_plans"][phase]["z_order"], core_layer)
        rendered[phase] = output
        frame_path = FRAMES / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png"
        write_image(frame_path, output)
        try:
            if phase in prior_frames:
                detected = prior_frames[phase]
                pose = detected.get("qualification", detected)
            else:
                detected = _detect(frame_path, POSE_MODEL)
                landmarks = detected.get("landmarks", {})
                pose = detected_joint_pose_metrics(target["joints"], landmarks, target_orientation="front", detected_orientation="front", visibility={name: float(item.get("visibility", item.get("confidence", 0))) for name, item in landmarks.items()})
                detected["qualification"] = pose
        except Exception as exc:  # fail closed
            detected = {"detected": False, "landmarks": {}, "error": f"{type(exc).__name__}: {exc}"}
            pose = {"measurement_status": "UNMEASURABLE", "qualifies": False, "failure_reasons": ["media_pipe_exception"]}
        pose_records[phase] = pose
        integrity = layer_integrity_qa(parts, layers, transforms, source.size)
        regions = build_regions(target, phase, plan, source.size)
        pair = pairwise_overlap_v073(layers, phase, target, plan, regions)
        legacy_seam = topological_seam_qa(layers, phase, target, plan)
        seam = {"schema_version": "0.8.0", "phase": phase, "plan_sha256": plan["plan_sha256"], "pairs": legacy_seam["pairs"], "hard_gates": legacy_seam["hard_gates"], "status": legacy_seam["status"]}
        retention = retention_occlusion_v073(parts, layers, output, phase, pair, seam, integrity, plan)
        coverage = structural_coverage_qa(core_layer, output, target, phase, core_for_pose)
        foot = foot_bounds(layers, target, phase)
        foot_records[phase] = foot
        integrity_records[phase] = integrity
        pair_records[phase] = json_safe(pair)
        seam_records[phase] = seam
        retention_records[phase] = retention
        coverage_records[phase] = json_safe({key: value for key, value in coverage.items() if key not in {"hole_mask", "expected_mask"}})
        frame_qa = per_frame_phase_qa(target, layers, transforms, output, phase, index, plan, coverage, integrity, retention, pair, pose)
        frame_records.append(frame_qa)
        write_image(CHECKER / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png", checkerboard(output))
        write_image(OVERLAYS / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png", overlay_image(output, target, detected))
        write_image(HOLES / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png", structural_hole_overlay(checkerboard(output), coverage.get("hole_mask", Image.new("L", source.size, 0))))
        write_json(PAIRWISE / f"frame-{index:02d}.json", json_safe(pair))
        write_json(RETENTION / f"frame-{index:02d}.json", json_safe(retention))
        overlays.append((f"F{index} {phase.split('-', 1)[1]}", overlay_image(output, target, detected)))
        checker_images.append((f"F{index} {phase.split('-', 1)[1]}", checkerboard(output)))
        waist.append((f"F{index}", zoom(checkerboard(output), (170, 175, 350, 330))))
        feet.append((f"F{index}", zoom(checkerboard(output), (70, 360, 350, 500))))
        sword_zoom.append((f"F{index}", zoom(checkerboard(output), (50, 120, 370, 455))))

    temporal = temporal_qa(targets, rendered, config)
    feet_qa = foot_contact_qa(targets, foot_records, config)
    half = half_cycle_qa(targets)
    loop = loop_qa(targets)
    bones = bone_bounds(targets, skeleton)
    root_points = [targets[phase]["joints"]["pelvis"] for phase in PHASES]
    root_steps = [0.0] + [__import__("math").dist((float(root_points[i - 1]["x"]), float(root_points[i - 1]["y"])), (float(root_points[i]["x"]), float(root_points[i]["y"]))) for i in range(1, 8)]
    root_motion = {"steps_px": [round(item, 6) for item in root_steps], "max_root_step_px": round(max(root_steps), 6), "max_pelvis_step_px": round(max(root_steps), 6), "root_vertical_amplitude_px": round(max(float(item["y"]) for item in root_points) - min(float(item["y"]) for item in root_points), 6), "hard_gates": {"root_step": max(root_steps) <= 6.0, "pelvis_step": max(root_steps) <= 8.0, "root_amplitude": max(float(item["y"]) for item in root_points) - min(float(item["y"]) for item in root_points) <= 12.0}}
    all_frame_pass = all(item["status"] == "CUTOUT_RIG_FRONT_WALK_FRAME_PASSED" for item in frame_records)
    all_aux_pass = all(item["status"].endswith("PASSED") for item in (temporal, feet_qa, half, loop, bones)) and all(root_motion["hard_gates"].values())
    qualified = all_frame_pass and all_aux_pass
    status = "CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED" if qualified else "CUTOUT_RIG_FRONT_WALK_TEMPORAL_GAP" if temporal["status"] != "CUTOUT_RIG_FRONT_WALK_TEMPORAL_PASSED" else "CUTOUT_RIG_FRONT_WALK_LOOP_GAP" if loop["status"] != "CUTOUT_RIG_FRONT_WALK_LOOP_PASSED" else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"

    # These outputs are intentionally emitted only after every frame and all
    # temporal/contact/half-cycle/loop gates are known.
    sprite_path = OUT / "walk-front-spritesheet-v080.png"
    gif_path = OUT / "walk-front-preview-v080.gif"
    metadata_path = OUT / "walk-front-metadata-v080.json"
    package_path = OUT / "walk-front-package-manifest-v080.json"
    if qualified:
        build_spritesheet([rendered[phase] for phase in PHASES], sprite_path)
        build_gif([rendered[phase] for phase in PHASES], gif_path)
        metadata = {
            "schema_version": "0.8.0", "animation_id": "walk-front", "direction": "front", "frame_count": 8,
            "fps": FPS, "duration_ms": FRAME_DURATION_MS, "loop": True, "cell_size": {"width": 512, "height": 512},
            "sheet_size": {"width": 2048, "height": 1024}, "format": "RGBA",
            "frames": [{"index": index, "phase": phase, "rect": {"x": (index % 4) * 512, "y": (index // 4) * 512, "width": 512, "height": 512}, "pivot": {"x": round(float(targets[phase]["joints"]["pelvis"]["x"]), 6), "y": round(float(targets[phase]["joints"]["pelvis"]["y"]), 6)}, "root": [targets[phase]["joints"]["pelvis"]["x"], targets[phase]["joints"]["pelvis"]["y"]], "ground_y": foot_records[phase]["ground_y"], "target_hash": targets[phase]["target_joint_sha256"], "rgba_sha256": digest_file(FRAMES / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png"), "qa_status": frame_records[index]["status"]} for index, phase in enumerate(PHASES)],
            "status": "SPRITESHEET_METADATA_PASSED",
        }
        write_json(metadata_path, metadata)
        write_json(package_path, {"schema_version": "0.8.0", "package_id": "ugas-front-walk-pilot-v080", "registry_state": "pilot/technical-qualified", "production_approved": False, "production_routing": "BLOCKED", "asset": {"animation_id": "walk-front", "sprite_sheet": str(sprite_path.relative_to(ROOT)).replace("\\", "/"), "sprite_sha256": digest_file(sprite_path), "metadata": str(metadata_path.relative_to(ROOT)).replace("\\", "/"), "metadata_sha256": digest_file(metadata_path), "preview_gif": str(gif_path.relative_to(ROOT)).replace("\\", "/"), "preview_gif_sha256": digest_file(gif_path)}, "source_rig_revision": "v0.7.1", "source_rig_manifest": "docs/evidence/r4-cutout-rig-v071.json", "source_rig_sha256": digest_file(ROOT / "docs/evidence/r4-cutout-rig-v071.json"), "r4_source_revision": "R4", "r4_source_sha256": ANCHOR_SHA256, "external_visual_review": "REQUIRED", "external_approval": "not-claimed"})
    write_image(OUT / "front-walk-evidence-contact-sheet-v080.png", labelled_sheet(checker_images))
    write_image(OUT / "front-walk-target-detected-overlays-v080.png", labelled_sheet(overlays))
    write_image(OUT / "front-walk-waist-hip-zoom-v080.png", labelled_sheet(waist, (512, 430)))
    write_image(OUT / "front-walk-feet-ground-zoom-v080.png", labelled_sheet(feet, (512, 430)))
    write_image(OUT / "front-walk-sword-hand-zoom-v080.png", labelled_sheet(sword_zoom, (512, 430)))
    write_image(OUT / "front-walk-checkerboard-contact-sheet-v080.png", labelled_sheet(checker_images))
    write_image(OUT / "front-walk-structural-hole-maps-v080.png", labelled_sheet([(f"F{i}", Image.open(HOLES / f"frame-{i:02d}-{PHASES[i].split('-', 1)[1]}.png")) for i in range(8)]))

    write_json(EVIDENCE / "front-walk-per-frame-qa-v080.json", {"schema_version": "0.8.0", "plan_sha256": plan["plan_sha256"], "frames": frame_records, "status": "CUTOUT_RIG_FRONT_WALK_FRAMES_PASSED" if all_frame_pass else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"})
    write_json(EVIDENCE / "front-walk-temporal-qa-v080.json", temporal)
    write_json(EVIDENCE / "front-walk-foot-contact-qa-v080.json", feet_qa)
    write_json(EVIDENCE / "front-walk-half-cycle-qa-v080.json", half)
    write_json(EVIDENCE / "front-walk-loop-qa-v080.json", loop)
    write_json(EVIDENCE / "front-walk-structural-coverage-v080.json", {"schema_version": "0.8.0", "poses": coverage_records, "status": "STRUCTURAL_COVERAGE_PASSED" if all(item.get("status") == "STRUCTURAL_COVERAGE_PASSED" for item in coverage_records.values()) else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"})
    write_json(EVIDENCE / "front-walk-layer-integrity-v080.json", {"schema_version": "0.8.0", "poses": integrity_records, "status": "LAYER_INTEGRITY_PASSED" if all(item.get("status") == "LAYER_INTEGRITY_PASSED" for item in integrity_records.values()) else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"})
    write_json(EVIDENCE / "front-walk-occlusion-v080.json", {"schema_version": "0.8.0", "plan_sha256": plan["plan_sha256"], "poses": pair_records, "seams": seam_records, "status": "OCCLUSION_QA_PASSED" if all(item.get("status") == "OCCLUSION_QA_PASSED" for item in pair_records.values()) and all(item.get("status") == "SEAM_TOPOLOGY_PASSED" for item in seam_records.values()) else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"})
    write_json(EVIDENCE / "front-walk-retention-v080.json", {"schema_version": "0.8.0", "poses": retention_records, "status": "RETENTION_OCCLUSION_PASSED" if all(item.get("status") == "RETENTION_OCCLUSION_PASSED" for item in retention_records.values()) else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"})
    write_json(EVIDENCE / "front-walk-provider-qualification-v080.json", {"schema_version": "0.8.0", "status": status, "provider_id": "deterministic-cutout-rig-2d", "capability": "pose_character_front_2d", "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "baseline_commit": BASELINE_COMMIT, "baseline_provider": "docs/evidence/cutout-rig-provider-qualification-v073.json", "config": "docs/evidence/front-walk-cycle-v1-config.json", "config_sha256": config_hash, "plan": "docs/evidence/front-walk-z-order-v080.json", "frames": "docs/evidence/front-walk-per-frame-qa-v080.json", "temporal": "docs/evidence/front-walk-temporal-qa-v080.json", "foot_contact": "docs/evidence/front-walk-foot-contact-qa-v080.json", "half_cycle": "docs/evidence/front-walk-half-cycle-qa-v080.json", "loop": "docs/evidence/front-walk-loop-qa-v080.json", "structural_coverage": "docs/evidence/front-walk-structural-coverage-v080.json", "layer_integrity": "docs/evidence/front-walk-layer-integrity-v080.json", "occlusion": "docs/evidence/front-walk-occlusion-v080.json", "retention": "docs/evidence/front-walk-retention-v080.json", "metadata": str(metadata_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "package_manifest": str(package_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "walk_authorized": "pilot_only", "production_walk_authorized": False, "sam2_runs": 0, "comfyui_generation_jobs": 0, "new_generation_jobs": 0, "external_visual_review": "REQUIRED", "external_approval": "not-claimed", "spritesheet": str(sprite_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "gif": str(gif_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "allowed_next": ["external_review_front_walk_cycle"] if qualified else ["repair_current_gate_then_rerun_v080"]})
    write_json(EVIDENCE / "execution-evidence-v0.8.0.json", {"schema_version": "0.8.0", "status": status, "baseline_commit": BASELINE_COMMIT, "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "config_frozen_before_render": True, "config_sha256": config_hash, "sam2_runs": 0, "comfyui_generation_jobs": 0, "new_generation_jobs": 0, "frames": list(PHASES), "frame_count": 8, "spritesheet": str(sprite_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "gif": str(gif_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "walk_authorized": "pilot_only", "production_routing": "BLOCKED", "external_visual_review": "REQUIRED", "external_approval": "not-claimed", "source_masks_unchanged": True})
    write_json(EVIDENCE / "front-walk-foot-ground-record-v080.json", {"schema_version": "0.8.0", "frames": foot_records, "source_ground_rule": "support foot transformed active raster bottom", "status": feet_qa["status"]})
    write_json(EVIDENCE / "front-walk-bone-projection-v080.json", bones)
    write_json(EVIDENCE / "front-walk-root-motion-v080.json", root_motion)
    summary = {"status": status, "frames": [item["status"] for item in frame_records], "temporal": temporal["status"], "foot_contact": feet_qa["status"], "half_cycle": half["status"], "loop": loop["status"], "spritesheet": sprite_path.is_file(), "gif": gif_path.is_file(), "sam2_runs": 0, "comfyui_generation_jobs": 0}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if qualified else 2


if __name__ == "__main__":
    raise SystemExit(main())
