"""Technical output QA, intentionally distinct from human visual approval."""

from __future__ import annotations

from pathlib import Path

from .image_utils import inspect_png, rgb_preservation


def validate_output(
    path: Path,
    *,
    width: int | None = None,
    height: int | None = None,
    max_bytes: int = 20 * 1024 * 1024,
    requires_transparency: bool = False,
    transparency_profile: dict | None = None,
    rgb_source: Path | None = None,
) -> dict:
    try:
        info = inspect_png(path)
        transparency_profile = {
            "min_transparent_fraction": 0.01,
            "max_foreground_coverage": 0.98,
            "allow_border_contact": False,
            "near_opaque_threshold": 250,
            "min_near_opaque_foreground_fraction": 0.85,
            "high_alpha_threshold": 250,
            "max_mean_abs_rgb_error": 2.0,
            **(transparency_profile or {}),
        }
        rgb_qa = None
        if rgb_source is not None:
            rgb_qa = rgb_preservation(
                rgb_source,
                path,
                high_alpha_threshold=int(transparency_profile["high_alpha_threshold"]),
                max_mean_abs_error=float(transparency_profile["max_mean_abs_rgb_error"]),
            )
        alpha_quality = (not requires_transparency or (
            info["has_alpha_channel"] and info["has_transparent_pixels"] and
            info.get("transparent_fraction", 0.0) >= transparency_profile["min_transparent_fraction"] and
            info.get("foreground_coverage", 0.0) <= transparency_profile["max_foreground_coverage"] and
            (transparency_profile["allow_border_contact"] or not info.get("border_contact", False)) and
            info.get("near_opaque_foreground_fraction", 0.0) >= transparency_profile["min_near_opaque_foreground_fraction"] and
            (rgb_qa is None or rgb_qa.get("passed", False))
        ))
        checks = {
            "exists": path.is_file(),
            "format": info["format"] == "PNG",
            "dimensions": (width is None or info["width"] == width) and (height is None or info["height"] == height),
            "size": info["bytes"] <= max_bytes,
            "non_empty_content": info["non_empty_content"],
        "transparency_requirement": alpha_quality,
        "rgb_preservation": rgb_qa if rgb_qa is not None else {"status": "not-run"},
        }
    except Exception as exc:
        return {"status": "failed", "checks": {"exists": path.is_file()}, "error": str(exc)}
    status = "TECHNICAL_VALID" if all(checks.values()) else "failed"
    return {
        "status": status,
        "checks": checks,
        "requirements": {"requires_transparency": requires_transparency, "transparency_profile": transparency_profile if requires_transparency else None},
        "technical": info,
        "alpha_metrics": {key: info.get(key) for key in (
            "alpha_zero_fraction", "alpha_opaque_fraction", "alpha_partial_fraction", "foreground_coverage",
            "near_opaque_threshold", "near_opaque_foreground_fraction", "soft_edge_foreground_fraction",
            "alpha_bbox", "alpha_centroid", "border_contact",
        )},
        "rgb_preservation": rgb_qa if rgb_qa is not None else {"status": "not-run"},
        "visual_review": "required",
        "production_ready": False,
    }
