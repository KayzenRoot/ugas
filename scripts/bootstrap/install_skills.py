"""Copy a complete or scoped UGAS Agent Skills set into a consumer project."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.constants import PROFILES, PROVIDERS, SKILLS


CORE_SKILLS = [
    "game-asset-installer",
    "game-asset-orchestrator",
    "game-context-resolver",
    "game-asset-planner",
    "game-asset-tool-router",
    "game-generation-provider-router",
]
TWO_D_SKILLS = [
    "game-art-director",
    "game-art-dna",
    "game-sprite-studio",
    "game-tileset-studio",
    "game-animation-studio",
    "game-vfx-studio",
    "game-ui-asset-studio",
    "game-icon-studio",
    "game-portrait-studio",
    "game-atlas-packer",
]
THREE_D_SKILLS = [
    "game-art-director",
    "game-art-dna",
    "game-3d-model-studio",
    "game-material-studio",
    "game-rigging-studio",
    "game-animation-3d-studio",
    "game-lod-studio",
]
COMMON_QUALITY_SKILLS = [
    "game-asset-registry",
    "game-asset-reuse-engine",
    "game-asset-budget-manager",
    "game-style-consistency-auditor",
    "game-license-auditor",
    "game-asset-dependency-graph",
    "game-provenance-manager",
    "game-engine-adapter",
    "game-asset-validator",
    "game-visual-regression",
    "game-runtime-validator",
    "provider-manifest-registry",
    "provider-model-registry",
    "provider-workflow-registry",
]


def _profile_dimension(profile_id: str) -> str:
    path = ROOT / "profiles" / f"{profile_id}.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)["dimension"]


def select_skills(mode: str, profile_id: str | None, explicit: list[str] | None, providers: list[str]) -> list[str]:
    if explicit:
        return [skill for skill in SKILLS if skill in set(explicit)]
    elif mode == "full":
        selected = list(SKILLS)
    elif mode == "core":
        selected = list(CORE_SKILLS)
    else:
        if not profile_id:
            raise ValueError("--profile is required when --mode=profile")
        selected = list(CORE_SKILLS) + (THREE_D_SKILLS if _profile_dimension(profile_id) == "3d" else TWO_D_SKILLS)
        selected += COMMON_QUALITY_SKILLS
    if mode == "profile":
        selected += [provider for provider in providers if provider not in selected]
    return [skill for skill in SKILLS if skill in set(selected)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Install UGAS Agent Skills into a consumer project")
    parser.add_argument("consumer_root", type=Path)
    parser.add_argument("--destination", default=".agents/skills", help="path relative to consumer root or an absolute path")
    parser.add_argument("--mode", choices=["full", "core", "profile"], default="full", help="default is the complete 38-skill set")
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--skills", nargs="+", choices=SKILLS, help="explicit skill list; overrides --mode selection")
    parser.add_argument("--providers", nargs="+", choices=PROVIDERS, default=list(PROVIDERS), help="provider skills included in profile mode")
    parser.add_argument("--force", action="store_true", help="replace existing skill directories explicitly")
    args = parser.parse_args()
    consumer = args.consumer_root.resolve()
    destination = Path(args.destination)
    if not destination.is_absolute():
        destination = consumer / destination
    selected = select_skills(args.mode, args.profile, args.skills, args.providers)
    destination.mkdir(parents=True, exist_ok=True)
    for skill in selected:
        source = ROOT / "skills" / skill
        target = destination / skill
        if target.exists() and not args.force:
            raise FileExistsError(f"skill already exists: {target}; pass --force to replace it")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    print(f"installed {len(selected)} skills (mode={args.mode}) into {destination}")
    for skill in selected:
        print(f"- {skill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
