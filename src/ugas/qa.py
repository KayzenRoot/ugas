"""Technical output QA, intentionally distinct from human visual approval."""

from __future__ import annotations

from pathlib import Path

from .image_utils import inspect_png


def validate_output(path: Path, *, width: int | None = None, height: int | None = None, max_bytes: int = 20 * 1024 * 1024, requires_transparency: bool = False, transparency_profile: dict | None = None) -> dict:
    try:
        info = inspect_png(path)
        alpha = info.get("alpha_metrics", {})
        transparency_profile = transparency_profile or {"min_transparent_fraction": 0.01, "max_foreground_coverage": 0.98, "allow_border_contact": False}
        alpha_quality = (not requires_transparency or (
            info["has_alpha_channel"] and info["has_transparent_pixels"] and
            info.get("transparent_fraction", 0.0) >= transparency_profile["min_transparent_fraction"] and
            info.get("foreground_coverage", 0.0) <= transparency_profile["max_foreground_coverage"] and
            (transparency_profile["allow_border_contact"] or not info.get("border_contact", False))
        ))
        checks = {
            "exists": path.is_file(),
            "format": info["format"] == "PNG",
            "dimensions": (width is None or info["width"] == width) and (height is None or info["height"] == height),
            "size": info["bytes"] <= max_bytes,
            "non_empty_content": info["non_empty_content"],
            "transparency_requirement": alpha_quality,
        }
    except Exception as exc:
        return {"status": "failed", "checks": {"exists": path.is_file()}, "error": str(exc)}
    status = "TECHNICAL_VALID" if all(checks.values()) else "failed"
    return {"status": status, "checks": checks, "requirements": {"requires_transparency": requires_transparency, "transparency_profile": transparency_profile if requires_transparency else None}, "technical": info, "alpha_metrics": {key: info.get(key) for key in ("alpha_zero_fraction", "alpha_opaque_fraction", "alpha_partial_fraction", "foreground_coverage", "alpha_bbox", "alpha_centroid", "border_contact")}, "visual_review": "required", "production_ready": False}
