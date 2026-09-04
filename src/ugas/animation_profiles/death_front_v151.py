"""UGAS v0.15.1 source-only DEATH_ANIMATION_FRONT correction.

This adapter keeps the qualified R4 cutout renderer and z-order plan, but
replaces the v0.15.0 root-motion proxy with an explicit, measured contact
contract.  Ground contact is read from rendered alpha bottoms against one
frozen D0 ground reference.  The adapter never labels a frame from
``root_shift_y`` alone.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Mapping

from PIL import Image

from ..cutout_rig import skeleton_point
from ..cutout_temporal_v081 import duplicate_body_measure
from . import death_front_v1 as legacy
from .common import image_digest, render_source_only


PHASES = legacy.PHASES
Z_ORDER = legacy.Z_ORDER
ANGLE_CHAINS = legacy.ANGLE_CHAINS
GROUND_CONTACT_FRAME = 4
FINAL_POSE_FRAME = 7
DEATH_COLLAPSE_ALLOWED_PAIRS = (
    ("torso_pelvis", "left_shin_foot"),
    ("torso_pelvis", "right_shin_foot"),
    ("left_upper_arm", "left_thigh"),
    ("left_upper_arm", "left_shin_foot"),
    ("left_forearm_hand", "left_shin_foot"),
    ("right_forearm_hand", "sword"),
)
BODY_REGIONS = (
    "torso_pelvis",
    "left_forearm_hand",
    "right_forearm_hand",
    "left_thigh",
    "right_thigh",
    "head",
)
FOOT_REGIONS = ("left_shin_foot", "right_shin_foot")


def load_context(spec: Mapping[str, Any], root):
    return legacy.load_context(spec, root)


def prepare(spec: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    prepared = legacy.prepare(spec, context)
    plan = copy.deepcopy(prepared["plan"])
    existing = {frozenset(map(str, pair)) for pair in plan["allowed_expected_occlusion_pairs"]}
    for pair in DEATH_COLLAPSE_ALLOWED_PAIRS:
        if frozenset(pair) not in existing:
            plan["allowed_expected_occlusion_pairs"].append(list(pair))
    plan["plan_sha256"] = hashlib.sha256(json.dumps({key: value for key, value in plan.items() if key != "plan_sha256"}, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    prepared["plan"] = plan
    prepared["support_contact_states"] = copy.deepcopy(_contact_contract(spec)["states"])
    return prepared


def render_frame(spec: Mapping[str, Any], context: Mapping[str, Any], prepared: Mapping[str, Any], index: int):
    target = prepared["targets"][index]
    image, details = render_source_only(context, target, list(Z_ORDER), prepared["presentation"])
    return image, {
        "phase": PHASES[index],
        "target_hash": target["target_joint_sha256"],
        "presentation_target_hash": details["target_presented"]["presentation_target_joint_sha256"],
        "z_order": list(Z_ORDER),
        "target": target,
    }


def _contact_contract(spec: Mapping[str, Any]) -> dict[str, Any]:
    value = spec.get("adapter_parameters", {}).get("contact_contract", {})
    if not isinstance(value, Mapping):
        raise ValueError("v0151_contact_contract_missing")
    states = value.get("states")
    if not isinstance(states, list) or len(states) != int(spec["frame_count"]):
        raise ValueError("v0151_contact_states_must_match_frame_count")
    return dict(value)


def _bottom(image: Image.Image) -> float | None:
    bbox = image.getchannel("A").getbbox()
    return float(bbox[3] - 1) if bbox else None


def _bbox_center_x(image: Image.Image) -> float | None:
    bbox = image.getchannel("A").getbbox()
    return (float(bbox[0] + bbox[2] - 1) / 2.0) if bbox else None


def _ground_reference(context: Mapping[str, Any], spec: Mapping[str, Any], details: list[Mapping[str, Any]]) -> tuple[float, dict[str, Any]]:
    if not details:
        raise ValueError("v0151_ground_reference_requires_frames")
    projected, actual = legacy._projected_and_actual_soles(context, details[0], spec)
    values = [float(projected[side]) for side in ("left", "right")]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("v0151_ground_reference_not_finite")
    reference = sum(values) / len(values)
    return reference, {
        "method": "single-frozen-D0-projected-source-alpha-sole-reference",
        "source_frame": 0,
        "projected_sole_y": {side: round(projected[side], 6) for side in ("left", "right")},
        "D0_actual_sole_y": {side: round(actual[side], 6) for side in ("left", "right")},
        "ground_reference_y": round(reference, 6),
        "recomputed_per_frame": False,
    }


def _body_observation(details: Mapping[str, Any], ground_reference: float, thresholds: Mapping[str, Any]) -> dict[str, Any]:
    tolerance = float(thresholds["body_contact_tolerance_px"])
    penetration = float(thresholds["body_contact_penetration_max_px"])
    regions: dict[str, Any] = {}
    contact_regions: list[str] = []
    for name in BODY_REGIONS:
        bottom = _bottom(details["presented_layers"][name])
        clearance = None if bottom is None else ground_reference - bottom
        contact = bottom is not None and -penetration <= float(clearance) <= tolerance
        if contact:
            contact_regions.append(name)
        regions[name] = {
            "bottom_y": None if bottom is None else round(bottom, 6),
            "ground_clearance_px": None if clearance is None else round(float(clearance), 6),
            "contact": contact,
        }
    return {
        "regions": regions,
        "contact_regions": contact_regions,
        "body_contact": bool(contact_regions),
        "metric": "ground_reference_y_minus_rendered_region_alpha_bottom_y",
        "tolerance_px": tolerance,
        "penetration_max_px": penetration,
    }


def _foot_observation(details: Mapping[str, Any], ground_reference: float, thresholds: Mapping[str, Any], declared: Mapping[str, Any]) -> dict[str, Any]:
    planted_tolerance = float(thresholds["foot_planted_tolerance_px"])
    penetration = float(thresholds["foot_penetration_max_px"])
    lifted_min = float(thresholds["foot_lifted_clearance_min_px"])
    feet: dict[str, Any] = {}
    measured: dict[str, str] = {}
    declared_feet = declared.get("foot_support", {})
    for side in ("left", "right"):
        name = f"{side}_shin_foot"
        layer = details["presented_layers"][name]
        bottom = _bottom(layer)
        center_x = _bbox_center_x(layer)
        clearance = None if bottom is None else ground_reference - bottom
        planted = bottom is not None and -penetration <= float(clearance) <= planted_tolerance
        lifted = bottom is not None and float(clearance) >= lifted_min
        measured_role = "planted" if planted else ("lifted" if lifted else "transitional")
        measured[side] = measured_role
        feet[side] = {
            "declared_role": declared_feet.get(side),
            "measured_role": measured_role,
            "bottom_y": None if bottom is None else round(bottom, 6),
            "center_x": None if center_x is None else round(center_x, 6),
            "ground_clearance_px": None if clearance is None else round(float(clearance), 6),
            "planted_gate": planted,
            "lifted_gate": lifted,
        }
    return {
        "declared_support_mode": declared.get("foot_support_mode"),
        "feet": feet,
        "measured_support": measured,
        "state_matches_rendered": all(feet[side]["declared_role"] == measured[side] for side in ("left", "right")),
        "ground_reference_y": round(ground_reference, 6),
        "thresholds": {
            "planted_tolerance_px": planted_tolerance,
            "penetration_max_px": penetration,
            "lifted_clearance_min_px": lifted_min,
        },
    }


def _contact_transition(
    spec: Mapping[str, Any],
    prepared: Mapping[str, Any],
    body_records: list[Mapping[str, Any]],
    foot_records: list[Mapping[str, Any]],
    ground_reference: float,
    ground_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    contract = _contact_contract(spec)
    states = contract["states"]
    marker = next((item for item in spec.get("event_markers", []) if item.get("event_id") == "ground_contact"), {})
    marker_frame = marker.get("frame")
    measured_frames = [index for index, item in enumerate(body_records) if item["body_contact"]]
    measured_first = measured_frames[0] if measured_frames else None
    declared_first = next((index for index, item in enumerate(states) if item.get("body_contact_class") != "suspended"), None)
    expected_regions = [set(map(str, item.get("body_contact_regions", []))) for item in states]
    measured_regions = [set(map(str, item["contact_regions"])) for item in body_records]
    region_match = all(expected_regions[index].issubset(measured_regions[index]) for index in range(len(states)))
    state_matches = all(foot_records[index]["state_matches_rendered"] and bool(states[index].get("grounded_terminal")) == (index >= 6 and body_records[index]["body_contact"]) for index in range(len(states)))
    no_premature_contact = all(not body_records[index]["body_contact"] for index in range(GROUND_CONTACT_FRAME))
    marker_matches = measured_first == int(marker_frame) == GROUND_CONTACT_FRAME and declared_first == GROUND_CONTACT_FRAME and no_premature_contact
    terminal_frames = [6, 7]
    terminal_grounded = all(body_records[index]["body_contact"] and bool(states[index].get("grounded_terminal")) for index in terminal_frames)
    terminal_regions = all(expected_regions[index] and expected_regions[index].issubset(measured_regions[index]) for index in terminal_frames)
    reference_stable = (
        ground_metadata.get("source_frame") == 0
        and ground_metadata.get("recomputed_per_frame") is False
        and math.isfinite(ground_reference)
        and all(abs(float(item.get("ground_reference_y", ground_reference)) - ground_reference) < 1e-6 for item in foot_records)
    )
    return {
        "marker_frame": marker_frame,
        "declared_first_body_contact_frame": declared_first,
        "measured_first_body_contact_frame": measured_first,
        "measured_body_contact_frames": measured_frames,
        "marker_matches_measured_body_contact_transition": marker_matches,
        "contact_state_transition_valid": state_matches and region_match,
        "final_pose_grounded_terminal": terminal_grounded and terminal_regions,
        "ground_reference_stable": reference_stable,
        "no_premature_body_contact": no_premature_contact,
        "declared_regions_match_measured": region_match,
        "terminal_grounded_frames": terminal_frames,
        "ground_reference": dict(ground_metadata),
        "declared_states": copy.deepcopy(states),
    }


def _contact_continuity(body_records: list[Mapping[str, Any]], foot_records: list[Mapping[str, Any]], thresholds: Mapping[str, Any]) -> dict[str, Any]:
    limit = float(thresholds["contact_step_max_px"])
    steps: list[dict[str, Any]] = []
    passed = True
    for index in range(1, len(body_records)):
        previous = body_records[index - 1]
        current = body_records[index]
        shared = sorted(set(previous["contact_regions"]) & set(current["contact_regions"]))
        for name in shared:
            a = previous["regions"][name]["bottom_y"]
            b = current["regions"][name]["bottom_y"]
            delta = abs(float(b) - float(a)) if a is not None and b is not None else float("inf")
            gate = delta <= limit
            passed = passed and gate
            steps.append({"from_frame": index - 1, "to_frame": index, "region": name, "bottom_delta_px": round(delta, 6), "gate": gate})
        for side in ("left", "right"):
            a = foot_records[index - 1]["feet"][side]
            b = foot_records[index]["feet"][side]
            if a["measured_role"] != "planted" or b["measured_role"] != "planted":
                continue
            delta = math.dist((float(a["center_x"]), float(a["bottom_y"])), (float(b["center_x"]), float(b["bottom_y"])))
            gate = delta <= limit
            passed = passed and gate
            steps.append({"from_frame": index - 1, "to_frame": index, "region": f"{side}_foot", "anchor_delta_px": round(delta, 6), "gate": gate})
    return {"threshold_px": limit, "steps": steps, "gate": passed, "status": "CONTACT_CONTINUITY_PASSED" if passed else "CONTACT_TELEPORT_GAP"}


def _temporal(spec: Mapping[str, Any], context: Mapping[str, Any], prepared: Mapping[str, Any], outputs: list[Image.Image], body_records: list[Mapping[str, Any]], foot_records: list[Mapping[str, Any]], transition: Mapping[str, Any]) -> dict[str, Any]:
    thresholds = spec["qa_profile"]["thresholds"]
    targets = prepared["targets"]
    samples = prepared["samples"]
    rest = skeleton_point(context["skeleton"], "pelvis")
    angles = legacy._angles(targets)
    deltas = [abs(legacy._signed_delta(angles[index - 1][key], angles[index][key])) for index in range(1, len(angles)) for key in angles[index]]
    accelerations = [abs(legacy._signed_delta(angles[index - 1][key], angles[index][key]) - legacy._signed_delta(angles[index - 2][key], angles[index - 1][key])) for index in range(2, len(angles)) for key in angles[index]]
    pelvis = [legacy._xy(target["joints"]["pelvis"]) for target in targets]
    displacements = [math.dist(point, rest) for point in pelvis]
    root_x = [legacy._scalar(samples[index], "root_shift_x") for index in range(len(targets))]
    root_y = [legacy._scalar(samples[index], "root_shift_y") for index in range(len(targets))]
    torso = [legacy._scalar(samples[index], "torso_rotation_deg") for index in range(len(targets))]
    irreversible = all(displacements[index + 1] + 0.5 >= displacements[index] for index in range(legacy.DESTABILIZATION_FRAME, len(displacements) - 1))
    terminal_residual = math.dist(pelvis[6], pelvis[7])
    collapse_ratio = displacements[FINAL_POSE_FRAME] / max(max(displacements), 1e-6)
    death_like = max(abs(value) for value in torso) > float(thresholds["hit_death_torso_rotation_max_deg"]) and max(root_y) > float(thresholds["hit_death_root_drop_max_px"])
    weapon = legacy._weapon_qa(spec, context, targets)
    frame_heights = []
    for output in outputs:
        bbox = output.getchannel("A").getbbox()
        frame_heights.append(float(bbox[3] - bbox[1]) if bbox else 0.0)
    height_reduction = (frame_heights[0] - frame_heights[FINAL_POSE_FRAME]) / max(1.0, frame_heights[0]) if frame_heights else 0.0
    target_hashes = [legacy.target_digest(target) for target in targets]
    contact_continuity = _contact_continuity(body_records, foot_records, thresholds)
    gates = {
        "frame_count_eight_non_loop": int(spec["frame_count"]) == 8 and spec["loop"] is False,
        "all_target_hashes_distinct": len(set(target_hashes)) == len(target_hashes),
        "lethal_onset_immediate": abs(root_x[0]) >= float(thresholds["lethal_onset_min_root_x_px"]) and root_y[0] >= float(thresholds["lethal_onset_min_root_y_px"]) and root_y[0] > 0.0,
        "collapse_progression": legacy._path(pelvis) >= float(thresholds["root_path_min_px"]) and displacements[2] >= float(thresholds["collapse_start_displacement_min_px"]),
        "irreversible_death": irreversible and collapse_ratio >= float(thresholds["terminal_to_peak_ratio_min"]),
        "terminal_stability": terminal_residual <= float(thresholds["terminal_residual_max_px"]),
        "death_like_collapse": death_like,
        "death_vs_hit_or_neutral": displacements[7] >= float(thresholds["death_vs_hit_recovery_min_px"]) and displacements[7] >= legacy.HIT_H5_RECOVERY_DISPLACEMENT_PX * float(thresholds["death_vs_hit_separation_ratio_min"]) and target_hashes[7] != legacy.HIT_H5_RECOVERY_TARGET_HASH and target_hashes[7] != target_hashes[0],
        "marker_matches_measured_body_contact_transition": bool(transition["marker_matches_measured_body_contact_transition"]),
        "contact_state_transition_valid": bool(transition["contact_state_transition_valid"]),
        "final_pose_grounded_terminal": bool(transition["final_pose_grounded_terminal"]),
        "ground_reference_stable": bool(transition["ground_reference_stable"]),
        # A contact path is only continuous when the measured region/state
        # sequence remains the declared sequence as well as staying within
        # the per-step pixel budget.  This makes a disappearing/reappearing
        # contact fail closed even if no two adjacent frames share that body
        # region to compare.
        "contact_teleport_free": contact_continuity["gate"] and bool(transition["contact_state_transition_valid"]),
        "weapon_wrist_continuity": weapon["status"] == "DEATH_WEAPON_QA_PASSED",
        "angular_continuity": max(deltas, default=999.0) <= float(thresholds["joint_angle_step_max_deg"]),
        "angular_acceleration_continuity": max(accelerations, default=999.0) <= float(thresholds["angular_acceleration_max_deg_per_frame2"]),
        "nonfinite_and_gap_free": all(math.isfinite(value) for target in targets for joint in target["joints"].values() for value in legacy._xy(joint)),
        "collapse_visible_in_bbox": height_reduction >= float(thresholds["collapse_height_reduction_min"]),
        "non_loop_has_no_closing_requirement": spec["loop"] is False,
    }
    return {
        "phase_order": list(PHASES),
        "collapse": {
            "rest_pelvis": {"x": round(rest[0], 6), "y": round(rest[1], 6)},
            "pelvis_displacements_px": [round(value, 6) for value in displacements],
            "root_shift_x": [round(value, 6) for value in root_x],
            "root_shift_y": [round(value, 6) for value in root_y],
            "torso_rotation_deg": [round(value, 6) for value in torso],
            "terminal_residual_px": round(terminal_residual, 6),
            "terminal_to_peak_ratio": round(collapse_ratio, 6),
            "root_motion_is_secondary_to_measured_contact": True,
        },
        "metrics": {
            "root_path_length_px": round(legacy._path(pelvis), 6),
            "terminal_displacement_px": round(displacements[7], 6),
            "collapse_start_displacement_px": round(displacements[2], 6),
            "terminal_to_peak_ratio": round(collapse_ratio, 6),
            "terminal_residual_px": round(terminal_residual, 6),
            "max_joint_angle_step_deg": round(max(deltas, default=0.0), 6),
            "max_angular_acceleration_deg_per_frame2": round(max(accelerations, default=0.0), 6),
            "collapse_height_reduction": round(height_reduction, 6),
        },
        "contact": {"transition": dict(transition), "continuity": contact_continuity},
        "weapon": weapon,
        "hard_gates": gates,
        "status": "DEATH_TEMPORAL_QA_PASSED" if all(gates.values()) else "DEATH_TEMPORAL_QA_GAP",
    }


def observe(spec: Mapping[str, Any], context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
    outputs: list[Image.Image] = []
    details: list[Mapping[str, Any]] = []
    for index in range(int(spec["frame_count"])):
        image, rendered = render_source_only(context, prepared["targets"][index], list(Z_ORDER), prepared["presentation"])
        outputs.append(image)
        details.append(rendered)
    ground_reference, ground_metadata = _ground_reference(context, spec, details)
    states = _contact_contract(spec)["states"]
    body_records = [_body_observation(detail, ground_reference, spec["qa_profile"]["thresholds"]) for detail in details]
    foot_records = [_foot_observation(detail, ground_reference, spec["qa_profile"]["thresholds"], states[index]) for index, detail in enumerate(details)]
    transition = _contact_transition(spec, prepared, body_records, foot_records, ground_reference, ground_metadata)
    temporal = _temporal(spec, context, prepared, outputs, body_records, foot_records, transition)
    return {"outputs": outputs, "details": details, "ground_reference": ground_reference, "ground_metadata": ground_metadata, "body_records": body_records, "foot_records": foot_records, "transition": transition, "temporal": temporal}


def qa(spec: Mapping[str, Any], context: Mapping[str, Any], manifest: Mapping[str, Any], root) -> dict[str, Any]:
    prepared = prepare(spec, context)
    observation = observe(spec, context, prepared)
    records: list[dict[str, Any]] = []
    binding_by_frame = {int(item["frame"]): str(item["target_hash"]) for item in spec["key_pose_bindings"]}
    structural: dict[str, Any] = {}
    for index, item in enumerate(manifest["frames"]):
        target = prepared["targets"][index]
        details = observation["details"][index]
        pair, seam, integrity, aux = legacy._plan_and_structural(context, target, details, PHASES[index], prepared["plan"])
        duplicate = duplicate_body_measure(observation["outputs"][index])
        alpha = legacy.actual_alpha_safe_margin(observation["outputs"][index], float(spec["qa_profile"]["thresholds"]["alpha_safe_margin_px"]))
        foot = observation["foot_records"][index]
        body = observation["body_records"][index]
        frame_gates = {
            "source_hashes": all(value["source_part_rgba_sha256"] == context["part_hashes"][value["part"]] for value in details["transforms"]),
            "target_binding": legacy.target_digest(target) == item["target_hash"],
            "key_pose_binding": index not in binding_by_frame or binding_by_frame[index] == legacy.target_digest(target),
            "global_uniform_transform": all(value.get("nonuniform_scale") is False for value in details["transforms"]) and bool(spec["presentation_transform"]["frozen_before_render"]),
            "alpha_safe_margin": bool(alpha["gate"]),
            "structural_holes_zero": aux["coverage"]["structural_hole_pixels"] == 0,
            "layer_integrity": integrity["status"] == "LAYER_INTEGRITY_PASSED",
            "occlusion": pair["status"] == "OCCLUSION_QA_PASSED",
            "seam": seam["status"] == "SEAM_TOPOLOGY_PASSED",
            "retention": aux["retention"]["status"] == "RETENTION_OCCLUSION_PASSED",
            "support_state_matches_rendered": foot["state_matches_rendered"],
            "body_contact_region_measured": body["body_contact"] == bool(spec["adapter_parameters"]["contact_contract"]["states"][index].get("body_contact_regions")),
            "no_duplicate_body": duplicate["gate"],
            "front_facing": target.get("orientation") == "front",
            "finite_target": all(math.isfinite(value) for joint in target["joints"].values() for value in legacy._xy(joint)),
        }
        passed = all(frame_gates.values())
        record = {
            "index": index,
            "phase": PHASES[index],
            "target_hash": target["target_joint_sha256"],
            "output_rgba_sha256": item["rgba_sha256"],
            "hard_gates": frame_gates,
            "passed": passed,
            "support_contact_state": copy.deepcopy(spec["adapter_parameters"]["contact_contract"]["states"][index]),
            "body_ground_contact": body,
            "feet": foot,
            "alpha": alpha,
            "duplicate_body": duplicate,
            "integrity": integrity,
            "occlusion": pair,
            "seam": seam,
            "coverage": {key: value for key, value in aux["coverage"].items() if key not in {"hole_mask", "expected_mask"}},
            "retention": aux["retention"],
            "z_order": list(Z_ORDER),
            "target": target,
            "status": "DEATH_FRAME_PASSED" if passed else "DEATH_FRAME_GAP",
        }
        records.append(record)
        structural[PHASES[index]] = {"pair": pair, "seam": seam, "coverage": record["coverage"], "retention": record["retention"]}
    temporal = observation["temporal"]
    top_gates = {
        "frame_count_exact": len(records) == int(spec["frame_count"]) == 8,
        "non_loop": spec["loop"] is False,
        "all_frames": bool(records) and all(record["passed"] for record in records),
        "temporal_quality": temporal["status"] == "DEATH_TEMPORAL_QA_PASSED",
        "track_hash_bound": prepared["track_hash"] == legacy.motion_tracks_sha256(spec),
        "event_timeline_frozen": [(item["event_id"], item["frame"]) for item in spec.get("event_markers", [])] == [("lethal_impact_onset", 0), ("collapse_start", 2), ("ground_contact", 4), ("final_pose", 7)],
        "provenance_source_only": bool(spec["provenance"]["source_only_pixels"]) and spec["provenance"]["sam2_used"] is False and int(spec["provenance"]["comfyui_generation_jobs"]) == 0 and spec["provenance"]["diffusion_used"] is False,
        "package_frame_bindings": len({item["rgba_sha256"] for item in manifest["frames"]}) == len(manifest["frames"]) and all((root / item["path"]).is_file() for item in manifest["frames"]),
    }
    failures = [name for name, passed in top_gates.items() if not passed]
    failures.extend(f"frame_{record['index']}_{name}" for record in records for name, passed in record["hard_gates"].items() if not passed)
    failures.extend(f"temporal_{name}" for name, passed in temporal["hard_gates"].items() if not passed)
    qualified = all(top_gates.values()) and not failures
    package_metadata = {
        "phase_markers": list(spec.get("event_markers", [])),
        "motion_quality_layer": "generic.motion_tracks",
        "source_only_renderer": "source-affine-resample-and-alpha-composite",
        "contact_semantics": "measured-rendered-alpha-body-contact-with-frozen-D0-ground-reference",
        "support_contact_states": copy.deepcopy(spec["adapter_parameters"]["contact_contract"]["states"]),
    }
    return {
        "animation_id": spec["animation_id"],
        "decision": "QUALIFIED" if qualified else "FAILED",
        "status": "CUTOUT_ANIMATION_RUNTIME_V1_DEATH_ANIMATION_FRONT_V0151_TECHNICALLY_QUALIFIED" if qualified else "DEATH_ANIMATION_FRONT_V0151_STRUCTURAL_SEMANTIC_OR_TEMPORAL_GAP",
        "frames": records,
        "temporal": temporal,
        "body_mechanics": {"metrics": temporal["metrics"], "collapse": temporal["collapse"], "contact": temporal["contact"], "hard_gates": {key: value for key, value in temporal["hard_gates"].items() if key in {"marker_matches_measured_body_contact_transition", "contact_state_transition_valid", "final_pose_grounded_terminal", "ground_reference_stable", "death_like_collapse", "death_vs_hit_or_neutral", "terminal_stability"}}, "status": "DEATH_BODY_MECHANICS_QA_PASSED" if all(value for key, value in temporal["hard_gates"].items() if key in {"marker_matches_measured_body_contact_transition", "contact_state_transition_valid", "final_pose_grounded_terminal", "ground_reference_stable", "death_like_collapse", "death_vs_hit_or_neutral", "terminal_stability"}) else "DEATH_BODY_MECHANICS_GAP"},
        "foot_ground": {"frames": [record["feet"] for record in records], "contact": temporal["contact"], "ground_reference_y": round(float(observation["ground_reference"]), 6), "status": "DEATH_SUPPORT_STATE_QA_PASSED" if all(record["feet"]["state_matches_rendered"] for record in records) else "DEATH_SUPPORT_STATE_GAP"},
        "weapon": temporal["weapon"],
        "package_metadata": package_metadata,
        "provenance": {"source_sha256": context["source_sha256"], "part_hashes": context["part_hashes"], "mask_hashes": context["mask_hashes"], "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "source_only_pixels": True},
        "hard_gates": top_gates,
        "failures": failures,
        "structural": structural,
    }
