"""Validate the v0.12.3 GitHub review manifest and its visual hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(manifest_path: Path, visual_path: Path) -> dict[str, object]:
    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "schemas/github-review-manifest-v1.json").read_text(encoding="utf-8"))
        validate_schema_document(schema)
        validate_instance(manifest, schema)
        visuals = json.loads(visual_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return {"status": "GITHUB_REVIEW_MANIFEST_FAILED", "failures": [f"schema:{type(exc).__name__}: {exc}"]}

    if manifest.get("pull_request", {}).get("base_sha") == manifest.get("pull_request", {}).get("head_sha"):
        # A local rehearsal may use the baseline HEAD before the feature commit,
        # but it must still expose the uncommitted changed-file set.
        if not manifest.get("changed_files"):
            failures.append("local-rehearsal-has-no-changed-files")
    paths: set[str] = set()
    for item in manifest.get("changed_files", []):
        path = str(item.get("path", ""))
        if not path or Path(path).is_absolute() or path.startswith(("\\", "//")):
            failures.append(f"changed-file-path-not-relative:{path}")
        if path in paths:
            failures.append(f"duplicate-changed-file:{path}")
        paths.add(path)
    forbidden_suffixes = (".safetensors", ".ckpt", ".gguf", ".onnx")
    if any(str(item.get("path", "")).casefold().endswith(forbidden_suffixes) for item in manifest.get("changed_files", [])):
        failures.append("forbidden-model-artifact-in-change-set")
    if manifest.get("known_gaps") is None:
        failures.append("known-gaps-missing")
    visual_items = visuals.get("visuals") if isinstance(visuals, dict) else None
    if not isinstance(visual_items, list) or len(visual_items) != 2:
        failures.append("visual-manifest-must-contain-two-v0122-dashboard-pngs")
        visual_items = []
    expected = {
        "docs/evidence/observability-v0122/dashboard-docker-overview-v0122.png",
        "docs/evidence/observability-v0122/dashboard-docker-live-activity-v0122.png",
    }
    listed = {str(item.get("path")) for item in visual_items if isinstance(item, dict)}
    if listed != expected:
        failures.append("visual-manifest-paths-invalid")
    for item in visual_items:
        if not isinstance(item, dict):
            failures.append("visual-manifest-item-not-object")
            continue
        relative = str(item.get("path", ""))
        source = ROOT / relative
        if not source.is_file():
            failures.append(f"visual-missing:{relative}")
            continue
        if item.get("media_type") != "image/png":
            failures.append(f"visual-media-type-invalid:{relative}")
        if item.get("byte_size") != source.stat().st_size:
            failures.append(f"visual-size-mismatch:{relative}")
        if item.get("sha256") != digest(source):
            failures.append(f"visual-hash-mismatch:{relative}")
    return {"status": "GITHUB_REVIEW_MANIFEST_PASSED" if not failures else "GITHUB_REVIEW_MANIFEST_FAILED", "failures": failures, "changed_file_count": len(manifest.get("changed_files", [])), "visual_count": len(visual_items), "base_sha": manifest.get("pull_request", {}).get("base_sha"), "head_sha": manifest.get("pull_request", {}).get("head_sha")}


if __name__ == "__main__":
    manifest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/evidence/github-review-v0123/github-review-manifest-local.json"
    visual = Path(sys.argv[2]) if len(sys.argv) > 2 else manifest.with_name("visual-manifest.json")
    result = validate(manifest, visual)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "GITHUB_REVIEW_MANIFEST_PASSED" else 1)
