"""Install UGAS metadata into a consumer project.

This wrapper keeps the bootstrap usable directly from a Git checkout. With no
profile, it records a pending selection when project evidence is insufficient.
"""

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.installer import install_consumer


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a UGAS .game-assets bootstrap")
    parser.add_argument("consumer_root", type=Path)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--policy", default="local-first", choices=["free-first", "local-first", "remote-first", "paid-disabled"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = install_consumer(ROOT, args.consumer_root, args.profile, args.policy, args.force)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
