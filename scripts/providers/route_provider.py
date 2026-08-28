"""Classify and route a request without invoking a provider."""

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.router import route_request


def main() -> int:
    parser = argparse.ArgumentParser(description="UGAS dry-run provider router")
    parser.add_argument("--request", required=True)
    parser.add_argument("--policy", default="local-first", choices=["free-first", "local-first", "remote-first", "paid-disabled"])
    parser.add_argument("--engine", default="unknown")
    parser.add_argument("--comfyui", choices=["available", "unavailable"], default="available")
    parser.add_argument("--render-node", choices=["available", "unavailable"], default="available")
    parser.add_argument("--dry-run", action="store_true", help="kept for script symmetry; routing is always dry-run")
    args = parser.parse_args()
    result = route_request(args.request, policy=args.policy, engine=args.engine, providers={
        "provider-comfyui": args.comfyui == "available",
        "provider-remote-render-node": args.render_node == "available",
    })
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result["asset_studio_relevant"] or result.get("provider") else 2


if __name__ == "__main__":
    raise SystemExit(main())
