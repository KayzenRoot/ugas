"""Real v0.4.2 2D generation, immutable revision orchestration and QA."""

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
from .constants import UGAS_VERSION
from .image_utils import compose_sheet, crop_grid, inspect_png, sha256, write_metadata
from .jobs import new_job, persist, transition
from .master_assets import (
    MasterAssetError,
    approve_visual,
    candidate_metrics,
    checkerboard_preview,
    compile_generation_prompt,
    compile_reference_edit_instruction,
    detect_halo,
    load_asset,
    make_master_spec,
    prompt_sha256,
    reference_edit_structural_qa,
    save_asset,
    write_json,
)
from .model_registry import load_model, verify_model_files
from .profiles import load_profile
from .provenance import append_event
from .qa import validate_output
from .workflow_registry import bind_workflow, load_workflow, validate_api_workflow


class GenerationError(RuntimeError):
    pass


FAST_MODEL = "flux2-klein-4b-distilled-nvfp4"
QUALITY_MODEL = "flux2-klein-4b-base-nvfp4"
FAST_TEXT = "flux2-klein-4b-distilled-text-to-image"
QUALITY_TEXT = "flux2-klein-base-4b-quality-text-to-image"
FAST_EDIT = "flux2-klein-4b-distilled-image-edit"
QUALITY_EDIT = "flux2-klein-base-4b-quality-image-edit"


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _model_root() -> Path:
    return Path.home() / "AppData" / "Local" / "UGAS" / "comfyui" / "models"


def _model_names(model: dict) -> dict[str, str]:
    names: dict[str, str] = {}
    for item in model.get("exact_files", []):
        relative = Path(item)
        if relative.parts and relative.parts[0] == "diffusion_models": names["__MODEL__"] = relative.name
        elif relative.parts and relative.parts[0] == "text_encoders": names["__CLIP__"] = relative.name
        elif relative.parts and relative.parts[0] == "vae": names["__VAE__"] = relative.name
        elif relative.parts and relative.parts[0] == "background_removal": names["__BG_MODEL__"] = relative.name
    return names


def _output_dir(repo_root: Path, output_dir: Path | None, default: str) -> Path:
    value = output_dir or (repo_root / "tmp" / default)
    value = value if value.is_absolute() else repo_root / value
    value.mkdir(parents=True, exist_ok=True)
    return value.resolve()


def _unique_job_dir(repo_root: Path, output_dir: Path | None, default: str) -> Path:
    """Return a unique job directory for every standalone or staged operation."""
    base = _output_dir(repo_root, output_dir, default)
    destination = base / f"job-{uuid.uuid4().hex}"
    destination.mkdir(parents=True, exist_ok=False)
    return destination.resolve()


def inspect_png_bytes(data: bytes) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def _run_job(repo_root: Path, client: ComfyUIClient, workflow: dict, *, output_dir: Path, filename: str, profile: str,
             capability: str, workflow_id: str, model_id: str, prompt: str, seed: int, width: int, height: int,
             input_hashes: dict[str, str] | None = None) -> tuple[dict, list[dict[str, Any]]]:
    model = load_model(repo_root, model_id)
    workflow_record = load_workflow(repo_root, workflow_id)
    from .model_registry import validate_model_workflow_compatibility
    compatibility = validate_model_workflow_compatibility(model, workflow_record)
    job = new_job(consumer_project_id=None, asset_request_id=f"request-{uuid.uuid4().hex}", profile=profile,
        provider="provider-comfyui", capability=capability, workflow={"id": workflow_id, "sha256": workflow_record["sha256"]},
        models=[{"id": model_id, "family": model.get("family"), "variant": model.get("variant")}],
        prompts={"positive": prompt, "negative": ""}, seed=seed, dimensions={"width": width, "height": height},
        parameters={"endpoint": client.base_url, "model_variant": model.get("variant"), "workflow_parameters": workflow_record.get("parameters", {}), "compatibility": compatibility}, input_hashes=input_hashes)
    validated = transition(job, "validated"); persist(validated, output_dir)
    try:
        job = validated; submitted = client.submit_workflow(workflow); job = transition(job, "queued"); job = transition(job, "running")
        history = client.poll_history(submitted["prompt_id"]); outputs = client.fetch_history_outputs(history)
        if not outputs: raise GenerationError("ComfyUI history contained no retrievable output")
        job = transition(job, "succeeded"); job = transition(job, "postprocessed")
        job["output_hashes"] = {item.get("filename", str(index)): inspect_png_bytes(item["data"]) for index, item in enumerate(outputs) if item.get("data", b"").startswith(b"\x89PNG")}
        job = transition(job, "validated_output"); job["provenance_event"] = {"event": "comfyui-job", "job_id": job["job_id"], "workflow": workflow_id, "model": model_id, "prompt": prompt, "seed": seed}; job = transition(job, "registered")
        target_outputs: list[dict[str, Any]] = []
        for index, item in enumerate(outputs):
            target = output_dir / (filename if index == 0 else f"{Path(filename).stem}-{index}{Path(filename).suffix}")
            target.write_bytes(item["data"]); target_outputs.append({**item, "path": str(target), "qa": validate_output(target, width=width, height=height)})
        job_path = persist(job, output_dir)
        return {"job": job, "job_path": str(job_path)}, target_outputs
    except (ComfyUIError, OSError, KeyError, GenerationError) as exc:
        job["error"] = str(exc)
        try: job = transition(job, "failed", error=str(exc))
        except Exception: job["state"] = "failed"
        persist(job, output_dir); raise GenerationError(str(exc)) from exc


def generate_image(repo_root: Path, *, endpoint: str, prompt: str, profile: str = "generic-2d",
                   model_id: str = FAST_MODEL, workflow_id: str = FAST_TEXT, output_dir: Path | None = None,
                   seed: int = 1, width: int = 256, height: int = 256, consumer_project_id: str | None = None,
                   timeout: float = 30.0, requires_transparency: bool = False, allow_unqualified: bool = False) -> dict:
    client = ComfyUIClient(endpoint, timeout=timeout)
    evidence = probe_comfy_capability(repo_root, client, model_id, workflow_id, capability="2d")
    if evidence["state"] not in {"ready", "verified"} and not allow_unqualified:
        raise GenerationError(f"ComfyUI capability is not ready: {evidence.get('failure_reason')}")
    workflow_record = load_workflow(repo_root, workflow_id); model_record = load_model(repo_root, model_id)
    workflow = bind_workflow(workflow_record["api"], prompt=prompt, seed=seed, width=width, height=height, model_names=_model_names(model_record))
    graph_check = validate_api_workflow(workflow, node_info=client.node_info())
    if not graph_check["live_valid"]: raise GenerationError(f"workflow native node validation failed: {graph_check['missing_nodes']}")
    destination = _unique_job_dir(repo_root, output_dir, "generated")
    job, outputs = _run_job(repo_root, client, workflow, output_dir=destination, filename="output.png", profile=profile, capability="2d", workflow_id=workflow_id, model_id=model_id, prompt=prompt, seed=seed, width=width, height=height)
    target = Path(outputs[0]["path"]); qa = validate_output(target, width=width, height=height, requires_transparency=requires_transparency); job_value = job["job"]; job_value["validation"] = qa; persist(job_value, destination)
    if qa["status"] != "TECHNICAL_VALID": raise GenerationError("technical output QA failed")
    event = {"event": "image-generated", "job_id": job_value["job_id"], "workflow": workflow_id, "model": model_id, "output": str(target), "sha256": qa["technical"]["sha256"]}; append_event(repo_root / "tmp" / "provenance.jsonl", event)
    if consumer_project_id:
        consumer_registry = Path(consumer_project_id) / ".game-assets" / "asset-registry.json"
        if consumer_registry.parent.exists(): register(consumer_registry, {"id": f"asset-{target.stem}", "status": "validated", "asset_type": "image", "dimension": "2d", "source_path": str(target), "sha256": qa["technical"]["sha256"], "manifest": str(target), "provenance": job_value["job_id"]})
    return {"status": job_value["state"], "job": job_value, "output": str(target), "qa": qa, "capability_evidence": evidence, "job_path": str(destination / f"{job_value['job_id']}.json")}


def _revision(asset_id: str, number: int, output: Path, qa: dict, *, derived_from: dict | None = None,
              transparency_status: str = "not-required", revision_id: str | None = None,
              metadata_path: Path | None = None, extra: dict | None = None) -> dict:
    technical_status = qa.get("status", "failed"); state = "TECHNICAL_VALID" if technical_status == "TECHNICAL_VALID" else "GENERATED"
    if transparency_status == "TRANSPARENCY_VALID": state = "TRANSPARENCY_VALID"
    return {"schema_version": UGAS_VERSION, "revision_id": revision_id or f"revision-{uuid.uuid4().hex}", "asset_id": asset_id, "revision_number": number, "derived_from": derived_from, "output_path": str(output), "output_sha256": qa.get("technical", {}).get("sha256"), "technical_status": technical_status, "transparency_status": transparency_status, "state": "VISUAL_REVIEW_REQUIRED" if technical_status == "TECHNICAL_VALID" and transparency_status != "failed" else state, "visual_approval": {"status": "pending"}, "production_ready": False, **({"metadata_path": str(metadata_path)} if metadata_path else {}), **(extra or {})}


def _persist_asset(asset: dict, asset_dir: Path) -> Path:
    path = asset_dir / "asset.json"; save_asset(path, asset); return path


def _join_original_rgb_with_alpha(source: Path, alpha_source: Path, destination: Path) -> dict[str, Any]:
    """Use the original RGB source and only the native foreground alpha/matte."""
    from PIL import Image
    with Image.open(source) as opened_source, Image.open(alpha_source) as opened_alpha:
        rgb = opened_source.convert("RGB")
        alpha = opened_alpha.convert("RGBA").getchannel("A")
        if alpha.getextrema() == (255, 255):
            # Some ComfyUI builds expose the matte as luminance without an
            # alpha channel. In that case the mask is the foreground matte.
            alpha = opened_alpha.convert("L")
        if alpha.size != rgb.size:
            raise GenerationError("BiRefNet matte dimensions do not match source RGB")
        joined = Image.merge("RGBA", (*rgb.split(), alpha))
        destination.parent.mkdir(parents=True, exist_ok=True)
        joined.save(destination, format="PNG", optimize=False)
    return inspect_png(destination)


def _create_revision(
    asset_dir: Path,
    asset_id: str,
    number: int,
    source: Path,
    qa: dict,
    *,
    derived_from: dict | None = None,
    transparency_status: str = "not-required",
    mask_source: Path | None = None,
    extra: dict | None = None,
) -> dict:
    """Persist a revision under a new ID-owned directory and record metadata."""
    revision_id = f"revision-{uuid.uuid4().hex}"
    revision_dir = asset_dir / "revisions" / revision_id
    revision_dir.mkdir(parents=True, exist_ok=False)
    output = revision_dir / "output.png"
    output.write_bytes(source.read_bytes())
    if mask_source is not None:
        (revision_dir / "mask.png").write_bytes(mask_source.read_bytes())
    checkerboard = revision_dir / "checkerboard.png"
    metadata_path = revision_dir / "metadata.json"
    final_qa = validate_output(
        output,
        width=qa.get("technical", {}).get("width"),
        height=qa.get("technical", {}).get("height"),
        requires_transparency=transparency_status == "TRANSPARENCY_VALID",
        rgb_source=Path(str((extra or {}).get("rgb_source"))) if (extra or {}).get("rgb_source") else None,
    )
    revision = _revision(
        asset_id,
        number,
        output,
        final_qa,
        derived_from=derived_from,
        transparency_status=transparency_status,
        revision_id=revision_id,
        metadata_path=metadata_path,
        extra={key: value for key, value in (extra or {}).items() if key != "rgb_source"},
    )
    checkerboard_preview(output, checkerboard)
    revision["checkerboard_path"] = str(checkerboard)
    write_json(metadata_path, revision)
    return revision


def _lane(policy: str, *, base_available: bool = True) -> tuple[str, str, str, str | None]:
    normalized = policy.casefold()
    if normalized not in {"quality-first", "balanced", "fast"}: raise GenerationError("quality policy must be quality-first, balanced or fast")
    if normalized == "fast": return FAST_MODEL, FAST_TEXT, "fast", None
    if normalized == "balanced": return (QUALITY_MODEL, QUALITY_TEXT, "quality", None) if base_available else (FAST_MODEL, FAST_TEXT, "fast", "QUALITY_UNAVAILABLE: balanced fell back to FAST")
    return (QUALITY_MODEL, QUALITY_TEXT, "quality", None) if base_available else (FAST_MODEL, FAST_TEXT, "fast", "QUALITY_UNAVAILABLE: quality-first fell back to FAST")


def _candidate_score(entry: dict[str, Any]) -> float:
    metrics = entry["metrics"]
    occupancy = metrics.get("occupancy", 0.0); target = metrics.get("occupancy_target", {"min": .2, "max": .82}); midpoint = (target["min"] + target["max"]) / 2
    return (1.0 - abs(occupancy - midpoint)) + (1.0 - metrics.get("center_offset", {}).get("x", 1.0)) + (1.0 - metrics.get("center_offset", {}).get("y", 1.0))


def generate_master_sprite(repo_root: Path, *, endpoint: str, prompt: str, profile: str = "generic-2d", candidates: int = 4,
                           seed: int = 1, width: int = 512, height: int = 512, output_dir: Path | None = None,
                           transparent: bool = False, quality_policy: str = "quality-first", model_id: str | None = None,
                           workflow_id: str | None = None) -> dict[str, Any]:
    profile_value = load_profile(repo_root, profile); spec = make_master_spec(prompt, profile=profile_value, profile_id=profile, candidates=candidates, seed=seed, width=width, height=height, requires_transparency=transparent)
    base_record = load_model(repo_root, QUALITY_MODEL); base_files = verify_model_files(base_record, _model_root()); base_available = base_files["hashes_verified"]
    selected_model, selected_workflow, lane, fallback_reason = _lane(quality_policy, base_available=base_available)
    if model_id: selected_model = model_id
    if workflow_id: selected_workflow = workflow_id
    compiled = compile_generation_prompt(spec.to_dict(), profile_value); asset_dir = _output_dir(repo_root, output_dir, "assets") / spec.asset_id; asset_dir.mkdir(parents=True, exist_ok=True)
    spec_path = asset_dir / "master-asset-spec.json"; write_json(spec_path, spec.to_dict()); (asset_dir / "compiled-prompt.txt").write_text(compiled + "\n", encoding="utf-8")
    candidate_dir = asset_dir / "candidates"; candidate_dir.mkdir(parents=True, exist_ok=True); entries: list[dict[str, Any]] = []; seen_hashes: set[str] = set(); seen_phashes: set[str] = set(); retry_log = []
    max_rounds = int(spec.generation_policy.get("max_auto_retry_rounds", 2))
    for round_index in range(max_rounds + 1):
        round_prompt = compiled if round_index == 0 else compile_generation_prompt(spec.to_dict(), profile_value, retry_reason=retry_log[-1]["reason"])
        for index in range(spec.candidate_count):
            candidate_seed = spec.seeds[index] + round_index * 1000; started = time.perf_counter()
            try:
                result = generate_image(repo_root, endpoint=endpoint, prompt=round_prompt, profile=profile, model_id=selected_model, workflow_id=selected_workflow, output_dir=candidate_dir, seed=candidate_seed, width=width, height=height, allow_unqualified=True)
                output = Path(result["output"]); elapsed_ms = round((time.perf_counter() - started) * 1000); qa = validate_output(output, width=width, height=height); output_hash = qa.get("technical", {}).get("sha256"); metrics = candidate_metrics(output, width=width, height=height, requires_transparency=False, occupancy_target=spec.subject_occupancy_target, margins=spec.margins, duplicate=output_hash in seen_hashes)
                duplicate = output_hash in seen_hashes or metrics.get("perceptual_hash") in seen_phashes; metrics = candidate_metrics(output, width=width, height=height, requires_transparency=False, occupancy_target=spec.subject_occupancy_target, margins=spec.margins, duplicate=duplicate); seen_hashes.add(output_hash); seen_phashes.add(metrics.get("perceptual_hash"))
                entries.append({"candidate_id": f"candidate-{len(entries) + 1}", "round": round_index, "seed": candidate_seed, "path": str(output), "sha256": output_hash, "qa": qa, "metrics": metrics, "duplicate": duplicate, "objective_score": _candidate_score({"metrics": metrics}) if metrics.get("eligible") else 0.0, "eligible": metrics.get("eligible", False), "visual_assessment": "pending", "runtime_ms": elapsed_ms, "model_id": selected_model, "workflow_id": selected_workflow, "lane": lane})
            except GenerationError as exc:
                entries.append({"candidate_id": f"candidate-{len(entries) + 1}", "round": round_index, "seed": candidate_seed, "error": str(exc), "eligible": False, "metrics": {"eligible": False, "hard_gate_failures": ["generation_failed"]}, "visual_assessment": "pending", "model_id": selected_model, "workflow_id": selected_workflow, "lane": lane})
        if any(item.get("eligible") for item in entries): break
        failures = sorted({failure for item in entries if item.get("round") == round_index for failure in item.get("metrics", {}).get("hard_gate_failures", [])})
        reason = "hard gates rejected candidates: " + ", ".join(failures or ["generation failure"])
        if "safe_margin" in failures:
            reason += "; reduce subject scale and increase empty border"
        retry_log.append({"round": round_index, "reason": reason, "prompt_sha256": prompt_sha256(round_prompt)})
    eligible = [item for item in entries if item.get("eligible")]; eligible.sort(key=lambda item: (-item["objective_score"], item["seed"], item.get("sha256") or ""))
    for rank, entry in enumerate(eligible, 1): entry["technical_rank"] = rank
    best = eligible[0] if eligible else None; sheet = compose_sheet([Path(entry["path"]) for entry in entries if entry.get("path")], asset_dir / "candidates-contact-sheet.png", min(4, max(1, len(entries)))) if entries else None
    spec_sha = hashlib.sha256(json.dumps(spec.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    candidate_set = {"schema_version": UGAS_VERSION, "pilot_id": f"v{UGAS_VERSION}-{spec.asset_id}", "set_id": f"candidate-set-{uuid.uuid4().hex}", "asset_id": spec.asset_id, "spec_sha256": spec_sha, "compiled_prompt_sha256": prompt_sha256(compiled), "candidate_count": len(entries), "candidates": entries, "eligible_candidate_count": len(eligible), "best_technical_candidate": best["candidate_id"] if best else None, "selection_status": "eligible" if best else "NO_ACCEPTABLE_CANDIDATE", "retry_log": retry_log, "lane": lane, "model_id": selected_model, "workflow_id": selected_workflow, "fallback_reason": fallback_reason, "visual_approval": "pending", "contact_sheet": sheet}
    candidate_path = asset_dir / "candidate-set.json"; write_json(candidate_path, candidate_set)
    if not best: raise GenerationError("NO_ACCEPTABLE_CANDIDATE: hard gates rejected every candidate after 2 retry rounds")
    best_output = Path(best["path"]); asset = {"schema_version": UGAS_VERSION, "asset_id": spec.asset_id, "id": spec.asset_id, "category": spec.category, "profile": profile, "created_at": _now(), "updated_at": _now(), "master_asset_spec": str(spec_path), "compiled_prompt": compiled, "compiled_prompt_sha256": prompt_sha256(compiled), "candidate_set": str(candidate_path), "requires_transparency": transparent, "generation": {"quality_policy": quality_policy, "lane": lane, "model_id": selected_model, "workflow_id": selected_workflow, "fallback_reason": fallback_reason}, "revisions": []}
    revision = _create_revision(asset_dir, spec.asset_id, 1, best_output, best["qa"], extra={"candidate_id": best["candidate_id"], "candidate_metrics": best["metrics"], "model_id": selected_model, "workflow_id": selected_workflow})
    asset["revisions"].append(revision); asset["current_revision"] = revision; asset_path = _persist_asset(asset, asset_dir)
    result: dict[str, Any] = {"status": "VISUAL_REVIEW_REQUIRED", "asset_id": spec.asset_id, "asset_path": str(asset_path), "spec_path": str(spec_path), "candidate_set": str(candidate_path), "contact_sheet": str(asset_dir / "candidates-contact-sheet.png"), "master_before_background_removal": str(revision["output_path"]), "compiled_prompt": compiled, "candidates": entries, "lane": lane, "model_id": selected_model, "workflow_id": selected_workflow, "fallback_reason": fallback_reason, "visual_approval": "pending", "revision_id": revision["revision_id"]}
    if transparent: result["background_removal"] = background_remove(repo_root, spec.asset_id, endpoint=endpoint, output_dir=asset_dir)
    return result


def benchmark_quality_lanes(repo_root: Path, *, endpoint: str, prompt: str, profile: str = "generic-2d", seed: int = 4301, width: int = 512, height: int = 512, output_dir: Path | None = None) -> dict[str, Any]:
    """Run shared seeds through FAST and QUALITY; qualification remains evidence-derived."""
    profile_value = load_profile(repo_root, profile); spec = make_master_spec(prompt, profile=profile_value, profile_id=profile, candidates=3, seed=seed, width=width, height=height)
    compiled = compile_generation_prompt(spec.to_dict(), profile_value); destination = _output_dir(repo_root, output_dir, "quality-benchmark"); entries: list[dict[str, Any]] = []
    for lane_name, model_id, workflow_id in (("FAST", FAST_MODEL, FAST_TEXT), ("QUALITY", QUALITY_MODEL, QUALITY_TEXT)):
        for offset in range(3):
            candidate_seed = seed + offset; started = time.perf_counter()
            try:
                result = generate_image(repo_root, endpoint=endpoint, prompt=compiled, profile=profile, model_id=model_id, workflow_id=workflow_id, output_dir=destination / lane_name.casefold(), seed=candidate_seed, width=width, height=height, allow_unqualified=True)
                output = Path(result["output"]); qa = validate_output(output, width=width, height=height); metrics = candidate_metrics(output, width=width, height=height, occupancy_target=spec.subject_occupancy_target, margins=spec.margins); entries.append({"lane": lane_name, "model_id": model_id, "workflow_id": workflow_id, "seed": candidate_seed, "path": str(output), "sha256": qa.get("technical", {}).get("sha256"), "steps": 4 if lane_name == "FAST" else 50, "guidance": 1.0 if lane_name == "FAST" else 4.0, "runtime_ms": round((time.perf_counter() - started) * 1000), "dimensions": {"width": width, "height": height}, "hard_gates": metrics.get("hard_gates", {}), "eligible": metrics.get("eligible", False), "qa": qa, "safe_margin_ok": metrics.get("safe_margin_ok"), "safe_margin_violations": metrics.get("safe_margin_violations", [])})
            except GenerationError as exc:
                entries.append({"lane": lane_name, "model_id": model_id, "workflow_id": workflow_id, "seed": candidate_seed, "steps": 4 if lane_name == "FAST" else 50, "guidance": 1.0 if lane_name == "FAST" else 4.0, "dimensions": {"width": width, "height": height}, "eligible": False, "status": "unavailable_on_this_hardware" if lane_name == "QUALITY" else "failed", "error": str(exc)})
    image_paths = [Path(item["path"]) for item in entries if item.get("path")]
    contact = compose_sheet(image_paths, destination / "quality-benchmark-contact-sheet.png", 3) if image_paths else None
    evidence = {"schema_version": UGAS_VERSION, "benchmark_id": f"quality-benchmark-{uuid.uuid4().hex}", "spec": spec.to_dict(), "compiled_prompt": compiled, "shared_seeds": [seed, seed + 1, seed + 2], "resolution": {"width": width, "height": height}, "lanes": {"FAST": {"model_id": FAST_MODEL, "workflow_id": FAST_TEXT, "steps": 4, "guidance": 1.0}, "QUALITY": {"model_id": QUALITY_MODEL, "workflow_id": QUALITY_TEXT, "steps": 50, "guidance": 4.0}}, "results": entries, "contact_sheet": str(contact["path"]) if contact else None, "visual_winner": None, "visual_review": "required"}
    write_json(repo_root / "docs" / "evidence" / "quality-benchmark.json", evidence)
    if contact: Path(repo_root / "docs" / "evidence" / "quality-benchmark-contact-sheet.png").write_bytes(Path(contact["path"]).read_bytes())
    return evidence


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
    staging_dir = _unique_job_dir(repo_root, (asset_path.parent / "jobs") if asset_path else output_dir, "background-removal")
    started = time.perf_counter()
    job, outputs = _run_job(
        repo_root,
        client,
        workflow,
        output_dir=staging_dir,
        filename="birefnet-output.png",
        profile=(asset or {}).get("profile", "generic-2d"),
        capability="background-removal",
        workflow_id="birefnet-background-removal",
        model_id="birefnet",
        prompt="native BiRefNet background removal",
        seed=0,
        width=source_info["width"],
        height=source_info["height"],
        input_hashes={"reference_sha256": sha256(source)},
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    output_info = [(Path(item["path"]), inspect_png(Path(item["path"]))) for item in outputs]
    transparent_source = next((path for path, info in output_info if info["has_transparent_pixels"]), None)
    if transparent_source is None:
        raise GenerationError("BiRefNet native output did not contain transparent pixels")
    mask_source = next((path for path, _ in output_info if path != transparent_source), None)
    joined_source = staging_dir / "joined-rgb-alpha.png"
    _join_original_rgb_with_alpha(source, transparent_source, joined_source)
    joined_qa = validate_output(joined_source, width=source_info["width"], height=source_info["height"], requires_transparency=True, rgb_source=source)
    halo = detect_halo(joined_source)
    if joined_qa["status"] != "TECHNICAL_VALID":
        raise GenerationError("BiRefNet output failed transparency or RGB-preservation QA")
    structural = None
    transparency_evidence_name = "transparency-qa-master.json"
    if asset is not None and asset_path is not None:
        asset["requires_transparency"] = True
        current = asset["current_revision"]
        previous_revisions = asset.get("revisions", [])
        derived_from = {"revision_id": current["revision_id"], "output_sha256": current["output_sha256"]}
        revision = _create_revision(
            asset_path.parent,
            asset["asset_id"],
            len(previous_revisions) + 1,
            joined_source,
            joined_qa,
            derived_from=derived_from,
            transparency_status="TRANSPARENCY_VALID",
            mask_source=mask_source,
            extra={
                "background_removal": {
                    "workflow_id": "birefnet-background-removal",
                    "model_id": "birefnet",
                    "source_sha256": sha256(source),
                    "halo": halo,
                },
                "rgb_source": str(source),
            },
        )
        revision_dir = Path(revision["output_path"]).parent
        revision["background_removal"]["mask_path"] = str(revision_dir / "mask.png") if mask_source else None
        is_reference_edit = current.get("workflow_id") in {QUALITY_EDIT, FAST_EDIT}
        if is_reference_edit:
            transparency_evidence_name = "transparency-qa-reference-edit.json"
            source_revision_id = (current.get("derived_from") or {}).get("revision_id")
            source_revision = next((item for item in previous_revisions if item.get("revision_id") == source_revision_id), None)
            if source_revision:
                thresholds = json.loads(Path(asset["master_asset_spec"]).read_text(encoding="utf-8")).get("generation_policy", {}).get("reference_edit_qa", {})
                structural = reference_edit_structural_qa(
                    Path(source_revision["output_path"]),
                    Path(revision["output_path"]),
                    thresholds=thresholds,
                    source_revision_id=source_revision.get("revision_id"),
                    output_revision_id=revision.get("revision_id"),
                    source_expected_sha256=source_revision.get("output_sha256"),
                    output_expected_sha256=revision.get("output_sha256"),
                )
                revision["reference_edit_qa"] = structural
                write_json(repo_root / "docs" / "evidence" / "reference-edit-qa.json", structural)
        write_json(revision["metadata_path"] and Path(revision["metadata_path"]), revision)
        asset.setdefault("revisions", []).append(revision)
        asset["current_revision"] = revision
        asset["updated_at"] = _now()
        save_asset(asset_path, asset)
        transparent_output = Path(revision["output_path"])
        checker = Path(revision["checkerboard_path"])
        mask_output = revision_dir / "mask.png" if mask_source else None
        integrity = __import__("ugas.master_assets", fromlist=["verify_asset_integrity"]).verify_asset_integrity(repo_root, str(asset_path))
        if integrity["status"] != "REVISION_INTEGRITY_PASSED":
            raise GenerationError("new asset revision failed integrity audit")
    else:
        transparent_output = staging_dir / "output.png"
        transparent_output.write_bytes(joined_source.read_bytes())
        mask_output = staging_dir / "mask.png" if mask_source else None
        if mask_output:
            mask_output.write_bytes(mask_source.read_bytes())
        checker = staging_dir / "checkerboard.png"
        checkerboard_preview(transparent_output, checker)
        integrity = None
    qa = validate_output(transparent_output, width=source_info["width"], height=source_info["height"], requires_transparency=True, rgb_source=source)
    transparency_evidence = {
        "schema_version": UGAS_VERSION,
        "asset_id": asset.get("asset_id") if asset else None,
        "revision_id": asset.get("current_revision", {}).get("revision_id") if asset else None,
        "source_sha256": sha256(source),
        "output_sha256": sha256(transparent_output),
        "source_path": str(source),
        "output_path": str(transparent_output),
        "qa": qa,
        "alpha_metrics": qa.get("alpha_metrics", {}),
        "rgb_preservation": qa.get("rgb_preservation", {}),
        "halo": halo,
        "status": "passed" if qa["status"] == "TECHNICAL_VALID" else "failed",
    }
    write_json(repo_root / "docs" / "evidence" / transparency_evidence_name, transparency_evidence)
    evidence = {**evidence, "schema_version": UGAS_VERSION, "state": "verified", "asset_capabilities_qualified": ["background-removal", "transparent-sprite-master"], "smoke_test": {"status": "passed", "source_sha256": sha256(source), "output": inspect_png(transparent_output), "mask": inspect_png(mask_output) if mask_output else None, "alpha_metrics": inspect_png(transparent_output).get("alpha_metrics"), "rgb_preservation": qa.get("rgb_preservation"), "halo": halo, "runtime_ms": elapsed_ms, "revision_id": transparency_evidence["revision_id"]}}
    write_json(repo_root / "docs" / "evidence" / "birefnet.json", evidence)
    append_event(repo_root / "tmp" / "provenance.jsonl", {"event": "background-removed", "workflow": "birefnet-background-removal", "model": "birefnet", "source_sha256": sha256(source), "output_sha256": qa["technical"]["sha256"], "mask_path": str(mask_output) if mask_output else None, "revision_id": transparency_evidence["revision_id"]})
    return {"status": "TRANSPARENCY_VALID", "output": str(transparent_output), "mask": str(mask_output) if mask_output else None, "checkerboard": str(checker), "revision_id": transparency_evidence["revision_id"], "qa": qa, "halo": halo, "reference_edit_qa": structural, "integrity": integrity, "capability_evidence": evidence}


def refine_master(repo_root: Path, asset_id: str, *, instruction: str, endpoint: str) -> dict[str, Any]:
    if not instruction.strip(): raise GenerationError("refinement instruction cannot be empty")
    asset_path, asset = load_asset(repo_root, asset_id); current = asset.get("current_revision") or {}; source = Path(current.get("output_path", ""))
    if not source.is_file(): raise GenerationError(f"current master output is missing: {source}")
    generation = asset.get("generation", {}); model_id = generation.get("model_id", FAST_MODEL); workflow_id = QUALITY_EDIT if model_id == QUALITY_MODEL else FAST_EDIT
    client = ComfyUIClient(endpoint, timeout=30.0); evidence = probe_comfy_capability(repo_root, client, model_id, workflow_id, capability="reference-edit")
    if evidence["state"] not in {"ready", "verified"}: raise GenerationError(f"reference-edit capability gap: {evidence.get('failure_reason')}")
    upload = client.upload_image(source); filename = upload.get("name") or upload.get("filename")
    if not isinstance(filename, str) or not filename: raise GenerationError("/upload/image did not return an input filename")
    model = load_model(repo_root, model_id); workflow_record = load_workflow(repo_root, workflow_id); compiled_instruction = compile_reference_edit_instruction(instruction, json.loads(Path(asset["master_asset_spec"]).read_text(encoding="utf-8"))); prompt = asset.get("compiled_prompt", "") + " " + compiled_instruction; dimensions = inspect_png(source); seed = len(asset.get("revisions", [])) + 1
    workflow = bind_workflow(workflow_record["api"], prompt=prompt, seed=seed, width=dimensions["width"], height=dimensions["height"], model_names=_model_names(model), image_filename=filename); graph_check = validate_api_workflow(workflow, node_info=client.node_info())
    if not graph_check["live_valid"]: raise GenerationError(f"reference-edit native node validation failed: {graph_check['missing_nodes']}")
    staging_dir = _unique_job_dir(repo_root, asset_path.parent / "jobs", "reference-edit")
    started = time.perf_counter(); job, outputs = _run_job(repo_root, client, workflow, output_dir=staging_dir, filename="reference-edit.png", profile=asset.get("profile", "generic-2d"), capability="reference-edit", workflow_id=workflow_id, model_id=model_id, prompt=prompt, seed=seed, width=dimensions["width"], height=dimensions["height"], input_hashes={"reference_sha256": sha256(source)})
    elapsed_ms = round((time.perf_counter() - started) * 1000); generated_output = Path(outputs[0]["path"]); qa = validate_output(generated_output, width=dimensions["width"], height=dimensions["height"])
    if qa["status"] != "TECHNICAL_VALID": raise GenerationError("reference-edit output failed technical QA")
    revision = _create_revision(asset_path.parent, asset["asset_id"], len(asset.get("revisions", [])) + 1, generated_output, qa, derived_from={"revision_id": current["revision_id"], "output_sha256": current["output_sha256"]}, transparency_status="failed" if asset.get("requires_transparency") else "not-required", extra={"reference_sha256": sha256(source), "instruction": compiled_instruction, "instruction_sha256": prompt_sha256(compiled_instruction), "workflow_id": workflow_id, "model_id": model_id, "job_id": job["job"]["job_id"]})
    output = Path(revision["output_path"])
    reference_evidence = {**evidence, "schema_version": UGAS_VERSION, "state": "verified", "asset_capabilities_qualified": ["reference-edit"], "smoke_test": {"status": "passed", "source_sha256": sha256(source), "output": inspect_png(output), "instruction": compiled_instruction, "instruction_sha256": prompt_sha256(compiled_instruction), "runtime_ms": elapsed_ms, "revision_id": revision["revision_id"]}}; write_json(repo_root / "docs" / "evidence" / "reference-edit.json", reference_evidence)
    asset.setdefault("revisions", []).append(revision); asset["current_revision"] = revision; asset["updated_at"] = _now(); save_asset(asset_path, asset); append_event(repo_root / "tmp" / "provenance.jsonl", {"event": "reference-edit", "asset_id": asset["asset_id"], "derived_from": current["revision_id"], "reference_sha256": sha256(source), "output_sha256": qa["technical"]["sha256"], "workflow": workflow_id, "instruction": compiled_instruction})
    return {"status": revision["state"], "asset_id": asset["asset_id"], "asset_path": str(asset_path), "output": str(output), "reference_sha256": sha256(source), "instruction_sha256": prompt_sha256(compiled_instruction), "qa": qa, "capability_evidence": reference_evidence}


def candidates_show(repo_root: Path, asset_id: str) -> dict[str, Any]:
    _, asset = load_asset(repo_root, asset_id); return json.loads(Path(asset["candidate_set"]).read_text(encoding="utf-8"))


def sprite_pilot(repo_root: Path, **kwargs) -> dict:
    columns = int(kwargs.pop("columns", 1)); rows = int(kwargs.pop("rows", 1))
    if columns != 1 or rows != 1: raise GenerationError(f"sprite-grid workflow not qualified in v{UGAS_VERSION}")
    result = generate_image(repo_root, **kwargs); output = Path(result["output"]); destination = Path(kwargs.get("output_dir") or output.parent); frame_dir = destination / f"{output.stem}-frames"; cropped = crop_grid(output, frame_dir / "frame.png", columns, rows, trim=False, pad=0); sheet_path = destination / f"{output.stem}-sheet.png"; sheet = compose_sheet([Path(item["path"]) for item in cropped["frames"]], sheet_path, columns); metadata = {"schema_version": UGAS_VERSION, "id": f"sprite-sheet-{output.stem}", "source": {"master": str(output), "master_sha256": inspect_png(output)["sha256"]}, "sheet": sheet, "grid": {"columns": columns, "rows": rows, "cell_width": cropped["frames"][0]["width"], "cell_height": cropped["frames"][0]["height"]}, "frames": cropped["frames"], "qa": {"technical_status": "TECHNICAL_VALID", "visual_review": "required", "production_ready": False}, "provenance_ref": result["job"]["job_id"]}; metadata_path = destination / f"{output.stem}-sheet.json"; write_metadata(metadata_path, metadata); result["sprite_sheet"] = str(sheet_path); result["sprite_metadata"] = str(metadata_path); result["pipeline"] = "master-image -> explicit crop/normalize -> sheet metadata -> technical QA; visual review required"; return result


def visual_approve(repo_root: Path, asset_id: str, note: str = "") -> dict[str, Any]:
    return approve_visual(repo_root, asset_id, note)
