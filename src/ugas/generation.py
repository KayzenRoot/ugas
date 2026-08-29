"""Real 2D generation orchestration over the ComfyUI HTTP API."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .asset_registry import register
from .capabilities import probe_comfy_capability
from .comfyui_client import ComfyUIClient, ComfyUIError
from .image_utils import compose_sheet, crop_grid, inspect_png, write_metadata
from .jobs import new_job, persist, transition
from .provenance import append_event
from .qa import validate_output
from .workflow_registry import bind_workflow, load_workflow
from .model_registry import load_model


class GenerationError(RuntimeError):
    pass


def generate_image(repo_root: Path, *, endpoint: str, prompt: str, profile: str = "generic-2d", model_id: str = "flux2-klein-4b-nvfp4", workflow_id: str = "flux2-klein-4b-text-to-image", output_dir: Path | None = None, seed: int = 1, width: int = 256, height: int = 256, consumer_project_id: str | None = None, timeout: float = 30.0, requires_transparency: bool = False) -> dict:
    client = ComfyUIClient(endpoint, timeout=timeout)
    evidence = probe_comfy_capability(repo_root, client, model_id, workflow_id)
    if evidence["state"] not in {"ready", "verified"}:
        raise GenerationError(f"ComfyUI capability is not ready: {evidence.get('failure_reason')}")
    workflow_record = load_workflow(repo_root, workflow_id)
    model_record = load_model(repo_root, model_id)
    names = {"__MODEL__": next((Path(item).name for item in model_record["exact_files"] if item.startswith("diffusion_models/")), ""), "__CLIP__": next((Path(item).name for item in model_record["exact_files"] if item.startswith("text_encoders/")), ""), "__VAE__": next((Path(item).name for item in model_record["exact_files"] if item.startswith("vae/")), "")}
    workflow = bind_workflow(workflow_record["api"], prompt=prompt, seed=seed, width=width, height=height, model_names=names)
    job = new_job(consumer_project_id=consumer_project_id, asset_request_id=f"request-{uuid.uuid4().hex}", profile=profile, provider="provider-comfyui", capability="2d", workflow={"id": workflow_id, "sha256": workflow_record["sha256"]}, models=[{"id": model_id}], prompts={"positive": prompt, "negative": ""}, seed=seed, dimensions={"width": width, "height": height}, parameters={"endpoint": endpoint, "requires_transparency": requires_transparency})
    jobs_dir = output_dir or (repo_root / "tmp" / "jobs")
    persist(transition(job, "validated"), jobs_dir)
    try:
        job = transition(job, "validated")
        submitted = client.submit_workflow(workflow)
        job = transition(job, "queued")
        job = transition(job, "running")
        history = client.poll_history(submitted["prompt_id"])
        output = client.fetch_history_outputs(history)
        if not output:
            raise GenerationError("ComfyUI history contained no retrievable output")
        output_dir = output_dir or (repo_root / "tmp" / "generated")
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{submitted['prompt_id']}.png"
        target.write_bytes(output[0]["data"])
        qa = validate_output(target, width=width, height=height, requires_transparency=requires_transparency)
        job = transition(job, "succeeded")
        job = transition(job, "postprocessed")
        job["output_hashes"] = {str(target): qa.get("technical", {}).get("sha256")}
        job["validation"] = qa
        job = transition(job, "validated_output") if qa["status"] == "TECHNICAL_VALID" else transition(job, "failed", error="technical output QA failed")
        if job["state"] == "validated_output":
            job["provenance_event"] = {"event": "image-generated", "job_id": job["job_id"], "workflow": workflow_id, "model": model_id, "output": str(target), "sha256": qa["technical"]["sha256"]}
            job = transition(job, "registered")
            append_event((repo_root / "tmp" / "provenance.jsonl"), job["provenance_event"])
            if consumer_project_id:
                consumer_registry = Path(consumer_project_id) / ".game-assets" / "asset-registry.json"
                if consumer_registry.parent.exists():
                    register(consumer_registry, {"id": f"asset-{submitted['prompt_id']}", "status": "validated", "asset_type": "image", "dimension": "2d", "source_path": str(target), "sha256": qa["technical"]["sha256"], "manifest": str(target), "provenance": job["job_id"]})
        job_path = persist(job, jobs_dir)
        return {"status": job["state"], "job": job, "output": str(target), "qa": qa, "capability_evidence": evidence, "job_path": str(job_path)}
    except (ComfyUIError, OSError, KeyError, GenerationError) as exc:
        job["error"] = str(exc)
        try:
            job = transition(job, "failed", error=str(exc))
        except Exception:
            job["state"] = "failed"
        persist(job, jobs_dir)
        raise GenerationError(str(exc)) from exc


def reference_edit(*args, **kwargs):
    raise GenerationError("reference-edit is not qualified in the v0.3.1 MVP")


def sprite_pilot(repo_root: Path, **kwargs) -> dict:
    """Generate only a 1x1 master pilot until a grid workflow is qualified."""
    columns = int(kwargs.pop("columns", 1)); rows = int(kwargs.pop("rows", 1))
    if columns != 1 or rows != 1:
        raise GenerationError("sprite-grid workflow not qualified in v0.3.1")
    result = generate_image(repo_root, **kwargs)
    output = Path(result["output"]); destination = Path(kwargs.get("output_dir") or output.parent)
    frame_dir = destination / f"{output.stem}-frames"
    cropped = crop_grid(output, frame_dir / "frame.png", columns, rows, trim=False, pad=0)
    sheet_path = destination / f"{output.stem}-sheet.png"
    sheet = compose_sheet([Path(item["path"]) for item in cropped["frames"]], sheet_path, columns)
    metadata = {"schema_version": "0.3.0", "id": f"sprite-sheet-{output.stem}", "source": {"master": str(output), "master_sha256": inspect_png(output)["sha256"]}, "sheet": sheet, "grid": {"columns": columns, "rows": rows, "cell_width": cropped["frames"][0]["width"], "cell_height": cropped["frames"][0]["height"]}, "frames": cropped["frames"], "qa": {"technical_status": "TECHNICAL_VALID", "visual_review": "required", "production_ready": False}, "provenance_ref": result["job"]["job_id"]}
    metadata_path = destination / f"{output.stem}-sheet.json"; write_metadata(metadata_path, metadata)
    result["sprite_sheet"] = str(sheet_path); result["sprite_metadata"] = str(metadata_path)
    result["pipeline"] = "master-image -> explicit crop/normalize -> sheet metadata -> technical QA; visual review required"
    return result
