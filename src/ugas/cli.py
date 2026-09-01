"""UGAS v0.8.0 machine-readable CLI."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

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
from .identity import ANCHOR_ASSET_ID
from .pose_guides import ensure_pose_guides, render_pose_guides
from .multiview import qualify_multiref, generate_directional_anchors, generate_walk_pilot, identity_inspect
from .openpose_guides import ensure_openpose_guides, render_openpose_evidence
from .pose_control import qualify_native_reference_order
from .refcontrol import qualify_refcontrol


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _json(value: object) -> None:
    import json
    print(json.dumps(value, indent=2, ensure_ascii=True, default=str))


def _json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def _run_cutout_rig_phase(root: Path, phase: str) -> dict[str, object]:
    """Run the isolated SAM2 adapter without importing its GPU stack here."""
    helper = root / "scripts" / "validation" / "run_cutout_rig_v071.py"
    local_appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    candidates = [
        os.environ.get("UGAS_SAM2_PYTHON"),
        str(local_appdata / "UGAS" / "comfyui" / ".venv" / "Scripts" / "python.exe"),
        sys.executable,
    ]
    selected = next((Path(value) for value in candidates if value and Path(value).is_file()), None)
    if selected is None:
        return {"status": "SAM2_RUNTIME_GAP", "reason": "no isolated SAM2 Python runtime was found"}
    environment = os.environ.copy()
    source_path = str(root / "src")
    environment["PYTHONPATH"] = source_path + os.pathsep + environment.get("PYTHONPATH", "")
    completed = subprocess.run(
        [str(selected), str(helper), "--phase", phase],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    output = completed.stdout.strip()
    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        result = {
            "status": "SAM2_RUNTIME_GAP" if phase == "sam2" else "CUTOUT_RIG_SEGMENTATION_RUNTIME_GAP",
            "reason": "isolated provider did not return JSON",
            "exit_code": completed.returncode,
            "stdout_tail": output[-1000:],
            "stderr_tail": completed.stderr[-1000:],
        }
    if isinstance(result, dict):
        result.setdefault("runtime_exit_code", completed.returncode)
        return result
    return {"status": "SAM2_RUNTIME_GAP", "reason": "isolated provider returned a non-object JSON value"}


def _common_generation(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--profile", default="generic-2d")
    parser.add_argument("--output-dir", type=Path)
    _json_flag(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ugas", description="Universal Game Asset Studio 0.8.0")
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
    identity = sub.add_parser("identity"); identity_sub = identity.add_subparsers(dest="identity_action", required=True); identity_inspect_parser = identity_sub.add_parser("inspect"); identity_inspect_parser.add_argument("asset_id", nargs="?", default=ANCHOR_ASSET_ID); identity_inspect_parser.add_argument("--output", type=Path); _json_flag(identity_inspect_parser)
    guides = sub.add_parser("pose-guides"); guides_sub = guides.add_subparsers(dest="guides_action", required=True); guide_validate = guides_sub.add_parser("validate"); _json_flag(guide_validate); guide_render = guides_sub.add_parser("render"); guide_render.add_argument("kind", choices=["views", "walk-front-8"]); _json_flag(guide_render)
    openpose = sub.add_parser("openpose"); openpose_sub = openpose.add_subparsers(dest="openpose_action", required=True); openpose_validate = openpose_sub.add_parser("validate"); _json_flag(openpose_validate); openpose_render = openpose_sub.add_parser("render"); openpose_render.add_argument("kind", choices=["challenge", "views", "walk-front-8"]); _json_flag(openpose_render)
    pose_control = sub.add_parser("pose-control"); pose_control_sub = pose_control.add_subparsers(dest="pose_control_action", required=True); pose_benchmark = pose_control_sub.add_parser("benchmark"); pose_benchmark.add_argument("--url", default="http://127.0.0.1:8188"); pose_benchmark.add_argument("--seed-base", type=int, default=52701); _json_flag(pose_benchmark); refcontrol_parser = pose_control_sub.add_parser("refcontrol"); refcontrol_parser.add_argument("--url", default="http://127.0.0.1:8188"); refcontrol_parser.add_argument("--model-root", type=Path); _json_flag(refcontrol_parser)
    multiref = sub.add_parser("multiref"); multiref_sub = multiref.add_subparsers(dest="multiref_action", required=True); multiref_qualify = multiref_sub.add_parser("qualify"); multiref_qualify.add_argument("--asset-id", default=ANCHOR_ASSET_ID); multiref_qualify.add_argument("--url", default="http://127.0.0.1:8188"); multiref_qualify.add_argument("--seed-base", type=int, default=50501); _json_flag(multiref_qualify)
    anchors = sub.add_parser("anchors"); anchors_sub = anchors.add_subparsers(dest="anchors_action", required=True); anchors_generate = anchors_sub.add_parser("generate"); anchors_generate.add_argument("asset_id", nargs="?", default=ANCHOR_ASSET_ID); anchors_generate.add_argument("--directions", nargs="+", default=["front", "left", "right", "back"]); anchors_generate.add_argument("--url", default="http://127.0.0.1:8188"); anchors_generate.add_argument("--seed-base", type=int, default=50601); _json_flag(anchors_generate); anchors_status = anchors_sub.add_parser("status"); anchors_status.add_argument("asset_id", nargs="?", default=ANCHOR_ASSET_ID); _json_flag(anchors_status)
    animation = sub.add_parser("animation"); animation_sub = animation.add_subparsers(dest="animation_action", required=True); animation_generate = animation_sub.add_parser("generate"); animation_generate.add_argument("asset_id", nargs="?", default=ANCHOR_ASSET_ID); animation_generate.add_argument("--animation", default="walk", choices=["walk"]); animation_generate.add_argument("--view", default="front", choices=["front"]); animation_generate.add_argument("--frames", type=int, default=8); animation_generate.add_argument("--url", default="http://127.0.0.1:8188"); animation_generate.add_argument("--seed-base", type=int, default=50701); _json_flag(animation_generate); animation_status = animation_sub.add_parser("status"); animation_status.add_argument("animation_id", nargs="?", default="walk-front-8"); _json_flag(animation_status); animation_preview = animation_sub.add_parser("preview"); animation_preview.add_argument("animation_id", nargs="?", default="walk-front-8"); _json_flag(animation_preview)
    cutout = sub.add_parser("cutout-rig"); cutout_sub = cutout.add_subparsers(dest="cutout_action", required=True)
    cutout_qualify = cutout_sub.add_parser("qualify-sam2"); _json_flag(cutout_qualify)
    cutout_build = cutout_sub.add_parser("build"); cutout_build.add_argument("--asset-id", required=True); _json_flag(cutout_build)
    cutout_pose = cutout_sub.add_parser("pose-pilot"); cutout_pose.add_argument("--poses", default="q0,q1,q2"); _json_flag(cutout_pose)
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
        if args.command == "identity":
            value = identity_inspect(root, args.asset_id)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(__import__("json").dumps(value["manifest"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); value["output"] = str(args.output)
            _json(value); return 0 if value.get("status") == "IDENTITY_MANIFEST_VALID" else 2
        if args.command == "pose-guides":
            value = ensure_pose_guides(root) if args.guides_action == "validate" else render_pose_guides(root, args.kind)
            _json(value); return 0 if value.get("status") in {"POSE_GUIDES_VALID", "POSE_GUIDES_RENDERED"} else 2
        if args.command == "openpose":
            value = ensure_openpose_guides(root) if args.openpose_action == "validate" else render_openpose_evidence(root) if args.kind == "challenge" else __import__("ugas.openpose_guides", fromlist=["render_openpose_guides"]).render_openpose_guides(root, args.kind)
            _json(value); return 0 if value.get("status") in {"OPENPOSE_GUIDES_VALID", "OPENPOSE_EVIDENCE_RENDERED", "OPENPOSE_GUIDES_RENDERED"} else 2
        if args.command == "pose-control":
            if args.pose_control_action == "benchmark":
                value = qualify_native_reference_order(root, endpoint=args.url, seed_base=args.seed_base); _json(value); return 0 if value.get("status") == "NATIVE_REFERENCE_ORDER_QUALIFIED" else 2
            value = qualify_refcontrol(root, endpoint=args.url, model_root=args.model_root); _json(value); return 0 if value.get("status") == "REFCONTROL_POSE_QUALIFIED" else 2
        if args.command == "multiref":
            value = qualify_multiref(root, endpoint=args.url, asset_id=args.asset_id, seed_base=args.seed_base); _json(value); return 0 if value.get("status") == "MULTI_REFERENCE_QUALIFIED" else 2
        if args.command == "anchors":
            if args.anchors_action == "status":
                path = root / "docs/evidence/directional-anchor-set.json"; value = __import__("json").loads(path.read_text(encoding="utf-8")) if path.is_file() else {"status": "NOT_RUN", "asset_id": args.asset_id}; _json(value); return 0 if value.get("status") == "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED" else 2
            value = generate_directional_anchors(root, args.asset_id, endpoint=args.url, directions=args.directions, seed_base=args.seed_base); _json(value); return 0 if value.get("status") == "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED" else 2
        if args.command == "animation":
            if args.animation_action == "status":
                path = root / "docs/evidence/walk-front-8.json"; value = __import__("json").loads(path.read_text(encoding="utf-8")) if path.is_file() else {"status": "NOT_RUN", "animation_id": args.animation_id}; _json(value); return 0 if value.get("status") == "WALK_CYCLE_VISUAL_REVIEW_REQUIRED" else 2
            if args.animation_action == "preview":
                path = root / "docs/evidence/walk-front-8-preview.gif"; value = {"status": "PREVIEW_READY" if path.is_file() else "NOT_AVAILABLE", "animation_id": args.animation_id, "preview": str(path)}; _json(value); return 0 if path.is_file() else 2
            value = generate_walk_pilot(root, args.asset_id, endpoint=args.url, frames=args.frames, seed_base=args.seed_base); _json(value); return 0 if value.get("status") == "WALK_CYCLE_VISUAL_REVIEW_REQUIRED" else 2
        if args.command == "cutout-rig":
            if args.cutout_action == "build" and args.asset_id != ANCHOR_ASSET_ID:
                value = {"status": "CUTOUT_RIG_SOURCE_SKELETON_GAP", "reason": "v0.7.3 is bound to canonical R4", "expected_asset_id": ANCHOR_ASSET_ID, "received_asset_id": args.asset_id}
            else:
                phase = "sam2" if args.cutout_action == "qualify-sam2" else "pose-pilot" if args.cutout_action == "pose-pilot" else "build"
                value = _run_cutout_rig_phase(root, phase)
                if args.cutout_action == "pose-pilot":
                    value["requested_poses"] = [item for item in args.poses.split(",") if item]
            _json(value)
            return 0 if value.get("status") in {"SAM2_RUNTIME_QUALIFIED", "CUTOUT_RIG_POSE_PROVIDER_QUALIFIED"} else 2
    except Exception as exc:
        _json({"status": "error", "error_type": type(exc).__name__, "error": str(exc)})
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
