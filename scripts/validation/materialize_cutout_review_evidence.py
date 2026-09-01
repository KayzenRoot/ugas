"""Bind the active v0.7.3 cutout-rig review roles to canonical evidence files."""

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

REQUIRED_V073_CURRENT_VISUALS = (
    "cutout-structural-core-v073.json",
    "cutout-structural-core-mask-v073.png",
    "cutout-authorized-occlusion-regions-v073.json",
    "cutout-layer-integrity-v073.json",
    "cutout-layer-integrity-calibration-v073.json",
    "cutout-structural-coverage-v073.json",
    "cutout-structural-hole-owner-diagnostics-v073.json",
    "cutout-pairwise-overlap-matrix-v073.json",
    "cutout-seam-topology-qa-v073.json",
    "cutout-retention-occlusion-v073.json",
    "cutout-q0-regression-v073.png",
    "cutout-q0-regression-v073-qa.json",
    "cutout-k1-contact-left-v073.png",
    "cutout-k2-passing-left-v073.png",
    "cutout-k3-contact-right-v073.png",
    "cutout-k4-passing-right-v073.png",
    "cutout-key-poses-checkerboard-v073.png",
    "cutout-key-poses-waist-zoom-v073.png",
    "cutout-structural-hole-overlay-v073.png",
    "cutout-key-poses-target-detected-overlays-v073.png",
    "cutout-rig-provider-qualification-v073.json",
    "execution-evidence-v0.7.3.json",
)

REQUIRED_V080_CURRENT_VISUALS = (
    ("front-walk-cycle-v1-config.json", "docs/evidence/front-walk-cycle-v1-config.json"),
    ("front-walk-targets-v080.json", "docs/evidence/front-walk-targets-v080.json"),
    ("front-walk-z-order-v080.json", "docs/evidence/front-walk-z-order-v080.json"),
    ("front-walk-per-frame-qa-v080.json", "docs/evidence/front-walk-per-frame-qa-v080.json"),
    ("front-walk-temporal-qa-v080.json", "docs/evidence/front-walk-temporal-qa-v080.json"),
    ("front-walk-foot-contact-qa-v080.json", "docs/evidence/front-walk-foot-contact-qa-v080.json"),
    ("front-walk-half-cycle-qa-v080.json", "docs/evidence/front-walk-half-cycle-qa-v080.json"),
    ("front-walk-loop-qa-v080.json", "docs/evidence/front-walk-loop-qa-v080.json"),
    ("front-walk-structural-coverage-v080.json", "docs/evidence/front-walk-structural-coverage-v080.json"),
    ("front-walk-layer-integrity-v080.json", "docs/evidence/front-walk-layer-integrity-v080.json"),
    ("front-walk-occlusion-v080.json", "docs/evidence/front-walk-occlusion-v080.json"),
    ("front-walk-retention-v080.json", "docs/evidence/front-walk-retention-v080.json"),
    ("front-walk-provider-qualification-v080.json", "docs/evidence/front-walk-provider-qualification-v080.json"),
    ("execution-evidence-v0.8.0.json", "docs/evidence/execution-evidence-v0.8.0.json"),
    ("walk-front-spritesheet-v080.png", "docs/evidence/walk-front-v080/walk-front-spritesheet-v080.png"),
    ("walk-front-metadata-v080.json", "docs/evidence/walk-front-v080/walk-front-metadata-v080.json"),
    ("walk-front-preview-v080.gif", "docs/evidence/walk-front-v080/walk-front-preview-v080.gif"),
    ("walk-front-package-manifest-v080.json", "docs/evidence/walk-front-v080/walk-front-package-manifest-v080.json"),
    ("front-walk-evidence-contact-sheet-v080.png", "docs/evidence/walk-front-v080/front-walk-evidence-contact-sheet-v080.png"),
    ("front-walk-checkerboard-contact-sheet-v080.png", "docs/evidence/walk-front-v080/front-walk-checkerboard-contact-sheet-v080.png"),
    ("front-walk-target-detected-overlays-v080.png", "docs/evidence/walk-front-v080/front-walk-target-detected-overlays-v080.png"),
    ("front-walk-structural-hole-maps-v080.png", "docs/evidence/walk-front-v080/front-walk-structural-hole-maps-v080.png"),
    ("front-walk-waist-hip-zoom-v080.png", "docs/evidence/walk-front-v080/front-walk-waist-hip-zoom-v080.png"),
    ("front-walk-feet-ground-zoom-v080.png", "docs/evidence/walk-front-v080/front-walk-feet-ground-zoom-v080.png"),
    ("front-walk-sword-hand-zoom-v080.png", "docs/evidence/walk-front-v080/front-walk-sword-hand-zoom-v080.png"),
)
REQUIRED_V080_CURRENT_VISUALS += tuple((f"frame-{index:02d}-{phase}.png", f"docs/evidence/walk-front-v080/frames/frame-{index:02d}-{phase}.png") for index, phase in enumerate(("contact-left", "down-left", "passing-left", "up-left", "contact-right", "down-right", "passing-right", "up-right")))
REQUIRED_V080_CURRENT_VISUALS += tuple((f"{folder}-frame-{index:02d}-{phase}.png", f"docs/evidence/walk-front-v080/{folder}/frame-{index:02d}-{phase}.png") for folder in ("checkerboard", "target-detected-overlays", "structural-hole-maps") for index, phase in enumerate(("contact-left", "down-left", "passing-left", "up-left", "contact-right", "down-right", "passing-right", "up-right")))
REQUIRED_V080_CURRENT_VISUALS += tuple((f"{folder}-frame-{index:02d}.json", f"docs/evidence/walk-front-v080/{folder}/frame-{index:02d}.json") for folder in ("pairwise", "retention") for index in range(8))


def digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    evidence = ROOT / "docs" / "evidence"
    v080_status = evidence / "front-walk-provider-qualification-v080.json"
    if v080_status.is_file():
        current = REQUIRED_V080_CURRENT_VISUALS
        missing = [archive for archive, source in current if not (ROOT / source).is_file()]
        if missing:
            print(json.dumps({"status": "REVIEW_VISUAL_MANIFEST_FAILED", "missing": missing}, indent=2))
            return 2
        manifest = {
            "schema_version": "0.8.0", "manifest_type": "review-visual-evidence", "review_state": "deterministic-front-walk-8frame-pilot-technically-qualified",
            "required_current_visuals": [archive for archive, _ in current],
            "images": [{"archive_name": archive, "source_path": source, "revision_id": ANCHOR_REVISION_ID, "sha256": digest(ROOT / source), "role": "v0.8.0 deterministic front-walk pilot evidence"} for archive, source in current],
            "human_visual_review": "required", "production_approval": "not-granted", "external_approval": "not-claimed",
        }
        path = evidence / "review-visuals-v0.8.0.json"
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": "REVIEW_VISUAL_MANIFEST_MATERIALIZED", "path": str(path), "count": len(current)}, indent=2))
        return 0
    missing = [name for name in REQUIRED_V073_CURRENT_VISUALS if not (evidence / name).is_file()]
    if missing:
        print(json.dumps({"status": "REVIEW_VISUAL_MANIFEST_FAILED", "missing": missing}, indent=2))
        return 2
    manifest = {
        "schema_version": "0.7.3",
        "manifest_type": "review-visual-evidence",
        "review_state": "deterministic-cutout-rig-structural-coverage-technically-qualified",
        "required_current_visuals": list(REQUIRED_V073_CURRENT_VISUALS),
        "images": [
            {
                "archive_name": name,
                "source_path": f"docs/evidence/{name}",
                "revision_id": ANCHOR_REVISION_ID,
                "sha256": digest(evidence / name),
                "role": "v0.7.3 deterministic cutout-rig structural coverage technical qualification evidence",
            }
            for name in REQUIRED_V073_CURRENT_VISUALS
        ],
        "human_visual_review": "required",
        "production_approval": "not-granted",
        "external_approval": "not-claimed",
    }
    path = evidence / "review-visuals-v0.7.3.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "REVIEW_VISUAL_MANIFEST_MATERIALIZED", "path": str(path), "count": len(REQUIRED_V073_CURRENT_VISUALS)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
