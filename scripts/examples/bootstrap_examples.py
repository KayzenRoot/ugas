"""Recreate example consumer metadata from the repository profiles."""

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.installer import install_consumer


EXAMPLES = {
    "consumer-godot-2d": "topdown-rpg-mmorpg-2d",
    "consumer-space-idle-2d": "space-idle-strategy-2d",
    "consumer-generic-3d": "stylized-3d",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the tracked UGAS examples")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for name, profile in EXAMPLES.items():
        result = install_consumer(ROOT, ROOT / "examples" / name, profile, "local-first", args.force)
        print(f"{name}: {result['status']} ({profile})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
