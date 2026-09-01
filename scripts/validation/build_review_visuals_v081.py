"""Build the hash-bound v0.8.1 visual review manifest from published evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ugas.review import REQUIRED_V081_REVIEW_EVIDENCE

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "evidence"
OUT = EVIDENCE / "walk-front-v081"
REVISION_ID = "revision-3a425d184b1a49be9f6d6c8d52d04b96"


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def source_for(archive_name: str) -> Path:
    if archive_name.startswith("checkerboard-frame-"):
        return OUT / "checkerboard" / archive_name.removeprefix("checkerboard-")
    if archive_name.startswith("target-detected-overlays-frame-"):
        return OUT / "target-detected-overlays" / archive_name.removeprefix("target-detected-overlays-")
    if archive_name.startswith("ground-line-overlays-frame-"):
        return OUT / "ground-line-overlays" / archive_name.removeprefix("ground-line-overlays-")
    if archive_name.startswith("structural-hole-maps-frame-"):
        return OUT / "structural-hole-maps" / archive_name.removeprefix("structural-hole-maps-")
    if archive_name.startswith("pairwise-frame-"):
        return OUT / "pairwise" / archive_name.removeprefix("pairwise-")
    if archive_name.startswith("retention-frame-"):
        return OUT / "retention" / archive_name.removeprefix("retention-")
    if archive_name.startswith("frame-") and "-alpha-bbox-" in archive_name:
        return OUT / archive_name
    if archive_name.startswith("frame-"):
        return OUT / "frames" / archive_name
    root_candidate = EVIDENCE / archive_name
    if root_candidate.is_file():
        return root_candidate
    return OUT / archive_name


def media_type(path: Path) -> str:
    return {
        ".png": "image/png",
        ".gif": "image/gif",
        ".json": "application/json",
    }.get(path.suffix.casefold(), "application/octet-stream")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    images = []
    for archive_name in sorted(REQUIRED_V081_REVIEW_EVIDENCE):
        source = source_for(archive_name)
        if not source.is_file():
            raise SystemExit(f"missing review source: {source}")
        relative = source.relative_to(ROOT).as_posix()
        images.append({
            "archive_name": archive_name,
            "source_path": relative,
            "revision_id": REVISION_ID,
            "sha256": digest(source),
            "media_type": media_type(source),
            "role": f"v0.8.1 front-walk review evidence: {archive_name}",
        })
    manifest = {
        "schema_version": "0.8.1",
        "manifest_type": "review-visual-evidence",
        "review_state": "front-walk-correction",
        "images": images,
        "required_current_visuals": sorted(REQUIRED_V081_REVIEW_EVIDENCE),
        "renderer_version": "deterministic-cutout-rig-2d-v0.8.1",
        "human_visual_review": "required",
        "production_approval": "not-granted",
        "provider_status": "CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED",
        "external_approval": "not-claimed",
    }
    path = EVIDENCE / "review-visuals-v0.8.1.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result = {"status": "REVIEW_VISUAL_MANIFEST_BUILT", "path": path.relative_to(ROOT).as_posix(), "items": len(images)}
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
