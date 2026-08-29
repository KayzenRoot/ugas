"""Command-line entry point for UGAS bootstrap and dry-run contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .context import resolve_project_context
from .installer import install_consumer
from .providers import comfyui_healthcheck, detect_local_gpu_capability
from .router import route_request


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ugas", description="Universal Game Asset Studio V0.2 bootstrap tools")
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="create .game-assets in a consumer project")
    install.add_argument("consumer_root", type=Path)
    install.add_argument("--profile", default=None)
    install.add_argument("--policy", default="local-first", choices=["free-first", "local-first", "remote-first", "paid-disabled"])
    install.add_argument("--force", action="store_true")

    inspect = sub.add_parser("inspect", help="inspect a consumer project")
    inspect.add_argument("consumer_root", type=Path)
    inspect.add_argument("--dimension", choices=["2d", "3d", "unknown"])
    inspect.add_argument("--profile")

    route = sub.add_parser("route", help="classify and route an asset request without generating assets")
    route.add_argument("request")
    route.add_argument("--policy", default="local-first", choices=["free-first", "local-first", "remote-first", "paid-disabled"])
    route.add_argument("--engine", default="unknown")
    route.add_argument("--comfyui", choices=["available", "unavailable", "unknown"], default="unknown")
    route.add_argument("--render-node", choices=["available", "unavailable", "unknown"], default="unknown")
    route.add_argument("--huggingface", choices=["available", "unavailable", "unknown"], default="unknown")

    comfy = sub.add_parser("comfyui-health", help="run or simulate a ComfyUI healthcheck")
    comfy.add_argument("--url", default="http://127.0.0.1:8188")
    comfy.add_argument("--dry-run", action="store_true")

    capability = sub.add_parser("capability", help="inspect render capability without downloading models")
    capability.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "install":
        print(json.dumps(install_consumer(_repo_root(), args.consumer_root, args.profile, args.policy, args.force), indent=2, ensure_ascii=False))
    elif args.command == "inspect":
        print(json.dumps(resolve_project_context(args.consumer_root, args.dimension, args.profile).to_dict(), indent=2, ensure_ascii=False))
    elif args.command == "route":
        result = route_request(args.request, policy=args.policy, engine=args.engine, providers={
            "provider-comfyui": args.comfyui,
            "provider-remote-render-node": args.render_node,
            "provider-huggingface": args.huggingface,
        })
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "comfyui-health":
        print(json.dumps(comfyui_healthcheck(args.url, dry_run=args.dry_run), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(detect_local_gpu_capability(dry_run=args.dry_run), indent=2, ensure_ascii=False))
    return 0
