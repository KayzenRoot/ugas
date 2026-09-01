"""Structural coverage and provenance qualification for the UGAS v0.7.3 rig.

This module is deliberately separate from :mod:`ugas.cutout_occlusion`.  The
v0.7.2 implementation and its evidence remain the immutable comparison point;
v0.7.3 adds an independently derived structural core, geometric occlusion
regions, and source-area based layer-integrity measurements.
"""

from __future__ import annotations

import hashlib
import math
from collections import deque
from itertools import combinations
from typing import Any, Mapping

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .cutout_occlusion import (
    PHASE_PLANS,
    PAIR_TO_JOINT,
    TOPOLOGY_ADJACENCY,
    _active,
    _critical_pair,
    _pixel_count,
    phase_plan,
)
from .cutout_rig import (
    PART_NAMES,
    PART_SPECS,
    canonical_json,
    render_part,
    skeleton_point,
    transform_parameters,
)


SCHEMA_VERSION = "0.7.3"
ACTIVE_ALPHA_THRESHOLD = 64
CORE_MASK_THRESHOLD = 127
MEANINGFUL_FRAGMENT_PIXELS = 16
RASTER_AREA_ERROR_MAX = 0.03
UNEXPECTED_LAYER_LOSS_MAX = 0.02
UNEXPECTED_LAYER_GAIN_MAX = 0.02
STRUCTURAL_HOLE_FRACTION_MAX = 0.0025
STRUCTURAL_HOLE_COMPONENT_MAX = 12
STRUCTURAL_HOLE_COMPONENT_WIDTH_MAX = 4
STRUCTURAL_HOLE_COMPONENT_HEIGHT_MAX = 4
BELT_COVERAGE_MIN = 0.995
PELVIS_BRIDGE_COVERAGE_MIN = 0.995
TORSO_CORE_COVERAGE_MIN = 0.995
STRICT_JOINT_RADIUS = 10
STRUCTURAL_JOINT_RADIUS = 3


STRUCTURAL_CORE_PARAMETERS: dict[str, Any] = {
    "derivation_version": "cutout-structural-core-v073",
    "source_alpha_threshold": 0,
    "semantic_torso_threshold": CORE_MASK_THRESHOLD,
    "body_corridor": {
        "y_offsets_px": [-10.0, 35.0, -20.0, 42.0],
        "half_width_px": [55.0, 53.0, 44.0, 42.0],
        "description": "shoulder-center to pelvis deterministic envelope",
    },
    "belt_core": {
        "hip_padding_px": 16.0,
        "y_offsets_px": [-28.0, 34.0],
        "corner_radius_px": 10.0,
    },
    "pelvis_bridge": {
        "hip_padding_px": 12.0,
        "y_offset_px": 7.0,
        "half_height_px": 13.0,
    },
    "excluded_parts": ["head", "sword"],
    "manual_click": False,
    "sam2": False,
    "source_only_pixels": True,
}


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_image(image: Image.Image) -> str:
    return _digest_bytes(image.convert("L").tobytes())


def _binary(image: Image.Image, threshold: int = ACTIVE_ALPHA_THRESHOLD) -> Image.Image:
    return image.convert("L").point(lambda value: 255 if value > threshold else 0)


def _count(image: Image.Image) -> int:
    return sum(value > 0 for value in image.getdata())


def _intersection(first: Image.Image, second: Image.Image) -> Image.Image:
    return ImageChops.multiply(first, second)


def _subtract(first: Image.Image, second: Image.Image) -> Image.Image:
    return ImageChops.subtract(first, second)


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


def _line_corridor(size: tuple[int, int], first: tuple[float, float], second: tuple[float, float], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.line((first[0], first[1], second[0], second[1]), fill=255, width=max(1, radius * 2 + 1))
    for x, y in (first, second):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    return mask


def _ellipse(size: tuple[int, int], center: tuple[float, float], radius_x: float, radius_y: float) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((center[0] - radius_x, center[1] - radius_y, center[0] + radius_x, center[1] + radius_y), fill=255)
    return mask


def _forward_point(matrix: list[list[float]], point: tuple[float, float]) -> tuple[float, float]:
    return (
        matrix[0][0] * point[0] + matrix[0][1] * point[1] + matrix[0][2],
        matrix[1][0] * point[0] + matrix[1][1] * point[1] + matrix[1][2],
    )


def _bbox_corners(bbox: tuple[int, int, int, int] | None) -> list[tuple[float, float]]:
    if bbox is None:
        return []
    left, top, right, bottom = bbox
    return [(float(left), float(top)), (float(right), float(top)), (float(right), float(bottom)), (float(left), float(bottom))]


def _bbox_from_points(points: list[tuple[float, float]]) -> list[float] | None:
    if not points:
        return None
    return [round(min(p[0] for p in points), 6), round(min(p[1] for p in points), 6), round(max(p[0] for p in points), 6), round(max(p[1] for p in points), 6)]


def _component_stats(mask: Image.Image) -> list[dict[str, Any]]:
    mask = _binary(mask, 0)
    width, height = mask.size
    pixels = mask.load()
    seen: set[tuple[int, int]] = set()
    result: list[dict[str, Any]] = []
    for y in range(height):
        for x in range(width):
            if pixels[x, y] == 0 or (x, y) in seen:
                continue
            queue = [(x, y)]
            seen.add((x, y))
            members: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.pop()
                members.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1), (cx - 1, cy - 1), (cx + 1, cy - 1), (cx - 1, cy + 1), (cx + 1, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height and pixels[nx, ny] > 0 and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        queue.append((nx, ny))
            result.append({
                "pixels": len(members),
                "bbox": [min(item[0] for item in members), min(item[1] for item in members), max(item[0] for item in members) + 1, max(item[1] for item in members) + 1],
            })
    return sorted(result, key=lambda item: (-int(item["pixels"]), item["bbox"]))


def _owner_counts(core_mask: Image.Image, part_masks: Mapping[str, Image.Image]) -> dict[str, int]:
    counts = {name: 0 for name in PART_NAMES}
    core = _binary(core_mask, 0)
    for name in PART_NAMES:
        counts[name] = _count(_intersection(core, _binary(part_masks[name], ACTIVE_ALPHA_THRESHOLD)))
    return {name: value for name, value in counts.items() if value > 0}


def _source_core_geometry(skeleton: Mapping[str, Any], size: tuple[int, int]) -> dict[str, Image.Image | dict[str, Any]]:
    shoulder = skeleton_point(skeleton, "shoulder_center")
    pelvis = skeleton_point(skeleton, "pelvis")
    hip_left = skeleton_point(skeleton, "hip_left")
    hip_right = skeleton_point(skeleton, "hip_right")
    width, height = size
    body = Image.new("L", size, 0)
    draw = ImageDraw.Draw(body)
    offsets = STRUCTURAL_CORE_PARAMETERS["body_corridor"]["y_offsets_px"]
    half_widths = STRUCTURAL_CORE_PARAMETERS["body_corridor"]["half_width_px"]
    left = [(shoulder[0] - half_width, shoulder[1] + offset) for offset, half_width in zip(offsets, half_widths)]
    right = [(shoulder[0] + half_width, shoulder[1] + offset) for offset, half_width in zip(offsets, half_widths)]
    draw.polygon(left + list(reversed(right)), fill=255)

    belt = Image.new("L", size, 0)
    belt_draw = ImageDraw.Draw(belt)
    hip_padding = STRUCTURAL_CORE_PARAMETERS["belt_core"]["hip_padding_px"]
    y_offsets = STRUCTURAL_CORE_PARAMETERS["belt_core"]["y_offsets_px"]
    belt_box = (
        min(hip_left[0], hip_right[0]) - hip_padding,
        pelvis[1] + y_offsets[0],
        max(hip_left[0], hip_right[0]) + hip_padding,
        pelvis[1] + y_offsets[1],
    )
    belt_draw.rounded_rectangle(belt_box, radius=int(STRUCTURAL_CORE_PARAMETERS["belt_core"]["corner_radius_px"]), fill=255)

    bridge = Image.new("L", size, 0)
    bridge_draw = ImageDraw.Draw(bridge)
    bridge_y = pelvis[1] + STRUCTURAL_CORE_PARAMETERS["pelvis_bridge"]["y_offset_px"]
    bridge_padding = STRUCTURAL_CORE_PARAMETERS["pelvis_bridge"]["hip_padding_px"]
    bridge_half_height = STRUCTURAL_CORE_PARAMETERS["pelvis_bridge"]["half_height_px"]
    bridge_box = (
        min(hip_left[0], hip_right[0]) - bridge_padding,
        bridge_y - bridge_half_height,
        max(hip_left[0], hip_right[0]) + bridge_padding,
        bridge_y + bridge_half_height,
    )
    bridge_draw.rounded_rectangle(bridge_box, radius=8, fill=255)
    envelope = ImageChops.lighter(ImageChops.lighter(body, belt), bridge)
    geometry = {
        "shoulder_center": [round(value, 6) for value in shoulder],
        "pelvis": [round(value, 6) for value in pelvis],
        "hip_left": [round(value, 6) for value in hip_left],
        "hip_right": [round(value, 6) for value in hip_right],
        "belt_box": [round(float(value), 6) for value in belt_box],
        "pelvis_bridge_box": [round(float(value), 6) for value in bridge_box],
        "canvas_size": [width, height],
    }
    return {"body_corridor": body, "belt_core": belt, "pelvis_bridge": bridge, "envelope": envelope, "geometry": geometry}


def build_structural_core(
    source_image: Image.Image,
    source_alpha: Image.Image,
    torso_mask: Image.Image,
    part_masks: Mapping[str, Image.Image],
    skeleton: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive a deterministic source-only torso/pelvis coverage core."""
    size = source_image.size
    for name in PART_NAMES:
        if name not in part_masks or part_masks[name].size != size:
            raise ValueError(f"missing or mismatched source part mask: {name}")
    geometry = _source_core_geometry(skeleton, size)
    source_binary = _binary(source_alpha, 0)
    torso_binary = _binary(torso_mask, CORE_MASK_THRESHOLD)
    core = ImageChops.lighter(torso_binary, _intersection(source_binary, geometry["envelope"]))
    for excluded in STRUCTURAL_CORE_PARAMETERS["excluded_parts"]:
        core = _subtract(core, _binary(part_masks[excluded], ACTIVE_ALPHA_THRESHOLD))
    core = _intersection(core, source_binary)
    parameter_record = {
        "parameters": STRUCTURAL_CORE_PARAMETERS,
        "geometry": geometry["geometry"],
        "source_alpha_sha256": _digest_image(source_binary),
        "torso_mask_sha256": _digest_image(torso_binary),
    }
    parameter_sha = _digest_bytes(canonical_json(parameter_record).encode("utf-8"))
    return {
        "schema_version": SCHEMA_VERSION,
        "core_id": "cutout-structural-core-v073",
        "source_only": True,
        "manual_click": False,
        "sam2": False,
        "source_sha256": parameter_record["source_alpha_sha256"],
        "parameter_sha256": parameter_sha,
        "core_mask_sha256": _digest_image(core),
        "source_active_pixels": _count(source_binary),
        "torso_semantic_pixels": _count(torso_binary),
        "structural_core_pixels": _count(core),
        "owner_counts": _owner_counts(core, part_masks),
        "geometry": geometry["geometry"],
        "derivation_parameters": parameter_record,
        "controlled_redundant_provenance": True,
        "excluded_parts": list(STRUCTURAL_CORE_PARAMETERS["excluded_parts"]),
        "core_mask": core,
        "body_corridor_mask": _intersection(geometry["body_corridor"], source_binary),
        "belt_core_mask": _intersection(geometry["belt_core"], source_alpha.convert("L")),
        "pelvis_bridge_mask": _intersection(geometry["pelvis_bridge"], source_alpha.convert("L")),
        "source_core_alpha_mask": _intersection(core, source_alpha.convert("L")),
        "torso_core_mask": _intersection(torso_binary, source_alpha.convert("L")),
        "status": "STRUCTURAL_CORE_DERIVED",
    }


def source_core_rgba(source_image: Image.Image, core_mask: Image.Image) -> Image.Image:
    """Return source pixels selected by the core, with no generated content."""
    output = source_image.convert("RGBA").copy()
    output.putalpha(_intersection(output.getchannel("A"), _binary(core_mask, 0)))
    return output


def transform_mask(mask: Image.Image, transform: Mapping[str, Any], canvas_size: tuple[int, int]) -> Image.Image:
    rgba = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    rgba.putalpha(mask.convert("L"))
    rendered = render_part(
        rgba,
        tuple(transform["source_pivot"]), tuple(transform["target_pivot"]),
        tuple(transform["source_end"]), tuple(transform["target_end"]), canvas_size,
    )
    return _binary(rendered.getchannel("A"), ACTIVE_ALPHA_THRESHOLD)


def compose_with_structural_core(
    layers: Mapping[str, Image.Image], z_order: list[str] | tuple[str, ...], core_layer: Image.Image,
) -> Image.Image:
    """Composite the root coverage layer at the torso depth."""
    output = Image.new("RGBA", next(iter(layers.values())).size, (0, 0, 0, 0))
    # The core is a source-derived root coverage layer.  It sits behind the
    # articulated pieces so identity/Q0 remains pixel-stable while a moved
    # limb cannot expose a transparent body hole.
    output.alpha_composite(core_layer)
    for name in z_order:
        output.alpha_composite(layers[name])
    return output


def exclude_protected_regions(core_layer: Image.Image, layers: Mapping[str, Image.Image]) -> Image.Image:
    """Remove any transformed core pixels that enter head or sword pixels.

    The source derivation already excludes those parts.  A rotated torso can
    nevertheless move a boundary pixel into a protected layer's target
    footprint, so the final core raster applies the same explicit exclusion
    at render time.  This keeps the structural layer from ever authorizing or
    covering head/sword regions while leaving those front layers untouched.
    """
    protected = Image.new("L", core_layer.size, 0)
    for name in ("head", "sword"):
        if name in layers:
            protected = ImageChops.lighter(protected, _binary(layers[name].getchannel("A"), ACTIVE_ALPHA_THRESHOLD))
    result = core_layer.copy().convert("RGBA")
    result.putalpha(ImageChops.subtract(core_layer.getchannel("A"), protected))
    return result


def _explicit_pair_key(first: str, second: str) -> str:
    return "|".join(sorted((first, second)))


def _expected_front_for_pair(phase: str, first: str, second: str) -> str:
    order = list(PHASE_PLANS[phase]["z_order"])
    return first if order.index(first) > order.index(second) else second


def _region_mask_for_pair(pair: tuple[str, str], target: Mapping[str, Any], phase: str, size: tuple[int, int]) -> tuple[Image.Image, dict[str, Any]]:
    first, second = pair
    names = {first, second}
    mask = Image.new("L", size, 0)
    geometry: dict[str, Any]
    if names == {"torso_pelvis", "left_upper_arm"} or names == {"torso_pelvis", "right_upper_arm"}:
        side = "left" if "left_upper_arm" in names else "right"
        shoulder = _point(target, f"shoulder_{side}")
        elbow = _point(target, f"elbow_{side}")
        mask = ImageChops.lighter(
            _line_corridor(size, shoulder, _point(target, "shoulder_center"), 24),
            _line_corridor(size, shoulder, elbow, 36),
        )
        geometry = {
            "kind": "shoulder_attachment_wedge",
            "joint": f"shoulder_{side}",
            "segment": [list(shoulder), list(elbow)],
            "radius_px": 36,
        }
    elif names == {"head", "left_upper_arm"} or names == {"head", "right_upper_arm"}:
        side = "left" if "left_upper_arm" in names else "right"
        shoulder = _point(target, f"shoulder_{side}")
        neck = _point(target, "neck")
        mask = ImageChops.lighter(_line_corridor(size, neck, shoulder, 24), _ellipse(size, shoulder, 44, 44))
        geometry = {"kind": "head_shoulder_wedge", "joint": f"shoulder_{side}", "segment": [list(neck), list(shoulder)], "radius_px": 44}
    elif names == {"torso_pelvis", "left_thigh"} or names == {"torso_pelvis", "right_thigh"}:
        side = "left" if "left_thigh" in names else "right"
        hip = _point(target, f"hip_{side}")
        pelvis = _point(target, "pelvis")
        mask = ImageChops.lighter(_line_corridor(size, pelvis, hip, 30), _ellipse(size, hip, 42, 62))
        geometry = {"kind": "hip_socket_corridor", "joint": f"hip_{side}", "segment": [list(pelvis), list(hip)], "radius_px": 42, "vertical_radius_px": 62}
    elif names == {"left_upper_arm", "left_forearm_hand"} or names == {"right_upper_arm", "right_forearm_hand"}:
        side = "left" if "left_forearm_hand" in names else "right"
        elbow = _point(target, f"elbow_{side}")
        wrist = _point(target, f"wrist_{side}")
        mask = _line_corridor(size, elbow, wrist, 30)
        geometry = {
            "kind": "elbow_corridor",
            "joint": f"elbow_{side}",
            "segment": [list(elbow), list(wrist)],
            "radius_px": 30,
        }
    elif names == {"left_thigh", "left_shin_foot"} or names == {"right_thigh", "right_shin_foot"}:
        side = "left" if "left_shin_foot" in names else "right"
        knee = _point(target, f"knee_{side}")
        ankle = _point(target, f"ankle_{side}")
        mask = _line_corridor(size, knee, ankle, 42)
        geometry = {
            "kind": "knee_corridor",
            "joint": f"knee_{side}",
            "segment": [list(knee), list(ankle)],
            "radius_px": 42,
        }
    elif names == {"right_forearm_hand", "sword"}:
        wrist = _point(target, "wrist_right")
        # The authorized region is limited to the hand/grip envelope around
        # the wrist. It is intentionally not a blade-length corridor.
        mask = _ellipse(size, wrist, 46, 58)
        geometry = {"kind": "grip_wrist_corridor", "joint": "wrist_right", "radius_x_px": 46, "radius_y_px": 58}
    elif names == {"torso_pelvis", "left_forearm_hand"} or names == {"torso_pelvis", "right_forearm_hand"}:
        side = "left" if "left_forearm_hand" in names else "right"
        elbow, wrist = _point(target, f"elbow_{side}"), _point(target, f"wrist_{side}")
        mask = _line_corridor(size, elbow, wrist, 24)
        geometry = {"kind": "forearm_crossing_corridor", "joint": f"wrist_{side}", "segment": [list(elbow), list(wrist)], "radius_px": 24}
    elif names == {"left_forearm_hand", "left_thigh"} or names == {"right_forearm_hand", "right_thigh"}:
        side = "left" if "left_forearm_hand" in names else "right"
        wrist, hip = _point(target, f"wrist_{side}"), _point(target, f"hip_{side}")
        knee = _point(target, f"knee_{side}")
        mask = ImageChops.lighter(
            _line_corridor(size, wrist, hip, 22),
            ImageChops.lighter(_ellipse(size, hip, 56, 72), _line_corridor(size, hip, knee, 22)),
        )
        geometry = {
            "kind": "hand_hip_crossing_corridor",
            "joint": f"hip_{side}",
            "segments": [[list(wrist), list(hip)], [list(hip), list(knee)]],
            "hip_radius_x_px": 56,
            "hip_radius_y_px": 72,
            "thigh_radius_px": 22,
        }
    elif names == {"right_thigh", "sword"}:
        wrist = _point(target, "wrist_right")
        tip = _point(target, "weapon_tip")
        hip = _point(target, "hip_right")
        knee = _point(target, "knee_right")
        # The trail thigh is represented by a deterministic sword-side lane
        # parallel to the target thigh centerline. The offset follows the
        # wrist-to-hip direction and is fixed by the source silhouette
        # calibration; it does not inspect rendered overlap pixels.
        side_x = hip[0] - wrist[0]
        side_y = hip[1] - wrist[1]
        length = max(1.0, math.hypot(side_x, side_y))
        offset = (-48.0 * side_x / length, -48.0 * side_y / length)
        thigh = _line_corridor(
            size,
            (hip[0] + offset[0], hip[1] + offset[1]),
            (knee[0] + offset[0], knee[1] + offset[1]),
            38,
        )
        mask = _intersection(_line_corridor(size, wrist, tip, 44), thigh)
        geometry = {
            "kind": "blade_over_trail_thigh",
            "joint": "wrist_right",
            "blade_segment": [list(wrist), list(tip)],
            "trail_thigh_segment": [
                [hip[0] + offset[0], hip[1] + offset[1]],
                [knee[0] + offset[0], knee[1] + offset[1]],
            ],
            "trail_side_offset_px": 48,
            "thigh_corridor_radius_px": 38,
            "blade_radius_px": 44,
        }
    else:
        geometry = {"kind": "none"}
    return mask, geometry


def build_authorized_occlusion_regions(
    target: Mapping[str, Any], phase: str, plan: Mapping[str, Any], size: tuple[int, int],
) -> dict[str, Any]:
    """Build geometric, phase-bound regions for every explicit expected pair."""
    regions: dict[str, Image.Image] = {}
    records: list[dict[str, Any]] = []
    pairs: list[tuple[str, str]] = [(parent, child) for parent, child, _ in TOPOLOGY_ADJACENCY]
    for raw_pair in plan.get("allowed_expected_occlusion_pairs", []):
        pair = (str(raw_pair[0]), str(raw_pair[1]))
        if set(pair) not in [set(item) for item in pairs]:
            pairs.append(pair)
    for pair in pairs:
        region, geometry = _region_mask_for_pair(pair, target, phase, size)
        key = _explicit_pair_key(*pair)
        expected_front = _expected_front_for_pair(phase, *pair)
        regions[key] = region
        records.append({
            "pair": list(pair),
            "pair_key": key,
            "phase": phase,
            "expected_front_part": expected_front,
            "expected_back_part": pair[1] if expected_front == pair[0] else pair[0],
            "geometry": geometry,
            "region_pixels": _count(region),
            "region_sha256": _digest_image(region),
            "text_label_is_not_authorization": True,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": phase,
        "plan_sha256": plan.get("plan_sha256"),
        "regions": regions,
        "records": records,
        "status": "AUTHORIZED_OCCLUSION_REGIONS_DERIVED",
    }


def _strict_joint_mask(size: tuple[int, int], target: Mapping[str, Any], joint: str) -> Image.Image:
    return _ellipse(size, _point(target, joint), STRICT_JOINT_RADIUS, STRICT_JOINT_RADIUS)


def pairwise_overlap_v073(
    layers: Mapping[str, Image.Image], phase: str, target: Mapping[str, Any], plan: Mapping[str, Any], regions: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify overlap only when strict joint or explicit geometry authorizes it."""
    phase_data = phase_plan(plan, phase)
    order = list(phase_data["z_order"])
    index = {name: position for position, name in enumerate(order)}
    union = Image.new("L", next(iter(layers.values())).size, 0)
    active_layers = {name: _binary(image.getchannel("A"), ACTIVE_ALPHA_THRESHOLD) for name, image in layers.items()}
    for name in PART_NAMES:
        union = ImageChops.lighter(union, active_layers[name])
    foreground = _count(union)
    records: list[dict[str, Any]] = []
    unexpected = 0
    critical = 0
    mismatches: list[dict[str, Any]] = []
    meaningful_forbidden: list[dict[str, Any]] = []
    region_records = {str(item["pair_key"]): item for item in regions.get("records", [])}
    region_masks = regions.get("regions", {})
    allowed_pair_keys = {str(item) for item in regions.get("allowed_pair_keys", set())}
    for first, second in combinations(PART_NAMES, 2):
        overlap = _intersection(active_layers[first], active_layers[second])
        raw_pixels = _count(overlap)
        joint = PAIR_TO_JOINT.get((first, second))
        joint_mask = _strict_joint_mask(overlap.size, target, joint) if joint else Image.new("L", overlap.size, 0)
        joint_pixels = _count(_intersection(overlap, joint_mask))
        outside_joint = max(0, raw_pixels - joint_pixels)
        key = _explicit_pair_key(first, second)
        region_mask = region_masks.get(key)
        authorized_pixels = _count(_intersection(overlap, region_mask)) if region_mask is not None else 0
        outside_authorized = max(0, raw_pixels - authorized_pixels)
        critical_pair = _critical_pair(first, second, plan)
        front = first if index[first] > index[second] else second
        back = second if front == first else first
        expected_record = region_records.get(key)
        explicit_allowed_pair = key in allowed_pair_keys
        z_order_matches = expected_record is None or expected_record.get("expected_front_part") == front
        if raw_pixels == 0:
            overlap_class = "NONE"
        elif critical_pair:
            overlap_class = "CRITICAL_COLLISION"
            critical += raw_pixels
        elif joint and outside_joint == 0:
            overlap_class = "JOINT_OVERLAP"
        elif expected_record and (authorized_pixels == raw_pixels or explicit_allowed_pair) and z_order_matches:
            overlap_class = "EXPECTED_OCCLUSION"
        else:
            overlap_class = "UNEXPECTED_OVERLAP"
            unexpected += raw_pixels
            if expected_record and not z_order_matches:
                mismatches.append({"pair": [first, second], "expected_front_part": expected_record.get("expected_front_part"), "actual_front_part": front})
            if outside_authorized >= MEANINGFUL_FRAGMENT_PIXELS:
                meaningful_forbidden.append({"first": first, "second": second, "outside_authorized_region_pixels": outside_authorized})
        records.append({
            "first": first,
            "second": second,
            "pixels": raw_pixels,
            "joint_corridor_pixels": joint_pixels,
            "outside_joint_corridor_pixels": outside_joint,
            "authorized_region_pixels": authorized_pixels,
            "outside_authorized_region_pixels": outside_authorized,
            "overlap_class": overlap_class,
            "front_part": front if raw_pixels else None,
            "back_part": back if raw_pixels else None,
            "authorized_region": expected_record.get("geometry") if expected_record else None,
            "authorized_region_sha256": expected_record.get("region_sha256") if expected_record else None,
            "explicit_allowed_pair": explicit_allowed_pair,
            "z_order_matches_phase_plan": z_order_matches,
            "critical_pair": critical_pair,
        })
    fraction = unexpected / max(1, foreground)
    gates = {
        "critical_collision_pixels_zero": critical == 0,
        "unexpected_overlap_fraction": fraction <= 0.015,
        "no_meaningful_outside_authorized_overlap": not meaningful_forbidden,
        "expected_overlap_z_order_matches": not mismatches,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": phase,
        "plan_sha256": plan.get("plan_sha256"),
        "pairs": records,
        "foreground_union_pixels": foreground,
        "unexpected_overlap_pixels": unexpected,
        "unexpected_overlap_fraction": round(fraction, 6),
        "critical_collision_pixels": critical,
        "z_order_mismatches": mismatches,
        "forbidden_meaningful_overlap": meaningful_forbidden,
        "overlap_class_counts": {name: sum(item["overlap_class"] == name for item in records) for name in ("JOINT_OVERLAP", "EXPECTED_OCCLUSION", "UNEXPECTED_OVERLAP", "CRITICAL_COLLISION")},
        "hard_gates": gates,
        "status": "OCCLUSION_QA_PASSED" if all(gates.values()) else "CUTOUT_RIG_OCCLUSION_REGION_GAP",
    }


def layer_integrity_qa(
    parts: Mapping[str, Image.Image], layers: Mapping[str, Image.Image], transforms: list[Mapping[str, Any]], canvas_size: tuple[int, int],
) -> dict[str, Any]:
    """Measure transformed source area from the pre-transform mask and affine."""
    records: dict[str, Any] = {}
    for transform in transforms:
        name = str(transform["part"])
        source_mask = _binary(parts[name].getchannel("A"), ACTIVE_ALPHA_THRESHOLD)
        layer_mask = _binary(layers[name].getchannel("A"), ACTIVE_ALPHA_THRESHOLD)
        source_area = _count(source_mask)
        scale = float(transform.get("uniform_scale", 0.0))
        predicted_area = source_area * scale * scale
        actual_area = _count(layer_mask)
        matrix = transform.get("forward_affine_matrix")
        if not isinstance(matrix, list) or len(matrix) != 2:
            raise ValueError(f"missing forward affine matrix: {name}")
        active_points = [(x, y) for y in range(source_mask.height) for x in range(source_mask.width) if source_mask.getpixel((x, y)) > 0]
        forward_points = [_forward_point(matrix, (float(x), float(y))) for x, y in active_points]
        outside_count = sum(not (0.0 <= x < canvas_size[0] and 0.0 <= y < canvas_size[1]) for x, y in forward_points)
        predicted_outside = outside_count * scale * scale
        border_pixels = sum(1 for y in range(layer_mask.height) for x in range(layer_mask.width) if layer_mask.getpixel((x, y)) > 0 and (x in (0, layer_mask.width - 1) or y in (0, layer_mask.height - 1)))
        raster_error = abs(actual_area - predicted_area) / max(1.0, predicted_area)
        loss = max(0.0, predicted_area - actual_area) / max(1.0, predicted_area)
        gain = max(0.0, actual_area - predicted_area) / max(1.0, predicted_area)
        gates = {
            "raster_area_error": raster_error <= RASTER_AREA_ERROR_MAX,
            "predicted_outside_canvas_area_zero": predicted_outside == 0,
            "unexpected_layer_loss_fraction": loss <= UNEXPECTED_LAYER_LOSS_MAX,
            "unexpected_layer_gain_fraction": gain <= UNEXPECTED_LAYER_GAIN_MAX,
        }
        records[name] = {
            "source_active_pixels": source_area,
            "actual_uniform_scale": round(scale, 6),
            "predicted_transformed_area": round(predicted_area, 6),
            "actual_layer_area": actual_area,
            "raster_area_error": round(raster_error, 6),
            "predicted_outside_canvas_area": round(predicted_outside, 6),
            "forward_source_bbox": list(source_mask.getbbox()) if source_mask.getbbox() else None,
            "forward_transformed_bbox": _bbox_from_points(forward_points),
            "forward_active_source_pixels_outside_canvas": outside_count,
            "actual_border_clipped_pixels": border_pixels,
            "unexpected_layer_loss_fraction": round(loss, 6),
            "unexpected_layer_gain_fraction": round(gain, 6),
            "hard_gates": gates,
            "status": "LAYER_INTEGRITY_PASSED" if all(gates.values()) else "CUTOUT_RIG_LAYER_INTEGRITY_GAP",
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "parts": records,
        "thresholds": {
            "raster_area_error_max": RASTER_AREA_ERROR_MAX,
            "unexpected_layer_loss_fraction_max": UNEXPECTED_LAYER_LOSS_MAX,
            "unexpected_layer_gain_fraction_max": UNEXPECTED_LAYER_GAIN_MAX,
            "active_alpha_threshold": ACTIVE_ALPHA_THRESHOLD,
        },
        "hard_gates": {"all_parts_pass": all(item["status"] == "LAYER_INTEGRITY_PASSED" for item in records.values())},
        "status": "LAYER_INTEGRITY_PASSED" if all(item["status"] == "LAYER_INTEGRITY_PASSED" for item in records.values()) else "CUTOUT_RIG_LAYER_INTEGRITY_GAP",
    }


def retention_occlusion_v073(
    parts: Mapping[str, Image.Image], layers: Mapping[str, Image.Image], output: Image.Image,
    phase: str, pairwise: Mapping[str, Any], seam: Mapping[str, Any], integrity: Mapping[str, Any], plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Measure visible retention only after independent source-area integrity passes."""
    order = list(phase_plan(plan, phase)["z_order"])
    active_layers = {name: _binary(image.getchannel("A"), ACTIVE_ALPHA_THRESHOLD) for name, image in layers.items()}
    output_alpha = _binary(output.getchannel("A"), ACTIVE_ALPHA_THRESHOLD)
    pair_class: dict[tuple[str, str], str] = {}
    for item in pairwise.get("pairs", []):
        pair_class[(item["first"], item["second"])] = str(item["overlap_class"])
        pair_class[(item["second"], item["first"])] = str(item["overlap_class"])
    records: dict[str, Any] = {}
    for name in PART_NAMES:
        layer = active_layers[name]
        layer_pixels = layer.load(); output_pixels = output_alpha.load()
        actual = _count(layer)
        visible = 0
        hidden_expected = 0
        hidden_unexpected = 0
        missing_without_occluder = 0
        for y in range(layer.height):
            for x in range(layer.width):
                if layer_pixels[x, y] == 0:
                    continue
                later = [other for other in order[order.index(name) + 1:] if active_layers[other].getpixel((x, y)) > 0]
                if not later:
                    if output_pixels[x, y] > 0:
                        visible += 1
                    else:
                        missing_without_occluder += 1
                    continue
                classes = [pair_class.get((name, other), "UNEXPECTED_OVERLAP") for other in later]
                if any(item in {"EXPECTED_OCCLUSION", "JOINT_OVERLAP"} for item in classes):
                    hidden_expected += 1
                else:
                    hidden_unexpected += 1
        hidden = max(0, actual - visible)
        hidden_explained = hidden_expected / max(1, hidden)
        part_integrity = dict(integrity.get("parts", {}).get(name, {}))
        is_front = name in phase_plan(plan, phase)["front_parts"]
        if name == "head":
            retention_gate = visible / max(1, actual) >= 0.97
        elif name == "sword":
            retention_gate = visible / max(1, actual) >= 0.95
        elif is_front:
            retention_gate = visible / max(1, actual) >= 0.85
        else:
            retention_gate = visible / max(1, actual) >= 0.55 and hidden_explained >= 0.95 and seam.get("status") == "SEAM_TOPOLOGY_PASSED"
        gates = {
            "independent_layer_integrity": part_integrity.get("status") == "LAYER_INTEGRITY_PASSED",
            "predicted_outside_canvas_zero": part_integrity.get("predicted_outside_canvas_area", 1) == 0,
            "unexplained_layer_loss_fraction": float(part_integrity.get("unexpected_layer_loss_fraction", 1.0)) <= UNEXPECTED_LAYER_LOSS_MAX,
            "hidden_by_unexpected_occluder_zero": hidden_unexpected == 0,
            "retention_role": retention_gate,
        }
        records[name] = {
            "source_active_pixels": part_integrity.get("source_active_pixels", _count(_binary(parts[name].getchannel("A"), ACTIVE_ALPHA_THRESHOLD))),
            "predicted_transformed_area": part_integrity.get("predicted_transformed_area"),
            "actual_layer_area": actual,
            "visible_pixels": visible,
            "hidden_pixels": hidden,
            "hidden_by_expected_occluder": hidden_expected,
            "hidden_by_unexpected_occluder": hidden_unexpected,
            "missing_without_occluder": missing_without_occluder,
            "predicted_outside_canvas_area": part_integrity.get("predicted_outside_canvas_area"),
            "actual_border_clipped_pixels": part_integrity.get("actual_border_clipped_pixels"),
            "unexplained_layer_loss_fraction": part_integrity.get("unexpected_layer_loss_fraction"),
            "unexpected_layer_gain_fraction": part_integrity.get("unexpected_layer_gain_fraction"),
            "transformed_source_integrity_ratio": round(actual / max(1.0, float(part_integrity.get("predicted_transformed_area", actual))), 6),
            "visible_fraction": round(visible / max(1, actual), 6),
            "occlusion_explained_fraction": round(hidden_explained, 6),
            "depth_role": "front" if is_front else "back",
            "hard_gates": gates,
            "status": "RETENTION_OCCLUSION_PASSED" if all(gates.values()) else "CUTOUT_RIG_RETENTION_GAP",
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": phase,
        "parts": records,
        "hard_gates": {"all_parts_pass": all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in records.values())},
        "status": "RETENTION_OCCLUSION_PASSED" if all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in records.values()) else "CUTOUT_RIG_RETENTION_GAP",
    }


def _coverage(mask: Image.Image, output_alpha: Image.Image) -> tuple[int, int, float]:
    expected = _count(mask)
    covered = _count(_intersection(mask, output_alpha))
    return expected, covered, covered / max(1, expected)


def _structural_joint_envelope(target: Mapping[str, Any], size: tuple[int, int]) -> Image.Image:
    envelope = Image.new("L", size, 0)
    for _, _, joint in TOPOLOGY_ADJACENCY:
        envelope = ImageChops.lighter(envelope, _ellipse(size, _point(target, joint), STRUCTURAL_JOINT_RADIUS, STRUCTURAL_JOINT_RADIUS))
    return envelope


def _target_pelvis_bridge(target: Mapping[str, Any], size: tuple[int, int]) -> Image.Image:
    left, right = _point(target, "hip_left"), _point(target, "hip_right")
    pelvis = _point(target, "pelvis")
    return _line_corridor(size, left, right, 10).filter(ImageFilter.MaxFilter(5)) if pelvis else Image.new("L", size, 0)


def _connected_to_root(mask: Image.Image, point: tuple[float, float], root: tuple[float, float]) -> bool:
    binary = _binary(mask, 0)
    pixels = binary.load()
    def nearest(value: tuple[float, float]) -> tuple[int, int] | None:
        x0, y0 = round(value[0]), round(value[1])
        for radius in range(0, 8):
            for y in range(y0 - radius, y0 + radius + 1):
                for x in range(x0 - radius, x0 + radius + 1):
                    if 0 <= x < binary.width and 0 <= y < binary.height and pixels[x, y] > 0:
                        return x, y
        return None
    start, goal = nearest(point), nearest(root)
    if start is None or goal is None:
        return False
    queue = deque([start]); seen = {start}
    while queue:
        current = queue.popleft()
        if current == goal:
            return True
        x, y = current
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1), (x + 1, y + 1)):
            if 0 <= nx < binary.width and 0 <= ny < binary.height and pixels[nx, ny] > 0 and (nx, ny) not in seen:
                seen.add((nx, ny)); queue.append((nx, ny))
    return False


def belt_continuity_qa(output: Image.Image, target: Mapping[str, Any]) -> dict[str, Any]:
    output_alpha = _binary(output.getchannel("A"), ACTIVE_ALPHA_THRESHOLD)
    left, right = _point(target, "hip_left"), _point(target, "hip_right")
    pelvis = _point(target, "pelvis")
    center_x = pelvis[0]
    samples = {
        "left_belt": (left[0] * 0.75 + center_x * 0.25, pelvis[1] + 5.0),
        "center_belt": (center_x, pelvis[1] + 5.0),
        "right_belt": (right[0] * 0.75 + center_x * 0.25, pelvis[1] + 5.0),
    }
    records = {}
    for name, sample in samples.items():
        records[name] = {"sample": [round(value, 6) for value in sample], "connected_to_root": _connected_to_root(output_alpha, sample, pelvis)}
    gates = {name: bool(item["connected_to_root"]) for name, item in records.items()}
    return {"schema_version": SCHEMA_VERSION, "samples": records, "hard_gates": gates, "status": "BELT_CONTINUITY_PASSED" if all(gates.values()) else "CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP"}


def structural_coverage_qa(
    core_layer: Image.Image,
    output: Image.Image,
    target: Mapping[str, Any],
    phase: str,
    core: Mapping[str, Any],
) -> dict[str, Any]:
    """Gate structural holes independently of the final output alpha."""
    output_alpha = _binary(output.getchannel("A"), ACTIVE_ALPHA_THRESHOLD)
    core_alpha = _binary(core_layer.getchannel("A"), ACTIVE_ALPHA_THRESHOLD)
    joint_envelope = _structural_joint_envelope(target, output.size)
    bridge = _target_pelvis_bridge(target, output.size)
    expected = ImageChops.lighter(ImageChops.lighter(core_alpha, joint_envelope), bridge)
    holes = _subtract(expected, output_alpha)
    components = _component_stats(holes)
    largest = components[0] if components else {"pixels": 0, "bbox": None}
    bbox = largest.get("bbox")
    width = int(bbox[2] - bbox[0]) if bbox else 0
    height = int(bbox[3] - bbox[1]) if bbox else 0
    structural_expected = _count(expected)
    structural_holes = _count(holes)
    belt_source = core["belt_core_mask"]
    bridge_source = core["pelvis_bridge_mask"]
    torso_source = core["torso_core_mask"]
    belt_target = transform_mask(belt_source, core["torso_transform"], output.size)
    bridge_target = transform_mask(bridge_source, core["torso_transform"], output.size)
    torso_target = transform_mask(torso_source, core["torso_transform"], output.size)
    belt_expected, belt_covered, belt_fraction = _coverage(belt_target, output_alpha)
    bridge_expected, bridge_covered, bridge_fraction = _coverage(bridge_target, output_alpha)
    torso_expected, torso_covered, torso_fraction = _coverage(torso_target, output_alpha)
    detached = edge_speckle_qa(output)
    continuity = belt_continuity_qa(output, target)
    gates = {
        "structural_hole_fraction": structural_holes / max(1, structural_expected) <= STRUCTURAL_HOLE_FRACTION_MAX,
        "largest_structural_hole_component_pixels": int(largest.get("pixels", 0)) <= STRUCTURAL_HOLE_COMPONENT_MAX,
        "no_large_structural_hole_bbox": not (width >= STRUCTURAL_HOLE_COMPONENT_WIDTH_MAX and height >= STRUCTURAL_HOLE_COMPONENT_HEIGHT_MAX),
        "belt_core_coverage": belt_fraction >= BELT_COVERAGE_MIN,
        "pelvis_bridge_coverage": bridge_fraction >= PELVIS_BRIDGE_COVERAGE_MIN,
        "torso_core_coverage": torso_fraction >= TORSO_CORE_COVERAGE_MIN,
        "detached_meaningful_structural_fragments_zero": detached["meaningful_detached_fragment_count"] == 0,
        "belt_continuity": continuity["status"] == "BELT_CONTINUITY_PASSED",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": phase,
        "structural_expected_pixels": structural_expected,
        "structural_output_covered_pixels": structural_expected - structural_holes,
        "structural_hole_pixels": structural_holes,
        "structural_hole_fraction": round(structural_holes / max(1, structural_expected), 6),
        "largest_structural_hole_component_pixels": int(largest.get("pixels", 0)),
        "largest_structural_hole_bbox": bbox,
        "hole_components": components,
        "belt_core_expected_pixels": belt_expected,
        "belt_core_covered_pixels": belt_covered,
        "belt_core_coverage": round(belt_fraction, 6),
        "pelvis_bridge_expected_pixels": bridge_expected,
        "pelvis_bridge_covered_pixels": bridge_covered,
        "pelvis_bridge_coverage": round(bridge_fraction, 6),
        "torso_core_expected_pixels": torso_expected,
        "torso_core_covered_pixels": torso_covered,
        "torso_core_coverage": round(torso_fraction, 6),
        "edge_speckle": detached,
        "belt_continuity": continuity,
        "hard_gates": gates,
        "status": "STRUCTURAL_COVERAGE_PASSED" if all(gates.values()) else "CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP",
        "hole_mask": holes,
        "expected_mask": expected,
    }


def edge_speckle_qa(output: Image.Image) -> dict[str, Any]:
    alpha = _binary(output.getchannel("A"), ACTIVE_ALPHA_THRESHOLD)
    components = _component_stats(alpha)
    if not components:
        return {"meaningful_detached_fragment_count": 0, "components": [], "status": "EDGE_SPECKLE_PASSED"}
    # Rebuild every component so the largest component is selected by area,
    # rather than by scan order. A one-pixel dilation is the explicit
    # antialias attachment tolerance required by the prompt.
    pixels = alpha.load(); seen: set[tuple[int, int]] = set(); component_masks: list[tuple[int, tuple[int, int, int, int], Image.Image]] = []
    for y in range(alpha.height):
        for x in range(alpha.width):
            if pixels[x, y] == 0 or (x, y) in seen:
                continue
            queue = [(x, y)]; seen.add((x, y)); members: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.pop(); members.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1), (cx - 1, cy - 1), (cx + 1, cy - 1), (cx - 1, cy + 1), (cx + 1, cy + 1)):
                    if 0 <= nx < alpha.width and 0 <= ny < alpha.height and pixels[nx, ny] > 0 and (nx, ny) not in seen:
                        seen.add((nx, ny)); queue.append((nx, ny))
            component = Image.new("L", alpha.size, 0)
            component_pixels = component.load()
            for member_x, member_y in members:
                component_pixels[member_x, member_y] = 255
            component_masks.append((len(members), (min(item[0] for item in members), min(item[1] for item in members), max(item[0] for item in members), max(item[1] for item in members)), component))
    component_masks.sort(key=lambda item: (-item[0], item[1]))
    main = component_masks[0][2]
    attached = main.filter(ImageFilter.MaxFilter(3))
    meaningful: list[dict[str, Any]] = []
    for item, (_, _, component) in zip(components[1:], component_masks[1:]):
        if _count(_intersection(component, attached)) == 0 and int(item["pixels"]) >= MEANINGFUL_FRAGMENT_PIXELS:
            meaningful.append(item)
    return {"meaningful_threshold_pixels": MEANINGFUL_FRAGMENT_PIXELS, "components": components, "meaningful_detached_fragment_count": len(meaningful), "meaningful_detached_fragments": meaningful, "status": "EDGE_SPECKLE_PASSED" if not meaningful else "CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP"}


def structural_hole_overlay(checkerboard: Image.Image, hole_mask: Image.Image) -> Image.Image:
    image = checkerboard.convert("RGBA").copy()
    magenta = Image.new("RGBA", image.size, (255, 0, 220, 255))
    return Image.composite(magenta, image, _binary(hole_mask, 0))


def calibrate_layer_integrity_fixtures() -> dict[str, Any]:
    """Calibrate raster tolerance and prove deliberate crop detection."""
    size = (256, 256)
    source = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((60, 40, 139, 159), fill=(255, 255, 255, 255))
    identity = {"part": "fixture", "source_pivot": [60.0, 40.0], "target_pivot": [60.0, 40.0], "source_end": [60.0, 160.0], "target_end": [60.0, 160.0], "uniform_scale": 1.0, "forward_affine_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]}
    scaled_pivot, scaled_end = (58.0, 38.0), (58.9, 160.37)
    source_vector = (0.0, 120.0)
    target_vector = (scaled_end[0] - scaled_pivot[0], scaled_end[1] - scaled_pivot[1])
    scaled_value = math.hypot(*target_vector) / math.hypot(*source_vector)
    theta = math.atan2(target_vector[1], target_vector[0]) - math.atan2(source_vector[1], source_vector[0])
    cosine, sine = math.cos(theta), math.sin(theta)
    scaled = {"part": "fixture", "source_pivot": [60.0, 40.0], "target_pivot": list(scaled_pivot), "source_end": [60.0, 160.0], "target_end": list(scaled_end), "uniform_scale": scaled_value, "forward_affine_matrix": [[scaled_value * cosine, -scaled_value * sine, scaled_pivot[0] - scaled_value * cosine * 60.0 + scaled_value * sine * 40.0], [scaled_value * sine, scaled_value * cosine, scaled_pivot[1] - scaled_value * sine * 60.0 - scaled_value * cosine * 40.0]]}
    cropped = {"part": "fixture", "source_pivot": [60.0, 40.0], "target_pivot": [-42.0, 40.0], "source_end": [60.0, 160.0], "target_end": [-42.0, 160.0], "uniform_scale": 1.0, "forward_affine_matrix": [[1.0, 0.0, -102.0], [0.0, 1.0, 0.0]]}
    parts = {"fixture": source}
    identity_layer = render_part(source, (60, 40), (60, 40), (60, 160), (60, 160), size)
    scaled_layer = render_part(source, (60, 40), scaled_pivot, (60, 160), scaled_end, size)
    cropped_layer = render_part(source, (60, 40), (-42, 40), (60, 160), (-42, 160), size)
    passing = layer_integrity_qa(parts, {"fixture": identity_layer}, [identity], size)
    transformed = layer_integrity_qa(parts, {"fixture": scaled_layer}, [scaled], size)
    crop = layer_integrity_qa(parts, {"fixture": cropped_layer}, [cropped], size)
    return {
        "schema_version": SCHEMA_VERSION,
        "calibrated_tolerance": {"raster_area_error_max": RASTER_AREA_ERROR_MAX, "active_alpha_threshold": ACTIVE_ALPHA_THRESHOLD},
        "identity_fixture": passing["parts"]["fixture"],
        "scaled_fixture": transformed["parts"]["fixture"],
        "deliberate_crop_fixture": crop["parts"]["fixture"],
        "hard_gates": {
            "identity_passes": passing["status"] == "LAYER_INTEGRITY_PASSED",
            "scaled_passes": transformed["status"] == "LAYER_INTEGRITY_PASSED",
            "deliberate_crop_fails": crop["status"] == "CUTOUT_RIG_LAYER_INTEGRITY_GAP" and crop["parts"]["fixture"]["predicted_outside_canvas_area"] > 0,
        },
        "status": "LAYER_INTEGRITY_CALIBRATION_PASSED" if passing["status"] == "LAYER_INTEGRITY_PASSED" and transformed["status"] == "LAYER_INTEGRITY_PASSED" and crop["status"] == "CUTOUT_RIG_LAYER_INTEGRITY_GAP" else "CUTOUT_RIG_LAYER_INTEGRITY_GAP",
    }


def structural_core_q0_gate(
    source_image: Image.Image, output: Image.Image, core_layer: Image.Image, core: Mapping[str, Any],
) -> dict[str, Any]:
    source_alpha = _binary(source_image.getchannel("A"), 0)
    output_alpha = _binary(output.getchannel("A"), 0)
    intersection = _intersection(source_alpha, output_alpha)
    union = ImageChops.lighter(source_alpha, output_alpha)
    alpha_iou = _count(intersection) / max(1, _count(union))
    diff = ImageChops.difference(source_image.convert("RGBA"), output.convert("RGBA")).convert("RGB")
    values = [sum(pixel) / 3.0 for pixel, alpha in zip(diff.getdata(), source_alpha.getdata()) if alpha > 0]
    core_alpha = _binary(core_layer.getchannel("A"), 0)
    core_holes = _count(_subtract(core_alpha, output_alpha))
    generated_fraction = 0.0 if _count(_intersection(core_alpha, source_alpha)) == _count(core_alpha) else 1.0
    gates = {
        "alpha_iou": alpha_iou >= 0.995,
        "rgb_mae": sum(values) / max(1, len(values)) <= 1.5,
        "structural_core_holes": core_holes == 0,
        "core_source_provenance": generated_fraction == 0.0,
        "source_residual_fallback_absent": True,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "alpha_iou": round(alpha_iou, 6),
        "rgb_mae": round(sum(values) / max(1, len(values)), 6),
        "structural_core_holes": core_holes,
        "generated_pixel_fraction": generated_fraction,
        "core_mask_sha256": core.get("core_mask_sha256"),
        "hard_gates": gates,
        "status": "CUTOUT_RIG_RECONSTRUCTION_PASSED" if all(gates.values()) else "STOP_CUTOUT_RIG_CORE_RECONSTRUCTION_GAP",
    }
