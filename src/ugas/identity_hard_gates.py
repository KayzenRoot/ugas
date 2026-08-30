"""Deterministic identity hard gates for the v0.6.1 SDXL smoke correction."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Mapping


ALPHA_THRESHOLD = 48
MIN_COMPONENT_AREA = 32
SECONDARY_BODY_AREA_RATIO = 0.25
SECONDARY_BODY_HEIGHT_RATIO = 0.35
SECONDARY_BODY_WIDTH_RATIO = 0.35
REGION_THRESHOLD = 0.45
BODY_PROPORTION_THRESHOLD = 0.55


def _components(path: Path, *, alpha_threshold: int = ALPHA_THRESHOLD) -> list[dict[str, Any]]:
    from PIL import Image

    with Image.open(path) as source:
        alpha = source.convert("RGBA").getchannel("A")
        width, height = alpha.size
        pixels = alpha.load()
        visited: set[tuple[int, int]] = set()
        result: list[dict[str, Any]] = []
        for y in range(height):
            for x in range(width):
                if (x, y) in visited or pixels[x, y] < alpha_threshold:
                    continue
                queue: deque[tuple[int, int]] = deque([(x, y)])
                visited.add((x, y))
                points: list[tuple[int, int]] = []
                while queue:
                    current_x, current_y = queue.popleft()
                    points.append((current_x, current_y))
                    for next_x, next_y in (
                        (current_x - 1, current_y), (current_x + 1, current_y),
                        (current_x, current_y - 1), (current_x, current_y + 1),
                        (current_x - 1, current_y - 1), (current_x + 1, current_y - 1),
                        (current_x - 1, current_y + 1), (current_x + 1, current_y + 1),
                    ):
                        if (
                            0 <= next_x < width
                            and 0 <= next_y < height
                            and (next_x, next_y) not in visited
                            and pixels[next_x, next_y] >= alpha_threshold
                        ):
                            visited.add((next_x, next_y))
                            queue.append((next_x, next_y))
                if len(points) < MIN_COMPONENT_AREA:
                    continue
                xs = [point[0] for point in points]
                ys = [point[1] for point in points]
                bbox = [min(xs), min(ys), max(xs) + 1, max(ys) + 1]
                result.append({
                    "area": len(points),
                    "relative_area": round(len(points) / max(1, width * height), 6),
                    "bbox": bbox,
                    "width": bbox[2] - bbox[0],
                    "height": bbox[3] - bbox[1],
                })
    return sorted(result, key=lambda item: (-int(item["area"]), item["bbox"]))


def analyze_foreground_components(path: Path) -> dict[str, Any]:
    """Classify body-sized secondary foreground without counting small weapons."""
    components = _components(path)
    primary = components[0] if components else None
    if primary is None:
        return {
            "alpha_threshold": ALPHA_THRESHOLD,
            "minimum_component_area": MIN_COMPONENT_AREA,
            "secondary_body_area_ratio_threshold": SECONDARY_BODY_AREA_RATIO,
            "large_foreground_components": 0,
            "components": [],
            "secondary_to_primary_area_ratio": 0.0,
            "multiple_subjects_detected": False,
            "single_subject_pass": False,
            "classification": "NO_FOREGROUND",
        }

    secondary: list[dict[str, Any]] = []
    accessories: list[dict[str, Any]] = []
    for item in components[1:]:
        area_ratio = float(item["area"]) / max(1, float(primary["area"]))
        body_sized = (
            area_ratio >= SECONDARY_BODY_AREA_RATIO
            and float(item["height"]) >= float(primary["height"]) * SECONDARY_BODY_HEIGHT_RATIO
            and float(item["width"]) >= float(primary["width"]) * SECONDARY_BODY_WIDTH_RATIO
        )
        if body_sized:
            secondary.append({**item, "area_ratio_to_primary": round(area_ratio, 6), "classification": "body-sized"})
        else:
            accessories.append({**item, "area_ratio_to_primary": round(area_ratio, 6), "classification": "small-accessory-or-weapon"})
    ratio = float(secondary[0]["area_ratio_to_primary"]) if secondary else 0.0
    return {
        "alpha_threshold": ALPHA_THRESHOLD,
        "minimum_component_area": MIN_COMPONENT_AREA,
        "secondary_body_area_ratio_threshold": SECONDARY_BODY_AREA_RATIO,
        "secondary_body_height_ratio_threshold": SECONDARY_BODY_HEIGHT_RATIO,
        "secondary_body_width_ratio_threshold": SECONDARY_BODY_WIDTH_RATIO,
        "large_foreground_components": 1 + len(secondary),
        "components": components,
        "secondary_body_components": secondary,
        "accessory_or_weapon_components": accessories,
        "secondary_to_primary_area_ratio": round(ratio, 6),
        "multiple_subjects_detected": bool(secondary),
        "single_subject_pass": not secondary,
        "classification": "MULTIPLE_BODY_SUBJECTS" if secondary else "SINGLE_BODY_SUBJECT",
    }


def evaluate_identity_hard_gates(
    descriptor: Mapping[str, Any],
    foreground: Mapping[str, Any],
) -> dict[str, Any]:
    """Require every identity component and the single-subject gate to pass."""
    components = descriptor.get("components") if isinstance(descriptor.get("components"), Mapping) else {}
    failure_reasons = [str(item) for item in descriptor.get("failure_reasons", [])]
    score = float(descriptor.get("identity_descriptor_score", 0.0) or 0.0)
    threshold = float(descriptor.get("threshold", 0.0) or 0.0)
    aggregate_pass = score >= threshold
    weapon_pass = descriptor.get("weapon_present") is True
    gates = {
        "aggregate_score": aggregate_pass,
        "weapon": weapon_pass,
        "head_face": float(components.get("head_face", 0.0) or 0.0) >= REGION_THRESHOLD,
        "armor_palette": float(components.get("armor_palette_material", 0.0) or 0.0) >= REGION_THRESHOLD,
        "black_cloth": float(components.get("black_cloth", 0.0) or 0.0) >= REGION_THRESHOLD,
        "body_proportions": float(components.get("body_proportions", 0.0) or 0.0) >= BODY_PROPORTION_THRESHOLD,
        "single_subject": foreground.get("multiple_subjects_detected") is False,
    }
    reasons = list(failure_reasons)
    if not aggregate_pass and "identity_descriptor_below_threshold" not in reasons:
        reasons.append("identity_descriptor_below_threshold")
    if not weapon_pass and "weapon_missing_or_not_detected" not in reasons:
        reasons.append("weapon_missing_or_not_detected")
    reason_by_gate = {
        "head_face": "head_face_drift",
        "armor_palette": "armor_palette_drift",
        "black_cloth": "black_cloth_drift",
        "body_proportions": "body_proportion_drift",
    }
    for gate, reason in reason_by_gate.items():
        if not gates[gate] and reason not in reasons:
            reasons.append(reason)
    if not gates["single_subject"] and "multiple_subjects_detected" not in reasons:
        reasons.append("multiple_subjects_detected")
    return {
        "aggregate_score_pass": gates["aggregate_score"],
        "weapon_pass": gates["weapon"],
        "head_face_pass": gates["head_face"],
        "armor_palette_pass": gates["armor_palette"],
        "black_cloth_pass": gates["black_cloth"],
        "body_proportions_pass": gates["body_proportions"],
        "single_subject_pass": gates["single_subject"],
        "failure_reasons": sorted(set(reasons)),
        "identity_pass": not reasons and all(gates.values()),
        "hard_gate_policy": {
            "region_threshold": REGION_THRESHOLD,
            "body_proportion_threshold": BODY_PROPORTION_THRESHOLD,
            "score_cannot_compensate_for_component_failure": True,
        },
        "foreground": dict(foreground),
    }
