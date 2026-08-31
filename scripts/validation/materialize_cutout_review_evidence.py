"""Bind v0.7.2 cutout-rig review roles to canonical evidence files."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.identity import ANCHOR_REVISION_ID


REQUIRED_CURRENT_VISUALS = (
    "sam2-provider-qualification-v071.json",
    "sam2-checkpoint-provenance-v071.json",
    "r4-source-skeleton-v071.json",
    "r4-cutout-part-prompts-v071.json",
    "r4-cutout-raw-masks-v071-manifest.json",
    "r4-cutout-refined-masks-v071-manifest.json",
    "r4-cutout-component-diagnostics-v071.json",
    "r4-cutout-rig-v071.json",
    "r4-cutout-parts-contact-sheet-v071.png",
    "r4-cutout-mask-overlay-v071.png",
    "cutout-q0-reconstruction-v071.png",
    "cutout-q0-alpha-aware-diff-v071.png",
    "cutout-q0-reconstruction-qa-v071.json",
    "cutout-q1-contact-left-v071.png",
    "cutout-q2-passing-left-v071.png",
    "cutout-q0-q1-q2-contact-sheet-v071.png",
    "cutout-q1-q2-target-detected-overlays-v071.png",
    "cutout-rig-pose-qa-v071.json",
    "cutout-rig-internal-qa-v071.json",
    "cutout-rig-seam-qa-v071.json",
    "cutout-rig-pixel-retention-v071.json",
    "cutout-rig-pixel-provenance-v071.json",
    "cutout-rig-provider-qualification-v071.json",
    "execution-evidence-v0.7.1.json",
)

REQUIRED_V072_CURRENT_VISUALS = (
    "cutout-occlusion-plan-v072.json",
    "cutout-pairwise-overlap-matrix-v072.json",
    "cutout-seam-topology-qa-v072.json",
    "cutout-retention-occlusion-v072.json",
    "cutout-front-walk-gait-v2.json",
    "cutout-front-walk-targets-v072-contact-sheet.png",
    "cutout-q0-regression-v072.png",
    "cutout-q0-regression-v072-qa.json",
    "cutout-k1-contact-left-v072.png",
    "cutout-k2-passing-left-v072.png",
    "cutout-k3-contact-right-v072.png",
    "cutout-k4-passing-right-v072.png",
    "cutout-key-poses-contact-sheet-v072.png",
    "cutout-key-poses-checkerboard-v072.png",
    "cutout-key-poses-target-detected-overlays-v072.png",
    "cutout-occlusion-classification-v072.png",
    "cutout-retention-heatmap-v072.png",
    "cutout-half-cycle-structure-v072.json",
    "cutout-rig-provider-qualification-v072.json",
    "execution-evidence-v0.7.2.json",
)


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    evidence = ROOT / "docs" / "evidence"
    missing = [name for name in REQUIRED_V072_CURRENT_VISUALS if not (evidence / name).is_file()]
    if missing:
        print(json.dumps({"status": "REVIEW_VISUAL_MANIFEST_FAILED", "missing": missing}, indent=2))
        return 2
    manifest = {
        "schema_version": "0.7.2",
        "manifest_type": "review-visual-evidence",
        "review_state": "deterministic-cutout-rig-key-poses-technically-qualified",
        "required_current_visuals": list(REQUIRED_V072_CURRENT_VISUALS),
        "images": [
            {
                "archive_name": name,
                "source_path": f"docs/evidence/{name}",
                "revision_id": ANCHOR_REVISION_ID,
                "sha256": digest(evidence / name),
                "role": "v0.7.2 deterministic cutout-rig occlusion/gait technical qualification evidence",
            }
            for name in REQUIRED_V072_CURRENT_VISUALS
        ],
        "human_visual_review": "required",
        "production_approval": "not-granted",
        "external_approval": "not-claimed",
    }
    path = evidence / "review-visuals-v0.7.2.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "REVIEW_VISUAL_MANIFEST_MATERIALIZED", "path": str(path), "count": len(REQUIRED_V072_CURRENT_VISUALS)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
