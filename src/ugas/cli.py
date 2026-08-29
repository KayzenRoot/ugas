"""UGAS v0.3 machine-readable CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .capabilities import probe_comfy_capability
from .constants import UGAS_VERSION
from .context import resolve_project_context
from .generation import generate_image, reference_edit, sprite_pilot
from .installer import install_consumer
from .model_registry import load_registry, load_model, verify_model_files
from .providers import comfyui_healthcheck
from .render_node import doctor, lifecycle, probe, setup
from .router import route_request
from .workflow_registry import load_workflows, load_workflow, validate_api_workflow
from .comfyui_client import ComfyUIClient


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _json(value: object) -> None:
    # Windows PowerShell may expose a legacy CP1252 stdout.  Keep the CLI
    # machine-readable even when diagnostic text contains Unicode (for
    # example, ComfyUI's VRAM summary can contain "≈").
    print(json.dumps(value, indent=2, ensure_ascii=True, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ugas", description="Universal Game Asset Studio 0.3.0")
    parser.add_argument("--version", action="version", version=UGAS_VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install"); install.add_argument("consumer_root", type=Path); install.add_argument("--profile"); install.add_argument("--policy", default="local-first", choices=["free-first", "local-first", "remote-first", "paid-disabled"]); install.add_argument("--force", action="store_true")
    inspect = sub.add_parser("inspect"); inspect.add_argument("consumer_root", type=Path); inspect.add_argument("--dimension", choices=["2d", "3d", "unknown"]); inspect.add_argument("--profile")
    route = sub.add_parser("route"); route.add_argument("request"); route.add_argument("--policy", default="local-first", choices=["free-first", "local-first", "remote-first", "paid-disabled"]); route.add_argument("--engine", default="unknown"); route.add_argument("--comfyui", choices=["available", "unavailable", "unknown"], default="unknown"); route.add_argument("--render-node", choices=["available", "unavailable", "unknown"], default="unknown"); route.add_argument("--huggingface", choices=["available", "unavailable", "unknown"], default="unknown")
    health = sub.add_parser("comfyui-health"); health.add_argument("--url", "--endpoint", default="http://127.0.0.1:8188"); health.add_argument("--dry-run", action="store_true")
    capability = sub.add_parser("capability"); capability.add_argument("--url", "--endpoint", default="http://127.0.0.1:8188"); capability.add_argument("--model", default="flux2-klein-4b-nvfp4"); capability.add_argument("--workflow", default="flux2-klein-4b-text-to-image"); capability.add_argument("--dry-run", action="store_true")
    doctor_parser = sub.add_parser("doctor"); doctor_parser.add_argument("--endpoint", default=None)
    render = sub.add_parser("render-node"); render_sub = render.add_subparsers(dest="render_action", required=True)
    for action in ("doctor", "setup", "start", "stop", "status", "probe"): render_sub.add_parser(action)
    providers = sub.add_parser("providers"); providers_sub = providers.add_subparsers(dest="provider_action", required=True); providers_sub.add_parser("probe").add_argument("--url", default="http://127.0.0.1:8188")
    models = sub.add_parser("models"); models_sub = models.add_subparsers(dest="model_action", required=True); models_sub.add_parser("list"); qualify = models_sub.add_parser("qualify"); qualify.add_argument("model_id"); qualify.add_argument("--root", type=Path, default=None); qualify.add_argument("--model-root", type=Path, default=None)
    workflows = sub.add_parser("workflows"); workflows_sub = workflows.add_subparsers(dest="workflow_action", required=True); workflows_sub.add_parser("list"); validate = workflows_sub.add_parser("validate"); validate.add_argument("workflow_id"); validate.add_argument("--url", default=None)
    generate = sub.add_parser("generate"); generate_sub = generate.add_subparsers(dest="generation_action", required=True)
    for name in ("image", "reference-edit", "sprite-pilot"):
        command = generate_sub.add_parser(name); command.add_argument("prompt"); command.add_argument("--url", default="http://127.0.0.1:8188"); command.add_argument("--profile", default="generic-2d"); command.add_argument("--model", default="flux2-klein-4b-nvfp4"); command.add_argument("--workflow", default="flux2-klein-4b-text-to-image"); command.add_argument("--output-dir", type=Path); command.add_argument("--seed", type=int, default=1); command.add_argument("--width", type=int, default=256); command.add_argument("--height", type=int, default=256); command.add_argument("--columns", type=int, default=1); command.add_argument("--rows", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _repo_root()
    try:
        if args.command == "install": _json(install_consumer(root, args.consumer_root, args.profile, args.policy, args.force)); return 0
        if args.command == "inspect": _json(resolve_project_context(args.consumer_root, args.dimension, args.profile).to_dict()); return 0
        if args.command == "route": _json(route_request(args.request, policy=args.policy, engine=args.engine, providers={"provider-comfyui": args.comfyui, "provider-remote-render-node": args.render_node, "provider-huggingface": args.huggingface})); return 0
        if args.command == "comfyui-health": _json(comfyui_healthcheck(args.url, dry_run=args.dry_run)); return 0
        if args.command == "capability": _json({"status": "dry-run"} if args.dry_run else probe_comfy_capability(root, ComfyUIClient(args.url), args.model, args.workflow)); return 0
        if args.command == "doctor": _json(doctor({"endpoint": args.endpoint} if args.endpoint else None)); return 0
        if args.command == "render-node":
            value = doctor() if args.render_action == "doctor" else setup() if args.render_action == "setup" else probe() if args.render_action == "probe" else lifecycle(args.render_action)
            _json(value); return 0 if value.get("status") not in {"not-ready", "blocked"} else 2
        if args.command == "providers": _json(probe({"endpoint": args.url})); return 0
        if args.command == "models":
            if args.model_action == "list": _json(load_registry(root)); return 0
            model_root = args.model_root or Path.home() / "AppData" / "Local" / "UGAS" / "comfyui" / "models"
            model = load_model(args.root or root, args.model_id); result = verify_model_files(model, model_root); _json(result); return 0 if result["qualified"] else 2
        if args.command == "workflows":
            if args.workflow_action == "list": _json({"workflows": load_workflows(root)}); return 0
            record = load_workflow(root, args.workflow_id); result = validate_api_workflow(record["api"])
            if args.url: result["live"] = probe_comfy_capability(root, ComfyUIClient(args.url), record["required_models"][0], args.workflow_id)
            _json(result); return 0 if result["valid_graph"] else 2
        if args.command == "generate":
            kwargs = {"endpoint": args.url, "prompt": args.prompt, "profile": args.profile, "model_id": args.model, "workflow_id": args.workflow, "output_dir": args.output_dir, "seed": args.seed, "width": args.width, "height": args.height, "columns": args.columns, "rows": args.rows}
            if args.generation_action != "sprite-pilot":
                kwargs.pop("columns"); kwargs.pop("rows")
            result = reference_edit(root, **kwargs) if args.generation_action == "reference-edit" else sprite_pilot(root, **kwargs) if args.generation_action == "sprite-pilot" else generate_image(root, **kwargs)
            _json(result); return 0
    except Exception as exc:
        _json({"status": "error", "error_type": type(exc).__name__, "error": str(exc)})
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
