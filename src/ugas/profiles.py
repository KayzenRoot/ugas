"""Profile loading and validation helpers."""

import json
from pathlib import Path

from .constants import PROFILES


PENDING_PROFILE = {
    "schema_version": "0.2.1",
    "id": "profile-pending",
    "name": "Profile selection pending",
    "dimension": "unknown",
    "description": "A complete placeholder profile used until the consumer chooses a specialized game profile.",
    "use_cases": [],
    "artistic_parameters": {"style_keywords": [], "palette": "project-defined", "shape_language": "project-defined", "consistency_rules": []},
    "technical_parameters": {"formats": ["JSON"], "default_sprite_size": "project-defined", "color_space": "sRGB"},
    "asset_structure": {},
    "budgets": {},
    "provider_guidance": [],
    "naming": {"pattern": "<category>_<subject>_<variant>_<revision>", "case": "snake_case", "stable_id_required": True},
    "animation": {"recommendation": "define after profile selection", "default_fps": 12, "loop_by_default": False},
    "limitations": ["profile selection is pending"],
    "selection_status": "pending",
    "profile_recommendation": None,
    "profile_confidence": "unknown",
    "profile_evidence": [],
}


def load_profile(repo_root: Path, profile_id: str) -> dict:
    if profile_id not in PROFILES:
        raise ValueError(f"Unknown profile: {profile_id}")
    path = repo_root / "profiles" / f"{profile_id}.json"
    with path.open(encoding="utf-8") as stream:
        profile = json.load(stream)
    if profile.get("id") != profile_id:
        raise ValueError(f"Profile id mismatch in {path}")
    profile.setdefault("schema_version", "0.2.1")
    return profile


def resolve_profile(repo_root: Path, profile_id: str | None, context) -> tuple[dict, str, str, list[str]]:
    if profile_id:
        profile = load_profile(repo_root, profile_id)
        return profile, profile_id, "high", ["explicit profile selection"]
    if context.profile_recommendation:
        profile = load_profile(repo_root, context.profile_recommendation)
        return profile, context.profile_recommendation, context.profile_confidence, context.profile_evidence
    return dict(PENDING_PROFILE), PENDING_PROFILE["id"], "unknown", []
