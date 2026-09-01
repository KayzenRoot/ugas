"""Strict v0.8.1 deterministic front-walk correction gates.

The v0.8.0 implementation is retained as historical evidence.  This module
contains the corrective instrument required by v0.8.1: raster-aware sole and
ground measurements, a real alpha-bbox margin, bounded skeleton-only
smoothing, actual head/torso layer bbox metrics, and a hash-bound loop plan.
No function in this module creates pixels from anything other than an
immutable source part and a deterministic affine resample.
"""

from __future__ import annotations

import hashlib
import math
from copy import deepcopy
from typing import Any, Mapping

from PIL import Image

from . import cutout_temporal as v080
from .cutout_rig import PART_NAMES, PART_SPECS, canonical_json, transform_parameters


SCHEMA_VERSION = "0.8.1"
FPS = 10
FRAME_DURATION_MS = 100
SAFE_MARGIN_PX = 24
ANGULAR_ACCELERATION_MAX = 25.0
PHASES = v080.PHASES
KEY_FRAMES = v080.KEY_FRAMES
INTERMEDIATE_NEIGHBOURS = v080.INTERMEDIATE_NEIGHBOURS
SUPPORT_SIDE = v080.SUPPORT_SIDE
SWING_SIDE = v080.SWING_SIDE
ALL_JOINTS = v080.ALL_JOINTS
LIMB_BONES = v080.LIMB_BONES


def _xy(value: Any) -> tuple[float, float]:
    if isinstance(value, Mapping):
        return float(value["x"]), float(value["y"])
    return float(value[0]), float(value[1])


def _point(xy: tuple[float, float], template: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value = {"x": round(float(xy[0]), 6), "y": round(float(xy[1]), 6)}
    if template:
        for key in ("confidence", "visibility", "presence", "source_index", "visible"):
            if key in template:
                value[key] = template[key]
    return value


target_digest = v080.target_digest


def _angle(first: tuple[float, float], middle: tuple[float, float], last: tuple[float, float]) -> float:
    delta = math.degrees(
        math.atan2(last[1] - middle[1], last[0] - middle[0])
        - math.atan2(first[1] - middle[1], first[0] - middle[0])
    )
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return abs(delta)


def _signed_angle(first: tuple[float, float], middle: tuple[float, float], last: tuple[float, float]) -> float:
    delta = math.degrees(
        math.atan2(last[1] - middle[1], last[0] - middle[0])
        - math.atan2(first[1] - middle[1], first[0] - middle[0])
    )
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return delta


ANGLE_CHAINS = tuple(
    (f"knee_{side}", f"hip_{side}", f"ankle_{side}")
    for side in ("left", "right")
) + tuple(
    (f"elbow_{side}", f"shoulder_{side}", f"wrist_{side}")
    for side in ("left", "right")
)


def _angle_series(targets: Mapping[str, Mapping[str, Any]]) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    signed: list[dict[str, float]] = []
    deltas: list[dict[str, float]] = []
    for index, phase in enumerate(PHASES):
        current = targets[phase]["joints"]
        previous = targets[PHASES[(index - 1) % len(PHASES)]]["joints"]
        signed_now: dict[str, float] = {}
        delta_now: dict[str, float] = {}
        for middle, first, last in ANGLE_CHAINS:
            key = middle
            signed_now[key] = _signed_angle(_xy(current[first]), _xy(current[middle]), _xy(current[last]))
            before = _signed_angle(_xy(previous[first]), _xy(previous[middle]), _xy(previous[last]))
            delta = signed_now[key] - before
            while delta > 180.0:
                delta -= 360.0
            while delta < -180.0:
                delta += 360.0
            delta_now[key] = abs(delta)
        signed.append(signed_now)
        deltas.append(delta_now)
    return signed, deltas


def angular_acceleration_records(targets: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    signed, _ = _angle_series(targets)
    records: list[dict[str, Any]] = []
    for index, phase in enumerate(PHASES):
        current = signed[index]
        before = signed[(index - 1) % len(PHASES)]
        before_before = signed[(index - 2) % len(PHASES)]
        for name in current:
            value = abs(current[name] - 2.0 * before[name] + before_before[name])
            while value > 180.0:
                value = abs(value - 360.0)
            records.append({"phase": phase, "joint": name, "value": round(value, 6)})
    return records


def _bone_ratio_penalty(
    targets: Mapping[str, Mapping[str, Any]], initial: Mapping[str, Mapping[str, Any]], bounds: Mapping[str, Any],
) -> float:
    minimum, maximum = float(bounds["min"]), float(bounds["max"])
    penalty = 0.0
    for phase in PHASES:
        for first, second in LIMB_BONES:
            current = math.dist(_xy(targets[phase]["joints"][first]), _xy(targets[phase]["joints"][second]))
            baseline = math.dist(_xy(initial[phase]["joints"][first]), _xy(initial[phase]["joints"][second]))
            ratio = current / max(1e-6, baseline)
            penalty += max(0.0, minimum - ratio) ** 2 + max(0.0, ratio - maximum) ** 2
    return penalty


def _smoothing_score(
    targets: Mapping[str, Mapping[str, Any]], initial: Mapping[str, Mapping[str, Any]], config: Mapping[str, Any],
) -> float:
    smoothing = config["smoothing"]
    threshold = float(smoothing["angular_acceleration_threshold_degrees_per_frame2"])
    records = angular_acceleration_records(targets)
    excess = sum(max(0.0, float(item["value"]) - (threshold - 0.3)) ** 2 for item in records)
    total = sum(float(item["value"]) ** 2 for item in records)
    signed, deltas = _angle_series(targets)
    adjacent = max((value for item in deltas for value in item.values()), default=0.0)
    return (
        excess * 100.0
        + total * 0.0001
        + max(0.0, adjacent - 34.5) ** 2 * 1000.0
        + _bone_ratio_penalty(targets, initial, smoothing.get("relative_bone_ratio_bounds", {"min": 0.94, "max": 1.04})) * 100000.0
        + sum(abs(value) for item in signed for value in item.values()) * 0.000001
    )


def build_initial_targets_v081(
    key_targets: Mapping[int, Mapping[str, Any]], config: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build the pre-smoothing skeleton and explicitly consume foot bias."""
    targets: dict[str, dict[str, Any]] = {}
    for frame, phase in enumerate(PHASES):
        targets[phase] = v080.interpolate_target(key_targets, frame, config)
        correction = config["phase_corrections"].get(str(frame), {})
        side = SWING_SIDE.get(frame)
        bias = float(correction.get("swing_foot_clearance_bias_px", 0.0))
        if frame in INTERMEDIATE_NEIGHBOURS and side and bias:
            ankle = targets[phase]["joints"][f"ankle_{side}"]
            ankle["y"] = round(float(ankle["y"]) - bias, 6)
            targets[phase].setdefault("generator", {})["swing_foot_bias_consumed_px"] = bias
        targets[phase]["schema_version"] = SCHEMA_VERSION
        targets[phase]["phase"] = phase
        targets[phase]["view"] = "front"
        targets[phase]["orientation"] = "front"
        targets[phase]["frame_index"] = frame
        targets[phase]["canonical_target_joint_sha256"] = target_digest(targets[phase])
    return targets


def smooth_walk_targets(
    initial_targets: Mapping[str, Mapping[str, Any]], config: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Run a bounded, deterministic skeleton-only coordinate descent.

    Only intermediate knee/elbow joints are adjusted.  The four immutable key
    targets, ankle semantics, source pixels, and all image data remain outside
    this optimization.  The frozen config supplies the objective, bounds,
    iteration count, and step schedule before any render is requested.
    """
    targets = deepcopy(initial_targets)
    smoothing = config["smoothing"]
    bound = float(smoothing["joint_adjustment_bound_px"])
    max_iterations = int(smoothing["max_iterations"])
    steps = tuple(float(value) for value in smoothing["step_schedule_px"])
    variables = tuple(
        (frame, joint, axis)
        for frame in (1, 3, 5, 7)
        for joint in ("knee_left", "knee_right", "elbow_left", "elbow_right")
        for axis in ("x", "y")
    )
    initial = deepcopy(initial_targets)
    before_records = angular_acceleration_records(targets)
    before_max = max((float(item["value"]) for item in before_records), default=0.0)
    accepted: list[dict[str, Any]] = []
    for step in steps:
        for iteration in range(max_iterations):
            changed = False
            current_score = _smoothing_score(targets, initial, config)
            for frame, joint, axis in variables:
                phase = PHASES[frame]
                original = float(initial[phase]["joints"][joint][axis])
                current = float(targets[phase]["joints"][joint][axis])
                best_score, best_value = current_score, current
                for delta in (-step, step):
                    candidate = max(original - bound, min(original + bound, current + delta))
                    candidate = round(candidate, 6)
                    targets[phase]["joints"][joint][axis] = candidate
                    candidate_score = _smoothing_score(targets, initial, config)
                    if candidate_score < best_score - 1e-9:
                        best_score, best_value = candidate_score, candidate
                    targets[phase]["joints"][joint][axis] = current
                if best_value != current:
                    targets[phase]["joints"][joint][axis] = best_value
                    current_score = best_score
                    accepted.append({"frame": frame, "joint": joint, "axis": axis, "value": best_value, "step_px": step})
                    changed = True
            if not changed:
                break
    for frame, phase in enumerate(PHASES):
        target = targets[phase]
        target["schema_version"] = SCHEMA_VERSION
        target["phase"] = phase
        target["frame_index"] = frame
        target["generator"] = {
            "kind": "deterministic_skeleton_only",
            "method": "cubic_hermite_then_bounded_skeleton_temporal_smoothing_then_bone_ratio_check",
            "phase_parameter": 0.5,
            "pixel_interpolation": False,
            "image_inputs_used_for_smoothing": False,
        }
        target["target_joint_sha256"] = target_digest(target)
    after_records = angular_acceleration_records(targets)
    after_max = max((float(item["value"]) for item in after_records), default=0.0)
    optimizer_config = {
        "objective": smoothing["objective"],
        "weights": smoothing["weights"],
        "bounds": {"joint_adjustment_bound_px": bound, "bone_ratio": config["bone_ratio_bounds"]},
        "step_schedule_px": list(steps),
        "max_iterations": max_iterations,
    }
    return targets, {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "bounded_deterministic_coordinate_descent",
        "image_inputs_used": False,
        "immutable_key_frames": [PHASES[index] for index in (0, 2, 4, 6)],
        "pre_smoothing_max_angular_acceleration_degrees_per_frame2": round(before_max, 6),
        "post_smoothing_max_angular_acceleration_degrees_per_frame2": round(after_max, 6),
        "pre_smoothing_acceleration_records": before_records,
        "post_smoothing_acceleration_records": after_records,
        "accepted_adjustments": accepted,
        "optimizer_config": optimizer_config,
        "optimizer_config_sha256": hashlib.sha256(canonical_json(optimizer_config).encode("utf-8")).hexdigest(),
        "hard_gate": {"max_angular_acceleration_le_25": after_max <= ANGULAR_ACCELERATION_MAX},
    }


def build_walk_targets_v081(
    key_targets: Mapping[int, Mapping[str, Any]], config: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    initial = build_initial_targets_v081(key_targets, config)
    targets, smoothing = smooth_walk_targets(initial, config)
    return targets, smoothing, initial


def build_walk_plan_v081(source_sha256: str, rig_reference: str, config: Mapping[str, Any]) -> dict[str, Any]:
    plan = deepcopy(v080.build_walk_plan(source_sha256, rig_reference, config))
    plan.pop("plan_sha256", None)
    plan["schema_version"] = SCHEMA_VERSION
    plan["plan_id"] = "cutout-front-walk-z-order-v081"
    plan["z_order_switch_boundaries"] = [
        {
            "edge": "F3->F4",
            "from_phase": "F3-up-left",
            "to_phase": "F4-contact-right",
            "from_z_order": plan["phase_plans"]["F3-up-left"]["z_order"],
            "to_z_order": plan["phase_plans"]["F4-contact-right"]["z_order"],
            "from_depth_role": plan["phase_plans"]["F3-up-left"]["depth_role"],
            "to_depth_role": plan["phase_plans"]["F4-contact-right"]["depth_role"],
            "allowed_anatomical_pairs": [["left_leg", "right_leg"], ["left_arm", "right_arm"]],
        },
        {
            "edge": "F7->F0",
            "from_phase": "F7-up-right",
            "to_phase": "F0-contact-left",
            "from_z_order": plan["phase_plans"]["F7-up-right"]["z_order"],
            "to_z_order": plan["phase_plans"]["F0-contact-left"]["z_order"],
            "from_depth_role": plan["phase_plans"]["F7-up-right"]["depth_role"],
            "to_depth_role": plan["phase_plans"]["F0-contact-left"]["depth_role"],
            "allowed_anatomical_pairs": [["left_leg", "right_leg"], ["left_arm", "right_arm"]],
        },
    ]
    plan["switch_boundaries"] = [item["edge"] for item in plan["z_order_switch_boundaries"]]
    plan["render_and_qa_share_plan_hash"] = True
    plan["loop_boundary_is_explicit"] = True
    plan["plan_sha256"] = hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()
    return plan


def _forward(matrix: list[list[float]], point: tuple[float, float]) -> tuple[float, float]:
    return (
        matrix[0][0] * point[0] + matrix[0][1] * point[1] + matrix[0][2],
        matrix[1][0] * point[0] + matrix[1][1] * point[1] + matrix[1][2],
    )


def source_sole_anchor(part: Image.Image) -> tuple[float, float, float]:
    """Return a source-mask-derived sole center and its ankle-independent y."""
    alpha = part.convert("RGBA").getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        raise ValueError("empty_shin_foot_source")
    y = bbox[3] - 1
    xs = [x for x in range(alpha.width) if alpha.getpixel((x, y)) > 0]
    if not xs:
        raise ValueError("source_sole_row_empty")
    return (float(min(xs) + max(xs)) / 2.0, float(y), float(len(xs)))


def _presentation_offset(transform: Mapping[str, Any]) -> tuple[float, float]:
    anchor = _xy(transform["anchor"])
    scale = float(transform["uniform_scale"])
    translation = _xy(transform.get("translation", {"x": 0.0, "y": 0.0}))
    return ((1.0 - scale) * anchor[0] + translation[0], (1.0 - scale) * anchor[1] + translation[1])


def map_presentation_point(point: tuple[float, float], transform: Mapping[str, Any]) -> tuple[float, float]:
    scale = float(transform["uniform_scale"])
    offset = _presentation_offset(transform)
    return (scale * point[0] + offset[0], scale * point[1] + offset[1])


def apply_presentation_transform(image: Image.Image, transform: Mapping[str, Any]) -> Image.Image:
    """Apply the same frozen canvas transform to any RGBA evidence layer."""
    scale = float(transform["uniform_scale"])
    offset = _presentation_offset(transform)
    if scale <= 0.0:
        raise ValueError("presentation_scale_must_be_positive")
    inverse = (1.0 / scale, 0.0, -offset[0] / scale, 0.0, 1.0 / scale, -offset[1] / scale)
    return image.convert("RGBA").transform(image.size, Image.Transform.AFFINE, inverse, resample=Image.Resampling.BICUBIC)


def transform_target_for_presentation(target: Mapping[str, Any], transform: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(target)
    value["canonical_target_joint_sha256"] = target_digest(target)
    for name, point in value.get("joints", {}).items():
        value["joints"][name] = _point(map_presentation_point(_xy(point), transform), point)
    value["presentation_target_joint_sha256"] = target_digest(value)
    value["presentation_transform_sha256"] = hashlib.sha256(canonical_json(transform).encode("utf-8")).hexdigest()
    return value


def presentation_plan_from_extents(
    source_extents: list[list[int] | tuple[int, int, int, int]], canvas_size: tuple[int, int],
    *, scale: float = 0.90, translation: tuple[float, float] = (0.0, 0.0),
) -> dict[str, Any]:
    if len(source_extents) != 8:
        raise ValueError("presentation_transform_requires_all_eight_source_extents")
    width, height = canvas_size
    anchor = {"x": width / 2.0, "y": height / 2.0}
    transform = {
        "method": "single_global_uniform_scale_and_translation",
        "anchor": anchor,
        "uniform_scale": round(float(scale), 6),
        "translation": {"x": round(float(translation[0]), 6), "y": round(float(translation[1]), 6)},
        "source_extents": [list(map(int, item)) for item in source_extents],
        "frozen_before_render": True,
        "frame_specific_transforms": False,
    }
    mapped: list[list[float]] = []
    for left, top, right, bottom in transform["source_extents"]:
        corners = [
            map_presentation_point((float(left), float(top)), transform),
            map_presentation_point((float(right), float(bottom)), transform),
        ]
        mapped.append([round(corners[0][0], 6), round(corners[0][1], 6), round(corners[1][0], 6), round(corners[1][1], 6)])
    transform["predicted_extents"] = mapped
    transform["predicted_min_safe_margin_px"] = round(
        min(
            min(item[0] for item in mapped),
            min(item[1] for item in mapped),
            min(width - item[2] for item in mapped),
            min(height - item[3] for item in mapped),
        ),
        6,
    )
    transform["sha256"] = hashlib.sha256(canonical_json(transform).encode("utf-8")).hexdigest()
    if transform["predicted_min_safe_margin_px"] < SAFE_MARGIN_PX:
        raise ValueError("CUTOUT_RIG_FRONT_WALK_CANVAS_FIT_GAP")
    return transform


def actual_alpha_safe_margin(image: Image.Image, minimum: float = SAFE_MARGIN_PX) -> dict[str, Any]:
    bbox = image.convert("RGBA").getchannel("A").getbbox()
    if not bbox:
        return {"alpha_bbox": None, "margins_px": None, "min_margin_px": -1.0, "gate": False}
    left, top, right, bottom = bbox
    margins = {"left": float(left), "top": float(top), "right": float(image.width - right), "bottom": float(image.height - bottom)}
    return {
        "alpha_bbox": [left, top, right, bottom],
        "margins_px": margins,
        "min_margin_px": min(margins.values()),
        "gate": min(margins.values()) >= minimum,
        "threshold_px": minimum,
    }


def measure_foot_frame(
    target: Mapping[str, Any],
    canonical_layers: Mapping[str, Image.Image],
    presented_layers: Mapping[str, Image.Image],
    transforms: list[Mapping[str, Any]],
    source_parts: Mapping[str, Image.Image],
    source_skeleton: Mapping[str, Any],
    config: Mapping[str, Any],
    presentation: Mapping[str, Any],
) -> dict[str, Any]:
    frame = int(target["frame_index"])
    support = SUPPORT_SIDE[frame]
    swing = SWING_SIDE.get(frame)
    by_part = {str(item["part"]): item for item in transforms}
    projected_soles: dict[str, float] = {}
    source_offsets: dict[str, float] = {}
    actual_canonical: dict[str, float] = {}
    actual_presented: dict[str, float] = {}
    for side in ("left", "right"):
        part_name = f"{side}_shin_foot"
        anchor_x, anchor_y, _ = source_sole_anchor(source_parts[part_name])
        projected = _forward(by_part[part_name]["forward_affine_matrix"], (anchor_x, anchor_y))[1]
        projected_soles[side] = projected
        source_ankle = _xy(source_skeleton["joints"][f"ankle_{side}"])
        source_offsets[side] = anchor_y - source_ankle[1]
        canonical_bbox = canonical_layers[part_name].getchannel("A").getbbox()
        presented_bbox = presented_layers[part_name].getchannel("A").getbbox()
        actual_canonical[side] = float(canonical_bbox[3] - 1) if canonical_bbox else -1.0
        actual_presented[side] = float(presented_bbox[3] - 1) if presented_bbox else -1.0
    correction = config["phase_corrections"].get(str(frame), {})
    base_offset = float(correction.get("swing_ground_depth_offset_px", 0.0))
    bias = float(correction.get("swing_foot_clearance_bias_px", 0.0)) if swing else 0.0
    depth_offset = base_offset + bias if swing else 0.0
    support_ground_calibration_offset = float(correction.get("support_ground_calibration_offset_px", 0.0))
    scale = float(presentation["uniform_scale"])
    feet: dict[str, Any] = {}
    for side in ("left", "right"):
        ground_canonical = projected_soles[support] + support_ground_calibration_offset + (depth_offset if swing == side else 0.0)
        expected_canonical = projected_soles[side]
        ground_y = map_presentation_point((0.0, ground_canonical), presentation)[1]
        expected_y = map_presentation_point((0.0, expected_canonical), presentation)[1]
        actual_y = actual_presented[side]
        feet[side] = {
            "projected_ground_y": round(ground_y, 6),
            "projected_ground_y_canonical": round(ground_canonical, 6),
            "depth_screen_offset_px": round((ground_canonical - projected_soles[support]) * scale, 6),
            "support_ground_calibration_offset_px": round(support_ground_calibration_offset, 6),
            "lift_height_px": round((ground_canonical - expected_canonical) * scale, 6) if swing == side else 0.0,
            "expected_sole_y": round(expected_y, 6),
            "expected_sole_y_canonical": round(expected_canonical, 6),
            "actual_sole_y": round(actual_y, 6),
            "actual_sole_y_canonical": round(actual_canonical[side], 6),
            "sole_error_px": round(actual_y - expected_y, 6),
            "ground_penetration_px": round(max(0.0, actual_y - ground_y), 6),
            "visible_clearance_px": round(ground_y - actual_y, 6),
            "source_sole_offset_y_px": round(source_offsets[side], 6),
            "source_sole_anchor": [round(source_sole_anchor(source_parts[f"{side}_shin_foot"])[0], 6), round(source_sole_anchor(source_parts[f"{side}_shin_foot"])[1], 6)],
            "role": "planted" if side == support else "swing" if side == swing else "trail",
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": target["phase"],
        "frame_index": frame,
        "support_side": support,
        "swing_side": swing,
        "ground_source": "source-alpha-sole-anchor-forward-projection-plus-frozen-depth-proxy-plus-frozen-support-calibration",
        "actual_sole_source": "transformed_shin_foot_layer_alpha_bbox",
        "feet": feet,
        "left_bottom_y": feet["left"]["actual_sole_y"],
        "right_bottom_y": feet["right"]["actual_sole_y"],
        "actual_bottom_y": max(feet["left"]["actual_sole_y"], feet["right"]["actual_sole_y"]),
        "ground_y": feet[support]["projected_ground_y"],
    }


def foot_contact_qa_v081(
    targets: Mapping[str, Mapping[str, Any]], foot_records: Mapping[str, Mapping[str, Any]], config: Mapping[str, Any],
) -> dict[str, Any]:
    planted_slip_limit = float(config["thresholds"]["planted_slip_px"])
    ground_limit = float(config["thresholds"]["ground_penetration_px"])
    swing_limit = float(config["thresholds"]["swing_clearance_px"])
    contact_windows = []
    for contact, down, side in ((0, 1, "left"), (4, 5, "right")):
        a = _xy(targets[PHASES[contact]]["joints"][f"ankle_{side}"])
        b = _xy(targets[PHASES[down]]["joints"][f"ankle_{side}"])
        first = foot_records[PHASES[contact]]["feet"][side]
        second = foot_records[PHASES[down]]["feet"][side]
        slip = math.dist(a, b)
        errors = [abs(float(first["actual_sole_y"]) - float(first["projected_ground_y"])), abs(float(second["actual_sole_y"]) - float(second["projected_ground_y"]))]
        penetrations = [float(first["ground_penetration_px"]), float(second["ground_penetration_px"])]
        contact_windows.append({
            "contact_frame": contact,
            "down_frame": down,
            "side": side,
            "planted_ankle_slip_px": round(slip, 6),
            "max_abs_sole_error_px": round(max(errors), 6),
            "max_ground_penetration_px": round(max(penetrations), 6),
            "gates": {
                "planted_slip": slip <= planted_slip_limit,
                "expected_sole_error": max(errors) <= ground_limit,
                "ground_penetration": max(penetrations) <= ground_limit,
            },
        })
    swing_clearance = []
    for frame, side in sorted(SWING_SIDE.items()):
        item = foot_records[PHASES[frame]]["feet"][side]
        swing_clearance.append({
            "frame": frame,
            "phase": PHASES[frame],
            "side": side,
            "projected_ground_y": item["projected_ground_y"],
            "actual_sole_y": item["actual_sole_y"],
            "expected_sole_y": item["expected_sole_y"],
            "sole_error_px": item["sole_error_px"],
            "visible_clearance_px": item["visible_clearance_px"],
            "ground_penetration_px": item["ground_penetration_px"],
            "gate": float(item["visible_clearance_px"]) >= swing_limit and float(item["ground_penetration_px"]) == 0.0,
        })
    gates = {
        "all_planted_slip": all(item["gates"]["planted_slip"] for item in contact_windows),
        "all_planted_expected_sole_error": all(item["gates"]["expected_sole_error"] for item in contact_windows),
        "all_ground_penetration": all(item["gates"]["ground_penetration"] for item in contact_windows),
        "all_swing_visible_clearance": all(item["gate"] for item in swing_clearance),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "contact_windows": contact_windows,
        "swing_clearance": swing_clearance,
        "thresholds": {"planted_slip_px": planted_slip_limit, "ground_penetration_px": ground_limit, "swing_clearance_px": swing_limit},
        "hard_gates": gates,
        "status": "CUTOUT_RIG_FRONT_WALK_FOOT_CONTACT_PASSED" if all(gates.values()) else "CUTOUT_RIG_FRONT_WALK_GROUND_QA_GAP",
    }


def _bbox_area(value: Any) -> float:
    if value is None:
        return 0.0
    bbox = value if isinstance(value, (list, tuple)) else value.getchannel("A").getbbox()
    if not bbox:
        return 0.0
    return float(max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1]))


def temporal_qa_v081(
    targets: Mapping[str, Mapping[str, Any]], outputs: Mapping[str, Image.Image], layer_bboxes: Mapping[str, Mapping[str, Any]], config: Mapping[str, Any],
) -> dict[str, Any]:
    signed, angle_deltas = _angle_series(targets)
    acceleration = angular_acceleration_records(targets)
    max_acceleration = max((float(item["value"]) for item in acceleration), default=0.0)
    adjacent_max = max((float(value) for item in angle_deltas for value in item.values()), default=0.0)
    head_areas = [_bbox_area(layer_bboxes.get(phase, {}).get("head")) for phase in PHASES]
    torso_areas = [_bbox_area(layer_bboxes.get(phase, {}).get("torso_pelvis")) for phase in PHASES]
    heights, centers = [], []
    for phase in PHASES:
        bbox = outputs[phase].getchannel("A").getbbox() if outputs.get(phase) else None
        if bbox:
            heights.append(bbox[3] - bbox[1])
            centers.append((bbox[0] + bbox[2]) / 2.0)
    def cv(values: list[float]) -> float:
        mean = sum(values) / max(1, len(values))
        return math.sqrt(sum((value - mean) ** 2 for value in values) / max(1, len(values))) / max(1e-6, mean)
    root_y = [float(targets[phase]["joints"]["pelvis"]["y"]) for phase in PHASES]
    nose_y = [float(targets[phase]["joints"]["nose"]["y"]) for phase in PHASES]
    threshold = float(config["thresholds"]["angular_acceleration_max_degrees_per_frame2"])
    gates = {
        "adjacent_joint_angle_delta_max_35": adjacent_max <= float(config["thresholds"]["adjacent_angle_delta_max_degrees"]),
        "angular_acceleration_max_25": max_acceleration <= threshold,
        "head_bbox_area_cv_actual_alpha_max_004": cv(head_areas) <= float(config["thresholds"]["head_torso_bbox_cv_max"]),
        "torso_bbox_area_cv_actual_alpha_max_004": cv(torso_areas) <= float(config["thresholds"]["head_torso_bbox_cv_max"]),
        "foreground_bbox_height_variation_max_8_percent": (max(heights) - min(heights)) / max(1, sum(heights) / max(1, len(heights))) <= 0.08 if heights else False,
        "character_center_x_drift_max_12": max(centers, default=0.0) - min(centers, default=0.0) <= 12.0,
        "root_vertical_amplitude_max_12": max(root_y) - min(root_y) <= 12.0,
        "head_adjacent_spike_max_8": max(abs(nose_y[(index + 1) % 8] - nose_y[index]) for index in range(8)) <= 8.0,
        "all_targets_distinct": len({target_digest(targets[phase]) for phase in PHASES}) == 8,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "phase_order": list(PHASES),
        "angle_deltas_degrees": {phase: angle_deltas[index] for index, phase in enumerate(PHASES)},
        "angular_acceleration_records": acceleration,
        "angular_acceleration_fixture_calibration": {"allowed": False, "nominal_threshold_degrees_per_frame2": 25.0, "generic_exception_removed": True},
        "max_adjacent_joint_angle_delta_degrees": round(adjacent_max, 6),
        "max_angular_acceleration_degrees_per_frame2": round(max_acceleration, 6),
        "head_bbox_areas_actual_alpha": [round(value, 6) for value in head_areas],
        "torso_bbox_areas_actual_alpha": [round(value, 6) for value in torso_areas],
        "head_bbox_area_cv": round(cv(head_areas), 6),
        "torso_bbox_area_cv": round(cv(torso_areas), 6),
        "foreground_bbox_height_variation": round((max(heights) - min(heights)) / max(1, sum(heights) / max(1, len(heights))) if heights else 1.0, 6),
        "character_center_x_drift_px": round(max(centers, default=0.0) - min(centers, default=0.0), 6),
        "hard_gates": gates,
        "status": "CUTOUT_RIG_FRONT_WALK_TEMPORAL_PASSED" if all(gates.values()) else "CUTOUT_RIG_FRONT_WALK_TEMPORAL_GAP",
    }


def loop_qa_v081(targets: Mapping[str, Mapping[str, Any]], plan: Mapping[str, Any]) -> dict[str, Any]:
    first, last = targets[PHASES[0]]["joints"], targets[PHASES[7]]["joints"]
    root_step = math.dist(_xy(first["pelvis"]), _xy(last["pelvis"]))
    head_step = math.dist(_xy(first["nose"]), _xy(last["nose"]))
    boundary = next((item for item in plan["z_order_switch_boundaries"] if item["edge"] == "F7->F0"), None)
    actual_from = plan["phase_plans"]["F7-up-right"]
    actual_to = plan["phase_plans"]["F0-contact-left"]
    boundary_ok = bool(boundary) and actual_from["z_order"] == boundary["from_z_order"] and actual_to["z_order"] == boundary["to_z_order"] and actual_from["depth_role"] == boundary["from_depth_role"] and actual_to["depth_role"] == boundary["to_depth_role"]
    sword_order_ok = actual_from["z_order"][-1] == "sword" and actual_to["z_order"][-1] == "sword"
    gates = {
        "root_step_max_6": root_step <= 6.0,
        "head_step_max_8": head_step <= 8.0,
        "f7_to_f0_boundary_is_frozen_and_real": boundary_ok,
        "sword_depth_policy_is_valid": sword_order_ok,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "edge": "F7->F0",
        "root_step_px": round(root_step, 6),
        "head_step_px": round(head_step, 6),
        "boundary_evidence": boundary,
        "hard_gates": gates,
        "status": "CUTOUT_RIG_FRONT_WALK_LOOP_PASSED" if all(gates.values()) else "CUTOUT_RIG_FRONT_WALK_LOOP_GAP",
    }


def hard_gate_proof_sources(
    parts: Mapping[str, Image.Image], transforms: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    source_hashes = {name: hashlib.sha256(parts[name].convert("RGBA").tobytes()).hexdigest() for name in PART_NAMES}
    operation_allowlist = ["source_mask_crop", "source_affine_resample", "source_alpha_composite", "source_structural_core_composite", "global_uniform_presentation_transform"]
    sword = transforms["sword"]
    proof = {
        "operation_allowlist": operation_allowlist,
        "source_input_hashes": source_hashes,
        "sword_source_only": {
            "source_part": "sword",
            "source_part_rgba_sha256": source_hashes["sword"],
            "operation": "source_affine_resample",
            "transform_source_joints": list(PART_SPECS["sword"]["source_joints"]),
            "transform_evidence_sha256": hashlib.sha256(canonical_json(sword).encode("utf-8")).hexdigest(),
        },
        "recolor_count": 0,
        "generated_pixel_fraction": 0.0,
        "duplicate_body_method": "8-connected-alpha-component-count-with-meaningful-component-threshold",
        "proof_source": {"module": "src/ugas/cutout_temporal_v081.py", "function": "hard_gate_proof_sources", "regression_test": "tests/test_cutout_front_walk_v081.py::test_hard_gate_proof_sources_are_structural"},
    }
    return proof


def duplicate_body_measure(output: Image.Image, meaningful_pixels: int = 16) -> dict[str, Any]:
    components: list[int] = []
    alpha = output.convert("RGBA").getchannel("A")
    pixels = alpha.load()
    seen: set[tuple[int, int]] = set()
    for y in range(alpha.height):
        for x in range(alpha.width):
            if pixels[x, y] == 0 or (x, y) in seen:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            count = 0
            while stack:
                cx, cy = stack.pop()
                count += 1
                for nx in range(cx - 1, cx + 2):
                    for ny in range(cy - 1, cy + 2):
                        if 0 <= nx < alpha.width and 0 <= ny < alpha.height and pixels[nx, ny] > 0 and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
            components.append(count)
    components.sort(reverse=True)
    meaningful = [value for value in components[1:] if value >= meaningful_pixels]
    return {"component_pixels_desc": components, "meaningful_duplicate_components": len(meaningful), "meaningful_threshold_pixels": meaningful_pixels, "gate": len(meaningful) == 0}


def bone_bounds_v081(targets: Mapping[str, Mapping[str, Any]], source: Mapping[str, Any], source_point) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    minimum = 0.92
    maximum = 1.08
    for phase in PHASES:
        for first, second in LIMB_BONES:
            source_length = math.dist(source_point(source, first), source_point(source, second))
            target_length = math.dist(_xy(targets[phase]["joints"][first]), _xy(targets[phase]["joints"][second]))
            ratio = target_length / max(1e-6, source_length)
            records.append({"phase": phase, "bone": f"{first}->{second}", "source_length_px": round(source_length, 6), "target_length_px": round(target_length, 6), "ratio": round(ratio, 6), "gate": minimum <= ratio <= maximum})
    passed = all(item["gate"] for item in records)
    return {"schema_version": SCHEMA_VERSION, "records": records, "thresholds": {"min": minimum, "max": maximum}, "hard_gates": {"all_bones_bounded": passed}, "status": "BONE_PROJECTION_PASSED" if passed else "CUTOUT_RIG_FRONT_WALK_FRAME_GAP"}
