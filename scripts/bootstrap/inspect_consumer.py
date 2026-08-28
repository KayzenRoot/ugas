"""Inspect a consumer project without mutating it."""

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.context import resolve_project_context


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a consumer project for UGAS")
    parser.add_argument("consumer_root", type=Path)
    parser.add_argument("--dimension", choices=["2d", "3d", "unknown"])
    args = parser.parse_args()
    print(json.dumps(resolve_project_context(args.consumer_root, args.dimension).to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
