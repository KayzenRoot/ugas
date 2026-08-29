"""Technical output QA, intentionally distinct from human visual approval."""

from __future__ import annotations

from pathlib import Path

from .image_utils import inspect_png


def validate_output(path: Path, *, width: int | None = None, height: int | None = None, max_bytes: int = 20 * 1024 * 1024) -> dict:
    try:
        info = inspect_png(path)
        checks = {"exists": path.is_file(), "format": info["format"] == "PNG", "dimensions": (width is None or info["width"] == width) and (height is None or info["height"] == height), "size": info["bytes"] <= max_bytes, "non_empty": info["has_alpha"]}
    except Exception as exc:
        return {"status": "failed", "checks": {"exists": path.is_file()}, "error": str(exc)}
    status = "TECHNICAL_VALID" if all(checks.values()) else "failed"
    return {"status": status, "checks": checks, "technical": info, "visual_review": "required", "production_ready": False}
