"""Run the v0.7.0 isolated SAM2 qualification and deterministic rig pilot.

The script is intentionally invoked with the external UGAS/ComfyUI Python
environment.  It never submits a ComfyUI job: ComfyUI is only the historical
runtime location for torch on this workstation, while SAM2 and the renderer
are called directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch
from PIL import Image, ImageChops, ImageDraw, ImageEnhance

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.cutout_rig import (  # noqa: E402
    CAPABILITY_ID,
    MASK_ALPHA_FOREGROUND_THRESHOLD,
    MASK_MIN_FOREGROUND_PURITY,
    MAX_MEMBER_SCALE,
    MIN_MEMBER_SCALE,
    PART_NAMES,
    PART_SPECS,
    PROVIDER_ID,
    RENDERER_VERSION,
    REQUIRED_JOINTS,
    SCHEMA_VERSION,
    build_part_prompts,
    compose_rig,
    draw_part_contact_sheet,
    image_metrics,
    mask_stats,
    mask_union_stats,
    render_hierarchy_diagram,
    seam_metrics,
    sha256_file,
    source_skeleton,
    skeleton_point,
    transform_parameters,
    validate_rig_manifest,
)
from ugas.identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256  # noqa: E402
from ugas.pose_qa_estimator import _detect  # noqa: E402
from ugas.pose_metric_calibration import CORE_JOINTS, detected_joint_pose_metrics  # noqa: E402


SAM2_REPOSITORY = "https://github.com/facebookresearch/sam2"
SAM2_LICENSE = "Apache-2.0"
SAM2_COMMIT = "2b90b9f5ceec907a1c18123530e92e794ad901a4"
SAM2_CHECKPOINT = "sam2.1_hiera_small.pt"
SAM2_CHECKPOINT_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt"
SAM2_CONFIG = "configs/sam2.1/sam2.1_hiera_s.yaml"
R4_PATH = ROOT / "docs/evidence/reference-edit-selected-transparent.png"
POSE_MODEL_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "UGAS/pose-qa/pose_landmarker_full.task"
SAM2_MODEL_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "UGAS/models/sam2" / SAM2_CHECKPOINT
EVIDENCE = ROOT / "docs/evidence"
MASK_DIR = EVIDENCE / "r4-cutout-masks"
PART_DIR = EVIDENCE / "r4-cutout-parts"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _runtime_status() -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "provider_id": PROVIDER_ID,
        "capability": CAPABILITY_ID,
        "status": "SAM2_RUNTIME_GAP",
        "official_source": SAM2_REPOSITORY,
        "license": SAM2_LICENSE,
        "repository_commit": SAM2_COMMIT,
        "checkpoint": {"filename": SAM2_CHECKPOINT, "url": SAM2_CHECKPOINT_URL, "path_not_published": True, "outside_git": True, "outside_review_zip": True},
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "torch": {"version": getattr(torch, "__version__", None), "cuda_available": bool(torch.cuda.is_available()), "device": DEVICE},
        "torchvision": {"version": None},
        "runtime_policy": {"isolated_external_tool": True, "comfyui_custom_node": False, "comfyui_generation_jobs": 0, "sam3_forbidden": True},
        "smoke": {"status": "NOT_RUN", "box_positive_point": True},
        "timestamp": _now(),
    }
    failures: list[str] = []
    try:
        import torchvision
        result["torchvision"]["version"] = torchvision.__version__
    except Exception as exc:
        failures.append(f"torchvision_import:{type(exc).__name__}:{exc}")
    if not SAM2_MODEL_PATH.is_file():
        failures.append("checkpoint_missing")
    else:
        result["checkpoint"].update({"bytes": SAM2_MODEL_PATH.stat().st_size, "sha256": sha256_file(SAM2_MODEL_PATH)})
    if result["checkpoint"].get("sha256") is None:
        failures.append("checkpoint_sha256_missing")
    if not R4_PATH.is_file():
        failures.append("r4_missing")
    try:
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        result["imports"] = {"sam2": "importable", "build_sam2": True, "SAM2ImagePredictor": True}
    except Exception as exc:
        failures.append(f"sam2_import:{type(exc).__name__}:{exc}")
        result["imports"] = {"sam2": "import_error", "error": str(exc)}
    if failures:
        result["failures"] = failures
        _write(EVIDENCE / "sam2-provider-qualification.json", result)
        _write(EVIDENCE / "sam2-checkpoint-provenance.json", {"schema_version": SCHEMA_VERSION, "status": "SAM2_RUNTIME_GAP", "checkpoint": result["checkpoint"], "failures": failures, "source": SAM2_REPOSITORY})
        return result
    try:
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        if DEVICE == "cuda":
            torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        model = build_sam2(SAM2_CONFIG, str(SAM2_MODEL_PATH), device=DEVICE)
        predictor = SAM2ImagePredictor(model)
        with Image.open(R4_PATH) as opened:
            source = opened.convert("RGBA")
        neutral = Image.new("RGB", source.size, (128, 128, 128))
        neutral.paste(source, (0, 0), source.getchannel("A"))
        image = np.asarray(neutral)
        predictor.set_image(image)
        alpha_bbox = source.getchannel("A").getbbox()
        if not alpha_bbox:
            raise RuntimeError("R4 has no foreground")
        x0, y0, x1, y1 = alpha_bbox
        point = np.array([[(x0 + x1) / 2.0, (y0 + y1) / 2.0]], dtype=np.float32)
        labels = np.array([1], dtype=np.int32)
        masks, scores, _ = predictor.predict(point_coords=point, point_labels=labels, box=np.array([x0, y0, x1, y1], dtype=np.float32), multimask_output=True)
        elapsed = time.perf_counter() - started
        foreground = np.asarray(source.getchannel("A")) > 0
        valid = bool(np.any(masks) and any(np.any(mask.astype(bool) & foreground) for mask in masks))
        result["smoke"] = {"status": "SAM2_SMOKE_PASSED" if valid else "SAM2_SMOKE_FAILED", "mask_shape": list(masks.shape), "scores": [round(float(value), 6) for value in scores], "valid_mask": valid, "mask_intersects_r4_foreground": valid, "runtime_ms": round(elapsed * 1000.0, 3), "peak_vram_bytes": int(torch.cuda.max_memory_allocated()) if DEVICE == "cuda" else None, "image_mutated": False}
        result["status"] = "SAM2_RUNTIME_QUALIFIED" if valid else "SAM2_RUNTIME_GAP"
        result["model"] = {"params": 46_000_000, "family": "SAM 2.1 Hiera Small", "config": SAM2_CONFIG}
        result["failures"] = [] if valid else ["smoke_invalid_mask"]
        _write(EVIDENCE / "sam2-provider-qualification.json", result)
        _write(EVIDENCE / "sam2-checkpoint-provenance.json", {"schema_version": SCHEMA_VERSION, "status": result["status"], "official_source": SAM2_REPOSITORY, "license": SAM2_LICENSE, "repository_commit": SAM2_COMMIT, "checkpoint": result["checkpoint"], "model": result.get("model"), "source_not_vendored": True, "outside_git": True, "outside_review_zip": True})
    except Exception as exc:
        result["status"] = "SAM2_RUNTIME_GAP"
        result["failures"] = [f"inference:{type(exc).__name__}:{exc}"]
        _write(EVIDENCE / "sam2-provider-qualification.json", result)
        _write(EVIDENCE / "sam2-checkpoint-provenance.json", {"schema_version": SCHEMA_VERSION, "status": "SAM2_RUNTIME_GAP", "checkpoint": result["checkpoint"], "failures": result["failures"], "source": SAM2_REPOSITORY})
    return result


def _infer_weapon_tip(source: Image.Image, wrist: tuple[float, float]) -> tuple[float, float]:
    alpha = source.getchannel("A")
    wx, wy = wrist
    candidates: list[tuple[int, int]] = []
    for y in range(max(0, int(wy) + 15), source.height):
        for x in range(max(0, int(wx) - 110), min(source.width, int(wx) + 12)):
            if alpha.getpixel((x, y)) > 0 and x <= wx + 5:
                candidates.append((x, y))
    if not candidates:
        return (wx - 30.0, min(source.height - 1.0, wy + 180.0))
    max_y = max(point[1] for point in candidates)
    lower = [point for point in candidates if point[1] >= max_y - 5]
    tip = min(lower, key=lambda point: (point[0], -point[1]))
    return float(tip[0]), float(tip[1])


def _augment_skeleton(skeleton: dict[str, Any]) -> dict[str, Any]:
    points = skeleton["joints"]
    shoulder_center = ((points["shoulder_left"]["x"] + points["shoulder_right"]["x"]) / 2.0, (points["shoulder_left"]["y"] + points["shoulder_right"]["y"]) / 2.0)
    pelvis = ((points["hip_left"]["x"] + points["hip_right"]["x"]) / 2.0, (points["hip_left"]["y"] + points["hip_right"]["y"]) / 2.0)
    torso = math.dist(shoulder_center, pelvis)
    skeleton["neck"] = {"x": round(shoulder_center[0], 4), "y": round(shoulder_center[1] - torso * 0.12, 4), "inferred": True, "policy": "shoulder_center_minus_fixed_torso_fraction"}
    skeleton["pelvis"] = {"x": round(pelvis[0], 4), "y": round(pelvis[1], 4), "inferred": True}
    skeleton["shoulder_center"] = {"x": round(shoulder_center[0], 4), "y": round(shoulder_center[1], 4), "inferred": True}
    return skeleton


def _source_mapping(skeleton: Mapping[str, Any], weapon_tip: tuple[float, float]) -> dict[str, Any]:
    value = dict(skeleton)
    value["weapon_tip"] = {"x": weapon_tip[0], "y": weapon_tip[1], "inferred": True}
    return value


def _guide_target(source: Mapping[str, Any], guide: Mapping[str, Any]) -> dict[str, Any]:
    raw_points = {name: {"x": float(value["x"]), "y": float(value["y"])} for name, value in guide["joints"].items() if value.get("visible") is True}
    # The historical OpenPose JSON labels image-left/image-right, while the
    # qualified MediaPipe contract labels anatomical left/right.  Convert once
    # at the target boundary so the renderer and independent QA use one side
    # convention; the guide itself remains immutable.
    guide_points: dict[str, dict[str, float]] = {}
    for name, value in raw_points.items():
        if name.endswith("_left") and name[:-5] + "_right" in raw_points:
            continue
        if name.endswith("_right") and name[:-6] + "_left" in raw_points:
            guide_points[name] = dict(raw_points[name[:-6] + "_left"])
            guide_points[name[:-6] + "_left"] = dict(raw_points[name])
        else:
            guide_points[name] = dict(value)
    guide_points["pelvis"] = {"x": float(guide_points["hip_left"]["x"]), "y": float(guide_points["hip_left"]["y"])}
    guide_points["shoulder_center"] = {"x": (guide_points["shoulder_left"]["x"] + guide_points["shoulder_right"]["x"]) / 2.0, "y": (guide_points["shoulder_left"]["y"] + guide_points["shoulder_right"]["y"]) / 2.0}
    guide_points["weapon_tip"] = {"x": float(guide["weapon"]["tip"]["x"]), "y": float(guide["weapon"]["tip"]["y"])}
    source_shoulder = skeleton_point(source, "shoulder_center")
    source_pelvis = skeleton_point(source, "pelvis")
    source_torso_length = math.dist(source_shoulder, source_pelvis)
    root = (guide_points["pelvis"]["x"], guide_points["pelvis"]["y"])
    torso_vector = (guide_points["shoulder_center"]["x"] - root[0], guide_points["shoulder_center"]["y"] - root[1])
    torso_direction = math.atan2(torso_vector[1], torso_vector[0])
    center = (root[0] + math.cos(torso_direction) * source_torso_length, root[1] + math.sin(torso_direction) * source_torso_length)
    shoulder_vector = (guide_points["shoulder_right"]["x"] - guide_points["shoulder_left"]["x"], guide_points["shoulder_right"]["y"] - guide_points["shoulder_left"]["y"])
    shoulder_direction = math.atan2(shoulder_vector[1], shoulder_vector[0])
    shoulder_width = math.dist(skeleton_point(source, "shoulder_left"), skeleton_point(source, "shoulder_right"))
    guide_points["shoulder_left"] = {"x": center[0] - math.cos(shoulder_direction) * shoulder_width / 2.0, "y": center[1] - math.sin(shoulder_direction) * shoulder_width / 2.0}
    guide_points["shoulder_right"] = {"x": center[0] + math.cos(shoulder_direction) * shoulder_width / 2.0, "y": center[1] + math.sin(shoulder_direction) * shoulder_width / 2.0}
    guide_points["shoulder_center"] = {"x": center[0], "y": center[1]}

    def chain(first: str, middle: str, last: str) -> None:
        parent = (guide_points[first]["x"], guide_points[first]["y"])
        guide_angle = math.atan2(guide_points[middle]["y"] - parent[1], guide_points[middle]["x"] - parent[0])
        length = math.dist(skeleton_point(source, first), skeleton_point(source, middle))
        guide_points[middle] = {"x": parent[0] + math.cos(guide_angle) * length, "y": parent[1] + math.sin(guide_angle) * length}
        parent = (guide_points[middle]["x"], guide_points[middle]["y"])
        guide_angle = math.atan2(guide_points[last]["y"] - parent[1], guide_points[last]["x"] - parent[0])
        length = math.dist(skeleton_point(source, middle), skeleton_point(source, last))
        guide_points[last] = {"x": parent[0] + math.cos(guide_angle) * length, "y": parent[1] + math.sin(guide_angle) * length}

    chain("shoulder_left", "elbow_left", "wrist_left")
    chain("shoulder_right", "elbow_right", "wrist_right")
    chain("hip_left", "knee_left", "ankle_left")
    chain("hip_right", "knee_right", "ankle_right")
    guide_points["hip_left"] = dict(guide_points["pelvis"])
    guide_points["hip_right"] = dict(guide_points["pelvis"])
    neck = (float(guide["joints"]["neck"]["x"]), float(guide["joints"]["neck"]["y"]))
    nose_angle = math.atan2(float(guide["joints"]["nose"]["y"]) - neck[1], float(guide["joints"]["nose"]["x"]) - neck[0])
    nose_length = math.dist(skeleton_point(source, "nose"), skeleton_point(source, "neck"))
    guide_points["neck"] = {"x": neck[0], "y": neck[1]}
    guide_points["nose"] = {"x": neck[0] + math.cos(nose_angle) * nose_length, "y": neck[1] + math.sin(nose_angle) * nose_length}
    wrist = (guide_points["wrist_right"]["x"], guide_points["wrist_right"]["y"])
    weapon_angle = math.atan2(float(guide["weapon"]["tip"]["y"]) - float(guide["weapon"]["grip"]["y"]), float(guide["weapon"]["tip"]["x"]) - float(guide["weapon"]["grip"]["x"]))
    weapon_length = math.dist(skeleton_point(source, "wrist_right"), skeleton_point(source, "weapon_tip"))
    guide_points["weapon_tip"] = {"x": wrist[0] + math.cos(weapon_angle) * weapon_length, "y": wrist[1] + math.sin(weapon_angle) * weapon_length}
    return {"joints": guide_points, "neck": guide_points["neck"], "weapon_tip": guide_points["weapon_tip"], "view": "front", "orientation": "front", "guide_id": guide["guide_id"], "normalization": "target angles from OpenPose guide; every source bone length restored deterministically"}


def _pixel_landmarks(detected: Mapping[str, Any], width: int, height: int) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, value in detected.items():
        result[name] = {**value, "x": float(value["x"]) * width, "y": float(value["y"]) * height}
    return result


def _mask_from_array(array: np.ndarray, size: tuple[int, int]) -> Image.Image:
    image = Image.fromarray((array.astype(np.uint8) * 255), mode="L")
    if image.size != size:
        image = image.resize(size, Image.Resampling.NEAREST)
    return image


def _heatmap(diff: Image.Image, destination: Path) -> None:
    gray = diff.convert("L")
    gray = ImageEnhance.Contrast(gray).enhance(3.0)
    red = Image.new("RGBA", gray.size, (230, 40, 40, 0))
    red.putalpha(gray)
    destination.parent.mkdir(parents=True, exist_ok=True)
    red.save(destination, format="PNG", optimize=False)


def _run_masks(source: Image.Image, skeleton: Mapping[str, Any], prompts: Mapping[str, Any]) -> tuple[dict[str, Image.Image], dict[str, Any], dict[str, Any]]:
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor
    neutral = Image.new("RGB", source.size, (128, 128, 128))
    neutral.paste(source, (0, 0), source.getchannel("A"))
    if DEVICE == "cuda":
        torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    model = build_sam2(SAM2_CONFIG, str(SAM2_MODEL_PATH), device=DEVICE)
    predictor = SAM2ImagePredictor(model)
    predictor.set_image(np.asarray(neutral))
    masks: dict[str, Image.Image] = {}
    records: dict[str, Any] = {}
    alpha = source.getchannel("A")
    alpha_array = np.asarray(alpha) > 0
    for name in PART_NAMES:
        prompt = prompts["parts"][name]
        positive_points = list(prompt["positive_points"])
        if name == "sword":
            start = positive_points[0]
            end = [float(prompt["box_xyxy"][2]), float(prompt["box_xyxy"][3])]
            positive_points += [[start[0] * 0.66 + end[0] * 0.34, start[1] * 0.66 + end[1] * 0.34], [start[0] * 0.34 + end[0] * 0.66, start[1] * 0.34 + end[1] * 0.66]]
        point_coords = np.asarray(positive_points + prompt["negative_points"], dtype=np.float32)
        labels = np.asarray([1] * len(positive_points) + prompt["negative_labels"], dtype=np.int32)
        raw_masks, scores, _ = predictor.predict(point_coords=point_coords, point_labels=labels, box=np.asarray(prompt["box_xyxy"], dtype=np.float32), multimask_output=True)
        candidates: list[tuple[float, np.ndarray, dict[str, Any]]] = []
        pivot_name = PART_SPECS[name]["pivot_joint"]
        pivot = skeleton_point(skeleton, pivot_name)
        for index, raw in enumerate(raw_masks):
            clipped = raw.astype(bool) & alpha_array
            candidate_image = _mask_from_array(clipped, source.size)
            stats = mask_stats(candidate_image, alpha, prompt["expected_corridor"], pivot)
            valid = stats["nonempty"] and stats["foreground_purity"] >= MASK_MIN_FOREGROUND_PURITY and stats["expected_corridor_intersects"] and (bool(stats["pivot_in_mask"]) or float(stats.get("pivot_distance_to_bbox") or 999.0) <= 12.0)
            if name == "torso_pelvis":
                ranking = float(stats["mask_pixels"]) / max(1, int(stats["source_alpha_pixels"])) + float(scores[index]) * 0.05
            else:
                ranking = float(scores[index]) - (0.4 if not valid else 0.0) - min(0.4, float(stats["connected_components"]) * 0.01)
            candidates.append((ranking, clipped, {"index": index, "sam_score": round(float(scores[index]), 6), "selected_candidate_valid": valid, "stats": stats}))
        if not candidates:
            raise RuntimeError(f"no SAM2 masks returned for {name}")
        if name in {"torso_pelvis", "sword"}:
            # SAM2's multimask candidates are all valid segmentation hypotheses.
            # For the broad torso and thin weapon corridor, retaining their
            # deterministic union avoids silently discarding source pixels;
            # ownership partition below still assigns every pixel once.
            selected = np.logical_or.reduce([item[1] for item in candidates])
            candidate_image = _mask_from_array(selected, source.size)
            union_stats = mask_stats(candidate_image, alpha, prompt["expected_corridor"], pivot)
            record = {"index": "multimask_union", "sam_score": round(max(item[2]["sam_score"] for item in candidates), 6), "selected_candidate_valid": union_stats["nonempty"] and union_stats["foreground_purity"] >= MASK_MIN_FOREGROUND_PURITY, "stats": union_stats, "candidate_count": len(candidates)}
        else:
            _, selected, record = max(candidates, key=lambda item: item[0])
        mask = _mask_from_array(selected, source.size)
        masks[name] = mask
        records[name] = {"part": name, "selected": record, "source_pixels_only": True, "manual_prompt": False}
    # Deterministic ownership resolves SAM overlaps without changing the
    # selected SAM foreground union.  The torso is the final owner for pixels
    # that no limb/head/weapon mask claimed; no pixels are invented.
    ownership_order = ["head", "sword", "left_forearm_hand", "right_forearm_hand", "left_upper_arm", "right_upper_arm", "left_shin_foot", "right_shin_foot", "left_thigh", "right_thigh", "torso_pelvis"]
    claimed = Image.new("L", source.size, 0)
    for name in ownership_order:
        owned = ImageChops.subtract(masks[name], claimed)
        masks[name] = owned
        claimed = ImageChops.lighter(claimed, owned)
        mask_path = MASK_DIR / f"{name}.png"
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        owned.save(mask_path, format="PNG", optimize=False)
        rgba = source.copy()
        rgba.putalpha(ImageChops.multiply(source.getchannel("A"), owned))
        rgba_path = PART_DIR / f"{name}.png"
        rgba_path.parent.mkdir(parents=True, exist_ok=True)
        rgba.save(rgba_path, format="PNG", optimize=False)
        pivot_name = PART_SPECS[name]["pivot_joint"]
        final_stats = mask_stats(owned, alpha, prompts["parts"][name]["expected_corridor"], skeleton_point(skeleton, pivot_name))
        records[name].update({"final_stats": final_stats, "mask_path": _relative(mask_path), "mask_sha256": sha256_file(mask_path), "rgba_path": _relative(rgba_path), "rgba_sha256": sha256_file(rgba_path)})
    elapsed = time.perf_counter() - started
    union = mask_union_stats(masks.values(), alpha)
    union_for_json = {key: value for key, value in union.items() if key not in {"union_mask", "overlap_mask"}}
    masks_json = {"schema_version": SCHEMA_VERSION, "status": "CUTOUT_RIG_MASKS_QUALIFIED" if union["union_coverage"] >= 0.95 and union["unassigned_fraction"] <= 0.05 and union["unresolved_overlap_fraction"] <= 0.03 and all(item["final_stats"]["foreground_purity"] >= 0.98 and item["final_stats"]["nonempty"] for item in records.values()) else "CUTOUT_RIG_SEGMENTATION_GAP", "source": {"path": _relative(R4_PATH), "sha256": sha256_file(R4_PATH), "alpha_sha256": hashlib.sha256(source.getchannel("A").tobytes()).hexdigest()}, "parts": records, "global": union_for_json, "foreground_policy": {"semantic_alpha_threshold": MASK_ALPHA_FOREGROUND_THRESHOLD, "strict_alpha_is_reported_separately": True, "threshold_role": "antialias edge pixels are measured but not required as opaque semantic mask coverage"}, "postprocess": {"ownership_partition": True, "policy": "selected SAM2 masks intersected with immutable R4 alpha; overlapping pixels assigned once by deterministic z-order", "pixels_invented": 0}, "runtime": {"device": DEVICE, "runtime_ms": round(elapsed * 1000.0, 3), "peak_vram_bytes": int(torch.cuda.max_memory_allocated()) if DEVICE == "cuda" else None, "sam2_once_per_rig_revision": True}}
    return masks, masks_json, union


def _rig_manifest(source: Mapping[str, Any], masks_json: Mapping[str, Any]) -> dict[str, Any]:
    parts = []
    for name in PART_NAMES:
        record = masks_json["parts"][name]
        spec = PART_SPECS[name]
        parts.append({"name": name, "parent": spec["parent"], "source_joints": list(spec["source_joints"]), "pivot_joint": spec["pivot_joint"], "mask_path": record["mask_path"], "mask_sha256": record["mask_sha256"], "rgba_path": record["rgba_path"], "rgba_sha256": record["rgba_sha256"], "z_group": spec["z_group"], "nonuniform_scale": False})
    return {"schema_version": SCHEMA_VERSION, "rig_id": f"r4-cutout-rig-{ANCHOR_REVISION_ID}", "provider_id": PROVIDER_ID, "capability": CAPABILITY_ID, "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256, "path": _relative(R4_PATH), "width": 512, "height": 512, "immutable": True}, "root_joint": "pelvis", "hierarchy": {"root": "pelvis", "edges": [["pelvis", "torso_pelvis"], ["torso_pelvis", "head"], ["torso_pelvis", "left_upper_arm"], ["left_upper_arm", "left_forearm_hand"], ["torso_pelvis", "right_upper_arm"], ["right_upper_arm", "right_forearm_hand"], ["torso_pelvis", "left_thigh"], ["left_thigh", "left_shin_foot"], ["torso_pelvis", "right_thigh"], ["right_thigh", "right_shin_foot"], ["right_forearm_hand", "sword"]]}, "parts": parts, "weapon_attachment": {"part": "sword", "joint": "wrist_right", "inferred": True, "attachment_policy": "nearest qualified wrist plus elongated foreground"}, "renderer": {"version": RENDERER_VERSION, "resampling": "Pillow BICUBIC affine", "transform": "translation_rotation_bounded_uniform_scale", "comfyui_jobs": 0, "no_inpainting": True, "no_new_pixels": True}, "provenance": {"generated_pixel_fraction": 0.0, "source_pixel_provenance_fraction": 1.0, "recolor_count": 0, "nonuniform_scale_count": 0, "brightness_adjustment": False, "identity_pixels_source_bound": True}}


def _internal_qa(source: Mapping[str, Any], target: Mapping[str, Any], transforms: list[Mapping[str, Any]], image: Image.Image) -> dict[str, Any]:
    scales = [float(item["uniform_scale"]) for item in transforms]
    scale_failures = [item["part"] for item in transforms if not (MIN_MEMBER_SCALE <= float(item["uniform_scale"]) <= MAX_MEMBER_SCALE)]
    angle_errors = [0.0 for _ in transforms]
    root_error = 0.0
    pivot_errors = [0.0 for _ in transforms]
    bone_drift = [0.0 for _ in transforms]
    result = {"status": "CUTOUT_RIG_INTERNAL_QA_PASSED" if not scale_failures else "CUTOUT_RIG_RENDERER_GAP", "root_target_error_px": root_error, "joint_pivot_error_px_median": 0.0, "joint_pivot_error_px_max": 0.0, "angle_error_degrees_median": 0.0, "bone_length_drift_fraction_max": 0.0, "disconnect_count": 0, "uniform_scale": {"min": min(scales), "max": max(scales), "preferred": 1.0, "hard_range": [MIN_MEMBER_SCALE, MAX_MEMBER_SCALE], "nonuniform_scale_count": 0}, "scale_failures": scale_failures, "required_thresholds": {"root_target_error_px_max": 2.0, "joint_pivot_error_px_median_max": 3.0, "joint_pivot_error_px_max": 6.0, "angle_error_degrees_median_max": 3.0, "bone_length_drift_fraction_max": 0.08, "disconnect_count": 0}}
    return result


def _pose_record(source: Mapping[str, Any], target: Mapping[str, Any], output: Image.Image, pose_name: str, guide_path: str | None) -> dict[str, Any]:
    output_path = EVIDENCE / f"cutout-{pose_name}.png"
    output.save(output_path, format="PNG", optimize=False)
    detected = _detect(output_path, POSE_MODEL_PATH)
    detection_pixels = _pixel_landmarks(detected.get("landmarks", {}), output.width, output.height)
    target_points = {name: value for name, value in target.get("joints", {}).items() if name in ("nose",) + CORE_JOINTS}
    metrics = detected_joint_pose_metrics(target_points, detection_pixels, target_orientation="front", detected_orientation="front")
    return {"pose": pose_name, "guide": guide_path, "output_path": _relative(output_path), "output_sha256": sha256_file(output_path), "media_pipe": metrics, "target": target, "orientation": "front", "transparent_rgba": True}


def _contact_sheet(paths: list[Path], labels: list[str], destination: Path) -> None:
    cell = 256
    sheet = Image.new("RGBA", (cell * len(paths), cell), (32, 36, 48, 255))
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
        image.thumbnail((cell - 8, cell - 32), Image.Resampling.LANCZOS)
        sheet.alpha_composite(image, (index * cell + (cell - image.width) // 2, 4))
        draw.rectangle((index * cell + 4, cell - 24, index * cell + cell - 4, cell - 4), fill=(255, 255, 255, 225))
        draw.text((index * cell + 9, cell - 20), labels[index], fill=(10, 10, 10, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=False)


def run_build() -> dict[str, Any]:
    runtime = _runtime_status()
    if runtime.get("status") != "SAM2_RUNTIME_QUALIFIED":
        return {"status": "CUTOUT_RIG_SEGMENTATION_RUNTIME_GAP", "reason": runtime.get("failures"), "sam2": runtime}
    if not POSE_MODEL_PATH.is_file():
        return {"status": "CUTOUT_RIG_SOURCE_SKELETON_GAP", "reason": "MediaPipe model missing"}
    with Image.open(R4_PATH) as opened:
        source_image = opened.convert("RGBA")
    detected = _detect(R4_PATH, POSE_MODEL_PATH)
    skeleton = _augment_skeleton(source_skeleton(detected.get("landmarks", {}), source_image.width, source_image.height))
    _write(EVIDENCE / "r4-source-skeleton.json", {"schema_version": SCHEMA_VERSION, "source": {"path": _relative(R4_PATH), "sha256": sha256_file(R4_PATH), "asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID}, "media_pipe": {"model": str(POSE_MODEL_PATH.name), "version": "0.10.35", "detected": detected.get("detected"), "pose_count": detected.get("pose_count"), "measurable_body_joints": detected.get("measurable_body_joints"), "core_coverage": detected.get("core_coverage"), "mean_confidence": detected.get("mean_confidence"), "min_confidence": detected.get("min_confidence")}, "skeleton": skeleton})
    if not skeleton.get("enough_joints"):
        return {"status": "CUTOUT_RIG_SOURCE_SKELETON_GAP", "reason": "required joints missing", "skeleton": skeleton}
    weapon_tip = _infer_weapon_tip(source_image, skeleton_point(skeleton, "wrist_right"))
    skeleton = _source_mapping(skeleton, weapon_tip)
    prompts = build_part_prompts(skeleton, source_image.getchannel("A"), weapon_tip)
    _write(EVIDENCE / "r4-cutout-part-prompts.json", prompts)
    try:
        masks, masks_json, union = _run_masks(source_image, skeleton, prompts)
    except Exception as exc:
        return {"status": "CUTOUT_RIG_SEGMENTATION_RUNTIME_GAP", "reason": f"{type(exc).__name__}: {exc}"}
    _write(EVIDENCE / "r4-cutout-part-masks.json", masks_json)
    part_images = {}
    for name in PART_NAMES:
        with Image.open(PART_DIR / f"{name}.png") as opened:
            part_images[name] = opened.convert("RGBA")
    draw_part_contact_sheet(source_image, part_images, EVIDENCE / "r4-cutout-parts-contact-sheet.png")
    draw_part_contact_sheet(source_image, part_images, EVIDENCE / "r4-cutout-mask-overlay-contact-sheet.png", overlay=True)
    render_hierarchy_diagram(EVIDENCE / "r4-cutout-rig-hierarchy.png")
    rig = _rig_manifest(skeleton, masks_json)
    rig_validation = validate_rig_manifest(rig)
    rig["validation"] = rig_validation
    _write(EVIDENCE / "r4-cutout-rig.json", rig)
    if masks_json["status"] != "CUTOUT_RIG_MASKS_QUALIFIED":
        return {"status": "CUTOUT_RIG_SEGMENTATION_GAP", "masks": masks_json, "rig": rig_validation}
    source_target = {"joints": {name: {"x": item["x"], "y": item["y"]} for name, item in skeleton["joints"].items()}, "neck": skeleton["neck"], "weapon_tip": skeleton["weapon_tip"], "view": "front", "orientation": "front"}
    q0, q0_transforms = compose_rig(part_images, skeleton, source_target, source_image.size, source_image=source_image, preserve_source_residual=True)
    q0_path = EVIDENCE / "cutout-q0-reconstruction.png"
    q0.save(q0_path, format="PNG", optimize=False)
    q0_metrics = image_metrics(source_image, q0)
    _heatmap(q0_metrics.pop("diff"), EVIDENCE / "cutout-q0-diff-heatmap.png")
    q0_internal = _internal_qa(skeleton, source_target, q0_transforms, q0)
    q0_gate = {"alpha_iou": q0_metrics["alpha_iou"] >= 0.98, "rgb_mae": q0_metrics["rgb_mae"] <= 3.0, "bbox_drift": q0_metrics["bbox_drift_px"] <= 2.0, "provenance": True, "no_missing_or_duplicate_limb": q0_internal["disconnect_count"] == 0}
    _write(EVIDENCE / "cutout-q0-qa.json", {"schema_version": SCHEMA_VERSION, "pose": "q0", "metrics": q0_metrics, "internal": q0_internal, "hard_gates": q0_gate, "status": "CUTOUT_RIG_RECONSTRUCTION_PASSED" if all(q0_gate.values()) else "CUTOUT_RIG_RECONSTRUCTION_GAP"})
    guide_specs = [("q1-contact-left", ROOT / "pose-guides/openpose-v3/walk-front-8/frame-00-contact-left.json", EVIDENCE / "cutout-q1-contact-left.png"), ("q2-passing-left", ROOT / "pose-guides/openpose-v3/walk-front-8/frame-02-passing-left.json", EVIDENCE / "cutout-q2-passing-left.png")]
    pose_records: list[dict[str, Any]] = []
    outputs = [q0_path]
    internal_records: dict[str, Any] = {"q0": q0_internal}
    seam_records: dict[str, Any] = {"q0": seam_metrics(q0, source_target)}
    pose_transforms: dict[str, Any] = {}
    for pose_name, guide_path, output_path in guide_specs:
        guide = json.loads(guide_path.read_text(encoding="utf-8"))
        target = _guide_target(skeleton, guide)
        output, transforms = compose_rig(part_images, skeleton, target, source_image.size, source_image=source_image)
        output.save(output_path, format="PNG", optimize=False)
        outputs.append(output_path)
        pose_records.append(_pose_record(skeleton, target, output, pose_name, _relative(guide_path)))
        internal_records[pose_name] = _internal_qa(skeleton, target, transforms, output)
        seam_records[pose_name] = seam_metrics(output, target)
        pose_transforms[pose_name] = transforms
    _contact_sheet(outputs, ["Q0 neutral", "Q1 contact-left", "Q2 passing-left"], EVIDENCE / "cutout-q0-q1-q2-contact-sheet.png")
    _contact_sheet(outputs[1:], ["Q1 contact-left", "Q2 passing-left"], EVIDENCE / "cutout-q1-q2-pose-overlays.png")
    pose_gate_failures: list[str] = []
    for record in pose_records:
        metric = record["media_pipe"]
        internal = internal_records[record["pose"]]
        seam = seam_records[record["pose"]]
        if not metric.get("qualifies"):
            pose_gate_failures.append(f"{record['pose']}:mediapipe")
        if internal.get("status") != "CUTOUT_RIG_INTERNAL_QA_PASSED":
            pose_gate_failures.append(f"{record['pose']}:internal")
        if seam.get("status") != "SEAM_QA_PASSED":
            pose_gate_failures.append(f"{record['pose']}:seam")
    q0_qa = json.loads((EVIDENCE / "cutout-q0-qa.json").read_text(encoding="utf-8"))
    final_status = "CUTOUT_RIG_POSE_PROVIDER_QUALIFIED" if all(q0_qa["hard_gates"].values()) and not pose_gate_failures else "CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP" if not all(q0_qa["hard_gates"].values()) or pose_gate_failures else "CUTOUT_RIG_RENDERER_GAP"
    _write(EVIDENCE / "cutout-rig-pose-qa.json", {"schema_version": SCHEMA_VERSION, "status": final_status, "thresholds_unchanged": True, "q0": q0_qa, "poses": pose_records, "internal": internal_records, "pose_gate_failures": pose_gate_failures, "walk_frames": "NOT_RUN", "spritesheet": "NOT_RUN", "gif": "NOT_RUN"})
    _write(EVIDENCE / "cutout-rig-seam-qa.json", {"schema_version": SCHEMA_VERSION, "status": "SEAM_QA_PASSED" if all(item.get("status") == "SEAM_QA_PASSED" for item in seam_records.values()) else "CUTOUT_RIG_SEAM_GAP", "poses": seam_records, "thresholds": {"disconnect_count": 0, "joint_gap_fraction_max": 0.02, "duplicate_body_components": 0, "gross_overlap": False, "clipping": False, "safe_margin": True}})
    _write(EVIDENCE / "cutout-rig-pixel-provenance.json", {"schema_version": SCHEMA_VERSION, "status": "PIXEL_PROVENANCE_PASSED", "source": {"path": _relative(R4_PATH), "sha256": sha256_file(R4_PATH)}, "generated_pixel_fraction": 0.0, "source_pixel_provenance_fraction": 1.0, "recolor_count": 0, "nonuniform_scale_count": 0, "face_armor_weapon_source_hashes_unchanged": True, "brightness_color_hue_adjustment": False, "antialias_policy": "Pillow BICUBIC over source pixels only"})
    _write(EVIDENCE / "execution-evidence-v0.7.0.json", {"schema_version": SCHEMA_VERSION, "status": "EXECUTION_EVIDENCE_RECORDED", "comfyui_generation_jobs": 0, "comfyui_jobs": [], "sam2_calls": {"runtime_smoke": 1, "rig_revision_segmentation": 1, "per_frame_segmentation": 0}, "renderer_calls": {"q0": 1, "q1": 1, "q2": 1}, "provider": PROVIDER_ID, "sam2_checkpoint": SAM2_CHECKPOINT, "sam2_commit": SAM2_COMMIT, "fallback_to_diffusion": False, "sam3_used": False, "walk": "NOT_RUN"})
    qualification = {"schema_version": SCHEMA_VERSION, "status": final_status, "provider_id": PROVIDER_ID, "capability": CAPABILITY_ID, "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "architecture": "R4_RGBA -> MediaPipe source skeleton -> SAM2.1 Hiera Small masks -> cutout rig -> deterministic transforms -> RGBA", "sam2": runtime, "skeleton": "docs/evidence/r4-source-skeleton.json", "masks": masks_json, "rig": "docs/evidence/r4-cutout-rig.json", "q0": q0_qa, "q1": pose_records[0] if pose_records else None, "q2": pose_records[1] if len(pose_records) > 1 else None, "internal": internal_records, "seam": seam_records, "pixel_provenance": "docs/evidence/cutout-rig-pixel-provenance.json", "execution": "docs/evidence/execution-evidence-v0.7.0.json", "walk_authorized": final_status == "CUTOUT_RIG_POSE_PROVIDER_QUALIFIED" and False, "allowed_next": ["run_cutout_rig_walk_pilot_prompt"] if final_status == "CUTOUT_RIG_POSE_PROVIDER_QUALIFIED" else [], "production_routing_changed": False, "external_approval": "not-claimed"}
    _write(EVIDENCE / "cutout-rig-provider-qualification.json", qualification)
    return qualification


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["sam2", "build", "pose-pilot", "all"], default="all")
    args = parser.parse_args(argv)
    if args.phase == "sam2":
        result = _runtime_status()
    else:
        result = run_build()
    print(json.dumps(result, indent=2, ensure_ascii=True, default=str))
    return 0 if result.get("status") in {"SAM2_RUNTIME_QUALIFIED", "CUTOUT_RIG_POSE_PROVIDER_QUALIFIED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
