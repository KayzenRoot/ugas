"""v0.4.0 master-sprite contracts, prompt compilation and revision gates."""

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

from .image_utils import inspect_png, sha256


class MasterAssetError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
    """Serializable human request compiled into a reproducible generation spec."""

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
            "schema_version": "0.4.0",
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
    width: int = 384,
    height: int = 384,
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
        asset_id=asset_id or f"asset-{uuid.uuid4().hex}",
        category="character",
        subtype="master-sprite",
        intended_view="2d gameplay sprite",
        orientation="front-facing three-quarter" if "top-down" not in prompt.casefold() else "top-down three-quarter",
        game_profile=profile_id,
        art_dna=dna,
        visual_style=", ".join(str(item) for item in keywords),
        palette_intent=str(dna.get("palette", "project-defined")),
        outline_policy="clean readable silhouette with controlled outline",
        lighting="soft directional key light with readable rim separation",
        detail_density="medium-high at gameplay distance",
        canvas_target={"width": int(width), "height": int(height)},
        subject_occupancy_target={"min": 0.25, "max": 0.80},
        margins={"left": 16, "top": 16, "right": 16, "bottom": 16},
        pivot_intent="center-bottom of subject",
        requires_transparency=bool(requires_transparency),
        positive_prompt=prompt.strip(),
        negative_constraints=[
            "multiple subjects",
            "cropped subject",
            "text or watermark",
            "extra limbs or duplicate equipment",
            "muddy silhouette",
            "motion blur",
        ],
        reference_anchors=refs,
        candidate_count=candidates,
        seeds=seeds,
        generation_policy={
            "provider": "provider-comfyui",
            "resolution_policy": "benchmark-384-before-512",
            "default_candidates": 4,
            "max_candidates": 6,
            "deterministic": True,
            "visual_approval": "pending",
        },
    )


def compile_prompt(spec: Mapping[str, Any], profile: Mapping[str, Any] | None = None) -> str:
    """Compile a stable, inspectable prompt; no hidden agent memory is involved."""
    dna = spec.get("art_dna", {})
    style = spec.get("visual_style") or ", ".join(map(str, dna.get("style_keywords", [])))
    profile_id = spec.get("game_profile") or (profile or {}).get("id", "unspecified")
    lines = [
        "UGAS MASTER SPRITE",
        f"subject: {spec.get('positive_prompt', '').strip()}",
        f"game profile: {profile_id}",
        f"art DNA style: {style}",
        f"palette intent: {spec.get('palette_intent', dna.get('palette', 'project-defined'))}",
        f"shape language: {dna.get('shape_language', 'clear readable shapes')}",
        f"outline policy: {spec.get('outline_policy', 'controlled outline')}",
        f"lighting: {spec.get('lighting', 'readable directional light')}",
        f"detail density: {spec.get('detail_density', 'medium')}",
        f"view: {spec.get('intended_view', '2d gameplay sprite')}; orientation: {spec.get('orientation', 'front-facing three-quarter')}",
        f"canvas: {spec.get('canvas_target', {}).get('width', 384)}x{spec.get('canvas_target', {}).get('height', 384)}",
        f"occupancy target: {spec.get('subject_occupancy_target', {}).get('min', 0.25)}-{spec.get('subject_occupancy_target', {}).get('max', 0.80)}",
        f"pivot intent: {spec.get('pivot_intent', 'center-bottom of subject')}",
        "transparent background" if spec.get("requires_transparency") else "simple clean background for later native removal",
        "avoid: " + "; ".join(str(item) for item in spec.get("negative_constraints", [])),
    ]
    return "\n".join(lines)


def prompt_sha256(compiled_prompt: str) -> str:
    return hashlib.sha256(compiled_prompt.encode("utf-8")).hexdigest()


def _foreground_bbox(path: Path) -> tuple[int, int, int, int] | None:
    from PIL import Image

    with Image.open(path) as source:
        image = source.convert("RGBA")
        if "A" in source.getbands() and image.getchannel("A").getextrema()[0] < 255:
            return image.getchannel("A").getbbox()
        pixels = image.load()
        sample = []
        for x in range(image.width):
            sample.extend((pixels[x, 0][:3], pixels[x, image.height - 1][:3]))
        for y in range(image.height):
            sample.extend((pixels[0, y][:3], pixels[image.width - 1, y][:3]))
        background = tuple(int(median([item[channel] for item in sample])) for channel in range(3))
        threshold = max(18, int(max(image.width, image.height) * 0.03))
        points = []
        for y in range(image.height):
            for x in range(image.width):
                rgb = pixels[x, y][:3]
                distance = sum(abs(int(rgb[channel]) - background[channel]) for channel in range(3))
                if distance > threshold:
                    points.append((x, y))
        if not points:
            return None
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _average_hash(path: Path, size: int = 8) -> str:
    from PIL import Image, ImageOps

    with Image.open(path) as source:
        image = ImageOps.grayscale(source.convert("RGB")).resize((size, size))
        values = list(image.getdata())
    average = sum(values) / len(values)
    return "".join("1" if value >= average else "0" for value in values)


def candidate_metrics(path: Path, *, width: int, height: int, requires_transparency: bool = False) -> dict[str, Any]:
    info = inspect_png(path)
    bbox = _foreground_bbox(path)
    if bbox:
        left, top, right, bottom = bbox
        box_width, box_height = right - left, bottom - top
        occupancy = (box_width * box_height) / max(1, width * height)
        center_offset = {
            "x": round(abs(((left + right) / 2) - width / 2) / max(1, width), 6),
            "y": round(abs(((top + bottom) / 2) - height / 2) / max(1, height), 6),
        }
        edge_clipping = left <= 0 or top <= 0 or right >= width or bottom >= height
    else:
        occupancy = 0.0
        center_offset = {"x": 1.0, "y": 1.0}
        edge_clipping = True
    alpha_ok = not requires_transparency or info["has_transparent_pixels"]
    occupancy_ok = 0.10 <= occupancy <= 0.90
    centered_ok = center_offset["x"] <= 0.25 and center_offset["y"] <= 0.25
    return {
        "foreground_bbox": list(bbox) if bbox else None,
        "occupancy": round(occupancy, 6),
        "occupancy_ok": occupancy_ok,
        "center_offset": center_offset,
        "centered_ok": centered_ok,
        "edge_clipping": edge_clipping,
        "edge_clipping_ok": not edge_clipping,
        "alpha_ok": alpha_ok,
        "perceptual_hash": _average_hash(path),
        "file_size_ok": info["bytes"] <= 20 * 1024 * 1024,
    }


def detect_halo(path: Path) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as source:
        image = source.convert("RGBA")
        alpha = image.getchannel("A")
        if alpha.getextrema()[0] == 255:
            return {"checked": False, "halo_detected": False, "reason": "no transparency"}
        border = []
        for x in range(image.width):
            border.extend([alpha.getpixel((x, 0)), alpha.getpixel((x, image.height - 1))])
        for y in range(image.height):
            border.extend([alpha.getpixel((0, y)), alpha.getpixel((image.width - 1, y))])
        semi = sum(0 < value < 255 for value in border)
        fraction = semi / max(1, len(border))
        return {"checked": True, "border_semi_transparent_fraction": round(fraction, 6), "halo_detected": fraction > 0.35}


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _find_asset(root: Path, asset_id: str) -> Path:
    candidate = Path(asset_id)
    if candidate.is_file() and candidate.name == "asset.json":
        return candidate
    if candidate.is_dir() and (candidate / "asset.json").is_file():
        return candidate / "asset.json"
    for path in (root / "tmp").glob("**/asset.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if value.get("asset_id") == asset_id or value.get("id") == asset_id:
            return path
    raise MasterAssetError(f"asset not found: {asset_id}")


def load_asset(root: Path, asset_id: str) -> tuple[Path, dict[str, Any]]:
    path = _find_asset(root, asset_id)
    return path, json.loads(path.read_text(encoding="utf-8"))


def save_asset(asset_path: Path, value: Mapping[str, Any]) -> None:
    write_json(asset_path, value)


def asset_status(root: Path, asset_id: str) -> dict[str, Any]:
    path, asset = load_asset(root, asset_id)
    current = asset.get("current_revision", {})
    approval = current.get("visual_approval") or {"status": "pending"}
    technical = current.get("technical_status") in {"TECHNICAL_VALID", "TRANSPARENCY_VALID"}
    same_revision_approval = approval.get("revision_id") == current.get("revision_id")
    production_ready = technical and same_revision_approval and approval.get("status") == "approved"
    return {
        "asset_id": asset.get("asset_id", asset.get("id")),
        "asset_path": str(path),
        "revision_id": current.get("revision_id"),
        "state": "PRODUCTION_READY" if production_ready else ("VISUALLY_APPROVED" if same_revision_approval and approval.get("status") == "approved" else current.get("state", "GENERATED")),
        "technical_status": current.get("technical_status"),
        "transparency_status": current.get("transparency_status"),
        "visual_approval": approval,
        "production_ready": production_ready,
        "current_revision_sha256": current.get("output_sha256"),
    }


def approve_visual(root: Path, asset_id: str, note: str = "") -> dict[str, Any]:
    path, asset = load_asset(root, asset_id)
    current = asset.get("current_revision")
    if not current or current.get("technical_status") not in {"TECHNICAL_VALID", "TRANSPARENCY_VALID"}:
        raise MasterAssetError("visual approval requires current technical QA to pass")
    stamp = _now()
    actor = os.environ.get("USERNAME") or os.environ.get("USER") or "local-user"
    current["visual_approval"] = {
        "status": "approved",
        "actor": actor,
        "approved_at": stamp,
        "revision_id": current.get("revision_id"),
        "output_sha256": current.get("output_sha256"),
        "note": note,
    }
    current["state"] = "PRODUCTION_READY"
    asset["updated_at"] = stamp
    save_asset(path, asset)
    return asset_status(root, str(path))
