"""v0.5.2 native A/B/C pose-control qualification.

This module intentionally stops at the native benchmark.  RefControl is a
separate, fail-closed escalation implemented only when this benchmark records
an actual native gap.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from .comfyui_client import ComfyUIClient
from .constants import UGAS_VERSION
from .generation import QUALITY_MODEL, _model_names, _run_job, _unique_job_dir, background_remove
from .identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256
from .image_utils import sha256
from .master_assets import write_json
from .model_registry import load_model, validate_model_workflow_compatibility
from .multiview import (
    AB_SEEDS,
    AB_POSE_FLOOR,
    AB_POSE_GAIN,
    _contact_sheet_with_labels,
    _score_output,
    normalize_frame,
)
from .openpose_guides import (
    CHALLENGE_NAME,
    OPENPOSE_GUIDE_RENDERER_VERSION,
    challenge_openpose_guide,
    ensure_openpose_guides,
    render_openpose_evidence,
    guide_hash,
)
from .state_consistency import assert_state_consistency
from .workflow_registry import bind_workflow, load_workflow, validate_api_workflow, workflow_hash


NATIVE_LANES = {
    "A": {"workflow_id": "flux2-klein-base-4b-quality-native-reference-order-a", "reference_order": ["identity-anchor"]},
    "B": {"workflow_id": "flux2-klein-base-4b-quality-native-reference-order-b", "reference_order": ["identity-anchor", "openpose-coco18-pose-guide"]},
    "C": {"workflow_id": "flux2-klein-base-4b-quality-native-reference-order-c", "reference_order": ["openpose-coco18-pose-guide", "identity-anchor"]},
}
SEEDS = (52701, 52702, 52703)
BASE_PROMPT = (
    "Single full-body 2D game character, transparent-ready composition, entire body visible from head to feet, "
    "same face, blue-steel cobalt metallic armor, black cloth, sword, readable silhouette, no text, no watermark, no redesign."
)
PROMPTS = {
    "A": BASE_PROMPT + " Produce a neutral standing gameplay reference while preserving the exact canonical identity.",
    "B": BASE_PROMPT + " Image 1 defines exact character identity, style, materials and proportions. Image 2 is the exact target pose. Apply the exact pose from image 2 while preserving image 1 identity.",
    "C": BASE_PROMPT + " Image 1 is the exact target pose. Image 2 defines exact character identity, style, materials and proportions. Apply the pose from image 1 while preserving image 2 identity.",
}


class PoseControlError(RuntimeError):
    pass


def _json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _assert_phase_zero(repo_root: Path) -> None:
    state = json.loads((repo_root / "docs/evidence/current-state.json").read_text(encoding="utf-8"))
    assert_state_consistency(
        state,
        (repo_root / "CHECKPOINT.md").read_text(encoding="utf-8"),
        (repo_root / "REVIEW-v0.5.2.md").read_text(encoding="utf-8"),
    )
    if state.get("current_gate") != "NATIVE_REFERENCE_ORDER_BENCHMARK" or state.get("stop_reason") is not None:
        raise PoseControlError("current state does not authorize the native reference-order benchmark")


def _runtime_snapshot(repo_root: Path, client: ComfyUIClient) -> dict[str, Any]:
    health = client.safe_health()
    nodes_result = client.safe_call(client.node_info)
    snapshot: dict[str, Any] = {
        "schema_version": UGAS_VERSION,
        "endpoint": client.base_url,
        "health": health,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "custom_nodes_required": [],
    }
    if health.get("status") != "healthy" or nodes_result.get("status") != "ok":
        snapshot.update({"status": "LOCAL_RUNTIME_GAP", "stop_reason": "LOCAL_RUNTIME_GAP", "node_info": nodes_result})
        return snapshot
    node_info = nodes_result["value"]
    model = load_model(repo_root, QUALITY_MODEL)
    model_types = client.list_model_types()
    inventories = {folder: client.list_models(folder) for folder in model_types}
    available_models = sorted({str(item) for values in inventories.values() for item in values})
    workflow_checks = {}
    for lane, config in NATIVE_LANES.items():
        record = load_workflow(repo_root, config["workflow_id"])
        graph = validate_api_workflow(record["api"], node_info=node_info, model_names=set(available_models))
        workflow_checks[lane] = {
            "id": record["id"],
            "template_sha256": record["sha256"],
            "graph": graph,
            "reference_order": config["reference_order"],
            "custom_nodes_required": record.get("custom_nodes_required", []),
            "compatibility": validate_model_workflow_compatibility(model, record),
        }
    snapshot.update({
        "status": "READY" if all(item["graph"]["live_valid"] and not item["custom_nodes_required"] for item in workflow_checks.values()) else "LOCAL_POSE_CONTROL_PROVIDER_GAP",
        "comfyui_version": health["value"].get("system", {}).get("comfyui_version"),
        "gpu": health["value"].get("devices", []),
        "node_info": {
            "count": len(node_info),
            "sha256": _json_hash(node_info),
            "ReferenceLatent": "ReferenceLatent" in node_info,
            "required_native_nodes": sorted({node.get("class_type") for config in workflow_checks.values() for node in load_workflow(repo_root, config["id"])["api"].values()}),
        },
        "inventories": inventories,
        "model": {"id": model["id"], "exact_files": model.get("exact_files", []), "sha256": model.get("sha256", {}), "status": model.get("status"), "license": model.get("license")},
        "workflows": workflow_checks,
    })
    write_json(repo_root / "docs/evidence/runtime-doctor-v0.5.2.json", snapshot)
    return snapshot


def _reference_names(lane: str, uploaded: list[str]) -> list[str]:
    if lane == "A":
        return uploaded[:1]
    return [uploaded[0], uploaded[1]] if lane == "B" else [uploaded[1], uploaded[0]]


def _run_native_candidate(
    repo_root: Path,
    client: ComfyUIClient,
    *,
    lane: str,
    seed: int,
    anchor: Path,
    guide_image: Path,
    guide: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    config = NATIVE_LANES[lane]
    workflow_record = load_workflow(repo_root, config["workflow_id"])
    model = load_model(repo_root, QUALITY_MODEL)
    uploads = [client.upload_image(anchor)]
    if lane != "A":
        uploads.append(client.upload_image(guide_image))
    uploaded = [item.get("name") or item.get("filename") for item in uploads]
    if not all(isinstance(item, str) and item for item in uploaded):
        raise PoseControlError("ComfyUI upload did not return exact reference filenames")
    uploaded = [str(item) for item in uploaded]
    workflow = bind_workflow(
        workflow_record["api"],
        prompt=PROMPTS[lane],
        seed=seed,
        width=512,
        height=512,
        model_names=_model_names(model),
        image_filenames=uploaded,
    )
    graph = validate_api_workflow(workflow, node_info=client.node_info())
    if not graph["live_valid"]:
        raise PoseControlError(f"native workflow node validation failed: {graph['missing_nodes']}")
    stage = f"native-abc-{lane.lower()}-seed-{seed}"
    job_dir = _unique_job_dir(repo_root, output_root, stage)
    semantic_filenames = _reference_names(lane, uploaded)
    semantic_hashes = [sha256(anchor)] if lane == "A" else ([sha256(anchor), sha256(guide_image)] if lane == "B" else [sha256(guide_image), sha256(anchor)])
    input_hashes = {
        "reference_order": config["reference_order"],
        "reference_filenames": semantic_filenames,
        "reference_sha256": semantic_hashes,
        "canonical_anchor_sha256": ANCHOR_SHA256,
        "openpose_guide_image_sha256": sha256(guide_image) if lane != "A" else None,
        "openpose_guide_json_sha256": guide_hash(guide),
    }
    qualification_context = {
        "phase": "POSE_CONTROL_ESCALATION",
        "stage": stage,
        "lane": lane,
        "reference_order": config["reference_order"],
        "prompt_semantics": "image 1 exact pose and image 2 exact identity" if lane == "C" else "image 1 exact identity and image 2 exact pose" if lane == "B" else "identity-only baseline",
        "base_prompt_sha256": hashlib.sha256(BASE_PROMPT.encode("utf-8")).hexdigest(),
        "source_anchor_revision_id": ANCHOR_REVISION_ID,
        "source_anchor_sha256": ANCHOR_SHA256,
        "guide_sha256": guide_hash(guide),
        "previous_frame_chaining": False,
        "workflow_template_sha256": workflow_record["sha256"],
        "workflow_bound_sha256": workflow_hash(workflow),
    }
    result, outputs = _run_job(
        repo_root,
        client,
        workflow,
        output_dir=job_dir,
        filename=f"{stage}.png",
        profile="generic-2d",
        capability="native-reference-order-benchmark",
        workflow_id=config["workflow_id"],
        model_id=QUALITY_MODEL,
        prompt=PROMPTS[lane],
        seed=seed,
        width=512,
        height=512,
        input_hashes=input_hashes,
        qualification_context=qualification_context,
        workflow_sha256=workflow_hash(workflow),
    )
    generated = Path(outputs[0]["path"])
    transparency = background_remove(
        repo_root,
        str(generated),
        endpoint=client.base_url,
        output_dir=job_dir / "background-removal",
        promote=False,
    )
    legacy_guide = _legacy_guide(guide)
    normalized = job_dir / "normalized.png"
    normalization = normalize_frame(Path(transparency["output"]), normalized, frame_name=stage, guide=legacy_guide)
    score = _score_output(normalized, legacy_guide, anchor)
    execution = result["job"].get("execution_evidence", {})
    return {
        "schema_version": UGAS_VERSION,
        "lane": lane,
        "mode": {"A": "identity-only-baseline", "B": "identity-first-pose-second", "C": "pose-first-identity-second"}[lane],
        "seed": seed,
        "workflow_id": config["workflow_id"],
        "workflow_template_sha256": workflow_record["sha256"],
        "workflow_bound_sha256": workflow_hash(workflow),
        "model_id": QUALITY_MODEL,
        "prompt": PROMPTS[lane],
        "prompt_sha256": hashlib.sha256(PROMPTS[lane].encode("utf-8")).hexdigest(),
        "reference_order": config["reference_order"],
        "reference_filenames": semantic_filenames,
        "input_hashes": input_hashes,
        "output": str(generated),
        "output_sha256": sha256(generated),
        "normalized_output": str(normalized),
        "normalized_sha256": sha256(normalized),
        "background_removal": transparency,
        "normalization": normalization,
        "score": score,
        "eligible": bool(score.get("technical", {}).get("eligible") and score.get("identity_pass") and score.get("pose", {}).get("pose_score", 0) >= AB_POSE_FLOOR),
        "execution_evidence": execution,
        "fresh_binding": execution.get("fresh_binding") is True,
        "previous_frame_input": None,
        "history_key_matches_prompt_id": execution.get("history_key_matches_prompt_id") is True,
    }


def _legacy_guide(guide: dict[str, Any]) -> dict[str, Any]:
    """Adapt COCO-18 coordinates to the preserved v0.5.1 scorer contract."""
    joints = guide["joints"]
    def point(name: str) -> list[float]:
        item = joints[name]
        return [float(item["x"]), float(item["y"])]
    return {
        "schema_version": "0.5.1",
        "guide_type": "qualification-challenge",
        "guide_id": guide["guide_id"],
        "view": guide.get("view"),
        "keypoints": {
            "head": point("nose"), "nose": point("nose"), "neck": point("neck"),
            "pelvis": [(joints["hip_left"]["x"] + joints["hip_right"]["x"]) / 2, (joints["hip_left"]["y"] + joints["hip_right"]["y"]) / 2],
            "shoulder_left": point("shoulder_left"), "shoulder_right": point("shoulder_right"),
            "elbow_left": point("elbow_left"), "elbow_right": point("elbow_right"),
            "hand_left": point("wrist_left"), "hand_right": point("wrist_right"),
            "knee_left": point("knee_left"), "knee_right": point("knee_right"),
            "foot_left": point("ankle_left"), "foot_right": point("ankle_right"),
            "weapon_grip": [guide["weapon"]["grip"]["x"], guide["weapon"]["grip"]["y"]],
            "weapon_tip": [guide["weapon"]["tip"]["x"], guide["weapon"]["tip"]["y"]],
        },
    }


def _lane_summary(records: list[dict[str, Any]], lane: str, baseline_mean: float | None) -> dict[str, Any]:
    items = [item for item in records if item.get("lane") == lane]
    scored = [item for item in items if item.get("score")]
    poses = [float(item["score"]["pose"]["pose_score"]) for item in scored]
    identities = [float(item["score"]["identity"]["identity_descriptor_score"]) for item in scored]
    weapons = [item["score"].get("weapon_present") is True for item in scored]
    fresh = [item.get("fresh_binding") is True for item in items]
    mean = sum(poses) / len(poses) if poses else 0.0
    valid = len(items) == AB_SEEDS and len(scored) == AB_SEEDS and all(item.get("eligible") and item.get("fresh_binding") is True for item in items) and all(item["score"]["identity"]["identity_descriptor_score"] >= 0.58 for item in scored) and all(weapons)
    return {
        "lane": lane,
        "records": len(items),
        "scored": len(scored),
        "pose_mean": round(mean, 6),
        "pose_floor": round(min(poses), 6) if poses else 0.0,
        "pose_gain_over_A": round(mean - baseline_mean, 6) if baseline_mean is not None else None,
        "identity_min": round(min(identities), 6) if identities else 0.0,
        "weapon_3_of_3": len(weapons) == AB_SEEDS and all(weapons),
        "fresh_3_of_3": len(fresh) == AB_SEEDS and all(fresh),
        "valid_before_gain": valid,
        "qualified": bool(valid and baseline_mean is not None and mean >= baseline_mean + AB_POSE_GAIN and mean >= 0.85 and min(poses, default=0.0) >= 0.75),
    }


def qualify_native_reference_order(repo_root: Path, *, endpoint: str = "http://127.0.0.1:8188", seed_base: int = 52701) -> dict[str, Any]:
    _assert_phase_zero(repo_root)
    guide_manifest = ensure_openpose_guides(repo_root)
    render_openpose_evidence(repo_root)
    shutil.copy2(repo_root / "docs/evidence/multiref-v2-ab-contact-sheet.png", repo_root / "docs/evidence/v051-gap-baseline.png")
    guide_path = repo_root / guide_manifest["challenge"]
    guide = json.loads(guide_path.read_text(encoding="utf-8"))
    guide_image = repo_root / "docs/evidence/openpose-guide-v3-control-example.png"
    anchor = repo_root / "docs/evidence/reference-edit-selected-transparent.png"
    client = ComfyUIClient(endpoint, timeout=90.0)
    runtime = _runtime_snapshot(repo_root, client)
    records: list[dict[str, Any]] = []
    execution_records: list[dict[str, Any]] = []
    if runtime.get("status") == "READY":
        if seed_base != SEEDS[0]:
            seeds = tuple(seed_base + offset for offset in range(AB_SEEDS))
        else:
            seeds = SEEDS
        for lane in ("A", "B", "C"):
            for seed in seeds:
                try:
                    record = _run_native_candidate(repo_root, client, lane=lane, seed=seed, anchor=anchor, guide_image=guide_image, guide=guide, output_root=repo_root / "tmp" / "pose-control-v052")
                    records.append(record)
                    execution_records.append({"stage": f"native-abc-{lane.lower()}-{seed}", "lane": lane, "image_edit": record["execution_evidence"], "background_removal": record["background_removal"].get("execution_evidence", {}), "reference_order": record["reference_order"], "workflow_sha256": record["workflow_bound_sha256"]})
                except Exception as exc:
                    records.append({"schema_version": UGAS_VERSION, "lane": lane, "seed": seed, "error": f"{type(exc).__name__}: {exc}", "fresh_binding": False, "previous_frame_input": None})
    else:
        for lane in ("A", "B", "C"):
            for seed in (seed_base + offset for offset in range(AB_SEEDS)):
                records.append({"schema_version": UGAS_VERSION, "lane": lane, "seed": seed, "error": runtime.get("stop_reason", "LOCAL_RUNTIME_GAP"), "fresh_binding": False, "previous_frame_input": None})
    a_records = [item for item in records if item.get("lane") == "A" and item.get("score")]
    a_mean = sum(float(item["score"]["pose"]["pose_score"]) for item in a_records) / len(a_records) if a_records else 0.0
    summaries = {lane: _lane_summary(records, lane, a_mean if a_records else None) for lane in ("A", "B", "C")}
    qualified_lanes = [lane for lane in ("B", "C") if summaries[lane]["qualified"]]
    status = "NATIVE_REFERENCE_ORDER_QUALIFIED" if qualified_lanes else "NATIVE_REFERENCE_ORDER_POSE_CONTROL_GAP"
    stop_reason = None if qualified_lanes else ("LOCAL_RUNTIME_GAP" if runtime.get("status") != "READY" else "NATIVE_REFERENCE_ORDER_POSE_CONTROL_GAP")
    contact_paths = [Path(item["normalized_output"]) for item in records if item.get("normalized_output")]
    labels = [f"{item['lane']} seed={item['seed']} pose={item['score']['pose']['pose_score']:.3f} id={item['score']['identity']['identity_descriptor_score']:.3f} {'PASS' if item.get('eligible') else 'REJECT'}" for item in records if item.get("normalized_output")]
    contact = None
    if contact_paths:
        contact = _contact_sheet_with_labels(contact_paths, labels, repo_root / "tmp" / "pose-control-v052" / "native-reference-order-abc-contact-sheet.png", 3)
        shutil.copy2(contact["path"], repo_root / "docs/evidence/native-reference-order-abc-contact-sheet.png")
    execution = {
        "schema_version": UGAS_VERSION,
        "status": status,
        "records": execution_records,
        "fresh_binding_required": True,
        "all_prompt_ids_present": bool(execution_records) and all(bool(item.get("image_edit", {}).get("prompt_id")) for item in execution_records) and len(execution_records) == 9,
        "all_history_bindings_exact": bool(execution_records) and all(item.get("image_edit", {}).get("history_key_matches_prompt_id") is True for item in execution_records) and len(execution_records) == 9,
        "stale_output_rejected": bool(execution_records) and all(item.get("image_edit", {}).get("target_existed_before_submission") is False for item in execution_records) and len(execution_records) == 9,
        "previous_frame_chaining": False,
        "record_count": len(execution_records),
    }
    write_json(repo_root / "docs/evidence/execution-evidence-v0.5.2.json", execution)
    evidence = {
        "schema_version": UGAS_VERSION,
        "status": status,
        "capability": "native-reference-order-benchmark",
        "asset_id": ANCHOR_ASSET_ID,
        "canonical_anchor": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256},
        "runtime": runtime,
        "guide": {"path": str(guide_path.relative_to(repo_root)).replace("\\", "/"), "sha256": guide_hash(guide), "control_path": "docs/evidence/openpose-guide-v3-control-example.png", "control_sha256": sha256(guide_image), "renderer_version": OPENPOSE_GUIDE_RENDERER_VERSION, "joint_schema": "COCO-18"},
        "benchmark_contract": {"seeds": list(SEEDS if seed_base == SEEDS[0] else tuple(seed_base + offset for offset in range(AB_SEEDS))), "same_resolution": "512x512", "same_model": QUALITY_MODEL, "same_sampler": "euler", "same_steps": 20, "same_guidance": 5.0, "no_previous_frame_input": True, "gain_threshold": AB_POSE_GAIN, "native_mean_threshold": 0.85, "native_floor_threshold": 0.75},
        "records": records,
        "baseline_A_pose_mean": round(a_mean, 6),
        "lanes": summaries,
        "qualified_lanes": qualified_lanes,
        "stop_reason": stop_reason,
        "contact_sheet": "docs/evidence/native-reference-order-abc-contact-sheet.png" if contact else None,
        "execution_evidence": "docs/evidence/execution-evidence-v0.5.2.json",
        "human_visual_review": "required",
        "production_approval": "not-granted",
    }
    write_json(repo_root / "docs/evidence/native-reference-order-qualification.json", evidence)
    return evidence
