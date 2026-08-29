"""Review-evidence manifest integrity checks for v0.4.2."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping


REQUIRED_V042_VISUAL_EVIDENCE = {
    "quality-benchmark-contact-sheet.png",
    "quality-benchmark.json",
    "master-selected-before-bg.png",
    "master-selected-transparent.png",
    "master-selected-checkerboard.png",
    "reference-edit-before-after.png",
    "reference-edit-transparent.png",
    "reference-edit-checkerboard.png",
    "revision-chain.json",
    "reference-edit-qa.json",
    "transparency-qa-master.json",
    "transparency-qa-reference-edit.json",
}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_review_visual_manifest(manifest: Mapping[str, Any], root: Path | None = None) -> dict[str, Any]:
    """Reject missing, aliased or hash-inconsistent logical visual roles."""
    items = manifest.get("images") if isinstance(manifest, Mapping) else None
    items = items if isinstance(items, list) else []
    by_name = {str(item.get("archive_name")): item for item in items if isinstance(item, Mapping)}
    missing = sorted(REQUIRED_V042_VISUAL_EVIDENCE - set(by_name))
    failures: list[str] = [f"missing visual evidence: {name}" for name in missing]
    master = by_name.get("master-selected-transparent.png")
    reference = by_name.get("reference-edit-transparent.png")
    if master and reference:
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
        "required_count": len(REQUIRED_V042_VISUAL_EVIDENCE),
        "listed_count": len(by_name),
        "failures": failures,
    }
