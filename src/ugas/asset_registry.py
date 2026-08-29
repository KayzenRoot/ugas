"""Consumer asset registry operations with duplicate hash detection."""

from __future__ import annotations

import json
from pathlib import Path


def load(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": "0.3.0", "assets": [], "registry_policy": {"reuse_before_generate": True, "provenance_required": True}}
    return json.loads(path.read_text(encoding="utf-8"))


def register(path: Path, asset: dict) -> dict:
    registry = load(path)
    asset_hash = asset.get("sha256")
    for existing in registry.get("assets", []):
        if asset_hash and asset_hash == existing.get("sha256"):
            return {"registered": False, "duplicate_of": existing.get("id"), "registry": registry}
    registry.setdefault("assets", []).append(asset)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"registered": True, "asset": asset, "registry": registry}
