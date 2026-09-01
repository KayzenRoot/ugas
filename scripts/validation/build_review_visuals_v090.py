"""Build the hash-bound v0.9.0 visual-role manifest after QA gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "evidence" / "idle-front-v090"
PACKAGE = ROOT / "docs" / "evidence" / "animation-runtime-v090" / "idle-front-v1"
PHASES = ("I0-neutral-A", "I1-inhale-early", "I2-inhale-mid", "I3-inhale-peak", "I4-return-A", "I5-neutral-B", "I6-exhale-early", "I7-exhale-mid", "I8-exhale-peak", "I9-return-B", "I10-settle", "I11-pre-loop")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add(items: list[dict], path: Path, archive_name: str, role: str) -> None:
    items.append({"archive_name": archive_name, "source_path": path.relative_to(ROOT).as_posix(), "revision_id": "idle-front-v1-render-v090", "sha256": sha(path), "media_type": "image/gif" if path.suffix.casefold() == ".gif" else "image/png", "role": role})


def main() -> int:
    items: list[dict] = []
    for index, phase in enumerate(PHASES):
        add(items, OUT / "frames" / f"frame-{index:02d}-{phase}.png", f"idle-frame-{index:02d}-{phase}.png", "canonical-transparent-frame")
        add(items, OUT / "checkerboard" / f"frame-{index:02d}-{phase}.png", f"idle-checkerboard-frame-{index:02d}-{phase}.png", "checkerboard-frame")
        add(items, OUT / "target-detected-overlays" / f"frame-{index:02d}-{phase}.png", f"idle-target-detected-frame-{index:02d}-{phase}.png", "target-detected-overlay")
        add(items, OUT / "alpha-bbox-overlays" / f"frame-{index:02d}-{phase}.png", f"idle-alpha-bbox-frame-{index:02d}-{phase}.png", "alpha-bbox-overlay")
        add(items, OUT / "feet-ground" / f"frame-{index:02d}-{phase}.png", f"idle-feet-ground-frame-{index:02d}-{phase}.png", "feet-ground-overlay")
        add(items, OUT / "structural-maps" / f"frame-{index:02d}-{phase}.png", f"idle-structural-frame-{index:02d}-{phase}.png", "structural-map")
    for name, role in (("idle-front-evidence-contact-sheet-v090.png", "canonical-contact-sheet"), ("idle-front-checkerboard-contact-sheet-v090.png", "checkerboard-contact-sheet"), ("idle-front-target-detected-overlays-v090.png", "target-detected-contact-sheet"), ("idle-front-alpha-bbox-overlays-v090.png", "alpha-bbox-contact-sheet"), ("idle-front-feet-ground-sheet-v090.png", "feet-ground-sheet"), ("idle-front-structural-maps-v090.png", "structural-maps-sheet"), ("idle-front-waist-hip-sheet-v090.png", "waist-hip-sheet"), ("idle-front-sword-hand-sheet-v090.png", "sword-hand-sheet"), ("idle-front-head-torso-sheet-v090.png", "head-torso-sheet"), ("idle-front-temporal-trajectory-v090.png", "temporal-trajectory")):
        add(items, OUT / name, name, role)
    add(items, PACKAGE / "idle-front-spritesheet-v090.png", "idle-front-spritesheet-v090.png", "final-rgba-spritesheet")
    add(items, PACKAGE / "idle-front-preview-v090.gif", "idle-front-preview-v090.gif", "review-gif")
    value = {"schema_version": "0.9.0", "review_state": "idle-front-v1-technically-qualified", "review_subject": {"animation_id": "idle-front-v1", "direction": "front", "frame_count": 12, "baseline_commit": "46ba3ae87558ff26055e14aa8d9c6f3ee147333c", "implementation_base_commit": "46ba3ae87558ff26055e14aa8d9c6f3ee147333c", "repository_ref": "https://github.com/csn1985-ship-it/ugas.git"}, "required_current_visuals": sorted({item["archive_name"] for item in items}), "images": items, "source_only_pixels": True, "sam2_runs": 0, "comfyui_generation_jobs": 0, "external_visual_review": "REQUIRED", "production_routing": "BLOCKED"}
    output = ROOT / "docs" / "evidence" / "review-visuals-v0.9.0.json"; output.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(output); return 0


if __name__ == "__main__": raise SystemExit(main())
