"""Bind v0.7.0 cutout-rig review roles to canonical evidence files."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.identity import ANCHOR_REVISION_ID


REQUIRED_CURRENT_VISUALS = (
    "sam2-provider-qualification.json",
    "sam2-checkpoint-provenance.json",
    "r4-source-skeleton.json",
    "r4-cutout-part-prompts.json",
    "r4-cutout-part-masks.json",
    "r4-cutout-rig.json",
    "r4-cutout-parts-contact-sheet.png",
    "r4-cutout-mask-overlay-contact-sheet.png",
    "r4-cutout-rig-hierarchy.png",
    "cutout-q0-reconstruction.png",
    "cutout-q0-diff-heatmap.png",
    "cutout-q0-qa.json",
    "cutout-q1-contact-left.png",
    "cutout-q2-passing-left.png",
    "cutout-q0-q1-q2-contact-sheet.png",
    "cutout-q1-q2-pose-overlays.png",
    "cutout-rig-pose-qa.json",
    "cutout-rig-seam-qa.json",
    "cutout-rig-pixel-provenance.json",
    "cutout-rig-provider-qualification.json",
    "execution-evidence-v0.7.0.json",
)


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    evidence = ROOT / "docs" / "evidence"
    missing = [name for name in REQUIRED_CURRENT_VISUALS if not (evidence / name).is_file()]
    if missing:
        print(json.dumps({"status": "REVIEW_VISUAL_MANIFEST_FAILED", "missing": missing}, indent=2))
        return 2
    manifest = {
        "schema_version": "0.7.0",
        "manifest_type": "review-visual-evidence",
        "review_state": "deterministic-cutout-rig-visual-or-estimator-gap",
        "required_current_visuals": list(REQUIRED_CURRENT_VISUALS),
        "images": [
            {
                "archive_name": name,
                "source_path": f"docs/evidence/{name}",
                "revision_id": ANCHOR_REVISION_ID,
                "sha256": digest(evidence / name),
                "role": "v0.7.0 deterministic cutout-rig evidence",
            }
            for name in REQUIRED_CURRENT_VISUALS
        ],
        "human_visual_review": "required",
        "production_approval": "not-granted",
        "external_approval": "not-claimed",
    }
    path = evidence / "review-visuals-v0.7.0.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "REVIEW_VISUAL_MANIFEST_MATERIALIZED", "path": str(path), "count": len(REQUIRED_CURRENT_VISUALS)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
