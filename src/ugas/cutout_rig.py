"""Deterministic cutout-rig contracts for UGAS v0.7.1.

This module deliberately contains no diffusion, ComfyUI, SAM or MediaPipe
imports.  The isolated runtime adapter supplies masks and source landmarks;
the functions here validate/hash them and render only pixels taken from the
canonical R4 RGBA source.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter


SCHEMA_VERSION = "0.7.1"
PROVIDER_ID = "deterministic-cutout-rig-2d"
CAPABILITY_ID = "pose_character_front_2d"
RENDERER_VERSION = "cutout-rig-renderer-1.0.0"
MASK_MIN_FOREGROUND_PURITY = 0.98
MASK_ALPHA_FOREGROUND_THRESHOLD = 64
MASK_MIN_UNION_COVERAGE = 0.95
MASK_MAX_UNASSIGNED = 0.05
MASK_MAX_UNRESOLVED_OVERLAP = 0.03
PREFERRED_SCALE = 1.0
MIN_MEMBER_SCALE = 0.92
MAX_MEMBER_SCALE = 1.08
MIN_SAFE_MARGIN = 24
MAX_GROSS_OVERLAP_FRACTION = 0.01
JOINT_BLEND_RADIUS = 3
REQUIRED_JOINTS = (
    "shoulder_left", "shoulder_right", "elbow_left", "elbow_right",
    "wrist_left", "wrist_right", "hip_left", "hip_right", "knee_left",
    "knee_right", "ankle_left", "ankle_right",
)
COCO18_AUXILIARY = ("nose",)
PART_NAMES = (
    "head", "torso_pelvis", "left_upper_arm", "left_forearm_hand",
    "right_upper_arm", "right_forearm_hand", "left_thigh", "left_shin_foot",
    "right_thigh", "right_shin_foot", "sword",
)
PART_COLORS = {
    "head": (255, 91, 91, 230), "torso_pelvis": (255, 179, 71, 230),
    "left_upper_arm": (255, 240, 71, 230), "left_forearm_hand": (155, 230, 71, 230),
    "right_upper_arm": (71, 230, 155, 230), "right_forearm_hand": (71, 205, 255, 230),
    "left_thigh": (91, 124, 255, 230), "left_shin_foot": (155, 91, 255, 230),
    "right_thigh": (230, 91, 255, 230), "right_shin_foot": (255, 91, 179, 230),
    "sword": (230, 230, 230, 230),
}
PART_SPECS = {
    "head": {"parent": "torso_pelvis", "source_joints": ("nose", "neck"), "pivot_joint": "neck", "z_group": 40},
    "torso_pelvis": {"parent": "root", "source_joints": ("shoulder_center", "pelvis"), "pivot_joint": "pelvis", "z_group": 20},
    "left_upper_arm": {"parent": "torso_pelvis", "source_joints": ("shoulder_left", "elbow_left"), "pivot_joint": "shoulder_left", "z_group": 30},
    "left_forearm_hand": {"parent": "left_upper_arm", "source_joints": ("elbow_left", "wrist_left"), "pivot_joint": "elbow_left", "z_group": 31},
    "right_upper_arm": {"parent": "torso_pelvis", "source_joints": ("shoulder_right", "elbow_right"), "pivot_joint": "shoulder_right", "z_group": 30},
    "right_forearm_hand": {"parent": "right_upper_arm", "source_joints": ("elbow_right", "wrist_right"), "pivot_joint": "elbow_right", "z_group": 31},
    "left_thigh": {"parent": "torso_pelvis", "source_joints": ("hip_left", "knee_left"), "pivot_joint": "hip_left", "z_group": 10},
    "left_shin_foot": {"parent": "left_thigh", "source_joints": ("knee_left", "ankle_left"), "pivot_joint": "knee_left", "z_group": 11},
    "right_thigh": {"parent": "torso_pelvis", "source_joints": ("hip_right", "knee_right"), "pivot_joint": "hip_right", "z_group": 10},
    "right_shin_foot": {"parent": "right_thigh", "source_joints": ("knee_right", "ankle_right"), "pivot_joint": "knee_right", "z_group": 11},
    "sword": {"parent": "right_forearm_hand", "source_joints": ("wrist_right", "weapon_tip"), "pivot_joint": "wrist_right", "z_group": 50},
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


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


def source_skeleton(landmarks: Mapping[str, Any], width: int, height: int) -> dict[str, Any]:
    """Convert qualified normalized MediaPipe output into pixel coordinates."""
    points: dict[str, dict[str, Any]] = {}
    for name, value in landmarks.items():
        point = _point(value)
        if point is None or value.get("visible") is False:
            continue
        points[name] = {
            "x": round(point[0] * width, 4), "y": round(point[1] * height, 4),
            "normalized_x": round(point[0], 8), "normalized_y": round(point[1], 8),
            "confidence": round(float(value.get("confidence", 0.0)), 6),
            "visibility": round(float(value.get("visibility", value.get("confidence", 0.0))), 6),
            "presence": round(float(value.get("presence", value.get("confidence", 0.0))), 6),
            "source_index": value.get("source_index"), "visible": True,
        }
    required_present = [name for name in REQUIRED_JOINTS if name in points]
    nose_present = "nose" in points
    return {
        "schema_version": SCHEMA_VERSION, "joint_schema": "UGAS-COCO-18-compatible",
        "coordinate_space": {"width": width, "height": height, "origin": "top-left", "normalized": "x/width,y/height"},
        "joints": points, "required_joints": list(REQUIRED_JOINTS),
        "required_present": required_present, "required_count": len(required_present),
        "auxiliary_present": list(COCO18_AUXILIARY if nose_present else ()),
        "enough_joints": len(required_present) == len(REQUIRED_JOINTS) and nose_present,
        "policy": "MediaPipe Pose Landmarker full v0.10.35; same qualified visibility policy as v0.5.4-v0.6.x",
        "status": "SOURCE_SKELETON_QUALIFIED" if len(required_present) == len(REQUIRED_JOINTS) and nose_present else "CUTOUT_RIG_SOURCE_SKELETON_GAP",
    }


def skeleton_point(skeleton: Mapping[str, Any], name: str) -> tuple[float, float]:
    if name == "pelvis":
        left = skeleton_point(skeleton, "hip_left")
        right = skeleton_point(skeleton, "hip_right")
        return ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
    if name == "shoulder_center":
        left = skeleton_point(skeleton, "shoulder_left")
        right = skeleton_point(skeleton, "shoulder_right")
        return ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
    if name in {"neck", "weapon_tip"}:
        value = skeleton.get(name)
        if value is None:
            raise KeyError(name)
        point = _point(value)
        if point is None:
            raise KeyError(name)
        return point
    value = (skeleton.get("joints") or {}).get(name, skeleton.get(name))
    point = _point(value)
    if point is None:
        raise KeyError(name)
    return point


def map_guide_sides(raw_points: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """Map image-side labels to anatomical sides without assuming symmetry."""
    result: dict[str, dict[str, float]] = {}
    mapping = {"anatomical_left": "guide_right", "anatomical_right": "guide_left"}
    for name, value in raw_points.items():
        if name.endswith("_left") or name.endswith("_right"):
            continue
        result[name] = {"x": float(value["x"]), "y": float(value["y"])}
    for base in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle"):
        result[f"{base}_left"] = {"x": float(raw_points[f"{base}_right"]["x"]), "y": float(raw_points[f"{base}_right"]["y"])}
        result[f"{base}_right"] = {"x": float(raw_points[f"{base}_left"]["x"]), "y": float(raw_points[f"{base}_left"]["y"])}
    return result, mapping


def component_gate(component_sizes: Iterable[int], max_meaningful_components: int) -> dict[str, Any]:
    """Measure meaningful connected components with the v0.7.1 policy."""
    sizes = sorted((int(size) for size in component_sizes if int(size) > 0), reverse=True)
    primary = sizes[0] if sizes else 0
    threshold = max(16, int(primary * 0.0025))
    meaningful = sum(size >= threshold for size in sizes)
    return {"primary_area": primary, "meaningful_component_threshold": threshold, "meaningful_component_count": meaningful, "max_meaningful_components": int(max_meaningful_components), "passed": meaningful <= int(max_meaningful_components)}


def _alpha_bbox(alpha: Image.Image) -> tuple[int, int, int, int]:
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("canonical source has no alpha foreground")
    return bbox


def _clamp_box(box: Sequence[float], width: int, height: int) -> list[float]:
    left, top, right, bottom = box
    return [round(max(0.0, min(float(width), left)), 4), round(max(0.0, min(float(height), top)), 4), round(max(0.0, min(float(width), right)), 4), round(max(0.0, min(float(height), bottom)), 4)]


def _corridor_box(first: tuple[float, float], second: tuple[float, float], width: int, height: int, factor: float = 0.42, padding: float = 8.0) -> list[float]:
    length = max(1.0, math.dist(first, second))
    half_width = max(7.0, length * factor / 2.0 + padding)
    return _clamp_box((min(first[0], second[0]) - half_width, min(first[1], second[1]) - half_width, max(first[0], second[0]) + half_width, max(first[1], second[1]) + half_width), width, height)


def _background_negative(alpha: Image.Image, box: Sequence[float]) -> list[float]:
    width, height = alpha.size
    candidates = [(4, 4), (width - 5, 4), (4, height - 5), (width - 5, height - 5), (width / 2, 4), (4, height / 2), (width - 5, height / 2)]
    left, top, right, bottom = box
    for x, y in candidates:
        if not (left <= x <= right and top <= y <= bottom) and alpha.getpixel((max(0, min(width - 1, int(x))), max(0, min(height - 1, int(y))))) == 0:
            return [round(float(x), 4), round(float(y), 4)]
    # Deterministic radial search when the canvas corners are occupied.
    for radius in range(8, max(width, height), 8):
        for x, y in ((width / 2 + radius, height / 2), (width / 2 - radius, height / 2), (width / 2, height / 2 + radius), (width / 2, height / 2 - radius)):
            ix, iy = int(max(0, min(width - 1, x))), int(max(0, min(height - 1, y)))
            if not (left <= x <= right and top <= y <= bottom) and alpha.getpixel((ix, iy)) == 0:
                return [round(float(x), 4), round(float(y), 4)]
    return [0.0, 0.0]


def build_part_prompts(skeleton: Mapping[str, Any], alpha: Image.Image, weapon_tip: tuple[float, float]) -> dict[str, Any]:
    """Build all SAM prompts from geometry and alpha; no click/user input."""
    width, height = alpha.size
    points = {name: skeleton_point(skeleton, name) for name in REQUIRED_JOINTS}
    neck = skeleton.get("neck") or {"x": skeleton_point(skeleton, "shoulder_center")[0], "y": skeleton_point(skeleton, "shoulder_center")[1] - math.dist(skeleton_point(skeleton, "shoulder_center"), skeleton_point(skeleton, "pelvis")) * 0.28}
    neck_point = _point(neck)
    if neck_point is None:
        neck_point = skeleton_point(skeleton, "shoulder_center")
    points["neck"] = neck_point
    points["nose"] = skeleton_point(skeleton, "nose")
    points["pelvis"] = skeleton_point(skeleton, "pelvis")
    points["shoulder_center"] = skeleton_point(skeleton, "shoulder_center")
    points["weapon_tip"] = weapon_tip
    alpha_bbox = _alpha_bbox(alpha)
    specs: dict[str, dict[str, Any]] = {}
    for name in PART_NAMES:
        if name == "head":
            center = points["nose"]
            radius = max(20.0, math.dist(center, points["neck"]) * 1.9)
            box = _clamp_box((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), width, height)
            positive = center
        elif name == "torso_pelvis":
            first, second = points["shoulder_center"], points["pelvis"]
            box = _corridor_box(first, second, width, height, factor=0.9, padding=14)
            positive = ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)
        elif name == "sword":
            first, second = points["wrist_right"], weapon_tip
            box = _corridor_box(first, second, width, height, factor=0.65, padding=12)
            positive = ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)
        else:
            first_name, second_name = PART_SPECS[name]["source_joints"]
            first, second = points[first_name], points[second_name]
            box = _corridor_box(first, second, width, height)
            positive = ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)
        px, py = int(max(0, min(width - 1, round(positive[0])))), int(max(0, min(height - 1, round(positive[1]))))
        if alpha.getpixel((px, py)) == 0:
            # Search deterministically around the midpoint for an alpha interior.
            found = None
            for radius in range(1, 32):
                for dx, dy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius), (radius, radius), (-radius, -radius)):
                    ix, iy = max(0, min(width - 1, px + dx)), max(0, min(height - 1, py + dy))
                    if alpha.getpixel((ix, iy)) > 0:
                        found = (ix, iy)
                        break
                if found:
                    break
            if found:
                positive = (float(found[0]), float(found[1]))
        specs[name] = {
            "part": name, "prompt_policy": "auto_geometry_midpoint_alpha_interior_box_corridor_background_negative",
            "positive_points": [[round(positive[0], 4), round(positive[1], 4)]],
            "positive_labels": [1], "negative_points": [_background_negative(alpha, box)], "negative_labels": [0],
            "box_xyxy": box, "expected_corridor": box, "alpha_bbox": list(alpha_bbox),
            "source_joints": list(PART_SPECS[name]["source_joints"]), "manual_click": False,
        }
    payload = {"schema_version": SCHEMA_VERSION, "prompt_policy": "deterministic; derived solely from R4 alpha and source skeleton; no human clicks", "source_alpha_sha256": sha256_bytes(alpha.tobytes()), "parts": specs}
    payload["prompts_sha256"] = sha256_bytes(canonical_json(payload).encode("utf-8"))
    return payload


def mask_stats(mask: Image.Image, alpha: Image.Image, expected_box: Sequence[float], pivot: tuple[float, float] | None = None) -> dict[str, Any]:
    mask = mask.convert("L")
    binary = mask.point(lambda value: 255 if value > 127 else 0)
    alpha_binary = alpha.point(lambda value: 255 if value > 0 else 0)
    mask_count = sum(1 for value in binary.getdata() if value > 0)
    alpha_count = sum(1 for value in alpha_binary.getdata() if value > 0)
    outside = ImageChops.subtract(binary, alpha_binary)
    outside_count = sum(1 for value in outside.getdata() if value > 0)
    bbox = binary.getbbox()
    expected = (int(expected_box[0]), int(expected_box[1]), int(expected_box[2]), int(expected_box[3]))
    bbox_intersects = bool(bbox and not (bbox[2] <= expected[0] or bbox[0] >= expected[2] or bbox[3] <= expected[1] or bbox[1] >= expected[3]))
    pivot_in_mask = None
    pivot_distance = None
    if pivot is not None:
        x, y = int(round(pivot[0])), int(round(pivot[1]))
        pivot_in_mask = 0 <= x < mask.width and 0 <= y < mask.height and binary.getpixel((x, y)) > 0
        if bbox:
            pivot_distance = round(math.sqrt(max(0, bbox[0] - x, x - bbox[2] + 1) ** 2 + max(0, bbox[1] - y, y - bbox[3] + 1) ** 2), 6)
    # Connected-component sanity is intentionally conservative and deterministic.
    components = _component_count(binary)
    return {
        "mask_pixels": mask_count, "source_alpha_pixels": alpha_count,
        "foreground_purity": round(1.0 - outside_count / max(1, mask_count), 6),
        "outside_source_alpha_pixels": outside_count, "bbox": list(bbox) if bbox else None,
        "expected_corridor_intersects": bbox_intersects, "pivot_in_mask": pivot_in_mask, "pivot_distance_to_bbox": pivot_distance,
        "connected_components": components, "nonempty": mask_count > 0,
    }


def _component_count(image: Image.Image) -> int:
    return len(_component_sizes(image))


def _component_sizes(image: Image.Image) -> list[int]:
    """Return 8-connected foreground component sizes in deterministic order."""
    width, height = image.size
    pixels = image.load()
    seen: set[tuple[int, int]] = set()
    sizes: list[int] = []
    for y in range(height):
        for x in range(width):
            if pixels[x, y] == 0 or (x, y) in seen:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            size = 0
            while stack:
                cx, cy = stack.pop()
                size += 1
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1), (cx - 1, cy - 1), (cx + 1, cy - 1), (cx - 1, cy + 1), (cx + 1, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height and pixels[nx, ny] > 0 and (nx, ny) not in seen:
                        seen.add((nx, ny)); stack.append((nx, ny))
            sizes.append(size)
    return sizes


def mask_union_stats(masks: Iterable[Image.Image], alpha: Image.Image) -> dict[str, Any]:
    masks = [item.convert("L").point(lambda value: 255 if value > 127 else 0) for item in masks]
    union = Image.new("L", alpha.size, 0)
    overlap = Image.new("L", alpha.size, 0)
    count = [0] * (alpha.width * alpha.height)
    for mask in masks:
        union = ImageChops.lighter(union, mask)
        for index, value in enumerate(mask.getdata()):
            if value > 0:
                count[index] += 1
    for index, value in enumerate(count):
        if value > 1:
            overlap.putpixel((index % alpha.width, index // alpha.width), 255)
    strict_alpha_count = sum(1 for value in alpha.getdata() if value > 0)
    alpha_count = sum(1 for value in alpha.getdata() if value > MASK_ALPHA_FOREGROUND_THRESHOLD)
    union_in_alpha = ImageChops.multiply(union, alpha.point(lambda value: 255 if value > MASK_ALPHA_FOREGROUND_THRESHOLD else 0))
    union_count = sum(1 for value in union_in_alpha.getdata() if value > 0)
    overlap_count = sum(1 for value in overlap.getdata() if value > 0)
    unassigned = max(0, alpha_count - union_count)
    return {
        "source_alpha_pixels": alpha_count, "strict_source_alpha_pixels": strict_alpha_count, "alpha_foreground_threshold": MASK_ALPHA_FOREGROUND_THRESHOLD, "union_foreground_pixels": union_count,
        "union_coverage": round(union_count / max(1, alpha_count), 6),
        "unassigned_fraction": round(unassigned / max(1, alpha_count), 6),
        "overlap_pixels": overlap_count, "unresolved_overlap_fraction": round(overlap_count / max(1, alpha_count), 6),
        "union_mask": union, "overlap_mask": overlap,
    }


def _vector(first: tuple[float, float], second: tuple[float, float]) -> tuple[float, float]:
    return second[0] - first[0], second[1] - first[1]


def _angle(vector: tuple[float, float]) -> float:
    return math.atan2(vector[1], vector[0])


def _target_point(target: Mapping[str, Any], name: str) -> tuple[float, float]:
    if name == "pelvis":
        left, right = _target_point(target, "hip_left"), _target_point(target, "hip_right")
        return ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
    if name == "shoulder_center":
        left, right = _target_point(target, "shoulder_left"), _target_point(target, "shoulder_right")
        return ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
    point = _point((target.get("joints") or {}).get(name, target.get(name)))
    if point is None:
        raise KeyError(name)
    return point


def transform_parameters(source: Mapping[str, Any], target: Mapping[str, Any], part: str) -> dict[str, Any]:
    first_name, second_name = PART_SPECS[part]["source_joints"]
    source_first = skeleton_point(source, first_name)
    source_second = skeleton_point(source, second_name)
    target_first = _target_point(target, first_name)
    target_second = _target_point(target, second_name)
    source_length = math.dist(source_first, source_second)
    target_length = math.dist(target_first, target_second)
    scale = target_length / max(1e-6, source_length)
    source_angle = _angle(_vector(source_first, source_second))
    target_angle = _angle(_vector(target_first, target_second))
    theta = target_angle - source_angle
    cos_value, sin_value = math.cos(theta), math.sin(theta)
    matrix = [
        [round(scale * cos_value, 9), round(-scale * sin_value, 9), round(target_first[0] - scale * cos_value * source_first[0] + scale * sin_value * source_first[1], 9)],
        [round(scale * sin_value, 9), round(scale * cos_value, 9), round(target_first[1] - scale * sin_value * source_first[0] - scale * cos_value * source_first[1], 9)],
    ]
    forward_pivot = (matrix[0][0] * source_first[0] + matrix[0][1] * source_first[1] + matrix[0][2], matrix[1][0] * source_first[0] + matrix[1][1] * source_first[1] + matrix[1][2])
    forward_end = (matrix[0][0] * source_second[0] + matrix[0][1] * source_second[1] + matrix[0][2], matrix[1][0] * source_second[0] + matrix[1][1] * source_second[1] + matrix[1][2])
    pivot_error = math.dist(forward_pivot, target_first)
    end_error = math.dist(forward_end, target_second)
    transformed_vector = _vector(forward_pivot, forward_end)
    angle_error = abs(math.degrees(_angle(transformed_vector) - target_angle))
    while angle_error > 180.0:
        angle_error -= 360.0
    bone_drift = abs(math.dist(forward_pivot, forward_end) / max(1e-6, target_length) - 1.0)
    return {
        "source_pivot": list(source_first), "target_pivot": list(target_first),
        "source_end": list(source_second), "target_end": list(target_second),
        "source_bone_length": round(source_length, 6), "target_bone_length": round(target_length, 6),
        "uniform_scale": round(scale, 6),
        "rotation_delta_degrees": round(math.degrees(source_angle - target_angle), 6),
        "forward_affine_matrix": matrix,
        "forward_source_pivot": [round(forward_pivot[0], 6), round(forward_pivot[1], 6)],
        "forward_source_end": [round(forward_end[0], 6), round(forward_end[1], 6)],
        "forward_pivot_error_px": round(pivot_error, 6),
        "forward_end_error_px": round(end_error, 6),
        "forward_angle_error_degrees": round(abs(angle_error), 6),
        "forward_bone_length_drift_fraction": round(bone_drift, 6),
        "nonuniform_scale": False,
        "scale_gate": MIN_MEMBER_SCALE <= scale <= MAX_MEMBER_SCALE,
    }


def transform_metric_gates(transform: Mapping[str, Any]) -> dict[str, bool]:
    """Evaluate forward affine evidence against the immutable v0.7.1 limits."""
    scale = float(transform.get("uniform_scale", 0.0))
    return {
        "pivot_max": float(transform.get("forward_pivot_error_px", 999.0)) <= 6.0,
        "angle_median": float(transform.get("forward_angle_error_degrees", 999.0)) <= 3.0,
        "bone_drift": float(transform.get("forward_bone_length_drift_fraction", 999.0)) <= 0.08,
        "bounded_scale": MIN_MEMBER_SCALE <= scale <= MAX_MEMBER_SCALE,
    }


def render_part(part_image: Image.Image, source_pivot: tuple[float, float], target_pivot: tuple[float, float], source_end: tuple[float, float], target_end: tuple[float, float], canvas_size: tuple[int, int]) -> Image.Image:
    """Apply a bounded similarity transform using only Pillow resampling."""
    source_vector = _vector(source_pivot, source_end)
    target_vector = _vector(target_pivot, target_end)
    source_length = max(1e-6, math.hypot(*source_vector))
    target_length = math.hypot(*target_vector)
    scale = target_length / source_length
    theta = _angle(target_vector) - _angle(source_vector)
    cos_value, sin_value = math.cos(theta), math.sin(theta)
    # Inverse map from output to input for Pillow's y-down image coordinates.
    a, b = cos_value / scale, sin_value / scale
    d, e = -sin_value / scale, cos_value / scale
    c = source_pivot[0] - a * target_pivot[0] - b * target_pivot[1]
    f = source_pivot[1] - d * target_pivot[0] - e * target_pivot[1]
    return part_image.transform(canvas_size, Image.Transform.AFFINE, (a, b, c, d, e, f), resample=Image.Resampling.BICUBIC)


def render_part_layers(parts: Mapping[str, Image.Image], source: Mapping[str, Any], target: Mapping[str, Any], canvas_size: tuple[int, int]) -> tuple[list[Image.Image], list[dict[str, Any]]]:
    layers: list[Image.Image] = []
    transforms: list[dict[str, Any]] = []
    for name in sorted(PART_NAMES, key=lambda item: (PART_SPECS[item]["z_group"], item)):
        image = parts[name]
        params = transform_parameters(source, target, name)
        transformed = render_part(image, tuple(params["source_pivot"]), tuple(params["target_pivot"]), tuple(params["source_end"]), tuple(params["target_end"]), canvas_size)
        layers.append(transformed)
        transforms.append({"part": name, **params, "z_group": PART_SPECS[name]["z_group"]})
    return layers, transforms


def compose_rig(parts: Mapping[str, Image.Image], source: Mapping[str, Any], target: Mapping[str, Any], canvas_size: tuple[int, int]) -> tuple[Image.Image, list[dict[str, Any]]]:
    output = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    layers, transforms = render_part_layers(parts, source, target, canvas_size)
    for transformed in layers:
        output.alpha_composite(transformed)
    return output, transforms


def image_metrics(source: Image.Image, rendered: Image.Image) -> dict[str, Any]:
    source = source.convert("RGBA")
    rendered = rendered.convert("RGBA")
    alpha_a = source.getchannel("A").point(lambda value: 255 if value > 0 else 0)
    alpha_b = rendered.getchannel("A").point(lambda value: 255 if value > 0 else 0)
    intersection = ImageChops.multiply(alpha_a, alpha_b)
    union = ImageChops.lighter(alpha_a, alpha_b)
    inter = sum(1 for value in intersection.getdata() if value > 0)
    union_count = sum(1 for value in union.getdata() if value > 0)
    diff = ImageChops.difference(source, rendered)
    diff_rgb = diff.convert("RGB")
    visible = source.getchannel("A")
    visible_values = [sum(pixel) / 3.0 for pixel, alpha in zip(diff_rgb.getdata(), visible.getdata()) if alpha > 0]
    mae = sum(visible_values) / max(1, len(visible_values))
    source_bbox, rendered_bbox = alpha_a.getbbox(), alpha_b.getbbox()
    drift = 0.0
    if source_bbox and rendered_bbox:
        drift = max(abs(a - b) for a, b in zip(source_bbox, rendered_bbox))
    return {"alpha_iou": round(inter / max(1, union_count), 6), "rgb_mae": round(mae, 6), "bbox_drift_px": round(float(drift), 6), "source_bbox": list(source_bbox) if source_bbox else None, "rendered_bbox": list(rendered_bbox) if rendered_bbox else None, "diff": diff}


def draw_part_contact_sheet(source: Image.Image, part_images: Mapping[str, Image.Image], destination: Path, *, overlay: bool = False) -> None:
    cell = 192
    columns = 3
    rows = (len(PART_NAMES) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * cell, rows * cell), (32, 36, 48, 255))
    draw = ImageDraw.Draw(sheet)
    for index, name in enumerate(PART_NAMES):
        image = part_images[name].convert("RGBA")
        if overlay:
            layer = Image.new("RGBA", image.size, PART_COLORS[name])
            image = Image.composite(layer, Image.new("RGBA", image.size, (0, 0, 0, 0)), image.getchannel("A"))
        image.thumbnail((cell - 8, cell - 28), Image.Resampling.LANCZOS)
        left, top = (index % columns) * cell, (index // columns) * cell
        sheet.alpha_composite(image, (left + (cell - image.width) // 2, top + 4))
        draw.rectangle((left + 4, top + cell - 23, left + cell - 4, top + cell - 4), fill=(255, 255, 255, 225))
        draw.text((left + 8, top + cell - 19), name, fill=(10, 10, 10, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=False)


def render_hierarchy_diagram(destination: Path) -> None:
    image = Image.new("RGBA", (960, 640), (20, 24, 36, 255))
    draw = ImageDraw.Draw(image)
    nodes = {
        "root/pelvis": (480, 54), "torso_pelvis": (480, 136), "head": (480, 218),
        "left_upper_arm": (170, 218), "left_forearm_hand": (90, 320),
        "right_upper_arm": (790, 218), "right_forearm_hand": (870, 320),
        "left_thigh": (320, 330), "left_shin_foot": (250, 470),
        "right_thigh": (640, 330), "right_shin_foot": (710, 470), "sword": (890, 470),
    }
    parents = {"torso_pelvis": "root/pelvis", "head": "torso_pelvis", "left_upper_arm": "torso_pelvis", "left_forearm_hand": "left_upper_arm", "right_upper_arm": "torso_pelvis", "right_forearm_hand": "right_upper_arm", "left_thigh": "torso_pelvis", "left_shin_foot": "left_thigh", "right_thigh": "torso_pelvis", "right_shin_foot": "right_thigh", "sword": "right_forearm_hand"}
    for child, parent in parents.items():
        draw.line((nodes[parent], nodes[child]), fill=(120, 140, 180, 255), width=3)
    for name, point in nodes.items():
        color = (100, 180, 255, 255) if name in {"root/pelvis", "torso_pelvis"} else PART_COLORS.get(name, (210, 210, 210, 255))
        draw.rounded_rectangle((point[0] - 90, point[1] - 20, point[0] + 90, point[1] + 20), radius=8, fill=color, outline=(255, 255, 255, 255), width=2)
        draw.text((point[0] - 78, point[1] - 7), name, fill=(8, 8, 12, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=False)


def validate_rig_manifest(manifest: Mapping[str, Any], *, expected_schema_version: str = SCHEMA_VERSION) -> dict[str, Any]:
    failures: list[str] = []
    if manifest.get("schema_version") != expected_schema_version:
        failures.append("schema_version")
    if manifest.get("provider_id") != PROVIDER_ID:
        failures.append("provider_id")
    source = manifest.get("source") if isinstance(manifest.get("source"), Mapping) else {}
    for key in ("asset_id", "revision_id", "sha256", "width", "height"):
        if not source.get(key):
            failures.append(f"source.{key}")
    parts = manifest.get("parts") if isinstance(manifest.get("parts"), list) else []
    names = {str(item.get("name")) for item in parts}
    if names != set(PART_NAMES):
        failures.append("parts.must_equal_required_11")
    for item in parts:
        if not item.get("mask_sha256") or not item.get("rgba_sha256") or not item.get("pivot_joint"):
            failures.append(f"part_incomplete:{item.get('name')}")
        if item.get("nonuniform_scale") is not False:
            failures.append(f"part_nonuniform:{item.get('name')}")
    if manifest.get("root_joint") != "pelvis":
        failures.append("root_joint")
    provenance = manifest.get("provenance") if isinstance(manifest.get("provenance"), Mapping) else {}
    if provenance.get("generated_pixel_fraction") != 0.0:
        failures.append("generated_pixel_fraction")
    return {"status": "CUTOUT_RIG_MANIFEST_VALID" if not failures else "CUTOUT_RIG_MANIFEST_INVALID", "failures": failures}


def seam_metrics(image: Image.Image, target: Mapping[str, Any], *, layers: Sequence[Image.Image] | None = None, min_safe_margin: int = MIN_SAFE_MARGIN) -> dict[str, Any]:
    alpha = image.getchannel("A")
    required = list(REQUIRED_JOINTS)
    gaps: dict[str, float] = {}
    for name in required:
        x, y = _target_point(target, name)
        radius = 5
        filled = 0
        total = 0
        for iy in range(max(0, int(y) - radius), min(alpha.height, int(y) + radius + 1)):
            for ix in range(max(0, int(x) - radius), min(alpha.width, int(x) + radius + 1)):
                total += 1
                if alpha.getpixel((ix, iy)) > 0:
                    filled += 1
        gaps[name] = round(1.0 - filled / max(1, total), 6)
    binary_alpha = alpha.point(lambda value: 255 if value > 0 else 0)
    bbox = binary_alpha.getbbox()
    width, height = binary_alpha.size
    margins = {
        "left": bbox[0] if bbox else 0,
        "top": bbox[1] if bbox else 0,
        "right": width - bbox[2] if bbox else 0,
        "bottom": height - bbox[3] if bbox else 0,
    }
    border_contact = any(binary_alpha.getpixel((x, y)) > 0 for x, y in [(x, 0) for x in range(width)] + [(x, height - 1) for x in range(width)] + [(0, y) for y in range(height)] + [(width - 1, y) for y in range(height)])
    component_sizes = _component_sizes(binary_alpha)
    largest_component = max(component_sizes, default=0)
    meaningful_threshold = max(16, int(largest_component * 0.0025))
    body_component_threshold = meaningful_threshold
    body_components = [size for size in component_sizes if size >= body_component_threshold]
    duplicate_body_components = max(0, len(body_components) - 1)
    background_hole_pixels = sum(1 for value in binary_alpha.crop((0, 0, width, height)).getdata() if value == 0) if not layers else 0
    occupancy_overlap_pixels = None
    gross_overlap_pixels = None
    overlap_outside_joint_pixels = None
    if layers:
        occupancy = [layer.getchannel("A").point(lambda value: 255 if value > 0 else 0) for layer in layers]
        counts = [0] * (width * height)
        for layer in occupancy:
            for index, value in enumerate(layer.getdata()):
                if value > 0:
                    counts[index] += 1
        occupancy_overlap_pixels = sum(value >= 2 for value in counts)
        joint_zone = Image.new("L", (width, height), 0)
        overlap_joints = required + (["neck"] if "neck" in (target.get("joints") or {}) or "neck" in target else [])
        for name in overlap_joints:
            x, y = _target_point(target, name)
            draw = ImageDraw.Draw(joint_zone)
            draw.ellipse((x - JOINT_BLEND_RADIUS * 2, y - JOINT_BLEND_RADIUS * 2, x + JOINT_BLEND_RADIUS * 2, y + JOINT_BLEND_RADIUS * 2), fill=255)
        overlap_outside_joint_pixels = sum(value >= 2 and joint_zone.getdata()[index] == 0 for index, value in enumerate(counts))
        gross_overlap_pixels = overlap_outside_joint_pixels
    torso_hole_pixels = 0
    torso_first, torso_second = _target_point(target, "shoulder_center"), _target_point(target, "pelvis")
    for step in range(0, 101):
        fraction = step / 100.0
        x = int(round(torso_first[0] + (torso_second[0] - torso_first[0]) * fraction))
        y = int(round(torso_first[1] + (torso_second[1] - torso_first[1]) * fraction))
        for iy in range(max(0, y - 3), min(height, y + 4)):
            for ix in range(max(0, x - 3), min(width, x + 4)):
                if binary_alpha.getpixel((ix, iy)) == 0:
                    torso_hole_pixels += 1
    background_hole_pixels = torso_hole_pixels
    max_gap = max(gaps.values()) if gaps else 1.0
    safe_margin = all(value >= min_safe_margin for value in margins.values())
    clipping = border_contact
    overlap_excess = None if gross_overlap_pixels is None else gross_overlap_pixels > max(1, int(sum(value > 0 for value in binary_alpha.getdata()) * MAX_GROSS_OVERLAP_FRACTION))
    occupancy_measured = layers is not None
    hard_gates = {"disconnect_zero": max_gap <= 0.02, "gap_at_most_002": max_gap <= 0.02, "duplicate_components_zero": duplicate_body_components == 0, "gross_overlap_false": occupancy_measured and not overlap_excess, "clipping_false": not clipping, "safe_margin_true": safe_margin, "background_holes_measured": occupancy_measured and background_hole_pixels == 0}
    return {"required_joints": required, "joint_gap_fraction": gaps, "max_joint_gap_fraction": round(max_gap, 6), "disconnect_count": 0 if max_gap <= 0.02 else 1, "duplicate_body_components": duplicate_body_components, "fragment_component_count": max(0, len(component_sizes) - len(body_components)), "component_sizes_desc": sorted(component_sizes, reverse=True)[:12], "meaningful_component_threshold": meaningful_threshold, "body_component_threshold": body_component_threshold, "background_hole_pixels": background_hole_pixels, "torso_corridor_hole_pixels": torso_hole_pixels, "overlap_pixels": occupancy_overlap_pixels, "overlap_outside_joint_pixels": overlap_outside_joint_pixels, "overlap_excess": overlap_excess, "clipping": clipping, "border_contact": border_contact, "bbox": list(bbox) if bbox else None, "margins_px": margins, "safe_margin": safe_margin, "occupancy_measured": occupancy_measured, "hard_gates": hard_gates, "status": "SEAM_QA_PASSED" if all(hard_gates.values()) else "CUTOUT_RIG_SEAM_GAP"}
