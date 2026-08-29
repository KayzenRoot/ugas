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
        transparent_pixels = sum(1 for value in alpha.getdata() if value < 255)
        opaque_pixels = total_pixels - transparent_pixels
        content_bbox = alpha.getbbox() if has_alpha_channel else image.convert("RGB").getbbox()
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
            "has_transparent_pixels": bool(has_alpha_channel and transparent_pixels > 0),
            "alpha_min": alpha_min if has_alpha_channel else None,
            "alpha_max": alpha_max if has_alpha_channel else None,
            "opaque_fraction": opaque_pixels / total_pixels if total_pixels else 0.0,
            "transparent_fraction": transparent_pixels / total_pixels if total_pixels else 0.0,
            "non_empty_content": content_bbox is not None,
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
