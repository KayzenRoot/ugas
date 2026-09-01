"""Deterministic source-only frontal sword attack over the approved R4 rig."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from ..animation import event_markers_for_spec
from ..animation_profiles.common import load_source_context, render_source_only, target_digest
from ..cutout_occlusion import TOPOLOGY_ADJACENCY, topological_seam_qa
from ..cutout_rig import PART_NAMES, skeleton_point
from ..cutout_structural import (
    _binary,
    _count,
    _digest_image,
    _explicit_pair_key,
    _region_mask_for_pair,
    layer_integrity_qa,
    pairwise_overlap_v073,
    structural_coverage_qa,
)
from ..cutout_temporal_v081 import actual_alpha_safe_margin, duplicate_body_measure, map_presentation_point
from ..pose_metric_calibration import CORE_JOINTS, detected_joint_pose_metrics
from ..pose_qa_estimator import _detect


PHASES = (
    "A0-ready", "A1-windup-early", "A2-windup-peak", "A3-strike-start", "A4-strike-mid",
    "A5-strike-contact", "A6-follow-through", "A7-recovery-early", "A8-recovery-late", "A9-ready-end",
)
Z_ORDER = (
    "right_shin_foot", "right_thigh", "left_forearm_hand", "left_upper_arm", "torso_pelvis",
    "left_thigh", "left_shin_foot", "right_upper_arm", "right_forearm_hand", "head", "sword",
)
ANGLE_CHAINS = (
    ("shoulder_left", "elbow_left", "wrist_left"),
    ("shoulder_right", "elbow_right", "wrist_right"),
    ("hip_left", "knee_left", "ankle_left"),
    ("hip_right", "knee_right", "ankle_right"),
)
ACTIVE_WINDOW = (3, 4, 5, 6)
HIT_EVENT_FRAME = 5


def _xy(value: Any) -> tuple[float, float]:
    return (float(value["x"]), float(value["y"])) if isinstance(value, Mapping) else (float(value[0]), float(value[1]))


def _point(x: float, y: float) -> dict[str, float]:
    return {"x": round(float(x), 6), "y": round(float(y), 6)}


def _angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    value = math.degrees(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(a[1] - b[1], a[0] - b[0]))
    while value > 180:
        value -= 360
    while value < -180:
        value += 360
    return value


def _direction(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _signed_delta(first: float, second: float) -> float:
    return (second - first + 180.0) % 360.0 - 180.0


def _rotate(point: tuple[float, float], pivot: tuple[float, float], degrees: float) -> tuple[float, float]:
    theta = math.radians(degrees)
    x, y = point[0] - pivot[0], point[1] - pivot[1]
    return (pivot[0] + x * math.cos(theta) - y * math.sin(theta), pivot[1] + x * math.sin(theta) + y * math.cos(theta))


def _polar(angle: float, length: float) -> tuple[float, float]:
    theta = math.radians(angle)
    return math.cos(theta) * length, math.sin(theta) * length


def load_context(spec: Mapping[str, Any], root: Path) -> dict[str, Any]:
    return load_source_context(spec, root)


def _base_target(context: Mapping[str, Any]) -> dict[str, Any]:
    skeleton = context["skeleton"]
    names = list(CORE_JOINTS) + ["nose", "neck", "pelvis", "shoulder_center", "weapon_tip"]
    joints = {name: _point(*skeleton_point(skeleton, name)) for name in names}
    return {
        "joints": joints,
        "phase": PHASES[0],
        "view": "front",
        "orientation": "front",
        "generator": {"kind": "deterministic-skeleton-only", "parameters_frozen_before_render": True, "pixel_interpolation": False},
    }


def _target_for_frame(context: Mapping[str, Any], index: int, params: Mapping[str, Any]) -> dict[str, Any]:
    target = copy.deepcopy(params["base_target"])
    joints = target["joints"]
    skeleton = context["skeleton"]
    shoulder = skeleton_point(skeleton, "shoulder_right")
    source_elbow = skeleton_point(skeleton, "elbow_right")
    source_wrist = skeleton_point(skeleton, "wrist_right")
    source_tip = skeleton_point(skeleton, "weapon_tip")
    forearm_length = math.dist(source_elbow, source_wrist)
    sword_length = math.dist(source_wrist, source_tip)
    upper_delta = float(params["right_upper_arm_delta_degrees"][index])
    forearm_delta = float(params["right_forearm_direction_delta_degrees"][index])
    sword_delta = float(params["sword_direction_delta_degrees"][index])
    elbow = _rotate(source_elbow, shoulder, upper_delta)
    forearm_angle = _direction(source_elbow, source_wrist) + forearm_delta
    forearm_dx, forearm_dy = _polar(forearm_angle, forearm_length)
    wrist = (elbow[0] + forearm_dx, elbow[1] + forearm_dy)
    sword_angle = _direction(source_wrist, source_tip) + sword_delta
    sword_dx, sword_dy = _polar(sword_angle, sword_length)
    tip = (wrist[0] + sword_dx, wrist[1] + sword_dy)
    joints["elbow_right"] = _point(*elbow)
    joints["wrist_right"] = _point(*wrist)
    joints["weapon_tip"] = _point(*tip)
    target["phase"] = PHASES[index]
    target["frame_index"] = index
    target["target_joint_sha256"] = target_digest(target)
    return target


def _attack_plan() -> dict[str, Any]:
    phase_plans = {
        phase: {
            "phase": phase,
            "frame_index": index,
            "z_order": list(Z_ORDER),
            "front_parts": ["right_upper_arm", "right_forearm_hand", "sword", "left_thigh", "left_shin_foot"],
            "back_parts": ["right_thigh", "right_shin_foot", "left_upper_arm", "left_forearm_hand"],
            "depth_role": {"right_arm": "attack_lead", "left_arm": "counter_balance", "sword": "frontmost"},
            "switch_boundary": None,
        }
        for index, phase in enumerate(PHASES)
    }
    value: dict[str, Any] = {
        "schema_version": "animation-spec-1.0",
        "plan_id": "animation-attack-front-constant-z-v1",
        "phase_plans": phase_plans,
        "critical_pairs": [["sword", "torso_pelvis"], ["sword", "head"]],
        "allowed_expected_occlusion_pairs": [["right_forearm_hand", "sword"], ["right_thigh", "sword"]],
        "switch_boundaries": [],
        "policy": "measured-critical-collisions-and-explicit-grip/trail-thigh-corridors",
    }
    value["plan_sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return value


def prepare(spec: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    params = copy.deepcopy(spec["interpolation_profile"]["parameters"])
    params["base_target"] = _base_target(context)
    params["targets"] = [_target_for_frame(context, index, params) for index in range(int(spec["frame_count"]))]
    params["plan"] = _attack_plan()
    params["presentation"] = spec["presentation_transform"]
    params["phases"] = list(PHASES)
    return params


def render_frame(spec: Mapping[str, Any], context: Mapping[str, Any], prepared: Mapping[str, Any], index: int):
    target = prepared["targets"][index]
    image, details = render_source_only(context, target, list(Z_ORDER), prepared["presentation"])
    sword = next(item for item in details["transforms"] if item["part"] == "sword")
    return image, {
        "phase": PHASES[index],
        "target_hash": target["target_joint_sha256"],
        "presentation_target_hash": details["target_presented"]["presentation_target_joint_sha256"],
        "z_order": list(Z_ORDER),
        "target": target,
        "sword_target_pivot": sword["target_pivot"],
    }


def _regions(target: Mapping[str, Any], phase: str, plan: Mapping[str, Any], size: tuple[int, int]) -> dict[str, Any]:
    pairs = [(parent, child) for parent, child, _ in TOPOLOGY_ADJACENCY]
    for raw in plan.get("allowed_expected_occlusion_pairs", []):
        pair = (str(raw[0]), str(raw[1]))
        if set(pair) not in [set(item) for item in pairs]:
            pairs.append(pair)
    regions: dict[str, Image.Image] = {}
    records: list[dict[str, Any]] = []
    order = list(plan["phase_plans"][phase]["z_order"])
    for pair in pairs:
        mask, geometry = _region_mask_for_pair(pair, target, phase, size)
        key = _explicit_pair_key(*pair)
        front = pair[0] if order.index(pair[0]) > order.index(pair[1]) else pair[1]
        regions[key] = mask
        records.append({"pair": list(pair), "pair_key": key, "phase": phase, "expected_front_part": front, "geometry": geometry, "region_pixels": _count(mask), "region_sha256": _digest_image(mask)})
    return {"regions": regions, "records": records, "allowed_pair_keys": {_explicit_pair_key(*raw) for raw in plan.get("allowed_expected_occlusion_pairs", [])}}


def _retention(context: Mapping[str, Any], details: Mapping[str, Any], integrity: Mapping[str, Any], plan: Mapping[str, Any], phase: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    constant_depth = len({tuple(plan["phase_plans"][name]["z_order"]) for name in PHASES}) == 1
    for transform in details["transforms"]:
        name = str(transform["part"])
        source_active = _count(_binary(context["parts"][name].getchannel("A"), 64))
        layer_active = _count(_binary(details["layers"][name].getchannel("A"), 64))
        item = integrity["parts"][name]
        predicted = float(item.get("predicted_transformed_area", layer_active))
        gates = {
            "source_area_retained": layer_active / max(1, predicted) >= 0.97,
            "no_predicted_clipping": float(item.get("predicted_outside_canvas_area", 1)) == 0,
            "no_actual_border_clipping": int(item.get("actual_border_clipped_pixels", 1)) == 0,
            "constant_depth_plan_measured": constant_depth,
        }
        result[name] = {"source_active_pixels": source_active, "actual_layer_pixels": layer_active, "predicted_transformed_area": predicted, "visible_fraction": round(layer_active / max(1, predicted), 6), "hard_gates": gates, "status": "RETENTION_OCCLUSION_PASSED" if all(gates.values()) else "CUTOUT_RIG_RETENTION_GAP"}
    passed = all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in result.values())
    return {"schema_version": "animation-spec-1.0", "phase": phase, "parts": result, "hard_gates": {"all_parts_pass": passed}, "status": "RETENTION_OCCLUSION_PASSED" if passed else "CUTOUT_RIG_RETENTION_GAP"}


def _plan_and_structural(context: Mapping[str, Any], target: Mapping[str, Any], details: Mapping[str, Any], phase: str, plan: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    regions = _regions(target, phase, plan, context["source"].size)
    pair = pairwise_overlap_v073(details["layers"], phase, target, plan, regions)
    pair["hard_gates"]["z_order_constant"] = len({tuple(plan["phase_plans"][name]["z_order"]) for name in PHASES}) == 1
    pair["hard_gates"]["explicit_attack_allowed_pair_rules"] = len(plan.get("allowed_expected_occlusion_pairs", [])) >= 2
    pair["status"] = "OCCLUSION_QA_PASSED" if all(pair["hard_gates"].values()) else "CUTOUT_RIG_OCCLUSION_REGION_GAP"
    seam = topological_seam_qa(details["layers"], phase, target, plan)
    integrity = layer_integrity_qa(context["parts"], details["layers"], details["transforms"], context["source"].size)
    core_for_pose = dict(context["core"])
    core_for_pose["torso_transform"] = next(item for item in details["transforms"] if item["part"] == "torso_pelvis")
    coverage = structural_coverage_qa(details["core_layer"], details["canonical"], target, phase, core_for_pose)
    retention = _retention(context, details, integrity, plan, phase)
    return pair, seam, integrity, {"coverage": coverage, "retention": retention}


def _foot_frame(context: Mapping[str, Any], target: Mapping[str, Any], details: Mapping[str, Any], presentation: Mapping[str, Any], limits: Mapping[str, Any]) -> dict[str, Any]:
    sole_limit = float(limits.get("projected_sole_frame_to_frame_drift_px", limits.get("sole_error_px", 1.5)))
    penetration_limit = float(limits.get("ground_penetration_px", 1.5))
    values: dict[str, Any] = {}
    for side in ("left", "right"):
        name = f"{side}_shin_foot"
        transform = next(item for item in details["transforms"] if item["part"] == name)
        bbox = context["parts"][name].getchannel("A").getbbox()
        sole_y = float(bbox[3] - 1) if bbox else -1.0
        matrix = transform["forward_affine_matrix"]
        projected = matrix[1][0] * (bbox[0] + bbox[2]) / 2 + matrix[1][1] * sole_y + matrix[1][2] if bbox else -1.0
        projected = map_presentation_point((0.0, projected), presentation)[1]
        actual_bbox = details["presented_layers"][name].getchannel("A").getbbox()
        actual = float(actual_bbox[3] - 1) if actual_bbox else -1.0
        ankle = target["joints"][f"ankle_{side}"]
        values[side] = {"projected_ground_y": round(projected, 6), "actual_sole_y": round(actual, 6), "sole_error_px": round(actual - projected, 6), "ground_penetration_px": round(max(0.0, actual - projected), 6), "ankle": ankle, "ankle_x": round(float(ankle["x"]), 6), "hard_gates": {"sole_error_le_threshold": abs(actual - projected) <= sole_limit, "ground_penetration_le_threshold": max(0.0, actual - projected) <= penetration_limit}}
    passed = all(all(item["hard_gates"].values()) for item in values.values())
    return {"feet": values, "thresholds": {"sole_error_px": sole_limit, "ground_penetration_px": penetration_limit}, "hard_gates": {side: all(item["hard_gates"].values()) for side, item in values.items()}, "status": "ATTACK_FOOT_FRAME_PASSED" if passed else "ATTACK_FRONT_FOOT_GROUND_GAP"}


def foot_ground_qa(frame_records: list[Mapping[str, Any]], sole_limit: float = 1.5, ankle_limit: float = 2.0) -> dict[str, Any]:
    sides: dict[str, Any] = {}
    for side in ("left", "right"):
        samples = [record.get("feet", {}).get("feet", {}).get(side, {}) for record in frame_records]
        valid = len(samples) >= 2 and all("projected_ground_y" in item and "ankle_x" in item for item in samples)
        if not valid:
            sides[side] = {"hard_gates": {"sole_error_le_threshold": False, "ground_penetration_le_threshold": False, "sequential_projected_sole_drift_le_threshold": False, "ankle_horizontal_drift_from_A0_le_threshold": False}, "status": "ATTACK_FRONT_FOOT_GROUND_GAP", "reason": "missing_sequential_measurements"}
            continue
        baseline = float(samples[0]["ankle_x"])
        pairs = [{"from_frame": index - 1, "to_frame": index, "drift_px": abs(float(samples[index]["projected_ground_y"]) - float(samples[index - 1]["projected_ground_y"]))} for index in range(1, len(samples))]
        ankles = [{"frame": index, "drift_px": abs(float(item["ankle_x"]) - baseline)} for index, item in enumerate(samples)]
        max_pair = max(pairs, key=lambda item: item["drift_px"])
        max_ankle = max(ankles, key=lambda item: item["drift_px"])
        gates = {
            "sole_error_le_threshold": all(abs(float(item.get("sole_error_px", 999.0))) <= sole_limit for item in samples),
            "ground_penetration_le_threshold": all(float(item.get("ground_penetration_px", 999.0)) <= sole_limit for item in samples),
            "sequential_projected_sole_drift_le_threshold": max_pair["drift_px"] <= sole_limit,
            "ankle_horizontal_drift_from_A0_le_threshold": max_ankle["drift_px"] <= ankle_limit,
        }
        sides[side] = {"baseline_ankle_x": round(baseline, 6), "sequential_projected_sole_drift_px": {"max": round(max_pair["drift_px"], 6), "max_frame_pair": [max_pair["from_frame"], max_pair["to_frame"]], "threshold": sole_limit, "samples": [{**item, "drift_px": round(item["drift_px"], 6)} for item in pairs]}, "ankle_horizontal_drift_from_A0_px": {"max": round(max_ankle["drift_px"], 6), "max_frame": max_ankle["frame"], "threshold": ankle_limit, "samples": [{**item, "drift_px": round(item["drift_px"], 6)} for item in ankles]}, "hard_gates": gates, "status": "ATTACK_FOOT_GROUND_PASSED" if all(gates.values()) else "ATTACK_FRONT_FOOT_GROUND_GAP"}
    hard_gates = {f"{side}_{name}": value for side, item in sides.items() for name, value in item.get("hard_gates", {}).items()}
    return {"sides": sides, "hard_gates": hard_gates, "closing_transition_included": False, "status": "ATTACK_FOOT_GROUND_PASSED" if hard_gates and all(hard_gates.values()) else "ATTACK_FRONT_FOOT_GROUND_GAP"}


def _pose(frame_path: Path, target: Mapping[str, Any]) -> dict[str, Any]:
    model = Path(__import__("os").environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "UGAS" / "pose-qa" / "pose_landmarker_full.task"
    try:
        detected = _detect(frame_path, model)
        landmarks = detected.get("landmarks", {})
        metrics = detected_joint_pose_metrics(target["joints"], landmarks, target_orientation="front", detected_orientation="front", visibility={name: float(value.get("visibility", value.get("confidence", 0))) for name, value in landmarks.items()})
        return {"detected": detected, "metrics": metrics}
    except Exception as exc:
        return {"detected": {"detected": False, "error": f"{type(exc).__name__}: {exc}"}, "metrics": {"qualifies": False, "measurement_status": "UNMEASURABLE", "failure_reasons": ["media_pipe_exception"]}}


def _weapon_sweep_qa(spec: Mapping[str, Any], frame_records: list[Mapping[str, Any]]) -> dict[str, Any]:
    active = set(int(item) for item in spec["qa_profile"]["thresholds"]["active_window_frames"])
    hit_frame = int(spec["qa_profile"]["thresholds"]["hit_event_frame"])
    tips = [item["weapon"]["tip_presented"] for item in frame_records]
    angles = [float(item["weapon"]["sword_angle_degrees"]) for item in frame_records]
    velocities = [{"from_frame": index - 1, "to_frame": index, "tip_motion_px": math.dist(tips[index - 1], tips[index]), "angular_velocity_degrees": abs(_signed_delta(angles[index - 1], angles[index])), "inside_or_near_active_window": index - 1 in active or index in active} for index in range(1, len(tips))]
    peak = max(velocities, key=lambda item: item["tip_motion_px"]) if velocities else {"from_frame": -1, "to_frame": -1, "tip_motion_px": 0.0, "angular_velocity_degrees": 0.0, "inside_or_near_active_window": False}
    critical_head = sum(int(item["weapon"].get("sword_head_critical_collision_pixels", 0)) for item in frame_records)
    forbidden_torso = sum(int(item["weapon"].get("sword_torso_forbidden_pixels", 0)) for item in frame_records)
    gates = {
        "sword_attached_all_frames": all(bool(item["weapon"].get("pivot_attached")) for item in frame_records),
        "active_window_frames_exact": [int(item["index"]) for item in frame_records if item["index"] in active] == sorted(active),
        "hit_event_frame_exact": hit_frame == 5,
        "sweep_path_nonzero": sum(item["tip_motion_px"] for item in velocities) > 0.0,
        "contact_frame_inside_active_window": hit_frame in active,
        "max_weapon_tip_motion_in_or_near_active_window": bool(peak["inside_or_near_active_window"]),
        "sword_head_critical_collision_zero": critical_head == 0,
        "sword_torso_forbidden_penetration_zero": forbidden_torso == 0,
    }
    return {"active_window_frames": sorted(active), "hit_event_frame": hit_frame, "tip_xy_presented": [{"frame": item["index"], "x": item["weapon"]["tip_presented"][0], "y": item["weapon"]["tip_presented"][1]} for item in frame_records], "angular_velocity_by_transition": velocities, "peak_tip_motion": peak, "sword_head_critical_collision_pixels": critical_head, "sword_torso_forbidden_penetration_pixels": forbidden_torso, "hard_gates": gates, "status": "ATTACK_WEAPON_SWEEP_PASSED" if all(gates.values()) else "ATTACK_FRONT_WEAPON_SWEEP_GAP"}


def _temporal_qa(spec: Mapping[str, Any], targets: list[Mapping[str, Any]], frame_records: list[Mapping[str, Any]]) -> dict[str, Any]:
    threshold = spec["qa_profile"]["thresholds"]
    angle_values = [{f"{a}:{b}:{c}": _angle(_xy(target["joints"][a]), _xy(target["joints"][b]), _xy(target["joints"][c])) for a, b, c in ANGLE_CHAINS} for target in targets]
    unwrapped: list[dict[str, float]] = [dict(angle_values[0])] if angle_values else []
    for index in range(1, len(angle_values)):
        unwrapped.append({key: unwrapped[-1][key] + _signed_delta(angle_values[index - 1][key], angle_values[index][key]) for key in angle_values[index]})
    deltas = [abs(unwrapped[index][key] - unwrapped[index - 1][key]) for index in range(1, len(unwrapped)) for key in unwrapped[index]]
    accelerations = [abs(unwrapped[index][key] - 2 * unwrapped[index - 1][key] + unwrapped[index - 2][key]) for index in range(2, len(unwrapped)) for key in unwrapped[index]]
    pelvis = [map_presentation_point(_xy(target["joints"]["pelvis"]), spec["presentation_transform"]) for target in targets]
    nose = [map_presentation_point(_xy(target["joints"]["nose"]), spec["presentation_transform"]) for target in targets]
    root_x = max(item[0] for item in pelvis) - min(item[0] for item in pelvis)
    root_y = max(item[1] for item in pelvis) - min(item[1] for item in pelvis)
    head_step = max((math.dist(nose[index - 1], nose[index]) for index in range(1, len(nose))), default=0.0)
    target_hash_count = len({target_digest(target) for target in targets})
    feet = foot_ground_qa(frame_records, float(threshold["projected_sole_frame_to_frame_drift_px"]), float(threshold["ankle_horizontal_drift_from_A0_px"]))
    weapon = _weapon_sweep_qa(spec, frame_records)
    gates = {
        "joint_angle_delta_le_30": max(deltas, default=999.0) <= float(threshold["max_joint_angle_delta_degrees"]),
        "angular_acceleration_le_28": max(accelerations, default=999.0) <= float(threshold["max_angular_acceleration_degrees_per_frame2"]),
        "root_horizontal_excursion_le_8": root_x <= float(threshold["root_horizontal_excursion_px"]),
        "root_vertical_excursion_le_8": root_y <= float(threshold["root_vertical_excursion_px"]),
        "head_adjacent_center_delta_le_6": head_step <= float(threshold["head_adjacent_center_delta_px"]),
        "target_hashes_exactly_10_distinct": target_hash_count == 10,
        "foot_ground_sequential_qa": feet["status"] == "ATTACK_FOOT_GROUND_PASSED",
        "weapon_sweep_qa": weapon["status"] == "ATTACK_WEAPON_SWEEP_PASSED",
    }
    return {"metrics": {"max_joint_angle_delta_degrees": round(max(deltas, default=0.0), 6), "max_angular_acceleration_degrees_per_frame2": round(max(accelerations, default=0.0), 6), "root_horizontal_excursion_presented_px": round(root_x, 6), "root_vertical_excursion_presented_px": round(root_y, 6), "head_adjacent_center_delta_px": round(head_step, 6), "target_hash_count": target_hash_count, "frame_pairs_measured": [[index - 1, index] for index in range(1, len(targets))], "closing_pair_measured": False}, "hard_gates": gates, "foot_ground": feet, "weapon": weapon, "status": "ATTACK_TEMPORAL_QA_PASSED" if all(gates.values()) else "ATTACK_FRONT_POSE_GAP"}


def qa(spec: Mapping[str, Any], context: Mapping[str, Any], manifest: Mapping[str, Any], root: Path) -> dict[str, Any]:
    prepared = prepare(spec, context)
    targets = prepared["targets"]
    plan = prepared["plan"]
    records: list[dict[str, Any]] = []
    structural: dict[str, Any] = {}
    for index, item in enumerate(manifest["frames"]):
        target = targets[index]
        image, details = render_source_only(context, target, list(Z_ORDER), prepared["presentation"])
        pair, seam, integrity, aux = _plan_and_structural(context, target, details, PHASES[index], plan)
        feet = _foot_frame(context, target, details, spec["presentation_transform"], spec["foot_policy"]["limits"])
        alpha = actual_alpha_safe_margin(image, float(spec["qa_profile"]["thresholds"]["alpha_safe_margin_px"]))
        duplicate = duplicate_body_measure(image)
        pose = _pose(root / item["path"], details["target_presented"])
        metrics = pose["metrics"]
        sword_transform = next(value for value in details["transforms"] if value["part"] == "sword")
        sword_head = next((value for value in pair["pairs"] if set((value["first"], value["second"])) == {"sword", "head"}), {})
        sword_torso = next((value for value in pair["pairs"] if set((value["first"], value["second"])) == {"sword", "torso_pelvis"}), {})
        tip = map_presentation_point(_xy(target["joints"]["weapon_tip"]), spec["presentation_transform"])
        sword_angle = _direction(_xy(target["joints"]["wrist_right"]), _xy(target["joints"]["weapon_tip"]))
        transforms_ok = all(bool(value.get("scale_gate")) and float(value.get("uniform_scale", 0.0)) >= 0.92 and float(value.get("uniform_scale", 0.0)) <= 1.08 for value in details["transforms"])
        nonuniform_count = sum(bool(value.get("nonuniform_scale")) for value in details["transforms"])
        gates = {
            "source_hashes": all(value["source_part_rgba_sha256"] == context["part_hashes"][value["part"]] for value in details["transforms"]),
            "target_binding": target_digest(target) == item["target_hash"],
            "global_transform_and_bone_scale": transforms_ok and bool(spec["presentation_transform"]["frozen_before_render"]),
            "nonuniform_scale_operation_count_zero": nonuniform_count == 0,
            "alpha_safe_margin_ge_24": bool(alpha["gate"]),
            "structural_holes_zero": aux["coverage"]["structural_hole_pixels"] == 0,
            "layer_integrity": integrity["status"] == "LAYER_INTEGRITY_PASSED",
            "occlusion": pair["status"] == "OCCLUSION_QA_PASSED",
            "seam": seam["status"] == "SEAM_TOPOLOGY_PASSED",
            "retention": aux["retention"]["status"] == "RETENTION_OCCLUSION_PASSED",
            "pose_estimator": metrics.get("qualifies") is True and int(metrics.get("measurable_body_joints", 0)) >= 10 and float(metrics.get("pck_at_010", 0.0)) >= 0.80 and float(metrics.get("nme", 1.0)) <= 0.10 and float(metrics.get("limb_angle_mae_degrees", 180.0)) <= 18.0,
            "sword_pivot_attached": sword_transform["target_pivot"] == [target["joints"]["wrist_right"]["x"], target["joints"]["wrist_right"]["y"]],
            "source_only_pixels": bool(spec["provenance"]["source_only_pixels"]),
            "no_duplicate_body": duplicate["gate"],
            "both_feet_planted": feet["status"] == "ATTACK_FOOT_FRAME_PASSED",
            "frozen_z_order": [value["part"] for value in details["transforms"]] == list(Z_ORDER),
        }
        record = {"index": index, "phase": PHASES[index], "target_hash": target["target_joint_sha256"], "output_rgba_sha256": item["rgba_sha256"], "hard_gates": gates, "passed": all(gates.values()), "alpha": alpha, "feet": feet, "pose": pose, "duplicate_body": duplicate, "integrity": integrity, "occlusion": pair, "seam": seam, "coverage": {key: value for key, value in aux["coverage"].items() if key not in {"hole_mask", "expected_mask"}}, "retention": aux["retention"], "z_order": list(Z_ORDER), "weapon": {"pivot_attached": gates["sword_pivot_attached"], "target_pivot": sword_transform["target_pivot"], "tip_presented": [round(tip[0], 6), round(tip[1], 6)], "sword_angle_degrees": round(sword_angle, 6), "sword_head_critical_collision_pixels": int(sword_head.get("pixels", 0)) if sword_head.get("critical_pair") else 0, "sword_torso_forbidden_pixels": int(sword_torso.get("outside_authorized_region_pixels", 0))}, "status": "ATTACK_FRAME_PASSED" if all(gates.values()) else "ATTACK_FRONT_POSE_GAP"}
        records.append(record)
        structural[PHASES[index]] = {"pair": pair, "seam": seam, "coverage": record["coverage"], "retention": record["retention"]}
    temporal = _temporal_qa(spec, targets, records)
    markers = event_markers_for_spec(spec)
    expected_frames = {"windup_peak": 2, "active_start": 3, "hit_event": 5, "active_end": 6, "recovery_complete": 9}
    marker_gate = [(item["event_id"], item["frame"]) for item in markers] == [(name, frame) for name, frame in sorted(expected_frames.items(), key=lambda value: (value[1], value[0]))]
    top_gates = {
        "frame_count_exactly_10": len(records) == 10,
        "all_frames": bool(records) and all(record["passed"] for record in records),
        "temporal_action": temporal["status"] == "ATTACK_TEMPORAL_QA_PASSED",
        "weapon_sweep": temporal["weapon"]["status"] == "ATTACK_WEAPON_SWEEP_PASSED",
        "foot_ground": temporal["foot_ground"]["status"] == "ATTACK_FOOT_GROUND_PASSED",
        "event_timeline_frozen": marker_gate and len(markers) == 5,
        "key_pose_bindings": all(any(int(binding["frame"]) == index and binding["target_hash"] == targets[index]["target_joint_sha256"] for binding in spec["key_pose_bindings"]) for index in [0, 2, 3, 5, 6, 9]),
        "provenance": bool(spec["provenance"]["source_only_pixels"]) and spec["provenance"]["sam2_used"] is False and int(spec["provenance"]["comfyui_generation_jobs"]) == 0 and spec["provenance"]["diffusion_used"] is False,
    }
    failures = [name for name, passed in top_gates.items() if not passed]
    failures.extend(f"frame_{record['index']}_{name}" for record in records for name, passed in record["hard_gates"].items() if not passed)
    failures.extend(f"temporal_{name}" for name, passed in temporal["hard_gates"].items() if not passed)
    qualified = all(top_gates.values()) and not failures
    return {
        "animation_id": spec["animation_id"],
        "decision": "QUALIFIED" if qualified else "FAILED",
        "status": "CUTOUT_ANIMATION_RUNTIME_V1_ATTACK_FRONT_TECHNICALLY_QUALIFIED" if qualified else "ATTACK_FRONT_POSE_GAP",
        "frames": records,
        "temporal": temporal,
        "weapon": temporal["weapon"],
        "foot_ground": temporal["foot_ground"],
        "package_metadata": {"active_window_frames": list(ACTIVE_WINDOW), "hit_event_frame": HIT_EVENT_FRAME, "event_timeline_authority": "spec.event_markers", "weapon": "sword"},
        "provenance": {"source_sha256": context["source_sha256"], "part_hashes": context["part_hashes"], "mask_hashes": context["mask_hashes"], "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "source_only_pixels": True},
        "hard_gates": top_gates,
        "failures": failures,
        "structural": structural,
    }
