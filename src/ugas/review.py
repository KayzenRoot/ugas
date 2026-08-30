"""Review-evidence manifest integrity checks for historical and current slices."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping


REQUIRED_V043_REVIEW_EVIDENCE = {
    "master-selected-before-bg.png",
    "master-selected-checkerboard.png",
    "reference-edit-config-benchmark-contact-sheet.png",
    "reference-edit-config-benchmark.json",
    "reference-edit-candidates-contact-sheet.png",
    "reference-edit-candidates.json",
    "reference-edit-selected-rgb.png",
    "reference-edit-selected-transparent.png",
    "reference-edit-selected-checkerboard.png",
    "reference-edit-before-after.png",
    "reference-edit-diff-heatmap.png",
    "reference-edit-target-mask.png",
    "reference-edit-protected-mask.png",
    "reference-edit-contract.json",
    "reference-edit-fidelity.json",
    "reference-edit-execution-evidence.json",
    "reference-edit-workflow-qualification.json",
    "revision-chain.json",
    "reference-edit-qa.json",
    "reference-edit-transparency-qa.json",
}

# Kept as a compatibility import for the v0.4.2 regression test module. The
# active manifest is intentionally the v0.4.3 contract above.
REQUIRED_V042_VISUAL_EVIDENCE = REQUIRED_V043_REVIEW_EVIDENCE

REQUIRED_V050_REVIEW_EVIDENCE = {
    "v043-approved-anchor.png", "multiref-ab-contact-sheet.png", "pose-guides-contact-sheet.png",
    "directional-anchors-contact-sheet.png", "anchor-front.png", "anchor-left.png", "anchor-right.png", "anchor-back.png",
    "walk-front-8-contact-sheet.png", "walk-front-8-spritesheet.png", "walk-front-8-preview.gif", "walk-frame-diff-contact.png",
}

REQUIRED_V051_BASE_REVIEW_EVIDENCE = {
    "v050-baseline-walk-contact.png",
    "pose-guides-v2-contact-sheet.png",
    "pose-guide-v2-control-example.png",
    "multiref-v2-ab-contact-sheet.png",
}
REQUIRED_V051_ANCHOR_REVIEW_EVIDENCE = REQUIRED_V051_BASE_REVIEW_EVIDENCE | {
    "directional-anchor-candidates-v2-contact-sheet.png",
    "directional-anchors-v2-contact-sheet.png",
}
REQUIRED_V051_WALK_REVIEW_EVIDENCE = REQUIRED_V051_ANCHOR_REVIEW_EVIDENCE | {
    "walk-v2-candidates-contact-sheet.png",
    "walk-v2-selected-contact-sheet.png",
    "walk-v2-pose-overlay-contact.png",
    "walk-v2-identity-drift-contact.png",
    "walk-v2-spritesheet.png",
    "walk-v2-preview.gif",
}
REQUIRED_V052_REVIEW_EVIDENCE = {
    "v051-gap-baseline.png",
    "openpose-guide-v3-control-example.png",
    "openpose-guides-v3-contact-sheet.png",
    "native-reference-order-abc-contact-sheet.png",
    "refcontrol-strength-benchmark-contact-sheet.png",
    "refcontrol-pose-overlay-contact.png",
}
REQUIRED_V053_REVIEW_EVIDENCE = {
    "pose-metric-calibration-contact-sheet.png",
    "pose-metric-negative-controls-contact-sheet.png",
    "v052-refcontrol-baseline-contact.png",
    "v053-pose-detection-overlay-contact.png",
}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    data = path.read_bytes()
    # Git may materialize tracked text as CRLF on Windows. Evidence hashes
    # describe canonical LF content; binary visual assets remain byte-exact.
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    digest.update(data)
    return digest.hexdigest()


def validate_review_visual_manifest(manifest: Mapping[str, Any], root: Path | None = None) -> dict[str, Any]:
    """Reject missing, aliased or hash-inconsistent logical visual roles."""
    items = manifest.get("images") if isinstance(manifest, Mapping) else None
    items = items if isinstance(items, list) else []
    by_name = {str(item.get("archive_name")): item for item in items if isinstance(item, Mapping)}
    schema_version = str(manifest.get("schema_version"))
    if schema_version == "0.5.0":
        required = REQUIRED_V050_REVIEW_EVIDENCE
    elif schema_version == "0.5.1":
        state = str(manifest.get("review_state", "multiref-gap"))
        required = REQUIRED_V051_WALK_REVIEW_EVIDENCE if state == "walk" else REQUIRED_V051_ANCHOR_REVIEW_EVIDENCE if state == "anchors" else REQUIRED_V051_BASE_REVIEW_EVIDENCE
    elif schema_version == "0.5.2":
        required = REQUIRED_V052_REVIEW_EVIDENCE
    elif schema_version == "0.5.3":
        required = REQUIRED_V053_REVIEW_EVIDENCE
    else:
        required = REQUIRED_V043_REVIEW_EVIDENCE
    missing = sorted(required - set(by_name))
    failures: list[str] = [f"missing visual evidence: {name}" for name in missing]
    role_pairs = [] if schema_version in {"0.5.0", "0.5.1"} else [
        (by_name.get("master-selected-checkerboard.png"), by_name.get("reference-edit-selected-checkerboard.png")),
        (by_name.get("master-selected-transparent.png"), by_name.get("reference-edit-selected-transparent.png")),
    ]
    # Keep the v0.4.2 role names checkable for the immutable historical
    # regression fixture; the active v0.4.3 manifest uses the roles above.
    if "reference-edit-transparent.png" in by_name:
        role_pairs.append((by_name.get("master-selected-transparent.png"), by_name.get("reference-edit-transparent.png")))
    for master, reference in role_pairs:
        if not master or not reference:
            continue
        for field in ("source_path", "revision_id", "sha256"):
            if not master.get(field) or not reference.get(field):
                failures.append(f"transparent role missing {field}")
        if master.get("source_path") == reference.get("source_path"):
            failures.append("transparent roles share a source path")
        if master.get("revision_id") == reference.get("revision_id"):
            failures.append("transparent roles share a revision_id")
        if master.get("sha256") == reference.get("sha256"):
            failures.append("transparent roles share a sha256")
    if root is not None:
        root = Path(root).resolve()
        for item in items:
            source = Path(str(item.get("source_path", "")))
            if not source.is_absolute():
                source = root / source
            if not source.is_file():
                failures.append(f"missing visual source: {source}")
                continue
            expected = item.get("sha256")
            if expected and _digest(source) != expected:
                failures.append(f"visual source hash mismatch: {item.get('archive_name')}")
    return {
        "status": "REVIEW_VISUAL_MANIFEST_PASSED" if not failures else "REVIEW_VISUAL_MANIFEST_FAILED",
        "required_count": len(required),
        "listed_count": len(by_name),
        "failures": failures,
    }
