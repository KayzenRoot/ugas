"""Deterministic source-only frontal sword attack using the generic motion layer.

The adapter is the only place that assigns meaning to opaque motion-track IDs.
All tracks are sampled before rasterization, and every motion proxy is measured
from the target skeleton before any PNG is written.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from ..animation import event_markers_for_spec
from ..cutout_occlusion import TOPOLOGY_ADJACENCY, topological_seam_qa
from ..cutout_rig import skeleton_point
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
from ..motion_curves import sample_all_tracks, validate_motion_tracks
from ..pose_metric_calibration import CORE_JOINTS
from . import attack_front_v1 as v1
from .common import load_source_context, render_source_only, target_digest


PHASES = (
    "V0-ready", "V1-anticipation-early", "V2-anticipation", "V3-windup-peak",
    "V4-strike-start", "V5-strike-mid", "V6-strike-contact", "V7-follow-through",
    "V8-follow-through-late", "V9-recovery-early", "V10-recovery-late", "V11-ready-end",
)
Z_ORDER = v1.Z_ORDER
ANGLE_CHAINS = v1.ANGLE_CHAINS
ACTIVE_WINDOW = (4, 5, 6, 7)
HIT_EVENT_FRAME = 6
REQUIRED_TRACKS = (
    "root_shift_x", "root_shift_y", "torso_rotation_deg", "torso_lean_x",
    "right_upper_arm_rotation_deg", "right_forearm_rotation_deg", "right_wrist/grip_rotation_deg",
    "sword_rotation_deg", "left_upper_arm_counter_deg", "left_forearm_counter_deg", "head_counter_rotation_deg",
)


def _xy(value: Any) -> tuple[float, float]:
    return (float(value["x"]), float(value["y"])) if isinstance(value, Mapping) else (float(value[0]), float(value[1]))


def _point(x: float, y: float) -> dict[str, float]:
    return {"x": round(float(x), 6), "y": round(float(y), 6)}


def _direction(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.degrees(math.atan2(second[1] - first[1], second[0] - first[0]))


def _signed_delta(first: float, second: float) -> float:
    return (second - first + 180.0) % 360.0 - 180.0


def _angle(first: tuple[float, float], middle: tuple[float, float], last: tuple[float, float]) -> float:
    value = math.degrees(math.atan2(last[1] - middle[1], last[0] - middle[0]) - math.atan2(first[1] - middle[1], first[0] - middle[0]))
    while value > 180.0:
        value -= 360.0
    while value < -180.0:
        value += 360.0
    return value


def _rotate(point: tuple[float, float], pivot: tuple[float, float], degrees: float) -> tuple[float, float]:
    theta = math.radians(degrees)
    x, y = point[0] - pivot[0], point[1] - pivot[1]
    return (pivot[0] + x * math.cos(theta) - y * math.sin(theta), pivot[1] + x * math.sin(theta) + y * math.cos(theta))


def _polar(angle: float, length: float) -> tuple[float, float]:
    theta = math.radians(angle)
    return math.cos(theta) * length, math.sin(theta) * length


def load_context(spec: Mapping[str, Any], root: Path) -> dict[str, Any]:
    context = load_source_context(spec, root)
    context["root"] = root.resolve()
    return context


def _base_target(context: Mapping[str, Any]) -> dict[str, Any]:
    skeleton = context["skeleton"]
    names = list(CORE_JOINTS) + ["nose", "neck", "pelvis", "shoulder_center", "weapon_tip"]
    return {
        "joints": {name: _point(*skeleton_point(skeleton, name)) for name in names},
        "phase": PHASES[0], "view": "front", "orientation": "front",
        "generator": {"kind": "deterministic-skeleton-only-motion-quality-layer", "parameters_frozen_before_render": True, "pixel_interpolation": False},
    }


def _scalar(samples: Mapping[str, Any], track_id: str) -> float:
    value = samples[track_id]
    if isinstance(value, list):
        raise ValueError(f"motion_track_must_be_scalar:{track_id}")
    return float(value)


def _target_for_frame(context: Mapping[str, Any], index: int, samples: Mapping[str, Any], base_target: Mapping[str, Any]) -> dict[str, Any]:
    target = copy.deepcopy(base_target)
    joints = target["joints"]
    skeleton = context["skeleton"]
    source_pelvis = skeleton_point(skeleton, "pelvis")
    root_x, root_y = _scalar(samples, "root_shift_x"), _scalar(samples, "root_shift_y")
    torso_rotation = _scalar(samples, "torso_rotation_deg")
    lean_x = _scalar(samples, "torso_lean_x")

    for side in ("left", "right"):
        hip = skeleton_point(skeleton, f"hip_{side}")
        knee = skeleton_point(skeleton, f"knee_{side}")
        ankle = skeleton_point(skeleton, f"ankle_{side}")
        joints[f"hip_{side}"] = _point(hip[0] + root_x, hip[1] + root_y)
        joints[f"knee_{side}"] = _point(knee[0] + root_x * 0.40, knee[1] + root_y * 0.40)
        joints[f"ankle_{side}"] = _point(*ankle)

    def torso_point(name: str, rotation: float = torso_rotation) -> tuple[float, float]:
        return tuple(value + offset for value, offset in zip(_rotate(skeleton_point(skeleton, name), source_pelvis, rotation), (root_x + lean_x, root_y)))

    shoulder_left = torso_point("shoulder_left")
    shoulder_right = torso_point("shoulder_right")
    neck = torso_point("neck", torso_rotation * 0.39)
    nose = torso_point("nose", torso_rotation * 0.39)
    for side in ("left", "right"):
        joints[f"hip_{side}"] = _point(*torso_point(f"hip_{side}"))
    head_counter = _scalar(samples, "head_counter_rotation_deg")
    nose = _rotate(nose, neck, head_counter)
    joints["shoulder_left"], joints["shoulder_right"] = _point(*shoulder_left), _point(*shoulder_right)
    joints["neck"], joints["nose"] = _point(*neck), _point(*nose)

    def arm(side: str, upper_track: str, forearm_track: str) -> tuple[tuple[float, float], tuple[float, float]]:
        shoulder = shoulder_left if side == "left" else shoulder_right
        source_shoulder = skeleton_point(skeleton, f"shoulder_{side}")
        source_elbow = skeleton_point(skeleton, f"elbow_{side}")
        source_wrist = skeleton_point(skeleton, f"wrist_{side}")
        upper_angle = _direction(source_shoulder, source_elbow) + torso_rotation + _scalar(samples, upper_track)
        elbow_offset = _polar(upper_angle, math.dist(source_shoulder, source_elbow))
        elbow = (shoulder[0] + elbow_offset[0], shoulder[1] + elbow_offset[1])
        forearm_angle = _direction(source_elbow, source_wrist) + torso_rotation + _scalar(samples, forearm_track)
        wrist_offset = _polar(forearm_angle, math.dist(source_elbow, source_wrist))
        wrist = (elbow[0] + wrist_offset[0], elbow[1] + wrist_offset[1])
        return elbow, wrist

    elbow_left, wrist_left = arm("left", "left_upper_arm_counter_deg", "left_forearm_counter_deg")
    elbow_right, wrist_right = arm("right", "right_upper_arm_rotation_deg", "right_forearm_rotation_deg")
    joints["elbow_left"], joints["wrist_left"] = _point(*elbow_left), _point(*wrist_left)
    joints["elbow_right"], joints["wrist_right"] = _point(*elbow_right), _point(*wrist_right)

    source_wrist, source_tip = skeleton_point(skeleton, "wrist_right"), skeleton_point(skeleton, "weapon_tip")
    grip_angle = _scalar(samples, "right_wrist/grip_rotation_deg")
    sword_angle = _direction(source_wrist, source_tip) + torso_rotation + grip_angle + _scalar(samples, "sword_rotation_deg")
    tip_offset = _polar(sword_angle, math.dist(source_wrist, source_tip))
    joints["weapon_tip"] = _point(wrist_right[0] + tip_offset[0], wrist_right[1] + tip_offset[1])
    joints["pelvis"] = _point((joints["hip_left"]["x"] + joints["hip_right"]["x"]) / 2.0, (joints["hip_left"]["y"] + joints["hip_right"]["y"]) / 2.0)
    joints["shoulder_center"] = _point((joints["shoulder_left"]["x"] + joints["shoulder_right"]["x"]) / 2.0, (joints["shoulder_left"]["y"] + joints["shoulder_right"]["y"]) / 2.0)
    target["phase"], target["frame_index"] = PHASES[index], index
    target["motion_tracks_sample"] = {key: value for key, value in samples.items()}
    target["target_joint_sha256"] = target_digest(target)
    return target


def _attack_plan() -> dict[str, Any]:
    phase_plans = {
        phase: {
            "phase": phase, "frame_index": index, "z_order": list(Z_ORDER),
            "front_parts": ["right_upper_arm", "right_forearm_hand", "sword", "left_thigh", "left_shin_foot"],
            "back_parts": ["right_thigh", "right_shin_foot", "left_upper_arm", "left_forearm_hand"],
            "depth_role": {"right_arm": "attack_lead", "left_arm": "counter_balance", "sword": "frontmost"},
            "switch_boundary": None,
        } for index, phase in enumerate(PHASES)
    }
    value: dict[str, Any] = {
        "schema_version": "animation-spec-1.0", "plan_id": "animation-attack-front-motion-quality-v2",
        "phase_plans": phase_plans, "critical_pairs": [["sword", "torso_pelvis"], ["sword", "head"]],
        "allowed_expected_occlusion_pairs": [["right_forearm_hand", "sword"], ["right_thigh", "sword"]],
        "switch_boundaries": [], "policy": "measured-critical-collisions-and-explicit-grip/trail-thigh-corridors",
    }
    value["plan_sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return value


def _series_metrics(spec: Mapping[str, Any], targets: list[Mapping[str, Any]], samples: list[Mapping[str, Any]]) -> dict[str, Any]:
    angle_values = [{f"{a}:{b}:{c}": _angle(_xy(target["joints"][a]), _xy(target["joints"][b]), _xy(target["joints"][c])) for a, b, c in ANGLE_CHAINS} for target in targets]
    unwrapped: list[dict[str, float]] = [dict(angle_values[0])] if angle_values else []
    for index in range(1, len(angle_values)):
        unwrapped.append({key: unwrapped[-1][key] + _signed_delta(angle_values[index - 1][key], angle_values[index][key]) for key in angle_values[index]})
    delta_series = [abs(unwrapped[index][key] - unwrapped[index - 1][key]) for index in range(1, len(unwrapped)) for key in unwrapped[index]]
    acceleration_series = [abs(unwrapped[index][key] - 2 * unwrapped[index - 1][key] + unwrapped[index - 2][key]) for index in range(2, len(unwrapped)) for key in unwrapped[index]]
    jerk_series = [abs(unwrapped[index][key] - 3 * unwrapped[index - 1][key] + 3 * unwrapped[index - 2][key] - unwrapped[index - 3][key]) for index in range(3, len(unwrapped)) for key in unwrapped[index]]
    pelvis = [_xy(target["joints"]["pelvis"]) for target in targets]
    nose = [map_presentation_point(_xy(target["joints"]["nose"]), spec["presentation_transform"]) for target in targets]
    torso_values = [_scalar(sample, "torso_rotation_deg") for sample in samples]
    head_values = [_scalar(sample, "head_counter_rotation_deg") for sample in samples]
    root_x = max(item[0] for item in pelvis) - min(item[0] for item in pelvis)
    root_y = max(item[1] for item in pelvis) - min(item[1] for item in pelvis)
    head_step = max((math.dist(nose[index - 1], nose[index]) for index in range(1, len(nose))), default=0.0)
    torso_step = max((abs(torso_values[index] - torso_values[index - 1]) for index in range(1, len(torso_values))), default=0.0)
    track_values = {track_id: [_scalar(sample, track_id) for sample in samples] for track_id in REQUIRED_TRACKS if track_id != "torso_lean_x"}
    track_ranges = {track_id: max(values) - min(values) for track_id, values in track_values.items()}
    distinct = len({target_digest(target) for target in targets})
    return {
        "max_joint_angle_delta_degrees": round(max(delta_series, default=0.0), 6),
        "max_angular_acceleration_degrees_per_frame2": round(max(acceleration_series, default=0.0), 6),
        "max_jerk_degrees_per_frame3": round(max(jerk_series, default=0.0), 6),
        "root_horizontal_excursion_px": round(root_x, 6), "root_vertical_excursion_px": round(root_y, 6),
        "head_adjacent_center_delta_px": round(head_step, 6), "torso_adjacent_rotation_delta_deg": round(torso_step, 6),
        "target_hash_count": distinct, "torso_rotation_range_deg": round(max(torso_values, default=0.0) - min(torso_values, default=0.0), 6),
        "head_counter_rotation_range_deg": round(max(head_values, default=0.0) - min(head_values, default=0.0), 6),
        "track_ranges": {key: round(value, 6) for key, value in track_ranges.items()},
        "angle_delta_samples": [round(value, 6) for value in delta_series],
        "angular_acceleration_samples": [round(value, 6) for value in acceleration_series],
        "jerk_samples": [round(value, 6) for value in jerk_series],
        "frame_pairs_measured": [[index - 1, index] for index in range(1, len(targets))],
        "closing_pair_measured": False,
    }


def _body_mechanics(spec: Mapping[str, Any], targets: list[Mapping[str, Any]], samples: list[Mapping[str, Any]], context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    pelvis = [_xy(target["joints"]["pelvis"]) for target in targets]
    right_relative = [(_xy(target["joints"]["wrist_right"])[0] - _xy(target["joints"]["shoulder_right"])[0], _xy(target["joints"]["wrist_right"])[1] - _xy(target["joints"]["shoulder_right"])[1]) for target in targets]
    left_wrist = [_xy(target["joints"]["wrist_left"]) for target in targets]
    path = lambda values: sum(math.dist(values[index - 1], values[index]) for index in range(1, len(values)))
    ranges = _series_metrics(spec, targets, samples)
    v1_path = None
    if context is not None:
        historical_spec_path = Path(context["root"]) / "profiles" / "animation" / "attack-front-v1.json"
        historical_spec = json.loads(historical_spec_path.read_text(encoding="utf-8"))
        historical_targets = v1.prepare(historical_spec, context)["targets"]
        historical_relative = [(_xy(target["joints"]["wrist_right"])[0] - _xy(target["joints"]["shoulder_right"])[0], _xy(target["joints"]["wrist_right"])[1] - _xy(target["joints"]["shoulder_right"])[1]) for target in historical_targets]
        v1_path = path(historical_relative)
    metrics = {
        "root_path_length_px": round(path(pelvis), 6),
        "torso_rotation_range_deg": ranges["torso_rotation_range_deg"],
        "right_shoulder_to_wrist_path_length_px": round(path(right_relative), 6),
        "attack_v1_equivalent_right_shoulder_to_wrist_path_length_px": round(v1_path, 6) if v1_path is not None else None,
        "left_wrist_counter_path_length_px": round(path(left_wrist), 6),
        "head_counter_motion_range_deg": ranges["head_counter_rotation_range_deg"],
        "track_ranges": ranges["track_ranges"],
        "proof_source": "src/ugas/animation_profiles/attack_front_v2.py:skeleton_targets_and_motion_tracks_before_render",
    }
    gates = {
        "root_path_length_gt_2": metrics["root_path_length_px"] > 2.0,
        "torso_rotation_range_ge_2": metrics["torso_rotation_range_deg"] >= 2.0,
        "right_shoulder_to_wrist_path_gt_zero": metrics["right_shoulder_to_wrist_path_length_px"] > 0.0,
        "right_shoulder_to_wrist_path_gt_attack_v1": v1_path is None or metrics["right_shoulder_to_wrist_path_length_px"] > v1_path,
        "left_wrist_counter_path_gt_1": metrics["left_wrist_counter_path_length_px"] > 1.0,
        "head_counter_motion_le_4": metrics["head_counter_motion_range_deg"] <= 4.0,
        "root_motion_nonzero": metrics["track_ranges"].get("root_shift_x", 0.0) > 0.0 or metrics["track_ranges"].get("root_shift_y", 0.0) > 0.0,
        "torso_motion_nonzero": metrics["torso_rotation_range_deg"] > 0.0,
        "left_arm_counter_motion_nonzero": metrics["track_ranges"].get("left_upper_arm_counter_deg", 0.0) > 0.0 or metrics["track_ranges"].get("left_forearm_counter_deg", 0.0) > 0.0,
    }
    return {"metrics": metrics, "hard_gates": gates, "status": "ATTACK_V2_BODY_MECHANICS_QA_PASSED" if all(gates.values()) else "ATTACK_V2_BODY_MECHANICS_GAP"}


def _pre_render_proxies(spec: Mapping[str, Any], targets: list[Mapping[str, Any]], samples: list[Mapping[str, Any]], context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tips = [_xy(target["joints"]["weapon_tip"]) for target in targets]
    anticipation = sum(math.dist(tips[index - 1], tips[index]) for index in range(1, 4))
    active_arc = sum(math.dist(tips[index - 1], tips[index]) for index in range(4, 8))
    follow = sum(math.dist(tips[index - 1], tips[index]) for index in range(7, 9))
    body = _body_mechanics(spec, targets, samples, context)
    metrics = {"anticipation_displacement_px": round(anticipation, 6), "active_window_sword_arc_px": round(active_arc, 6), "follow_through_displacement_px": round(follow, 6), **body["metrics"]}
    gates = {
        "anticipation_displacement_gt_0": anticipation > 0.0,
        "active_window_sword_arc_gt_80pct_anticipation": active_arc > anticipation * 0.8,
        "follow_through_displacement_gt_0": follow > 0.0,
        "root_motion_nonzero": body["hard_gates"]["root_motion_nonzero"],
        "torso_motion_nonzero": body["hard_gates"]["torso_motion_nonzero"],
        "left_arm_counter_motion_nonzero": body["hard_gates"]["left_arm_counter_motion_nonzero"],
        "right_shoulder_to_wrist_path_gt_attack_v1": body["hard_gates"]["right_shoulder_to_wrist_path_gt_attack_v1"],
    }
    return {"metrics": metrics, "hard_gates": gates, "body_mechanics": body, "status": "MOTION_PROXIES_PASSED" if all(gates.values()) else "ATTACK_V2_BODY_MECHANICS_GAP"}


def prepare(spec: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    tracks = validate_motion_tracks(spec)
    present = {track["track_id"] for track in tracks}
    missing = [track_id for track_id in REQUIRED_TRACKS if track_id not in present]
    if missing:
        raise ValueError(f"attack_v2_required_motion_tracks_missing:{','.join(missing)}")
    samples = [sample_all_tracks(spec, index) for index in range(int(spec["frame_count"]))]
    base_target = _base_target(context)
    targets = [_target_for_frame(context, index, samples[index], base_target) for index in range(int(spec["frame_count"]))]
    series = _series_metrics(spec, targets, samples)
    threshold = spec["qa_profile"]["thresholds"]
    temporal_gates = {
        "joint_angle_delta_le_28": series["max_joint_angle_delta_degrees"] <= float(threshold["max_joint_angle_delta_degrees"]),
        "angular_acceleration_le_24": series["max_angular_acceleration_degrees_per_frame2"] <= float(threshold["max_angular_acceleration_degrees_per_frame2"]),
        "jerk_le_36": series["max_jerk_degrees_per_frame3"] <= float(threshold["max_jerk_degrees_per_frame3"]),
        "root_horizontal_excursion_in_2_6": 2.0 <= series["root_horizontal_excursion_px"] <= 6.0,
        "root_vertical_excursion_in_1_5": 1.0 <= series["root_vertical_excursion_px"] <= 5.0,
        "head_adjacent_center_delta_le_5": series["head_adjacent_center_delta_px"] <= float(threshold["head_adjacent_center_delta_px"]),
        "torso_adjacent_rotation_delta_le_4": series["torso_adjacent_rotation_delta_deg"] <= float(threshold["torso_adjacent_rotation_delta_deg"]),
        "target_hashes_exactly_12_distinct": series["target_hash_count"] == 12,
    }
    proxies = _pre_render_proxies(spec, targets, samples, context)
    if not all(temporal_gates.values()):
        raise ValueError("MOTION_CURVE_TEMPORAL_GAP")
    if not all(proxies["hard_gates"].values()):
        raise ValueError("ATTACK_V2_BODY_MECHANICS_GAP")
    return {"tracks": tracks, "samples": samples, "targets": targets, "plan": _attack_plan(), "presentation": spec["presentation_transform"], "phases": list(PHASES), "series": series, "temporal_gates": temporal_gates, "proxies": proxies}


def render_frame(spec: Mapping[str, Any], context: Mapping[str, Any], prepared: Mapping[str, Any], index: int):
    target = prepared["targets"][index]
    image, details = render_source_only(context, target, list(Z_ORDER), prepared["presentation"])
    sword = next(item for item in details["transforms"] if item["part"] == "sword")
    return image, {"phase": PHASES[index], "target_hash": target["target_joint_sha256"], "presentation_target_hash": details["target_presented"]["presentation_target_joint_sha256"], "z_order": list(Z_ORDER), "target": target, "sword_target_pivot": sword["target_pivot"], "motion_tracks_sample": target["motion_tracks_sample"]}


def _regions(target: Mapping[str, Any], phase: str, plan: Mapping[str, Any], size: tuple[int, int]) -> dict[str, Any]:
    pairs = [(parent, child) for parent, child, _ in TOPOLOGY_ADJACENCY]
    for pair in (("head", "left_upper_arm"), ("head", "right_upper_arm")):
        if set(pair) not in [set(item) for item in pairs]:
            pairs.append(pair)
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
        gates = {"source_area_retained": layer_active / max(1, predicted) >= 0.97, "no_predicted_clipping": float(item.get("predicted_outside_canvas_area", 1)) == 0, "no_actual_border_clipping": int(item.get("actual_border_clipped_pixels", 1)) == 0, "constant_depth_plan_measured": constant_depth}
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
    return v1._foot_frame(context, target, details, presentation, limits)


def _balance_proxy(targets: list[Mapping[str, Any]], margin: float) -> dict[str, Any]:
    samples = []
    for index, target in enumerate(targets):
        pelvis = _xy(target["joints"]["pelvis"])
        feet = [_xy(target["joints"][f"ankle_{side}"]) for side in ("left", "right")]
        low, high = min(item[0] for item in feet) - margin, max(item[0] for item in feet) + margin
        samples.append({"frame": index, "pelvis_x": round(pelvis[0], 6), "support_corridor_x": [round(low, 6), round(high, 6)], "within_corridor": low <= pelvis[0] <= high})
    gates = {"pelvis_between_near_support_feet": all(item["within_corridor"] for item in samples)}
    return {"margin_px": margin, "samples": samples, "hard_gates": gates, "status": "BALANCE_PROXY_PASSED" if all(gates.values()) else "ATTACK_V2_FOOT_GROUND_GAP", "proof_source": "src/ugas/animation_profiles/attack_front_v2.py:pelvis_support_foot_corridor"}


def _foot_ground_qa(frame_records: list[Mapping[str, Any]], targets: list[Mapping[str, Any]], spec: Mapping[str, Any]) -> dict[str, Any]:
    result = v1.foot_ground_qa(frame_records, float(spec["qa_profile"]["thresholds"]["projected_sole_frame_to_frame_drift_px"]), float(spec["qa_profile"]["thresholds"]["ankle_horizontal_drift_from_A0_px"]))
    balance = _balance_proxy(targets, float(spec["qa_profile"]["thresholds"]["balance_corridor_margin_px"]))
    result["balance_proxy"] = balance
    result["hard_gates"].update({f"balance_{key}": value for key, value in balance["hard_gates"].items()})
    result["status"] = "ATTACK_V2_FOOT_GROUND_QA_PASSED" if all(result["hard_gates"].values()) else "ATTACK_V2_FOOT_GROUND_GAP"
    return result


def _weapon_arc_qa(spec: Mapping[str, Any], frame_records: list[Mapping[str, Any]]) -> dict[str, Any]:
    active = set(int(item) for item in spec["qa_profile"]["thresholds"]["active_window_frames"])
    hit_frame = int(spec["qa_profile"]["thresholds"]["hit_event_frame"])
    tips = [item["weapon"]["tip_presented"] for item in frame_records]
    angles = [float(item["weapon"]["signed_sword_angle_degrees"]) for item in frame_records]
    velocities = [{"from_frame": index - 1, "to_frame": index, "tip_motion_px": round(math.dist(tips[index - 1], tips[index]), 6), "angular_velocity_degrees_per_frame": round(_signed_delta(angles[index - 1], angles[index]), 6), "inside_or_near_active_window": index - 1 in active or index in active} for index in range(1, len(tips))]
    accelerations = [{"from_frame": item["from_frame"] - 1, "to_frame": item["to_frame"], "angular_acceleration_degrees_per_frame2": round(velocities[index]["angular_velocity_degrees_per_frame"] - velocities[index - 1]["angular_velocity_degrees_per_frame"], 6)} for index, item in enumerate(velocities[1:], start=1)]
    jerks = [{"from_frame": item["from_frame"] - 1, "to_frame": item["to_frame"], "angular_jerk_degrees_per_frame3": round(accelerations[index]["angular_acceleration_degrees_per_frame2"] - accelerations[index - 1]["angular_acceleration_degrees_per_frame2"], 6)} for index, item in enumerate(accelerations[1:], start=1)]
    peak = max(velocities, key=lambda item: abs(item["angular_velocity_degrees_per_frame"]), default={"from_frame": -1, "to_frame": -1, "tip_motion_px": 0.0, "angular_velocity_degrees_per_frame": 0.0, "inside_or_near_active_window": False})
    path = lambda first, last: round(sum(item["tip_motion_px"] for item in velocities if first <= item["from_frame"] and item["to_frame"] <= last), 6)
    critical_head = sum(int(item["weapon"].get("sword_head_critical_collision_pixels", 0)) for item in frame_records)
    forbidden_torso = sum(int(item["weapon"].get("sword_torso_forbidden_pixels", 0)) for item in frame_records)
    paths = {"total": path(0, 11), "pre_hit": path(0, hit_frame), "active": path(min(active), max(active)), "recovery": path(hit_frame + 1, 11), "post_hit_follow_through": path(hit_frame, min(11, hit_frame + 2))}
    gates = {
        "sword_pivot_attached_all_frames": all(bool(item["weapon"].get("pivot_attached")) for item in frame_records),
        "active_window_frames_exact": [int(item["index"]) for item in frame_records if item["index"] in active] == sorted(active),
        "hit_event_frame_exact": hit_frame == HIT_EVENT_FRAME,
        "weapon_tip_path_nonzero": paths["total"] > 0.0,
        "peak_speed_inside_or_near_active_window": bool(peak.get("inside_or_near_active_window")),
        "hit_event_inside_active_window": hit_frame in active,
        "pre_hit_acceleration_pattern_exists": any(abs(item["angular_acceleration_degrees_per_frame2"]) > 0.0 for item in accelerations if item["to_frame"] <= hit_frame),
        "post_hit_follow_through_path_nonzero": paths["post_hit_follow_through"] > 0.0,
        "sword_head_collision_zero": critical_head == 0,
        "sword_torso_forbidden_penetration_zero": forbidden_torso == 0,
    }
    return {"active_window_frames": sorted(active), "hit_event_frame": hit_frame, "signed_sword_angle_degrees_by_frame": [{"frame": index, "degrees": round(angle, 6)} for index, angle in enumerate(angles)], "tip_xy_presented": [{"frame": item["index"], "x": item["weapon"]["tip_presented"][0], "y": item["weapon"]["tip_presented"][1]} for item in frame_records], "path_lengths_px": paths, "angular_velocity": velocities, "angular_acceleration": accelerations, "angular_jerk": jerks, "peak_speed": peak, "sword_head_collision_pixels": critical_head, "sword_torso_forbidden_penetration_pixels": forbidden_torso, "hard_gates": gates, "status": "ATTACK_V2_WEAPON_ARC_QA_PASSED" if all(gates.values()) else "ATTACK_V2_WEAPON_ARC_GAP", "proof_source": "src/ugas/animation_profiles/attack_front_v2.py:measured_tip_and_angle_trajectory"}


def _temporal_qa(spec: Mapping[str, Any], prepared: Mapping[str, Any], frame_records: list[Mapping[str, Any]]) -> dict[str, Any]:
    series = prepared["series"]
    threshold = spec["qa_profile"]["thresholds"]
    weapon = _weapon_arc_qa(spec, frame_records)
    foot_ground = _foot_ground_qa(frame_records, prepared["targets"], spec)
    gates = {**prepared["temporal_gates"], "weapon_arc_qa": weapon["status"] == "ATTACK_V2_WEAPON_ARC_QA_PASSED", "foot_ground_qa": foot_ground["status"] == "ATTACK_V2_FOOT_GROUND_QA_PASSED"}
    return {"metrics": {**series, "proof_source": "src/ugas/animation_profiles/attack_front_v2.py:skeleton_series_before_render"}, "hard_gates": gates, "weapon": weapon, "foot_ground": foot_ground, "status": "ATTACK_V2_TEMPORAL_QA_PASSED" if all(gates.values()) else "ATTACK_V2_TEMPORAL_GAP"}


def _pose(frame_path: Path, target: Mapping[str, Any]) -> dict[str, Any]:
    return v1._pose(frame_path, target)


def qa(spec: Mapping[str, Any], context: Mapping[str, Any], manifest: Mapping[str, Any], root: Path) -> dict[str, Any]:
    prepared = prepare(spec, context)
    targets, plan = prepared["targets"], prepared["plan"]
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
        transforms_ok = all(bool(value.get("scale_gate")) and 0.92 <= float(value.get("uniform_scale", 0.0)) <= 1.08 for value in details["transforms"])
        nonuniform_count = sum(bool(value.get("nonuniform_scale")) for value in details["transforms"])
        gates = {
            "source_hashes": all(value["source_part_rgba_sha256"] == context["part_hashes"][value["part"]] for value in details["transforms"]),
            "target_binding": target_digest(target) == item["target_hash"], "global_transform_and_bone_scale": transforms_ok and bool(spec["presentation_transform"]["frozen_before_render"]),
            "nonuniform_scale_operation_count_zero": nonuniform_count == 0, "alpha_safe_margin_ge_24": bool(alpha["gate"]), "structural_holes_zero": aux["coverage"]["structural_hole_pixels"] == 0,
            "layer_integrity": integrity["status"] == "LAYER_INTEGRITY_PASSED", "occlusion": pair["status"] == "OCCLUSION_QA_PASSED", "seam": seam["status"] == "SEAM_TOPOLOGY_PASSED", "retention": aux["retention"]["status"] == "RETENTION_OCCLUSION_PASSED",
            "pose_estimator": metrics.get("qualifies") is True and int(metrics.get("measurable_body_joints", 0)) >= 10 and float(metrics.get("pck_at_010", 0.0)) >= 0.80 and float(metrics.get("nme", 1.0)) <= 0.10 and float(metrics.get("limb_angle_mae_degrees", 180.0)) <= 18.0 and float(metrics.get("lower_body_pck", 0.0)) >= 0.75,
            "sword_pivot_attached": sword_transform["target_pivot"] == [target["joints"]["wrist_right"]["x"], target["joints"]["wrist_right"]["y"]], "source_only_pixels": bool(spec["provenance"]["source_only_pixels"]), "no_duplicate_body": duplicate["gate"], "both_feet_planted": feet["status"] == "ATTACK_FOOT_FRAME_PASSED", "frozen_z_order": [value["part"] for value in details["transforms"]] == list(Z_ORDER),
        }
        record = {"index": index, "phase": PHASES[index], "target_hash": target["target_joint_sha256"], "output_rgba_sha256": item["rgba_sha256"], "hard_gates": gates, "passed": all(gates.values()), "alpha": alpha, "feet": feet, "pose": pose, "duplicate_body": duplicate, "integrity": integrity, "occlusion": pair, "seam": seam, "coverage": {key: value for key, value in aux["coverage"].items() if key not in {"hole_mask", "expected_mask"}}, "retention": aux["retention"], "z_order": list(Z_ORDER), "weapon": {"pivot_attached": gates["sword_pivot_attached"], "target_pivot": sword_transform["target_pivot"], "tip_presented": [round(tip[0], 6), round(tip[1], 6)], "signed_sword_angle_degrees": round(sword_angle, 6), "sword_head_critical_collision_pixels": int(sword_head.get("pixels", 0)) if sword_head.get("critical_pair") else 0, "sword_torso_forbidden_pixels": int(sword_torso.get("outside_authorized_region_pixels", 0))}, "status": "ATTACK_V2_FRAME_PASSED" if all(gates.values()) else "ATTACK_V2_STRUCTURAL_OR_POSE_GAP"}
        records.append(record)
        structural[PHASES[index]] = {"pair": pair, "seam": seam, "coverage": record["coverage"], "retention": record["retention"]}
    temporal = _temporal_qa(spec, prepared, records)
    body = prepared["proxies"]["body_mechanics"]
    markers = event_markers_for_spec(spec)
    expected = [("windup_peak", 3), ("active_start", 4), ("hit_event", 6), ("active_end", 7), ("recovery_complete", 11)]
    marker_gate = [(item["event_id"], item["frame"]) for item in markers] == expected
    top_gates = {
        "frame_count_exactly_12": len(records) == 12, "all_frames": bool(records) and all(record["passed"] for record in records), "temporal_quality": temporal["status"] == "ATTACK_V2_TEMPORAL_QA_PASSED", "body_mechanics": body["status"] == "ATTACK_V2_BODY_MECHANICS_QA_PASSED", "weapon_arc": temporal["weapon"]["status"] == "ATTACK_V2_WEAPON_ARC_QA_PASSED", "foot_ground": temporal["foot_ground"]["status"] == "ATTACK_V2_FOOT_GROUND_QA_PASSED", "event_timeline_frozen": marker_gate and len(markers) == 5, "key_pose_bindings": all(any(int(binding["frame"]) == index and binding["target_hash"] == targets[index]["target_joint_sha256"] for binding in spec["key_pose_bindings"]) for index in [0, 3, 4, 6, 7, 11]), "front_facing": all(target.get("orientation") == "front" for target in targets), "provenance": bool(spec["provenance"]["source_only_pixels"]) and spec["provenance"]["sam2_used"] is False and int(spec["provenance"]["comfyui_generation_jobs"]) == 0 and spec["provenance"]["diffusion_used"] is False,
    }
    failures = [name for name, passed in top_gates.items() if not passed]
    failures.extend(f"frame_{record['index']}_{name}" for record in records for name, passed in record["hard_gates"].items() if not passed)
    failures.extend(f"temporal_{name}" for name, passed in temporal["hard_gates"].items() if not passed)
    qualified = all(top_gates.values()) and not failures
    return {"animation_id": spec["animation_id"], "decision": "QUALIFIED" if qualified else "FAILED", "status": "CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED" if qualified else "ATTACK_V2_STRUCTURAL_OR_POSE_GAP", "frames": records, "temporal": temporal, "weapon": temporal["weapon"], "foot_ground": temporal["foot_ground"], "body_mechanics": body, "package_metadata": {"active_window_frames": list(ACTIVE_WINDOW), "hit_event_frame": HIT_EVENT_FRAME, "event_timeline_authority": "spec.event_markers", "motion_quality_layer": "generic.motion_tracks", "weapon": "sword"}, "provenance": {"source_sha256": context["source_sha256"], "part_hashes": context["part_hashes"], "mask_hashes": context["mask_hashes"], "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "source_only_pixels": True}, "hard_gates": top_gates, "failures": failures, "structural": structural}
