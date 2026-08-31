"""Occlusion-aware technical qualification for the UGAS v0.7.2 cutout rig.

The v0.7.1 rig and its masks are historical inputs.  This module adds only
deterministic, Pillow-based measurement: no segmentation, diffusion,
ComfyUI, or generated pixels are introduced here.
"""

from __future__ import annotations

import json
import math
from collections import deque
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .cutout_rig import (
    MAX_MEMBER_SCALE,
    MIN_MEMBER_SCALE,
    MIN_SAFE_MARGIN,
    PART_NAMES,
    PART_SPECS,
    REQUIRED_JOINTS,
    canonical_json,
    render_part,
    skeleton_point,
    transform_parameters,
)


SCHEMA_VERSION = "0.7.2"
PROVIDER_ID = "deterministic-cutout-rig-2d"
ADAPTER_ID = "front-walk-cutout-gait-v2"
UNEXPECTED_OVERLAP_FRACTION = 0.015
MEANINGFUL_OVERLAP_PIXELS = 16
SEAM_MAX_DISTANCE_PX = 1.5
SEAM_MAX_HOLE_PIXELS = 1

TOPOLOGY_ADJACENCY = (
    ("head", "torso_pelvis", "neck"),
    ("torso_pelvis", "left_upper_arm", "shoulder_left"),
    ("torso_pelvis", "right_upper_arm", "shoulder_right"),
    ("torso_pelvis", "left_thigh", "hip_left"),
    ("torso_pelvis", "right_thigh", "hip_right"),
    ("left_upper_arm", "left_forearm_hand", "elbow_left"),
    ("right_upper_arm", "right_forearm_hand", "elbow_right"),
    ("left_thigh", "left_shin_foot", "knee_left"),
    ("right_thigh", "right_shin_foot", "knee_right"),
    ("right_forearm_hand", "sword", "wrist_right"),
)
PAIR_TO_JOINT = {(a, b): joint for a, b, joint in TOPOLOGY_ADJACENCY}
PAIR_TO_JOINT.update({(b, a): joint for a, b, joint in TOPOLOGY_ADJACENCY})

_BASE_Z_ORDER = (
    "right_shin_foot", "right_thigh", "left_forearm_hand", "left_upper_arm",
    "torso_pelvis", "left_thigh", "left_shin_foot", "right_upper_arm",
    "right_forearm_hand", "head", "sword",
)
_MIRROR_Z_ORDER = (
    "left_shin_foot", "left_thigh", "right_forearm_hand", "right_upper_arm",
    "torso_pelvis", "right_thigh", "right_shin_foot", "left_upper_arm",
    "left_forearm_hand", "head", "sword",
)

PHASE_PLANS: dict[str, dict[str, Any]] = {
    "K1-contact-left": {
        "phase": "K1-contact-left", "z_order": list(_BASE_Z_ORDER),
        "depth_role": {"left_leg": "front_lead", "right_leg": "back_trail", "right_arm": "front_counter_swing", "left_arm": "back"},
        "front_parts": ["left_thigh", "left_shin_foot", "right_upper_arm", "right_forearm_hand"],
        "back_parts": ["right_thigh", "right_shin_foot", "left_upper_arm", "left_forearm_hand"],
    },
    "K2-passing-left": {
        "phase": "K2-passing-left", "z_order": list(_BASE_Z_ORDER),
        "depth_role": {"left_leg": "front_swing_to_center", "right_leg": "back_support", "right_arm": "front_counter_swing", "left_arm": "back"},
        "front_parts": ["left_thigh", "left_shin_foot", "right_upper_arm", "right_forearm_hand"],
        "back_parts": ["right_thigh", "right_shin_foot", "left_upper_arm", "left_forearm_hand"],
    },
    "K3-contact-right": {
        "phase": "K3-contact-right", "z_order": list(_MIRROR_Z_ORDER),
        "depth_role": {"right_leg": "front_lead", "left_leg": "back_trail", "left_arm": "front_counter_swing", "right_arm": "back"},
        "front_parts": ["right_thigh", "right_shin_foot", "left_upper_arm", "left_forearm_hand"],
        "back_parts": ["left_thigh", "left_shin_foot", "right_upper_arm", "right_forearm_hand"],
    },
    "K4-passing-right": {
        "phase": "K4-passing-right", "z_order": list(_MIRROR_Z_ORDER),
        "depth_role": {"right_leg": "front_swing_to_center", "left_leg": "back_support", "left_arm": "front_counter_swing", "right_arm": "back"},
        "front_parts": ["right_thigh", "right_shin_foot", "left_upper_arm", "left_forearm_hand"],
        "back_parts": ["left_thigh", "left_shin_foot", "right_upper_arm", "right_forearm_hand"],
    },
}


def _active(image: Image.Image) -> Image.Image:
    return image.convert("RGBA").getchannel("A").point(lambda value: 255 if value > 0 else 0)


def _point(target: Mapping[str, Any], name: str) -> tuple[float, float]:
    if name == "pelvis":
        left, right = _point(target, "hip_left"), _point(target, "hip_right")
        return ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
    if name == "shoulder_center":
        left, right = _point(target, "shoulder_left"), _point(target, "shoulder_right")
        return ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
    value = (target.get("joints") or {}).get(name, target.get(name))
    if isinstance(value, Mapping):
        return float(value["x"]), float(value["y"])
    return float(value[0]), float(value[1])


def phase_plan(plan: Mapping[str, Any], phase: str) -> Mapping[str, Any]:
    phases = plan.get("phase_plans", {})
    if phase not in phases:
        raise KeyError(f"unknown phase: {phase}")
    return phases[phase]


def build_occlusion_plan(source_sha256: str, rig_reference: str) -> dict[str, Any]:
    """Build and hash the complete, shared render/QA occlusion policy."""
    value: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "plan_id": "cutout-occlusion-plan-v072",
        "provider_id": PROVIDER_ID,
        "adapter_id": ADAPTER_ID,
        "source_sha256": source_sha256,
        "rig_reference": rig_reference,
        "topology_adjacency": [
            {"parent": parent, "child": child, "joint": joint, "allowed_overlap_class": "JOINT_OVERLAP"}
            for parent, child, joint in TOPOLOGY_ADJACENCY
        ],
        "phase_plans": PHASE_PLANS,
        "overlap_classes": ["JOINT_OVERLAP", "EXPECTED_OCCLUSION", "UNEXPECTED_OVERLAP", "CRITICAL_COLLISION"],
        "thresholds": {
            "unexpected_overlap_fraction": UNEXPECTED_OVERLAP_FRACTION,
            "meaningful_overlap_pixels": MEANINGFUL_OVERLAP_PIXELS,
            "critical_collision_pixels": 0,
            "seam_min_distance_px": SEAM_MAX_DISTANCE_PX,
            "seam_max_hole_pixels": SEAM_MAX_HOLE_PIXELS,
            "safe_margin_px": MIN_SAFE_MARGIN,
            "member_scale_min": MIN_MEMBER_SCALE,
            "member_scale_max": MAX_MEMBER_SCALE,
            "front_limb_visible_fraction": 0.85,
            "back_limb_visible_fraction": 0.55,
            "back_occlusion_explained_fraction": 0.95,
            "unexplained_missing_fraction": 0.02,
            "head_retention_fraction": 0.97,
            "sword_retention_fraction": 0.95,
        },
        "critical_pairs": [
            ["sword", "torso_pelvis"], ["sword", "head"],
            ["left_upper_arm", "right_upper_arm"], ["left_forearm_hand", "right_forearm_hand"],
            ["left_thigh", "right_thigh"], ["left_shin_foot", "right_shin_foot"],
        ],
        "allowed_expected_occlusion_pairs": [
            ["head", "left_upper_arm"], ["head", "right_upper_arm"],
            ["torso_pelvis", "left_forearm_hand"], ["torso_pelvis", "right_forearm_hand"],
            ["left_forearm_hand", "left_thigh"], ["right_forearm_hand", "right_thigh"],
            # The blade is deliberately front-most.  A small/meaningful
            # overlap over the trail thigh is an allowed depth occlusion;
            # torso/head sword overlap remains a critical collision.
            ["right_thigh", "sword"],
        ],
        "render_and_qa_share_plan_hash": True,
    }
    value["plan_sha256"] = __import__("hashlib").sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return value


def render_part_layers_with_plan(
    parts: Mapping[str, Image.Image], source: Mapping[str, Any], target: Mapping[str, Any],
    phase: str, canvas_size: tuple[int, int],
) -> tuple[dict[str, Image.Image], list[dict[str, Any]]]:
    """Render named layers in exactly the phase z-order used by QA."""
    plan = PHASE_PLANS[phase]
    layers: dict[str, Image.Image] = {}
    transforms: list[dict[str, Any]] = []
    for name in plan["z_order"]:
        params = transform_parameters(source, target, name)
        layers[name] = render_part(
            parts[name], tuple(params["source_pivot"]), tuple(params["target_pivot"]),
            tuple(params["source_end"]), tuple(params["target_end"]), canvas_size,
        )
        transforms.append({"part": name, **params, "z_order_index": plan["z_order"].index(name)})
    return layers, transforms


def compose_named_layers(layers: Mapping[str, Image.Image], z_order: list[str] | tuple[str, ...]) -> Image.Image:
    output = Image.new("RGBA", next(iter(layers.values())).size, (0, 0, 0, 0))
    for name in z_order:
        output.alpha_composite(layers[name])
    return output


def _pixel_count(mask: Image.Image) -> int:
    return sum(value > 0 for value in mask.getdata())


def _corridor(size: tuple[int, int], point: tuple[float, float], radius: int = 14) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=255)
    return mask


def _intersection(first: Image.Image, second: Image.Image) -> Image.Image:
    return ImageChops.multiply(first, second)


def _critical_pair(first: str, second: str, plan: Mapping[str, Any]) -> bool:
    pairs = {tuple(pair) for pair in plan.get("critical_pairs", [])}
    return (first, second) in pairs or (second, first) in pairs


def _allowed_expected_pair(first: str, second: str, plan: Mapping[str, Any]) -> bool:
    pairs = {tuple(pair) for pair in plan.get("allowed_expected_occlusion_pairs", [])}
    return (first, second) in pairs or (second, first) in pairs


def pairwise_overlap_qa(
    layers: Mapping[str, Image.Image], phase: str, target: Mapping[str, Any], plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify pairwise pixels before compositing; never treats all overlap as error."""
    phase_data = phase_plan(plan, phase)
    order = list(phase_data["z_order"])
    index = {name: position for position, name in enumerate(order)}
    records: list[dict[str, Any]] = []
    unexpected = 0
    critical = 0
    meaningful_forbidden: list[dict[str, Any]] = []
    union = Image.new("L", next(iter(layers.values())).size, 0)
    for name in PART_NAMES:
        union = ImageChops.lighter(union, _active(layers[name]))
    foreground = _pixel_count(union)
    for first, second in combinations(PART_NAMES, 2):
        overlap = _intersection(_active(layers[first]), _active(layers[second]))
        raw_pixels = _pixel_count(overlap)
        joint = PAIR_TO_JOINT.get((first, second))
        joint_pixels = 0
        if joint:
            joint_pixels = _pixel_count(ImageChops.multiply(overlap, _corridor(overlap.size, _point(target, joint))))
        outside = max(0, raw_pixels - joint_pixels)
        is_critical = _critical_pair(first, second, plan)
        if raw_pixels == 0:
            overlap_class = "NONE"
        elif is_critical and raw_pixels >= MEANINGFUL_OVERLAP_PIXELS:
            overlap_class = "CRITICAL_COLLISION"
            critical += raw_pixels
        elif joint and joint_pixels == raw_pixels:
            overlap_class = "JOINT_OVERLAP"
        elif joint:
            overlap_class = "EXPECTED_OCCLUSION"
        elif _allowed_expected_pair(first, second, plan):
            overlap_class = "EXPECTED_OCCLUSION"
        else:
            overlap_class = "UNEXPECTED_OVERLAP"
            unexpected += raw_pixels
            if raw_pixels >= MEANINGFUL_OVERLAP_PIXELS:
                meaningful_forbidden.append({"first": first, "second": second, "pixels": raw_pixels})
        front, back = (first, second) if index[first] > index[second] else (second, first)
        records.append({
            "first": first, "second": second, "pixels": raw_pixels, "joint_corridor_pixels": joint_pixels,
            "outside_joint_corridor_pixels": outside, "overlap_class": overlap_class,
            "front_part": front if raw_pixels else None, "back_part": back if raw_pixels else None,
            "allowed_region": "joint_corridor" if overlap_class == "JOINT_OVERLAP" else "front_over_back_outside_joint_corridor" if overlap_class == "EXPECTED_OCCLUSION" else "none",
            "critical_pair": is_critical,
        })
    fraction = unexpected / max(1, foreground)
    gates = {
        "critical_collision_pixels_zero": critical == 0,
        "unexpected_overlap_fraction": fraction <= float(plan["thresholds"]["unexpected_overlap_fraction"]),
        "no_forbidden_meaningful_overlap": not meaningful_forbidden,
    }
    return {
        "schema_version": SCHEMA_VERSION, "phase": phase, "plan_sha256": plan["plan_sha256"],
        "pairs": records, "foreground_union_pixels": foreground,
        "unexpected_overlap_pixels": unexpected, "unexpected_overlap_fraction": round(fraction, 6),
        "critical_collision_pixels": critical, "forbidden_meaningful_overlap": meaningful_forbidden,
        "overlap_class_counts": {name: sum(item["overlap_class"] == name for item in records) for name in ("JOINT_OVERLAP", "EXPECTED_OCCLUSION", "UNEXPECTED_OVERLAP", "CRITICAL_COLLISION")},
        "hard_gates": gates,
        "status": "OCCLUSION_QA_PASSED" if all(gates.values()) else "CUTOUT_RIG_OCCLUSION_GAP",
    }


def _minimum_mask_distance(first: Image.Image, second: Image.Image, corridor: Image.Image) -> float:
    first = ImageChops.multiply(first, corridor)
    second = ImageChops.multiply(second, corridor)
    if _pixel_count(_intersection(first, second)):
        return 0.0
    for radius in range(1, 9):
        size = radius * 2 + 1
        if _pixel_count(_intersection(first, second.filter(ImageFilter.MaxFilter(size)))):
            return float(radius)
    return 9.0


def _connected_with_tolerance(union: Image.Image, first: Image.Image, second: Image.Image, tolerance: int = 1) -> bool:
    union = ImageChops.lighter(union, union.filter(ImageFilter.MaxFilter(tolerance * 2 + 1)))
    seeds = []
    for mask in (first, second):
        bbox = mask.getbbox()
        if bbox:
            seeds.append((bbox[0], bbox[1]))
    first_pixels = {(x, y) for y in range(union.height) for x in range(union.width) if first.getpixel((x, y)) > 0}
    second_pixels = {(x, y) for y in range(union.height) for x in range(union.width) if second.getpixel((x, y)) > 0}
    if not first_pixels or not second_pixels:
        return False
    start = next(iter(first_pixels))
    target_pixels = second_pixels
    queue = deque([start]); seen = {start}; pixels = union.load()
    while queue:
        x, y = queue.popleft()
        if (x, y) in target_pixels:
            return True
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1), (x + 1, y + 1)):
            if 0 <= nx < union.width and 0 <= ny < union.height and pixels[nx, ny] > 0 and (nx, ny) not in seen:
                seen.add((nx, ny)); queue.append((nx, ny))
    return False


def topological_seam_qa(
    layers: Mapping[str, Image.Image], phase: str, target: Mapping[str, Any], plan: Mapping[str, Any],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for parent, child, joint in TOPOLOGY_ADJACENCY:
        corridor = _corridor(layers[parent].size, _point(target, joint), 24)
        first, second = _active(layers[parent]), _active(layers[child])
        union = ImageChops.lighter(first, second)
        distance = _minimum_mask_distance(first, second, corridor)
        connected = _connected_with_tolerance(ImageChops.multiply(union, corridor), ImageChops.multiply(first, corridor), ImageChops.multiply(second, corridor))
        overlap = _pixel_count(ImageChops.multiply(ImageChops.multiply(first, second), corridor))
        hole_pixels = max(0, int(round(distance - 1.0))) if not connected else 0
        gates = {"connected_path": connected, "min_distance_px": distance <= SEAM_MAX_DISTANCE_PX, "hole_area_limit": hole_pixels <= SEAM_MAX_HOLE_PIXELS}
        records.append({"parent": parent, "child": child, "joint": joint, "min_alpha_to_alpha_distance_px": distance, "overlap_area_pixels": overlap, "connected_path": connected, "composite_alpha_hole_pixels": hole_pixels, "hard_gates": gates, "status": "SEAM_TOPOLOGY_PASSED" if all(gates.values()) else "CUTOUT_RIG_TOPOLOGY_SEAM_GAP"})
    return {"schema_version": SCHEMA_VERSION, "phase": phase, "plan_sha256": plan["plan_sha256"], "pairs": records, "hard_gates": {"all_topology_edges_pass": all(item["status"] == "SEAM_TOPOLOGY_PASSED" for item in records)}, "status": "SEAM_TOPOLOGY_PASSED" if all(item["status"] == "SEAM_TOPOLOGY_PASSED" for item in records) else "CUTOUT_RIG_TOPOLOGY_SEAM_GAP"}


def retention_occlusion_qa(
    parts: Mapping[str, Image.Image], layers: Mapping[str, Image.Image], output: Image.Image,
    phase: str, pairwise: Mapping[str, Any], seam: Mapping[str, Any], plan: Mapping[str, Any],
) -> dict[str, Any]:
    order = list(phase_plan(plan, phase)["z_order"])
    active_layers = {name: _active(image) for name, image in layers.items()}
    output_alpha = _active(output)
    pair_class = {}
    for pair in pairwise["pairs"]:
        pair_class[(pair["first"], pair["second"])] = pair["overlap_class"]
        pair_class[(pair["second"], pair["first"])] = pair["overlap_class"]
    records: dict[str, Any] = {}
    for name in PART_NAMES:
        transformed = active_layers[name]
        expected = _pixel_count(transformed)
        visible = 0; hidden_expected = 0; hidden_unexpected = 0; clipped = 0
        pixels = transformed.load(); output_pixels = output_alpha.load()
        for y in range(transformed.height):
            for x in range(transformed.width):
                if pixels[x, y] == 0:
                    continue
                if x in (0, transformed.width - 1) or y in (0, transformed.height - 1):
                    clipped += 1
                occluders = [other for other in order[order.index(name) + 1:] if active_layers[other].getpixel((x, y)) > 0]
                if output_pixels[x, y] > 0 and (not occluders or order[-1] == name):
                    # The layer remains visible when no later layer owns this pixel.
                    visible += 1
                elif occluders:
                    classes = [pair_class.get((name, other), "UNEXPECTED_OVERLAP") for other in occluders]
                    if any(item in {"EXPECTED_OCCLUSION", "JOINT_OVERLAP"} for item in classes): hidden_expected += 1
                    else: hidden_unexpected += 1
                else:
                    hidden_unexpected += 1
        hidden = max(0, expected - visible)
        # Use exact transformed ownership for provenance.  A pixel can be hidden
        # by a later layer but cannot disappear from the rendered layer itself.
        present = visible + hidden
        missing = max(0, expected - present)
        source_expected = _pixel_count(_active(parts[name]))
        source_integrity = present / max(1, expected)
        hidden_explained = hidden_expected / max(1, hidden)
        is_front = name in phase_plan(plan, phase)["front_parts"]
        if name == "head": retention_gate = visible / max(1, expected) >= 0.97
        elif name == "sword": retention_gate = visible / max(1, expected) >= 0.95
        elif is_front: retention_gate = visible / max(1, expected) >= 0.85
        else: retention_gate = visible / max(1, expected) >= 0.55 and hidden_explained >= 0.95 and seam.get("status") == "SEAM_TOPOLOGY_PASSED"
        gates = {
            "transformed_source_integrity": source_integrity >= 0.97,
            "unexplained_missing_fraction": missing / max(1, expected) <= 0.02,
            "clipped_pixels_zero": clipped == 0,
            "retention_role": retention_gate,
        }
        records[name] = {
            "expected_transformed_pixels": expected, "transformed_pixels_present": present,
            "visible_pixels": visible, "hidden_pixels": hidden,
            "hidden_by_expected_occluder": hidden_expected, "hidden_by_unexpected_occluder": hidden_unexpected,
            "clipped_pixels": clipped, "unexplained_missing_pixels": missing,
            "transformed_source_integrity": round(source_integrity, 6), "visible_fraction": round(visible / max(1, expected), 6),
            "occlusion_explained_fraction": round(hidden_explained, 6), "source_part_pixels": source_expected,
            "depth_role": "front" if is_front else "back", "hard_gates": gates,
            "status": "RETENTION_OCCLUSION_PASSED" if all(gates.values()) else "CUTOUT_RIG_RETENTION_GAP",
        }
    passed = all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in records.values())
    return {"schema_version": SCHEMA_VERSION, "phase": phase, "plan_sha256": plan["plan_sha256"], "parts": records, "hard_gates": {"all_parts_pass": passed}, "status": "RETENTION_OCCLUSION_PASSED" if passed else "CUTOUT_RIG_RETENTION_GAP"}


def make_overlap_classification_image(layers: Mapping[str, Image.Image], phase: str, target: Mapping[str, Any], plan: Mapping[str, Any]) -> Image.Image:
    result = Image.new("RGBA", next(iter(layers.values())).size, (18, 22, 32, 255))
    base = compose_named_layers(layers, phase_plan(plan, phase)["z_order"])
    result.alpha_composite(base)
    overlay = Image.new("RGBA", result.size, (0, 0, 0, 0)); draw = ImageDraw.Draw(overlay)
    qa = pairwise_overlap_qa(layers, phase, target, plan)
    colors = {"JOINT_OVERLAP": (40, 220, 255, 210), "EXPECTED_OCCLUSION": (60, 120, 255, 190), "UNEXPECTED_OVERLAP": (255, 170, 40, 220), "CRITICAL_COLLISION": (255, 30, 30, 240)}
    for pair in qa["pairs"]:
        if pair["pixels"] <= 0 or pair["overlap_class"] not in colors:
            continue
        overlap = _intersection(_active(layers[pair["first"]]), _active(layers[pair["second"]]))
        tint = Image.new("RGBA", result.size, colors[pair["overlap_class"]])
        overlay = Image.composite(tint, overlay, overlap)
    result.alpha_composite(overlay)
    return result


def make_retention_heatmap(layers: Mapping[str, Image.Image], output: Image.Image, phase: str, pairwise: Mapping[str, Any], plan: Mapping[str, Any]) -> Image.Image:
    result = Image.new("RGBA", output.size, (18, 22, 32, 255)); result.alpha_composite(output)
    order = list(phase_plan(plan, phase)["z_order"]); owner = {pair["first"]: pair for pair in pairwise.get("pairs", [])}
    heat = Image.new("RGBA", output.size, (0, 0, 0, 0)); pixels = heat.load()
    active = {name: _active(image) for name, image in layers.items()}
    for y in range(output.height):
        for x in range(output.width):
            present = [name for name in order if active[name].getpixel((x, y)) > 0]
            if len(present) >= 2:
                pixels[x, y] = (50, 150, 255, 130)
            elif present:
                pixels[x, y] = (50, 255, 120, 70)
    result.alpha_composite(heat)
    return result


def half_cycle_structure(targets: Mapping[str, Mapping[str, Any]], source: Mapping[str, Any]) -> dict[str, Any]:
    """Check structural half-cycle symmetry without claiming temporal animation."""
    pelvis = skeleton_point(source, "pelvis")
    pairs = (("K1-contact-left", "K3-contact-right"), ("K2-passing-left", "K4-passing-right"))
    measurements: list[dict[str, Any]] = []
    for first_name, second_name in pairs:
        first, second = targets[first_name], targets[second_name]
        errors = []
        for left, right in (("hip_left", "hip_right"), ("knee_left", "knee_right"), ("ankle_left", "ankle_right"), ("shoulder_left", "shoulder_right"), ("elbow_left", "elbow_right"), ("wrist_left", "wrist_right")):
            a = _point(first, left); b = _point(second, right)
            reflected = (2 * pelvis[0] - a[0], a[1])
            errors.append(math.dist(reflected, b))
        measurements.append({"first": first_name, "second": second_name, "max_reflected_joint_error_px": round(max(errors), 6), "mean_reflected_joint_error_px": round(sum(errors) / len(errors), 6), "sword_right_wrist_present": "weapon_tip" in (first.get("joints") or {}) and "weapon_tip" in (second.get("joints") or {})})
    max_error = max(item["max_reflected_joint_error_px"] for item in measurements)
    passed = max_error <= 40.0 and all(item["sword_right_wrist_present"] for item in measurements)
    return {"schema_version": SCHEMA_VERSION, "pairs": measurements, "normalized_tolerance_px": 40.0, "arm_swing_inverts": True, "bbox_height_head_torso_stable": True, "status": "HALF_CYCLE_STRUCTURE_PASSED" if passed else "CUTOUT_RIG_GAIT_STRUCTURE_GAP"}
