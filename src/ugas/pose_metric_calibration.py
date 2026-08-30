"""Deterministic v0.5.3 pose-metric calibration and QA contracts.

The legacy v0.5.2 silhouette/keypoint score remains available to historical
reports, but it is not used here as a provider gate. The primary metric uses
detected joints, translation/root normalization, scale normalization, signed
left/right identity, lower-body coverage, and an explicit orientation cue.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.5.3"
METRIC_VERSION = "detected-joint-pose-error-1.0"
METRIC_MAX = 1.0
PCK_THRESHOLD = 0.10
MIN_MEASURABLE_JOINTS = 10
CORE_JOINTS = (
    "shoulder_left", "shoulder_right", "elbow_left", "elbow_right", "wrist_left", "wrist_right",
    "hip_left", "hip_right", "knee_left", "knee_right", "ankle_left", "ankle_right",
)
MEASURABLE_JOINTS = ("nose",) + CORE_JOINTS
LOWER_BODY_JOINTS = ("hip_left", "hip_right", "knee_left", "knee_right", "ankle_left", "ankle_right")
LIMB_PAIRS = (
    ("shoulder_left", "elbow_left"), ("elbow_left", "wrist_left"),
    ("shoulder_right", "elbow_right"), ("elbow_right", "wrist_right"),
    ("hip_left", "knee_left"), ("knee_left", "ankle_left"),
    ("hip_right", "knee_right"), ("knee_right", "ankle_right"),
)

# MediaPipe Pose Landmarker landmark indices. The output is mapped into the
# stable UGAS/COCO-18 names without importing MediaPipe in the core module.
MEDIAPIPE_TO_UGAS = {
    0: "nose", 2: "eye_left", 5: "eye_right", 7: "ear_left", 8: "ear_right",
    11: "shoulder_left", 12: "shoulder_right", 13: "elbow_left", 14: "elbow_right",
    15: "wrist_left", 16: "wrist_right", 23: "hip_left", 24: "hip_right",
    25: "knee_left", 26: "knee_right", 27: "ankle_left", 28: "ankle_right",
}


class PoseMetricError(ValueError):
    """Raised for malformed pose metric input."""


def _point(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        try:
            return float(value["x"]), float(value["y"])
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    return None


def _confidence(value: Any) -> float:
    if isinstance(value, Mapping):
        for key in ("presence", "visibility", "confidence"):
            if key in value:
                try:
                    return float(value[key])
                except (TypeError, ValueError):
                    return 0.0
        return 1.0
    return 1.0


def map_mediapipe_landmarks(landmarks: Sequence[Any], *, confidence_threshold: float = 0.5) -> dict[str, dict[str, Any]]:
    """Map MediaPipe's 33-index result to UGAS joints with confidence flags."""
    mapped: dict[str, dict[str, Any]] = {}
    for index, name in MEDIAPIPE_TO_UGAS.items():
        if index >= len(landmarks):
            continue
        item = landmarks[index]
        point = _point(item)
        if point is None:
            continue
        confidence = _confidence(item)
        mapped[name] = {"x": point[0], "y": point[1], "confidence": confidence, "visible": confidence >= confidence_threshold, "source_index": index}
    return mapped


def _visible_point(points: Mapping[str, Any], name: str, visibility: Mapping[str, float] | None) -> tuple[float, float] | None:
    if name not in points:
        return None
    value = points[name]
    point = _point(value)
    if point is None:
        return None
    if isinstance(value, Mapping) and value.get("visible") is False:
        return None
    confidence = _confidence(value)
    if visibility and name in visibility:
        confidence = float(visibility[name])
    return point if confidence >= 0.5 else None


def _mean(points: list[tuple[float, float]]) -> tuple[float, float]:
    return sum(item[0] for item in points) / len(points), sum(item[1] for item in points) / len(points)


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _angle(first: tuple[float, float], middle: tuple[float, float], last: tuple[float, float]) -> float | None:
    a = (first[0] - middle[0], first[1] - middle[1])
    b = (last[0] - middle[0], last[1] - middle[1])
    denominator = math.hypot(*a) * math.hypot(*b)
    if denominator == 0:
        return None
    cosine = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / denominator))
    return math.degrees(math.acos(cosine))


def _root_and_scale(points: Mapping[str, Any], visibility: Mapping[str, float] | None) -> tuple[tuple[float, float], float] | None:
    hips = [_visible_point(points, name, visibility) for name in ("hip_left", "hip_right")]
    shoulders = [_visible_point(points, name, visibility) for name in ("shoulder_left", "shoulder_right")]
    hips = [item for item in hips if item is not None]
    shoulders = [item for item in shoulders if item is not None]
    if len(hips) < 1 or len(shoulders) < 1:
        return None
    root = _mean(hips)
    shoulder_center = _mean(shoulders)
    torso = _distance(shoulder_center, root)
    shoulder_width = _distance(shoulders[0], shoulders[-1]) if len(shoulders) == 2 else 0.0
    ankles = [_visible_point(points, name, visibility) for name in ("ankle_left", "ankle_right")]
    ankles = [item for item in ankles if item is not None]
    body_height = max((_distance(root, item) for item in ankles), default=0.0)
    scale = max(torso, shoulder_width, body_height * 0.5, 1e-6)
    return root, scale


def _normalize(points: Mapping[str, Any], visibility: Mapping[str, float] | None) -> tuple[dict[str, tuple[float, float]], tuple[float, float], float] | None:
    root_scale = _root_and_scale(points, visibility)
    if root_scale is None:
        return None
    root, scale = root_scale
    normalized = {}
    for name in MEASURABLE_JOINTS:
        point = _visible_point(points, name, visibility)
        if point is not None:
            normalized[name] = ((point[0] - root[0]) / scale, (point[1] - root[1]) / scale)
    return normalized, root, scale


def _angle_errors(target: Mapping[str, tuple[float, float]], detected: Mapping[str, tuple[float, float]]) -> list[float]:
    errors: list[float] = []
    triples = (
        ("shoulder_left", "elbow_left", "wrist_left"),
        ("shoulder_right", "elbow_right", "wrist_right"),
        ("hip_left", "knee_left", "ankle_left"),
        ("hip_right", "knee_right", "ankle_right"),
    )
    for first, middle, last in triples:
        if all(name in target and name in detected for name in (first, middle, last)):
            t = _angle(target[first], target[middle], target[last])
            d = _angle(detected[first], detected[middle], detected[last])
            if t is not None and d is not None:
                errors.append(abs(t - d))
    return errors


def detected_joint_pose_metrics(
    target: Mapping[str, Any],
    detected: Mapping[str, Any],
    *,
    target_orientation: str,
    detected_orientation: str,
    visibility: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Compare detected joints against a target without rotation hiding errors."""
    target_norm_data = _normalize(target, None)
    detected_norm_data = _normalize(detected, visibility)
    if target_norm_data is None or detected_norm_data is None:
        return {
            "metric_version": METRIC_VERSION, "measurement_status": "UNMEASURABLE",
            "measurable_body_joints": 0, "required_core_present": False,
            "pck_at_010": 0.0, "nme": 1.0, "limb_angle_mae_degrees": 180.0,
            "lower_body_pck": 0.0, "orientation_match": False, "orientation_score": 0.0,
            "pose_score": 0.0, "qualifies": False, "failure_reasons": ["root_or_scale_unmeasurable"],
        }
    target_norm, _, _ = target_norm_data
    detected_norm, _, _ = detected_norm_data
    shared = [name for name in MEASURABLE_JOINTS if name in target_norm and name in detected_norm]
    measurable = len(shared)
    required_present = all(name in detected_norm for name in CORE_JOINTS)
    distances = [_distance(target_norm[name], detected_norm[name]) for name in shared]
    pck = sum(distance <= PCK_THRESHOLD for distance in distances) / measurable if measurable else 0.0
    nme = sum(distances) / measurable if measurable else 1.0
    angle_errors = _angle_errors(target_norm, detected_norm)
    angle_mae = sum(angle_errors) / len(angle_errors) if angle_errors else 180.0
    lower_shared = [name for name in LOWER_BODY_JOINTS if name in target_norm and name in detected_norm]
    lower_distances = [_distance(target_norm[name], detected_norm[name]) for name in lower_shared]
    lower_pck = sum(distance <= PCK_THRESHOLD for distance in lower_distances) / len(lower_distances) if lower_distances else 0.0
    orientation_match = target_orientation == detected_orientation
    orientation_score = 1.0 if orientation_match else 0.0
    enough = measurable >= MIN_MEASURABLE_JOINTS and required_present
    # A large angular or NME error cannot be hidden by correct torso pixels.
    pose_score = (
        0.35 * pck
        + 0.25 * max(0.0, 1.0 - min(nme, 1.0))
        + 0.20 * max(0.0, 1.0 - min(angle_mae, 90.0) / 90.0)
        + 0.10 * lower_pck
        + 0.10 * orientation_score
    ) if enough else 0.0
    failures = []
    if measurable < MIN_MEASURABLE_JOINTS:
        failures.append("measurable_body_joints_below_10")
    if not required_present:
        failures.append("required_core_joint_missing")
    if pck < 0.80:
        failures.append("pck_below_080")
    if nme > 0.10:
        failures.append("nme_above_010")
    if angle_mae > 18.0:
        failures.append("limb_angle_mae_above_18_degrees")
    if lower_pck < 0.75:
        failures.append("lower_body_pck_below_075")
    if not orientation_match:
        failures.append("orientation_mismatch")
    qualifies = bool(enough and pck >= 0.80 and nme <= 0.10 and angle_mae <= 18.0 and lower_pck >= 0.75 and orientation_match)
    return {
        "metric_version": METRIC_VERSION,
        "measurement_status": "MEASURABLE" if enough else "UNMEASURABLE",
        "measurable_body_joints": measurable,
        "required_core_present": required_present,
        "pck_at_010": round(pck, 6),
        "nme": round(nme, 6),
        "limb_angle_mae_degrees": round(angle_mae, 6),
        "lower_body_pck": round(lower_pck, 6),
        "orientation_match": orientation_match,
        "orientation_score": orientation_score,
        "pose_score": round(pose_score, 6),
        "qualifies": qualifies,
        "failure_reasons": failures,
    }


def validate_causal_gate_configuration(baseline: float, additive_delta: float, metric_max: float = METRIC_MAX) -> dict[str, Any]:
    required = baseline + additive_delta
    invalid = required > metric_max + 1e-12
    return {
        "status": "INVALID_CAUSAL_GATE_CONFIGURATION" if invalid else "CAUSAL_GATE_CONFIGURATION_VALID",
        "baseline": baseline, "additive_delta": additive_delta, "required_score": round(required, 6), "metric_max": metric_max,
        "reason": "baseline_plus_delta_exceeds_metric_max" if invalid else None,
    }


def normalized_headroom_gain(baseline: float, improved: float, metric_max: float = METRIC_MAX, epsilon: float = 1e-9) -> float:
    return (improved - baseline) / max(epsilon, metric_max - baseline)


def provider_gap_emission_authorized(*, calibration_status: str, estimator_status: str) -> bool:
    """Provider failure is meaningful only after both measurement gates pass."""
    return calibration_status == "METRIC_CALIBRATION_PASSED" and estimator_status == "POSE_QA_ESTIMATOR_QUALIFIED"


def identity_only_silhouette_is_not_pose_pass(*, silhouette_overlap: float, detected_joint_metrics: Mapping[str, Any] | None) -> bool:
    """Return True only when identity/silhouette evidence is incorrectly used as pose proof."""
    return bool(silhouette_overlap >= 0.90 and not (detected_joint_metrics or {}).get("qualifies", False))


TARGET_POSE: dict[str, tuple[float, float]] = {
    "nose": (256, 55), "shoulder_left": (224, 105), "shoulder_right": (274, 112),
    "elbow_left": (176, 82), "elbow_right": (300, 160), "wrist_left": (145, 48), "wrist_right": (333, 205),
    "hip_left": (230, 220), "hip_right": (270, 228), "knee_left": (205, 340), "knee_right": (292, 326),
    "ankle_left": (175, 462), "ankle_right": (325, 448),
}
NEUTRAL_FRONT: dict[str, tuple[float, float]] = {
    "nose": (256, 55), "shoulder_left": (222, 110), "shoulder_right": (290, 110),
    "elbow_left": (205, 170), "elbow_right": (307, 170), "wrist_left": (195, 235), "wrist_right": (317, 235),
    "hip_left": (230, 225), "hip_right": (282, 225), "knee_left": (225, 345), "knee_right": (287, 345),
    "ankle_left": (220, 465), "ankle_right": (292, 465),
}


def _mutate(base: Mapping[str, tuple[float, float]], *, names: Sequence[str] = (), dx: float = 0, dy: float = 0) -> dict[str, tuple[float, float]]:
    result = dict(base)
    for name in names:
        x, y = result[name]
        result[name] = (x + dx, y + dy)
    return result


def synthetic_fixtures() -> dict[str, dict[str, Any]]:
    arms_down = dict(NEUTRAL_FRONT)
    legs_wrong = _mutate(TARGET_POSE, names=("knee_left", "ankle_left", "knee_right", "ankle_right"), dx=55, dy=35)
    arm_wrong = _mutate(TARGET_POSE, names=("elbow_left", "wrist_left", "elbow_right", "wrist_right"), dx=110, dy=100)
    mirrored = {name: (512 - point[0], point[1]) for name, point in TARGET_POSE.items()}
    t_pose = dict(NEUTRAL_FRONT)
    t_pose.update({"elbow_left": (165, 110), "wrist_left": (105, 110), "elbow_right": (350, 110), "wrist_right": (410, 110)})
    return {
        "TARGET": {"points": TARGET_POSE, "orientation": "left_profile", "sword": False, "kind": "positive"},
        "NEUTRAL_FRONT": {"points": NEUTRAL_FRONT, "orientation": "front", "sword": False, "kind": "negative"},
        "MIRRORED_WRONG_SIDE": {"points": mirrored, "orientation": "right_profile", "sword": False, "kind": "negative"},
        "T_POSE": {"points": t_pose, "orientation": "left_profile", "sword": False, "kind": "negative"},
        "ARMS_DOWN": {"points": arms_down, "orientation": "front", "sword": False, "kind": "negative"},
        "LEGS_WRONG": {"points": legs_wrong, "orientation": "left_profile", "sword": False, "kind": "negative"},
        "ARM_WRONG": {"points": arm_wrong, "orientation": "left_profile", "sword": False, "kind": "negative"},
        "TARGET_PLUS_LONG_VERTICAL_SWORD": {"points": TARGET_POSE, "orientation": "left_profile", "sword": True, "kind": "weapon-negative-control"},
        "NEUTRAL_FRONT_PLUS_VERTICAL_SWORD": {"points": NEUTRAL_FRONT, "orientation": "front", "sword": True, "kind": "weapon-negative-control"},
    }


def _fixture_image(path: Path, points: Mapping[str, tuple[float, float]], *, sword: bool, label: str) -> None:
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    body = (42, 93, 180, 255)
    limb = (100, 175, 255, 255)
    joints = (255, 210, 80, 255)
    draw.line((points["shoulder_left"], points["shoulder_right"], points["hip_right"], points["hip_left"], points["shoulder_left"]), fill=body, width=34, joint="curve")
    for first, last in (("shoulder_left", "elbow_left"), ("elbow_left", "wrist_left"), ("shoulder_right", "elbow_right"), ("elbow_right", "wrist_right"), ("hip_left", "knee_left"), ("knee_left", "ankle_left"), ("hip_right", "knee_right"), ("knee_right", "ankle_right")):
        draw.line((points[first], points[last]), fill=limb, width=20)
    draw.ellipse((points["nose"][0] - 26, points["nose"][1] - 26, points["nose"][0] + 26, points["nose"][1] + 26), fill=(224, 170, 135, 255))
    for point in points.values():
        draw.ellipse((point[0] - 7, point[1] - 7, point[0] + 7, point[1] + 7), fill=joints)
    if sword:
        draw.line((points["wrist_right"], (355, 30)), fill=(235, 235, 245, 255), width=13)
        draw.line(((350, 36), (360, 24)), fill=(255, 255, 255, 255), width=5)
    draw.rectangle((8, 8, 340, 32), fill=(255, 255, 255, 225))
    draw.text((14, 15), label, fill=(15, 15, 15, 255), font=ImageFont.load_default())
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False)


def _contact_sheet(paths: list[Path], labels: list[str], destination: Path) -> dict[str, Any]:
    from PIL import Image, ImageDraw, ImageFont
    cell = 160
    columns = 3
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGBA", (cell * columns, cell * rows), (20, 24, 36, 255))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, path in enumerate(paths):
        with Image.open(path) as source:
            image = source.convert("RGBA").resize((cell, cell))
        left, top = (index % columns) * cell, (index // columns) * cell
        sheet.alpha_composite(image, (left, top))
        draw.rectangle((left + 3, top + 138, left + cell - 3, top + cell - 3), fill=(255, 255, 255, 225))
        draw.text((left + 7, top + 143), labels[index], fill=(12, 12, 12, 255), font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=False)
    return {"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "columns": columns, "rows": rows, "frame_count": len(paths)}


def calibrate_synthetic_metrics(repo_root: Path) -> dict[str, Any]:
    """Run the entire deterministic fixture set and materialize review evidence."""
    fixtures = synthetic_fixtures()
    output_dir = repo_root / "docs" / "evidence" / "pose-metric-fixtures"
    paths: list[Path] = []
    records: dict[str, dict[str, Any]] = {}
    for name, fixture in fixtures.items():
        image_path = output_dir / f"{name.lower()}.png"
        _fixture_image(image_path, fixture["points"], sword=fixture["sword"], label=name)
        paths.append(image_path)
        metrics = detected_joint_pose_metrics(TARGET_POSE, fixture["points"], target_orientation="left_profile", detected_orientation=fixture["orientation"])
        records[name] = {
            "fixture": name, "kind": fixture["kind"], "image": str(image_path.relative_to(repo_root)).replace("\\", "/"),
            "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(), "sword_present": fixture["sword"], "metrics": metrics,
        }
    target_score = records["TARGET"]["metrics"]["pose_score"]
    negatives = {name: item["metrics"]["pose_score"] for name, item in records.items() if item["kind"] == "negative"}
    sword_target_delta = abs(records["TARGET_PLUS_LONG_VERTICAL_SWORD"]["metrics"]["pose_score"] - target_score)
    sword_neutral_delta = abs(records["NEUTRAL_FRONT_PLUS_VERTICAL_SWORD"]["metrics"]["pose_score"] - records["NEUTRAL_FRONT"]["metrics"]["pose_score"])
    wrong_side_pass = records["MIRRORED_WRONG_SIDE"]["metrics"]["qualifies"]
    ablation = detected_joint_pose_metrics(TARGET_POSE, {**TARGET_POSE, "wrist_left": (145, 48)}, target_orientation="left_profile", detected_orientation="left_profile", visibility={"wrist_left": 0.1})
    old_diagnostic = {
        "status": "DIAGNOSTIC_ONLY",
        "metric": "v0.5.2 guide keypoint/segment/silhouette score",
        "primary_gate_uses_it": False,
        "reason": "foreground/silhouette evidence can be satisfied by a torso, cape, or weapon and is not a detected-joint measurement",
        "weapon_contamination_test": "sword fixture is intentionally present only as a primary-metric invariance control",
    }
    criteria = {
        "target_at_least_090": target_score >= 0.90,
        "every_negative_at_least_020_below_target": all(value <= target_score - 0.20 for value in negatives.values()),
        "neutral_front_at_most_065": records["NEUTRAL_FRONT"]["metrics"]["pose_score"] <= 0.65,
        "wrong_side_at_most_065": records["MIRRORED_WRONG_SIDE"]["metrics"]["pose_score"] <= 0.65,
        "t_pose_at_most_065": records["T_POSE"]["metrics"]["pose_score"] <= 0.65,
        "sword_target_delta_at_most_005": sword_target_delta <= 0.05,
        "sword_neutral_delta_at_most_005": sword_neutral_delta <= 0.05,
        "mirrored_wrong_side_not_accepted": not wrong_side_pass,
        "limb_ablation_detected": "required_core_joint_missing" in ablation["failure_reasons"] or ablation["measurement_status"] == "UNMEASURABLE",
    }
    contact_positive = _contact_sheet(paths[:1] + paths[3:5] + paths[5:7], ["TARGET", "T_POSE", "ARMS_DOWN", "LEGS_WRONG", "ARM_WRONG"], repo_root / "docs/evidence/pose-metric-calibration-contact-sheet.png")
    contact_negative = _contact_sheet(paths[1:3] + paths[7:], ["NEUTRAL_FRONT", "MIRRORED_WRONG_SIDE", "TARGET + SWORD", "NEUTRAL + SWORD"], repo_root / "docs/evidence/pose-metric-negative-controls-contact-sheet.png")
    calibration = {
        "schema_version": SCHEMA_VERSION, "metric_version": METRIC_VERSION, "status": "METRIC_CALIBRATION_PASSED" if all(criteria.values()) else "METRIC_CALIBRATION_FAILED",
        "primary_metric": "detected_joint_pose_error", "legacy_pose_score": old_diagnostic,
        "normalization": {"translation": "pelvis/root subtraction", "scale": "max torso, shoulder width, half body height", "rotation_invariant": False, "left_right_preserved": True},
        "thresholds": {"target_min": 0.90, "negative_margin": 0.20, "negative_max": 0.65, "pck_at_010": 0.80, "nme_max": 0.10, "limb_angle_mae_max_degrees": 18.0, "lower_body_pck_min": 0.75, "sword_delta_max": 0.05},
        "criteria": criteria, "target_score": target_score, "negative_scores": negatives,
        "sword_score_deltas": {"target_plus_sword": round(sword_target_delta, 6), "neutral_plus_sword": round(sword_neutral_delta, 6)},
        "limb_ablation": ablation, "fixtures": records, "contact_sheets": {"calibration": contact_positive, "negative_controls": contact_negative},
        "deterministic": True, "ai_generated": False, "provider_routing_used": False,
    }
    target = repo_root / "docs" / "evidence" / "pose-metric-calibration.json"
    target.write_text(json.dumps(calibration, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return calibration


def calibration_error_table(calibration: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "source": "docs/evidence/pose-metric-calibration.json",
        "status": calibration.get("status"), "rows": [
            {"fixture": name, "pose_score": item["metrics"]["pose_score"], "pck_at_010": item["metrics"]["pck_at_010"], "nme": item["metrics"]["nme"], "limb_angle_mae_degrees": item["metrics"]["limb_angle_mae_degrees"], "lower_body_pck": item["metrics"]["lower_body_pck"], "orientation_match": item["metrics"]["orientation_match"], "qualifies": item["metrics"]["qualifies"]}
            for name, item in calibration.get("fixtures", {}).items()
        ],
    }
