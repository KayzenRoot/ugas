"""Copy selected UGAS Agent Skills into a consumer project."""

from pathlib import Path
import argparse
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.constants import SKILLS


DEFAULT_SKILLS = [
    "game-asset-installer",
    "game-asset-orchestrator",
    "game-context-resolver",
    "game-asset-planner",
    "game-asset-tool-router",
    "game-generation-provider-router",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Install UGAS Agent Skills into a consumer project")
    parser.add_argument("consumer_root", type=Path)
    parser.add_argument("--destination", default=".agents/skills", help="path relative to consumer root or an absolute path")
    parser.add_argument("--skills", nargs="+", choices=SKILLS, default=DEFAULT_SKILLS)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    consumer = args.consumer_root.resolve()
    destination = Path(args.destination)
    if not destination.is_absolute():
        destination = consumer / destination
    destination.mkdir(parents=True, exist_ok=True)
    installed = []
    for skill in args.skills:
        source = ROOT / "skills" / skill
        target = destination / skill
        if target.exists() and not args.force:
            raise FileExistsError(f"skill already exists: {target}; pass --force to replace it")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        installed.append(skill)
    print(f"installed {len(installed)} skills into {destination}")
    for skill in installed:
        print(f"- {skill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
