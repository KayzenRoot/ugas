"""Execute the bounded v0.6.2 P-only SDXL OpenPose model-card calibration."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ugas.comfyui_client import ComfyUIClient
from ugas.constants import UGAS_VERSION
from ugas.generation import _run_job, _unique_job_dir
from ugas.image_utils import sha256
from ugas.model_registry import load_model, verify_model_files
from ugas.openpose_guides import file_sha256, render_openpose_guide_at_resolution, validate_openpose_guide
from ugas.pose_metric_calibration import detected_joint_pose_metrics
from ugas.pose_qa_estimator import _contact_sheet, _detect_with_landmarker, _draw_overlay, _landmarker, _default_model_path, prepare_preprocessed_image
from ugas.sdxl_openpose_calibration import (
    CALIBRATION_MATRIX,
    CONFIRMATION_SEEDS,
    CONTROLNET_MODEL_ID,
    GUIDE_JSON_RELATIVE,
    MODEL_CARD_CONFIGURATION,
    MODEL_CARD_LICENSE,
    MODEL_CARD_REVISION,
    MODEL_CARD_URL,
    MODEL_ID,
    NEGATIVE_PROMPT_SHA256,
    PHASE,
    PROMPT_ID,
    PROMPT_SHA256,
    SEED,
    WORKFLOW_ID,
    WORKFLOW_TEMPLATE_RELATIVE,
    canonical_hash,
    choose_best_stage_a,
    derive_p_workflow,
    is_oom_error,
    qualification_status,
    validate_calibration_matrix,
)
from ugas.state_consistency import validate_state_consistency
from ugas.workflow_registry import load_workflow


ENDPOINT = "http://127.0.0.1:8188"
PROMPT = (
    "Single full-body 2D game character in an exact left-facing profile pose. "
    "Preserve the canonical R4 identity: face and head, blue-steel cobalt metallic armor, "
    "black cloth, body proportions, palette and sword. Reproduce the supplied OpenPose "
    "guide's raised left arm, bent legs, torso angle and foot placement. Full body visible, "
    "clean readable silhouette, sword beside the body, no extra subjects, no text, no watermark, "
    "no mannequin, no guide lines, no copied background and no motion effects."
)
NEGATIVE_PROMPT = "cropped limbs, extra limbs, duplicate sword, different armor, missing sword, text, watermark, mannequin, skeleton, motion blur"
THRESHOLDS_RELATIVE = "docs/evidence/pose-thresholds-v054.json"
TEMPLATE_PATH = ROOT / WORKFLOW_TEMPLATE_RELATIVE
GUIDE_JSON_PATH = ROOT / GUIDE_JSON_RELATIVE
EVIDENCE_ROOT = ROOT / "docs" / "evidence"
CALIBRATION_ROOT = EVIDENCE_ROOT / "sdxl-openpose-calibration"
RAW_ROOT = CALIBRATION_ROOT / "raw"
OVERLAY_ROOT = CALIBRATION_ROOT / "overlays"
TEMP_ROOT = ROOT / "tmp" / "sdxl-openpose-calibration"

MODEL_NAMES = {
    "__SDXL_CHECKPOINT__": "sd_xl_base_1.0.safetensors",
    "__CONTROLNET__": "xinsir-controlnet-openpose-sdxl-1.0.safetensors",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _digest_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _thresholds() -> dict[str, Any]:
    value = _read(ROOT / THRESHOLDS_RELATIVE)
    if value.get("schema_version") != "0.5.4" or value.get("thresholds_are_frozen_before_jobs") is not True:
        raise RuntimeError("frozen v0.5.4 pose thresholds are required")
    return value


def _model_boundary() -> dict[str, Any]:
    stack = _read(EVIDENCE_ROOT / "sdxl-model-stack-qualification.json")
    artifacts = {item.get("id"): item for item in stack.get("artifacts", [])}
    model_root = Path.home() / "AppData" / "Local" / "UGAS" / "comfyui" / "models"
    checks: dict[str, Any] = {}
    for model_id in (MODEL_ID, CONTROLNET_MODEL_ID):
        item = artifacts.get(model_id)
        model = load_model(ROOT, model_id)
        verified = verify_model_files(model, model_root)
        if not item or item.get("verification", {}).get("verified") is not True or verified.get("hashes_verified") is not True:
            raise RuntimeError(f"MODEL_HASH_MISMATCH:{model_id}")
        checks[model_id] = {"manifest": item, "local_verification": verified}
    return {"source": "docs/evidence/sdxl-model-stack-qualification.json", "download_requested": False, "models": checks, "ipadapter_outside_scope": True}


def _runtime_baseline() -> dict[str, Any]:
    value = _read(EVIDENCE_ROOT / "runtime-doctor-v0.6.0.json")
    if value.get("status") != "RUNTIME_DOCTOR_PASSED":
        raise RuntimeError(f"RUNTIME_DOCTOR_FAILED:{value.get('failures')}")
    return value


def _guide_points(guide: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    required = ("nose", "shoulder_left", "shoulder_right", "elbow_left", "elbow_right", "wrist_left", "wrist_right", "hip_left", "hip_right", "knee_left", "knee_right", "ankle_left", "ankle_right")
    points: dict[str, tuple[float, float]] = {}
    for name in required:
        point = (guide.get("joints") or {}).get(name)
        if not isinstance(point, Mapping) or point.get("visible") is False:
            raise RuntimeError(f"guide joint is missing or hidden:{name}")
        points[name] = (float(point["x"]) / 512.0, float(point["y"]) / 512.0)
    return points


def _orientation(landmarks: Mapping[str, Any]) -> str:
    def x(name: str) -> float | None:
        value = landmarks.get(name)
        if not isinstance(value, Mapping) or value.get("visible") is False:
            return None
        try:
            return float(value["x"])
        except (KeyError, TypeError, ValueError):
            return None
    nose, left, right = x("nose"), x("shoulder_left"), x("shoulder_right")
    if nose is None or left is None or right is None:
        return "unknown"
    delta = nose - ((left + right) / 2.0)
    if delta <= -0.045:
        return "left_profile"
    if delta >= 0.045:
        return "right_profile"
    return "front"


def _raw_pose_qa(raw: Path, *, config: Mapping[str, Any], stage: str, job_dir: Path, guide_points: Mapping[str, tuple[float, float]], thresholds: Mapping[str, Any]) -> dict[str, Any]:
    prepared = prepare_preprocessed_image(raw, "raw_rgb_neutral_gray", job_dir / "raw-pose-preprocess.png")
    model_path = Path(_default_model_path())
    if not model_path.is_file():
        raise RuntimeError("POSE_QA_ESTIMATOR_MODEL_MISSING")
    with _landmarker(model_path) as (mp, detector):
        detection = _detect_with_landmarker(Path(prepared["path"]), mp, detector)
    detected_orientation = _orientation(detection.get("landmarks", {}))
    pose = detected_joint_pose_metrics(guide_points, detection.get("landmarks", {}), target_orientation="left_profile", detected_orientation=detected_orientation)
    absolute = bool(
        pose.get("qualifies")
        and pose.get("measurable_body_joints", 0) >= thresholds["absolute_pose"]["measurable_body_joints_min"]
        and pose.get("pck_at_010", 0.0) >= thresholds["absolute_pose"]["pck_at_010_min"]
        and pose.get("nme", 1.0) <= thresholds["absolute_pose"]["nme_max"]
        and pose.get("limb_angle_mae_degrees", 180.0) <= thresholds["absolute_pose"]["limb_angle_mae_max_degrees"]
        and pose.get("lower_body_pck", 0.0) >= thresholds["absolute_pose"]["lower_body_pck_min"]
        and pose.get("orientation_match") is True
    )
    overlay = job_dir / "raw-pose-overlay.png"
    _draw_overlay(Path(prepared["path"]), detection.get("landmarks", {}), prepared["alpha_bbox_normalized"], f"{config['id']} {stage} raw", overlay, f"pck={pose.get('pck_at_010', 0.0):.3f} nme={pose.get('nme', 1.0):.3f}")
    permanent_overlay = OVERLAY_ROOT / f"{stage}.png"
    permanent_overlay.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(overlay, permanent_overlay)
    return {
        "status": "RAW_POSE_PASS" if absolute else "RAW_POSE_FAILED",
        "preprocess_policy": "raw_rgb_neutral_gray",
        "preprocess": prepared,
        "detection": {key: detection.get(key) for key in ("detected", "pose_count", "measurable_body_joints", "core_coverage", "mean_confidence", "min_confidence")},
        "detected_orientation": detected_orientation,
        "pose": pose,
        "absolute_pose_pass": absolute,
        "overlay_path": _relative(permanent_overlay),
        "raw_output_sha256": sha256(raw),
    }


def _human_form_qa(raw: Path, *, config: Mapping[str, Any], guide_points: Mapping[str, tuple[float, float]]) -> dict[str, Any]:
    """Run only deterministic technical checks available without identity R4."""
    from PIL import Image, ImageStat

    model_path = Path(_default_model_path())
    if not model_path.is_file():
        return {"status": "HUMAN_VISUAL_REVIEW_REQUIRED", "human_form_pass": False, "failure_reasons": ["POSE_QA_ESTIMATOR_MODEL_MISSING"]}
    with _landmarker(model_path, num_poses=2) as (mp, detector):
        detection = _detect_with_landmarker(raw, mp, detector)
    with Image.open(raw) as opened:
        image = opened.convert("RGB")
        small = image.resize((64, 64), Image.Resampling.BILINEAR)
        quantized = {(pixel[0] // 16, pixel[1] // 16, pixel[2] // 16) for pixel in small.getdata()}
        luma = ImageStat.Stat(small.convert("L"))
        border_pixels = [
            pixel
            for y in range(64)
            for x in range(64)
            if x < 4 or x >= 60 or y < 4 or y >= 60
            for pixel in [small.getpixel((x, y))]
        ]
        inner_pixels = [small.getpixel((x, y)) for y in range(8, 56) for x in range(8, 56)]
        border_luma = [sum(pixel) / 3.0 for pixel in border_pixels]
        inner_luma = [sum(pixel) / 3.0 for pixel in inner_pixels]
        border_mean = fmean(border_luma)
        inner_mean = fmean(inner_luma)
        border_std = (fmean([(value - border_mean) ** 2 for value in border_luma])) ** 0.5
    frame_like = abs(border_mean - inner_mean) > 65.0 and border_std < 18.0
    stencil_collapse = len(quantized) < 64 or float(luma.stddev[0]) < 9.0
    detection_sufficient = bool(detection.get("detected") and detection.get("pose_count", 0) == 1 and detection.get("measurable_body_joints", 0) >= 10 and detection.get("core_coverage", 0.0) >= 0.8)
    reasons = []
    if not detection_sufficient:
        reasons.append("mediapipe_detectability_insufficient_or_multiple_poses")
    if frame_like:
        reasons.append("gross_canvas_border_artifact")
    if stencil_collapse:
        reasons.append("pure_stencil_or_silhouette_collapse")
    return {
        "status": "HUMAN_FORM_TECHNICAL_PASS" if not reasons else "HUMAN_FORM_TECHNICAL_FAILED",
        "human_form_pass": not reasons,
        "single_primary_human_subject": detection.get("pose_count") == 1,
        "duplicate_full_body": detection.get("pose_count", 0) > 1,
        "mediapipe_detectability_sufficient": detection_sufficient,
        "frame_like_border_artifact": frame_like,
        "stencil_collapse": stencil_collapse,
        "image_metrics": {"quantized_color_count": len(quantized), "luma_stddev": round(float(luma.stddev[0]), 6), "border_inner_mean_delta": round(abs(border_mean - inner_mean), 6), "border_stddev": round(border_std, 6)},
        "failure_reasons": reasons,
        "visual_review": "required",
    }


def _release_memory(client: ComfyUIClient) -> dict[str, Any]:
    try:
        value = client.free_memory(unload_models=True, free_memory=True)
        return {"status": "COMFYUI_FREE_MEMORY_PASSED", "endpoint": "/free", "unload_models": True, "free_memory": True, "response": value}
    except Exception as exc:
        return {"status": "COMFYUI_FREE_MEMORY_FAILED", "endpoint": "/free", "unload_models": True, "free_memory": True, "error": f"{type(exc).__name__}: {exc}"}


def _runtime_snapshot(client: ComfyUIClient) -> dict[str, Any]:
    try:
        health = client.health()
        system = health.get("system", {}) if isinstance(health, Mapping) else {}
        devices = health.get("devices", []) if isinstance(health, Mapping) else []
        return {"status": "RUNTIME_SNAPSHOT_PASSED", "comfyui": {"version": system.get("comfyui_version"), "pytorch": system.get("pytorch_version")}, "devices": devices}
    except Exception as exc:
        return {"status": "RUNTIME_SNAPSHOT_FAILED", "error": f"{type(exc).__name__}: {exc}"}


def _failed_attempt(config: Mapping[str, Any], seed: int, stage: str, error: Exception, *, strategy: str) -> dict[str, Any]:
    return {
        "schema_version": UGAS_VERSION, "phase": PHASE, "lane": "P", "config_id": config["id"], "seed": seed, "stage": stage, "strategy": strategy,
        "status": "GENERATION_FAILED", "error": f"{type(error).__name__}: {error}", "oom": is_oom_error(error),
        "generation": {"submitted": False, "completed": False, "prompt_id": None, "history_record_key": None, "history_key_matches_prompt_id": False, "fresh_binding": False, "target_existed_before_submission": None, "raw_output_path": None, "raw_output_sha256": None, "raw_output_hash_matches_comfy": False},
        "raw_pose_qa": None, "human_form_qa": None, "stage_a_pass": False,
    }


def _attempt(client: ComfyUIClient, *, config: Mapping[str, Any], seed: int, stage: str, strategy: str, guide_path: Path, guide_value: dict[str, Any], guide_points: Mapping[str, tuple[float, float]], thresholds: Mapping[str, Any], template: Mapping[str, Any], template_sha256: str, node_info: Mapping[str, Any], available_models: set[str]) -> dict[str, Any]:
    try:
        upload = client.upload_image(guide_path)
        guide_name = upload.get("name") or upload.get("filename")
        if not guide_name:
            raise RuntimeError("ComfyUI guide upload did not return a filename")
        workflow, workflow_meta = derive_p_workflow(template, config, prompt=PROMPT, negative_prompt=NEGATIVE_PROMPT, seed=seed, guide_filename=str(guide_name), model_names=MODEL_NAMES, node_info=node_info, available_models=available_models)
        job_dir = _unique_job_dir(ROOT, TEMP_ROOT, stage)
        input_hashes = {"openpose_guide_json_sha256": _digest_json(guide_value), "openpose_control_png_sha256": sha256(guide_path)}
        context = {"prompt_id": PROMPT_ID, "phase": PHASE, "lane": "P", "config_id": config["id"], "strategy": strategy, "model_card_configuration": MODEL_CARD_CONFIGURATION, "previous_frame_chaining": False, "ipadapter_executed": False, "guide_json_sha256": input_hashes["openpose_guide_json_sha256"], "guide_png_sha256": input_hashes["openpose_control_png_sha256"]}
        result, outputs = _run_job(ROOT, client, workflow, output_dir=job_dir, filename=f"{config['id'].lower()}-seed-{seed}.png", profile="generic-2d", capability="sdxl-openpose-model-card-calibration", workflow_id=WORKFLOW_ID, model_id=MODEL_ID, prompt=PROMPT, seed=seed, width=int(config["width"]), height=int(config["height"]), input_hashes=input_hashes, qualification_context=context, seed_was_used_before=False, workflow_sha256=workflow_meta["workflow_sha256"])
        raw = Path(outputs[0]["path"])
        raw_destination = RAW_ROOT / f"{stage}.png"
        if raw_destination.exists():
            raise RuntimeError("RAW_OUTPUT_STALE_TARGET")
        raw_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw, raw_destination)
        execution = result["job"].get("execution_evidence", {})
        raw_hash = sha256(raw_destination)
        fresh = bool(execution.get("fresh_binding") is True and execution.get("history_key_matches_prompt_id") is True and execution.get("target_existed_before_submission") is False and execution.get("seed_was_used_before") is False and context["previous_frame_chaining"] is False)
        generation = {"submitted": True, "completed": True, "prompt_id": execution.get("prompt_id"), "history_record_key": execution.get("history_record_key"), "history_key_matches_prompt_id": execution.get("history_key_matches_prompt_id") is True, "fresh_binding": fresh, "target_existed_before_submission": execution.get("target_existed_before_submission"), "previous_frame_chaining": False, "raw_output_path": _relative(raw_destination), "raw_output_sha256": raw_hash, "raw_output_bytes": raw_destination.stat().st_size, "raw_output_hash_matches_comfy": raw_hash == (execution.get("outputs") or [{}])[0].get("data_sha256"), "execution_evidence": execution}
        try:
            pose = _raw_pose_qa(raw_destination, config=config, stage=stage, job_dir=job_dir, guide_points=guide_points, thresholds=thresholds)
        except Exception as exc:
            pose = {"status": "RAW_POSE_QA_FAILED", "preprocess_policy": "raw_rgb_neutral_gray", "absolute_pose_pass": False, "failure_reasons": [f"{type(exc).__name__}: {exc}"], "raw_output_sha256": raw_hash}
        human = _human_form_qa(raw_destination, config=config, guide_points=guide_points)
        stage_a_pass = bool(fresh and generation["raw_output_hash_matches_comfy"] and pose.get("absolute_pose_pass") is True and human.get("human_form_pass") is True)
        return {"schema_version": UGAS_VERSION, "phase": PHASE, "lane": "P", "config_id": config["id"], "config": dict(config), "seed": seed, "stage": stage, "strategy": strategy, "workflow_template_sha256": template_sha256, "workflow_sha256": workflow_meta["workflow_sha256"], "workflow_graph": workflow_meta["graph"], "guide_upload_name": str(guide_name), "generation": generation, "raw_output_path": _relative(raw_destination), "raw_output_sha256": raw_hash, "raw_pose_qa": pose, "human_form_qa": human, "stage_a_pass": stage_a_pass, "status": "TRIAGE_PASS" if stage_a_pass else "TRIAGE_FAILED", "runtime_ms": execution.get("runtime_ms"), "postprocess": {"status": "NOT_RUN", "reason": "BiRefNet is outside P-only qualification"}, "identity_qa": None}
    except Exception as exc:
        return _failed_attempt(config, seed, stage, exc, strategy=strategy)


def _p2_with_retry(client: ComfyUIClient, *, config: Mapping[str, Any], seed: int, guide_path: Path, guide_value: dict[str, Any], guide_points: Mapping[str, tuple[float, float]], thresholds: Mapping[str, Any], template: Mapping[str, Any], template_sha256: str, node_info: Mapping[str, Any], available_models: set[str]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    normal = _attempt(client, config=config, seed=seed, stage="p2-seed-62701-normal", strategy="normal-runtime", guide_path=guide_path, guide_value=guide_value, guide_points=guide_points, thresholds=thresholds, template=template, template_sha256=template_sha256, node_info=node_info, available_models=available_models)
    attempts = [normal]
    release = None
    if normal.get("status") == "GENERATION_FAILED" and normal.get("oom") is True:
        release = _release_memory(client)
        retry = _attempt(client, config=config, seed=seed, stage="p2-seed-62701-lowvram-retry", strategy="comfyui-free-memory-unload-retry", guide_path=guide_path, guide_value=guide_value, guide_points=guide_points, thresholds=thresholds, template=template, template_sha256=template_sha256, node_info=node_info, available_models=available_models)
        retry["retry_after_memory_strategy"] = release
        attempts.append(retry)
        if retry.get("status") != "GENERATION_FAILED":
            return retry, attempts, release
        retry["hardware_status"] = "SDXL_OPENPOSE_1024_HARDWARE_GAP"
        return retry, attempts, release
    return normal, attempts, release


def _matrix_entry(config: Mapping[str, Any], *, guide_path: Path, guide_value: dict[str, Any], template_sha256: str, workflow: dict[str, Any], workflow_meta: dict[str, Any], object_info: dict[str, Any]) -> dict[str, Any]:
    return {**dict(config), "workflow_id": WORKFLOW_ID, "workflow_template_path": WORKFLOW_TEMPLATE_RELATIVE, "workflow_template_sha256": template_sha256, "derived_workflow_sha256": workflow_meta["workflow_sha256"], "workflow": workflow, "graph": workflow_meta["graph"], "guide_json_path": GUIDE_JSON_RELATIVE, "guide_json_sha256": _digest_json(guide_value), "control_png_path": _relative(guide_path), "control_png_sha256": sha256(guide_path), "scheduler_mapping": {"model_card": MODEL_CARD_CONFIGURATION["scheduler"], "comfyui_sampler_name": config["sampler_name"], "comfyui_scheduler": config["scheduler"]}, "object_info_sha256": _digest_json(object_info)}


def _write_contacts(records: list[Mapping[str, Any]], *, path_key: str, filename: str, label: str) -> str | None:
    def value(item: Mapping[str, Any]) -> str | None:
        if path_key == "raw_pose_qa":
            nested = item.get("raw_pose_qa")
            return str(nested.get("overlay_path")) if isinstance(nested, Mapping) and nested.get("overlay_path") else None
        return str(item.get(path_key)) if item.get(path_key) else None
    items = [(ROOT / path, item) for item in records if (path := value(item)) and (ROOT / path).is_file()]
    if not items:
        return None
    destination = TEMP_ROOT / filename
    labels = [f"{item.get('config_id')} seed={item.get('seed')} {label}" for _, item in items]
    _contact_sheet([path for path, _ in items], labels, destination, columns=3)
    permanent = EVIDENCE_ROOT / filename
    permanent.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(destination, permanent)
    return _relative(permanent)


def _execution_evidence(attempts: list[Mapping[str, Any]], confirmation: list[Mapping[str, Any]], status: str) -> dict[str, Any]:
    all_records = [dict(item) for item in attempts + confirmation]
    completed = [item for item in all_records if (item.get("generation") or {}).get("completed") is True]
    return {"schema_version": UGAS_VERSION, "prompt_id": PROMPT_ID, "phase": PHASE, "status": status, "triage_config_count": 3, "triage_attempted_execution_count": len(attempts), "confirmation_attempted_execution_count": len(confirmation), "attempted_execution_count": len(all_records), "generation_completed_count": len(completed), "all_completed_prompt_history_raw_sha": bool(completed) and len(completed) == len(all_records) and all((item.get("generation") or {}).get("fresh_binding") is True and (item.get("generation") or {}).get("raw_output_hash_matches_comfy") is True for item in completed), "previous_frame_chaining": False, "ipadapter_executed": False, "records": [{"phase": "confirmation" if item in confirmation else "triage", "config_id": item.get("config_id"), "seed": item.get("seed"), "stage": item.get("stage"), "status": item.get("status"), "generation": item.get("generation"), "workflow_sha256": item.get("workflow_sha256"), "strategy": item.get("strategy")} for item in all_records]}


def _write_visual_manifest(confirmation: list[Mapping[str, Any]]) -> str:
    """Bind current v0.6.2 review roles to immutable files and hashes."""
    historical_path = EVIDENCE_ROOT / "review-visuals-v0.6.1.json"
    historical = _read(historical_path)
    images = [dict(item) for item in historical.get("images", [])]
    existing = {str(item.get("archive_name")) for item in images}
    current_paths = [
        ("sdxl-openpose-config-triage-contact-sheet.png", EVIDENCE_ROOT / "sdxl-openpose-config-triage-contact-sheet.png", "v0.6.2-triage-raw"),
        ("sdxl-openpose-config-pose-overlays-contact-sheet.png", EVIDENCE_ROOT / "sdxl-openpose-config-pose-overlays-contact-sheet.png", "v0.6.2-triage-pose"),
        ("sdxl-openpose-config-matrix.json", EVIDENCE_ROOT / "sdxl-openpose-config-matrix.json", "v0.6.2-config-matrix"),
        ("sdxl-openpose-config-runtime-table.json", EVIDENCE_ROOT / "sdxl-openpose-config-runtime-table.json", "v0.6.2-runtime-table"),
        ("execution-evidence-v0.6.2.json", EVIDENCE_ROOT / "execution-evidence-v0.6.2.json", "v0.6.2-execution"),
        ("sdxl-openpose-p-qualification.json", EVIDENCE_ROOT / "sdxl-openpose-p-qualification.json", "v0.6.2-p-qualification"),
    ]
    for width in (512, 768, 1024):
        current_paths.append((f"sdxl-openpose-guide-{width}.png", EVIDENCE_ROOT / f"sdxl-openpose-guide-{width}.png", f"v0.6.2-guide-{width}"))
    for directory, prefix in ((RAW_ROOT, "raw"), (OVERLAY_ROOT, "overlay")):
        if directory.is_dir():
            for path in sorted(directory.glob("*.png")):
                current_paths.append((f"{prefix}-{path.name}", path, f"v0.6.2-{prefix}-{path.stem}"))
    if confirmation:
        for name in ("sdxl-openpose-confirmation-contact-sheet.png", "sdxl-openpose-confirmation-pose-overlays.png"):
            current_paths.append((name, EVIDENCE_ROOT / name, f"v0.6.2-{Path(name).stem}"))
    def file_digest(source: Path) -> str:
        data = source.read_bytes()
        if source.suffix.casefold() in {".json", ".md", ".txt"}:
            data = data.replace(b"\r\n", b"\n")
        return hashlib.sha256(data).hexdigest()

    for archive_name, source, revision_id in current_paths:
        if archive_name in existing or not source.is_file():
            continue
        images.append({"archive_name": archive_name, "source_path": _relative(source), "revision_id": revision_id, "sha256": file_digest(source)})
    required_current = [
        "sdxl-openpose-config-triage-contact-sheet.png",
        "sdxl-openpose-config-pose-overlays-contact-sheet.png",
        "sdxl-openpose-config-matrix.json",
        "sdxl-openpose-config-runtime-table.json",
        "execution-evidence-v0.6.2.json",
        "sdxl-openpose-p-qualification.json",
        "sdxl-openpose-guide-512.png",
        "sdxl-openpose-guide-768.png",
        "sdxl-openpose-guide-1024.png",
    ]
    required_current.extend(item[0] for item in current_paths if item[0].startswith("raw-") or item[0].startswith("overlay-"))
    if confirmation:
        required_current.extend(["sdxl-openpose-confirmation-contact-sheet.png", "sdxl-openpose-confirmation-pose-overlays.png"])
    manifest = {"schema_version": UGAS_VERSION, "manifest_type": "review-visual-evidence", "review_state": "sdxl-openpose-model-card-calibration", "images": images, "required_current_visuals": sorted(set(required_current))}
    path = EVIDENCE_ROOT / "review-visuals-v0.6.2.json"
    _write(path, manifest)
    return _relative(path)


def run(endpoint: str = ENDPOINT, *, json_output: bool = False) -> dict[str, Any]:
    progress = lambda message: print(message, file=sys.stderr if json_output else sys.stdout, flush=True)
    failures = validate_calibration_matrix()
    if failures:
        raise RuntimeError("invalid calibration matrix: " + ",".join(failures))
    if UGAS_VERSION != "0.6.2":
        raise RuntimeError("runtime version is not 0.6.2")
    thresholds = _thresholds()
    model_boundary = _model_boundary()
    runtime = _runtime_baseline()
    guide_value = _read(GUIDE_JSON_PATH)
    guide_validation = validate_openpose_guide(guide_value)
    if guide_validation["status"] != "OPENPOSE_GUIDE_VALID":
        raise RuntimeError("guide validation failed")
    guide_points = _guide_points(guide_value)
    template_record = load_workflow(ROOT, WORKFLOW_ID)
    template = template_record["api"]
    template_sha256 = template_record["sha256"]
    if template_record.get("version") not in {"0.6.0", "0.6.2"}:
        raise RuntimeError("unexpected P workflow baseline version")
    client = ComfyUIClient(endpoint, timeout=120.0)
    node_info_full = client.node_info()
    object_info = node_info_full.get("KSampler", {}) if isinstance(node_info_full, Mapping) else {}
    required_inputs = object_info.get("input", {}).get("required", {}) if isinstance(object_info, Mapping) else {}
    sampler_values = required_inputs.get("sampler_name", [[], {}])[0] if isinstance(required_inputs.get("sampler_name"), list) else []
    scheduler_values = required_inputs.get("scheduler", [[], {}])[0] if isinstance(required_inputs.get("scheduler"), list) else []
    if "euler_ancestral" not in sampler_values or "normal" not in scheduler_values:
        raise RuntimeError("KSampler object_info cannot validate Euler Ancestral semantic mapping")
    available_models = {item for folder in ("checkpoints", "controlnet") for item in client.list_models(folder)}
    guide_manifest: dict[str, Any] = {}
    matrix_entries: list[dict[str, Any]] = []
    for config in CALIBRATION_MATRIX:
        guide_path = EVIDENCE_ROOT / f"sdxl-openpose-guide-{config['width']}.png"
        render = render_openpose_guide_at_resolution(guide_value, guide_path, width=int(config["width"]), height=int(config["height"]))
        guide_manifest[config["id"]] = {"path": _relative(guide_path), "sha256": file_sha256(guide_path), "guide_json_sha256": _digest_json(guide_value), "renderer_version": render["renderer_version"], "render_parameters": render["render_parameters"]}
        workflow, workflow_meta = derive_p_workflow(template, config, prompt=PROMPT, negative_prompt=NEGATIVE_PROMPT, seed=SEED, guide_filename=f"sdxl-openpose-guide-{config['width']}.png", model_names=MODEL_NAMES, node_info=node_info_full, available_models=available_models)
        matrix_entries.append(_matrix_entry(config, guide_path=guide_path, guide_value=guide_value, template_sha256=template_sha256, workflow=workflow, workflow_meta=workflow_meta, object_info=object_info))
    object_info_digest = _digest_json(object_info)
    matrix = {"schema_version": UGAS_VERSION, "prompt_id": PROMPT_ID, "phase": PHASE, "status": "MATRIX_VALIDATED", "exact_matrix": True, "source_workflow": {"id": WORKFLOW_ID, "path": WORKFLOW_TEMPLATE_RELATIVE, "sha256": template_sha256, "preserved": True}, "model_card": {"url": MODEL_CARD_URL, "revision": MODEL_CARD_REVISION, "license": MODEL_CARD_LICENSE, "configuration": MODEL_CARD_CONFIGURATION}, "prompt": {"positive_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(), "negative_sha256": hashlib.sha256(NEGATIVE_PROMPT.encode()).hexdigest(), "historical_positive_sha256": PROMPT_SHA256, "historical_negative_sha256": NEGATIVE_PROMPT_SHA256}, "scheduler_mapping": {"target": MODEL_CARD_CONFIGURATION["scheduler"], "runtime_sampler_name": "euler_ancestral", "runtime_scheduler": "normal", "object_info_sha256": object_info_digest, "observed_sampler_values": sampler_values, "observed_scheduler_values": scheduler_values, "semantic_mapping_validated": True}, "guide_rendering": guide_manifest, "configs": matrix_entries, "ipadapter_nodes_forbidden": True}
    _write(EVIDENCE_ROOT / "sdxl-openpose-config-matrix.json", matrix)
    progress("P0/P1/P2 matrix validated; starting sequential triage")
    records: list[dict[str, Any]] = []
    all_attempts: list[dict[str, Any]] = []
    for config in CALIBRATION_MATRIX:
        progress(f"RUN {config['id']} {config['width']}x{config['height']} steps={config['steps']} sampler={config['sampler_name']} scheduler={config['scheduler']} strength={config['controlnet_strength']}")
        guide_path = EVIDENCE_ROOT / f"sdxl-openpose-guide-{config['width']}.png"
        if config["id"] == "P2":
            record, attempts, _release = _p2_with_retry(client, config=config, seed=SEED, guide_path=guide_path, guide_value=guide_value, guide_points=guide_points, thresholds=thresholds, template=template, template_sha256=template_sha256, node_info=node_info_full, available_models=available_models)
            all_attempts.extend(attempts)
        else:
            record = _attempt(client, config=config, seed=SEED, stage=f"{config['id'].lower()}-seed-{SEED}", strategy="normal-runtime", guide_path=guide_path, guide_value=guide_value, guide_points=guide_points, thresholds=thresholds, template=template, template_sha256=template_sha256, node_info=node_info_full, available_models=available_models)
            all_attempts.append(record)
        record["runtime_snapshot"] = _runtime_snapshot(client)
        records.append(record)
        if record.get("status") == "GENERATION_FAILED" and record.get("oom") is True:
            progress(f"{config['id']} OOM; retry/hardware status recorded")
        else:
            pose = record.get("raw_pose_qa") or {}
            progress(f"DONE {config['id']} status={record.get('status')} pose={pose.get('status', 'NOT_RUN')} pck={((pose.get('pose') or {}).get('pck_at_010', 'NA'))} nme={((pose.get('pose') or {}).get('nme', 'NA'))}")
        _release_memory(client)
    stage_best = choose_best_stage_a(records)
    triage_attempts = list(all_attempts)
    confirmation: list[dict[str, Any]] = []
    confirmation_contact = None
    confirmation_overlay_contact = None
    selected_id = str(stage_best.get("config_id")) if stage_best else None
    if stage_best:
        selected_config = next(config for config in CALIBRATION_MATRIX if config["id"] == selected_id)
        guide_path = EVIDENCE_ROOT / f"sdxl-openpose-guide-{selected_config['width']}.png"
        progress(f"STAGE A PASS: confirming {selected_id} with seeds {','.join(str(seed) for seed in CONFIRMATION_SEEDS)}")
        for confirm_seed in CONFIRMATION_SEEDS:
            item = _attempt(client, config=selected_config, seed=confirm_seed, stage=f"confirmation-{selected_id.lower()}-seed-{confirm_seed}", strategy="normal-runtime", guide_path=guide_path, guide_value=guide_value, guide_points=guide_points, thresholds=thresholds, template=template, template_sha256=template_sha256, node_info=node_info_full, available_models=available_models)
            confirmation.append(item)
            all_attempts.append(item)
            _release_memory(client)
        confirmation_contact = _write_contacts(confirmation, path_key="raw_output_path", filename="sdxl-openpose-confirmation-contact-sheet.png", label="confirmation raw")
        confirmation_overlay_contact = _write_contacts(confirmation, path_key="raw_pose_qa", filename="sdxl-openpose-confirmation-pose-overlays.png", label="confirmation pose")
    else:
        progress("NO STAGE A PASS: confirmation remains NOT_RUN")
    confirmation_pass = bool(confirmation and len(confirmation) == 3 and all(item.get("stage_a_pass") is True for item in confirmation))
    p2 = next((item for item in records if item.get("config_id") == "P2"), {})
    p2_hardware_gap = p2.get("hardware_status") == "SDXL_OPENPOSE_1024_HARDWARE_GAP" or any(item.get("hardware_status") == "SDXL_OPENPOSE_1024_HARDWARE_GAP" for item in all_attempts)
    status = qualification_status(selected_id=selected_id, confirmation_pass=confirmation_pass, p2_hardware_gap=p2_hardware_gap)
    if not stage_best:
        status = "SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS"
    matrix["status"] = "CALIBRATION_COMPLETED"
    matrix["triage_results"] = records
    matrix["confirmation_status"] = "RUN" if confirmation else "NOT_RUN"
    matrix["confirmation_seeds"] = list(CONFIRMATION_SEEDS) if confirmation else []
    matrix["p2_hardware_substatus"] = "SDXL_OPENPOSE_1024_HARDWARE_GAP" if p2_hardware_gap else None
    _write(EVIDENCE_ROOT / "sdxl-openpose-config-matrix.json", matrix)
    _write(EVIDENCE_ROOT / "sdxl-openpose-config-runtime-table.json", {"schema_version": UGAS_VERSION, "phase": PHASE, "status": status, "runtime_baseline": runtime, "runtime_before_jobs": _runtime_snapshot(client), "configs": [{"config_id": item.get("config_id"), "dimensions": [item.get("config", {}).get("width"), item.get("config", {}).get("height")], "steps": item.get("config", {}).get("steps"), "sampler_name": item.get("config", {}).get("sampler_name"), "scheduler": item.get("config", {}).get("scheduler"), "controlnet_strength": item.get("config", {}).get("controlnet_strength"), "status": item.get("status"), "runtime_ms": item.get("runtime_ms"), "attempts": [{"stage": attempt.get("stage"), "strategy": attempt.get("strategy"), "status": attempt.get("status"), "oom": attempt.get("oom", False), "error": attempt.get("error"), "runtime_ms": attempt.get("runtime_ms"), "retry_after_memory_strategy": attempt.get("retry_after_memory_strategy")} for attempt in all_attempts if attempt.get("config_id") == item.get("config_id")] } for item in records], "p2_retry_policy": {"max_retries": 1, "parameters_unchanged": True, "strategy": "comfyui-free-memory-unload-retry"}})
    raw_contact = _write_contacts(records, path_key="raw_output_path", filename="sdxl-openpose-config-triage-contact-sheet.png", label="triage raw")
    overlay_records = [item for item in records if (item.get("raw_pose_qa") or {}).get("overlay_path")]
    overlay_contact = _write_contacts(overlay_records, path_key="raw_pose_qa", filename="sdxl-openpose-config-pose-overlays-contact-sheet.png", label="triage pose")
    execution = _execution_evidence(triage_attempts, confirmation, status)
    execution["triage_records"] = records
    execution["confirmation_records"] = confirmation
    execution["all_configs_have_record"] = len(records) == 3 and {item.get("config_id") for item in records} == {"P0", "P1", "P2"}
    execution["raw_contact_sheet"] = raw_contact
    execution["pose_overlay_contact_sheet"] = overlay_contact
    _write(EVIDENCE_ROOT / "execution-evidence-v0.6.2.json", execution)
    qualification = {"schema_version": UGAS_VERSION, "prompt_id": PROMPT_ID, "phase": PHASE, "status": status, "model_card": {"url": MODEL_CARD_URL, "revision": MODEL_CARD_REVISION, "license": MODEL_CARD_LICENSE, "configuration": MODEL_CARD_CONFIGURATION}, "baseline": {"version": "0.6.1", "commit": "95e590360dc90b509be5e70495f5904af2eb489f", "tests_audited": 152, "snapshot_checks": 500}, "scope": {"lane": "P", "configs": ["P0", "P1", "P2"], "triage_seed": SEED, "confirmation_seeds": list(CONFIRMATION_SEEDS) if confirmation else [], "ipadapter_executed": False, "identity_r4_executed": False, "benchmark": "NOT_RUN", "walk": "NOT_RUN", "anchors": "NOT_RUN", "new_provider": False}, "thresholds": {"source": THRESHOLDS_RELATIVE, "schema_version": thresholds["schema_version"], "changed": False, "absolute_pose": thresholds["absolute_pose"]}, "triage": {"records": records, "selected_configuration": selected_id, "selection_rule": "pose metrics first; runtime only final tie-breaker", "stage_a_pass_count": sum(item.get("stage_a_pass") is True for item in records)}, "confirmation": {"status": "NOT_RUN" if not confirmation else "COMPLETED", "seeds": list(CONFIRMATION_SEEDS) if confirmation else [], "records": confirmation, "pass": confirmation_pass}, "p2": {"status": "SDXL_OPENPOSE_1024_HARDWARE_GAP" if p2_hardware_gap else p2.get("status"), "hardware_gap": p2_hardware_gap, "normal_and_retry_preserve_parameters": True}, "raw_contact_sheet": raw_contact, "pose_overlay_contact_sheet": overlay_contact, "confirmation_contact_sheet": confirmation_contact, "confirmation_pose_overlay_contact_sheet": confirmation_overlay_contact, "execution_evidence": "docs/evidence/execution-evidence-v0.6.2.json", "guide_manifest": guide_manifest, "model_boundary": model_boundary, "runtime": runtime, "production_approval": "not-granted", "external_approval": "not-claimed"}
    qualification["review_visual_manifest"] = "docs/evidence/review-visuals-v0.6.2.json"
    _write(EVIDENCE_ROOT / "sdxl-openpose-p-qualification.json", qualification)
    _write_visual_manifest(confirmation)
    return {"status": status, "new_generation_jobs": len(all_attempts), "triage_records": records, "confirmation_records": confirmation, "execution": execution, "qualification": qualification}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UGAS v0.6.2 P-only SDXL OpenPose model-card calibration")
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    try:
        result = run(args.endpoint, json_output=args.json_output)
    except Exception as exc:
        payload = {"status": "SDXL_OPENPOSE_CALIBRATION_BLOCKED", "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps({"status": result["status"], "new_generation_jobs": result["new_generation_jobs"], "triage_config_count": 3, "confirmation": "RUN" if result["confirmation_records"] else "NOT_RUN"}, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"SDXL_OPENPOSE_P_LANE_QUALIFIED", "SDXL_OPENPOSE_P_LANE_QUALIFIED_768", "SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS", "SDXL_OPENPOSE_1024_HARDWARE_GAP"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
