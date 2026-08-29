"""Detect local capability without downloading models."""

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.providers import detect_local_gpu_capability


def main() -> int:
    parser = argparse.ArgumentParser(description="UGAS render capability probe")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(detect_local_gpu_capability(args.dry_run), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
