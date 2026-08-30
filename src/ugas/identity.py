"""Canonical identity manifest binding the v0.5 experiments to R4."""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from .constants import UGAS_VERSION
from .image_utils import inspect_png, sha256

ANCHOR_ASSET_ID = "asset-2fec6fed1d714d0cb58ad75b56d7ba71"
ANCHOR_REVISION_ID = "revision-3a425d184b1a49be9f6d6c8d52d04b96"
ANCHOR_SHA256 = "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798"


class IdentityManifestError(ValueError):
    pass


def _bbox_stats(path: Path) -> dict[str, Any]:
    from PIL import Image
    with Image.open(path) as opened:
        image = opened.convert("RGBA"); alpha = image.getchannel("A"); bbox = alpha.getbbox()
        if not bbox: raise IdentityManifestError("canonical anchor has no foreground alpha")
        pixels = image.load(); samples = [pixels[x, y][:3] for y in range(image.height) for x in range(image.width) if pixels[x, y][3] > 220]
        if not samples: raise IdentityManifestError("canonical anchor has no opaque foreground")
        mean = [round(statistics.fmean(item[channel] for item in samples), 3) for channel in range(3)]
        palette = image.convert("RGB").quantize(colors=8, method=Image.Quantize.MEDIANCUT).getpalette()
        colors = []
        for index in range(8):
            colors.append([int(palette[index * 3]), int(palette[index * 3 + 1]), int(palette[index * 3 + 2])])
        left, top, right, bottom = bbox
        return {"alpha_bbox": [left, top, right, bottom], "normalized_size": {"width": round((right - left) / image.width, 6), "height": round((bottom - top) / image.height, 6)}, "mean_rgb": mean, "palette": colors, "pivot": {"x": round((left + right) / 2, 3), "y": bottom, "normalized_x": round(((left + right) / 2) / image.width, 6), "normalized_y": round(bottom / image.height, 6)}, "opaque_pixels": len(samples)}


def _find_anchor(repo_root: Path, asset_id: str) -> Path:
    if asset_id != ANCHOR_ASSET_ID:
        raise IdentityManifestError(f"v0.5 pilot is bound to the approved R4 anchor {ANCHOR_ASSET_ID}")
    path = repo_root / "docs" / "evidence" / "reference-edit-selected-transparent.png"
    if not path.is_file(): raise IdentityManifestError(f"missing canonical R4 anchor: {path}")
    if sha256(path) != ANCHOR_SHA256: raise IdentityManifestError("canonical R4 anchor hash mismatch")
    return path


def build_identity_manifest(repo_root: Path, asset_id: str = ANCHOR_ASSET_ID) -> dict[str, Any]:
    path = _find_anchor(repo_root, asset_id); image = inspect_png(path); stats = _bbox_stats(path)
    manifest = {
        "schema_version": UGAS_VERSION, "manifest_type": "character-identity", "asset_id": asset_id,
        "character_id": "ugas-character-r4-canonical", "canonical_revision": {"revision_id": ANCHOR_REVISION_ID, "asset_id": asset_id, "path": str(path.relative_to(repo_root)).replace("\\", "/"), "sha256": ANCHOR_SHA256, "dimensions": {"width": image["width"], "height": image["height"]}, "transparency": {"required": True, "has_alpha": image["has_alpha"], "transparent_pixels": image["has_transparent_pixels"]}},
        "identity_signature": {"palette": stats["palette"], "armor": {"material": "blue-steel/cobalt metallic armor", "mean_rgb": stats["mean_rgb"]}, "cloth": {"material": "black cloth", "protected": True}, "skin": {"protected": True}, "head": {"protected": True}, "weapon": {"type": "sword", "protected": True}, "proportions": {"normalized_subject_width": stats["normalized_size"]["width"], "normalized_subject_height": stats["normalized_size"]["height"]}},
        "geometry": {"alpha_bbox": stats["alpha_bbox"], "normalized_size": stats["normalized_size"], "pivot_policy": "centerline of alpha bbox at foot baseline", "ground_policy": "lowest opaque pixel is baseline; no stretch", "pivot": stats["pivot"]},
        "protected_properties": ["face", "head", "skin", "armor silhouette", "black cloth", "sword presence", "body proportions", "palette identity", "transparent background"],
        "allowed_transforms": ["pose/view conditioning through reference[1]", "translation to shared pivot", "alpha normalization without stretch"],
        "art_dna": {"profile": "profiles/generic-2d.json", "style_reference": "source-controlled canonical R4"},
        "external_pipeline_anchor": {"status": "APPROVED AS A PIPELINE IDENTITY ANCHOR FOR THE NEXT EXPERIMENTAL INCREMENT", "approval_type": "external-pipeline-anchor", "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256, "production_approval": "not-granted", "production_ready_governance": "preserved"},
        "source_image_inspection": image,
    }
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return manifest


def validate_identity_manifest(manifest: dict[str, Any], repo_root: Path | None = None) -> dict[str, Any]:
    required = {"schema_version", "asset_id", "character_id", "canonical_revision", "identity_signature", "geometry", "protected_properties", "allowed_transforms", "external_pipeline_anchor"}
    failures = [f"missing:{key}" for key in sorted(required - set(manifest))]
    canonical = manifest.get("canonical_revision", {})
    if canonical.get("revision_id") != ANCHOR_REVISION_ID or canonical.get("sha256") != ANCHOR_SHA256: failures.append("canonical_anchor_binding_invalid")
    approval = manifest.get("external_pipeline_anchor", {})
    if approval.get("approval_type") != "external-pipeline-anchor" or approval.get("production_approval") != "not-granted": failures.append("approval_scope_invalid")
    if repo_root is not None:
        path = repo_root / str(canonical.get("path", ""))
        if not path.is_file() or sha256(path) != ANCHOR_SHA256: failures.append("canonical_file_hash_invalid")
    return {"status": "IDENTITY_MANIFEST_VALID" if not failures else "IDENTITY_MANIFEST_INVALID", "failures": failures, "manifest_sha256": manifest.get("manifest_sha256")}


def write_identity_manifest(repo_root: Path, output: Path | None = None, asset_id: str = ANCHOR_ASSET_ID) -> dict[str, Any]:
    manifest = build_identity_manifest(repo_root, asset_id); target = output or repo_root / "docs" / "evidence" / "identity-manifest.json"; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": validate_identity_manifest(manifest, repo_root)["status"], "manifest": str(target), "asset_id": asset_id, "canonical_sha256": ANCHOR_SHA256, "validation": validate_identity_manifest(manifest, repo_root)}
