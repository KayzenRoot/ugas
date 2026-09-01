"""Run the strict v0.8.1 correction of the same deterministic front walk.

The runner consumes the immutable v0.7.3 key targets and v0.7.1 cutout
parts, performs skeleton-only smoothing before rendering, applies one frozen
global presentation transform, and writes visual evidence only for the
existing F0..F7 front cycle.  It never calls SAM2, ComfyUI, diffusion, or a
new generation provider.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

import run_cutout_front_walk_v080 as v080  # noqa: E402
import run_cutout_rig_v073 as v073  # noqa: E402
from ugas.cutout_occlusion import TOPOLOGY_ADJACENCY, topological_seam_qa  # noqa: E402
from ugas.cutout_rig import PART_NAMES, canonical_json, render_part, skeleton_point  # noqa: E402
from ugas.cutout_structural import (  # noqa: E402
    _binary,
    _count,
    _digest_image,
    _explicit_pair_key,
    _region_mask_for_pair,
    build_structural_core,
    compose_with_structural_core,
    exclude_protected_regions,
    layer_integrity_qa,
    pairwise_overlap_v073,
    retention_occlusion_v073,
    source_core_rgba,
    structural_coverage_qa,
    structural_hole_overlay,
)
from ugas.cutout_temporal_v081 import (  # noqa: E402
    ALL_JOINTS,
    ANGULAR_ACCELERATION_MAX,
    FRAME_DURATION_MS,
    FPS,
    PHASES,
    SAFE_MARGIN_PX,
    SUPPORT_SIDE,
    SWING_SIDE,
    actual_alpha_safe_margin,
    apply_presentation_transform,
    bone_bounds_v081,
    build_walk_plan_v081,
    build_walk_targets_v081,
    duplicate_body_measure,
    foot_contact_qa_v081,
    hard_gate_proof_sources,
    loop_qa_v081,
    measure_foot_frame,
    presentation_plan_from_extents,
    target_digest,
    temporal_qa_v081,
    transform_target_for_presentation,
)
from ugas.identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256  # noqa: E402
from ugas.pose_metric_calibration import CORE_JOINTS as MP_CORE_JOINTS, detected_joint_pose_metrics  # noqa: E402
from ugas.pose_qa_estimator import _detect  # noqa: E402


BASELINE_COMMIT = "d634d69d3cceac239d8eb5fe8623c764eb6c6b53"
PARENT_V073_COMMIT = "d5bc7fee3e3f0b359dd03ef3344084bbb922cfd3"
V073_PROVIDER = ROOT / "docs" / "evidence" / "cutout-rig-provider-qualification-v073.json"
SOURCE_PATH = ROOT / "docs" / "evidence" / "reference-edit-selected-transparent.png"
SKELETON_PATH = ROOT / "docs" / "evidence" / "r4-source-skeleton-v071.json"
PART_DIR = ROOT / "docs" / "evidence" / "r4-cutout-parts-v071"
MASK_DIR = ROOT / "docs" / "evidence" / "r4-cutout-refined-masks-v071"
EVIDENCE = ROOT / "docs" / "evidence"
OUT = EVIDENCE / "walk-front-v081"
FRAMES = OUT / "frames"
CHECKER = OUT / "checkerboard"
OVERLAYS = OUT / "target-detected-overlays"
GROUND = OUT / "ground-line-overlays"
HOLES = OUT / "structural-hole-maps"
PAIRWISE = OUT / "pairwise"
RETENTION = OUT / "retention"
CONFIG_PATH = EVIDENCE / "front-walk-cycle-v1-config-v081.json"
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
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, Image.Image):
        return None
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def frozen_config() -> tuple[dict[str, Any], str]:
    baseline = read_json(EVIDENCE / "front-walk-per-frame-qa-v080.json")
    source_extents = [item["output_bbox"] for item in baseline["frames"]]
    presentation = presentation_plan_from_extents(source_extents, (512, 512), scale=0.90)
    expected = {
        "schema_version": "0.8.1",
        "config_id": "front-walk-cycle-v1-v081",
        "freeze_rule": "write_and_hash_before_smoothing_parameters_or_first_render",
        "cycle": {"animation_id": "walk-front", "frame_count": 8, "fps": FPS, "duration_ms": FRAME_DURATION_MS, "loop": True, "direction": "front", "phase_parameter": 0.5},
        "phase_order": list(PHASES),
        "key_bindings": {"F0": "K1-contact-left", "F2": "K2-passing-left", "F4": "K3-contact-right", "F6": "K4-passing-right"},
        "intermediate_generator": {
            "kind": "deterministic_skeleton_only",
            "curve": "cubic_hermite",
            "tangent": "central_difference_over_four_key_cycle",
            "projection": "source_calibrated_bone_ratio_bounds",
            "smoothing": "bounded_deterministic_coordinate_descent",
            "pixel_interpolation": False,
            "optical_flow": False,
            "image_inputs_used_for_smoothing": False,
        },
        "phase_corrections": {
            "1": {"root_translation_y_px": 2.0, "planted_ankle_offset_px": [0.5, 1.0], "sword_angle_offset_degrees": 0.0},
            "2": {"support_ground_calibration_offset_px": 3.0, "swing_foot_clearance_bias_px": 5.0, "swing_ground_depth_offset_px": 23.0, "sword_angle_offset_degrees": 0.0},
            "3": {"root_translation_y_px": -2.0, "swing_foot_clearance_bias_px": 5.0, "swing_ground_depth_offset_px": 23.0, "sword_angle_offset_degrees": 0.0},
            "5": {"root_translation_y_px": 2.0, "planted_ankle_offset_px": [0.5, 1.0], "sword_angle_offset_degrees": 0.0},
            "6": {"swing_foot_clearance_bias_px": 5.0, "swing_ground_depth_offset_px": 23.0, "sword_angle_offset_degrees": 0.0},
            "7": {"root_translation_y_px": -2.0, "swing_foot_clearance_bias_px": 5.0, "swing_ground_depth_offset_px": 23.0, "sword_angle_offset_degrees": 0.0},
        },
        "bone_ratio_bounds": {"min": 0.92, "max": 1.08, "nonuniform_stretch": False},
        "smoothing": {
            "objective": "minimize_cyclic_angular_acceleration_with_bounded_joint_adjustment_and_bone_ratio_penalty",
            "weights": {"acceleration_excess": 100.0, "total_acceleration": 0.0001, "adjacent_delta_guard": 1000.0, "bone_ratio_penalty": 100000.0},
            "joint_adjustment_bound_px": 3.0,
            "step_schedule_px": [2.0, 1.0, 0.5, 0.25, 0.1],
            "max_iterations": 30,
            "angular_acceleration_threshold_degrees_per_frame2": ANGULAR_ACCELERATION_MAX,
            "relative_bone_ratio_bounds": {"min": 0.94, "max": 1.04},
            "optimized_joints": ["knee_left", "knee_right", "elbow_left", "elbow_right"],
            "optimized_frames": [1, 3, 5, 7],
        },
        "thresholds": {
            "planted_slip_px": 2.5,
            "ground_penetration_px": 1.5,
            "swing_clearance_px": 4.0,
            "adjacent_angle_delta_max_degrees": 35.0,
            "angular_acceleration_max_degrees_per_frame2": ANGULAR_ACCELERATION_MAX,
            "head_torso_bbox_cv_max": 0.04,
            "root_step_px": 6.0,
            "pelvis_step_px": 8.0,
            "root_vertical_amplitude_px": 12.0,
            "head_adjacent_step_px": 8.0,
            "safe_margin_px": SAFE_MARGIN_PX,
            "media_pipe_measurable_joints": 10,
            "media_pipe_pck_at_10": 0.80,
            "media_pipe_nme": 0.10,
            "media_pipe_angle_mae_degrees": 18.0,
        },
        "presentation_transform": presentation,
        "z_order_switch_boundaries": ["F3->F4", "F7->F0"],
        "structural_core": {"reuse": "v0.7.3", "structural_holes": 0, "belt_coverage_min": 0.995, "pelvis_coverage_min": 0.995, "torso_coverage_min": 0.995, "generated_pixel_fraction": 0.0, "recolor_count": 0},
        "provenance": {"generated_pixel_fraction": 0.0, "recolor_count": 0, "sword_source_pixels_only": True, "no_duplicate_body": "measured_8_connected_alpha_components"},
        "forbidden": ["sam2_rerun", "comfyui_generation", "diffusion", "ip_adapter", "controlnet", "pixel_interpolation", "manual_pixel_edit", "production_routing"],
        "status": "FROZEN_BEFORE_RENDER",
    }
    config_hash = hashlib.sha256(canonical_json(expected).encode("utf-8")).hexdigest()
    if CONFIG_PATH.exists() and canonical_json(read_json(CONFIG_PATH)) != canonical_json(expected):
        raise RuntimeError("FROZEN_CONFIG_CHANGED_AFTER_INITIALIZATION")
    if not CONFIG_PATH.exists():
        write_json(CONFIG_PATH, expected)
    return expected, config_hash


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


def ground_line_overlay(output: Image.Image, target: Mapping[str, Any], record: Mapping[str, Any]) -> Image.Image:
    image = output.copy().convert("RGBA")
    draw = ImageDraw.Draw(image)
    colors = {"left": (50, 230, 120, 255), "right": (255, 130, 40, 255)}
    for side in ("left", "right"):
        item = record["feet"][side]
        y = float(item["projected_ground_y"])
        color = colors[side]
        draw.line((0, y, image.width - 1, y), fill=color, width=2)
        ankle = target["joints"][f"ankle_{side}"]
        ax, ay = float(ankle["x"]), float(ankle["y"])
        sx, sy = ax, float(item["actual_sole_y"])
        ex, ey = ax, float(item["expected_sole_y"])
        draw.ellipse((ax - 4, ay - 4, ax + 4, ay + 4), outline=(255, 255, 255, 255), width=2)
        draw.ellipse((sx - 3, sy - 3, sx + 3, sy + 3), outline=(255, 40, 210, 255), width=2)
        draw.ellipse((ex - 2, ey - 2, ex + 2, ey + 2), outline=(40, 180, 255, 255), width=2)
        draw.text((8 if side == "left" else 260, max(2, int(y) - 16)), f"{side} ground={y:.1f} sole={sy:.1f}", fill=color)
    return image


def alpha_bbox_overlay(output: Image.Image, qa: Mapping[str, Any]) -> Image.Image:
    image = output.copy().convert("RGBA")
    draw = ImageDraw.Draw(image)
    bbox = qa.get("alpha_bbox")
    if bbox:
        draw.rectangle(tuple(bbox), outline=(255, 40, 40, 255), width=2)
        draw.text((8, 8), f"alpha bbox {bbox} min={float(qa['min_margin_px']):.1f}px", fill=(255, 40, 40, 255))
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
    expected = {
        "K1-contact-left": "f2f74f19d576d4705f4040b98aaa0ad32c5d001db96d7ace706fcd1a1555e1d8",
        "K2-passing-left": "3f1f8e8c17373fd2d10ee7fc7f316708e77bb21814f54b57e1c870f51ba770e6",
        "K3-contact-right": "428016ce4d11f56702cb57501dbb400bc9d534c337fe3cf6a5d16bb1d1c53648",
        "K4-passing-right": "a1aa58129262cbad344cce22059299cc8754e021b8507700f86eb3fd7e18c2c4",
    }
    for frame, target in targets.items():
        if target_digest(target) != hashes[mapping[frame]] or hashes[mapping[frame]] != expected[mapping[frame]]:
            raise RuntimeError(f"BASELINE_KEY_POSE_DRIFT:{mapping[frame]}")
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
        expected_front = pair[0] if order.index(pair[0]) > order.index(pair[1]) else pair[1]
        regions[key] = region
        records.append({"pair": list(pair), "pair_key": key, "phase": phase, "expected_front_part": expected_front, "expected_back_part": pair[1] if expected_front == pair[0] else pair[0], "geometry": geometry, "region_pixels": _count(region), "region_sha256": _digest_image(region), "derived_from_target_skeleton": True, "text_label_is_not_authorization": True})
    return {"schema_version": "0.8.1", "phase": phase, "plan_sha256": plan["plan_sha256"], "regions": regions, "records": records, "status": "AUTHORIZED_OCCLUSION_REGIONS_DERIVED"}


def presented_layer_qa(canonical_layers: Mapping[str, Image.Image], presented_layers: Mapping[str, Image.Image], presentation: Mapping[str, Any]) -> dict[str, Any]:
    scale = float(presentation["uniform_scale"])
    records: dict[str, Any] = {}
    for name in PART_NAMES:
        before = _count(_binary(canonical_layers[name].getchannel("A"), 64))
        after = _count(_binary(presented_layers[name].getchannel("A"), 64))
        expected = before * scale * scale
        bbox = presented_layers[name].getchannel("A").getbbox()
        border = sum(1 for y in range(presented_layers[name].height) for x in range(presented_layers[name].width) if presented_layers[name].getchannel("A").getpixel((x, y)) > 64 and (x in (0, presented_layers[name].width - 1) or y in (0, presented_layers[name].height - 1)))
        error = abs(after - expected) / max(1.0, expected)
        records[name] = {"canonical_active_pixels": before, "presented_active_pixels": after, "expected_presented_active_pixels": round(expected, 6), "raster_area_error": round(error, 6), "presented_bbox": list(bbox) if bbox else None, "presented_border_pixels": border, "hard_gates": {"uniform_transform_area": error <= 0.12, "no_presented_border_clipping": border == 0}}
    passed = all(all(item["hard_gates"].values()) for item in records.values())
    return {"schema_version": "0.8.1", "presentation_scale": scale, "parts": records, "status": "PRESENTATION_TRANSFORM_PASSED" if passed else "CUTOUT_RIG_FRONT_WALK_CANVAS_FIT_GAP"}


def root_motion(targets: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    points = [targets[phase]["joints"]["pelvis"] for phase in PHASES]
    steps = [math.dist((float(points[index - 1]["x"]), float(points[index - 1]["y"])), (float(points[index]["x"]), float(points[index]["y"]))) for index in range(1, len(points))]
    max_step = max(steps, default=0.0)
    amplitude = max(float(item["y"]) for item in points) - min(float(item["y"]) for item in points)
    gates = {"root_step": max_step <= 6.0, "pelvis_step": max_step <= 8.0, "root_amplitude": amplitude <= 12.0}
    return {"schema_version": "0.8.1", "steps_px": [0.0] + [round(value, 6) for value in steps], "max_root_step_px": round(max_step, 6), "max_pelvis_step_px": round(max_step, 6), "root_vertical_amplitude_px": round(amplitude, 6), "hard_gates": gates, "status": "ROOT_MOTION_PASSED" if all(gates.values()) else "CUTOUT_RIG_FRONT_WALK_TEMPORAL_GAP"}


def temporal_trajectory_image(temporal: Mapping[str, Any]) -> Image.Image:
    image = Image.new("RGBA", (1200, 680), (18, 22, 32, 255))
    draw = ImageDraw.Draw(image)
    left, top, width, height = 90, 50, 1040, 510
    draw.rectangle((left, top, left + width, top + height), outline=(160, 170, 190, 255), width=2)
    max_value = max(30.0, float(temporal.get("max_angular_acceleration_degrees_per_frame2", 0.0)))
    y_gate = top + height - (ANGULAR_ACCELERATION_MAX / max_value) * height
    draw.line((left, y_gate, left + width, y_gate), fill=(255, 70, 70, 255), width=3)
    draw.text((left + 10, max(2, int(y_gate) - 20)), "hard limit 25 deg/frame2", fill=(255, 120, 120, 255))
    by_joint: dict[str, list[float]] = {}
    for item in temporal.get("angular_acceleration_records", []):
        by_joint.setdefault(str(item["joint"]), []).append(float(item["value"]))
    colors = [(40, 210, 255, 255), (255, 190, 50, 255), (110, 240, 120, 255), (230, 100, 255, 255)]
    for index, (joint, values) in enumerate(sorted(by_joint.items())):
        points = []
        for frame, value in enumerate(values):
            x = left + frame * width / 7.0
            y = top + height - min(value, max_value) / max_value * height
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=colors[index % len(colors)], width=2)
        draw.text((left + 10 + (index % 4) * 240, top + height + 20 + (index // 4) * 18), joint, fill=colors[index % len(colors)])
    for frame in range(8):
        x = left + frame * width / 7.0
        draw.text((int(x) - 10, top + height + 4), f"F{frame}", fill=(220, 225, 235, 255))
    draw.text((left, 18), f"v0.8.1 cyclic angular acceleration max={float(temporal.get('max_angular_acceleration_degrees_per_frame2', 0.0)):.3f}", fill=(240, 240, 245, 255))
    return image


def build_spritesheet(frames: list[Image.Image], path: Path) -> None:
    sheet = Image.new("RGBA", (2048, 1024), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame.convert("RGBA"), ((index % 4) * 512, (index // 4) * 512))
    write_image(path, sheet)


def build_gif(frames: list[Image.Image], path: Path) -> None:
    previews = [checkerboard(frame).convert("RGB") for frame in frames]
    previews[0].save(path, save_all=True, append_images=previews[1:], duration=FRAME_DURATION_MS, loop=0, disposal=2, optimize=False)


def _remove_package_outputs() -> None:
    for name in ("walk-front-spritesheet-v081.png", "walk-front-preview-v081.gif", "walk-front-metadata-v081.json", "walk-front-package-manifest-v081.json"):
        path = OUT / name
        if path.exists():
            path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualify the UGAS v0.8.1 deterministic front-walk correction")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    config, config_hash = frozen_config()
    _remove_package_outputs()
    source, parts, masks, skeleton = load_inputs()
    key_targets, key_hashes = load_key_targets()
    targets, smoothing, initial_targets = build_walk_targets_v081(key_targets, config)
    plan = build_walk_plan_v081(ANCHOR_SHA256, "docs/evidence/r4-cutout-rig-v071.json", config)
    presentation = config["presentation_transform"]
    presentation_hash = str(presentation["sha256"])
    presented_targets = {phase: transform_target_for_presentation(targets[phase], presentation) for phase in PHASES}
    key_binding = {}
    for frame, key_name in ((0, "K1-contact-left"), (2, "K2-passing-left"), (4, "K3-contact-right"), (6, "K4-passing-right")):
        phase = PHASES[frame]
        key_binding[f"F{frame}"] = {"baseline_phase": key_name, "canonical_target_joint_sha256": key_hashes[key_name], "canonical_exact": target_digest(targets[phase]) == key_hashes[key_name], "presentation_target_joint_sha256": presented_targets[phase]["presentation_target_joint_sha256"], "presentation_transform_sha256": presentation_hash}
    write_json(EVIDENCE / "front-walk-temporal-pre-smoothing-v081.json", {"schema_version": "0.8.1", "phase_order": list(PHASES), "status": "SKELETON_PRE_SMOOTHING_RECORDED", "image_inputs_used": False, "angular_acceleration_records": smoothing["pre_smoothing_acceleration_records"], "max_angular_acceleration_degrees_per_frame2": smoothing["pre_smoothing_max_angular_acceleration_degrees_per_frame2"], "optimizer_config_sha256": smoothing["optimizer_config_sha256"]})
    write_json(EVIDENCE / "front-walk-targets-v081.json", {"schema_version": "0.8.1", "config_sha256": config_hash, "plan_sha256": plan["plan_sha256"], "presentation_transform_sha256": presentation_hash, "key_binding": key_binding, "smoothing": {key: value for key, value in smoothing.items() if key not in {"pre_smoothing_acceleration_records", "post_smoothing_acceleration_records"}}, "canonical_targets": {phase: targets[phase] for phase in PHASES}, "presentation_targets": presented_targets})
    write_json(EVIDENCE / "front-walk-z-order-v081.json", plan)
    for directory in (FRAMES, CHECKER, OVERLAYS, GROUND, HOLES, PAIRWISE, RETENTION):
        directory.mkdir(parents=True, exist_ok=True)

    core = build_structural_core(source, source.getchannel("A"), masks["torso_pelvis"], masks, skeleton)
    canonical_rendered: dict[str, Image.Image] = {}
    rendered: dict[str, Image.Image] = {}
    presented_layers_by_phase: dict[str, dict[str, Image.Image]] = {}
    layer_bboxes: dict[str, dict[str, Image.Image]] = {}
    foot_records: dict[str, Any] = {}
    pose_records: dict[str, Any] = {}
    integrity_records: dict[str, Any] = {}
    presentation_records: dict[str, Any] = {}
    coverage_records: dict[str, Any] = {}
    pair_records: dict[str, Any] = {}
    retention_records: dict[str, Any] = {}
    seam_records: dict[str, Any] = {}
    frame_records: list[dict[str, Any]] = []
    overlays: list[tuple[str, Image.Image]] = []
    checker_images: list[tuple[str, Image.Image]] = []
    ground_images: list[tuple[str, Image.Image]] = []
    bbox_images: list[tuple[str, Image.Image]] = []
    waist, feet, sword_zoom = [], [], []
    for index, phase in enumerate(PHASES):
        target = targets[phase]
        target_presented = presented_targets[phase]
        layers, transforms = v080.render_walk_layers(parts, skeleton, target, plan, phase, source.size)
        transforms = [dict(item, source_part_rgba_sha256=hashlib.sha256(parts[item["part"]].tobytes()).hexdigest(), pixel_operation="source_affine_resample") for item in transforms]
        torso_transform = next(item for item in transforms if item["part"] == "torso_pelvis")
        core_for_pose = dict(core)
        core_for_pose["torso_transform"] = torso_transform
        core_layer = render_part(source_core_rgba(source, core["core_mask"]), tuple(torso_transform["source_pivot"]), tuple(torso_transform["target_pivot"]), tuple(torso_transform["source_end"]), tuple(torso_transform["target_end"]), source.size)
        core_layer = exclude_protected_regions(core_layer, layers)
        canonical_output = compose_with_structural_core(layers, plan["phase_plans"][phase]["z_order"], core_layer)
        presented_layers = {name: apply_presentation_transform(image, presentation) for name, image in layers.items()}
        presented_core = apply_presentation_transform(core_layer, presentation)
        output = apply_presentation_transform(canonical_output, presentation)
        canonical_rendered[phase] = canonical_output
        rendered[phase] = output
        presented_layers_by_phase[phase] = presented_layers
        layer_bboxes[phase] = {"head": presented_layers["head"], "torso_pelvis": presented_layers["torso_pelvis"]}
        frame_path = FRAMES / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png"
        write_image(frame_path, output)
        try:
            detected = _detect(frame_path, POSE_MODEL)
            landmarks = detected.get("landmarks", {})
            pose = detected_joint_pose_metrics(target_presented["joints"], landmarks, target_orientation="front", detected_orientation="front", visibility={name: float(item.get("visibility", item.get("confidence", 0))) for name, item in landmarks.items()})
            detected["qualification"] = pose
        except Exception as exc:
            detected = {"detected": False, "landmarks": {}, "error": f"{type(exc).__name__}: {exc}"}
            pose = {"measurement_status": "UNMEASURABLE", "qualifies": False, "failure_reasons": ["media_pipe_exception"]}
        pose_records[phase] = pose
        integrity = layer_integrity_qa(parts, layers, transforms, source.size)
        presentation_qa = presented_layer_qa(layers, presented_layers, presentation)
        regions = build_regions(target, phase, plan, source.size)
        pair = pairwise_overlap_v073(layers, phase, target, plan, regions)
        legacy_seam = topological_seam_qa(layers, phase, target, plan)
        seam = {"schema_version": "0.8.1", "phase": phase, "plan_sha256": plan["plan_sha256"], "pairs": legacy_seam["pairs"], "hard_gates": legacy_seam["hard_gates"], "status": legacy_seam["status"]}
        retention = retention_occlusion_v073(parts, layers, canonical_output, phase, pair, seam, integrity, plan)
        coverage = structural_coverage_qa(core_layer, canonical_output, target, phase, core_for_pose)
        foot = measure_foot_frame(target, layers, presented_layers, transforms, parts, skeleton, config, presentation)
        alpha_qa = actual_alpha_safe_margin(output)
        duplicate = duplicate_body_measure(output)
        transforms_by_part = {item["part"]: item for item in transforms}
        proof = hard_gate_proof_sources(parts, transforms_by_part)
        source_only = proof["sword_source_only"]["source_part_rgba_sha256"] == transforms_by_part["sword"]["source_part_rgba_sha256"] and proof["sword_source_only"]["operation"] in proof["operation_allowlist"]
        duplicate_ok = duplicate["gate"]
        support = foot["feet"][foot["support_side"]]
        swing = foot["feet"].get(foot["swing_side"]) if foot["swing_side"] else None
        scale_ok = all(0.92 <= float(item.get("uniform_scale", 0.0)) <= 1.08 and item.get("nonuniform_scale") is False for item in transforms)
        sword_transform = transforms_by_part["sword"]
        sword_attached = sword_transform["target_pivot"] == [target["joints"]["wrist_right"]["x"], target["joints"]["wrist_right"]["y"]]
        sword_corridor = not any(item.get("first") == "sword" and item.get("second") == "torso_pelvis" and item.get("overlap_class") == "CRITICAL_COLLISION" for item in pair.get("pairs", []))
        frame_gates = {
            "canonical_target_binding": target_digest(target) == target.get("target_joint_sha256"),
            "presentation_target_binding": target_digest(target_presented) == target_presented.get("presentation_target_joint_sha256"),
            "target_skeleton_complete": all(name in target["joints"] for name in ALL_JOINTS),
            "bone_transform_scale_bounds": scale_ok,
            "actual_alpha_safe_margin_24_px": bool(alpha_qa["gate"]),
            "no_border_clipping": all(item.get("actual_border_clipped_pixels", 1) == 0 for item in integrity.get("parts", {}).values()) and all(item["hard_gates"]["no_presented_border_clipping"] for item in presentation_qa["parts"].values()),
            "presentation_transform_fidelity": presentation_qa["status"] == "PRESENTATION_TRANSFORM_PASSED",
            "structural_coverage": coverage.get("status") == "STRUCTURAL_COVERAGE_PASSED",
            "layer_integrity": integrity.get("status") == "LAYER_INTEGRITY_PASSED",
            "topology_occlusion": pair.get("status") == "OCCLUSION_QA_PASSED",
            "retention": retention.get("status") == "RETENTION_OCCLUSION_PASSED",
            "media_pipe": pose.get("qualifies") is True,
            "projected_ground_and_sole": support["ground_penetration_px"] <= 1.5 and (swing is None or (swing["visible_clearance_px"] >= 4.0 and swing["ground_penetration_px"] == 0.0)),
            "weapon_corridor": sword_corridor,
            "weapon_right_hand_attached": sword_attached,
            "sword_source_pixels_only": source_only,
            "no_detached_fragment": coverage.get("edge_speckle", {}).get("meaningful_detached_fragment_count") == 0,
            "no_duplicate_body": duplicate_ok,
            "generated_pixel_fraction_zero": proof["generated_pixel_fraction"] == 0.0,
            "recolor_count_zero": proof["recolor_count"] == 0,
        }
        frame_qa = {"schema_version": "0.8.1", "frame_index": index, "phase": phase, "canonical_target_joint_sha256": target["target_joint_sha256"], "presentation_target_joint_sha256": target_presented["presentation_target_joint_sha256"], "target": target, "presentation_target": target_presented, "output_rgba_sha256": _digest_image(output), "output_bbox": alpha_qa["alpha_bbox"], "alpha_safe_margin": alpha_qa, "root_pelvis": {"center": [target["joints"]["pelvis"]["x"], target["joints"]["pelvis"]["y"]]}, "sword": {"target_pivot": sword_transform["target_pivot"], "weapon_attachment": "wrist_right", "source_hash_invariant": source_only, "face_crossing": not sword_corridor}, "foot": foot, "duplicate_body": duplicate, "hard_gate_proof_sources": proof, "bone_scale_bounds_passed": scale_ok, "media_pipe": pose, "hard_gates": frame_gates, "status": "CUTOUT_RIG_FRONT_WALK_FRAME_PASSED" if all(frame_gates.values()) else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"}
        foot_records[phase] = foot
        integrity_records[phase] = integrity
        presentation_records[phase] = presentation_qa
        pair_records[phase] = json_safe(pair)
        seam_records[phase] = seam
        retention_records[phase] = retention
        coverage_records[phase] = json_safe({key: value for key, value in coverage.items() if key not in {"hole_mask", "expected_mask"}})
        frame_records.append(frame_qa)
        checker = checkerboard(output)
        ground_overlay = ground_line_overlay(output, target_presented, foot)
        overlay = overlay_image(output, target_presented, detected)
        hole_overlay = structural_hole_overlay(checker, apply_presentation_transform(coverage.get("hole_mask", Image.new("L", source.size, 0)).convert("RGBA"), presentation).getchannel("A"))
        write_image(CHECKER / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png", checker)
        write_image(OVERLAYS / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png", overlay)
        write_image(GROUND / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png", ground_overlay)
        write_image(HOLES / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png", hole_overlay)
        write_image(OUT / f"frame-{index:02d}-alpha-bbox-{phase.split('-', 1)[1]}.png", alpha_bbox_overlay(output, alpha_qa))
        write_json(PAIRWISE / f"frame-{index:02d}.json", json_safe(pair))
        write_json(RETENTION / f"frame-{index:02d}.json", json_safe(retention))
        overlays.append((f"F{index} {phase.split('-', 1)[1]}", overlay))
        checker_images.append((f"F{index} {phase.split('-', 1)[1]}", checker))
        ground_images.append((f"F{index} {phase.split('-', 1)[1]}", ground_overlay))
        bbox_images.append((f"F{index} {phase.split('-', 1)[1]}", alpha_bbox_overlay(output, alpha_qa)))
        waist.append((f"F{index}", zoom(checker, (170, 175, 350, 330))))
        feet.append((f"F{index}", zoom(ground_overlay, (70, 360, 350, 500))))
        sword_zoom.append((f"F{index}", zoom(checker, (50, 120, 370, 455))))

    temporal = temporal_qa_v081(targets, rendered, layer_bboxes, config)
    temporal["pre_smoothing"] = {"max_angular_acceleration_degrees_per_frame2": smoothing["pre_smoothing_max_angular_acceleration_degrees_per_frame2"], "records": smoothing["pre_smoothing_acceleration_records"]}
    temporal["post_smoothing"] = {"max_angular_acceleration_degrees_per_frame2": smoothing["post_smoothing_max_angular_acceleration_degrees_per_frame2"], "records": smoothing["post_smoothing_acceleration_records"], "optimizer_config_sha256": smoothing["optimizer_config_sha256"]}
    feet_qa = foot_contact_qa_v081(targets, foot_records, config)
    half = v080.half_cycle_qa(targets)
    half["schema_version"] = "0.8.1"
    loop = loop_qa_v081(targets, plan)
    bones = bone_bounds_v081(targets, skeleton, skeleton_point)
    motion = root_motion(targets)
    all_frame_pass = all(item["status"] == "CUTOUT_RIG_FRONT_WALK_FRAME_PASSED" for item in frame_records)
    all_aux_pass = all(item["status"].endswith("PASSED") for item in (temporal, feet_qa, half, loop, bones, motion))
    qualified = all_frame_pass and all_aux_pass
    if not all(frame["hard_gates"].get("actual_alpha_safe_margin_24_px", False) for frame in frame_records):
        status = "CUTOUT_RIG_FRONT_WALK_CANVAS_FIT_GAP"
    elif temporal["status"] != "CUTOUT_RIG_FRONT_WALK_TEMPORAL_PASSED":
        status = "CUTOUT_RIG_FRONT_WALK_TEMPORAL_GAP"
    elif loop["status"] != "CUTOUT_RIG_FRONT_WALK_LOOP_PASSED":
        status = "CUTOUT_RIG_FRONT_WALK_LOOP_GAP"
    elif not all_frame_pass:
        status = "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"
    else:
        status = "CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED" if qualified else "CUTOUT_RIG_FRONT_WALK_PACKAGING_GAP"

    sprite_path = OUT / "walk-front-spritesheet-v081.png"
    gif_path = OUT / "walk-front-preview-v081.gif"
    metadata_path = OUT / "walk-front-metadata-v081.json"
    package_path = OUT / "walk-front-package-manifest-v081.json"
    if qualified:
        build_spritesheet([rendered[phase] for phase in PHASES], sprite_path)
        build_gif([rendered[phase] for phase in PHASES], gif_path)
        metadata = {"schema_version": "0.8.1", "animation_id": "walk-front", "direction": "front", "frame_count": 8, "fps": FPS, "duration_ms": FRAME_DURATION_MS, "loop": True, "cell_size": {"width": 512, "height": 512}, "sheet_size": {"width": 2048, "height": 1024}, "format": "RGBA", "frames": [{"index": index, "phase": phase, "rect": {"x": (index % 4) * 512, "y": (index // 4) * 512, "width": 512, "height": 512}, "pivot": presented_targets[phase]["joints"]["pelvis"], "root": [presented_targets[phase]["joints"]["pelvis"]["x"], presented_targets[phase]["joints"]["pelvis"]["y"]], "projected_ground_y": foot_records[phase]["feet"][SUPPORT_SIDE[index]]["projected_ground_y"], "target_hash": targets[phase]["target_joint_sha256"], "presentation_target_hash": presented_targets[phase]["presentation_target_joint_sha256"], "rgba_sha256": digest_file(FRAMES / f"frame-{index:02d}-{phase.split('-', 1)[1]}.png"), "qa_status": frame_records[index]["status"]} for index, phase in enumerate(PHASES)], "status": "SPRITESHEET_METADATA_PASSED"}
        write_json(metadata_path, metadata)
        write_json(package_path, {"schema_version": "0.8.1", "package_id": "ugas-front-walk-pilot-v081", "registry_state": "pilot/technical-qualified", "production_approved": False, "production_routing": "BLOCKED", "asset": {"animation_id": "walk-front", "sprite_sheet": str(sprite_path.relative_to(ROOT)).replace("\\", "/"), "sprite_sha256": digest_file(sprite_path), "metadata": str(metadata_path.relative_to(ROOT)).replace("\\", "/"), "metadata_sha256": digest_file(metadata_path), "preview_gif": str(gif_path.relative_to(ROOT)).replace("\\", "/"), "preview_gif_sha256": digest_file(gif_path)}, "source_rig_revision": "v0.7.1", "source_rig_manifest": "docs/evidence/r4-cutout-rig-v071.json", "source_rig_sha256": digest_file(ROOT / "docs/evidence/r4-cutout-rig-v071.json"), "r4_source_revision": "R4", "r4_source_sha256": ANCHOR_SHA256, "external_visual_review": "REQUIRED", "external_approval": "not-claimed"})

    write_image(OUT / "front-walk-evidence-contact-sheet-v081.png", labelled_sheet(checker_images))
    write_image(OUT / "front-walk-checkerboard-contact-sheet-v081.png", labelled_sheet(checker_images))
    write_image(OUT / "front-walk-target-detected-overlays-v081.png", labelled_sheet(overlays))
    write_image(OUT / "front-walk-ground-line-overlays-v081.png", labelled_sheet(ground_images))
    write_image(OUT / "front-walk-alpha-bbox-contact-sheet-v081.png", labelled_sheet(bbox_images))
    write_image(OUT / "front-walk-structural-hole-maps-v081.png", labelled_sheet([(f"F{i}", Image.open(HOLES / f"frame-{i:02d}-{PHASES[i].split('-', 1)[1]}.png")) for i in range(8)]))
    write_image(OUT / "front-walk-waist-hip-zoom-v081.png", labelled_sheet(waist, (512, 430)))
    write_image(OUT / "front-walk-feet-ground-zoom-v081.png", labelled_sheet(feet, (512, 430)))
    write_image(OUT / "front-walk-sword-hand-zoom-v081.png", labelled_sheet(sword_zoom, (512, 430)))
    write_image(OUT / "front-walk-temporal-trajectory-v081.png", temporal_trajectory_image(temporal))

    write_json(EVIDENCE / "front-walk-per-frame-qa-v081.json", {"schema_version": "0.8.1", "plan_sha256": plan["plan_sha256"], "presentation_transform_sha256": presentation_hash, "frames": frame_records, "status": "CUTOUT_RIG_FRONT_WALK_FRAMES_PASSED" if all_frame_pass else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"})
    write_json(EVIDENCE / "front-walk-temporal-qa-v081.json", temporal)
    write_json(EVIDENCE / "front-walk-foot-contact-qa-v081.json", feet_qa)
    write_json(EVIDENCE / "front-walk-half-cycle-qa-v081.json", half)
    write_json(EVIDENCE / "front-walk-loop-qa-v081.json", loop)
    write_json(EVIDENCE / "front-walk-structural-coverage-v081.json", {"schema_version": "0.8.1", "poses": coverage_records, "status": "STRUCTURAL_COVERAGE_PASSED" if all(item.get("status") == "STRUCTURAL_COVERAGE_PASSED" for item in coverage_records.values()) else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"})
    write_json(EVIDENCE / "front-walk-layer-integrity-v081.json", {"schema_version": "0.8.1", "poses": integrity_records, "presentation_poses": presentation_records, "status": "LAYER_INTEGRITY_PASSED" if all(item.get("status") == "LAYER_INTEGRITY_PASSED" for item in integrity_records.values()) and all(item.get("status") == "PRESENTATION_TRANSFORM_PASSED" for item in presentation_records.values()) else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"})
    write_json(EVIDENCE / "front-walk-occlusion-v081.json", {"schema_version": "0.8.1", "plan_sha256": plan["plan_sha256"], "poses": pair_records, "seams": seam_records, "status": "OCCLUSION_QA_PASSED" if all(item.get("status") == "OCCLUSION_QA_PASSED" for item in pair_records.values()) and all(item.get("status") == "SEAM_TOPOLOGY_PASSED" for item in seam_records.values()) else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"})
    write_json(EVIDENCE / "front-walk-retention-v081.json", {"schema_version": "0.8.1", "poses": retention_records, "status": "RETENTION_OCCLUSION_PASSED" if all(item.get("status") == "RETENTION_OCCLUSION_PASSED" for item in retention_records.values()) else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"})
    write_json(EVIDENCE / "front-walk-foot-ground-record-v081.json", {"schema_version": "0.8.1", "frames": foot_records, "source_ground_rule": "source-alpha-sole-anchor-forward-projection-plus-frozen-depth-proxy-plus-frozen-support-calibration", "status": feet_qa["status"]})
    write_json(EVIDENCE / "front-walk-bone-projection-v081.json", bones)
    write_json(EVIDENCE / "front-walk-root-motion-v081.json", motion)
    qualification = {"schema_version": "0.8.1", "status": status, "provider_id": "deterministic-cutout-rig-2d", "capability": "pose_character_front_2d", "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "baseline_commit": BASELINE_COMMIT, "parent_v073_commit": PARENT_V073_COMMIT, "baseline_provider": "docs/evidence/cutout-rig-provider-qualification-v073.json", "config": str(CONFIG_PATH.relative_to(ROOT)).replace("\\", "/"), "config_sha256": config_hash, "plan": "docs/evidence/front-walk-z-order-v081.json", "frames": "docs/evidence/front-walk-per-frame-qa-v081.json", "temporal_pre_smoothing": "docs/evidence/front-walk-temporal-pre-smoothing-v081.json", "temporal": "docs/evidence/front-walk-temporal-qa-v081.json", "foot_contact": "docs/evidence/front-walk-foot-contact-qa-v081.json", "half_cycle": "docs/evidence/front-walk-half-cycle-qa-v081.json", "loop": "docs/evidence/front-walk-loop-qa-v081.json", "structural_coverage": "docs/evidence/front-walk-structural-coverage-v081.json", "layer_integrity": "docs/evidence/front-walk-layer-integrity-v081.json", "occlusion": "docs/evidence/front-walk-occlusion-v081.json", "retention": "docs/evidence/front-walk-retention-v081.json", "metadata": str(metadata_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "package_manifest": str(package_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "walk_authorized": "pilot_only", "production_walk_authorized": False, "sam2_runs": 0, "comfyui_generation_jobs": 0, "new_generation_jobs": 0, "external_visual_review": "REQUIRED", "external_approval": "not-claimed", "spritesheet": str(sprite_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "gif": str(gif_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "allowed_next": ["external_review_front_walk_cycle"] if qualified else ["repair_v081_walk_qa_then_rerun_same_cycle"], "forbidden": ["run_other_animation_or_direction", "run_comfyui_generation_for_this_slice", "rerun_sam2", "change_frozen_config_after_render", "same-cycle correction only"]}
    write_json(EVIDENCE / "front-walk-provider-qualification-v081.json", qualification)
    write_json(EVIDENCE / "execution-evidence-v0.8.1.json", {"schema_version": "0.8.1", "status": status, "baseline_commit": BASELINE_COMMIT, "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "config_frozen_before_render": True, "config_sha256": config_hash, "presentation_transform_frozen_before_render": True, "presentation_transform_sha256": presentation_hash, "sam2_runs": 0, "comfyui_generation_jobs": 0, "new_generation_jobs": 0, "frames": list(PHASES), "frame_count": 8, "spritesheet": str(sprite_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "gif": str(gif_path.relative_to(ROOT)).replace("\\", "/") if qualified else "NOT_RUN", "walk_authorized": "pilot_only", "production_routing": "BLOCKED", "external_visual_review": "REQUIRED", "external_approval": "not-claimed", "source_masks_unchanged": True, "new_animation_or_direction": False})
    summary = {"status": status, "frames": [item["status"] for item in frame_records], "temporal": temporal["status"], "foot_contact": feet_qa["status"], "half_cycle": half["status"], "loop": loop["status"], "spritesheet": sprite_path.is_file(), "gif": gif_path.is_file(), "sam2_runs": 0, "comfyui_generation_jobs": 0}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if qualified else 2


if __name__ == "__main__":
    raise SystemExit(main())
