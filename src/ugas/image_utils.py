"""Small deterministic PNG/sprite operations used by the 2D pilot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ImagePipelineError(RuntimeError):
    pass


def _image(path: Path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImagePipelineError("Pillow is required for image QA and sprite processing") from exc
    try:
        return Image.open(path).convert("RGBA")
    except Exception as exc:
        raise ImagePipelineError(f"invalid image: {path}") from exc


def _open(path: Path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImagePipelineError("Pillow is required for image QA and sprite processing") from exc
    try:
        return Image.open(path)
    except Exception as exc:
        raise ImagePipelineError(f"invalid image: {path}") from exc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_png(path: Path) -> dict:
    with _open(path) as image:
        source_mode = image.mode
        bands = image.getbands()
        has_alpha_channel = "A" in bands or (source_mode == "P" and "transparency" in image.info)
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        alpha_min, alpha_max = alpha.getextrema()
        total_pixels = image.width * image.height
        alpha_values = list(alpha.getdata())
        transparent_pixels = sum(1 for value in alpha_values if value == 0)
        partial_pixels = sum(1 for value in alpha_values if 0 < value < 255)
        opaque_pixels = sum(1 for value in alpha_values if value == 255)
        near_opaque_threshold = 250
        foreground_pixels = sum(1 for value in alpha_values if value > 0)
        near_opaque_pixels = sum(1 for value in alpha_values if value >= near_opaque_threshold)
        soft_edge_pixels = sum(1 for value in alpha_values if 0 < value < near_opaque_threshold)
        content_bbox = alpha.getbbox() if has_alpha_channel else image.convert("RGB").getbbox()
        foreground_points = [(x, y) for y in range(image.height) for x in range(image.width) if alpha.getpixel((x, y)) > 0] if has_alpha_channel else []
        border_contact = bool(has_alpha_channel and (any(alpha.getpixel((x, 0)) > 0 or alpha.getpixel((x, image.height - 1)) > 0 for x in range(image.width)) or any(alpha.getpixel((0, y)) > 0 or alpha.getpixel((image.width - 1, y)) > 0 for y in range(image.height))))
        return {
            "path": str(path),
            "format": "PNG",
            "width": image.width,
            "height": image.height,
            "mode": source_mode,
            "source_mode": source_mode,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "has_alpha": has_alpha_channel,
            "has_alpha_channel": has_alpha_channel,
            "has_transparent_pixels": bool(has_alpha_channel and transparent_pixels + partial_pixels > 0),
            "alpha_min": alpha_min if has_alpha_channel else None,
            "alpha_max": alpha_max if has_alpha_channel else None,
            "opaque_fraction": opaque_pixels / total_pixels if total_pixels else 0.0,
            "transparent_fraction": transparent_pixels / total_pixels if total_pixels else 0.0,
            "alpha_zero_fraction": transparent_pixels / total_pixels if total_pixels else 0.0,
            "alpha_opaque_fraction": opaque_pixels / total_pixels if total_pixels else 0.0,
            "alpha_partial_fraction": partial_pixels / total_pixels if total_pixels else 0.0,
            "foreground_coverage": (total_pixels - transparent_pixels) / total_pixels if total_pixels else 0.0,
            "near_opaque_threshold": near_opaque_threshold,
            "near_opaque_foreground_fraction": near_opaque_pixels / foreground_pixels if foreground_pixels else 0.0,
            "soft_edge_foreground_fraction": soft_edge_pixels / foreground_pixels if foreground_pixels else 0.0,
            "alpha_bbox": list(alpha.getbbox()) if has_alpha_channel and alpha.getbbox() else None,
            "alpha_centroid": ([sum(x for x, _ in foreground_points) / len(foreground_points) / image.width, sum(y for _, y in foreground_points) / len(foreground_points) / image.height] if foreground_points else None),
            "border_contact": border_contact,
            "non_empty_content": content_bbox is not None,
        }


def rgb_preservation(source: Path, result: Path, *, high_alpha_threshold: int = 250, max_mean_abs_error: float = 2.0) -> dict:
    """Compare RGB values on strongly foreground pixels after alpha joining.

    Background removal is allowed to alter the matte, not the subject's RGB
    appearance. The result is measured only where the resulting alpha is
    strongly foreground so transparent background pixels cannot hide a
    recolour of the subject.
    """
    try:
        from PIL import Image
        with Image.open(source) as source_image, Image.open(result) as result_image:
            source_rgb = source_image.convert("RGB")
            result_rgba = result_image.convert("RGBA")
            if source_rgb.size != result_rgba.size:
                return {
                    "compared_pixels": 0,
                    "high_alpha_threshold": high_alpha_threshold,
                    "mae_r": None,
                    "mae_g": None,
                    "mae_b": None,
                    "mae_total": None,
                    "passed": False,
                    "error": "source and result dimensions differ",
                }
            source_pixels = source_rgb.load()
            result_pixels = result_rgba.load()
            sums = [0.0, 0.0, 0.0]
            compared = 0
            for y in range(result_rgba.height):
                for x in range(result_rgba.width):
                    red, green, blue, alpha = result_pixels[x, y]
                    if alpha < high_alpha_threshold:
                        continue
                    original = source_pixels[x, y]
                    sums[0] += abs(original[0] - red)
                    sums[1] += abs(original[1] - green)
                    sums[2] += abs(original[2] - blue)
                    compared += 1
            maes = [value / compared for value in sums] if compared else [float("inf")] * 3
            total = sum(maes) / 3 if compared else float("inf")
            return {
                "compared_pixels": compared,
                "high_alpha_threshold": high_alpha_threshold,
                "mae_r": round(maes[0], 6) if compared else None,
                "mae_g": round(maes[1], 6) if compared else None,
                "mae_b": round(maes[2], 6) if compared else None,
                "mae_total": round(total, 6) if compared else None,
                "max_mean_abs_error": max_mean_abs_error,
                "passed": bool(compared and total <= max_mean_abs_error),
            }
    except Exception as exc:
        return {
            "compared_pixels": 0,
            "high_alpha_threshold": high_alpha_threshold,
            "mae_r": None,
            "mae_g": None,
            "mae_b": None,
            "mae_total": None,
            "passed": False,
            "error": str(exc),
        }


def crop_grid(source: Path, destination: Path, columns: int, rows: int, *, trim: bool = False, pad: int = 0, anchor: str = "center") -> dict:
    if columns < 1 or rows < 1:
        raise ImagePipelineError("grid columns and rows must be positive")
    image = _image(source)
    if image.width % columns or image.height % rows:
        raise ImagePipelineError("source dimensions do not divide evenly into the requested grid")
    cell_w, cell_h = image.width // columns, image.height // rows
    destination.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    from PIL import Image
    for index in range(columns * rows):
        col, row = index % columns, index // columns
        frame = image.crop((col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h))
        if trim:
            bbox = frame.getchannel("A").getbbox()
            if bbox:
                frame = frame.crop(bbox)
        if pad:
            canvas = Image.new("RGBA", (frame.width + pad * 2, frame.height + pad * 2), (0, 0, 0, 0))
            left = (canvas.width - frame.width) // 2 if anchor == "center" else pad
            top = (canvas.height - frame.height) // 2 if anchor == "center" else pad
            canvas.alpha_composite(frame, (left, top))
            frame = canvas
        path = destination.parent / f"{destination.stem}_{index:03d}.png"
        frame.save(path, format="PNG", optimize=False)
        frames.append({"index": index, "row": row, "column": col, "path": str(path), "sha256": sha256(path), "width": frame.width, "height": frame.height})
    return {"source": inspect_png(source), "columns": columns, "rows": rows, "frames": frames}


def compose_sheet(frames: list[Path], destination: Path, columns: int) -> dict:
    from PIL import Image
    if not frames or columns < 1:
        raise ImagePipelineError("at least one frame and one column are required")
    loaded = [_image(path) for path in frames]
    width, height = max(image.width for image in loaded), max(image.height for image in loaded)
    rows = (len(loaded) + columns - 1) // columns
    sheet = Image.new("RGBA", (width * columns, height * rows), (0, 0, 0, 0))
    for index, image in enumerate(loaded):
        sheet.alpha_composite(image, ((index % columns) * width, (index // columns) * height))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=False)
    return inspect_png(destination) | {"columns": columns, "rows": rows, "frame_count": len(loaded)}


def write_metadata(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
