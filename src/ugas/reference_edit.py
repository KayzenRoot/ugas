"""Reference-edit contracts, deterministic recolour and appearance fidelity QA.

This module intentionally keeps visual appearance gates separate from silhouette
geometry.  A reference edit can preserve a silhouette while changing the face,
skin exposure or the whole image luminance; those failures must be visible to
the machine-readable gate.
"""

from __future__ import annotations

import colorsys
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any, Mapping

from .image_utils import sha256


class ReferenceEditError(RuntimeError):
    """A malformed contract or impossible reference-edit operation."""


DEFAULT_CONTRACT_THRESHOLDS: dict[str, float] = {
    "silhouette_iou_min": 0.90,
    "centroid_drift_max": 0.025,
    "bbox_scale_delta_max": 0.05,
    "foreground_luma_ratio_min": 0.88,
    "foreground_luma_ratio_max": 1.12,
    "foreground_luma_mae_max": 18.0,
    "head_luma_ratio_min": 0.90,
    "head_luma_ratio_max": 1.10,
    "head_luma_mae_max": 12.0,
    "head_changed_fraction_max": 0.12,
    "protected_rgb_mae_max": 10.0,
    "protected_changed_fraction_max": 0.18,
    "max_global_change_fraction": 0.20,
    "target_changed_fraction_min": 0.10,
    "target_hue_distance_max": 0.40,
    "runtime_plausibility_ratio_min": 0.25,
}


def contract_sha256(contract: Mapping[str, Any]) -> str:
    payload = json.dumps(contract, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_edit_contract(
    *,
    asset_id: str,
    source_revision_id: str,
    source_sha256: str,
    instruction: str = "Change armor color/material tint from blue steel to deep cobalt/navy steel.",
    candidate_count: int = 4,
    seeds: list[int] | None = None,
    preferred_route: str = "deterministic-then-generative",
) -> dict[str, Any]:
    if candidate_count < 1 or candidate_count > 6:
        raise ReferenceEditError("candidate_count must be between 1 and 6")
    values = list(seeds or [])
    if values and len(values) != candidate_count:
        raise ReferenceEditError("seeds length must equal candidate_count")
    contract = {
        "schema_version": "0.4.3",
        "contract_id": f"reference-edit-contract-{hashlib.sha256(f'{asset_id}:{source_revision_id}'.encode()).hexdigest()[:16]}",
        "asset_id": asset_id,
        "source_revision_id": source_revision_id,
        "source_sha256": source_sha256,
        "edit_type": "reference-edit-color-only",
        "requested_change": instruction,
        "target_property": "armor color/material tint",
        "allowed_changes": ["blue steel armor -> deep cobalt/navy steel armor tint"],
        "protected_properties": [
            "face identity", "skin tone", "facial exposure and lighting", "hair", "body proportions",
            "exact pose", "camera", "silhouette", "sword shape and position", "black cloth",
            "global background and composition before background removal",
        ],
        "protected_regions": ["head/face/skin", "hair", "sword", "black cloth", "non-target foreground", "background"],
        "preserve_identity": True,
        "preserve_pose": True,
        "preserve_camera": True,
        "preserve_silhouette": True,
        "preserve_exposure": True,
        "preserve_skin_face": True,
        "target_mask_policy": {
            "space": "HSV with alpha foreground restriction",
            "hue_range_degrees": [170, 285],
            "minimum_saturation": 0.20,
            "blue_dominance": "B >= R*1.05 and B >= G*0.90",
            "exclude_sword_like_component": "8-connected component >=500 px, height/width >=2.35, left-side and lower-canvas extent",
            "confidence_min": 0.40,
            "transformation": "set hue near 220 degrees, preserve value/luminance and texture, raise saturation only as needed",
        },
        "protected_mask_policy": {
            "head": "top-central 32 percent of alpha foreground bbox, expanded by 4 percent of canvas",
            "outside_target": "foreground alpha excluding target mask",
        },
        "thresholds": dict(DEFAULT_CONTRACT_THRESHOLDS),
        "candidate_count": candidate_count,
        "seeds": values,
        "preferred_route": preferred_route,
        "human_review_required": True,
        "created_by": "UGAS-03E",
    }
    validate_edit_contract(contract)
    return contract


def validate_edit_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version", "asset_id", "source_revision_id", "source_sha256", "edit_type", "requested_change",
        "target_property", "allowed_changes", "protected_properties", "protected_regions", "preserve_identity",
        "preserve_pose", "preserve_camera", "preserve_silhouette", "preserve_exposure", "preserve_skin_face",
        "target_mask_policy", "protected_mask_policy", "thresholds", "candidate_count", "seeds", "preferred_route",
    }
    missing = sorted(required - set(contract))
    if missing:
        raise ReferenceEditError("edit contract missing fields: " + ", ".join(missing))
    if str(contract["schema_version"]) != "0.4.3":
        raise ReferenceEditError("reference-edit contract must use schema version 0.4.3")
    if not all(bool(contract[name]) for name in ("preserve_identity", "preserve_pose", "preserve_camera", "preserve_silhouette", "preserve_exposure", "preserve_skin_face")):
        raise ReferenceEditError("identity, pose, camera, silhouette and exposure protections are mandatory")
    count = int(contract["candidate_count"])
    seeds = list(contract["seeds"])
    if not 1 <= count <= 6 or (seeds and len(seeds) != count) or len(set(seeds)) != len(seeds):
        raise ReferenceEditError("candidate count/seeds are invalid")
    thresholds = dict(DEFAULT_CONTRACT_THRESHOLDS)
    thresholds.update({str(key): float(value) for key, value in dict(contract["thresholds"]).items()})
    if not 0.0 < thresholds["silhouette_iou_min"] <= 1.0 or thresholds["centroid_drift_max"] <= 0:
        raise ReferenceEditError("structural thresholds are invalid")
    return {"valid": True, "schema_version": "0.4.3", "contract_sha256": contract_sha256(contract), "thresholds": thresholds}


def _rgba(path: Path):
    from PIL import Image
    with Image.open(path) as opened:
        return opened.convert("RGBA")


def _luma(rgb: tuple[int, int, int]) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _foreground_mask(image, alpha_threshold: int = 8):
    from PIL import Image
    alpha = image.getchannel("A")
    return alpha.point(lambda value: 255 if value > alpha_threshold else 0, mode="L")


def _target_mask(image, contract: Mapping[str, Any]):
    from PIL import Image
    policy = contract["target_mask_policy"]
    low, high = map(float, policy["hue_range_degrees"])
    min_sat = float(policy["minimum_saturation"])
    pixels = image.load()
    mask = Image.new("L", image.size, 0)
    values = mask.load()
    total_foreground = 0
    matches = 0
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if a <= 8:
                continue
            total_foreground += 1
            h, saturation, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            degrees = h * 360
            hue_ok = low <= degrees <= high if low <= high else degrees >= low or degrees <= high
            blue_ok = b >= r * 1.05 and b >= g * 0.90
            if hue_ok and saturation >= min_sat and blue_ok:
                values[x, y] = 255
                matches += 1
    # A blue-grey sword can satisfy the colour predicate while not being
    # armour. Remove a connected, slender, left-side component so the
    # deterministic route cannot recolour the protected weapon.
    points = {(x, y) for y in range(image.height) for x in range(image.width) if values[x, y] > 8}
    visited: set[tuple[int, int]] = set()
    for start in list(points):
        if start in visited:
            continue
        queue = [start]; component: list[tuple[int, int]] = []; visited.add(start)
        while queue:
            x, y = queue.pop(); component.append((x, y))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                neighbor = (x + dx, y + dy)
                if neighbor in points and neighbor not in visited:
                    visited.add(neighbor); queue.append(neighbor)
        xs = [point[0] for point in component]; ys = [point[1] for point in component]
        box_width, box_height = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        sword_like = len(component) >= 500 and box_height / max(1, box_width) >= 2.35 and min(xs) < image.width * 0.48 and max(ys) > image.height * 0.70
        if sword_like:
            for x, y in component:
                values[x, y] = 0
            matches -= len(component)
    confidence = matches / max(1, total_foreground)
    return mask, {"foreground_pixels": total_foreground, "target_pixels": matches, "confidence": round(confidence, 6), "threshold": float(policy["confidence_min"]), "uncertain": confidence < float(policy["confidence_min"])}


def build_target_mask(source: Path, contract: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    from PIL import Image
    validate_edit_contract(contract)
    image = _rgba(Path(source))
    mask, info = _target_mask(image, contract)
    destination = Path(source).with_name(Path(source).stem + "-target-mask.png")
    mask.save(destination, format="PNG", optimize=False)
    info.update({"path": str(destination), "sha256": sha256(destination), "policy": contract["target_mask_policy"]})
    return destination, info


def _head_mask(image):
    from PIL import Image, ImageDraw
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    mask = Image.new("L", image.size, 0)
    if not bbox:
        return mask, {"bbox": None, "region": None}
    left, top, right, bottom = bbox
    width, height = right - left, bottom - top
    expand = max(1, round(max(image.width, image.height) * 0.04))
    head_bottom = top + max(1, round(height * 0.32))
    head_left = max(0, left - expand)
    head_right = min(image.width, right + expand)
    head_top = max(0, top - expand)
    head_bottom = min(image.height, head_bottom + expand)
    ImageDraw.Draw(mask).rectangle((head_left, head_top, head_right - 1, head_bottom - 1), fill=255)
    mask = Image.composite(mask, Image.new("L", image.size, 0), alpha)
    return mask, {"bbox": list(bbox), "region": [head_left, head_top, head_right, head_bottom]}


def build_protected_mask(source: Path, contract: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    from PIL import Image, ImageChops
    validate_edit_contract(contract)
    image = _rgba(Path(source))
    mask, info = _head_mask(image)
    target, _ = _target_mask(image, contract)
    mask = ImageChops.subtract(mask, target)
    destination = Path(source).with_name(Path(source).stem + "-protected-mask.png")
    mask.save(destination, format="PNG", optimize=False)
    info.update({"path": str(destination), "sha256": sha256(destination), "policy": contract["protected_mask_policy"]})
    return destination, info


def deterministic_recolor(source: Path, destination: Path, target_mask: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    """Recolour only the high-confidence target mask while preserving RGB value/texture."""
    from PIL import Image
    validation = validate_edit_contract(contract)
    if not Path(target_mask).is_file():
        raise ReferenceEditError("target mask does not exist")
    with Image.open(source) as opened, Image.open(target_mask) as mask_opened:
        image = opened.convert("RGBA")
        mask = mask_opened.convert("L")
        if image.size != mask.size:
            raise ReferenceEditError("target mask dimensions differ from source")
        target_pixels = sum(value > 8 for value in mask.getdata())
        foreground_pixels = sum(value > 8 for value in image.getchannel("A").getdata())
        confidence = target_pixels / max(1, foreground_pixels)
        if confidence < float(contract["target_mask_policy"]["confidence_min"]):
            raise ReferenceEditError("TARGET_MASK_UNCERTAIN: target mask confidence is below the contract threshold")
        result = image.copy()
        source_pixels = image.load(); result_pixels = result.load(); mask_pixels = mask.load()
        changed = 0
        for y in range(image.height):
            for x in range(image.width):
                if mask_pixels[x, y] <= 8:
                    continue
                r, g, b, a = source_pixels[x, y]
                hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                new_hue = 220 / 360
                new_saturation = min(1.0, max(saturation, 0.45))
                nr, ng, nb = colorsys.hsv_to_rgb(new_hue, new_saturation, value)
                original_luma = _luma((r, g, b))
                recolored_luma = _luma((nr * 255, ng * 255, nb * 255))
                scale = original_luma / max(1e-6, recolored_luma)
                result_pixels[x, y] = (min(255, round(nr * 255 * scale)), min(255, round(ng * 255 * scale)), min(255, round(nb * 255 * scale)), a)
                changed += 1
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        result.convert("RGB").save(destination, format="PNG", optimize=False)
    return {
        "status": "DETERMINISTIC_RECOLOR_GENERATED",
        "route": "deterministic-recolor",
        "source_path": str(source),
        "source_sha256": sha256(Path(source)),
        "output_path": str(destination),
        "output_sha256": sha256(destination),
        "target_mask_path": str(target_mask),
        "target_mask_sha256": sha256(Path(target_mask)),
        "target_pixels": target_pixels,
        "foreground_pixels": foreground_pixels,
        "target_confidence": round(confidence, 6),
        "changed_pixels": changed,
        "transformation": contract["target_mask_policy"]["transformation"],
        "outside_target_bit_for_bit": True,
        "contract_sha256": validation["contract_sha256"],
    }


def _points(mask) -> set[tuple[int, int]]:
    return {(x, y) for y in range(mask.height) for x in range(mask.width) if mask.getpixel((x, y)) > 8}


def _geometry(mask) -> dict[str, Any]:
    points = _points(mask)
    if not points:
        return {"bbox": None, "centroid": None, "area": 0}
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {"bbox": [min(xs), min(ys), max(xs) + 1, max(ys) + 1], "centroid": [sum(xs) / len(xs) / mask.width, sum(ys) / len(ys) / mask.height], "area": len(points)}


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p05": None, "p25": None, "p50": None, "p75": None, "p95": None}
    ordered = sorted(values)
    def percentile(p: float) -> float:
        index = (len(ordered) - 1) * p
        low, high = math.floor(index), math.ceil(index)
        if low == high:
            return ordered[low]
        return ordered[low] + (ordered[high] - ordered[low]) * (index - low)
    return {f"p{int(p * 100):02d}": round(percentile(p), 6) for p in (0.05, 0.25, 0.50, 0.75, 0.95)}


def _pixel_stats(source, candidate, mask) -> dict[str, Any]:
    source_pixels, candidate_pixels, mask_pixels = source.load(), candidate.load(), mask.load()
    source_luma: list[float] = []
    candidate_luma: list[float] = []
    rgb_errors: list[float] = []
    changed = 0
    total = 0
    for y in range(source.height):
        for x in range(source.width):
            if mask_pixels[x, y] <= 8:
                continue
            sr, sg, sb, _ = source_pixels[x, y]
            cr, cg, cb, _ = candidate_pixels[x, y]
            source_luma.append(_luma((sr, sg, sb)))
            candidate_luma.append(_luma((cr, cg, cb)))
            error = (abs(sr - cr) + abs(sg - cg) + abs(sb - cb)) / 3
            rgb_errors.append(error)
            changed += error > 3.0
            total += 1
    source_mean = statistics.fmean(source_luma) if source_luma else 0.0
    candidate_mean = statistics.fmean(candidate_luma) if candidate_luma else 0.0
    return {
        "pixels": total,
        "source_luma_mean": round(source_mean, 6),
        "candidate_luma_mean": round(candidate_mean, 6),
        "luma_ratio": round(candidate_mean / max(1e-6, source_mean), 6),
        "luma_mae": round(statistics.fmean(abs(a - b) for a, b in zip(source_luma, candidate_luma)), 6) if source_luma else None,
        "source_luma_percentiles": _percentiles(source_luma),
        "candidate_luma_percentiles": _percentiles(candidate_luma),
        "rgb_mae": round(statistics.fmean(rgb_errors), 6) if rgb_errors else None,
        "changed_fraction": round(changed / max(1, total), 6),
    }


def _mask_from_image(image, *, alpha: bool = True):
    return _foreground_mask(image) if alpha else image.convert("L")


def reference_edit_fidelity(
    source: Path,
    candidate: Path,
    contract: Mapping[str, Any],
    *,
    target_mask: Path | None = None,
    protected_mask: Path | None = None,
    source_revision_id: str | None = None,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    """Run structural, global photometric, head and protected-region gates."""
    from PIL import Image, ImageChops
    validation = validate_edit_contract(contract)
    limits = validation["thresholds"]
    source = Path(source).resolve(); candidate = Path(candidate).resolve()
    result: dict[str, Any] = {
        "schema_version": "0.4.3",
        "candidate_id": candidate_id,
        "source_revision_id": source_revision_id,
        "source_path": str(source),
        "candidate_path": str(candidate),
        "source_sha256": sha256(source) if source.is_file() else None,
        "candidate_sha256": sha256(candidate) if candidate.is_file() else None,
        "contract_sha256": validation["contract_sha256"],
        "thresholds": limits,
    }
    if not source.is_file() or not candidate.is_file():
        result.update({"status": "REFERENCE_EDIT_FIDELITY_FAILED", "failure_reasons": ["source_or_candidate_missing"]})
        return result
    with Image.open(source) as source_opened, Image.open(candidate) as candidate_opened:
        source_image, candidate_image = source_opened.convert("RGBA"), candidate_opened.convert("RGBA")
        if source_image.size != candidate_image.size:
            result.update({"status": "REFERENCE_EDIT_FIDELITY_FAILED", "failure_reasons": ["dimension_mismatch"]})
            return result
        source_mask = _foreground_mask(source_image)
        candidate_mask = _foreground_mask(candidate_image)
        source_points, candidate_points = _points(source_mask), _points(candidate_mask)
        union = source_points | candidate_points
        intersection = source_points & candidate_points
        iou = len(intersection) / max(1, len(union))
        source_geo, candidate_geo = _geometry(source_mask), _geometry(candidate_mask)
        source_centroid = source_geo["centroid"] or [1.0, 1.0]
        candidate_centroid = candidate_geo["centroid"] or [1.0, 1.0]
        centroid_drift = max(abs(source_centroid[0] - candidate_centroid[0]), abs(source_centroid[1] - candidate_centroid[1]))
        source_bbox, candidate_bbox = source_geo["bbox"], candidate_geo["bbox"]
        source_area = max(1, (source_bbox[2] - source_bbox[0]) * (source_bbox[3] - source_bbox[1])) if source_bbox else 1
        candidate_area = ((candidate_bbox[2] - candidate_bbox[0]) * (candidate_bbox[3] - candidate_bbox[1])) if candidate_bbox else 0
        bbox_delta = abs(candidate_area - source_area) / source_area
        if target_mask and Path(target_mask).is_file():
            target = Image.open(target_mask).convert("L")
        else:
            target, target_info = _target_mask(source_image, contract)
        if protected_mask and Path(protected_mask).is_file():
            protected = Image.open(protected_mask).convert("L")
        else:
            protected, _ = _head_mask(source_image)
        if target.size != source_image.size or protected.size != source_image.size:
            result.update({"status": "REFERENCE_EDIT_FIDELITY_FAILED", "failure_reasons": ["mask_dimension_mismatch"]})
            return result
        alpha = source_image.getchannel("A")
        foreground = _foreground_mask(source_image)
        non_target = ImageChops.subtract(foreground, target)
        source_luma = _pixel_stats(source_image, source_image, foreground)
        candidate_luma = _pixel_stats(source_image, candidate_image, foreground)
        head_stats = _pixel_stats(source_image, candidate_image, protected)
        protected_stats = _pixel_stats(source_image, candidate_image, non_target)
        target_stats = _pixel_stats(source_image, candidate_image, target)
        direction_values: list[float] = []
        source_target_hues: list[float] = []
        candidate_target_hues: list[float] = []
        for x, y in _points(target):
            sr, sg, sb, _ = source_image.getpixel((x, y)); cr, cg, cb, _ = candidate_image.getpixel((x, y))
            sh, _, _ = colorsys.rgb_to_hsv(sr / 255, sg / 255, sb / 255)
            ch, _, _ = colorsys.rgb_to_hsv(cr / 255, cg / 255, cb / 255)
            source_target_hues.append(sh); candidate_target_hues.append(ch)
            direction_values.append((cb - cr) - (sb - sr))
        target_mean_hue = statistics.fmean(candidate_target_hues) if candidate_target_hues else None
        hue_distance = min(abs((target_mean_hue or 0) - 220 / 360), 1 - abs((target_mean_hue or 0) - 220 / 360)) if target_mean_hue is not None else 1.0
        changed_target = target_stats["changed_fraction"]
        global_changed = source_luma["changed_fraction"]
        checks = {
            "silhouette_iou": iou >= limits["silhouette_iou_min"],
            "centroid_drift": centroid_drift <= limits["centroid_drift_max"],
            "bbox_scale_delta": bbox_delta <= limits["bbox_scale_delta_max"],
            "not_pixel_identical": result["source_sha256"] != result["candidate_sha256"],
            "foreground_luma_ratio": limits["foreground_luma_ratio_min"] <= candidate_luma["luma_ratio"] <= limits["foreground_luma_ratio_max"],
            "foreground_luma_mae": (candidate_luma["luma_mae"] if candidate_luma["luma_mae"] is not None else 999) <= limits["foreground_luma_mae_max"],
            "head_luma_ratio": limits["head_luma_ratio_min"] <= head_stats["luma_ratio"] <= limits["head_luma_ratio_max"],
            "head_luma_mae": (head_stats["luma_mae"] if head_stats["luma_mae"] is not None else 999) <= limits["head_luma_mae_max"],
            "head_changed_fraction": head_stats["changed_fraction"] <= limits["head_changed_fraction_max"],
            "protected_rgb_mae": (protected_stats["rgb_mae"] if protected_stats["rgb_mae"] is not None else 999) <= limits["protected_rgb_mae_max"],
            "protected_changed_fraction": protected_stats["changed_fraction"] <= limits["protected_changed_fraction_max"],
            "global_change_fraction": global_changed <= limits["max_global_change_fraction"],
            "target_changed": changed_target >= limits["target_changed_fraction_min"],
            "target_hue_direction": bool(direction_values) and statistics.fmean(direction_values) > 0,
            "target_hue_destination": bool(candidate_target_hues) and hue_distance <= limits["target_hue_distance_max"],
        }
        result.update({
            "status": "REFERENCE_EDIT_FIDELITY_PASSED" if all(checks.values()) else "REFERENCE_EDIT_FIDELITY_FAILED",
            "failure_reasons": [name for name, passed in checks.items() if not passed],
            "checks": checks,
            "structural": {"source": source_geo, "candidate": candidate_geo, "silhouette_iou": round(iou, 6), "centroid_drift": round(centroid_drift, 6), "bbox_scale_delta": round(bbox_delta, 6)},
            "appearance": {"foreground": candidate_luma, "source_foreground": source_luma, "head": head_stats, "protected_outside_target": protected_stats, "target": target_stats, "target_candidate_mean_hue": round(target_mean_hue, 6) if target_mean_hue is not None else None, "target_hue_distance_to_220": round(hue_distance, 6), "target_direction_score": round(statistics.fmean(direction_values), 6) if direction_values else None, "global_changed_fraction": global_changed},
            "target_mask": {"path": str(target_mask) if target_mask else None, "sha256": sha256(Path(target_mask)) if target_mask and Path(target_mask).is_file() else None, "pixels": len(_points(target))},
            "protected_mask": {"path": str(protected_mask) if protected_mask else None, "sha256": sha256(Path(protected_mask)) if protected_mask and Path(protected_mask).is_file() else None, "pixels": len(_points(protected))},
            "human_review": "required",
            "production_ready": False,
        })
    return result


def runtime_plausibility(runtime_ms: int | float, benchmark_runtimes: list[int | float], *, min_ratio: float = 0.25) -> dict[str, Any]:
    values = [float(value) for value in benchmark_runtimes if float(value) > 0]
    median = statistics.median(values) if values else None
    ratio = float(runtime_ms) / median if median else None
    suspicious = bool(median and ratio is not None and ratio < min_ratio)
    return {"runtime_ms": round(float(runtime_ms), 3), "benchmark_runtimes_ms": [round(value, 3) for value in values], "benchmark_median_ms": round(median, 3) if median else None, "ratio_to_median": round(ratio, 6) if ratio is not None else None, "minimum_ratio": min_ratio, "status": "SUSPICIOUS_EXECUTION_EVIDENCE" if suspicious else "RUNTIME_PLAUSIBLE", "cache_explanation_required": suspicious}


def validate_execution_evidence(evidence: Mapping[str, Any], *, previously_used_seeds: set[int] | None = None) -> dict[str, Any]:
    """Validate exact job/history/output binding before evidence is accepted."""
    required = ("client_job_id", "prompt_id", "history_record_key", "runtime_ms", "seed", "outputs", "fresh_binding")
    failures = [name for name in required if not evidence.get(name)]
    failures.extend(["history_prompt_mismatch"] if evidence.get("history_record_key") != evidence.get("prompt_id") or evidence.get("history_key_matches_prompt_id") is not True else [])
    failures.extend(["stale_output"] if evidence.get("target_existed_before_submission") is not False else [])
    failures.extend(["fresh_binding_false"] if evidence.get("fresh_binding") is not True else [])
    if previously_used_seeds and int(evidence.get("seed", -1)) in previously_used_seeds:
        failures.append("seed_reused")
    plausibility = evidence.get("runtime_plausibility", {})
    if plausibility.get("status") == "SUSPICIOUS_EXECUTION_EVIDENCE" and not evidence.get("cache", {}).get("authoritative_explanation"):
        failures.append("suspicious_runtime_without_cache_explanation")
    return {"status": "FRESH_EXECUTION_EVIDENCE_PASSED" if not failures else "FRESH_EXECUTION_EVIDENCE_FAILED", "failures": sorted(set(failures))}
