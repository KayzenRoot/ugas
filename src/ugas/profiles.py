"""Profile loading and validation helpers."""

import json
from pathlib import Path

from .constants import PROFILES


def load_profile(repo_root: Path, profile_id: str) -> dict:
    if profile_id not in PROFILES:
        raise ValueError(f"Unknown profile: {profile_id}")
    path = repo_root / "profiles" / f"{profile_id}.json"
    with path.open(encoding="utf-8") as stream:
        profile = json.load(stream)
    if profile.get("id") != profile_id:
        raise ValueError(f"Profile id mismatch in {path}")
    return profile
