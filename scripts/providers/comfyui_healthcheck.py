"""ComfyUI readiness probe; defaults to a no-network dry run."""

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.providers import comfyui_healthcheck


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or simulate the UGAS ComfyUI contract")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = comfyui_healthcheck(args.url, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"dry-run-ready", "healthy"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
