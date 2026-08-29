"""Real 2D master-sprite, reference-edit and transparency orchestration."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from .asset_registry import register
from .capabilities import probe_comfy_capability
from .comfyui_client import ComfyUIClient, ComfyUIError
from .image_utils import compose_sheet, crop_grid, inspect_png, sha256, write_metadata
from .jobs import new_job, persist, transition
from .master_assets import (
    MasterAssetError,
    approve_visual,
    candidate_metrics,
    compile_prompt,
    detect_halo,
    load_asset,
    make_master_spec,
    prompt_sha256,
    save_asset,
    write_json,
)
from .model_registry import load_model
from .profiles import load_profile
from .provenance import append_event
from .qa import validate_output
from .workflow_registry import bind_workflow, load_workflow, validate_api_workflow


class GenerationError(RuntimeError):
    pass


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _model_names(model: dict) -> dict[str, str]:
    names: dict[str, str] = {}
    for item in model.get("exact_files", []):
        relative = Path(item)
        if relative.parts and relative.parts[0] == "diffusion_models":
            names["__MODEL__"] = relative.name
        elif relative.parts and relative.parts[0] == "text_encoders":
            names["__CLIP__"] = relative.name
        elif relative.parts and relative.parts[0] == "vae":
            names["__VAE__"] = relative.name
        elif relative.parts and relative.parts[0] == "background_removal":
            names["__BG_MODEL__"] = relative.name
    return names


def _output_dir(repo_root: Path, output_dir: Path | None, default: str) -> Path:
    value = output_dir or (repo_root / "tmp" / default)
    value = value if value.is_absolute() else repo_root / value
    value.mkdir(parents=True, exist_ok=True)
    return value.resolve()


def inspect_png_bytes(data: bytes) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def _run_job(
    repo_root: Path,
    client: ComfyUIClient,
    workflow: dict,
    *,
    output_dir: Path,
    filename: str,
    profile: str,
    capability: str,
    workflow_id: str,
    model_id: str,
    prompt: str,
    seed: int,
    width: int,
    height: int,
    input_hashes: dict[str, str] | None = None,
) -> tuple[dict, list[dict[str, Any]]]:
    model = load_model(repo_root, model_id)
    workflow_record = load_workflow(repo_root, workflow_id)
    job = new_job(
        consumer_project_id=None,
        asset_request_id=f"request-{uuid.uuid4().hex}",
        profile=profile,
        provider="provider-comfyui",
        capability=capability,
        workflow={"id": workflow_id, "sha256": workflow_record["sha256"]},
        models=[{"id": model_id}],
        prompts={"positive": prompt, "negative": ""},
        seed=seed,
        dimensions={"width": width, "height": height},
        parameters={"endpoint": client.base_url},
        input_hashes=input_hashes,
    )
    validated = transition(job, "validated")
    persist(validated, output_dir)
    try:
        job = validated
        submitted = client.submit_workflow(workflow)
        job = transition(job, "queued")
        job = transition(job, "running")
        history = client.poll_history(submitted["prompt_id"])
        outputs = client.fetch_history_outputs(history)
        if not outputs:
            raise GenerationError("ComfyUI history contained no retrievable output")
        job = transition(job, "succeeded")
        job = transition(job, "postprocessed")
        job["output_hashes"] = {item.get("filename", str(index)): inspect_png_bytes(item["data"]) for index, item in enumerate(outputs) if item.get("data", b"").startswith(b"\x89PNG")}
        job = transition(job, "validated_output")
        job["provenance_event"] = {"event": "comfyui-job", "job_id": job["job_id"], "workflow": workflow_id, "model": model_id, "prompt": prompt, "seed": seed}
        job = transition(job, "registered")
        target_outputs: list[dict[str, Any]] = []
        for index, item in enumerate(outputs):
            target = output_dir / (filename if index == 0 else f"{Path(filename).stem}-{index}{Path(filename).suffix}")
            target.write_bytes(item["data"])
            target_outputs.append({**item, "path": str(target), "qa": validate_output(target, width=width, height=height)})
        job_path = persist(job, output_dir)
        return {"job": job, "job_path": str(job_path)}, target_outputs
    except (ComfyUIError, OSError, KeyError, GenerationError) as exc:
        job["error"] = str(exc)
        try:
            job = transition(job, "failed", error=str(exc))
        except Exception:
            job["state"] = "failed"
        persist(job, output_dir)
        raise GenerationError(str(exc)) from exc


def generate_image(
    repo_root: Path,
    *,
    endpoint: str,
    prompt: str,
    profile: str = "generic-2d",
    model_id: str = "flux2-klein-4b-nvfp4",
    workflow_id: str = "flux2-klein-4b-text-to-image",
    output_dir: Path | None = None,
    seed: int = 1,
    width: int = 256,
    height: int = 256,
    consumer_project_id: str | None = None,
    timeout: float = 30.0,
    requires_transparency: bool = False,
) -> dict:
    client = ComfyUIClient(endpoint, timeout=timeout)
    evidence = probe_comfy_capability(repo_root, client, model_id, workflow_id, capability="2d")
    if evidence["state"] not in {"ready", "verified"}:
        raise GenerationError(f"ComfyUI capability is not ready: {evidence.get('failure_reason')}")
    workflow_record = load_workflow(repo_root, workflow_id)
    model_record = load_model(repo_root, model_id)
    workflow = bind_workflow(workflow_record["api"], prompt=prompt, seed=seed, width=width, height=height, model_names=_model_names(model_record))
    destination = _output_dir(repo_root, output_dir, "generated")
    job, outputs = _run_job(repo_root, client, workflow, output_dir=destination, filename=f"{uuid.uuid4().hex}.png", profile=profile, capability="2d", workflow_id=workflow_id, model_id=model_id, prompt=prompt, seed=seed, width=width, height=height)
    target = Path(outputs[0]["path"])
    qa = validate_output(target, width=width, height=height, requires_transparency=requires_transparency)
    job_value = job["job"]
    job_value["validation"] = qa
    persist(job_value, destination)
    if qa["status"] != "TECHNICAL_VALID":
        raise GenerationError("technical output QA failed")
    event = {"event": "image-generated", "job_id": job_value["job_id"], "workflow": workflow_id, "model": model_id, "output": str(target), "sha256": qa["technical"]["sha256"]}
    append_event(repo_root / "tmp" / "provenance.jsonl", event)
    if consumer_project_id:
        consumer_registry = Path(consumer_project_id) / ".game-assets" / "asset-registry.json"
        if consumer_registry.parent.exists():
            register(consumer_registry, {"id": f"asset-{target.stem}", "status": "validated", "asset_type": "image", "dimension": "2d", "source_path": str(target), "sha256": qa["technical"]["sha256"], "manifest": str(target), "provenance": job_value["job_id"]})
    return {"status": job_value["state"], "job": job_value, "output": str(target), "qa": qa, "capability_evidence": evidence, "job_path": str(destination / f"{job_value['job_id']}.json")}


def _revision(asset_id: str, number: int, output: Path, qa: dict, *, derived_from: dict | None = None, transparency_status: str = "not-required", extra: dict | None = None) -> dict:
    technical_status = qa.get("status", "failed")
    state = "TECHNICAL_VALID" if technical_status == "TECHNICAL_VALID" else "GENERATED"
    if transparency_status == "TRANSPARENCY_VALID":
        state = "TRANSPARENCY_VALID"
    return {
        "schema_version": "0.4.0",
        "revision_id": f"revision-{uuid.uuid4().hex}",
        "asset_id": asset_id,
        "revision_number": number,
        "derived_from": derived_from,
        "output_path": str(output),
        "output_sha256": qa.get("technical", {}).get("sha256"),
        "technical_status": technical_status,
        "transparency_status": transparency_status,
        "state": "VISUAL_REVIEW_REQUIRED" if technical_status == "TECHNICAL_VALID" and transparency_status != "failed" else state,
        "visual_approval": {"status": "pending"},
        "production_ready": False,
        **(extra or {}),
    }


def _persist_asset(asset: dict, asset_dir: Path) -> Path:
    path = asset_dir / "asset.json"
    save_asset(path, asset)
    return path


def generate_master_sprite(
    repo_root: Path,
    *,
    endpoint: str,
    prompt: str,
    profile: str = "generic-2d",
    candidates: int = 4,
    seed: int = 1,
    width: int = 384,
    height: int = 384,
    output_dir: Path | None = None,
    transparent: bool = False,
) -> dict[str, Any]:
    profile_value = load_profile(repo_root, profile)
    spec = make_master_spec(prompt, profile=profile_value, profile_id=profile, candidates=candidates, seed=seed, width=width, height=height, requires_transparency=transparent)
    compiled = compile_prompt(spec.to_dict(), profile_value)
    asset_dir = _output_dir(repo_root, output_dir, "assets") / spec.asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    spec_path = asset_dir / "master-asset-spec.json"
    write_json(spec_path, spec.to_dict())
    (asset_dir / "compiled-prompt.txt").write_text(compiled + "\n", encoding="utf-8")
    candidate_dir = asset_dir / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    seen_phashes: set[str] = set()
    for index, candidate_seed in enumerate(spec.seeds):
        started = time.perf_counter()
        result = generate_image(repo_root, endpoint=endpoint, prompt=compiled, profile=profile, output_dir=candidate_dir, seed=candidate_seed, width=width, height=height)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        output = Path(result["output"])
        qa = validate_output(output, width=width, height=height)
        metrics = candidate_metrics(output, width=width, height=height, requires_transparency=False)
        output_hash = qa.get("technical", {}).get("sha256")
        duplicate = output_hash in seen_hashes or metrics["perceptual_hash"] in seen_phashes
        seen_hashes.add(output_hash)
        seen_phashes.add(metrics["perceptual_hash"])
        objective_score = sum(bool(value) for value in (qa["status"] == "TECHNICAL_VALID", not duplicate, metrics["edge_clipping_ok"], metrics["occupancy_ok"], metrics["centered_ok"], metrics["file_size_ok"]))
        entries.append({"candidate_id": f"candidate-{index + 1}", "seed": candidate_seed, "path": str(output), "sha256": output_hash, "qa": qa, "metrics": metrics, "duplicate": duplicate, "objective_score": objective_score, "visual_assessment": "pending", "runtime_ms": elapsed_ms})
    entries.sort(key=lambda item: (-item["objective_score"], item["seed"], item["sha256"] or ""))
    for rank, entry in enumerate(entries, 1):
        entry["technical_rank"] = rank
    best = entries[0] if entries else None
    sheet = compose_sheet([Path(entry["path"]) for entry in entries], asset_dir / "candidates-contact-sheet.png", min(4, max(1, len(entries))))
    spec_sha = hashlib.sha256(json.dumps(spec.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    candidate_set = {"schema_version": "0.4.0", "set_id": f"candidate-set-{uuid.uuid4().hex}", "asset_id": spec.asset_id, "spec_sha256": spec_sha, "compiled_prompt_sha256": prompt_sha256(compiled), "candidate_count": len(entries), "candidates": entries, "best_technical_candidate": best["candidate_id"] if best else None, "visual_approval": "pending", "contact_sheet": sheet}
    candidate_path = asset_dir / "candidate-set.json"
    write_json(candidate_path, candidate_set)
    if not best:
        raise GenerationError("candidate generation returned no candidates")
    best_output = Path(best["path"])
    asset = {"schema_version": "0.4.0", "asset_id": spec.asset_id, "id": spec.asset_id, "category": spec.category, "profile": profile, "created_at": _now(), "updated_at": _now(), "master_asset_spec": str(spec_path), "compiled_prompt": compiled, "candidate_set": str(candidate_path), "requires_transparency": transparent, "revisions": []}
    revision = _revision(spec.asset_id, 1, best_output, best["qa"], extra={"candidate_id": best["candidate_id"], "candidate_metrics": best["metrics"]})
    asset["revisions"].append(revision)
    asset["current_revision"] = revision
    asset_path = _persist_asset(asset, asset_dir)
    result: dict[str, Any] = {"status": "VISUAL_REVIEW_REQUIRED", "asset_id": spec.asset_id, "asset_path": str(asset_path), "spec_path": str(spec_path), "candidate_set": str(candidate_path), "contact_sheet": str(asset_dir / "candidates-contact-sheet.png"), "master_before_background_removal": str(best_output), "compiled_prompt": compiled, "candidates": entries, "visual_approval": "pending"}
    if transparent:
        result["background_removal"] = background_remove(repo_root, spec.asset_id, endpoint=endpoint, output_dir=asset_dir)
    return result


def background_remove(repo_root: Path, image_or_asset_id: str, *, endpoint: str, output_dir: Path | None = None) -> dict[str, Any]:
    asset_path: Path | None = None
    asset: dict | None = None
    try:
        asset_path, asset = load_asset(repo_root, image_or_asset_id)
        source = Path(asset["current_revision"]["output_path"])
    except MasterAssetError:
        source = Path(image_or_asset_id)
        if not source.is_file():
            raise GenerationError(f"image or asset not found: {image_or_asset_id}")
    if not source.is_file():
        raise GenerationError(f"source image not found: {source}")
    client = ComfyUIClient(endpoint, timeout=30.0)
    evidence = probe_comfy_capability(repo_root, client, "birefnet", "birefnet-background-removal", capability="background-removal")
    if evidence["state"] not in {"ready", "verified"}:
        raise GenerationError(f"BiRefNet capability gap: {evidence.get('failure_reason')}")
    upload = client.upload_image(source)
    filename = upload.get("name") or upload.get("filename")
    if not isinstance(filename, str) or not filename:
        raise GenerationError("/upload/image did not return an input filename")
    workflow_record = load_workflow(repo_root, "birefnet-background-removal")
    model = load_model(repo_root, "birefnet")
    workflow = bind_workflow(workflow_record["api"], prompt="", model_names=_model_names(model), image_filename=filename)
    graph_check = validate_api_workflow(workflow, node_info=client.node_info())
    if not graph_check["live_valid"]:
        raise GenerationError(f"BiRefNet native node validation failed: {graph_check['missing_nodes']}")
    source_info = inspect_png(source)
    destination_dir = _output_dir(repo_root, output_dir, "background-removal")
    started = time.perf_counter()
    job, outputs = _run_job(repo_root, client, workflow, output_dir=destination_dir, filename="birefnet-output.png", profile=(asset or {}).get("profile", "generic-2d"), capability="background-removal", workflow_id="birefnet-background-removal", model_id="birefnet", prompt="native BiRefNet background removal", seed=0, width=source_info["width"], height=source_info["height"], input_hashes={"reference_sha256": sha256(source)})
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    output_info = [(Path(item["path"]), inspect_png(Path(item["path"]))) for item in outputs]
    transparent_source = next((path for path, info in output_info if info["has_transparent_pixels"]), None)
    if transparent_source is None:
        raise GenerationError("BiRefNet native output did not contain transparent pixels")
    mask_source = next((path for path, _ in output_info if path != transparent_source), None)
    transparent_output = destination_dir / "master-transparent.png"
    if transparent_source != transparent_output:
        transparent_output.write_bytes(transparent_source.read_bytes())
    mask_output = destination_dir / "master-mask.png" if mask_source else None
    if mask_source and mask_output and mask_source != mask_output:
        mask_output.write_bytes(mask_source.read_bytes())
    qa = validate_output(transparent_output, width=source_info["width"], height=source_info["height"], requires_transparency=True)
    halo = detect_halo(transparent_output)
    if qa["status"] != "TECHNICAL_VALID":
        raise GenerationError("BiRefNet output failed real transparency QA")
    if asset is not None and asset_path is not None:
        asset["requires_transparency"] = True
        current = asset["current_revision"]
        revision = _revision(asset["asset_id"], len(asset.get("revisions", [])) + 1, transparent_output, qa, derived_from={"revision_id": current["revision_id"], "output_sha256": current["output_sha256"]}, transparency_status="TRANSPARENCY_VALID", extra={"background_removal": {"workflow_id": "birefnet-background-removal", "model_id": "birefnet", "source_sha256": sha256(source), "mask_path": str(mask_output) if mask_output else None, "halo": halo}})
        asset.setdefault("revisions", []).append(revision)
        asset["current_revision"] = revision
        asset["updated_at"] = _now()
        save_asset(asset_path, asset)
    evidence = {**evidence, "state": "verified", "asset_capabilities_qualified": ["background-removal", "transparent-sprite-master"], "smoke_test": {"status": "passed", "source_sha256": sha256(source), "output": inspect_png(transparent_output), "mask": inspect_png(mask_output) if mask_output else None, "halo": halo, "runtime_ms": elapsed_ms}}
    write_json(repo_root / "docs" / "evidence" / "birefnet.json", evidence)
    append_event(repo_root / "tmp" / "provenance.jsonl", {"event": "background-removed", "workflow": "birefnet-background-removal", "model": "birefnet", "source_sha256": sha256(source), "output_sha256": qa["technical"]["sha256"], "mask_path": str(mask_output) if mask_output else None})
    return {"status": "TRANSPARENCY_VALID", "output": str(transparent_output), "mask": str(mask_output) if mask_output else None, "qa": qa, "halo": halo, "capability_evidence": evidence}


def refine_master(repo_root: Path, asset_id: str, *, instruction: str, endpoint: str) -> dict[str, Any]:
    if not instruction.strip():
        raise GenerationError("refinement instruction cannot be empty")
    asset_path, asset = load_asset(repo_root, asset_id)
    current = asset.get("current_revision") or {}
    source = Path(current.get("output_path", ""))
    if not source.is_file():
        raise GenerationError(f"current master output is missing: {source}")
    client = ComfyUIClient(endpoint, timeout=30.0)
    evidence = probe_comfy_capability(repo_root, client, "flux2-klein-4b-nvfp4", "flux2-klein-4b-image-edit", capability="reference-edit")
    if evidence["state"] not in {"ready", "verified"}:
        raise GenerationError(f"reference-edit capability gap: {evidence.get('failure_reason')}")
    upload = client.upload_image(source)
    filename = upload.get("name") or upload.get("filename")
    if not isinstance(filename, str) or not filename:
        raise GenerationError("/upload/image did not return an input filename")
    model = load_model(repo_root, "flux2-klein-4b-nvfp4")
    workflow_record = load_workflow(repo_root, "flux2-klein-4b-image-edit")
    prompt = asset.get("compiled_prompt", "") + "\nREFINEMENT INSTRUCTION: " + instruction.strip()
    dimensions = inspect_png(source)
    seed = len(asset.get("revisions", [])) + 1
    workflow = bind_workflow(workflow_record["api"], prompt=prompt, negative_prompt="", seed=seed, width=dimensions["width"], height=dimensions["height"], model_names=_model_names(model), image_filename=filename)
    graph_check = validate_api_workflow(workflow, node_info=client.node_info())
    if not graph_check["live_valid"]:
        raise GenerationError(f"reference-edit native node validation failed: {graph_check['missing_nodes']}")
    revision_dir = asset_path.parent / "revisions"
    started = time.perf_counter()
    job, outputs = _run_job(repo_root, client, workflow, output_dir=revision_dir, filename=f"reference-edit-{len(asset.get('revisions', [])) + 1}.png", profile=asset.get("profile", "generic-2d"), capability="reference-edit", workflow_id="flux2-klein-4b-image-edit", model_id="flux2-klein-4b-nvfp4", prompt=prompt, seed=seed, width=dimensions["width"], height=dimensions["height"], input_hashes={"reference_sha256": sha256(source)})
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    output = Path(outputs[0]["path"])
    qa = validate_output(output, width=dimensions["width"], height=dimensions["height"], requires_transparency=False)
    if qa["status"] != "TECHNICAL_VALID":
        raise GenerationError("reference-edit output failed technical QA")
    reference_evidence = {**evidence, "state": "verified", "asset_capabilities_qualified": ["reference-edit"], "smoke_test": {"status": "passed", "source_sha256": sha256(source), "output": inspect_png(output), "instruction": instruction, "runtime_ms": elapsed_ms}}
    write_json(repo_root / "docs" / "evidence" / "reference-edit.json", reference_evidence)
    revision = _revision(asset["asset_id"], len(asset.get("revisions", [])) + 1, output, qa, derived_from={"revision_id": current["revision_id"], "output_sha256": current["output_sha256"]}, transparency_status="failed" if asset.get("requires_transparency") else "not-required", extra={"reference_sha256": sha256(source), "instruction": instruction, "workflow_id": "flux2-klein-4b-image-edit", "model_id": "flux2-klein-4b-nvfp4", "job_id": job["job"]["job_id"]})
    asset.setdefault("revisions", []).append(revision)
    asset["current_revision"] = revision
    asset["updated_at"] = _now()
    save_asset(asset_path, asset)
    append_event(repo_root / "tmp" / "provenance.jsonl", {"event": "reference-edit", "asset_id": asset["asset_id"], "derived_from": current["revision_id"], "reference_sha256": sha256(source), "output_sha256": qa["technical"]["sha256"], "workflow": "flux2-klein-4b-image-edit", "instruction": instruction})
    return {"status": revision["state"], "asset_id": asset["asset_id"], "asset_path": str(asset_path), "output": str(output), "reference_sha256": sha256(source), "qa": qa, "capability_evidence": reference_evidence}


def candidates_show(repo_root: Path, asset_id: str) -> dict[str, Any]:
    _, asset = load_asset(repo_root, asset_id)
    path = Path(asset["candidate_set"])
    return json.loads(path.read_text(encoding="utf-8"))


def sprite_pilot(repo_root: Path, **kwargs) -> dict:
    """Legacy master-only pilot; grid > 1 remains explicitly out of scope."""
    columns = int(kwargs.pop("columns", 1)); rows = int(kwargs.pop("rows", 1))
    if columns != 1 or rows != 1:
        raise GenerationError("sprite-grid workflow not qualified in v0.4.0")
    result = generate_image(repo_root, **kwargs)
    output = Path(result["output"]); destination = Path(kwargs.get("output_dir") or output.parent)
    frame_dir = destination / f"{output.stem}-frames"
    cropped = crop_grid(output, frame_dir / "frame.png", columns, rows, trim=False, pad=0)
    sheet_path = destination / f"{output.stem}-sheet.png"
    sheet = compose_sheet([Path(item["path"]) for item in cropped["frames"]], sheet_path, columns)
    metadata = {"schema_version": "0.4.0", "id": f"sprite-sheet-{output.stem}", "source": {"master": str(output), "master_sha256": inspect_png(output)["sha256"]}, "sheet": sheet, "grid": {"columns": columns, "rows": rows, "cell_width": cropped["frames"][0]["width"], "cell_height": cropped["frames"][0]["height"]}, "frames": cropped["frames"], "qa": {"technical_status": "TECHNICAL_VALID", "visual_review": "required", "production_ready": False}, "provenance_ref": result["job"]["job_id"]}
    metadata_path = destination / f"{output.stem}-sheet.json"; write_metadata(metadata_path, metadata)
    result["sprite_sheet"] = str(sheet_path); result["sprite_metadata"] = str(metadata_path)
    result["pipeline"] = "master-image -> explicit crop/normalize -> sheet metadata -> technical QA; visual review required"
    return result


def visual_approve(repo_root: Path, asset_id: str, note: str = "") -> dict[str, Any]:
    return approve_visual(repo_root, asset_id, note)
