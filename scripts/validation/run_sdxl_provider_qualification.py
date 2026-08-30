"""Run the bounded UGAS v0.6.1 corrective SDXL smoke qualification.

The script implements only the prompt's P/I/PI qualification slice. It never
creates walk frames, directional anchors, spritesheets, GIFs or animation
artifacts. Model weights and the GPL custom node remain outside this repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from ugas.comfyui_client import ComfyUIClient
from ugas.constants import UGAS_VERSION
from ugas.generation import _run_job, _unique_job_dir, background_remove
from ugas.identity import ANCHOR_REVISION_ID, ANCHOR_SHA256
from ugas.identity_hard_gates import analyze_foreground_components, evaluate_identity_hard_gates
from ugas.image_utils import inspect_png, sha256
from ugas.model_registry import load_model, verify_model_files
from ugas.multiview import _identity_descriptor
from ugas.pose_metric_calibration import detected_joint_pose_metrics
from ugas.pose_qa_estimator import (
    _contact_sheet,
    _detect_with_landmarker,
    _draw_overlay,
    _landmarker,
    _default_model_path,
    prepare_preprocessed_image,
)
from ugas.state_consistency import validate_state_consistency
from ugas.workflow_registry import bind_workflow, load_workflow, validate_api_workflow, workflow_hash


PROMPT_ID = "PROMPT-05C-UGAS-SDXL-SMOKE-EVIDENCE-HARD-GATES-v0.6.1"
ENDPOINT = "http://127.0.0.1:8188"
SMOKE_SEED = 61701
PAIRED_SEEDS: tuple[int, ...] = ()
BENCHMARK_SEED = None
CONFIRMATION_SEEDS: tuple[int, ...] = ()
WIDTH = 512
HEIGHT = 512
ANCHOR_RELATIVE = "docs/evidence/reference-edit-selected-transparent.png"
GUIDE_RELATIVE = "docs/evidence/openpose-guide-v3-control-example.png"
GUIDE_JSON_RELATIVE = "pose-guides/openpose-v3/challenges/multiref-strong-left-arm-up.json"
OUTPUT_ROOT = REPO_ROOT / "tmp" / "sdxl-provider-v061"
PERMANENT_ROOT = REPO_ROOT / "docs" / "evidence" / "sdxl-qualification"
RAW_ROOT = PERMANENT_ROOT / "raw"
EXECUTION_EVIDENCE_PATH = REPO_ROOT / "docs" / "evidence" / "execution-evidence-v0.6.1.json"
WORKFLOWS = {
    "P": "sdxl-openpose-controlnet-p",
    "I": "sdxl-ipadapter-i",
    "PI": "sdxl-openpose-ipadapter-character",
}
MODEL_NAMES = {
    "__SDXL_CHECKPOINT__": "sd_xl_base_1.0.safetensors",
    "__CONTROLNET__": "xinsir-controlnet-openpose-sdxl-1.0.safetensors",
    "__IPADAPTER__": "ip-adapter-plus_sdxl_vit-h.safetensors",
    "__CLIP_VISION__": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
    "__CONTROLNET_STRENGTH__": 0.9,
    "__IP_STRENGTH__": 0.8,
}
COMMON_PROMPT = (
    "Single full-body 2D game character in an exact left-facing profile pose. "
    "Preserve the canonical R4 identity: face and head, blue-steel cobalt metallic armor, "
    "black cloth, body proportions, palette and sword. Reproduce the supplied OpenPose "
    "guide's raised left arm, bent legs, torso angle and foot placement. Full body visible, "
    "clean readable silhouette, sword beside the body, no extra subjects, no text, no watermark, "
    "no mannequin, no guide lines, no copied background and no motion effects."
)
NEGATIVE_PROMPT = "cropped limbs, extra limbs, duplicate sword, different armor, missing sword, text, watermark, mannequin, skeleton, motion blur"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def _review_digest(path: Path) -> str:
    """Match the review verifier's canonical hash for text and binary evidence."""
    data = path.read_bytes()
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _guide_points(guide: dict[str, Any]) -> dict[str, tuple[float, float]]:
    joints = guide.get("joints") or {}
    required = (
        "nose", "shoulder_left", "shoulder_right", "elbow_left", "elbow_right",
        "wrist_left", "wrist_right", "hip_left", "hip_right", "knee_left",
        "knee_right", "ankle_left", "ankle_right",
    )
    points: dict[str, tuple[float, float]] = {}
    for name in required:
        item = joints.get(name)
        if not isinstance(item, dict) or item.get("visible") is False:
            raise RuntimeError(f"challenge guide missing visible joint: {name}")
        points[name] = (float(item["x"]) / WIDTH, float(item["y"]) / HEIGHT)
    return points


def _infer_orientation(landmarks: dict[str, Any]) -> str:
    def x(name: str) -> float | None:
        item = landmarks.get(name)
        if not isinstance(item, dict) or item.get("visible") is False:
            return None
        try:
            return float(item["x"])
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


def _thresholds() -> dict[str, Any]:
    value = _read(REPO_ROOT / "docs/evidence/pose-thresholds-v054.json")
    if value.get("schema_version") != "0.5.4" or value.get("thresholds_are_frozen_before_jobs") is not True:
        raise RuntimeError("v0.5.4 thresholds are not frozen and reusable")
    expected_ranges = {"pck": [0.0, 1.0], "nme": [0.0, 1.0], "lower_body_pck": [0.0, 1.0], "normalized_score": [0.0, 1.0], "identity_score": [0.0, 1.0], "angle_mae_degrees": [0.0, 180.0]}
    if value.get("range_validation", {}).get("bounded_metrics") != expected_ranges:
        raise RuntimeError("v0.5.4 metric ranges changed")
    return value


def _model_qualification() -> dict[str, Any]:
    stack = REPO_ROOT / "docs/evidence/sdxl-model-stack-qualification.json"
    if not stack.is_file():
        raise RuntimeError("MODEL_ARTIFACT_MISSING: run qualify_sdxl_models.py first")
    value = _read(stack)
    if value.get("status") != "MODEL_ARTIFACTS_VERIFIED":
        raise RuntimeError(f"MODEL_ARTIFACT_QUALIFICATION_FAILED: {value.get('status')}")
    if len(value.get("artifacts", [])) != 4 or any(not item.get("verification", {}).get("verified") for item in value["artifacts"]):
        raise RuntimeError("MODEL_HASH_MISMATCH: all four exact artifacts are required")
    for model_id in ("sdxl-base-1.0", "xinsir-controlnet-openpose-sdxl-1.0", "ipadapter-plus-sdxl-vit-h", "clip-vision-vit-h"):
        model = load_model(REPO_ROOT, model_id)
        check = verify_model_files(model, Path.home() / "AppData" / "Local" / "UGAS" / "comfyui" / "models")
        if not check["hashes_verified"]:
            raise RuntimeError(f"MODEL_HASH_MISMATCH: {model_id}")
    return value


def _audit() -> dict[str, Any]:
    value = _read(REPO_ROOT / "docs/evidence/custom-node-audit-ipadapter-plus.json")
    if value.get("audit_status") != "CUSTOM_NODE_AUDIT_PASSED" or value.get("commit") != "a0f451a5113cf9becb0847b92884cb10cbdec0ef":
        raise RuntimeError("IPADAPTER_CUSTOM_NODE_SECURITY_GAP")
    if value.get("license") != "GPL-3.0-only" or value.get("distribution_boundary") != "local-only" or value.get("source_vendored_in_ugas") is not False:
        raise RuntimeError("IPADAPTER_CUSTOM_NODE_SECURITY_GAP")
    return value


def _runtime() -> dict[str, Any]:
    value = _read(REPO_ROOT / "docs/evidence/runtime-doctor-v0.6.0.json")
    if value.get("status") != "RUNTIME_DOCTOR_PASSED":
        raise RuntimeError(f"SDXL_CONTROL_PROVIDER_HARDWARE_GAP: {value.get('failures')}")
    return value


def _state_update(gate: str, *, started: bool, jobs: int, stop_reason: str | None = None) -> dict[str, Any]:
    path = REPO_ROOT / "docs/evidence/current-state.json"
    state = _read(path)
    state["current_gate"] = gate
    state["stop_reason"] = stop_reason
    state["provider_smoke_status"] = gate
    state["state_consistency"]["status"] = gate
    state["state_consistency"]["new_generation_started"] = bool(started)
    state["state_consistency"]["new_generation_jobs"] = int(jobs)
    state["allowed_next_actions"] = ["review_sdxl_provider_smoke_classification", "preserve_v060_provider_lane"]
    _write(path, state)
    checkpoint = (REPO_ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
    review = (REPO_ROOT / "REVIEW-v0.6.1.md").read_text(encoding="utf-8")
    result = validate_state_consistency(state, checkpoint, review)
    _write(REPO_ROOT / "docs/evidence/state-consistency.json", result)
    if result["status"] != "STATE_CONSISTENCY_PASSED":
        raise RuntimeError("state consistency failed: " + "; ".join(result["failures"]))
    return result


def _replace_current_docs(gate: str, *, started: bool, jobs: int) -> None:
    for path in (REPO_ROOT / "CHECKPOINT.md", REPO_ROOT / "REVIEW-v0.6.1.md"):
        text = path.read_text(encoding="utf-8")
        if path.name == "CHECKPOINT.md":
            text = re.sub(r"(\*\*STATUS:\*\*\s*`)\w+(?:_\w+)*(`)", rf"\g<1>{gate}\g<2>", text, count=1)
        else:
            text = re.sub(r"(`)SDXL_[A-Z0-9_]+(`\s+—\s+smoke)", rf"\g<1>{gate}\g<2>", text, count=1)
            text = re.sub(r"(O estado atual é `)[^`]+(`)", rf"\g<1>{gate}\g<2>", text, count=1)
        text = re.sub(r"`new_generation_started=(?:true|false)`", f"`new_generation_started={'true' if started else 'false'}`", text, count=1)
        text = re.sub(r"`new_generation_jobs=\d+`", f"`new_generation_jobs={jobs}`", text, count=1)
        path.write_text(text, encoding="utf-8")


def _workflow_qualification(client: ComfyUIClient, guide_name: str, identity_name: str) -> dict[str, Any]:
    node_info = client.node_info()
    inventory = {folder: client.list_models(folder) for folder in ("checkpoints", "controlnet", "ipadapter", "clip_vision")}
    available = {item for values in inventory.values() for item in values}
    checks = []
    for lane, workflow_id in WORKFLOWS.items():
        record = load_workflow(REPO_ROOT, workflow_id)
        if lane == "P":
            filenames = [None, guide_name]
        elif lane == "I":
            filenames = [identity_name]
        else:
            filenames = [identity_name, guide_name]
        bound = bind_workflow(record["api"], prompt=COMMON_PROMPT, negative_prompt=NEGATIVE_PROMPT, seed=SMOKE_SEED, width=WIDTH, height=HEIGHT, model_names=MODEL_NAMES, image_filenames=filenames)
        graph = validate_api_workflow(bound, node_info=node_info, model_names=available)
        checks.append({"lane": lane, "workflow_id": workflow_id, "template_sha256": record["sha256"], "bound_sha256": workflow_hash(bound), "graph": graph, "required_custom_nodes": record.get("custom_nodes_required", []), "model_names": {key: value for key, value in MODEL_NAMES.items() if isinstance(value, str)}, "direct_guide": lane in {"P", "PI"}, "r4_identity_only": lane in {"I", "PI"}, "previous_outputs": False})
    status = "SDXL_PROVIDER_WORKFLOW_VALID" if all(item["graph"]["live_valid"] for item in checks) else "SDXL_PROVIDER_WORKFLOW_GAP"
    result = {"schema_version": UGAS_VERSION, "status": status, "prompt_id": PROMPT_ID, "resolution": [WIDTH, HEIGHT], "prompt_sha256": hashlib.sha256(COMMON_PROMPT.encode()).hexdigest(), "negative_prompt_sha256": hashlib.sha256(NEGATIVE_PROMPT.encode()).hexdigest(), "anchor": {"path": ANCHOR_RELATIVE, "sha256": ANCHOR_SHA256, "revision_id": ANCHOR_REVISION_ID}, "guide": {"path": GUIDE_RELATIVE, "uploaded_name": guide_name}, "lanes": checks, "ipadapter_never_receives_skeleton": True, "controlnet_never_receives_r4_identity": True}
    _write(REPO_ROOT / "docs/evidence/sdxl-provider-workflow-qualification-v0.6.1.json", result)
    if status != "SDXL_PROVIDER_WORKFLOW_VALID":
        raise RuntimeError(status)
    return result


def _technical_error(error: Exception) -> bool:
    text = str(error).casefold()
    return any(token in text for token in ("out of memory", "cuda out of memory", "oom", "memoryerror", "vram"))


def _raw_pose_qa(
    raw: Path,
    *,
    lane: str,
    seed: int,
    stage: str,
    job_dir: Path,
    guide_points: dict[str, tuple[float, float]],
    thresholds: dict[str, Any],
) -> dict[str, Any] | None:
    if lane not in {"P", "PI"}:
        return None
    policy = "raw_rgb_neutral_gray"
    prepared = prepare_preprocessed_image(raw, policy, job_dir / "raw-pose-preprocess.png")
    model_path = Path(_default_model_path())
    if not model_path.is_file():
        raise RuntimeError("POSE_QA_ESTIMATOR_MODEL_MISSING")
    with _landmarker(model_path) as (mp, detector):
        detection = _detect_with_landmarker(Path(prepared["path"]), mp, detector)
    orientation = _infer_orientation(detection["landmarks"])
    pose = detected_joint_pose_metrics(guide_points, detection["landmarks"], target_orientation="left_profile", detected_orientation=orientation)
    absolute = bool(
        pose["qualifies"]
        and pose["measurable_body_joints"] >= thresholds["absolute_pose"]["measurable_body_joints_min"]
        and pose["pck_at_010"] >= thresholds["absolute_pose"]["pck_at_010_min"]
        and pose["nme"] <= thresholds["absolute_pose"]["nme_max"]
        and pose["limb_angle_mae_degrees"] <= thresholds["absolute_pose"]["limb_angle_mae_max_degrees"]
        and pose["lower_body_pck"] >= thresholds["absolute_pose"]["lower_body_pck_min"]
        and pose["orientation_match"]
    )
    overlay = job_dir / "raw-pose-overlay.png"
    _draw_overlay(
        Path(prepared["path"]),
        detection["landmarks"],
        prepared["alpha_bbox_normalized"],
        f"{lane} seed {seed} raw",
        overlay,
        f"pck={pose['pck_at_010']:.3f} nme={pose['nme']:.3f}",
    )
    permanent_overlay = PERMANENT_ROOT / "overlays" / f"{stage}-raw.png"
    permanent_overlay.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(overlay, permanent_overlay)
    return {
        "status": "RAW_POSE_PASS" if absolute else "RAW_POSE_FAILED",
        "preprocess_policy": policy,
        "preprocess": prepared,
        "detection": {key: detection.get(key) for key in ("detected", "measurable_body_joints", "core_coverage", "mean_confidence", "min_confidence")},
        "detected_orientation": orientation,
        "pose": pose,
        "absolute_pose_pass": absolute,
        "overlay_path": _relative(permanent_overlay),
        "raw_output_sha256": sha256(raw),
    }


def _run_one(client: ComfyUIClient, *, lane: str, seed: int, anchor: Path, guide: Path, guide_value: dict[str, Any], guide_points: dict[str, tuple[float, float]], thresholds: dict[str, Any], control_strength: float = 0.9, ip_strength: float = 0.8, stage: str) -> dict[str, Any]:
    workflow_id = WORKFLOWS[lane]
    record = load_workflow(REPO_ROOT, workflow_id)
    uploads = []
    identity_name = None
    guide_name = None
    if lane in {"I", "PI"}:
        uploads.append(client.upload_image(anchor))
        identity_name = uploads[-1].get("name") or uploads[-1].get("filename")
    if lane in {"P", "PI"}:
        uploads.append(client.upload_image(guide))
        guide_name = uploads[-1].get("name") or uploads[-1].get("filename")
    if lane == "P":
        filenames = [None, guide_name]
    elif lane == "I":
        filenames = [identity_name]
    else:
        filenames = [identity_name, guide_name]
    model_names = dict(MODEL_NAMES)
    model_names["__CONTROLNET_STRENGTH__"] = control_strength
    model_names["__IP_STRENGTH__"] = ip_strength
    workflow = bind_workflow(record["api"], prompt=COMMON_PROMPT, negative_prompt=NEGATIVE_PROMPT, seed=seed, width=WIDTH, height=HEIGHT, model_names=model_names, image_filenames=filenames)
    graph = validate_api_workflow(workflow, node_info=client.node_info(), model_names={name for folder in ("checkpoints", "controlnet", "ipadapter", "clip_vision") for name in client.list_models(folder)})
    if not graph["live_valid"]:
        raise RuntimeError(f"workflow graph invalid: {graph}")
    job_dir = _unique_job_dir(REPO_ROOT, OUTPUT_ROOT, stage)
    input_hashes = {"canonical_anchor_sha256": sha256(anchor) if lane in {"I", "PI"} else None, "openpose_guide_image_sha256": sha256(guide) if lane in {"P", "PI"} else None, "openpose_guide_json_sha256": hashlib.sha256(json.dumps(guide_value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    context = {"prompt_id": PROMPT_ID, "phase": "SDXL_CONTROL_POSE_PROVIDER_SMOKE_CORRECTION", "factorial_lane": lane, "controlnet_strength": control_strength if lane in {"P", "PI"} else None, "ipadapter_weight": ip_strength if lane in {"I", "PI"} else None, "controlnet_start": 0.0, "controlnet_end": 1.0, "ipadapter_start": 0.0, "ipadapter_end": 1.0, "ipadapter_weight_type": "linear", "canonical_anchor_revision_id": ANCHOR_REVISION_ID, "canonical_anchor_sha256": ANCHOR_SHA256, "guide_json_sha256": input_hashes["openpose_guide_json_sha256"], "previous_frame_chaining": False, "previous_outputs": False}
    result, outputs = _run_job(REPO_ROOT, client, workflow, output_dir=job_dir, filename=f"{stage}.png", profile="generic-2d", capability="sdxl-provider-qualification", workflow_id=workflow_id, model_id="sdxl-base-1.0", prompt=COMMON_PROMPT, seed=seed, width=WIDTH, height=HEIGHT, input_hashes=input_hashes, qualification_context=context, seed_was_used_before=False, workflow_sha256=workflow_hash(workflow))
    raw = Path(outputs[0]["path"])
    execution = result["job"].get("execution_evidence", {})
    fresh = bool(
        execution.get("fresh_binding") is True
        and execution.get("history_key_matches_prompt_id") is True
        and execution.get("target_existed_before_submission") is False
        and execution.get("seed_was_used_before") is False
        and context["previous_frame_chaining"] is False
    )
    raw_destination = RAW_ROOT / f"{stage}.png"
    raw_destination.parent.mkdir(parents=True, exist_ok=True)
    raw_existed = raw_destination.exists()
    if raw_existed:
        raise RuntimeError("RAW_OUTPUT_STALE_TARGET")
    shutil.copy2(raw, raw_destination)
    raw_hash = sha256(raw_destination)
    generation = {
        "submitted": True,
        "completed": True,
        "prompt_id": execution.get("prompt_id"),
        "history_record_key": execution.get("history_record_key"),
        "history_key_matches_prompt_id": execution.get("history_key_matches_prompt_id") is True,
        "fresh_binding": fresh,
        "target_existed_before_submission": execution.get("target_existed_before_submission"),
        "previous_frame_chaining": context["previous_frame_chaining"],
        "raw_output_path": _relative(raw_destination),
        "raw_output_sha256": raw_hash,
        "raw_output_bytes": raw_destination.stat().st_size,
        "raw_output_hash_matches_comfy": raw_hash == (execution.get("outputs") or [{}])[0].get("data_sha256"),
        "execution_evidence": execution,
    }
    raw_pose: dict[str, Any] | None
    try:
        raw_pose = _raw_pose_qa(raw_destination, lane=lane, seed=seed, stage=stage, job_dir=job_dir, guide_points=guide_points, thresholds=thresholds)
    except Exception as exc:
        raw_pose = {
            "status": "RAW_POSE_QA_FAILED",
            "preprocess_policy": "raw_rgb_neutral_gray",
            "absolute_pose_pass": False,
            "failure_reasons": [f"{type(exc).__name__}: {exc}"],
            "raw_output_sha256": raw_hash,
        }
    record_base: dict[str, Any] = {
        "schema_version": UGAS_VERSION,
        "lane": lane,
        "seed": seed,
        "stage": stage,
        "workflow_id": workflow_id,
        "workflow_template_sha256": record["sha256"],
        "workflow_bound_sha256": workflow_hash(workflow),
        "controlnet_strength": control_strength if lane in {"P", "PI"} else None,
        "ipadapter_weight": ip_strength if lane in {"I", "PI"} else None,
        "generation": generation,
        "raw_output_path": _relative(raw_destination),
        "raw_output_sha256": raw_hash,
        "raw_pose_qa": raw_pose,
        "postprocess": {"attempted": False, "passed": False, "error": None},
        "identity_qa": None,
        "output_path": None,
        "output_sha256": None,
        "execution_evidence": execution,
        "fresh_binding": fresh,
        "technical_pass": False,
    }
    # This snapshot is written before BiRefNet so a later exception cannot erase
    # the generation binding or the raw PNG from the machine-readable evidence.
    _write(PERMANENT_ROOT / "execution" / f"{stage}.json", record_base)
    postprocess = record_base["postprocess"]
    postprocess["attempted"] = True
    try:
        transparent = background_remove(REPO_ROOT, str(raw_destination), endpoint=client.base_url, output_dir=job_dir / "background-removal", promote=False, evidence_prefix=f"sdxl-{stage}")
        final = Path(transparent["output"])
        final_qa = _load_transparent_qa(final)
        if final_qa.get("status") != "TECHNICAL_VALID":
            raise RuntimeError(f"technical transparency QA failed: {final_qa}")
        postprocess.update({"passed": True, "status": "POSTPROCESS_PASSED", "birefnet": transparent})
    except Exception as exc:
        postprocess.update({"passed": False, "status": "POSTPROCESS_FAILED", "error": f"{type(exc).__name__}: {exc}"})
        record_base.update({"final_stage_status": "POSTPROCESS_FAILED", "status": "POSTPROCESS_FAILED"})
        _write(PERMANENT_ROOT / "execution" / f"{stage}.json", record_base)
        return record_base

    permanent = PERMANENT_ROOT / "outputs" / f"{stage}.png"
    permanent.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final, permanent)
    identity = _identity_descriptor(final, anchor) if lane in {"I", "PI"} else None
    foreground = analyze_foreground_components(final) if identity is not None else None
    identity_qa = evaluate_identity_hard_gates(identity, foreground) if identity is not None and foreground is not None else None
    identity_pass = bool(identity_qa and identity_qa["identity_pass"])
    pose = raw_pose.get("pose") if raw_pose else None
    absolute = bool(raw_pose and raw_pose.get("absolute_pose_pass")) if lane in {"P", "PI"} else True
    if lane in {"P", "PI"} and not absolute:
        final_stage_status = "RAW_POSE_FAILED"
    elif lane in {"I", "PI"} and not identity_pass:
        final_stage_status = "IDENTITY_FAILED"
    else:
        final_stage_status = "SMOKE_PASSED"
    technical_pass = bool(fresh and postprocess["passed"] and absolute and (lane == "P" or identity_pass))
    result = {
        **record_base,
        "output_path": _relative(permanent),
        "output_sha256": sha256(permanent),
        "output_png": inspect_png(permanent),
        "pose": pose,
        "identity": identity,
        "identity_qa": identity_qa,
        "absolute_pose_pass": absolute,
        "identity_pass": identity_pass if lane in {"I", "PI"} else None,
        "weapon_present": bool(identity.get("weapon_present")) if identity else None,
        "technical_pass": technical_pass,
        "final_stage_status": final_stage_status,
        "status": final_stage_status,
        "runtime_ms": execution.get("runtime_ms"),
    }
    _write(PERMANENT_ROOT / "execution" / f"{stage}.json", result)
    return result


def _load_transparent_qa(path: Path) -> dict[str, Any]:
    from ugas.qa import validate_output
    return validate_output(path, width=WIDTH, height=HEIGHT, requires_transparency=True)


def _failure_record(lane: str, seed: int, stage: str, error: Exception, *, technical: bool = False) -> dict[str, Any]:
    return {
        "schema_version": UGAS_VERSION,
        "lane": lane,
        "seed": seed,
        "stage": stage,
        "status": "GENERATION_FAILED",
        "final_stage_status": "GENERATION_FAILED",
        "generation": {
            "submitted": False,
            "completed": False,
            "prompt_id": None,
            "history_record_key": None,
            "history_key_matches_prompt_id": False,
            "fresh_binding": False,
            "raw_output_path": None,
            "raw_output_sha256": None,
        },
        "raw_pose_qa": None,
        "postprocess": {"attempted": False, "passed": False, "error": None},
        "identity_qa": None,
        "technical_pass": technical,
        "error": f"{type(error).__name__}: {error}",
        "absolute_pose_pass": False,
        "identity_pass": False,
        "weapon_present": False,
        "fresh_binding": False,
        "execution_evidence": {},
    }


def _release_runtime(client: ComfyUIClient) -> None:
    """Keep sequential model unload/offload explicit between qualification jobs."""
    try:
        client.free_memory(unload_models=True, free_memory=True)
    except Exception:
        # The job result remains authoritative; inability to release memory is
        # recorded by the next technical attempt rather than masking it here.
        pass


def _contact(records: list[dict[str, Any]], filename: str) -> str | None:
    items = [(REPO_ROOT / item["output_path"], item) for item in records if item.get("output_path") and (REPO_ROOT / item["output_path"]).is_file()]
    if not items:
        return None
    destination = OUTPUT_ROOT / filename
    paths = [path for path, _ in items]
    labels = [f"{item['lane']} seed={item['seed']} pose={item.get('pose', {}).get('pose_score', 0.0):.3f} id={item.get('identity', {}).get('identity_descriptor_score', 0.0):.3f}" for _, item in items]
    sheet = _contact_sheet(paths, labels, destination, columns=3)
    permanent = REPO_ROOT / "docs" / "evidence" / filename
    shutil.copy2(destination, permanent)
    return _relative(permanent)


def _summaries(records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for lane in WORKFLOWS:
        items = [item for item in records if item.get("lane") == lane]
        scored = [item for item in items if item.get("technical_pass") and item.get("pose") and item.get("identity")]
        poses = [float(item["pose"].get("pose_score", 0.0)) for item in scored]
        identities = [float(item["identity"].get("identity_descriptor_score", 0.0)) for item in scored]
        result[lane] = {"records": len(items), "scored": len(scored), "technical_all_pass": len(items) > 0 and len(scored) == len(items), "absolute_pose_all_pass": len(items) == 3 and all(item.get("absolute_pose_pass") for item in items), "identity_weapon_all_pass": len(items) == 3 and all(item.get("identity_pass") and item.get("weapon_present") for item in items), "fresh_all_pass": len(items) == 3 and all(item.get("fresh_binding") for item in items), "pose_median": round(median(poses), 6) if poses else 0.0, "identity_median": round(median(identities), 6) if identities else 0.0, "pose_error_median": round(1.0 - median(poses), 6) if poses else 1.0, "identity_min": round(min(identities), 6) if identities else 0.0}
    return result


def _causal(summaries: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    p, i, pi = summaries["P"], summaries["I"], summaries["PI"]
    pose_reduction = (i["pose_error_median"] - pi["pose_error_median"]) / max(1e-9, i["pose_error_median"])
    pose_headroom = (pi["pose_median"] - i["pose_median"]) / max(1e-9, 1.0 - i["pose_median"])
    identity_gain = (pi["identity_median"] - p["identity_median"]) / max(1e-9, 1.0 - p["identity_median"])
    required_reduction = float(thresholds["causal"]["relative_joint_error_reduction_min"])
    required_headroom = float(thresholds["causal"]["normalized_score_gain_min"])
    return {"pose_PI_error_reduction_vs_I": round(pose_reduction, 6), "pose_PI_normalized_headroom_vs_I": round(pose_headroom, 6), "identity_PI_relative_gain_vs_P": round(identity_gain, 6), "relative_joint_error_reduction_min_reused": required_reduction, "normalized_score_gain_min_reused": required_headroom, "pose_causal_pass": bool(pose_reduction >= required_reduction and pose_headroom >= required_headroom), "identity_causal_pass": bool(identity_gain >= required_reduction and pi["identity_median"] > p["identity_median"]), "absolute_gates_required": True, "thresholds_changed": False}


def _benchmark(client: ComfyUIClient, anchor: Path, guide: Path, guide_value: dict[str, Any], guide_points: dict[str, tuple[float, float]], thresholds: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    configs = ((0.8, 0.7), (0.8, 0.9), (1.0, 0.7), (1.0, 0.9))
    records = []
    for index, (control, ip) in enumerate(configs, 1):
        stage = f"benchmark-pi-c{control:.1f}-i{ip:.1f}-seed-{BENCHMARK_SEED}"
        try:
            records.append(_run_one(client, lane="PI", seed=BENCHMARK_SEED, anchor=anchor, guide=guide, guide_value=guide_value, guide_points=guide_points, thresholds=thresholds, control_strength=control, ip_strength=ip, stage=stage))
        except Exception as exc:
            records.append(_failure_record("PI", BENCHMARK_SEED, stage, exc))
        finally:
            _release_runtime(client)
    valid = [item for item in records if item.get("technical_pass") and item.get("pose") and item.get("identity")]
    ranked = sorted(valid, key=lambda item: (float(item["pose"].get("pose_score", 0.0)), float(item["identity"].get("identity_descriptor_score", 0.0)), int(item.get("weapon_present", False)), float(item["pose"].get("lower_body_pck", 0.0)), -float(item["pose"].get("nme", 1.0)), -float(item.get("runtime_ms") or 1e12)), reverse=True)
    ranking = [{"rank": index, "stage": item["stage"], "controlnet_strength": item.get("controlnet_strength"), "ipadapter_weight": item.get("ipadapter_weight"), "pose_score": item["pose"].get("pose_score"), "identity_score": item["identity"].get("identity_descriptor_score"), "weapon_present": item.get("weapon_present"), "lower_body_pck": item["pose"].get("lower_body_pck"), "nme": item["pose"].get("nme"), "runtime_ms": item.get("runtime_ms")} for index, item in enumerate(ranked, 1)]
    result = {"schema_version": UGAS_VERSION, "status": "SDXL_STRENGTH_BENCHMARK_COMPLETED" if len(valid) == 4 else "SDXL_STRENGTH_BENCHMARK_GAP", "seed": BENCHMARK_SEED, "fixed_start_end": {"controlnet": [0.0, 1.0], "ipadapter": [0.0, 1.0]}, "ipadapter_weight_type": "linear", "configs": [{"controlnet_strength": c, "ipadapter_weight": i} for c, i in configs], "ranking_rule": ["pose", "identity", "weapon", "lower_body", "nme", "runtime"], "ranking": ranking, "records": records, "winner": ranking[0] if ranking else None, "seed_not_used_for_ranking": True}
    _write(REPO_ROOT / "docs/evidence/sdxl-strength-benchmark.json", result)
    return records, result, _contact(records, "sdxl-strength-benchmark-contact-sheet.png")


def _execution(records: list[dict[str, Any]], status: str) -> dict[str, Any]:
    executions = [item.get("execution_evidence", {}) for item in records if item.get("execution_evidence")]
    return {"schema_version": UGAS_VERSION, "status": status, "prompt_id": PROMPT_ID, "records": executions, "attempted_record_count": len(records), "completed_execution_count": len(executions), "all_prompt_ids_present": len(executions) == len(records) and all(bool(item.get("prompt_id")) for item in executions), "all_history_bindings_exact": len(executions) == len(records) and all(item.get("history_key_matches_prompt_id") is True for item in executions), "stale_output_rejected": len(executions) == len(records) and all(item.get("target_existed_before_submission") is False for item in executions), "previous_frame_chaining": False, "weights_in_git": False, "custom_node_source_vendored": False}


def _provider_status(records: list[dict[str, Any]], *, qualified: bool, doctor: dict[str, Any]) -> str:
    if qualified:
        return "SDXL_CONTROL_POSE_PROVIDER_QUALIFIED"
    errors = [str(item.get("error", "")) for item in records]
    if any(_technical_error(RuntimeError(error)) for error in errors):
        return "SDXL_CONTROL_PROVIDER_HARDWARE_GAP"
    by_lane = {lane: any(item.get("technical_pass") for item in records if item.get("lane") == lane) for lane in WORKFLOWS}
    if by_lane["P"] and not by_lane["I"]:
        return "SDXL_IDENTITY_ADAPTER_GAP"
    if by_lane["I"] and not by_lane["P"]:
        return "SDXL_OPENPOSE_CONTROL_GAP"
    return "SDXL_CONTROL_POSE_PROVIDER_GAP"


def run(endpoint: str = ENDPOINT) -> dict[str, Any]:
    thresholds = _thresholds()
    audit = _audit()
    model_qualification = _model_qualification()
    doctor = _runtime()
    anchor = REPO_ROOT / ANCHOR_RELATIVE
    guide = REPO_ROOT / GUIDE_RELATIVE
    guide_value = _read(REPO_ROOT / GUIDE_JSON_RELATIVE)
    guide_points = _guide_points(guide_value)
    if sha256(anchor) != ANCHOR_SHA256:
        raise RuntimeError("canonical R4 anchor hash mismatch")
    if not anchor.is_file() or not guide.is_file():
        raise RuntimeError("canonical anchor or direct guide is missing")
    client = ComfyUIClient(endpoint, timeout=90.0)
    identity_upload = client.upload_image(anchor)
    guide_upload = client.upload_image(guide)
    identity_name = identity_upload.get("name") or identity_upload.get("filename")
    guide_name = guide_upload.get("name") or guide_upload.get("filename")
    workflow_evidence = _workflow_qualification(client, str(guide_name), str(identity_name))
    _replace_current_docs("SDXL_P_I_PI_SMOKE_REQUIRED", started=False, jobs=0)
    _state_update("SDXL_P_I_PI_SMOKE_REQUIRED", started=False, jobs=0)
    records: list[dict[str, Any]] = []
    for lane in ("P", "I", "PI"):
        stage = f"smoke-{lane.lower()}-seed-{SMOKE_SEED}"
        try:
            records.append(_run_one(client, lane=lane, seed=SMOKE_SEED, anchor=anchor, guide=guide, guide_value=guide_value, guide_points=guide_points, thresholds=thresholds, stage=stage))
        except Exception as exc:
            records.append(_failure_record(lane, SMOKE_SEED, stage, exc))
        finally:
            _release_runtime(client)
    smoke_technical_green = len(records) == 3 and all(item.get("technical_pass") for item in records)
    smoke_contact = _contact(records, "sdxl-p-i-pi-smoke-contact-sheet.png")
    total_attempted = len(records)
    paired_records: list[dict[str, Any]] = []
    benchmark_records: list[dict[str, Any]] = []
    benchmark: dict[str, Any] = {"status": "NOT_RUN", "winner": None}
    benchmark_contact = None
    confirmation_records: list[dict[str, Any]] = []
    if smoke_technical_green:
        _replace_current_docs("SDXL_STRENGTH_BENCHMARK_REQUIRED", started=True, jobs=total_attempted)
        _state_update("SDXL_STRENGTH_BENCHMARK_REQUIRED", started=True, jobs=total_attempted)
        for lane in ("P", "I", "PI"):
            for seed in PAIRED_SEEDS:
                stage = f"paired-{lane.lower()}-seed-{seed}"
                try:
                    paired_records.append(_run_one(client, lane=lane, seed=seed, anchor=anchor, guide=guide, guide_value=guide_value, guide_points=guide_points, thresholds=thresholds, stage=stage))
                except Exception as exc:
                    paired_records.append(_failure_record(lane, seed, stage, exc))
                finally:
                    _release_runtime(client)
        total_attempted += len(paired_records)
        benchmark_records, benchmark, benchmark_contact = _benchmark(client, anchor, guide, guide_value, guide_points, thresholds)
        total_attempted += len(benchmark_records)
        all_records = records + paired_records + benchmark_records
        paired_summary = _summaries(paired_records)
        causal = _causal(paired_summary, thresholds)
        pair_qualification = bool(paired_summary["PI"]["absolute_pose_all_pass"] and paired_summary["PI"]["identity_weapon_all_pass"] and paired_summary["PI"]["fresh_all_pass"] and causal["pose_causal_pass"] and causal["identity_causal_pass"])
        _write(REPO_ROOT / "docs/evidence/sdxl-paired-qualification.json", {"schema_version": UGAS_VERSION, "status": "SDXL_PAIRED_QUALIFICATION_GREEN" if pair_qualification else "SDXL_PAIRED_QUALIFICATION_GAP", "seeds": list(PAIRED_SEEDS), "summaries": paired_summary, "causal": causal, "records": paired_records, "absolute_thresholds_reused": thresholds["absolute_pose"], "identity_weapon_thresholds_reused": thresholds["identity_weapon"]})
        if pair_qualification and benchmark.get("winner"):
            _replace_current_docs("SDXL_POSE_PROVIDER_CONFIRMATION_REQUIRED", started=True, jobs=total_attempted)
            _state_update("SDXL_POSE_PROVIDER_CONFIRMATION_REQUIRED", started=True, jobs=total_attempted)
            winner = benchmark["winner"]
            for seed in CONFIRMATION_SEEDS:
                stage = f"confirmation-pi-c{winner['controlnet_strength']:.1f}-i{winner['ipadapter_weight']:.1f}-seed-{seed}"
                try:
                    confirmation_records.append(_run_one(client, lane="PI", seed=seed, anchor=anchor, guide=guide, guide_value=guide_value, guide_points=guide_points, thresholds=thresholds, control_strength=float(winner["controlnet_strength"]), ip_strength=float(winner["ipadapter_weight"]), stage=stage))
                except Exception as exc:
                    confirmation_records.append(_failure_record("PI", seed, stage, exc))
                finally:
                    _release_runtime(client)
            total_attempted += len(confirmation_records)
    all_qualification_records = records + paired_records + benchmark_records + confirmation_records
    overlays = [item for item in all_qualification_records if item.get("overlay_path")]
    overlay_contact = None
    if overlays:
        overlay_paths = [REPO_ROOT / item["overlay_path"] for item in overlays if (REPO_ROOT / item["overlay_path"]).is_file()]
        labels = [f"{item['lane']} seed={item['seed']} joints={item.get('pose', {}).get('measurable_body_joints', 0)} pck={item.get('pose', {}).get('pck_at_010', 0.0):.3f}" for item in overlays if (REPO_ROOT / item["overlay_path"]).is_file()]
        destination = OUTPUT_ROOT / "sdxl-pose-detection-overlays-contact-sheet.png"
        _contact_sheet(overlay_paths, labels, destination, columns=3)
        permanent = REPO_ROOT / "docs/evidence/sdxl-pose-detection-overlays-contact-sheet.png"
        shutil.copy2(destination, permanent)
        overlay_contact = _relative(permanent)
    identity_table = {"schema_version": UGAS_VERSION, "metric": "identity_descriptor_v1 + regional hard gates", "canonical_anchor_sha256": ANCHOR_SHA256, "records": [{"lane": item.get("lane"), "seed": item.get("seed"), "identity": item.get("identity"), "identity_pass": item.get("identity_pass"), "weapon_present": item.get("weapon_present"), "output_path": item.get("output_path")} for item in all_qualification_records if item.get("identity")], "regions": ["head_face", "armor_palette_material", "black_cloth", "body_proportions", "weapon_presence"]}
    _write(REPO_ROOT / "docs/evidence/sdxl-identity-drift-contact.json", identity_table)
    summaries = _summaries(paired_records if paired_records else records)
    causal = _causal(summaries, thresholds) if paired_records else {"pose_causal_pass": False, "identity_causal_pass": False, "reason": "paired qualification not reached"}
    confirmation_green = len(confirmation_records) == 3 and all(item.get("absolute_pose_pass") and item.get("identity_pass") and item.get("weapon_present") and item.get("fresh_binding") for item in confirmation_records)
    qualified = bool(smoke_technical_green and benchmark.get("winner") and len(paired_records) == 9 and summaries["PI"]["absolute_pose_all_pass"] and summaries["PI"]["identity_weapon_all_pass"] and summaries["PI"]["fresh_all_pass"] and causal.get("pose_causal_pass") and causal.get("identity_causal_pass") and confirmation_green)
    status = _provider_status(all_qualification_records, qualified=qualified, doctor=doctor)
    execution = _execution(all_qualification_records, status)
    _write(REPO_ROOT / "docs/evidence/execution-evidence-v0.6.0.json", execution)
    provider = {"schema_version": UGAS_VERSION, "status": status, "prompt_id": PROMPT_ID, "phase": "SDXL_CONTROL_POSE_PROVIDER_QUALIFICATION", "answer": "SDXL + native OpenPose ControlNet + IP-Adapter can only be considered pose-and-identity capable here if the combined PI lane passes all absolute, identity/weapon, fresh-execution and causal gates.", "audit": audit, "model_qualification": model_qualification, "runtime_doctor": doctor, "workflow_qualification": workflow_evidence, "anchor": {"path": ANCHOR_RELATIVE, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "guide": {"path": GUIDE_RELATIVE, "json_path": GUIDE_JSON_RELATIVE, "image_sha256": sha256(guide), "json_sha256": input_hashes_hash(guide_value)}, "thresholds": {"source": "docs/evidence/pose-thresholds-v054.json", "schema_version": thresholds["schema_version"], "changed": False, "absolute": thresholds["absolute_pose"], "causal": thresholds["causal"], "identity_weapon": thresholds["identity_weapon"]}, "seeds": {"smoke": SMOKE_SEED, "paired": list(PAIRED_SEEDS), "benchmark": BENCHMARK_SEED, "confirmation": list(CONFIRMATION_SEEDS)}, "smoke": {"technical_green": smoke_technical_green, "records": records, "contact_sheet": smoke_contact}, "paired": {"records": paired_records, "summaries": summaries, "causal": causal}, "benchmark": benchmark, "benchmark_contact_sheet": benchmark_contact, "confirmation": {"records": confirmation_records, "green": confirmation_green}, "pose_overlay_contact_sheet": overlay_contact, "identity_drift_table": "docs/evidence/sdxl-identity-drift-contact.json", "execution_evidence": "docs/evidence/execution-evidence-v0.6.0.json", "walk_authorized": False, "animation_authorized": False, "production_approval": "not-granted", "external_approval": "not-claimed", "new_generation_jobs": total_attempted}
    _write(REPO_ROOT / "docs/evidence/sdxl-provider-qualification.json", provider)
    _write(REPO_ROOT / "docs/evidence/review-visuals-v0.6.0.json", _visual_manifest(provider, all_qualification_records))
    _replace_current_docs(status, started=total_attempted > 0, jobs=total_attempted)
    _state_update(status, started=total_attempted > 0, jobs=total_attempted, stop_reason=None if qualified else status)
    return provider


def input_hashes_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _visual_manifest(provider: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    names = ["sdxl-p-i-pi-smoke-contact-sheet.png", "sdxl-strength-benchmark-contact-sheet.png", "sdxl-pose-detection-overlays-contact-sheet.png", "sdxl-identity-drift-contact.json"]
    required_current: list[str] = []
    if provider.get("smoke", {}).get("technical_green") is True:
        required_current.append("sdxl-p-i-pi-smoke-contact-sheet.png")
    if any(item.get("output_path") for item in records):
        required_current.extend(["sdxl-pose-detection-overlays-contact-sheet.png", "sdxl-identity-drift-contact.json"])
    if provider.get("benchmark", {}).get("status") != "NOT_RUN":
        required_current.append("sdxl-strength-benchmark-contact-sheet.png")
    entries = []
    historical_path = REPO_ROOT / "docs/evidence/review-visuals-v0.5.5.json"
    if historical_path.is_file():
        for item in _read(historical_path).get("images", []):
            if isinstance(item, dict) and item.get("source_path") and (REPO_ROOT / str(item["source_path"])).is_file():
                entries.append({"archive_name": item["archive_name"], "source_path": item["source_path"], "revision_id": item.get("revision_id", "historical-v0.5.5"), "sha256": _review_digest(REPO_ROOT / str(item["source_path"]))})
    for name in names:
        path = REPO_ROOT / "docs/evidence" / name
        if path.is_file():
            entries.append({"archive_name": name, "source_path": _relative(path), "revision_id": "v0.6.0", "sha256": _review_digest(path)})
    for item in records:
        relative = item.get("output_path")
        if relative and (REPO_ROOT / relative).is_file():
            archive_name = Path(relative).name
            entries.append({"archive_name": archive_name, "source_path": relative, "revision_id": "v0.6.0", "sha256": _review_digest(REPO_ROOT / relative)})
    return {"schema_version": UGAS_VERSION, "manifest_type": "review-visual-evidence", "review_state": "sdxl-provider-qualification", "images": entries, "required_current_visuals": sorted(set(required_current)), "renderer_version": "sdxl-provider-v0.6.0", "human_visual_review": "required", "production_approval": "not-granted", "provider_status": provider.get("status")}


def _execution_v061(records: list[dict[str, Any]], status: str) -> dict[str, Any]:
    generation_records = [{"lane": item.get("lane"), "seed": item.get("seed"), "generation": item.get("generation", {})} for item in records]
    completed = [item for item in generation_records if item["generation"].get("completed") is True]
    all_prompt_ids = bool(completed) and len(completed) == len(generation_records) and all(bool(item["generation"].get("prompt_id")) for item in completed)
    all_history = bool(completed) and len(completed) == len(generation_records) and all(item["generation"].get("history_key_matches_prompt_id") is True for item in completed)
    all_raw = bool(completed) and len(completed) == len(generation_records) and all(bool(item["generation"].get("raw_output_path")) and bool(item["generation"].get("raw_output_sha256")) and item["generation"].get("raw_output_hash_matches_comfy") is True for item in completed)
    all_fresh = bool(completed) and len(completed) == len(generation_records) and all(item["generation"].get("target_existed_before_submission") is False and item["generation"].get("fresh_binding") is True for item in completed)
    return {
        "schema_version": UGAS_VERSION,
        "status": status,
        "prompt_id": PROMPT_ID,
        "records": generation_records,
        "attempted_record_count": len(records),
        "generation_completed_count": len(completed),
        "completed_execution_count": len(completed),
        "all_prompt_ids_present": all_prompt_ids,
        "all_history_bindings_exact": all_history,
        "all_raw_outputs_hash_bound": all_raw,
        "all_targets_fresh": all_fresh,
        "stale_output_rejected": all_fresh,
        "previous_frame_chaining": False,
        "weights_in_git": False,
        "custom_node_source_vendored": False,
    }


def _record_paths_v061(records: list[dict[str, Any]], key: str) -> list[tuple[Path, dict[str, Any]]]:
    result = []
    for item in records:
        value = item.get(key)
        if value:
            path = REPO_ROOT / str(value)
            if path.is_file():
                result.append((path, item))
    return result


def _contact_v061(records: list[dict[str, Any]], path_key: str, filename: str, label: str) -> str | None:
    items = _record_paths_v061(records, path_key)
    if not items:
        return None
    destination = OUTPUT_ROOT / filename
    labels = [f"{item.get('lane')} seed={item.get('seed')} {label}" for _, item in items]
    _contact_sheet([path for path, _ in items], labels, destination, columns=3)
    permanent = REPO_ROOT / "docs" / "evidence" / filename
    permanent.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(destination, permanent)
    return _relative(permanent)


def _raw_pose_contact_v061(records: list[dict[str, Any]], filename: str) -> str | None:
    items = []
    for item in records:
        raw_pose = item.get("raw_pose_qa") or {}
        if raw_pose.get("overlay_path"):
            items.append({**item, "raw_pose_overlay_path": raw_pose["overlay_path"]})
    return _contact_v061(items, "raw_pose_overlay_path", filename, "raw pose")


def _provider_status_v061(records: list[dict[str, Any]], *, smoke_green: bool) -> str:
    errors = [str(item.get("error", "")) + " " + str((item.get("postprocess") or {}).get("error", "")) for item in records]
    if any(_technical_error(RuntimeError(error)) for error in errors):
        return "SDXL_CONTROL_PROVIDER_HARDWARE_GAP"
    by_lane = {lane: next((item for item in records if item.get("lane") == lane), {}) for lane in WORKFLOWS}
    p_pose = bool((by_lane["P"].get("raw_pose_qa") or {}).get("absolute_pose_pass"))
    pi_pose = bool((by_lane["PI"].get("raw_pose_qa") or {}).get("absolute_pose_pass"))
    p_post = (by_lane["P"].get("postprocess") or {}).get("passed") is True
    if p_pose and not p_post:
        return "SDXL_POSTPROCESS_GAP"
    if not p_pose and not pi_pose:
        return "SDXL_OPENPOSE_CONTROL_GAP"
    if p_pose and not pi_pose:
        return "SDXL_COMBINED_CONDITIONING_INTERFERENCE_GAP"
    if (by_lane["I"].get("identity_qa") or {}).get("identity_pass") is False:
        return "SDXL_IDENTITY_ADAPTER_GAP"
    if (by_lane["PI"].get("identity_qa") or {}).get("identity_pass") is False:
        return "SDXL_COMBINED_IDENTITY_GAP"
    if smoke_green:
        return "SDXL_SMOKE_GREEN_READY_FOR_BENCHMARK_PROMPT"
    return "SDXL_OPENPOSE_CONTROL_GAP"


def _run_v061(endpoint: str = ENDPOINT, *, smoke_only: bool = True, seed: int = SMOKE_SEED) -> dict[str, Any]:
    if not smoke_only:
        raise RuntimeError("v0.6.1 permits only the corrective smoke")
    if seed != SMOKE_SEED:
        raise RuntimeError(f"v0.6.1 corrective smoke requires seed {SMOKE_SEED}")
    thresholds = _thresholds()
    audit = _audit()
    model_qualification = _model_qualification()
    doctor = _runtime()
    anchor = REPO_ROOT / ANCHOR_RELATIVE
    guide = REPO_ROOT / GUIDE_RELATIVE
    guide_value = _read(REPO_ROOT / GUIDE_JSON_RELATIVE)
    guide_points = _guide_points(guide_value)
    if not anchor.is_file() or sha256(anchor) != ANCHOR_SHA256:
        raise RuntimeError("canonical R4 anchor hash mismatch")
    if not guide.is_file():
        raise RuntimeError("canonical direct guide is missing")
    client = ComfyUIClient(endpoint, timeout=90.0)
    identity_upload = client.upload_image(anchor)
    guide_upload = client.upload_image(guide)
    identity_name = identity_upload.get("name") or identity_upload.get("filename")
    guide_name = guide_upload.get("name") or guide_upload.get("filename")
    workflow_evidence = _workflow_qualification(client, str(guide_name), str(identity_name))
    _replace_current_docs("SDXL_P_I_PI_SMOKE_REQUIRED", started=False, jobs=0)
    _state_update("SDXL_P_I_PI_SMOKE_REQUIRED", started=False, jobs=0)
    records: list[dict[str, Any]] = []
    for lane in ("P", "I", "PI"):
        stage = f"smoke-{lane.lower()}-seed-{seed}"
        try:
            item = _run_one(client, lane=lane, seed=seed, anchor=anchor, guide=guide, guide_value=guide_value, guide_points=guide_points, thresholds=thresholds, stage=stage)
        except Exception as exc:
            item = _failure_record(lane, seed, stage, exc)
        records.append(item)
        _write(EXECUTION_EVIDENCE_PATH, _execution_v061(records, "RUNNING"))
        _release_runtime(client)

    smoke_green = len(records) == 3 and all(item.get("technical_pass") is True for item in records)
    status = _provider_status_v061(records, smoke_green=smoke_green)
    raw_contact = _contact_v061(records, "raw_output_path", "sdxl-smoke-raw-p-i-pi-contact-sheet.png", "raw")
    raw_pose_contact = _raw_pose_contact_v061(records, "sdxl-smoke-raw-pose-overlays-contact-sheet.png")
    postprocessed_contact = _contact_v061(records, "output_path", "sdxl-smoke-postprocessed-contact-sheet.png", "processed")
    _write(REPO_ROOT / "docs/evidence/sdxl-smoke-phase-table.json", {
        "schema_version": UGAS_VERSION,
        "status": status,
        "lanes": [{"lane": item.get("lane"), "seed": item.get("seed"), "generation": item.get("generation"), "raw_pose_qa": item.get("raw_pose_qa"), "postprocess": item.get("postprocess"), "identity_qa": item.get("identity_qa"), "final_stage_status": item.get("final_stage_status")} for item in records],
    })
    _write(REPO_ROOT / "docs/evidence/sdxl-identity-hard-gates.json", {
        "schema_version": UGAS_VERSION,
        "status": "IDENTITY_HARD_GATES_RECORDED",
        "canonical_anchor_sha256": ANCHOR_SHA256,
        "records": [{"lane": item.get("lane"), "seed": item.get("seed"), "descriptor": item.get("identity"), "hard_gates": item.get("identity_qa"), "output_path": item.get("output_path")} for item in records if item.get("identity") is not None],
        "hard_gate_policy": {"aggregate_score_cannot_compensate": True, "required": ["aggregate_score", "weapon", "head_face", "armor_palette", "black_cloth", "body_proportions", "single_subject"]},
    })
    p_record = next((item for item in records if item.get("lane") == "P"), {})
    if (p_record.get("postprocess") or {}).get("passed") is False and (p_record.get("postprocess") or {}).get("attempted") is True:
        _write(REPO_ROOT / "docs/evidence/sdxl-p-postprocess-diagnostics.json", {"schema_version": UGAS_VERSION, "lane": "P", "status": "POSTPROCESS_GAP", "generation": p_record.get("generation"), "raw_pose_qa": p_record.get("raw_pose_qa"), "postprocess": p_record.get("postprocess")})
    execution = _execution_v061(records, status)
    _write(EXECUTION_EVIDENCE_PATH, execution)
    provider = {
        "schema_version": UGAS_VERSION,
        "status": status,
        "prompt_id": PROMPT_ID,
        "phase": "SDXL_CONTROL_POSE_PROVIDER_SMOKE_CORRECTION",
        "answer": "This release classifies only the corrected P/I/PI smoke. It does not authorize benchmark, confirmation, walk or animation.",
        "audit": audit,
        "model_qualification": model_qualification,
        "runtime_doctor": doctor,
        "workflow_qualification": workflow_evidence,
        "anchor": {"path": ANCHOR_RELATIVE, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256},
        "guide": {"path": GUIDE_RELATIVE, "json_path": GUIDE_JSON_RELATIVE, "image_sha256": sha256(guide), "json_sha256": input_hashes_hash(guide_value)},
        "thresholds": {"source": "docs/evidence/pose-thresholds-v054.json", "schema_version": thresholds["schema_version"], "changed": False, "absolute": thresholds["absolute_pose"], "causal": thresholds["causal"], "identity_weapon": thresholds["identity_weapon"]},
        "seeds": {"smoke": seed, "paired": [], "benchmark": None, "confirmation": []},
        "smoke": {"technical_green": smoke_green, "records": records, "raw_contact_sheet": raw_contact, "raw_pose_overlays_contact_sheet": raw_pose_contact, "postprocessed_contact_sheet": postprocessed_contact, "phase_table": "docs/evidence/sdxl-smoke-phase-table.json"},
        "paired": {"status": "NOT_RUN", "records": []},
        "benchmark": {"status": "NOT_RUN", "reason": "forbidden in v0.6.1"},
        "confirmation": {"status": "NOT_RUN", "records": [], "green": False},
        "identity_hard_gates": "docs/evidence/sdxl-identity-hard-gates.json",
        "p_postprocess_diagnostics": "docs/evidence/sdxl-p-postprocess-diagnostics.json" if (REPO_ROOT / "docs/evidence/sdxl-p-postprocess-diagnostics.json").is_file() else None,
        "execution_evidence": "docs/evidence/execution-evidence-v0.6.1.json",
        "walk_authorized": False,
        "anchors_authorized": False,
        "animation_authorized": False,
        "production_approval": "not-granted",
        "external_approval": "not-claimed",
        "new_generation_jobs": len(records),
    }
    _write(REPO_ROOT / "docs/evidence/sdxl-provider-qualification-v0.6.1.json", provider)
    _write(REPO_ROOT / "docs/evidence/review-visuals-v0.6.1.json", _visual_manifest_v061(provider, records))
    _replace_current_docs(status, started=bool(records), jobs=len(records))
    _state_update(status, started=bool(records), jobs=len(records), stop_reason=status)
    return provider


def _visual_manifest_v061(provider: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []

    def add(path: Path, archive_name: str | None = None, revision_id: str = "v0.6.1") -> None:
        if path.is_file():
            entries.append({"archive_name": archive_name or path.name, "source_path": _relative(path), "revision_id": revision_id, "sha256": _review_digest(path)})

    historical = REPO_ROOT / "docs/evidence/review-visuals-v0.5.5.json"
    if historical.is_file():
        for item in _read(historical).get("images", []):
            source = REPO_ROOT / str(item.get("source_path", ""))
            if source.is_file():
                add(source, str(item.get("archive_name") or source.name), str(item.get("revision_id") or "historical-v0.5.5"))
    for name in ("sdxl-smoke-raw-p-i-pi-contact-sheet.png", "sdxl-smoke-raw-pose-overlays-contact-sheet.png", "sdxl-smoke-postprocessed-contact-sheet.png", "sdxl-smoke-phase-table.json", "sdxl-identity-hard-gates.json", "sdxl-p-postprocess-diagnostics.json", "execution-evidence-v0.6.1.json"):
        add(REPO_ROOT / "docs/evidence" / name)
    for item in records:
        raw = item.get("raw_output_path")
        output = item.get("output_path")
        if raw:
            add(REPO_ROOT / str(raw))
        if output:
            add(REPO_ROOT / str(output))
    required = ["sdxl-smoke-raw-p-i-pi-contact-sheet.png", "sdxl-smoke-raw-pose-overlays-contact-sheet.png", "sdxl-smoke-phase-table.json", "sdxl-identity-hard-gates.json", "execution-evidence-v0.6.1.json"]
    if any(item.get("output_path") for item in records):
        required.append("sdxl-smoke-postprocessed-contact-sheet.png")
    if provider.get("p_postprocess_diagnostics"):
        required.append("sdxl-p-postprocess-diagnostics.json")
    return {"schema_version": UGAS_VERSION, "manifest_type": "review-visual-evidence", "review_state": "sdxl-smoke-correction", "images": entries, "required_current_visuals": sorted(set(required)), "renderer_version": "sdxl-provider-v0.6.1", "human_visual_review": "required", "production_approval": "not-granted", "provider_status": provider.get("status")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--seed", type=int, default=SMOKE_SEED)
    args = parser.parse_args()
    try:
        result = _run_v061(args.endpoint, smoke_only=True, seed=args.seed)
    except Exception as exc:
        print(f"SDXL_QUALIFICATION_BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "new_generation_jobs": result["new_generation_jobs"], "smoke_technical_green": result["smoke"]["technical_green"], "benchmark": result["benchmark"]["status"]}, indent=2))
    return 0 if result["status"] == "SDXL_SMOKE_GREEN_READY_FOR_BENCHMARK_PROMPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
