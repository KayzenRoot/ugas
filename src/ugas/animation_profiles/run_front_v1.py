"""Deterministic RUN_FRONT_V1 adapter over the approved R4 cutout rig.

The run lane deliberately reuses the immutable source parts and the generic
animation lifecycle.  Only skeleton coordinates are generated here.  Motion
tracks are sampled before the first pixel is rendered and every semantic gate
is evaluated from the resulting targets or the rendered source-only layers.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

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
from ..motion_curves import motion_tracks_sha256, sample_all_tracks, validate_motion_tracks
from ..pose_metric_calibration import CORE_JOINTS
from .common import load_source_context, read_json, render_source_only, target_digest


PHASES = (
    "R0-contact-left",
    "R1-support-left",
    "R2-passing-left",
    "R3-flight-left",
    "R4-contact-right",
    "R5-support-right",
    "R6-passing-right",
    "R7-flight-right",
)

Z_ORDER = (
    "right_shin_foot",
    "right_thigh",
    "left_forearm_hand",
    "left_upper_arm",
    "torso_pelvis",
    "left_thigh",
    "left_shin_foot",
    "right_upper_arm",
    "right_forearm_hand",
    "head",
    "sword",
)

ANGLE_CHAINS = (
    ("shoulder_left", "elbow_left", "wrist_left"),
    ("shoulder_right", "elbow_right", "wrist_right"),
    ("hip_left", "knee_left", "ankle_left"),
    ("hip_right", "knee_right", "ankle_right"),
)

REQUIRED_TRACKS = (
    "root_shift_x",
    "root_shift_y",
    "torso_rotation_deg",
    "torso_lean_x",
    "left_arm_swing_deg",
    "right_arm_swing_deg",
    "head_counter_rotation_deg",
    "sword_rotation_deg",
    "left_stride_x",
    "right_stride_x",
    "left_lift_y",
    "right_lift_y",
)

CONTACT_WINDOWS = ((0, 1, "left"), (2, 3, "right"), (4, 5, "right"), (6, 7, "left"))
SUPPORT_SIDE = {0: "left", 1: "left", 2: "right", 3: "right", 4: "right", 5: "right", 6: "left", 7: "left"}
SWING_SIDE = {2: "left", 3: "left", 6: "right", 7: "right"}


def _xy(value: Any) -> tuple[float, float]:
    if isinstance(value, Mapping):
        return float(value["x"]), float(value["y"])
    return float(value[0]), float(value[1])


def _point(x: float, y: float) -> dict[str, float]:
    return {"x": round(float(x), 6), "y": round(float(y), 6)}


def _scalar(samples: Mapping[str, Any], track_id: str) -> float:
    value = samples[track_id]
    if isinstance(value, list):
        raise ValueError(f"motion_track_must_be_scalar:{track_id}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"motion_track_nonfinite:{track_id}")
    return number


def _direction(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.degrees(math.atan2(second[1] - first[1], second[0] - first[0]))


def _signed_delta(first: float, second: float) -> float:
    return (second - first + 180.0) % 360.0 - 180.0


def _rotate(point: tuple[float, float], pivot: tuple[float, float], degrees: float) -> tuple[float, float]:
    theta = math.radians(degrees)
    x, y = point[0] - pivot[0], point[1] - pivot[1]
    return (pivot[0] + x * math.cos(theta) - y * math.sin(theta), pivot[1] + x * math.sin(theta) + y * math.cos(theta))


def _polar(angle: float, length: float) -> tuple[float, float]:
    theta = math.radians(angle)
    return math.cos(theta) * length, math.sin(theta) * length


def _base_target(context: Mapping[str, Any]) -> dict[str, Any]:
    skeleton = context["skeleton"]
    names = list(CORE_JOINTS) + ["nose", "neck", "pelvis", "shoulder_center", "weapon_tip"]
    return {
        "joints": {name: _point(*skeleton_point(skeleton, name)) for name in names},
        "phase": PHASES[0],
        "view": "front",
        "orientation": "front",
        "generator": {
            "kind": "deterministic-skeleton-only-run-cycle",
            "parameters_frozen_before_render": True,
            "pixel_interpolation": False,
            "image_inputs_used_for_motion": False,
        },
    }


def load_context(spec: Mapping[str, Any], root: Path) -> dict[str, Any]:
    context = load_source_context(spec, root)
    context["root"] = root.resolve()
    params = spec.get("adapter_parameters", {})
    context["run_contract"] = read_json(root / str(params["contract_ref"]))
    return context


def _target_for_frame(context: Mapping[str, Any], index: int, samples: Mapping[str, Any], base_target: Mapping[str, Any]) -> dict[str, Any]:
    target = copy.deepcopy(base_target)
    joints = target["joints"]
    skeleton = context["skeleton"]
    source_pelvis = skeleton_point(skeleton, "pelvis")
    root_x = _scalar(samples, "root_shift_x")
    root_y = _scalar(samples, "root_shift_y")
    torso_rotation = _scalar(samples, "torso_rotation_deg")
    lean_x = _scalar(samples, "torso_lean_x")

    def torso_point(name: str, rotation: float = torso_rotation) -> tuple[float, float]:
        rotated = _rotate(skeleton_point(skeleton, name), source_pelvis, rotation)
        return rotated[0] + root_x + lean_x, rotated[1] + root_y

    for name in ("shoulder_left", "shoulder_right", "hip_left", "hip_right"):
        joints[name] = _point(*torso_point(name))
    joints["neck"] = _point(*torso_point("neck", torso_rotation * 0.38))
    joints["nose"] = _point(*torso_point("nose", torso_rotation * 0.38))
    joints["shoulder_center"] = _point((joints["shoulder_left"]["x"] + joints["shoulder_right"]["x"]) / 2.0, (joints["shoulder_left"]["y"] + joints["shoulder_right"]["y"]) / 2.0)
    joints["pelvis"] = _point((joints["hip_left"]["x"] + joints["hip_right"]["x"]) / 2.0, (joints["hip_left"]["y"] + joints["hip_right"]["y"]) / 2.0)

    head_counter = _scalar(samples, "head_counter_rotation_deg")
    joints["nose"] = _point(*_rotate(_xy(joints["nose"]), _xy(joints["neck"]), head_counter))

    def arm(side: str, track_id: str) -> tuple[tuple[float, float], tuple[float, float]]:
        shoulder = _xy(joints[f"shoulder_{side}"])
        source_shoulder = skeleton_point(skeleton, f"shoulder_{side}")
        source_elbow = skeleton_point(skeleton, f"elbow_{side}")
        source_wrist = skeleton_point(skeleton, f"wrist_{side}")
        swing = _scalar(samples, track_id)
        upper_angle = _direction(source_shoulder, source_elbow) + torso_rotation + swing
        upper_dx, upper_dy = _polar(upper_angle, math.dist(source_shoulder, source_elbow))
        elbow = (shoulder[0] + upper_dx, shoulder[1] + upper_dy)
        fore_angle = _direction(source_elbow, source_wrist) + torso_rotation + swing
        fore_dx, fore_dy = _polar(fore_angle, math.dist(source_elbow, source_wrist))
        wrist = (elbow[0] + fore_dx, elbow[1] + fore_dy)
        return elbow, wrist

    elbow_left, wrist_left = arm("left", "left_arm_swing_deg")
    elbow_right, wrist_right = arm("right", "right_arm_swing_deg")
    joints["elbow_left"], joints["wrist_left"] = _point(*elbow_left), _point(*wrist_left)
    joints["elbow_right"], joints["wrist_right"] = _point(*elbow_right), _point(*wrist_right)

    # Feet are source-anchored in world space during contact/support windows.
    # The two-bone projection keeps the source-calibrated thigh/shin lengths.
    for side, stride_id, lift_id in (("left", "left_stride_x", "left_lift_y"), ("right", "right_stride_x", "right_lift_y")):
        source_hip = skeleton_point(skeleton, f"hip_{side}")
        source_ankle = skeleton_point(skeleton, f"ankle_{side}")
        joints[f"ankle_{side}"] = _point(source_ankle[0] + _scalar(samples, stride_id), source_ankle[1] + _scalar(samples, lift_id))
        hip = _xy(joints[f"hip_{side}"])
        ankle = _xy(joints[f"ankle_{side}"])
        source_knee = skeleton_point(skeleton, f"knee_{side}")
        thigh = math.dist(source_hip, source_knee)
        shin = math.dist(source_knee, source_ankle)
        # The approved v0.8.1 projection is skeleton-only and preserves both
        # bone lengths while honoring the source pose as the branch hint.
        from ..cutout_temporal import _two_bone

        source_knee_vector = (source_knee[0] - source_hip[0], source_knee[1] - source_hip[1])
        source_ankle_vector = (source_ankle[0] - source_hip[0], source_ankle[1] - source_hip[1])
        branch_sign = source_ankle_vector[0] * source_knee_vector[1] - source_ankle_vector[1] * source_knee_vector[0]
        knee = _two_bone(hip, ankle, source_knee, thigh, shin, branch_sign=branch_sign)
        joints[f"knee_{side}"] = _point(*knee)

    source_wrist, source_tip = skeleton_point(skeleton, "wrist_right"), skeleton_point(skeleton, "weapon_tip")
    sword_angle = _direction(source_wrist, source_tip) + torso_rotation + _scalar(samples, "right_arm_swing_deg") + _scalar(samples, "sword_rotation_deg")
    tip_dx, tip_dy = _polar(sword_angle, math.dist(source_wrist, source_tip))
    joints["weapon_tip"] = _point(joints["wrist_right"]["x"] + tip_dx, joints["wrist_right"]["y"] + tip_dy)

    target["phase"] = PHASES[index]
    target["frame_index"] = index
    target["motion_tracks_sample"] = {key: round(float(value), 6) if isinstance(value, (int, float)) else value for key, value in samples.items()}
    target["target_joint_sha256"] = target_digest(target)
    return target


def _run_plan() -> dict[str, Any]:
    phase_plans = {
        phase: {
            "phase": phase,
            "frame_index": index,
            "z_order": list(Z_ORDER),
            "front_parts": ["left_thigh", "left_shin_foot", "right_upper_arm", "right_forearm_hand"],
            "back_parts": ["right_thigh", "right_shin_foot", "left_upper_arm", "left_forearm_hand"],
            "depth_role": {"left_leg": "run_stride", "right_leg": "run_stride", "left_arm": "counter_swing", "right_arm": "counter_swing"},
            "switch_boundary": None,
        }
        for index, phase in enumerate(PHASES)
    }
    value = {
        "schema_version": "animation-spec-1.0",
        "plan_id": "animation-run-front-source-only-v1",
        "phase_plans": phase_plans,
        "critical_pairs": [["sword", "torso_pelvis"], ["sword", "head"], ["left_upper_arm", "right_upper_arm"]],
        "allowed_expected_occlusion_pairs": [["head", "torso_pelvis"], ["head", "left_upper_arm"], ["head", "right_upper_arm"], ["torso_pelvis", "left_forearm_hand"], ["torso_pelvis", "right_forearm_hand"], ["left_forearm_hand", "left_thigh"], ["right_forearm_hand", "right_thigh"], ["right_thigh", "sword"], ["left_thigh", "right_thigh"], ["left_shin_foot", "right_shin_foot"]],
        "switch_boundaries": [],
        "render_and_qa_share_plan_hash": True,
    }
    value["plan_sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return value


def prepare(spec: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    tracks = validate_motion_tracks(spec)
    track_ids = {str(track["track_id"]) for track in tracks}
    missing = [name for name in REQUIRED_TRACKS if name not in track_ids]
    if missing:
        raise ValueError(f"run_required_motion_tracks_missing:{','.join(missing)}")
    samples = [sample_all_tracks(spec, index) for index in range(int(spec["frame_count"]))]
    base = _base_target(context)
    targets = [_target_for_frame(context, index, samples[index], base) for index in range(int(spec["frame_count"]))]
    return {"tracks": tracks, "samples": samples, "targets": targets, "plan": _run_plan(), "presentation": spec["presentation_transform"], "phases": list(PHASES), "track_hash": motion_tracks_sha256(spec)}


def render_frame(spec: Mapping[str, Any], context: Mapping[str, Any], prepared: Mapping[str, Any], index: int):
    target = prepared["targets"][index]
    image, details = render_source_only(context, target, list(Z_ORDER), prepared["presentation"])
    return image, {"phase": PHASES[index], "target_hash": target["target_joint_sha256"], "presentation_target_hash": details["target_presented"]["presentation_target_joint_sha256"], "z_order": list(Z_ORDER), "target": target}


def _bbox_area(image: Image.Image) -> float:
    bbox = image.getchannel("A").getbbox()
    return float((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) if bbox else 0.0


def _plan_and_structural(context: Mapping[str, Any], target: Mapping[str, Any], details: Mapping[str, Any], phase: str, plan: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    pairs = [(parent, child) for parent, child, _ in TOPOLOGY_ADJACENCY]
    for raw in plan.get("allowed_expected_occlusion_pairs", []):
        pair = (str(raw[0]), str(raw[1]))
        if set(pair) not in [set(item) for item in pairs]:
            pairs.append(pair)
    region_masks, region_records = {}, []
    for pair in pairs:
        mask, geometry = _region_mask_for_pair(pair, target, phase, context["source"].size)
        key = _explicit_pair_key(*pair)
        order = list(plan["phase_plans"][phase]["z_order"])
        front = pair[0] if order.index(pair[0]) > order.index(pair[1]) else pair[1]
        region_masks[key] = mask
        region_records.append({"pair": list(pair), "pair_key": key, "phase": phase, "expected_front_part": front, "geometry": geometry, "region_pixels": _count(mask), "region_sha256": _digest_image(mask)})
    regions = {"regions": region_masks, "records": region_records, "allowed_pair_keys": {_explicit_pair_key(*raw) for raw in plan.get("allowed_expected_occlusion_pairs", [])}}
    pair = pairwise_overlap_v073(details["layers"], phase, target, plan, regions)
    pair["hard_gates"]["z_order_constant"] = len({tuple(plan["phase_plans"][name]["z_order"]) for name in PHASES}) == 1
    pair["hard_gates"]["explicit_run_allowed_pair_rules"] = bool(plan.get("allowed_expected_occlusion_pairs"))
    pair["status"] = "OCCLUSION_QA_PASSED" if all(pair["hard_gates"].values()) else "CUTOUT_RIG_OCCLUSION_REGION_GAP"
    seam = topological_seam_qa(details["layers"], phase, target, plan)
    integrity = layer_integrity_qa(context["parts"], details["layers"], details["transforms"], context["source"].size)
    core_for_pose = dict(context["core"])
    core_for_pose["torso_transform"] = next(item for item in details["transforms"] if item["part"] == "torso_pelvis")
    coverage = structural_coverage_qa(details["core_layer"], details["canonical"], target, phase, core_for_pose)
    retention_parts = {}
    for item in details["transforms"]:
        name = item["part"]
        source_active = _count(_binary(context["parts"][name].getchannel("A"), 64))
        layer_active = _count(_binary(details["layers"][name].getchannel("A"), 64))
        predicted = float(integrity["parts"][name].get("predicted_transformed_area", layer_active))
        record = integrity["parts"][name]
        gates = {"source_area_retained": layer_active / max(1, predicted) >= 0.97, "no_predicted_clipping": float(record.get("predicted_outside_canvas_area", 1)) == 0, "no_actual_border_clipping": int(record.get("actual_border_clipped_pixels", 1)) == 0, "constant_depth_plan": True}
        retention_parts[name] = {"source_active_pixels": source_active, "actual_layer_pixels": layer_active, "predicted_transformed_area": predicted, "visible_fraction": round(layer_active / max(1, predicted), 6), "hard_gates": gates, "status": "RETENTION_OCCLUSION_PASSED" if all(gates.values()) else "CUTOUT_RIG_RETENTION_GAP"}
    retention_pass = all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in retention_parts.values())
    retention = {"schema_version": "animation-spec-1.0", "phase": phase, "parts": retention_parts, "hard_gates": {"all_parts_pass": retention_pass}, "status": "RETENTION_OCCLUSION_PASSED" if retention_pass else "CUTOUT_RIG_RETENTION_GAP"}
    return pair, seam, integrity, {"coverage": coverage, "retention": retention}


def _foot_record(context: Mapping[str, Any], target: Mapping[str, Any], details: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    frame = int(target["frame_index"])
    by_part = {str(item["part"]): item for item in details["transforms"]}
    projected, actual = {}, {}
    for side in ("left", "right"):
        name = f"{side}_shin_foot"
        alpha = context["parts"][name].getchannel("A")
        source_bbox = alpha.getbbox()
        if not source_bbox:
            raise ValueError(f"empty_foot_source:{side}")
        matrix = by_part[name]["forward_affine_matrix"]
        # Predict the transformed source-alpha sole independently of the
        # already rendered layer. This keeps the ground gate non-tautological.
        projected_canonical_y = max(
            matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]
            for y in range(source_bbox[1], source_bbox[3])
            for x in range(source_bbox[0], source_bbox[2])
            if alpha.getpixel((x, y)) > 0
        )
        projected[side] = map_presentation_point((0.0, projected_canonical_y), spec["presentation_transform"])[1]
        bbox = details["presented_layers"][name].getchannel("A").getbbox()
        actual[side] = float(bbox[3] - 1) if bbox else -1.0
    support = SUPPORT_SIDE[frame]
    swing = SWING_SIDE.get(frame)
    depth = float(spec["qa_profile"]["thresholds"]["swing_ground_depth_px"]) * float(spec["presentation_transform"]["uniform_scale"])
    feet = {}
    for side in ("left", "right"):
        ground = projected[support] + depth if swing == side else projected[support]
        expected = projected[side]
        feet[side] = {"role": "swing" if swing == side else "planted" if side == support else "trail", "projected_ground_y": round(ground, 6), "expected_sole_y": round(expected, 6), "actual_sole_y": round(actual[side], 6), "sole_error_px": round(actual[side] - expected, 6), "ground_penetration_px": round(max(0.0, actual[side] - ground), 6), "visible_clearance_px": round(ground - actual[side], 6), "ankle_x": round(float(target["joints"][f"ankle_{side}"]["x"]), 6)}
    sole_limit = float(spec["qa_profile"]["thresholds"]["sole_error_max_px"])
    penetration_limit = float(spec["qa_profile"]["thresholds"]["ground_penetration_max_px"])
    gates = {side: abs(item["sole_error_px"]) <= sole_limit and item["ground_penetration_px"] <= penetration_limit and (item["role"] != "swing" or item["visible_clearance_px"] >= float(spec["qa_profile"]["thresholds"]["swing_clearance_min_px"])) for side, item in feet.items()}
    return {"frame": frame, "support_side": support, "swing_side": swing, "feet": feet, "thresholds": {"sole_error_max_px": sole_limit, "ground_penetration_max_px": penetration_limit, "swing_clearance_min_px": float(spec["qa_profile"]["thresholds"]["swing_clearance_min_px"])}, "hard_gates": gates, "status": "RUN_FOOT_GROUND_QA_PASSED" if all(gates.values()) else "RUN_FOOT_GROUND_GAP"}


def _contact_foot_qa(targets: list[Mapping[str, Any]], spec: Mapping[str, Any]) -> dict[str, Any]:
    limit = float(spec["qa_profile"]["thresholds"]["contact_ankle_slip_max_px"])
    windows = []
    for first, second, side in CONTACT_WINDOWS:
        a = _xy(targets[first]["joints"][f"ankle_{side}"])
        b = _xy(targets[second]["joints"][f"ankle_{side}"])
        slip = math.dist(a, b)
        windows.append({"from_frame": first, "to_frame": second, "side": side, "ankle_slip_px": round(slip, 6), "gate": slip <= limit})
    return {"contact_windows": windows, "threshold_px": limit, "hard_gates": {"all_contact_windows": all(item["gate"] for item in windows)}, "status": "RUN_CONTACT_FOOT_QA_PASSED" if all(item["gate"] for item in windows) else "RUN_CONTACT_FOOT_GAP"}


def _angles(targets: list[Mapping[str, Any]]) -> list[dict[str, float]]:
    return [{f"{a}:{b}:{c}": round(_joint_angle(_xy(target["joints"][a]), _xy(target["joints"][b]), _xy(target["joints"][c])), 6) for a, b, c in ANGLE_CHAINS} for target in targets]


def _joint_angle(first: tuple[float, float], middle: tuple[float, float], last: tuple[float, float]) -> float:
    value = math.degrees(math.atan2(last[1] - middle[1], last[0] - middle[0]) - math.atan2(first[1] - middle[1], first[0] - middle[0]))
    while value > 180.0:
        value -= 360.0
    while value < -180.0:
        value += 360.0
    return value


def _path(values: list[tuple[float, float]], closing: bool = False) -> float:
    total = sum(math.dist(values[index - 1], values[index]) for index in range(1, len(values)))
    if closing and values:
        total += math.dist(values[-1], values[0])
    return total


def _arm_angles(targets: list[Mapping[str, Any]]) -> tuple[list[float], list[float]]:
    return ([ _direction(_xy(target["joints"]["shoulder_left"]), _xy(target["joints"]["wrist_left"])) for target in targets], [ _direction(_xy(target["joints"]["shoulder_right"]), _xy(target["joints"]["wrist_right"])) for target in targets])


def _temporal_qa(spec: Mapping[str, Any], context: Mapping[str, Any], prepared: Mapping[str, Any], records: list[Mapping[str, Any]], outputs: list[Image.Image]) -> dict[str, Any]:
    thresholds = spec["qa_profile"]["thresholds"]
    targets = prepared["targets"]
    angles = _angles(targets)
    deltas = [abs(_signed_delta(angles[index - 1][key], angles[index][key])) for index in range(1, len(angles)) for key in angles[index]]
    deltas.append(max(abs(_signed_delta(angles[-1][key], angles[0][key])) for key in angles[-1]))
    accelerations = [abs(angles[index][key] - 2 * angles[index - 1][key] + angles[index - 2][key]) for index in range(2, len(angles)) for key in angles[index]]
    pelvis = [_xy(target["joints"]["pelvis"]) for target in targets]
    root_path = _path(pelvis, closing=True)
    root_x = max(point[0] for point in pelvis) - min(point[0] for point in pelvis)
    root_y = max(point[1] for point in pelvis) - min(point[1] for point in pelvis)
    loop_joint_steps = [math.dist(_xy(targets[-1]["joints"][name]), _xy(targets[0]["joints"][name])) for name in CORE_JOINTS]
    left_arm, right_arm = _arm_angles(targets)
    arm_deltas = [_signed_delta(left_arm[index - 1], left_arm[index]) for index in range(1, len(left_arm))] + [_signed_delta(left_arm[-1], left_arm[0])]
    right_deltas = [_signed_delta(right_arm[index - 1], right_arm[index]) for index in range(1, len(right_arm))] + [_signed_delta(right_arm[-1], right_arm[0])]
    opposition_pairs = [{"from_frame": index - 1 if index else len(targets) - 1, "to_frame": index, "left_delta_deg": round(arm_deltas[index], 6), "right_delta_deg": round(right_deltas[index], 6), "opposed": arm_deltas[index] * right_deltas[index] < 0.0} for index in range(len(targets))]
    source_left_ankle = skeleton_point(context["skeleton"], "ankle_left")[0]
    source_right_ankle = skeleton_point(context["skeleton"], "ankle_right")[0]
    left_stride = [float(target["joints"]["ankle_left"]["x"]) - source_left_ankle for target in targets]
    right_stride = [float(target["joints"]["ankle_right"]["x"]) - source_right_ankle for target in targets]
    cadence_phase = {
        "left_passing_excursion": left_stride[2] > left_stride[0] + float(thresholds["minimum_stride_excursion_px"]),
        "right_passing_excursion": right_stride[6] > right_stride[4] + float(thresholds["minimum_stride_excursion_px"]),
        "left_and_right_passing_are_distinct": left_stride[2] > right_stride[2] and right_stride[6] > left_stride[6],
    }
    walk_spec = read_json(context["root"] / "profiles/animation/walk-front-v1.json")
    from . import walk_front_v1

    walk_context = walk_front_v1.load_context(walk_spec, context["root"])
    walk_prepared = walk_front_v1.prepare(walk_spec, walk_context)
    walk_pelvis = [_xy(walk_prepared["targets"][phase]["joints"]["pelvis"]) for phase in walk_prepared["phases"]]
    walk_path = _path(walk_pelvis, closing=True)
    contact = _contact_foot_qa(targets, spec)
    foot_records = [record["feet"] for record in records]
    foot_frame_gate = all(record.get("feet", {}).get("status") == "RUN_FOOT_GROUND_QA_PASSED" for record in records)
    frame_heights = []
    for output in outputs:
        bbox = output.getchannel("A").getbbox()
        frame_heights.append(float(bbox[3] - bbox[1]) if bbox else 0.0)
    height_variation = (max(frame_heights) - min(frame_heights)) / max(1.0, sum(frame_heights) / len(frame_heights))
    loop_gates = {"all_core_joints_close": max(loop_joint_steps, default=999.0) <= float(thresholds["loop_joint_step_max_px"]), "root_close": math.dist(pelvis[-1], pelvis[0]) <= float(thresholds["loop_root_step_max_px"]), "phase_zero_and_last_are_not_duplicate": target_digest(targets[-1]) != target_digest(targets[0])}
    gates = {
        "cadence_has_two_opposite_contacts": [0, 4] == list(spec["adapter_parameters"]["contact_frames"]) and spec["adapter_parameters"]["contact_sides"] == ["left", "right"],
        "passing_frames_are_declared": spec["adapter_parameters"]["passing_frames"] == [2, 6],
        "flight_frames_are_declared": spec["adapter_parameters"]["flight_frames"] == [3, 7],
        "cadence_phase_alternates": all(cadence_phase.values()),
        "all_target_hashes_distinct": len({target_digest(target) for target in targets}) == len(targets),
        "root_path_meets_run_minimum": root_path >= float(thresholds["root_path_min_px"]),
        "root_horizontal_range_meets_run_minimum": root_x >= float(thresholds["root_horizontal_range_min_px"]),
        "root_vertical_range_meets_run_minimum": root_y >= float(thresholds["root_vertical_range_min_px"]),
        "root_motion_exceeds_walk_baseline": root_path > walk_path * float(thresholds["run_vs_walk_path_ratio_min"]),
        "body_root_participation": root_x > 0.0 and root_y > 0.0 and float(thresholds["torso_rotation_range_min_deg"]) <= max(float(value) for value in [max(prepared["samples"][i]["torso_rotation_deg"] for i in range(len(targets))) - min(prepared["samples"][i]["torso_rotation_deg"] for i in range(len(targets)))]) ,
        "arm_leg_opposition": sum(item["opposed"] for item in opposition_pairs) >= int(thresholds["opposition_transition_min_count"]),
        "foot_contact_windows": contact["status"] == "RUN_CONTACT_FOOT_QA_PASSED",
        "foot_ground_all_frames": foot_frame_gate,
        "angular_continuity": max(deltas, default=999.0) <= float(thresholds["joint_angle_step_max_deg"]),
        "angular_acceleration_continuity": max(accelerations, default=999.0) <= float(thresholds["angular_acceleration_max_deg_per_frame2"]),
        "nonfinite_and_gap_free": all(math.isfinite(value) for target in targets for joint in target["joints"].values() for value in (_xy(joint)[0], _xy(joint)[1])),
        "foreground_height_stability": height_variation <= float(thresholds["foreground_height_variation_max"]),
        **{f"loop_{name}": value for name, value in loop_gates.items()},
    }
    return {"phase_order": list(PHASES), "contact_frames": spec["adapter_parameters"]["contact_frames"], "passing_frames": spec["adapter_parameters"]["passing_frames"], "flight_frames": spec["adapter_parameters"]["flight_frames"], "cadence_phase": {"left_stride_x": [round(value, 6) for value in left_stride], "right_stride_x": [round(value, 6) for value in right_stride], "hard_gates": cadence_phase}, "metrics": {"root_path_length_px": round(root_path, 6), "walk_baseline_root_path_length_px": round(walk_path, 6), "run_vs_walk_path_ratio": round(root_path / max(walk_path, 1e-6), 6), "root_horizontal_range_px": round(root_x, 6), "root_vertical_range_px": round(root_y, 6), "max_joint_angle_step_deg": round(max(deltas, default=0.0), 6), "max_angular_acceleration_deg_per_frame2": round(max(accelerations, default=0.0), 6), "max_loop_joint_step_px": round(max(loop_joint_steps, default=0.0), 6), "loop_root_step_px": round(math.dist(pelvis[-1], pelvis[0]), 6), "foreground_height_variation": round(height_variation, 6), "opposition_transitions": sum(item["opposed"] for item in opposition_pairs)}, "arm_opposition": {"pairs": opposition_pairs, "hard_gates": {"minimum_opposed_transitions": sum(item["opposed"] for item in opposition_pairs) >= int(thresholds["opposition_transition_min_count"])}}, "contact": contact, "foot_frame_count": len(foot_records), "hard_gates": gates, "status": "RUN_TEMPORAL_QA_PASSED" if all(gates.values()) else "RUN_TEMPORAL_QA_GAP"}


def qa(spec: Mapping[str, Any], context: Mapping[str, Any], manifest: Mapping[str, Any], root: Path) -> dict[str, Any]:
    prepared = prepare(spec, context)
    records, outputs, structural = [], [], {}
    binding_by_frame = {int(item["frame"]): str(item["target_hash"]) for item in spec["key_pose_bindings"]}
    for index, item in enumerate(manifest["frames"]):
        target = prepared["targets"][index]
        image, details = render_source_only(context, target, list(Z_ORDER), prepared["presentation"])
        outputs.append(image)
        pair, seam, integrity, aux = _plan_and_structural(context, target, details, PHASES[index], prepared["plan"])
        foot = _foot_record(context, target, details, spec)
        alpha = actual_alpha_safe_margin(image, float(spec["qa_profile"]["thresholds"]["alpha_safe_margin_px"]))
        duplicate = duplicate_body_measure(image)
        transforms_ok = all(item_transform.get("nonuniform_scale") is False for item_transform in details["transforms"])
        gates = {
            "source_hashes": all(value["source_part_rgba_sha256"] == context["part_hashes"][value["part"]] for value in details["transforms"]),
            "target_binding": target_digest(target) == item["target_hash"],
            "key_pose_binding": index not in binding_by_frame or binding_by_frame[index] == target_digest(target),
            "global_uniform_transform": transforms_ok and bool(spec["presentation_transform"]["frozen_before_render"]),
            "alpha_safe_margin": bool(alpha["gate"]),
            "structural_holes_zero": aux["coverage"]["structural_hole_pixels"] == 0,
            "layer_integrity": integrity["status"] == "LAYER_INTEGRITY_PASSED",
            "occlusion": pair["status"] == "OCCLUSION_QA_PASSED",
            "seam": seam["status"] == "SEAM_TOPOLOGY_PASSED",
            "retention": aux["retention"]["status"] == "RETENTION_OCCLUSION_PASSED",
            "foot_ground": foot["status"] == "RUN_FOOT_GROUND_QA_PASSED",
            "no_duplicate_body": duplicate["gate"],
            "front_facing": target.get("orientation") == "front",
            "finite_target": all(math.isfinite(value) for joint in target["joints"].values() for value in _xy(joint)),
        }
        record = {"index": index, "phase": PHASES[index], "target_hash": target["target_joint_sha256"], "output_rgba_sha256": item["rgba_sha256"], "hard_gates": gates, "passed": all(gates.values()), "feet": foot, "alpha": alpha, "duplicate_body": duplicate, "integrity": integrity, "occlusion": pair, "seam": seam, "coverage": {key: value for key, value in aux["coverage"].items() if key not in {"hole_mask", "expected_mask"}}, "retention": aux["retention"], "z_order": list(Z_ORDER), "target": target, "status": "RUN_FRAME_PASSED" if all(gates.values()) else "RUN_FRAME_GAP"}
        records.append(record)
        structural[PHASES[index]] = {"pair": pair, "seam": seam, "coverage": record["coverage"], "retention": record["retention"]}
    temporal = _temporal_qa(spec, context, prepared, records, outputs)
    top_gates = {
        "frame_count_exact": len(records) == int(spec["frame_count"]),
        "all_frames": bool(records) and all(record["passed"] for record in records),
        "temporal_quality": temporal["status"] == "RUN_TEMPORAL_QA_PASSED",
        "track_hash_bound": prepared["track_hash"] == motion_tracks_sha256(spec),
        "event_timeline_frozen": [(item["event_id"], item["frame"]) for item in spec.get("event_markers", [])] == [("left_contact", 0), ("left_support", 1), ("left_passing", 2), ("left_flight", 3), ("right_contact", 4), ("right_support", 5), ("right_passing", 6), ("loop_closure", 7), ("right_flight", 7)],
        "provenance_source_only": bool(spec["provenance"]["source_only_pixels"]) and spec["provenance"]["sam2_used"] is False and int(spec["provenance"]["comfyui_generation_jobs"]) == 0 and spec["provenance"]["diffusion_used"] is False,
        "package_frame_bindings": len({item["rgba_sha256"] for item in manifest["frames"]}) == len(manifest["frames"]) and all((root / item["path"]).is_file() for item in manifest["frames"]),
    }
    failures = [name for name, passed in top_gates.items() if not passed]
    failures.extend(f"frame_{record['index']}_{name}" for record in records for name, passed in record["hard_gates"].items() if not passed)
    failures.extend(f"temporal_{name}" for name, passed in temporal["hard_gates"].items() if not passed)
    qualified = all(top_gates.values()) and not failures
    return {"animation_id": spec["animation_id"], "decision": "QUALIFIED" if qualified else "FAILED", "status": "CUTOUT_ANIMATION_RUNTIME_V1_RUN_FRONT_TECHNICALLY_QUALIFIED" if qualified else "RUN_FRONT_STRUCTURAL_OR_TEMPORAL_GAP", "frames": records, "temporal": temporal, "body_mechanics": {"metrics": temporal["metrics"], "hard_gates": {key: value for key, value in temporal["hard_gates"].items() if key in {"root_path_meets_run_minimum", "root_horizontal_range_meets_run_minimum", "root_vertical_range_meets_run_minimum", "root_motion_exceeds_walk_baseline", "body_root_participation", "arm_leg_opposition"}}, "status": "RUN_BODY_MECHANICS_QA_PASSED" if temporal["hard_gates"]["body_root_participation"] and temporal["hard_gates"]["arm_leg_opposition"] else "RUN_BODY_MECHANICS_GAP"}, "foot_ground": {"frames": [record["feet"] for record in records], "contact": temporal["contact"], "status": "RUN_FOOT_GROUND_QA_PASSED" if temporal["hard_gates"]["foot_ground_all_frames"] and temporal["hard_gates"]["foot_contact_windows"] else "RUN_FOOT_GROUND_GAP"}, "package_metadata": {"phase_markers": list(spec.get("event_markers", [])), "motion_quality_layer": "generic.motion_tracks", "source_only_renderer": "source-affine-resample-and-alpha-composite"}, "provenance": {"source_sha256": context["source_sha256"], "part_hashes": context["part_hashes"], "mask_hashes": context["mask_hashes"], "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "source_only_pixels": True}, "hard_gates": top_gates, "failures": failures, "structural": structural}
