"""Deterministic idle-front adapter over the immutable R4 cutout rig."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw

from ..cutout_occlusion import TOPOLOGY_ADJACENCY, topological_seam_qa
from ..cutout_rig import PART_NAMES, PART_SPECS, skeleton_point, transform_parameters
from ..cutout_structural import _binary, _count, _digest_image, _explicit_pair_key, _region_mask_for_pair, layer_integrity_qa, pairwise_overlap_v073, structural_coverage_qa
from ..pose_metric_calibration import CORE_JOINTS, detected_joint_pose_metrics
from ..pose_qa_estimator import _detect
from ..animation_profiles.common import load_source_context, render_source_only, sha256_bytes, target_digest
from ..cutout_temporal_v081 import actual_alpha_safe_margin, duplicate_body_measure, map_presentation_point


PHASES = ("I0-neutral-A", "I1-inhale-early", "I2-inhale-mid", "I3-inhale-peak", "I4-return-A", "I5-neutral-B", "I6-exhale-early", "I7-exhale-mid", "I8-exhale-peak", "I9-return-B", "I10-settle", "I11-pre-loop")
Z_ORDER = ("right_shin_foot", "right_thigh", "left_forearm_hand", "left_upper_arm", "torso_pelvis", "left_thigh", "left_shin_foot", "right_upper_arm", "right_forearm_hand", "head", "sword")
ANGLE_CHAINS = (("shoulder_left", "elbow_left", "wrist_left"), ("shoulder_right", "elbow_right", "wrist_right"), ("hip_left", "knee_left", "ankle_left"), ("hip_right", "knee_right", "ankle_right"))


def _xy(value: Any) -> tuple[float, float]:
    return (float(value["x"]), float(value["y"])) if isinstance(value, Mapping) else (float(value[0]), float(value[1]))


def _point(x: float, y: float) -> dict[str, float]:
    return {"x": round(float(x), 6), "y": round(float(y), 6)}


def _angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    value = math.degrees(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(a[1] - b[1], a[0] - b[0]))
    while value > 180: value -= 360
    while value < -180: value += 360
    return value


def load_context(spec: Mapping[str, Any], root: Path) -> dict[str, Any]:
    return load_source_context(spec, root)


def _base_target(context: Mapping[str, Any]) -> dict[str, Any]:
    skeleton = context["skeleton"]
    names = list(CORE_JOINTS) + ["nose", "neck", "pelvis", "shoulder_center", "weapon_tip"]
    joints = {name: _point(*skeleton_point(skeleton, name)) for name in names}
    return {"joints": joints, "phase": PHASES[0], "view": "front", "orientation": "front", "generator": {"kind": "deterministic-skeleton-only", "parameters_frozen_before_render": True, "pixel_interpolation": False}}


def _wave(index: int) -> float:
    theta = (2.0 * math.pi * index) / len(PHASES)
    return math.sin(theta) + 0.08 * math.sin(2.0 * theta)


def _target_for_frame(context: Mapping[str, Any], index: int, params: Mapping[str, Any]) -> dict[str, Any]:
    target = copy.deepcopy(params["base_target"])
    wave = _wave(index)
    root_shift = float(params["root_vertical_amplitude_canonical_px"]) * wave
    head_shift = round(float(params["head_vertical_amplitude_canonical_px"]) * wave)
    shoulder_shift = round(float(params["shoulder_vertical_amplitude_canonical_px"]) * wave)
    joints = target["joints"]
    for name in ("hip_left", "hip_right", "pelvis"):
        joints[name]["y"] = round(joints[name]["y"] + root_shift, 6)
    hip_spread = round(float(params.get("hip_spread_canonical_px", 1.5)) * abs(wave), 6)
    joints["hip_left"]["x"] = round(joints["hip_left"]["x"] - hip_spread, 6)
    joints["hip_right"]["x"] = round(joints["hip_right"]["x"] + hip_spread, 6)
    joints["pelvis"]["x"] = round((joints["hip_left"]["x"] + joints["hip_right"]["x"]) / 2.0, 6)
    for name in ("shoulder_left", "shoulder_right", "shoulder_center", "elbow_left", "elbow_right", "wrist_left", "wrist_right"):
        joints[name]["y"] = round(joints[name]["y"] + shoulder_shift, 6)
    joints["nose"]["y"] = round(joints["nose"]["y"] + head_shift, 6)
    joints["neck"]["y"] = round(joints["neck"]["y"] + shoulder_shift, 6)
    wrist = _xy(joints["wrist_right"]); tip = _xy(joints["weapon_tip"])
    theta = math.radians(float(params["sword_angle_amplitude_degrees"]) * wave)
    vx, vy = tip[0] - wrist[0], tip[1] - wrist[1]
    joints["weapon_tip"] = _point(wrist[0] + vx * math.cos(theta) - vy * math.sin(theta), wrist[1] + vx * math.sin(theta) + vy * math.cos(theta))
    target["phase"] = PHASES[index]; target["frame_index"] = index; target["target_joint_sha256"] = target_digest(target)
    return target


def _idle_plan() -> dict[str, Any]:
    phase_plans = {phase: {"phase": phase, "frame_index": index, "z_order": list(Z_ORDER), "front_parts": ["left_thigh", "left_shin_foot", "right_upper_arm", "right_forearm_hand"], "back_parts": ["right_thigh", "right_shin_foot", "left_upper_arm", "left_forearm_hand"], "depth_role": {"left_leg": "front_lead", "right_leg": "back_trail", "left_arm": "front_counter_swing", "right_arm": "back"}, "switch_boundary": None} for index, phase in enumerate(PHASES)}
    value = {"schema_version": "animation-spec-1.0", "plan_id": "animation-idle-front-constant-z-v1", "phase_plans": phase_plans, "critical_pairs": [["sword", "torso_pelvis"], ["sword", "head"], ["left_upper_arm", "right_upper_arm"], ["left_forearm_hand", "right_forearm_hand"]], "allowed_expected_occlusion_pairs": [["head", "left_upper_arm"], ["head", "right_upper_arm"], ["torso_pelvis", "left_forearm_hand"], ["torso_pelvis", "right_forearm_hand"], ["left_forearm_hand", "left_thigh"], ["right_forearm_hand", "right_thigh"], ["right_thigh", "sword"], ["left_thigh", "right_thigh"], ["left_shin_foot", "right_shin_foot"]]}
    import hashlib, json
    value["plan_sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return value


def prepare(spec: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    params = dict(spec["interpolation_profile"]["parameters"])
    params["base_target"] = _base_target(context)
    params["targets"] = [_target_for_frame(context, index, params) for index in range(int(spec["frame_count"]))]
    params["plan"] = _idle_plan()
    params["presentation"] = spec["presentation_transform"]
    params["phases"] = list(PHASES)
    return params


def render_frame(spec: Mapping[str, Any], context: Mapping[str, Any], prepared: Mapping[str, Any], index: int):
    target = prepared["targets"][index]
    image, details = render_source_only(context, target, list(Z_ORDER), prepared["presentation"])
    return image, {"phase": PHASES[index], "target_hash": target["target_joint_sha256"], "presentation_target_hash": details["target_presented"]["presentation_target_joint_sha256"], "z_order": list(Z_ORDER), "target": target}


def _bbox_area(image: Image.Image) -> float:
    bbox = image.getchannel("A").getbbox()
    return float((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) if bbox else 0.0


def layer_bbox_measurement(presented_layers: Mapping[str, Image.Image]) -> dict[str, Any]:
    """Measure the alpha bbox of the named presented layer, not the composite."""
    result: dict[str, Any] = {}
    for name in ("head", "torso_pelvis"):
        image = presented_layers[name]
        bbox = image.getchannel("A").getbbox()
        result[name] = {"bbox": list(bbox) if bbox else None, "area": _bbox_area(image)}
    return result


def layer_bbox_temporal_gate(layer_bboxes: list[Mapping[str, Any]], threshold: float = 0.025) -> dict[str, Any]:
    """Evaluate independent head and torso layer bbox-area stability."""
    areas = {name: [float(item.get(name, {}).get("area", 0.0)) for item in layer_bboxes] for name in ("head", "torso_pelvis")}
    cvs = {name: _cv(values) if values and all(values) else 999.0 for name, values in areas.items()}
    gates = {"head_bbox_area_cv_le_threshold": cvs["head"] <= threshold, "torso_bbox_area_cv_le_threshold": cvs["torso_pelvis"] <= threshold}
    return {"areas": areas, "cv": cvs, "hard_gates": gates, "status": "IDLE_LAYER_BBOX_TEMPORAL_PASSED" if all(gates.values()) else "IDLE_LAYER_BBOX_TEMPORAL_GAP"}


def _cv(values: list[float]) -> float:
    mean = sum(values) / max(1, len(values))
    return math.sqrt(sum((v - mean) ** 2 for v in values) / max(1, len(values))) / max(1e-6, mean)


def _dual_feet(context: Mapping[str, Any], target: Mapping[str, Any], details: Mapping[str, Any], presentation: Mapping[str, Any], limits: Mapping[str, Any] | None = None) -> dict[str, Any]:
    limits = limits or {}
    sole_limit = float(limits.get("sole_error_px", 1.5))
    penetration_limit = float(limits.get("ground_penetration_px", 1.5))
    records: dict[str, Any] = {}
    for side in ("left", "right"):
        name = f"{side}_shin_foot"; transform = next(item for item in details["transforms"] if item["part"] == name)
        anchor = context["parts"][name].getchannel("A").getbbox(); sole_y = float(anchor[3] - 1) if anchor else -1.0
        matrix = transform["forward_affine_matrix"]; projected = matrix[1][0] * (anchor[0] + anchor[2]) / 2 + matrix[1][1] * sole_y + matrix[1][2] if anchor else -1
        projected = map_presentation_point((0.0, projected), presentation)[1]
        bbox = details["presented_layers"][name].getchannel("A").getbbox(); actual = float(bbox[3] - 1) if bbox else -1
        ankle = target["joints"][f"ankle_{side}"]
        records[side] = {"projected_ground_y": round(projected, 6), "actual_sole_y": round(actual, 6), "sole_error_px": round(actual - projected, 6), "ground_penetration_px": round(max(0.0, actual - projected), 6), "ankle": ankle, "ankle_x": round(float(ankle["x"]), 6)}
    gates = {side: abs(item["sole_error_px"]) <= sole_limit and item["ground_penetration_px"] <= penetration_limit for side, item in records.items()}
    return {"feet": records, "hard_gates": gates, "thresholds": {"sole_error_px": sole_limit, "ground_penetration_px": penetration_limit}, "status": "IDLE_DUAL_FEET_PLANTED_PASSED" if all(gates.values()) else "IDLE_DUAL_FEET_GROUND_GAP"}


def dual_foot_gate(feet_record: Mapping[str, Any], sole_error_limit: float = 1.5) -> bool:
    """Re-evaluate the immutable per-frame foot error without tuning."""
    return all(abs(float(item.get("sole_error_px", 999.0))) <= sole_error_limit and float(item.get("ground_penetration_px", 999.0)) <= sole_error_limit for item in feet_record.get("feet", {}).values())


def dual_foot_drift_qa(frame_records: list[Mapping[str, Any]], sole_limit: float = 1.5, ankle_limit: float = 2.0) -> dict[str, Any]:
    """Measure cyclic sole-anchor and baseline ankle-x drift for both feet."""
    sides: dict[str, Any] = {}
    for side in ("left", "right"):
        samples = [record.get("feet", {}).get("feet", {}).get(side, {}) for record in frame_records]
        valid = len(samples) >= 2 and all("projected_ground_y" in item and "ankle_x" in item for item in samples)
        if not valid:
            sides[side] = {"hard_gates": {"sole_error_le_threshold": False, "ground_penetration_le_threshold": False, "frame_to_frame_sole_anchor_drift_le_threshold": False, "ankle_horizontal_drift_from_baseline_le_threshold": False}, "status": "IDLE_DUAL_FEET_DRIFT_GAP", "reason": "missing_frame_measurements"}
            continue
        baseline_ankle_x = float(samples[0]["ankle_x"])
        baseline_projected_sole_y = float(samples[0]["projected_ground_y"])
        sole_pairs = [{"from_frame": (index - 1) % len(samples), "to_frame": index, "drift_px": abs(float(samples[index]["projected_ground_y"]) - float(samples[(index - 1) % len(samples)]["projected_ground_y"]))} for index in range(len(samples))]
        ankle_samples = [{"frame": index, "drift_px": abs(float(item["ankle_x"]) - baseline_ankle_x)} for index, item in enumerate(samples)]
        max_sole = max(sole_pairs, key=lambda item: item["drift_px"])
        max_ankle = max(ankle_samples, key=lambda item: item["drift_px"])
        hard_gates = {"sole_error_le_threshold": all(abs(float(item.get("sole_error_px", 999.0))) <= sole_limit for item in samples), "ground_penetration_le_threshold": all(float(item.get("ground_penetration_px", 999.0)) <= sole_limit for item in samples), "frame_to_frame_sole_anchor_drift_le_threshold": max_sole["drift_px"] <= sole_limit, "ankle_horizontal_drift_from_baseline_le_threshold": max_ankle["drift_px"] <= ankle_limit}
        sides[side] = {"baseline_ankle_x": round(baseline_ankle_x, 6), "baseline_projected_sole_y": round(baseline_projected_sole_y, 6), "frame_to_frame_sole_anchor_drift_px": {"max": round(max_sole["drift_px"], 6), "max_frame_pair": [max_sole["from_frame"], max_sole["to_frame"]], "threshold": sole_limit, "samples": [{**item, "drift_px": round(item["drift_px"], 6)} for item in sole_pairs]}, "ankle_horizontal_drift_from_baseline_px": {"max": round(max_ankle["drift_px"], 6), "max_frame": max_ankle["frame"], "threshold": ankle_limit, "samples": [{**item, "drift_px": round(item["drift_px"], 6)} for item in ankle_samples]}, "hard_gates": hard_gates, "status": "IDLE_DUAL_FEET_DRIFT_PASSED" if all(hard_gates.values()) else "IDLE_DUAL_FEET_DRIFT_GAP"}
    hard_gates = {f"{side}_{name}": value for side, item in sides.items() for name, value in item.get("hard_gates", {}).items()}
    return {"sides": sides, "hard_gates": hard_gates, "status": "IDLE_DUAL_FEET_DRIFT_PASSED" if hard_gates and all(hard_gates.values()) else "IDLE_DUAL_FEET_DRIFT_GAP"}


def z_order_gate(frame_records: list[Mapping[str, Any]]) -> bool:
    return bool(frame_records) and all(list(item.get("z_order", ())) == list(Z_ORDER) for item in frame_records) and len({tuple(item.get("z_order", ())) for item in frame_records}) == 1


def _plan_and_structural(context: Mapping[str, Any], target: Mapping[str, Any], details: Mapping[str, Any], phase: str, plan: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    pairs = [(parent, child) for parent, child, _ in TOPOLOGY_ADJACENCY]
    for raw in plan.get("allowed_expected_occlusion_pairs", []):
        pair = (str(raw[0]), str(raw[1]))
        if set(pair) not in [set(item) for item in pairs]: pairs.append(pair)
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
    pair["hard_gates"]["explicit_idle_allowed_pair_rules"] = bool(plan.get("allowed_expected_occlusion_pairs"))
    pair["status"] = "OCCLUSION_QA_PASSED" if all(pair["hard_gates"].values()) else "CUTOUT_RIG_OCCLUSION_REGION_GAP"
    seam = topological_seam_qa(details["layers"], phase, target, plan)
    integrity = layer_integrity_qa(context["parts"], details["layers"], details["transforms"], context["source"].size)
    core_for_pose = dict(context["core"]); core_for_pose["torso_transform"] = next(item for item in details["transforms"] if item["part"] == "torso_pelvis")
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
    retention = {"schema_version": "animation-spec-1.0", "phase": phase, "parts": retention_parts, "hard_gates": {"all_parts_pass": all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in retention_parts.values())}, "status": "RETENTION_OCCLUSION_PASSED" if all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in retention_parts.values()) else "CUTOUT_RIG_RETENTION_GAP"}
    return pair, seam, integrity, {"coverage": coverage, "retention": retention}


def _pose(frame_path: Path, target: Mapping[str, Any], root: Path) -> dict[str, Any]:
    model = Path(__import__("os").environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "UGAS" / "pose-qa" / "pose_landmarker_full.task"
    try:
        detected = _detect(frame_path, model)
        landmarks = detected.get("landmarks", {})
        metrics = detected_joint_pose_metrics(target["joints"], landmarks, target_orientation="front", detected_orientation="front", visibility={n: float(v.get("visibility", v.get("confidence", 0))) for n, v in landmarks.items()})
        return {"detected": detected, "metrics": metrics}
    except Exception as exc:
        return {"detected": {"detected": False, "error": f"{type(exc).__name__}: {exc}"}, "metrics": {"qualifies": False, "measurement_status": "UNMEASURABLE", "failure_reasons": ["media_pipe_exception"]}}


def temporal_gate_summary(spec: Mapping[str, Any], targets: list[Mapping[str, Any]], outputs: list[Image.Image], frame_records: list[Mapping[str, Any]]) -> dict[str, Any]:
    threshold = spec["qa_profile"]["thresholds"]
    angles: list[dict[str, float]] = []
    for target in targets:
        angles.append({f"{a}:{b}:{c}": _angle(_xy(target["joints"][a]), _xy(target["joints"][b]), _xy(target["joints"][c])) for a, b, c in ANGLE_CHAINS})
    deltas = [abs(angles[i][key] - angles[(i - 1) % len(angles)][key]) for i in range(len(angles)) for key in angles[i]]
    accelerations = [abs(angles[i][key] - 2 * angles[(i - 1) % len(angles)][key] + angles[(i - 2) % len(angles)][key]) for i in range(len(angles)) for key in angles[i]]
    p = [map_presentation_point(_xy(item["joints"]["pelvis"]), spec["presentation_transform"]) for item in targets]
    n = [map_presentation_point(_xy(item["joints"]["nose"]), spec["presentation_transform"]) for item in targets]
    tips = [map_presentation_point(_xy(item["joints"]["weapon_tip"]), spec["presentation_transform"]) for item in targets]
    wrists = [map_presentation_point(_xy(item["joints"]["wrist_right"]), spec["presentation_transform"]) for item in targets]
    root_y = max(item[1] for item in p) - min(item[1] for item in p); root_x = max(item[0] for item in p) - min(item[0] for item in p)
    head_step = max(math.dist(n[i], n[(i - 1) % len(n)]) for i in range(len(n)))
    sword_pp = max(math.dist(tips[i], tips[(i + 6) % len(tips)]) for i in range(len(tips)))
    boundary_root = math.dist(p[0], p[-1]); boundary_head = math.dist(n[0], n[-1]); boundary_sword = math.dist(tips[0], tips[-1])
    target_hashes = {target_digest(item) for item in targets}
    z_switches = sum(frame_records[i].get("z_order") != frame_records[(i - 1) % len(frame_records)].get("z_order") for i in range(len(frame_records)))
    heights = [float((out.getchannel("A").getbbox() or (0, 0, 0, 0))[3] - (out.getchannel("A").getbbox() or (0, 0, 0, 0))[1]) for out in outputs]
    feet = all(bool(record.get("feet", {}).get("hard_gates", {})) and all(record["feet"]["hard_gates"].values()) for record in frame_records)
    dual_feet = dual_foot_drift_qa(frame_records, float(spec["foot_policy"]["limits"].get("frame_to_frame_sole_anchor_drift_px", 1.5)), float(spec["foot_policy"]["limits"].get("ankle_horizontal_drift_from_baseline_px", 2.0)))
    layer_bbox = layer_bbox_temporal_gate([record.get("layer_bboxes", {}) for record in frame_records], float(threshold["head_torso_bbox_cv"]))
    head_areas = layer_bbox["areas"]["head"]
    torso_areas = layer_bbox["areas"]["torso_pelvis"]
    head_cv = layer_bbox["cv"]["head"]
    torso_cv = layer_bbox["cv"]["torso_pelvis"]
    gates = {"joint_angle_delta_le_10": max(deltas, default=999) <= float(threshold["joint_angle_delta_max_degrees"]), "angular_acceleration_le_8": max(accelerations, default=999) <= float(threshold["angular_acceleration_max_degrees_per_frame2"]), "root_vertical_pp_2_to_4": 2.0 <= root_y <= 4.0, "root_horizontal_pp_le_3": root_x <= 3.0, "head_adjacent_le_3": head_step <= 3.0, "head_bbox_cv_le_025": head_cv <= float(threshold["head_torso_bbox_cv"]), "torso_bbox_cv_le_025": torso_cv <= float(threshold["head_torso_bbox_cv"]), "feet_all_frames_pass": feet, "dual_foot_all_four_properties": dual_feet["status"] == "IDLE_DUAL_FEET_DRIFT_PASSED", "sword_visible_motion_pp_2_to_8": 2.0 <= sword_pp <= 8.0, "z_order_switches_zero": z_switches == 0, "loop_root_step_le_1_5": boundary_root <= 1.5, "loop_head_step_le_1_5": boundary_head <= 1.5, "loop_sword_step_le_3": boundary_sword <= 3.0, "distinct_target_hashes_at_least_10": len(target_hashes) >= 10, "foreground_bbox_height_variation_le_4_percent": (max(heights) - min(heights)) / max(1.0, sum(heights) / len(heights)) <= 0.04}
    return {"metrics": {"max_joint_angle_delta_degrees": max(deltas, default=0), "max_angular_acceleration_degrees_per_frame2": max(accelerations, default=0), "root_vertical_pp_presented_px": root_y, "root_horizontal_pp_presented_px": root_x, "head_adjacent_step_px": head_step, "head_bbox_areas": [round(value, 6) for value in head_areas], "torso_bbox_areas": [round(value, 6) for value in torso_areas], "head_bbox_area_cv": round(head_cv, 6), "torso_bbox_area_cv": round(torso_cv, 6), "foreground_bbox_heights": [round(value, 6) for value in heights], "sword_motion_pp_px": sword_pp, "loop_root_step_px": boundary_root, "loop_head_step_px": boundary_head, "loop_sword_step_px": boundary_sword, "distinct_target_hash_count": len(target_hashes), "phase_order": list(PHASES), "i11_is_distinct_from_i0": target_digest(targets[-1]) != target_digest(targets[0]), "dual_foot": dual_feet}, "hard_gates": gates, "status": "IDLE_TEMPORAL_LOOP_PASSED" if all(gates.values()) else "IDLE_TEMPORAL_LOOP_GAP"}


def qa(spec: Mapping[str, Any], context: Mapping[str, Any], manifest: Mapping[str, Any], root: Path) -> dict[str, Any]:
    prepared = prepare(spec, context)
    outputs: list[Image.Image] = []; targets: list[dict[str, Any]] = []; records: list[dict[str, Any]] = []; structural: dict[str, Any] = {}
    plan = prepared["plan"]
    for index, item in enumerate(manifest["frames"]):
        target = prepared["targets"][index]; targets.append(target)
        image, details = render_source_only(context, target, list(Z_ORDER), prepared["presentation"]); outputs.append(image)
        pair, seam, integrity, aux = _plan_and_structural(context, target, details, PHASES[index], plan)
        feet = _dual_feet(context, target, details, spec["presentation_transform"], spec["foot_policy"]["limits"])
        layer_bboxes = layer_bbox_measurement(details["presented_layers"])
        alpha = actual_alpha_safe_margin(image, 24)
        duplicate = duplicate_body_measure(image)
        frame_path = root / item["path"]
        pose = _pose(frame_path, details["target_presented"], root)
        metrics = pose["metrics"]
        sword = next(t for t in details["transforms"] if t["part"] == "sword")
        gates = {"source_hashes": all(t["source_part_rgba_sha256"] == context["part_hashes"][t["part"]] for t in details["transforms"]), "target_binding": target_digest(target) == item["target_hash"], "global_transform": all(t["nonuniform_scale"] is False for t in details["transforms"]) and spec["presentation_transform"]["frozen_before_render"], "alpha_margin_24": bool(alpha["gate"]), "structural_holes_zero": aux["coverage"]["structural_hole_pixels"] == 0, "layer_integrity": integrity["status"] == "LAYER_INTEGRITY_PASSED", "occlusion": pair["status"] == "OCCLUSION_QA_PASSED", "retention": aux["retention"]["status"] == "RETENTION_OCCLUSION_PASSED", "media_pipe_10_pck_nme_angle": metrics.get("qualifies") is True and int(metrics.get("measurable_body_joints", 0)) >= 10 and float(metrics.get("pck_at_010", 0)) >= 0.80 and float(metrics.get("nme", 1)) <= 0.10 and float(metrics.get("limb_angle_mae_degrees", 180)) <= 18, "sword_attached": sword["target_pivot"] == [target["joints"]["wrist_right"]["x"], target["joints"]["wrist_right"]["y"]], "source_only": True, "no_duplicate_body": duplicate["gate"], "both_feet_planted": feet["status"] == "IDLE_DUAL_FEET_PLANTED_PASSED", "frozen_z_order": details["transforms"] and list(Z_ORDER) == list(details["transforms"][0:len(Z_ORDER)][i]["part"] for i in range(len(Z_ORDER)))}
        record = {"index": index, "phase": PHASES[index], "target_hash": target["target_joint_sha256"], "output_rgba_sha256": item["rgba_sha256"], "hard_gates": gates, "alpha": alpha, "feet": feet, "layer_bboxes": layer_bboxes, "pose": pose, "duplicate_body": duplicate, "sword": {"target_pivot": sword["target_pivot"], "visible_tip_motion_source_only": True}, "integrity": integrity, "occlusion": pair, "seam": seam, "coverage": {k: v for k, v in aux["coverage"].items() if k not in {"hole_mask", "expected_mask"}}, "retention": aux["retention"], "z_order": list(Z_ORDER), "status": "IDLE_FRAME_PASSED" if all(gates.values()) else "IDLE_FRAME_GAP"}
        records.append(record); structural[PHASES[index]] = {"pair": pair, "seam": seam, "coverage": record["coverage"], "retention": record["retention"]}
    temporal = temporal_gate_summary(spec, targets, outputs, records)
    frame_pass = all(record["status"] == "IDLE_FRAME_PASSED" for record in records)
    gates = {"all_frames": frame_pass, "temporal_loop": temporal["status"] == "IDLE_TEMPORAL_LOOP_PASSED", "provenance": spec["provenance"]["source_only_pixels"] and spec["provenance"]["sam2_used"] is False and spec["provenance"]["comfyui_generation_jobs"] == 0 and spec["provenance"]["diffusion_used"] is False, "target_motion_nonzero": len({target_digest(t) for t in targets}) >= 10}
    failures = [name for name, passed in gates.items() if not passed]
    failures.extend(f"frame_{record['index']}_{name}" for record in records for name, passed in record["hard_gates"].items() if not passed)
    failures.extend(f"temporal_{name}" for name, passed in temporal["hard_gates"].items() if not passed)
    qualified = all(gates.values()) and not failures
    return {"animation_id": spec["animation_id"], "decision": "QUALIFIED" if qualified else "FAILED", "status": "CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED" if qualified else "ANIMATION_RUNTIME_IDLE_FRONT_GAP", "frames": records, "temporal": temporal, "provenance": {"source_sha256": context["source_sha256"], "part_hashes": context["part_hashes"], "mask_hashes": context["mask_hashes"], "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "source_only_pixels": True}, "hard_gates": gates, "failures": failures, "structural": structural}
