"""Execute the bounded UGAS v0.5.4 pose-provider lane recheck.

This script is intentionally narrow: after the MediaPipe QA estimator has
qualified, it runs exactly lanes A, C and R for exactly three fresh seeds. It
does not run a walk, create directional anchors, add a provider, or tune a
strength. Every submission is bound to the canonical R4 identity anchor and
the deterministic v0.3 challenge guide.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from ugas.comfyui_client import ComfyUIClient
from ugas.generation import QUALITY_MODEL, _model_names, _run_job, _unique_job_dir, background_remove
from ugas.image_utils import inspect_png, sha256
from ugas.model_registry import load_model, verify_model_files
from ugas.pose_metric_calibration import detected_joint_pose_metrics
from ugas.pose_qa_estimator import (
    _contact_sheet,
    _detect_with_landmarker,
    _draw_overlay,
    _landmarker,
    prepare_preprocessed_image,
)
from ugas.workflow_registry import bind_workflow, load_workflow, validate_api_workflow, workflow_hash


PROMPT_ID = "PROMPT-04F-UGAS-POSE-QA-LICENSE-ESTIMATOR-LANE-RECHECK-v0.5.4"
ENDPOINT = "http://127.0.0.1:8188"
SEEDS = (54701, 54702, 54703)
LANE_IDS = {
    "A": "flux2-klein-base-4b-quality-native-reference-order-a",
    "C": "flux2-klein-base-4b-quality-native-reference-order-c",
    "R": "flux2-klein-base-4b-quality-refcontrol-pose",
}
ANCHOR_RELATIVE = "docs/evidence/reference-edit-selected-transparent.png"
GUIDE_RELATIVE = "docs/evidence/openpose-guide-v3-control-example.png"
GUIDE_JSON_RELATIVE = "pose-guides/openpose-v3/challenges/multiref-strong-left-arm-up.json"
POSE_POLICY = "transparent_neutral_gray"
LORA_MODEL_ID = "xocialize-refcontrol-flux2-klein-4b-pose-lora"
LORA_FILENAME = "refcontrol-pose-klein-4b.safetensors"
LORA_STRENGTH = 0.8


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def _guide_points(guide: dict[str, Any]) -> dict[str, tuple[float, float]]:
    joints = guide.get("joints") or {}
    required = ("nose", "shoulder_left", "shoulder_right", "elbow_left", "elbow_right", "wrist_left", "wrist_right", "hip_left", "hip_right", "knee_left", "knee_right", "ankle_left", "ankle_right")
    result: dict[str, tuple[float, float]] = {}
    for name in required:
        item = joints.get(name)
        if not isinstance(item, dict) or item.get("visible") is False:
            raise RuntimeError(f"challenge guide is missing visible joint: {name}")
        result[name] = (float(item["x"]) / 512.0, float(item["y"]) / 512.0)
    return result


def _validate_thresholds(value: dict[str, Any]) -> None:
    if value.get("schema_version") != "0.5.4" or value.get("thresholds_are_frozen_before_jobs") is not True:
        raise RuntimeError("v0.5.4 thresholds are missing or were not frozen before provider jobs")
    bounded = value.get("range_validation", {}).get("bounded_metrics", {})
    expected_ranges = {"pck": (0.0, 1.0), "nme": (0.0, 1.0), "lower_body_pck": (0.0, 1.0), "normalized_score": (0.0, 1.0), "identity_score": (0.0, 1.0), "angle_mae_degrees": (0.0, 180.0)}
    for name, expected in expected_ranges.items():
        actual = bounded.get(name)
        if actual != list(expected):
            raise RuntimeError(f"threshold range is not explicit for {name}: {actual!r}")
    if value["fresh_execution"]["lanes"] != ["A", "C", "R"] or value["fresh_execution"]["seeds"] != list(SEEDS):
        raise RuntimeError("lane or seed policy is outside the v0.5.4 prompt")
    if value["fresh_execution"]["outputs_required"] != 9:
        raise RuntimeError("v0.5.4 requires exactly 9 fresh outputs")


def _lane_prompt(lane: str) -> str:
    if lane == "A":
        return "Single full-body game character. Use image 1 as the exact identity anchor: preserve face, armor, black cloth, sword, palette and proportions. This is the identity-only baseline; do not copy any guide, text, label or background. Keep the character as a clean 2D game sprite on a simple neutral background."
    if lane == "C":
        return "Single full-body game character. Image 1 defines the exact identity anchor: preserve face, armor, black cloth, sword, palette and proportions. Image 2 defines the exact left-facing profile pose only: reproduce its raised left arm, bent legs, torso angle and foot placement. Use native pose-first then identity-second reference conditioning. Do not copy the mannequin, guide lines, text, label or background."
    return "Single full-body game character. Image 1 defines the exact identity anchor: preserve face, armor, black cloth, sword, palette and proportions. Image 2 defines the exact left-facing profile pose only: reproduce its raised left arm, bent legs, torso angle and foot placement. Apply RefControl pose conditioning at the authorized strength 0.8, then preserve identity. Do not copy the mannequin, guide lines, text, label or background."


def _record_failure(lane: str, seed: int, workflow_id: str, error: Exception, *, anchor_hash: str, guide_hash: str, workflow_sha: str | None = None) -> dict[str, Any]:
    return {
        "lane": lane,
        "seed": seed,
        "workflow_id": workflow_id,
        "workflow_sha256": workflow_sha,
        "status": "FAILED",
        "error": f"{type(error).__name__}: {error}",
        "anchor_sha256": anchor_hash,
        "guide_sha256": guide_hash,
        "seed_was_used_before": False,
        "target_existed_before_submission": False,
        "previous_frame_chaining": False,
        "fresh_binding": False,
        "absolute_pose_pass": False,
        "identity_pass": False,
        "weapon_present": False,
    }


def _execute_one(
    *,
    client: ComfyUIClient,
    lane: str,
    seed: int,
    anchor: Path,
    guide_image: Path | None,
    guide_hash: str,
    anchor_hash: str,
    guide_points: dict[str, tuple[float, float]],
    thresholds: dict[str, Any],
    model_names: dict[str, str],
    lora_model_id: str | None,
    endpoint: str,
    output_root: Path,
    model_id: str,
) -> dict[str, Any]:
    workflow_id = LANE_IDS[lane]
    record = load_workflow(REPO_ROOT, workflow_id)
    uploads = [client.upload_image(anchor)]
    if guide_image is not None:
        uploads.append(client.upload_image(guide_image))
    filenames = [item.get("name") or item.get("filename") for item in uploads]
    if not all(isinstance(item, str) and item for item in filenames):
        raise RuntimeError("ComfyUI upload did not return exact filenames")
    workflow = bind_workflow(
        record["api"],
        prompt=_lane_prompt(lane),
        seed=seed,
        width=512,
        height=512,
        model_names=model_names,
        image_filenames=[str(item) for item in filenames],
        lora_name=LORA_FILENAME if lane == "R" else None,
        lora_strength=LORA_STRENGTH if lane == "R" else None,
    )
    graph = validate_api_workflow(workflow, node_info=client.node_info())
    if not graph["live_valid"]:
        raise RuntimeError(f"workflow native node validation failed: {graph['missing_nodes']} {graph['missing_models']}")
    stage = f"v054-{lane.lower()}-seed-{seed}"
    job_dir = _unique_job_dir(REPO_ROOT, output_root, stage)
    filename = f"{stage}.png"
    input_hashes = {"identity_anchor_sha256": anchor_hash}
    if guide_image is not None:
        input_hashes.update({"pose_guide_image_sha256": sha256(guide_image), "pose_guide_json_sha256": guide_hash})
    qualification_context = {
        "prompt_id": PROMPT_ID,
        "lane": lane,
        "seed": seed,
        "canonical_anchor": ANCHOR_RELATIVE,
        "guide": GUIDE_RELATIVE if guide_image is not None else None,
        "guide_json": GUIDE_JSON_RELATIVE if guide_image is not None else None,
        "previous_frame_chaining": False,
        "target_existed_before_submission": False,
        "seed_was_used_before": False,
        "lora_strength": LORA_STRENGTH if lane == "R" else None,
        "lora_model_id": lora_model_id,
    }
    started = time.perf_counter()
    job_result, outputs = _run_job(
        REPO_ROOT,
        client,
        workflow,
        output_dir=job_dir,
        filename=filename,
        profile="generic-2d",
        capability=record["capability"],
        workflow_id=workflow_id,
        model_id=model_id,
        prompt=_lane_prompt(lane),
        seed=seed,
        width=512,
        height=512,
        input_hashes=input_hashes,
        qualification_context=qualification_context,
        seed_was_used_before=False,
        workflow_sha256=workflow_hash(record["api"]),
    )
    raw = Path(outputs[0]["path"])
    raw_sha256 = sha256(raw)
    # Identity metrics and the estimator's foreground sanity gate operate on
    # the same native RGB-preserving alpha join used by prior UGAS evidence.
    transparent = background_remove(REPO_ROOT, str(raw), endpoint=endpoint, output_dir=job_dir / "birefnet", promote=False)
    final_source = Path(transparent["output"])
    final_dir = REPO_ROOT / "docs/evidence/v054-lanes"
    final_path = final_dir / f"{lane.lower()}-seed-{seed}.png"
    final_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(final_source, final_path)
    from ugas.multiview import _identity_descriptor

    identity = _identity_descriptor(final_path, anchor)
    preprocessed = prepare_preprocessed_image(final_path, POSE_POLICY, job_dir / "pose-qa.png")
    model_path = Path(__import__("ugas.pose_qa_estimator", fromlist=["_default_model_path"])._default_model_path())
    with _landmarker(model_path) as (mp, detector):
        detection = _detect_with_landmarker(Path(preprocessed["path"]), mp, detector)
    detected_orientation = _infer_orientation(detection["landmarks"])
    pose = detected_joint_pose_metrics(
        guide_points,
        detection["landmarks"],
        target_orientation="left_profile",
        detected_orientation=detected_orientation,
    )
    absolute = bool(
        pose["qualifies"]
        and pose["measurable_body_joints"] >= thresholds["absolute_pose"]["measurable_body_joints_min"]
        and pose["pck_at_010"] >= thresholds["absolute_pose"]["pck_at_010_min"]
        and pose["nme"] <= thresholds["absolute_pose"]["nme_max"]
        and pose["limb_angle_mae_degrees"] <= thresholds["absolute_pose"]["limb_angle_mae_max_degrees"]
        and pose["lower_body_pck"] >= thresholds["absolute_pose"]["lower_body_pck_min"]
        and pose["orientation_match"]
    )
    identity_pass = bool(identity.get("identity_descriptor_score", 0.0) >= thresholds["identity_weapon"]["identity_score_min"] and identity.get("weapon_present") is True)
    execution = job_result["job"].get("execution_evidence", {})
    fresh = bool(execution.get("fresh_binding") and execution.get("history_key_matches_prompt_id") and not execution.get("seed_was_used_before") and not execution.get("target_existed_before_submission") and not qualification_context["previous_frame_chaining"])
    overlay = job_dir / "pose-overlay.png"
    _draw_overlay(Path(preprocessed["path"]), detection["landmarks"], preprocessed["alpha_bbox_normalized"], f"{lane} seed {seed}", overlay, f"pck={pose['pck_at_010']:.3f} nme={pose['nme']:.3f} id={identity.get('identity_descriptor_score', 0.0):.3f}")
    return {
        "lane": lane,
        "seed": seed,
        "workflow_id": workflow_id,
        "workflow_sha256": workflow_hash(record["api"]),
        "model_id": model_id,
        "base_model_id": QUALITY_MODEL,
        "lora_model_id": lora_model_id,
        "lora_strength": LORA_STRENGTH if lane == "R" else None,
        "prompt_id": execution.get("prompt_id"),
        "history_record_key": execution.get("history_record_key"),
        "history_key_matches_prompt_id": execution.get("history_key_matches_prompt_id"),
        "anchor_sha256": anchor_hash,
        "guide_sha256": guide_hash if guide_image is not None else None,
        "guide_image_sha256": sha256(guide_image) if guide_image is not None else None,
        "raw_output_path": _relative(raw),
        "raw_output_sha256": raw_sha256,
        "output_path": _relative(final_path),
        "output_sha256": sha256(final_path),
        "output_png": inspect_png(final_path),
        "birefnet_execution": transparent.get("execution_evidence", {}),
        "pose_qa_preprocess": preprocessed,
        "detection": {key: detection[key] for key in ("detected", "measurable_body_joints", "core_coverage", "mean_confidence", "min_confidence")},
        "detected_orientation": detected_orientation,
        "pose": pose,
        "identity": identity,
        "absolute_pose_pass": absolute,
        "identity_pass": identity_pass,
        "weapon_present": bool(identity.get("weapon_present")),
        "fresh_binding": fresh,
        "seed_was_used_before": False,
        "target_existed_before_submission": False,
        "previous_frame_chaining": False,
        "execution_runtime_ms": round((time.perf_counter() - started) * 1000, 3),
        "overlay_path": _relative(overlay),
        "status": "PASSED" if absolute and identity_pass and fresh else "FAILED_GATES",
    }


def _infer_orientation(landmarks: dict[str, Any]) -> str:
    """Infer the signed profile cue used by the v0.5.3 metric contract."""
    def x(name: str) -> float | None:
        value = landmarks.get(name)
        if not isinstance(value, dict) or value.get("visible") is False:
            return None
        try:
            return float(value["x"])
        except (KeyError, TypeError, ValueError):
            return None

    nose, left, right = x("nose"), x("shoulder_left"), x("shoulder_right")
    if nose is None or left is None or right is None:
        return "unknown"
    shoulder_center = (left + right) / 2.0
    delta = nose - shoulder_center
    if delta <= -0.045:
        return "left_profile"
    if delta >= 0.045:
        return "right_profile"
    return "front"


def _decision(records: list[dict[str, Any]], thresholds: dict[str, Any]) -> dict[str, Any]:
    by_lane = {lane: [item for item in records if item["lane"] == lane and item.get("status") not in {"FAILED"}] for lane in LANE_IDS}
    baseline_errors = [1.0 - float(item.get("pose", {}).get("pose_score", 0.0)) for item in by_lane["A"]]
    baseline_error = median(baseline_errors) if baseline_errors else 1.0
    lane_summary: dict[str, Any] = {}
    for lane, items in by_lane.items():
        errors = [1.0 - float(item.get("pose", {}).get("pose_score", 0.0)) for item in items]
        pose_scores = [float(item.get("pose", {}).get("pose_score", 0.0)) for item in items]
        error = median(errors) if errors else 1.0
        reduction = (baseline_error - error) / max(1e-9, baseline_error) if lane != "A" else 0.0
        normalized_gain = (median(pose_scores) - (1.0 - baseline_error)) / max(1e-9, baseline_error) if lane != "A" else 0.0
        lane_summary[lane] = {
            "record_count": len(items),
            "absolute_pose_all_pass": bool(len(items) == 3 and all(item.get("absolute_pose_pass") for item in items)),
            "identity_weapon_all_pass": bool(len(items) == 3 and all(item.get("identity_pass") and item.get("weapon_present") for item in items)),
            "fresh_execution_all_pass": bool(len(items) == 3 and all(item.get("fresh_binding") for item in items)),
            "median_pose_score": round(median(pose_scores), 6) if pose_scores else 0.0,
            "median_pose_error": round(error, 6),
            "relative_joint_error_reduction_vs_A": round(reduction, 6),
            "normalized_score_gain_vs_A": round(normalized_gain, 6),
            "causal_pass": bool(
                lane != "A"
                and len(items) == 3
                and all(item.get("absolute_pose_pass") for item in items)
                and all(item.get("identity_pass") and item.get("weapon_present") for item in items)
                and all(item.get("fresh_binding") for item in items)
                and (reduction >= thresholds["causal"]["relative_joint_error_reduction_min"] or normalized_gain >= thresholds["causal"]["normalized_score_gain_min"])
            ),
        }
    qualified_lane = next((lane for lane in ("R", "C") if lane_summary.get(lane, {}).get("causal_pass")), None)
    if qualified_lane:
        status = "POSE_LANE_QUALIFIED"
        stop_reason = None
    elif records and records[0].get("estimator_status") == "POSE_QA_ESTIMATOR_QUALIFIED":
        status = "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED"
        stop_reason = status
    else:
        status = "POSE_QA_ESTIMATOR_GAP"
        stop_reason = status
    return {"status": status, "stop_reason": stop_reason, "baseline_lane": "A", "baseline_median_pose_error": round(baseline_error, 6), "lane_summary": lane_summary, "qualified_lane": qualified_lane}


def run(repo_root: Path, endpoint: str) -> int:
    thresholds_path = repo_root / "docs/evidence/pose-thresholds-v054.json"
    thresholds = _load(thresholds_path)
    _validate_thresholds(thresholds)
    qualification_path = repo_root / "docs/evidence/pose-qa-estimator-qualification-v054.json"
    qualification = _load(qualification_path)
    estimator_status = qualification.get("status")
    anchor = repo_root / ANCHOR_RELATIVE
    guide_image = repo_root / GUIDE_RELATIVE
    guide_json = repo_root / GUIDE_JSON_RELATIVE
    if estimator_status != "POSE_QA_ESTIMATOR_QUALIFIED":
        decision = {"status": "POSE_QA_ESTIMATOR_GAP", "stop_reason": "POSE_QA_ESTIMATOR_GAP", "qualified_lane": None}
        _write(repo_root / "docs/evidence/v054-pose-error-table.json", {"schema_version": "0.5.4", "status": decision["status"], "rows": [], "decision": decision})
        _write(repo_root / "docs/evidence/v054-provider-qualification.json", {"schema_version": "0.5.4", "status": decision["status"], "stop_reason": decision["stop_reason"], "estimator_status": estimator_status, "lanes": {}, "seeds": list(SEEDS), "provider_routing_used": False, "walk_authorized": False})
        return 2
    if not anchor.is_file() or not guide_image.is_file() or not guide_json.is_file():
        raise RuntimeError("canonical R4 anchor or v0.3 challenge guide is missing")
    anchor_hash, guide_hash = sha256(anchor), sha256(guide_json)
    guide = _load(guide_json)
    guide_points = _guide_points(guide)
    base_model = load_model(repo_root, QUALITY_MODEL)
    lora_model = load_model(repo_root, LORA_MODEL_ID)
    model_root = Path.home() / "AppData" / "Local" / "UGAS" / "comfyui" / "models"
    lora_files = verify_model_files(lora_model, model_root)
    if not lora_files["hashes_verified"]:
        raise RuntimeError("RefControl LoRA hash is not verified; lane R must not run")
    model_names = {**_model_names(base_model), **_model_names(lora_model)}
    client = ComfyUIClient(endpoint, timeout=60.0)
    # This is read-only live graph validation for the three authorized lanes.
    node_info = client.node_info()
    lane_graphs = {}
    for lane, workflow_id in LANE_IDS.items():
        record = load_workflow(repo_root, workflow_id)
        filenames = ["anchor.png"] + ([] if lane == "A" else ["guide.png"])
        bound = bind_workflow(record["api"], prompt=_lane_prompt(lane), seed=SEEDS[0], width=512, height=512, model_names=model_names, image_filenames=filenames, lora_name=LORA_FILENAME if lane == "R" else None, lora_strength=LORA_STRENGTH if lane == "R" else None)
        lane_graphs[lane] = {"workflow_id": workflow_id, "workflow_sha256": workflow_hash(record["api"]), "validation": validate_api_workflow(bound, node_info=node_info), "reference_order": record.get("parameters", {}).get("reference_order"), "lora_strength": LORA_STRENGTH if lane == "R" else None}
        if not lane_graphs[lane]["validation"]["live_valid"]:
            raise RuntimeError(f"lane {lane} graph is not live-valid: {lane_graphs[lane]['validation']}")
    records: list[dict[str, Any]] = []
    output_root = repo_root / "tmp/pose-qa-v054/lanes"
    for lane in ("A", "C", "R"):
        for seed in SEEDS:
            try:
                item = _execute_one(client=client, lane=lane, seed=seed, anchor=anchor, guide_image=None if lane == "A" else guide_image, guide_hash=guide_hash, anchor_hash=anchor_hash, guide_points=guide_points, thresholds=thresholds, model_names=model_names, lora_model_id=LORA_MODEL_ID if lane == "R" else None, endpoint=endpoint, output_root=output_root, model_id=LORA_MODEL_ID if lane == "R" else QUALITY_MODEL)
                item["estimator_status"] = estimator_status
                records.append(item)
                print(f"{lane} seed={seed}: {item['status']} pose={item['pose']['pose_score']:.3f} pck={item['pose']['pck_at_010']:.3f} id={item['identity']['identity_descriptor_score']:.3f}", flush=True)
            except Exception as exc:
                item = _record_failure(lane, seed, LANE_IDS[lane], exc, anchor_hash=anchor_hash, guide_hash=guide_hash, workflow_sha=lane_graphs[lane]["workflow_sha256"])
                item["estimator_status"] = estimator_status
                records.append(item)
                print(f"{lane} seed={seed}: FAILED {type(exc).__name__}: {exc}", flush=True)
    overlays = [repo_root / item["overlay_path"] for item in records if item.get("overlay_path")]
    overlay_labels = [f"{item['lane']} seed {item['seed']} | {item.get('status')}" for item in records if item.get("overlay_path")]
    overlay_sheet = _contact_sheet(overlays, overlay_labels, repo_root / "docs/evidence/v054-pose-overlays-contact-sheet.png", columns=3) if overlays else None
    outputs = [repo_root / item["output_path"] for item in records if item.get("output_path")]
    output_labels = [f"{item['lane']} seed {item['seed']}" for item in records if item.get("output_path")]
    output_sheet = _contact_sheet(outputs, output_labels, repo_root / "docs/evidence/v054-lanes-contact-sheet.png", columns=3) if outputs else None
    decision = _decision(records, thresholds)
    rows = []
    for item in records:
        pose = item.get("pose", {})
        rows.append({"lane": item["lane"], "seed": item["seed"], "status": item.get("status"), "pose_error": round(1.0 - float(pose.get("pose_score", 0.0)), 6), "pck_at_010": pose.get("pck_at_010"), "nme": pose.get("nme"), "limb_angle_mae_degrees": pose.get("limb_angle_mae_degrees"), "lower_body_pck": pose.get("lower_body_pck"), "orientation_match": pose.get("orientation_match"), "absolute_pose_pass": item.get("absolute_pose_pass", False), "identity_score": item.get("identity", {}).get("identity_descriptor_score", 0.0), "weapon_present": item.get("weapon_present", False), "identity_pass": item.get("identity_pass", False), "fresh_binding": item.get("fresh_binding", False), "output_path": item.get("output_path"), "output_sha256": item.get("output_sha256")})
    _write(repo_root / "docs/evidence/v054-pose-error-table.json", {"schema_version": "0.5.4", "status": decision["status"], "metric_version": "detected-joint-pose-error-1.0", "thresholds": "docs/evidence/pose-thresholds-v054.json", "rows": rows, "decision": decision, "overlay_contact_sheet": overlay_sheet, "lane_contact_sheet": output_sheet})
    _write(repo_root / "docs/evidence/v054-provider-qualification.json", {"schema_version": "0.5.4", "status": decision["status"], "stop_reason": decision["stop_reason"], "prompt_id": PROMPT_ID, "estimator_status": estimator_status, "license_status": "POSE_QA_LOCAL_USE_LICENSE_RESOLVED", "selected_preprocess_policy": POSE_POLICY, "anchor": {"path": ANCHOR_RELATIVE, "sha256": anchor_hash}, "guide": {"path": GUIDE_RELATIVE, "json_path": GUIDE_JSON_RELATIVE, "json_sha256": guide_hash, "orientation": "left_profile"}, "model_stack": {"base_model_id": QUALITY_MODEL, "refcontrol_model_id": LORA_MODEL_ID, "refcontrol_lora_filename": LORA_FILENAME, "refcontrol_lora_strength": LORA_STRENGTH, "refcontrol_hashes_verified": lora_files["hashes_verified"]}, "lanes": lane_graphs, "seeds": list(SEEDS), "records": records, "record_count": len(records), "fresh_outputs": len([item for item in records if item.get("output_path")]), "decision": decision, "walk_authorized": False, "directional_anchors_authorized": False, "new_provider_used": False, "new_strength_used": False, "production_approval": "not-granted", "human_visual_review": "required"})
    execution_records = [{"lane": item["lane"], "seed": item["seed"], "workflow_id": item["workflow_id"], "prompt_id": item.get("prompt_id"), "history_record_key": item.get("history_record_key"), "history_key_matches_prompt_id": item.get("history_key_matches_prompt_id", False), "anchor_sha256": item.get("anchor_sha256"), "guide_sha256": item.get("guide_sha256"), "output_path": item.get("output_path"), "output_sha256": item.get("output_sha256"), "fresh_binding": item.get("fresh_binding", False), "seed_was_used_before": item.get("seed_was_used_before", False), "target_existed_before_submission": item.get("target_existed_before_submission", False), "previous_frame_chaining": item.get("previous_frame_chaining", False), "image_edit_execution": item.get("prompt_id"), "background_removal_execution": item.get("birefnet_execution", {})} for item in records]
    _write(repo_root / "docs/evidence/execution-evidence-v0.5.4.json", {"schema_version": "0.5.4", "prompt_id": PROMPT_ID, "status": decision["status"], "lanes": ["A", "C", "R"], "seeds": list(SEEDS), "required_output_count": 9, "record_count": len(execution_records), "records": execution_records, "all_fresh_binding": bool(len(execution_records) == 9 and all(item["fresh_binding"] for item in execution_records)), "no_previous_frame_chaining": all(not item["previous_frame_chaining"] for item in execution_records), "no_walk_executed": True, "provider_routing_used": bool(execution_records), "production_approval": "not-granted"})
    print(json.dumps({"status": decision["status"], "qualified_lane": decision["qualified_lane"], "records": len(records), "outputs": len(outputs), "overlay_sheet": str(overlay_sheet["path"]) if overlay_sheet else None}, ensure_ascii=False))
    return 0 if decision["status"] == "POSE_LANE_QUALIFIED" else 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=ENDPOINT)
    args = parser.parse_args()
    try:
        return run(REPO_ROOT, args.endpoint)
    except Exception as exc:
        print(f"v0.5.4 lane recheck blocked: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
