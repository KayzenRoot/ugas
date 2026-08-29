"""Technical output QA, intentionally distinct from human visual approval."""

from __future__ import annotations

from pathlib import Path

from .image_utils import inspect_png


def validate_output(path: Path, *, width: int | None = None, height: int | None = None, max_bytes: int = 20 * 1024 * 1024, requires_transparency: bool = False) -> dict:
    try:
        info = inspect_png(path)
        checks = {
            "exists": path.is_file(),
            "format": info["format"] == "PNG",
            "dimensions": (width is None or info["width"] == width) and (height is None or info["height"] == height),
            "size": info["bytes"] <= max_bytes,
            "non_empty_content": info["non_empty_content"],
            "transparency_requirement": not requires_transparency or info["has_transparent_pixels"],
        }
    except Exception as exc:
        return {"status": "failed", "checks": {"exists": path.is_file()}, "error": str(exc)}
    status = "TECHNICAL_VALID" if all(checks.values()) else "failed"
    return {"status": status, "checks": checks, "requirements": {"requires_transparency": requires_transparency}, "technical": info, "visual_review": "required", "production_ready": False}
