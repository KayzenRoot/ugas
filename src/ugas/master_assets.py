"""v0.4.2 master-sprite contracts, immutable revisions and quality gates."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Mapping

from .constants import UGAS_VERSION
from .image_utils import inspect_png, sha256


class MasterAssetError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_reference(path: Path) -> dict[str, str]:
    return {"name": path.name, "sha256": sha256(path)}


def _art_dna(profile: Mapping[str, Any], art_dna: Mapping[str, Any] | None) -> dict[str, Any]:
    if art_dna is not None:
        return json.loads(json.dumps(dict(art_dna), ensure_ascii=False))
    artistic = profile.get("artistic_parameters", {})
    return {
        "style_keywords": list(artistic.get("style_keywords", [])),
        "palette": artistic.get("palette", "project-defined"),
        "shape_language": artistic.get("shape_language", "project-defined"),
        "consistency_rules": list(artistic.get("consistency_rules", [])),
    }


@dataclass(frozen=True)
class MasterAssetSpec:
    """Serializable visual request plus machine-only composition constraints."""

    asset_id: str
    category: str
    subtype: str
    intended_view: str
    orientation: str
    game_profile: str
    art_dna: dict[str, Any]
    visual_style: str
    palette_intent: str
    outline_policy: str
    lighting: str
    detail_density: str
    canvas_target: dict[str, int]
    subject_occupancy_target: dict[str, float]
    margins: dict[str, int]
    pivot_intent: str
    requires_transparency: bool
    positive_prompt: str
    negative_constraints: list[str]
    reference_anchors: list[dict[str, str]]
    candidate_count: int
    seeds: list[int]
    generation_policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": UGAS_VERSION,
            "asset_id": self.asset_id,
            "category": self.category,
            "subtype": self.subtype,
            "intended_view": self.intended_view,
            "orientation": self.orientation,
            "game_profile": self.game_profile,
            "art_dna": self.art_dna,
            "visual_style": self.visual_style,
            "palette_intent": self.palette_intent,
            "outline_policy": self.outline_policy,
            "lighting": self.lighting,
            "detail_density": self.detail_density,
            "canvas_target": self.canvas_target,
            "subject_occupancy_target": self.subject_occupancy_target,
            "margins": self.margins,
            "pivot_intent": self.pivot_intent,
            "requires_transparency": self.requires_transparency,
            "positive_prompt": self.positive_prompt,
            "negative_constraints": self.negative_constraints,
            "reference_anchors": self.reference_anchors,
            "candidate_count": self.candidate_count,
            "seeds": self.seeds,
            "generation_policy": self.generation_policy,
        }


def make_master_spec(
    prompt: str,
    *,
    profile: Mapping[str, Any],
    profile_id: str,
    candidates: int = 4,
    seed: int = 1,
    width: int = 512,
    height: int = 512,
    requires_transparency: bool = False,
    references: list[Path] | None = None,
    asset_id: str | None = None,
) -> MasterAssetSpec:
    if not prompt.strip():
        raise MasterAssetError("master sprite prompt cannot be empty")
    if candidates < 1 or candidates > 6:
        raise MasterAssetError("candidates must be between 1 and 6")
    if width < 64 or height < 64:
        raise MasterAssetError("master canvas must be at least 64x64")
    dna = _art_dna(profile, None)
    keywords = dna.get("style_keywords") or ["stylized game art"]
    refs = [_hash_reference(path.resolve()) for path in references or []]
    seeds = [int(seed) + index for index in range(candidates)]
    return MasterAssetSpec(
        asset_id=asset_id or f"asset-{uuid.uuid4().hex}", category="character", subtype="master-sprite",
        intended_view="2d gameplay sprite",
        orientation="front-facing three-quarter" if "top-down" not in prompt.casefold() else "top-down three-quarter",
        game_profile=profile_id, art_dna=dna, visual_style=", ".join(str(item) for item in keywords),
        palette_intent=str(dna.get("palette", "project-defined")), outline_policy="clean readable silhouette with controlled outline",
        lighting="soft directional key light with readable rim separation", detail_density="medium-high at gameplay distance",
        canvas_target={"width": int(width), "height": int(height)}, subject_occupancy_target={"min": 0.20, "max": 0.82},
        margins={"left": 24, "top": 24, "right": 24, "bottom": 24}, pivot_intent="center-bottom of subject",
        requires_transparency=bool(requires_transparency), positive_prompt=prompt.strip(),
        negative_constraints=["multiple subjects", "cropped subject", "text or watermark", "extra limbs or duplicate equipment", "muddy silhouette", "motion blur or visual effects", "weapon crossing the torso"],
        reference_anchors=refs, candidate_count=candidates, seeds=seeds,
        generation_policy={
            "provider": "provider-comfyui", "quality_policy": "quality-first", "lane_order": ["quality", "fast"],
            "resolution_policy": "benchmark-512-preferred", "default_candidates": 4, "max_candidates": 6,
            "max_auto_retry_rounds": 2, "deterministic": True, "visual_approval": "pending",
            "reference_edit_qa": {"silhouette_iou_min": 0.70, "centroid_drift_max": 0.08, "bbox_scale_delta_max": 0.15, "allow_pixel_identical": False},
        },
    )


def compile_generation_prompt(spec: Mapping[str, Any], profile: Mapping[str, Any] | None = None, *, retry_reason: str | None = None) -> str:
    """Return only natural visual language; dimensions and QA stay in the spec."""
    dna = spec.get("art_dna", {})
    style = spec.get("visual_style") or ", ".join(map(str, dna.get("style_keywords", []))) or "cohesive stylized game art"
    subject = str(spec.get("positive_prompt", "")).strip()
    orientation = "three-quarter front view"
    if "top-down" in str(spec.get("orientation", "")).casefold():
        orientation = "top-down three-quarter view"
    prompt = ("Single full-body game character, neutral idle stance, entire body visible from head to feet, centered, "
        f"{orientation}, arms separated enough to read the silhouette, weapon held beside the body without crossing the torso, "
        "clean readable anatomy, generous empty space around the entire silhouette, simple contrasting background, no motion effects, no text, no cropped limbs. "
        f"{style}. {subject}")
    if retry_reason:
        prompt += f" Corrective pass: {retry_reason}."
        if "safe_margin" in retry_reason.casefold() or "margin" in retry_reason.casefold():
            prompt += " Make the character noticeably smaller than a typical portrait, with very large blank space around the silhouette; keep head, hands, sword and feet comfortably away from every edge, especially leave a deep blank area below the feet. Do not fill the canvas."
        if "edge_clipping" in retry_reason.casefold():
            prompt += " Keep the complete silhouette away from every canvas edge."
    return " ".join(prompt.split())


def compile_prompt(spec: Mapping[str, Any], profile: Mapping[str, Any] | None = None) -> str:
    return compile_generation_prompt(spec, profile)


def compile_reference_edit_instruction(instruction: str, spec: Mapping[str, Any] | None = None) -> str:
    change = " ".join(str(instruction).split())
    if not change:
        raise MasterAssetError("reference edit instruction cannot be empty")
    return (f"Change only this visual property: {change}. Keep the same character identity, face, body proportions, exact pose, "
        "camera angle, silhouette, weapon type and overall composition. Preserve the neutral idle stance, full-body framing, "
        "readable hands and weapon beside the body. Do not redesign the character, add subjects, crop limbs, add text or add motion effects.")


def prompt_sha256(compiled_prompt: str) -> str:
    return hashlib.sha256(compiled_prompt.encode("utf-8")).hexdigest()


def _foreground_bbox(path: Path) -> tuple[int, int, int, int] | None:
    from PIL import Image
    with Image.open(path) as source:
        image = source.convert("RGBA")
        alpha = image.getchannel("A")
        if "A" in source.getbands() and alpha.getextrema() != (255, 255):
            return alpha.getbbox()
        pixels = image.load(); sample = []
        for x in range(image.width): sample.extend((pixels[x, 0][:3], pixels[x, image.height - 1][:3]))
        for y in range(image.height): sample.extend((pixels[0, y][:3], pixels[image.width - 1, y][:3]))
        background = tuple(int(median([item[channel] for item in sample])) for channel in range(3))
        threshold = max(24, int(max(image.width, image.height) * 0.04)); points = []
        for y in range(image.height):
            for x in range(image.width):
                rgb = pixels[x, y][:3]
                if sum(abs(int(rgb[channel]) - background[channel]) for channel in range(3)) > threshold: points.append((x, y))
        if not points: return None
        xs = [point[0] for point in points]; ys = [point[1] for point in points]
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _average_hash(path: Path, size: int = 8) -> str:
    from PIL import Image, ImageOps
    with Image.open(path) as source: values = list(ImageOps.grayscale(source.convert("RGB")).resize((size, size)).getdata())
    average = sum(values) / len(values)
    return "".join("1" if value >= average else "0" for value in values)


def candidate_metrics(path: Path, *, width: int, height: int, requires_transparency: bool = False,
                      occupancy_target: Mapping[str, float] | None = None, centering_limit: float = 0.18,
                      duplicate: bool = False, max_bytes: int = 20 * 1024 * 1024,
                      margins: Mapping[str, int] | None = None) -> dict[str, Any]:
    try:
        info = inspect_png(path); bbox = _foreground_bbox(path)
    except Exception as exc:
        return {"eligible": False, "hard_gate_failures": ["invalid_png"], "hard_gates": {"valid_png": False}, "error": str(exc)}
    target = occupancy_target or {"min": 0.20, "max": 0.82}
    if bbox:
        left, top, right, bottom = bbox; box_width, box_height = right - left, bottom - top
        occupancy = (box_width * box_height) / max(1, width * height)
        center_offset = {"x": round(abs(((left + right) / 2) - width / 2) / max(1, width), 6), "y": round(abs(((top + bottom) / 2) - height / 2) / max(1, height), 6)}
        edge_clipping = left <= 0 or top <= 0 or right >= width or bottom >= height
    else:
        occupancy = 0.0; center_offset = {"x": 1.0, "y": 1.0}; edge_clipping = True
        left, top, right, bottom = 0, 0, 0, 0
    declared_margins = {"left": 0, "top": 0, "right": 0, "bottom": 0}
    declared_margins.update({key: int(value) for key, value in (margins or {}).items() if key in declared_margins})
    safe_margin_violations: list[str] = []
    if bbox:
        if left < declared_margins["left"]: safe_margin_violations.append("left")
        if top < declared_margins["top"]: safe_margin_violations.append("top")
        if right > width - declared_margins["right"]: safe_margin_violations.append("right")
        if bottom > height - declared_margins["bottom"]: safe_margin_violations.append("bottom")
    else:
        safe_margin_violations = ["missing_foreground"]
    safe_margin_ok = not safe_margin_violations
    alpha_ok = not requires_transparency or info.get("has_transparent_pixels", False)
    gates = {
        "valid_png": info.get("format") == "PNG", "dimensions": info.get("width") == width and info.get("height") == height,
        "non_empty": bool(info.get("non_empty_content")), "not_duplicate": not duplicate, "edge_clipping": not edge_clipping,
        "safe_margin": safe_margin_ok,
        "occupancy": float(target.get("min", 0.20)) <= occupancy <= float(target.get("max", 0.82)),
        "centered": center_offset["x"] <= centering_limit and center_offset["y"] <= centering_limit,
        "file_size": info.get("bytes", max_bytes + 1) <= max_bytes, "alpha": alpha_ok,
    }
    failures = [name for name, passed in gates.items() if not passed]
    return {"foreground_bbox": list(bbox) if bbox else None, "occupancy": round(occupancy, 6), "occupancy_target": dict(target),
        "margins": declared_margins, "safe_margin_ok": safe_margin_ok, "safe_margin_violations": safe_margin_violations,
        "occupancy_ok": gates["occupancy"], "center_offset": center_offset, "centered_ok": gates["centered"],
        "edge_clipping": edge_clipping, "edge_clipping_ok": gates["edge_clipping"], "alpha_ok": alpha_ok,
        "perceptual_hash": _average_hash(path), "file_size_ok": gates["file_size"], "hard_gates": gates,
        "hard_gate_failures": failures, "eligible": not failures}


def detect_halo(path: Path) -> dict[str, Any]:
    from PIL import Image
    with Image.open(path) as source:
        image = source.convert("RGBA"); alpha = image.getchannel("A")
        if alpha.getextrema()[0] == 255: return {"checked": False, "halo_detected": False, "reason": "no transparency"}
        border = []
        for x in range(image.width): border.extend([alpha.getpixel((x, 0)), alpha.getpixel((x, image.height - 1))])
        for y in range(image.height): border.extend([alpha.getpixel((0, y)), alpha.getpixel((image.width - 1, y))])
        fraction = sum(0 < value < 255 for value in border) / max(1, len(border))
        return {"checked": True, "border_semi_transparent_fraction": round(fraction, 6), "halo_detected": fraction > 0.35}


def _mask_points(path: Path, size: int = 128) -> set[tuple[int, int]]:
    from PIL import Image
    with Image.open(path) as source:
        image = source.convert("RGBA"); alpha = image.getchannel("A")
        if "A" not in source.getbands() or alpha.getextrema() == (255, 255):
            bbox = _foreground_bbox(path)
            if not bbox: return set()
            left, top, right, bottom = bbox
            return {(x, y) for y in range(round(top / image.height * size), round(bottom / image.height * size)) for x in range(round(left / image.width * size), round(right / image.width * size))}
        mask = alpha.resize((size, size))
        return {(x, y) for y in range(size) for x in range(size) if mask.getpixel((x, y)) > 8}


def _mask_geometry(points: set[tuple[int, int]], size: int = 128) -> dict[str, Any]:
    if not points: return {"bbox": None, "centroid": None, "area": 0}
    xs = [point[0] for point in points]; ys = [point[1] for point in points]
    return {"bbox": [min(xs), min(ys), max(xs) + 1, max(ys) + 1], "centroid": [sum(xs) / len(xs) / size, sum(ys) / len(ys) / size], "area": len(points)}


def reference_edit_structural_qa(
    source: Path,
    output: Path,
    *,
    thresholds: Mapping[str, Any] | None = None,
    source_revision_id: str | None = None,
    output_revision_id: str | None = None,
    source_expected_sha256: str | None = None,
    output_expected_sha256: str | None = None,
) -> dict[str, Any]:
    limits = {"silhouette_iou_min": 0.70, "centroid_drift_max": 0.08, "bbox_scale_delta_max": 0.15, "allow_pixel_identical": False}
    limits.update(dict(thresholds or {}))
    source = Path(source).resolve()
    output = Path(output).resolve()
    checks: dict[str, bool] = {
        "source_exists": source.is_file(),
        "output_exists": output.is_file(),
        "distinct_paths": source != output,
        "distinct_revisions": not source_revision_id or not output_revision_id or source_revision_id != output_revision_id,
        "source_hash_matches_metadata": True,
        "output_hash_matches_metadata": True,
    }
    source_hash = sha256(source) if source.is_file() else None
    output_hash = sha256(output) if output.is_file() else None
    if source_expected_sha256 is not None:
        checks["source_hash_matches_metadata"] = source_hash == source_expected_sha256
    if output_expected_sha256 is not None:
        checks["output_hash_matches_metadata"] = output_hash == output_expected_sha256
    immutable_ok = all(checks.values())
    if not immutable_ok:
        return {
            "status": "REFERENCE_EDIT_QA_FAILED",
            "source_sha256": source_hash,
            "output_sha256": output_hash,
            "source_revision_id": source_revision_id,
            "output_revision_id": output_revision_id,
            "metrics": {"silhouette_iou": 0.0, "centroid_drift": 1.0, "bbox_scale_delta": 1.0, "pixel_identical": source_hash is not None and source_hash == output_hash},
            "thresholds": limits,
            "checks": {**checks, "immutable_inputs": False, "not_pixel_identical": False},
        }
    source_points = _mask_points(source)
    output_points = _mask_points(output)
    union = source_points | output_points
    intersection = source_points & output_points
    source_geometry = _mask_geometry(source_points)
    output_geometry = _mask_geometry(output_points)
    iou = len(intersection) / max(1, len(union))
    source_centroid = source_geometry["centroid"] or [1.0, 1.0]
    output_centroid = output_geometry["centroid"] or [1.0, 1.0]
    centroid_drift = max(abs(source_centroid[0] - output_centroid[0]), abs(source_centroid[1] - output_centroid[1]))
    source_bbox = source_geometry["bbox"] or [0, 0, 0, 0]
    output_bbox = output_geometry["bbox"] or [0, 0, 0, 0]
    source_size = max(1, (source_bbox[2] - source_bbox[0]) * (source_bbox[3] - source_bbox[1]))
    output_size = (output_bbox[2] - output_bbox[0]) * (output_bbox[3] - output_bbox[1])
    bbox_scale_delta = abs(output_size - source_size) / source_size
    pixel_identical = source_hash == output_hash
    checks.update({
        "immutable_inputs": True,
        "silhouette_iou": iou >= float(limits["silhouette_iou_min"]),
        "centroid_drift": centroid_drift <= float(limits["centroid_drift_max"]),
        "bbox_scale_delta": bbox_scale_delta <= float(limits["bbox_scale_delta_max"]),
        "not_pixel_identical": bool(limits["allow_pixel_identical"]) or not pixel_identical,
    })
    return {
        "status": "REFERENCE_EDIT_QA_PASSED" if all(checks.values()) else "REFERENCE_EDIT_QA_FAILED",
        "source_sha256": source_hash,
        "output_sha256": output_hash,
        "source_revision_id": source_revision_id,
        "output_revision_id": output_revision_id,
        "source": source_geometry,
        "output": output_geometry,
        "metrics": {"silhouette_iou": round(iou, 6), "centroid_drift": round(centroid_drift, 6), "bbox_scale_delta": round(bbox_scale_delta, 6), "pixel_identical": pixel_identical},
        "thresholds": limits,
        "checks": checks,
    }


def checkerboard_preview(source: Path, destination: Path, *, tile: int = 16) -> dict[str, Any]:
    from PIL import Image, ImageDraw
    with Image.open(source) as opened: image = opened.convert("RGBA")
    background = Image.new("RGBA", image.size, (224, 224, 224, 255)); draw = ImageDraw.Draw(background)
    for y in range(0, image.height, tile):
        for x in range(0, image.width, tile):
            if (x // tile + y // tile) % 2 == 0: draw.rectangle((x, y, min(x + tile, image.width), min(y + tile, image.height)), fill=(176, 176, 176, 255))
    background.alpha_composite(image); destination.parent.mkdir(parents=True, exist_ok=True); background.convert("RGB").save(destination, format="PNG", optimize=False)
    return inspect_png(destination)


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _find_asset(root: Path, asset_id: str) -> Path:
    candidate = Path(asset_id)
    if candidate.is_file() and candidate.name == "asset.json": return candidate
    if candidate.is_dir() and (candidate / "asset.json").is_file(): return candidate / "asset.json"
    for path in (root / "tmp").glob("**/asset.json"):
        try: value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): continue
        if value.get("asset_id") == asset_id or value.get("id") == asset_id: return path
    raise MasterAssetError(f"asset not found: {asset_id}")


def load_asset(root: Path, asset_id: str) -> tuple[Path, dict[str, Any]]:
    path = _find_asset(root, asset_id); return path, json.loads(path.read_text(encoding="utf-8"))


def save_asset(asset_path: Path, value: Mapping[str, Any]) -> None:
    write_json(asset_path, value)


def _revision_path(asset_path: Path, revision: Mapping[str, Any]) -> Path:
    value = Path(str(revision.get("output_path", "")))
    return value if value.is_absolute() else (asset_path.parent / value).resolve()


def _revision_metadata_path(asset_path: Path, revision: Mapping[str, Any]) -> Path:
    value = revision.get("metadata_path")
    if value:
        path = Path(str(value))
        return path if path.is_absolute() else (asset_path.parent / path).resolve()
    return _revision_path(asset_path, revision).parent / "metadata.json"


def _recomputed_production_ready(asset: Mapping[str, Any], current: Mapping[str, Any], *, integrity_ok: bool) -> bool:
    approval = current.get("visual_approval") or {}
    technical = current.get("technical_status") in {"TECHNICAL_VALID", "TRANSPARENCY_VALID"}
    transparency = not bool(asset.get("requires_transparency")) or current.get("transparency_status") == "TRANSPARENCY_VALID"
    approval_ok = (
        approval.get("status") == "approved"
        and approval.get("revision_id") == current.get("revision_id")
        and approval.get("output_sha256") == current.get("output_sha256")
    )
    return bool(integrity_ok and technical and transparency and approval_ok)


def verify_asset_integrity(root: Path, asset_id: str) -> dict[str, Any]:
    """Audit the immutable revision graph and recompute production readiness."""
    try:
        asset_path, asset = load_asset(root, asset_id)
    except Exception as exc:
        return {"status": "REVISION_INTEGRITY_FAILED", "asset_id": asset_id, "failures": [str(exc)], "checks": {}}

    revisions = asset.get("revisions") or []
    failures: list[str] = []
    checks: dict[str, Any] = {
        "asset_exists": True,
        "unique_revision_ids": True,
        "unique_output_paths": True,
        "output_paths_exist": True,
        "output_hashes_match": True,
        "revision_metadata_match": True,
        "revision_ordering": True,
        "derived_from_exists": True,
        "derived_from_hashes_match": True,
        "no_forward_or_cyclic_derivation": True,
        "current_revision_references_stored_revision": True,
        "approval_binds_to_current_revision": True,
        "production_ready_recomputed": True,
    }
    by_id: dict[str, Mapping[str, Any]] = {}
    by_path: dict[str, str] = {}
    for index, revision in enumerate(revisions):
        revision_id = str(revision.get("revision_id", ""))
        if not revision_id or revision_id in by_id:
            checks["unique_revision_ids"] = False
            failures.append(f"duplicate or missing revision_id at index {index}")
        else:
            by_id[revision_id] = revision
        number = revision.get("revision_number")
        if number != index + 1:
            checks["revision_ordering"] = False
            failures.append(f"revision ordering is not contiguous at {revision_id or index}")
        output = _revision_path(asset_path, revision)
        output_key = str(output.resolve())
        if output_key in by_path and by_path[output_key] != revision_id:
            checks["unique_output_paths"] = False
            failures.append(f"output path is shared by {by_path[output_key]} and {revision_id}")
        else:
            by_path[output_key] = revision_id
        if not output.is_file():
            checks["output_paths_exist"] = False
            failures.append(f"missing output for {revision_id}: {output}")
            continue
        actual_hash = sha256(output)
        if actual_hash != revision.get("output_sha256"):
            checks["output_hashes_match"] = False
            failures.append(f"output hash mismatch for {revision_id}")
        metadata = _revision_metadata_path(asset_path, revision)
        if metadata.is_file():
            try:
                stored_metadata = json.loads(metadata.read_text(encoding="utf-8"))
                for key in ("revision_id", "revision_number", "output_path", "output_sha256"):
                    if stored_metadata.get(key) != revision.get(key):
                        checks["revision_metadata_match"] = False
                        failures.append(f"revision metadata mismatch for {revision_id}: {key}")
            except (OSError, json.JSONDecodeError) as exc:
                checks["revision_metadata_match"] = False
                failures.append(f"invalid revision metadata for {revision_id}: {exc}")

    for revision in revisions:
        revision_id = str(revision.get("revision_id", ""))
        parent = revision.get("derived_from")
        if not parent:
            continue
        parent_id = str(parent.get("revision_id", ""))
        referenced = by_id.get(parent_id)
        if referenced is None:
            checks["derived_from_exists"] = False
            failures.append(f"missing derived_from revision for {revision_id}: {parent_id}")
            continue
        if parent.get("output_sha256") != referenced.get("output_sha256"):
            checks["derived_from_hashes_match"] = False
            failures.append(f"derived_from hash mismatch for {revision_id}")
        if int(referenced.get("revision_number", 0)) >= int(revision.get("revision_number", 0)):
            checks["no_forward_or_cyclic_derivation"] = False
            failures.append(f"forward derivation for {revision_id}")
        seen: set[str] = set()
        cursor = revision_id
        while cursor:
            if cursor in seen:
                checks["no_forward_or_cyclic_derivation"] = False
                failures.append(f"cyclic derivation at {revision_id}")
                break
            seen.add(cursor)
            item = by_id.get(cursor)
            if item is None:
                break
            cursor = str((item.get("derived_from") or {}).get("revision_id", ""))

    current = asset.get("current_revision") or {}
    current_id = current.get("revision_id") if isinstance(current, Mapping) else current
    current_record = by_id.get(str(current_id)) if current_id else None
    if current_record is None:
        checks["current_revision_references_stored_revision"] = False
        failures.append("current_revision does not reference a stored revision")
        current_record = {}
    elif isinstance(current, Mapping) and current.get("output_sha256") != current_record.get("output_sha256"):
        checks["current_revision_references_stored_revision"] = False
        failures.append("current_revision hash differs from stored revision")
    approval = current_record.get("visual_approval") or {}
    if approval.get("status") == "approved" and (
        approval.get("revision_id") != current_record.get("revision_id")
        or approval.get("output_sha256") != current_record.get("output_sha256")
    ):
        checks["approval_binds_to_current_revision"] = False
        failures.append("visual approval is not bound to current revision/hash")
    integrity_ok = not failures
    recomputed = _recomputed_production_ready(asset, current_record, integrity_ok=integrity_ok)
    if bool(current_record.get("production_ready")) != recomputed:
        checks["production_ready_recomputed"] = False
        failures.append("stored production_ready does not match recomputed state")
    return {
        "status": "REVISION_INTEGRITY_PASSED" if not failures else "REVISION_INTEGRITY_FAILED",
        "asset_id": asset.get("asset_id", asset.get("id", asset_id)),
        "asset_path": str(asset_path),
        "current_revision_id": current_record.get("revision_id"),
        "revision_count": len(revisions),
        "revisions": [
            {
                "revision_id": item.get("revision_id"),
                "revision_number": item.get("revision_number"),
                "output_path": str(_revision_path(asset_path, item)),
                "output_sha256": item.get("output_sha256"),
                "derived_from": item.get("derived_from"),
            }
            for item in revisions
        ],
        "checks": checks,
        "production_ready_recomputed": recomputed,
        "failures": failures,
    }


def audit_asset_revisions(root: Path, asset_id: str) -> dict[str, Any]:
    """Backward-friendly alias for callers that name the operation an audit."""
    return verify_asset_integrity(root, asset_id)


def asset_status(root: Path, asset_id: str) -> dict[str, Any]:
    path, asset = load_asset(root, asset_id)
    current = asset.get("current_revision", {})
    approval = current.get("visual_approval") or {"status": "pending"}
    integrity = verify_asset_integrity(root, str(path))
    production_ready = bool(integrity.get("status") == "REVISION_INTEGRITY_PASSED" and integrity.get("production_ready_recomputed"))
    approval_ok = approval.get("status") == "approved" and approval.get("revision_id") == current.get("revision_id") and approval.get("output_sha256") == current.get("output_sha256")
    return {"asset_id": asset.get("asset_id", asset.get("id")), "asset_path": str(path), "revision_id": current.get("revision_id"), "state": "PRODUCTION_READY" if production_ready else ("VISUALLY_APPROVED" if approval_ok else current.get("state", "GENERATED")), "technical_status": current.get("technical_status"), "transparency_status": current.get("transparency_status"), "visual_approval": approval, "production_ready": production_ready, "current_revision_sha256": current.get("output_sha256"), "approval_hash_ok": approval_ok, "revision_integrity": integrity}


def approve_visual(root: Path, asset_id: str, note: str = "") -> dict[str, Any]:
    path, asset = load_asset(root, asset_id); current = asset.get("current_revision")
    if not current or current.get("technical_status") not in {"TECHNICAL_VALID", "TRANSPARENCY_VALID"}: raise MasterAssetError("visual approval requires current technical QA to pass")
    if asset.get("requires_transparency") and current.get("transparency_status") != "TRANSPARENCY_VALID": raise MasterAssetError("visual approval requires current transparency QA to pass")
    integrity = verify_asset_integrity(root, str(path))
    if integrity["status"] != "REVISION_INTEGRITY_PASSED": raise MasterAssetError("visual approval requires revision integrity to pass")
    stamp = _now(); actor = os.environ.get("USERNAME") or os.environ.get("USER") or "local-user"
    current["visual_approval"] = {"status": "approved", "actor": actor, "approved_at": stamp, "revision_id": current.get("revision_id"), "output_sha256": current.get("output_sha256"), "note": note}
    current["state"] = "VISUALLY_APPROVED"; current["production_ready"] = True; asset["updated_at"] = stamp
    for stored_revision in asset.get("revisions", []):
        if stored_revision.get("revision_id") == current.get("revision_id"):
            stored_revision.update(current)
    save_asset(path, asset)
    metadata_path = _revision_metadata_path(path, current)
    if metadata_path.is_file(): write_json(metadata_path, current)
    return asset_status(root, str(path))
