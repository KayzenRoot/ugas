"""UGAS v0.4.3 machine-readable CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from .capabilities import probe_comfy_capability
from .comfyui_client import ComfyUIClient
from .constants import UGAS_VERSION
from .context import resolve_project_context
from .generation import (
    background_remove,
    benchmark_quality_lanes,
    candidates_show,
    generate_image,
    generate_master_sprite,
    reference_edit_pilot,
    refine_master,
    sprite_pilot,
    visual_approve,
)
from .installer import install_consumer
from .model_registry import load_model, load_registry, verify_model_files
from .providers import comfyui_healthcheck
from .render_node import doctor, lifecycle, probe, setup
from .router import route_request
from .workflow_registry import load_workflows, load_workflow, validate_api_workflow


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _json(value: object) -> None:
    import json
    print(json.dumps(value, indent=2, ensure_ascii=True, default=str))


def _json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def _common_generation(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--profile", default="generic-2d")
    parser.add_argument("--output-dir", type=Path)
    _json_flag(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ugas", description="Universal Game Asset Studio 0.4.3")
    parser.add_argument("--version", action="version", version=UGAS_VERSION)
    _json_flag(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install"); install.add_argument("consumer_root", type=Path); install.add_argument("--profile"); install.add_argument("--policy", default="local-first", choices=["free-first", "local-first", "remote-first", "paid-disabled"]); install.add_argument("--force", action="store_true"); _json_flag(install)
    inspect = sub.add_parser("inspect"); inspect.add_argument("consumer_root", type=Path); inspect.add_argument("--dimension", choices=["2d", "3d", "unknown"]); inspect.add_argument("--profile"); _json_flag(inspect)
    route = sub.add_parser("route"); route.add_argument("request"); route.add_argument("--policy", default="local-first", choices=["free-first", "local-first", "remote-first", "paid-disabled"]); route.add_argument("--engine", default="unknown"); route.add_argument("--comfyui", choices=["available", "unavailable", "unknown"], default="unknown"); route.add_argument("--render-node", choices=["available", "unavailable", "unknown"], default="unknown"); route.add_argument("--huggingface", choices=["available", "unavailable", "unknown"], default="unknown"); _json_flag(route)
    health = sub.add_parser("comfyui-health"); health.add_argument("--url", "--endpoint", default="http://127.0.0.1:8188"); health.add_argument("--dry-run", action="store_true"); _json_flag(health)
    capability = sub.add_parser("capability"); capability.add_argument("--url", "--endpoint", default="http://127.0.0.1:8188"); capability.add_argument("--model", default="flux2-klein-4b-distilled-nvfp4"); capability.add_argument("--workflow", default="flux2-klein-4b-distilled-text-to-image"); capability.add_argument("--dry-run", action="store_true"); _json_flag(capability)
    doctor_parser = sub.add_parser("doctor"); doctor_parser.add_argument("--endpoint", default=None); _json_flag(doctor_parser)
    render = sub.add_parser("render-node"); render_sub = render.add_subparsers(dest="render_action", required=True)
    for action in ("doctor", "setup", "start", "stop", "status", "probe"):
        leaf = render_sub.add_parser(action); _json_flag(leaf)
    providers = sub.add_parser("providers"); providers_sub = providers.add_subparsers(dest="provider_action", required=True); probe_parser = providers_sub.add_parser("probe"); probe_parser.add_argument("--url", default="http://127.0.0.1:8188"); _json_flag(probe_parser)
    models = sub.add_parser("models"); models_sub = models.add_subparsers(dest="model_action", required=True); list_models = models_sub.add_parser("list"); _json_flag(list_models); qualify = models_sub.add_parser("qualify"); qualify.add_argument("model_id"); qualify.add_argument("--root", type=Path, default=None); qualify.add_argument("--model-root", type=Path, default=None); _json_flag(qualify)
    workflows = sub.add_parser("workflows"); workflows_sub = workflows.add_subparsers(dest="workflow_action", required=True); list_workflows = workflows_sub.add_parser("list"); _json_flag(list_workflows); validate = workflows_sub.add_parser("validate"); validate.add_argument("workflow_id"); validate.add_argument("--url", default=None); _json_flag(validate)

    generate = sub.add_parser("generate"); generate_sub = generate.add_subparsers(dest="generation_action", required=True)
    image = generate_sub.add_parser("image"); image.add_argument("prompt"); image.add_argument("--model", default="flux2-klein-4b-distilled-nvfp4"); image.add_argument("--workflow", default="flux2-klein-4b-distilled-text-to-image"); image.add_argument("--seed", type=int, default=1); image.add_argument("--width", type=int, default=256); image.add_argument("--height", type=int, default=256); image.add_argument("--requires-transparency", action="store_true"); _common_generation(image)
    master = generate_sub.add_parser("master-sprite"); master.add_argument("prompt"); master.add_argument("--candidates", type=int, default=4); master.add_argument("--seed", type=int, default=1); master.add_argument("--width", type=int, default=512); master.add_argument("--height", type=int, default=512); master.add_argument("--transparent", action="store_true"); master.add_argument("--quality-policy", default="quality-first", choices=["quality-first", "balanced", "fast"]); _common_generation(master)
    legacy_ref = generate_sub.add_parser("reference-edit"); legacy_ref.add_argument("prompt"); legacy_ref.add_argument("--asset-id", required=True); legacy_ref.add_argument("--instruction", default=None); legacy_ref.add_argument("--url", default="http://127.0.0.1:8188"); _json_flag(legacy_ref)
    pilot = generate_sub.add_parser("sprite-pilot"); pilot.add_argument("prompt"); pilot.add_argument("--model", default="flux2-klein-4b-distilled-nvfp4"); pilot.add_argument("--workflow", default="flux2-klein-4b-distilled-text-to-image"); pilot.add_argument("--seed", type=int, default=1); pilot.add_argument("--width", type=int, default=256); pilot.add_argument("--height", type=int, default=256); pilot.add_argument("--columns", type=int, default=1); pilot.add_argument("--rows", type=int, default=1); pilot.add_argument("--requires-transparency", action="store_true"); _common_generation(pilot)

    refine = sub.add_parser("refine"); refine_sub = refine.add_subparsers(dest="refine_action", required=True); refine_master_parser = refine_sub.add_parser("master-sprite"); refine_master_parser.add_argument("asset_id"); refine_master_parser.add_argument("--instruction", required=True); refine_master_parser.add_argument("--url", default="http://127.0.0.1:8188"); _json_flag(refine_master_parser)
    reference = sub.add_parser("reference-edit"); reference_sub = reference.add_subparsers(dest="reference_action", required=True); reference_pilot = reference_sub.add_parser("pilot"); reference_pilot.add_argument("source_asset_id"); reference_pilot.add_argument("--instruction", default="Change armor color/material tint from blue steel to deep cobalt/navy steel."); reference_pilot.add_argument("--candidates", type=int, default=4); reference_pilot.add_argument("--seed-base", type=int, default=10401); reference_pilot.add_argument("--url", default="http://127.0.0.1:8188"); reference_pilot.add_argument("--output-dir", type=Path); _json_flag(reference_pilot)
    background = sub.add_parser("background"); background_sub = background.add_subparsers(dest="background_action", required=True); remove = background_sub.add_parser("remove"); remove.add_argument("image_or_asset_id"); remove.add_argument("--url", default="http://127.0.0.1:8188"); remove.add_argument("--output-dir", type=Path); _json_flag(remove)
    candidates = sub.add_parser("candidates"); candidates_sub = candidates.add_subparsers(dest="candidates_action", required=True); show = candidates_sub.add_parser("show"); show.add_argument("asset_id"); _json_flag(show)
    visual = sub.add_parser("visual"); visual_sub = visual.add_subparsers(dest="visual_action", required=True); approve = visual_sub.add_parser("approve"); approve.add_argument("asset_id"); approve.add_argument("--note", default=""); _json_flag(approve)
    benchmark = sub.add_parser("benchmark"); benchmark_sub = benchmark.add_subparsers(dest="benchmark_action", required=True); quality = benchmark_sub.add_parser("quality"); quality.add_argument("prompt"); quality.add_argument("--url", default="http://127.0.0.1:8188"); quality.add_argument("--profile", default="generic-2d"); quality.add_argument("--seed", type=int, default=4301); quality.add_argument("--width", type=int, default=512); quality.add_argument("--height", type=int, default=512); _json_flag(quality)
    asset = sub.add_parser("asset"); asset_sub = asset.add_subparsers(dest="asset_action", required=True); status = asset_sub.add_parser("status"); status.add_argument("asset_id"); _json_flag(status); verify_integrity = asset_sub.add_parser("verify-integrity"); verify_integrity.add_argument("asset_id"); _json_flag(verify_integrity)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _repo_root()
    try:
        if args.command == "install": _json(install_consumer(root, args.consumer_root, args.profile, args.policy, args.force)); return 0
        if args.command == "inspect": _json(resolve_project_context(args.consumer_root, args.dimension, args.profile).to_dict()); return 0
        if args.command == "route": _json(route_request(args.request, policy=args.policy, engine=args.engine, providers={"provider-comfyui": args.comfyui, "provider-remote-render-node": args.render_node, "provider-huggingface": args.huggingface})); return 0
        if args.command == "comfyui-health": _json(comfyui_healthcheck(args.url, dry_run=args.dry_run)); return 0
        if args.command == "capability":
            workflow_record = load_workflow(root, args.workflow)
            capability = workflow_record.get("capability", "2d")
            _json({"status": "dry-run"} if args.dry_run else probe_comfy_capability(root, ComfyUIClient(args.url), args.model, args.workflow, capability=capability)); return 0
        if args.command == "doctor": _json(doctor({"endpoint": args.endpoint} if args.endpoint else None)); return 0
        if args.command == "render-node":
            value = doctor() if args.render_action == "doctor" else setup() if args.render_action == "setup" else probe() if args.render_action == "probe" else lifecycle(args.render_action)
            _json(value); return 0 if value.get("status") not in {"not-ready", "blocked"} else 2
        if args.command == "providers": _json(probe({"endpoint": args.url})); return 0
        if args.command == "models":
            if args.model_action == "list": _json(load_registry(root)); return 0
            model_root = args.model_root or Path.home() / "AppData" / "Local" / "UGAS" / "comfyui" / "models"; model = load_model(args.root or root, args.model_id); result = verify_model_files(model, model_root); _json(result); return 0 if result["qualified"] else 2
        if args.command == "workflows":
            if args.workflow_action == "list": _json({"workflows": load_workflows(root)}); return 0
            record = load_workflow(root, args.workflow_id); result = validate_api_workflow(record["api"])
            if args.url: result["live"] = probe_comfy_capability(root, ComfyUIClient(args.url), record["required_models"][0], args.workflow_id, capability=record.get("capability", "2d"))
            _json(result); return 0 if result["valid_graph"] else 2
        if args.command == "generate":
            if args.generation_action == "master-sprite":
                _json(generate_master_sprite(root, endpoint=args.url, prompt=args.prompt, profile=args.profile, candidates=args.candidates, seed=args.seed, width=args.width, height=args.height, output_dir=args.output_dir, transparent=args.transparent, quality_policy=args.quality_policy)); return 0
            if args.generation_action == "reference-edit":
                _json(refine_master(root, args.asset_id, instruction=args.instruction or args.prompt, endpoint=args.url)); return 0
            kwargs = {"endpoint": args.url, "prompt": args.prompt, "profile": args.profile, "model_id": args.model, "workflow_id": args.workflow, "output_dir": args.output_dir, "seed": args.seed, "width": args.width, "height": args.height, "requires_transparency": args.requires_transparency}
            if args.generation_action == "sprite-pilot": kwargs.update({"columns": args.columns, "rows": args.rows}); _json(sprite_pilot(root, **kwargs)); return 0
            _json(generate_image(root, **kwargs)); return 0
        if args.command == "refine": _json(refine_master(root, args.asset_id, instruction=args.instruction, endpoint=args.url)); return 0
        if args.command == "reference-edit":
            result = reference_edit_pilot(root, args.source_asset_id, instruction=args.instruction, endpoint=args.url, candidates=args.candidates, seed_base=args.seed_base, output_dir=args.output_dir)
            _json(result); return 0 if result.get("status") in {"VISUAL_REVIEW_REQUIRED", "REFERENCE_EDIT_FIDELITY_PASSED"} else 2
        if args.command == "background": _json(background_remove(root, args.image_or_asset_id, endpoint=args.url, output_dir=args.output_dir)); return 0
        if args.command == "candidates": _json(candidates_show(root, args.asset_id)); return 0
        if args.command == "visual": _json(visual_approve(root, args.asset_id, args.note)); return 0
        if args.command == "benchmark": _json(benchmark_quality_lanes(root, endpoint=args.url, prompt=args.prompt, profile=args.profile, seed=args.seed, width=args.width, height=args.height)); return 0
        if args.command == "asset":
            if args.asset_action == "verify-integrity":
                result = __import__("ugas.master_assets", fromlist=["verify_asset_integrity"]).verify_asset_integrity(root, args.asset_id); _json(result); return 0 if result.get("status") == "REVISION_INTEGRITY_PASSED" else 2
            _json(__import__("ugas.master_assets", fromlist=["asset_status"]).asset_status(root, args.asset_id)); return 0
    except Exception as exc:
        _json({"status": "error", "error_type": type(exc).__name__, "error": str(exc)})
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
