"""Create truthful PNG transport copies for the immutable v0.12.2 visuals."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs/evidence/github-review-v0123"
TRANSPORT_DIR = OUTPUT_DIR / "visuals"
SOURCES = (
    "docs/evidence/observability-v0122/dashboard-docker-overview-v0122.png",
    "docs/evidence/observability-v0122/dashboard-docker-live-activity-v0122.png",
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TRANSPORT_SIGNATURE = "89504E470D0A1A0A"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def detect_media_type(data: bytes) -> str:
    """Detect the supported media type from magic bytes, never the suffix."""
    if data.startswith(PNG_SIGNATURE):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff") and data[6:10] == b"JFIF":
        return "image/jpeg"
    raise ValueError("unsupported-or-unrecognized-media-signature")


def decoded_pixel_hash(image: Image.Image) -> str:
    rgba = image.convert("RGBA")
    payload = f"{rgba.width}x{rgba.height}:".encode("ascii") + rgba.tobytes()
    return sha256_bytes(payload)


def _load_authoritative_visuals() -> dict[str, dict[str, Any]]:
    """Load manifest-bound transport metadata without rewriting committed bytes."""
    for manifest_path in (
        ROOT / "docs/evidence/github-governance-v0124/visual-manifest.json",
        OUTPUT_DIR / "visual-manifest.json",
    ):
        if not manifest_path.is_file():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items = payload.get("visuals")
        if not isinstance(items, list):
            continue
        bound: dict[str, dict[str, Any]] = {}
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("source_path"), str):
                bound[item["source_path"]] = item
        if bound:
            return bound
    return {}


def _committed_transport_entry(source_name: str, transport: Path, bound: dict[str, Any]) -> dict[str, Any] | None:
    if bound.get("source_path") != source_name:
        return None
    if bound.get("transport_path") != transport.relative_to(ROOT).as_posix():
        return None
    if not transport.is_file():
        return None
    transport_bytes = transport.read_bytes()
    if bound.get("transport_size") != len(transport_bytes):
        return None
    if bound.get("transport_sha256") != sha256_bytes(transport_bytes):
        return None
    return dict(bound)


def build_manifest() -> dict[str, Any]:
    TRANSPORT_DIR.mkdir(parents=True, exist_ok=True)
    authoritative = _load_authoritative_visuals()
    visuals: list[dict[str, Any]] = []
    for source_name in SOURCES:
        source = ROOT / source_name
        if not source.is_file():
            raise FileNotFoundError(source)
        source_bytes = source.read_bytes()
        source_type = detect_media_type(source_bytes)
        if source_type != "image/jpeg":
            raise ValueError(f"historical source is not JPEG/JFIF: {source_name}")
        transport_name = f"{source.stem}-transport.png"
        transport = TRANSPORT_DIR / transport_name
        preserved = _committed_transport_entry(source_name, transport, authoritative.get(source_name, {}))
        if preserved is not None:
            visuals.append(preserved)
            continue
        with Image.open(source) as decoded:
            decoded.load()
            source_pixels = decoded_pixel_hash(decoded)
            width, height = decoded.size
            # Saving the decoded image as PNG is the only transformation.  No
            # resize, crop, color change, sharpening or screenshot recreation
            # is performed.
            decoded.save(transport, format="PNG", optimize=False)
        transport_bytes = transport.read_bytes()
        transport_type = detect_media_type(transport_bytes)
        with Image.open(transport) as transported:
            transported.load()
            transport_pixels = decoded_pixel_hash(transported)
        visuals.append(
            {
                "source_path": source_name,
                "source_media_type": source_type,
                "source_size": len(source_bytes),
                "source_sha256": sha256_bytes(source_bytes),
                "transport_path": transport.relative_to(ROOT).as_posix(),
                "transport_media_type": transport_type,
                "transport_signature": transport_bytes[:8].hex().upper(),
                "transport_size": len(transport_bytes),
                "transport_sha256": sha256_bytes(transport_bytes),
                "width": width,
                "height": height,
                "source_decoded_pixel_sha256": source_pixels,
                "transport_decoded_pixel_sha256": transport_pixels,
                "decoded_pixel_equal": source_pixels == transport_pixels,
            }
        )
    return {
        "schema_version": "1.0",
        "manifest_type": "review-visual-transport",
        "source_policy": "immutable-v0.12.2-source-byte-preserved",
        "transport_policy": "decoded-pixel-equivalent-png-only",
        "visuals": visuals,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT_DIR / "visual-manifest.json"))
    args = parser.parse_args()
    manifest = build_manifest()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "REVIEW_VISUAL_TRANSPORT_BUILT", "manifest": output.as_posix(), "visual_count": len(manifest["visuals"]), "transport_signature": TRANSPORT_SIGNATURE}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
