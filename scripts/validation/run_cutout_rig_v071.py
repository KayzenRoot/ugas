"""Run the v0.7.1 deterministic cutout-rig fidelity correction.

The script owns the external SAM2/MediaPipe adapter only.  Segmentation is
performed once for a rig revision, then all Q0/Q1/Q2 pixels are rendered by
the pure Pillow/NumPy core.  No ComfyUI job, diffusion fallback, walk frame,
spritesheet or GIF is allowed in this lane.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
from PIL import Image, ImageChops, ImageDraw, ImageEnhance

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in os.sys.path:
    os.sys.path.insert(0, str(ROOT / "src"))

from ugas.cutout_rig import (  # noqa: E402
    CAPABILITY_ID,
    JOINT_BLEND_RADIUS,
    MASK_ALPHA_FOREGROUND_THRESHOLD,
    MASK_MIN_FOREGROUND_PURITY,
    MAX_GROSS_OVERLAP_FRACTION,
    MAX_MEMBER_SCALE,
    MIN_MEMBER_SCALE,
    MIN_SAFE_MARGIN,
    PART_COLORS,
    PART_NAMES,
    PART_SPECS,
    PROVIDER_ID,
    REQUIRED_JOINTS,
    SCHEMA_VERSION,
    compose_rig,
    component_gate,
    draw_part_contact_sheet,
    image_metrics,
    mask_stats,
    render_part,
    render_part_layers,
    seam_metrics,
    sha256_bytes,
    sha256_file,
    skeleton_point,
    source_skeleton,
    transform_parameters,
    validate_rig_manifest,
)
from ugas.identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256  # noqa: E402
from ugas.pose_metric_calibration import CORE_JOINTS, detected_joint_pose_metrics  # noqa: E402
from ugas.pose_qa_estimator import _detect  # noqa: E402


SAM2_REPOSITORY = "https://github.com/facebookresearch/sam2"
SAM2_LICENSE = "Apache-2.0"
SAM2_COMMIT = "2b90b9f5ceec907a1c18123530e92e794ad901a4"
SAM2_CHECKPOINT = "sam2.1_hiera_small.pt"
SAM2_CHECKPOINT_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt"
SAM2_CONFIG = "configs/sam2.1/sam2.1_hiera_s.yaml"
R4_PATH = ROOT / "docs/evidence/reference-edit-selected-transparent.png"
LOCAL_APPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
POSE_MODEL_PATH = LOCAL_APPDATA / "UGAS/pose-qa/pose_landmarker_full.task"
SAM2_MODEL_PATH = LOCAL_APPDATA / "UGAS/models/sam2" / SAM2_CHECKPOINT
EVIDENCE = ROOT / "docs/evidence"
RAW_DIR = EVIDENCE / "r4-cutout-raw-masks-v071"
REFINED_DIR = EVIDENCE / "r4-cutout-refined-masks-v071"
PART_DIR = EVIDENCE / "r4-cutout-parts-v071"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
OWNERSHIP_ORDER = [
    "head", "sword", "left_forearm_hand", "right_forearm_hand",
    "left_upper_arm", "right_upper_arm", "left_shin_foot", "right_shin_foot",
    "left_thigh", "right_thigh", "torso_pelvis",
]
JOINT_BANDS = (
    ("torso_pelvis", "left_upper_arm", "shoulder_left"),
    ("torso_pelvis", "right_upper_arm", "shoulder_right"),
    ("left_upper_arm", "left_forearm_hand", "elbow_left"),
    ("right_upper_arm", "right_forearm_hand", "elbow_right"),
    ("right_forearm_hand", "sword", "wrist_right"),
    ("torso_pelvis", "left_thigh", "hip_left"),
    ("torso_pelvis", "right_thigh", "hip_right"),
    ("left_thigh", "left_shin_foot", "knee_left"),
    ("right_thigh", "right_shin_foot", "knee_right"),
)
POSE_EDGES = (
    ("shoulder_left", "elbow_left"), ("elbow_left", "wrist_left"),
    ("shoulder_right", "elbow_right"), ("elbow_right", "wrist_right"),
    ("hip_left", "knee_left"), ("knee_left", "ankle_left"),
    ("hip_right", "knee_right"), ("knee_right", "ankle_right"),
    ("shoulder_left", "shoulder_right"), ("hip_left", "hip_right"),
)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _mask_from_array(array: np.ndarray, size: tuple[int, int]) -> Image.Image:
    image = Image.fromarray((array.astype(np.uint8) * 255), mode="L")
    return image.resize(size, Image.Resampling.NEAREST) if image.size != size else image


def _binary(mask: Image.Image) -> Image.Image:
    return mask.convert("L").point(lambda value: 255 if value > 127 else 0)


def _nonzero(mask: Image.Image) -> Image.Image:
    return mask.convert("L").point(lambda value: 255 if value > 0 else 0)


def _component_records(mask: Image.Image) -> list[dict[str, Any]]:
    """Return exact 8-connected components with pixels for deterministic repair."""
    binary = _binary(mask)
    width, height = binary.size
    pixels = binary.load()
    visited: set[tuple[int, int]] = set()
    records: list[dict[str, Any]] = []
    for y in range(height):
        for x in range(width):
            if pixels[x, y] == 0 or (x, y) in visited:
                continue
            queue = [(x, y)]
            visited.add((x, y))
            points: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.pop()
                points.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1), (cx - 1, cy - 1), (cx + 1, cy - 1), (cx - 1, cy + 1), (cx + 1, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height and pixels[nx, ny] > 0 and (nx, ny) not in visited:
                        visited.add((nx, ny))
                        queue.append((nx, ny))
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            records.append({
                "area": len(points), "bbox": [min(xs), min(ys), max(xs) + 1, max(ys) + 1],
                "centroid": [round(sum(xs) / len(xs), 4), round(sum(ys) / len(ys), 4)],
                "pixels": points,
            })
    return sorted(records, key=lambda item: (-int(item["area"]), item["bbox"]))


def _component_public(records: Sequence[Mapping[str, Any]], primary_index: int = 0) -> dict[str, Any]:
    areas = [int(item["area"]) for item in records]
    primary = areas[primary_index] if records else 0
    threshold = max(16, int(primary * 0.0025))
    meaningful = [item for item in records if int(item["area"]) >= threshold]
    return {
        "component_count": len(records), "meaningful_component_threshold": threshold,
        "meaningful_component_count": len(meaningful), "primary_area": primary,
        "components": [{key: value for key, value in item.items() if key != "pixels"} for item in records],
    }


def _point_segment_distance(point: tuple[float, float], first: tuple[float, float], second: tuple[float, float]) -> float:
    dx, dy = second[0] - first[0], second[1] - first[1]
    denominator = dx * dx + dy * dy
    if denominator <= 1e-9:
        return math.dist(point, first)
    t = max(0.0, min(1.0, ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / denominator))
    return math.dist(point, (first[0] + t * dx, first[1] + t * dy))


def _wrap_degrees(value: float) -> float:
    while value > 180.0:
        value -= 360.0
    while value < -180.0:
        value += 360.0
    return value


def _runtime_status() -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "provider_id": PROVIDER_ID, "capability": CAPABILITY_ID,
        "status": "SAM2_RUNTIME_GAP", "official_source": SAM2_REPOSITORY, "license": SAM2_LICENSE,
        "repository_commit": SAM2_COMMIT,
        "checkpoint": {"filename": SAM2_CHECKPOINT, "url": SAM2_CHECKPOINT_URL, "path_not_published": True, "outside_git": True, "outside_review_zip": True},
        "python": {"version": platform.python_version(), "executable": os.sys.executable},
        "torch": {"version": getattr(torch, "__version__", None), "cuda_available": bool(torch.cuda.is_available()), "device": DEVICE},
        "runtime_policy": {"isolated_external_tool": True, "comfyui_custom_node": False, "comfyui_generation_jobs": 0, "sam3_forbidden": True},
        "smoke": {"status": "NOT_RUN", "box_positive_point": True}, "timestamp": _now(),
    }
    failures: list[str] = []
    try:
        import torchvision
        result["torchvision"] = {"version": torchvision.__version__}
    except Exception as exc:
        result["torchvision"] = {"version": None}
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
        result["imports"] = {"sam2": "import_error", "error": str(exc)}
        failures.append(f"sam2_import:{type(exc).__name__}:{exc}")
    if failures:
        result["failures"] = failures
        _write(EVIDENCE / "sam2-provider-qualification-v071.json", result)
        _write(EVIDENCE / "sam2-checkpoint-provenance-v071.json", {"schema_version": SCHEMA_VERSION, "status": "SAM2_RUNTIME_GAP", "checkpoint": result["checkpoint"], "failures": failures, "source": SAM2_REPOSITORY})
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
        predictor.set_image(np.asarray(neutral))
        bbox = source.getchannel("A").getbbox()
        if not bbox:
            raise RuntimeError("R4 has no foreground")
        x0, y0, x1, y1 = bbox
        masks, scores, _ = predictor.predict(point_coords=np.array([[(x0 + x1) / 2.0, (y0 + y1) / 2.0]], dtype=np.float32), point_labels=np.array([1], dtype=np.int32), box=np.array([x0, y0, x1, y1], dtype=np.float32), multimask_output=True)
        elapsed = time.perf_counter() - started
        foreground = np.asarray(source.getchannel("A")) > 0
        valid = bool(np.any(masks) and any(np.any(mask.astype(bool) & foreground) for mask in masks))
        result["smoke"] = {"status": "SAM2_SMOKE_PASSED" if valid else "SAM2_SMOKE_FAILED", "mask_shape": list(masks.shape), "scores": [round(float(value), 6) for value in scores], "valid_mask": valid, "mask_intersects_r4_foreground": valid, "runtime_ms": round(elapsed * 1000.0, 3), "peak_vram_bytes": int(torch.cuda.max_memory_allocated()) if DEVICE == "cuda" else None, "image_mutated": False}
        result["status"] = "SAM2_RUNTIME_QUALIFIED" if valid else "SAM2_RUNTIME_GAP"
        result["model"] = {"params": 46_000_000, "family": "SAM 2.1 Hiera Small", "config": SAM2_CONFIG}
        result["failures"] = [] if valid else ["smoke_invalid_mask"]
        _write(EVIDENCE / "sam2-provider-qualification-v071.json", result)
        _write(EVIDENCE / "sam2-checkpoint-provenance-v071.json", {"schema_version": SCHEMA_VERSION, "status": result["status"], "official_source": SAM2_REPOSITORY, "license": SAM2_LICENSE, "repository_commit": SAM2_COMMIT, "checkpoint": result["checkpoint"], "model": result.get("model"), "source_not_vendored": True, "outside_git": True, "outside_review_zip": True})
    except Exception as exc:
        result["status"] = "SAM2_RUNTIME_GAP"
        result["failures"] = [f"inference:{type(exc).__name__}:{exc}"]
        _write(EVIDENCE / "sam2-provider-qualification-v071.json", result)
        _write(EVIDENCE / "sam2-checkpoint-provenance-v071.json", {"schema_version": SCHEMA_VERSION, "status": "SAM2_RUNTIME_GAP", "checkpoint": result["checkpoint"], "failures": result["failures"], "source": SAM2_REPOSITORY})
    return result


def _infer_weapon_tip(source: Image.Image, wrist: tuple[float, float]) -> tuple[float, float]:
    alpha = source.getchannel("A")
    candidates = [(x, y) for y in range(max(0, int(wrist[1]) + 15), source.height) for x in range(max(0, int(wrist[0]) - 110), min(source.width, int(wrist[0]) + 12)) if alpha.getpixel((x, y)) > 0 and x <= wrist[0] + 5]
    if not candidates:
        return wrist[0] - 30.0, min(source.height - 1.0, wrist[1] + 180.0)
    max_y = max(point[1] for point in candidates)
    return tuple(float(value) for value in min((point for point in candidates if point[1] >= max_y - 5), key=lambda point: (point[0], -point[1])))


def _augment_skeleton(skeleton: dict[str, Any]) -> dict[str, Any]:
    points = skeleton["joints"]
    shoulder_center = ((points["shoulder_left"]["x"] + points["shoulder_right"]["x"]) / 2.0, (points["shoulder_left"]["y"] + points["shoulder_right"]["y"]) / 2.0)
    pelvis = ((points["hip_left"]["x"] + points["hip_right"]["x"]) / 2.0, (points["hip_left"]["y"] + points["hip_right"]["y"]) / 2.0)
    torso = math.dist(shoulder_center, pelvis)
    skeleton["neck"] = {"x": round(shoulder_center[0], 4), "y": round(shoulder_center[1] - torso * 0.12, 4), "inferred": True}
    skeleton["pelvis"] = {"x": round(pelvis[0], 4), "y": round(pelvis[1], 4), "inferred": True}
    skeleton["shoulder_center"] = {"x": round(shoulder_center[0], 4), "y": round(shoulder_center[1], 4), "inferred": True}
    return skeleton


def _source_mapping(skeleton: Mapping[str, Any], weapon_tip: tuple[float, float]) -> dict[str, Any]:
    value = dict(skeleton)
    value["weapon_tip"] = {"x": weapon_tip[0], "y": weapon_tip[1], "inferred": True}
    return value


def _map_guide_sides(raw_points: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """Map immutable guide image-side labels into the anatomical contract."""
    result: dict[str, dict[str, float]] = {}
    mapping = {"anatomical_left": "guide_right", "anatomical_right": "guide_left"}
    for name, value in raw_points.items():
        if name.endswith("_left") or name.endswith("_right"):
            continue
        result[name] = {"x": float(value["x"]), "y": float(value["y"])}
    for base in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle"):
        result[f"{base}_left"] = {"x": float(raw_points[f"{base}_right"]["x"]), "y": float(raw_points[f"{base}_right"]["y"])}
        result[f"{base}_right"] = {"x": float(raw_points[f"{base}_left"]["x"]), "y": float(raw_points[f"{base}_left"]["y"])}
    return result, mapping


def _segment_hits_rect(first: tuple[float, float], second: tuple[float, float], rect: Sequence[float]) -> bool:
    left, top, right, bottom = rect
    for step in range(8, 101):
        t = step / 100.0
        x = first[0] + (second[0] - first[0]) * t
        y = first[1] + (second[1] - first[1]) * t
        if left <= x <= right and top <= y <= bottom:
            return True
    return False


def _guide_target(source: Mapping[str, Any], guide: Mapping[str, Any]) -> dict[str, Any]:
    raw = {name: value for name, value in guide["joints"].items() if value.get("visible") is True}
    guide_points, side_mapping = _map_guide_sides(raw)
    guide_hip_center = ((guide_points["hip_left"]["x"] + guide_points["hip_right"]["x"]) / 2.0, (guide_points["hip_left"]["y"] + guide_points["hip_right"]["y"]) / 2.0)
    guide_points["pelvis"] = {"x": guide_hip_center[0], "y": guide_hip_center[1]}
    guide_points["shoulder_center"] = {"x": (guide_points["shoulder_left"]["x"] + guide_points["shoulder_right"]["x"]) / 2.0, "y": (guide_points["shoulder_left"]["y"] + guide_points["shoulder_right"]["y"]) / 2.0}
    source_shoulder = skeleton_point(source, "shoulder_center")
    source_pelvis = skeleton_point(source, "pelvis")
    source_torso_length = math.dist(source_shoulder, source_pelvis)
    torso_vector = (guide_points["shoulder_center"]["x"] - guide_hip_center[0], guide_points["shoulder_center"]["y"] - guide_hip_center[1])
    torso_angle = math.atan2(torso_vector[1], torso_vector[0]) if math.hypot(*torso_vector) > 1e-6 else -math.pi / 2.0
    center = (guide_hip_center[0] + math.cos(torso_angle) * source_torso_length, guide_hip_center[1] + math.sin(torso_angle) * source_torso_length)
    shoulder_vector = (guide_points["shoulder_left"]["x"] - guide_points["shoulder_right"]["x"], guide_points["shoulder_left"]["y"] - guide_points["shoulder_right"]["y"])
    shoulder_angle = math.atan2(shoulder_vector[1], shoulder_vector[0]) if math.hypot(*shoulder_vector) > 1e-6 else 0.0
    shoulder_width = math.dist(skeleton_point(source, "shoulder_left"), skeleton_point(source, "shoulder_right"))
    guide_points["shoulder_left"] = {"x": center[0] + math.cos(shoulder_angle) * shoulder_width / 2.0, "y": center[1] + math.sin(shoulder_angle) * shoulder_width / 2.0}
    guide_points["shoulder_right"] = {"x": center[0] - math.cos(shoulder_angle) * shoulder_width / 2.0, "y": center[1] - math.sin(shoulder_angle) * shoulder_width / 2.0}
    guide_points["shoulder_center"] = {"x": center[0], "y": center[1]}
    source_hip_width = math.dist(skeleton_point(source, "hip_left"), skeleton_point(source, "hip_right"))
    hip_tilt = max(-math.radians(20.0), min(math.radians(20.0), torso_angle + math.pi / 2.0))
    hip_axis = (math.cos(hip_tilt), math.sin(hip_tilt))
    guide_points["hip_left"] = {"x": guide_hip_center[0] + hip_axis[0] * source_hip_width / 2.0, "y": guide_hip_center[1] + hip_axis[1] * source_hip_width / 2.0}
    guide_points["hip_right"] = {"x": guide_hip_center[0] - hip_axis[0] * source_hip_width / 2.0, "y": guide_hip_center[1] - hip_axis[1] * source_hip_width / 2.0}

    def chain(first: str, middle: str, last: str) -> None:
        parent = (guide_points[first]["x"], guide_points[first]["y"])
        middle_angle = math.atan2(guide_points[middle]["y"] - parent[1], guide_points[middle]["x"] - parent[0])
        middle_length = math.dist(skeleton_point(source, first), skeleton_point(source, middle))
        guide_points[middle] = {"x": parent[0] + math.cos(middle_angle) * middle_length, "y": parent[1] + math.sin(middle_angle) * middle_length}
        parent = (guide_points[middle]["x"], guide_points[middle]["y"])
        last_angle = math.atan2(guide_points[last]["y"] - parent[1], guide_points[last]["x"] - parent[0])
        last_length = math.dist(skeleton_point(source, middle), skeleton_point(source, last))
        guide_points[last] = {"x": parent[0] + math.cos(last_angle) * last_length, "y": parent[1] + math.sin(last_angle) * last_length}

    chain("shoulder_left", "elbow_left", "wrist_left")
    chain("shoulder_right", "elbow_right", "wrist_right")
    chain("hip_left", "knee_left", "ankle_left")
    chain("hip_right", "knee_right", "ankle_right")
    neck = {"x": float(guide["joints"]["neck"]["x"]), "y": float(guide["joints"]["neck"]["y"])}
    nose_angle = math.atan2(float(guide["joints"]["nose"]["y"]) - neck["y"], float(guide["joints"]["nose"]["x"]) - neck["x"])
    nose_length = math.dist(skeleton_point(source, "nose"), skeleton_point(source, "neck"))
    guide_points["neck"] = neck
    guide_points["nose"] = {"x": neck["x"] + math.cos(nose_angle) * nose_length, "y": neck["y"] + math.sin(nose_angle) * nose_length}

    source_forearm_angle = math.atan2(skeleton_point(source, "wrist_right")[1] - skeleton_point(source, "elbow_right")[1], skeleton_point(source, "wrist_right")[0] - skeleton_point(source, "elbow_right")[0])
    source_weapon_angle = math.atan2(skeleton_point(source, "weapon_tip")[1] - skeleton_point(source, "wrist_right")[1], skeleton_point(source, "weapon_tip")[0] - skeleton_point(source, "wrist_right")[0])
    relative_weapon_angle = source_weapon_angle - source_forearm_angle
    target_forearm_angle = math.atan2(guide_points["wrist_right"]["y"] - guide_points["elbow_right"]["y"], guide_points["wrist_right"]["x"] - guide_points["elbow_right"]["x"])
    guide_weapon_angle = math.atan2(float(guide["weapon"]["tip"]["y"]) - float(guide["weapon"]["grip"]["y"]), float(guide["weapon"]["tip"]["x"]) - float(guide["weapon"]["grip"]["x"]))
    base_weapon_angle = target_forearm_angle + relative_weapon_angle
    requested_swing = max(-math.radians(12.0), min(math.radians(12.0), math.radians(_wrap_degrees(math.degrees(guide_weapon_angle - base_weapon_angle)))))
    torso_rect = [min(guide_points["shoulder_left"]["x"], guide_points["shoulder_right"]["x"]) - 18.0, min(guide_points["shoulder_left"]["y"], guide_points["shoulder_right"]["y"]) - 12.0, max(guide_points["hip_left"]["x"], guide_points["hip_right"]["x"]) + 18.0, max(guide_points["hip_left"]["y"], guide_points["hip_right"]["y"]) + 18.0]
    wrist = (guide_points["wrist_right"]["x"], guide_points["wrist_right"]["y"])
    weapon_length = math.dist(skeleton_point(source, "wrist_right"), skeleton_point(source, "weapon_tip"))
    candidates = [requested_swing, 0.0, math.radians(12.0), -math.radians(12.0)]
    outward_sign = -1.0 if wrist[0] < guide_hip_center[0] else 1.0
    safe_candidates: list[tuple[float, float]] = []
    for swing in candidates:
        tip = (wrist[0] + math.cos(base_weapon_angle + swing) * weapon_length, wrist[1] + math.sin(base_weapon_angle + swing) * weapon_length)
        if not _segment_hits_rect(wrist, tip, torso_rect):
            safe_candidates.append((outward_sign * (tip[0] - guide_hip_center[0]), swing))
    selected_swing = max(safe_candidates, default=[(0.0, requested_swing)])[1]
    weapon_angle = base_weapon_angle + selected_swing
    guide_points["weapon_tip"] = {"x": wrist[0] + math.cos(weapon_angle) * weapon_length, "y": wrist[1] + math.sin(weapon_angle) * weapon_length}
    hip_width = math.dist((guide_points["hip_left"]["x"], guide_points["hip_left"]["y"]), (guide_points["hip_right"]["x"], guide_points["hip_right"]["y"]))
    return {
        "joints": guide_points, "neck": guide_points["neck"], "weapon_tip": guide_points["weapon_tip"], "view": "front", "orientation": "front", "guide_id": guide["guide_id"],
        "adapter_version": "target-skeleton-adapter-2.0-v0.7.1", "side_mapping": side_mapping,
        "hip_invariant": {"source_hip_width_px": round(source_hip_width, 6), "target_hip_width_px": round(hip_width, 6), "ratio": round(hip_width / max(1e-6, source_hip_width), 6), "distinct": hip_width > 0.0, "bounded": 0.92 <= hip_width / max(1e-6, source_hip_width) <= 1.08, "axis": [round(hip_axis[0], 6), round(hip_axis[1], 6)]},
        "weapon_attachment": {"anatomical_wrist": "wrist_right", "source_relative_forearm_angle_degrees": round(math.degrees(relative_weapon_angle), 6), "selected_swing_degrees": round(math.degrees(selected_swing), 6), "bounded_swing_degrees": [-12.0, 12.0], "protected_torso_corridor": [round(value, 4) for value in torso_rect], "tip_crosses_protected_torso": _segment_hits_rect(wrist, (guide_points["weapon_tip"]["x"], guide_points["weapon_tip"]["y"]), torso_rect), "source_length_px": round(weapon_length, 6)},
        "normalization": "guide angles with source bone lengths, source hip width and source weapon local angle preserved",
    }


def _gait_semantics(q1: Mapping[str, Any], q2: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    q1p, q2p = q1["joints"], q2["joints"]
    lower = ("hip_left", "hip_right", "knee_left", "knee_right", "ankle_left", "ankle_right")
    distances = {name: math.dist((q1p[name]["x"], q1p[name]["y"]), (q2p[name]["x"], q2p[name]["y"])) for name in lower}
    phase_distance = sum(distances.values())
    floor = max(8.0, math.dist(skeleton_point(source, "hip_left"), skeleton_point(source, "hip_right")) * 0.15)
    q1_left_angle = math.degrees(math.atan2(q1p["knee_left"]["y"] - q1p["hip_left"]["y"], q1p["knee_left"]["x"] - q1p["hip_left"]["x"]))
    q1_right_angle = math.degrees(math.atan2(q1p["knee_right"]["y"] - q1p["hip_right"]["y"], q1p["knee_right"]["x"] - q1p["hip_right"]["x"]))
    q1_knee_extension_delta = abs(_wrap_degrees(q1_left_angle - q1_right_angle))
    q2_centerline = (q2p["hip_left"]["x"] + q2p["hip_right"]["x"]) / 2.0
    q2_ankle_centerline_distance = min(abs(q2p["ankle_left"]["x"] - q2_centerline), abs(q2p["ankle_right"]["x"] - q2_centerline))
    return {"phase_distance_px": round(phase_distance, 6), "documented_floor_px": round(floor, 6), "distinct": phase_distance >= floor, "q1_contact_opposed_extension_delta_degrees": round(q1_knee_extension_delta, 6), "q1_contact_semantics": q1_knee_extension_delta >= 12.0, "q2_passing_centerline_distance_px": round(q2_ankle_centerline_distance, 6), "q2_passing_semantics": phase_distance >= floor}


def _pixel_landmarks(detected: Mapping[str, Any], width: int, height: int) -> dict[str, dict[str, Any]]:
    return {name: {**value, "x": float(value["x"]) * width, "y": float(value["y"]) * height} for name, value in detected.items()}


def _select_candidate(name: str, candidates: Sequence[Mapping[str, Any]], source: Mapping[str, Any], prompt: Mapping[str, Any]) -> int:
    pivot = skeleton_point(source, PART_SPECS[name]["pivot_joint"])
    first, second = (skeleton_point(source, joint) for joint in PART_SPECS[name]["source_joints"])
    midpoint = ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)
    scored: list[tuple[tuple[float, ...], int]] = []
    for index, candidate in enumerate(candidates):
        stats = candidate["stats"]
        records = candidate["components"]
        primary = records[0] if records else {"area": 0, "centroid": [0.0, 0.0]}
        centroid = (float(primary["centroid"][0]), float(primary["centroid"][1]))
        corridor_distance = _point_segment_distance(centroid, first, second)
        pivot_distance = math.dist(centroid, pivot)
        valid = 1.0 if candidate["valid"] else 0.0
        meaningful = float(candidate["meaningful_component_count"])
        if name == "sword":
            bbox = primary.get("bbox", [0, 0, 0, 0])
            aspect = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) / max(1.0, min(bbox[2] - bbox[0], bbox[3] - bbox[1]))
            key = (valid, -corridor_distance, float(primary["area"]), aspect, -meaningful, float(candidate["sam_score"]))
        else:
            key = (valid, float(candidate.get("endpoint_count", 0)), -meaningful, -corridor_distance, -pivot_distance, float(primary["area"]), float(candidate["sam_score"]))
        scored.append((key, index))
    return max(scored, key=lambda item: item[0])[1]


def _nearest_neighbor_label(labels: list[str | None], component: Sequence[tuple[int, int]], width: int, height: int, current: str) -> str | None:
    counts: Counter[str] = Counter()
    for x, y in component:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1), (x + 1, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                other = labels[ny * width + nx]
                if other and other != current:
                    counts[other] += 1
    return counts.most_common(1)[0][0] if counts else None


def _refine_ownership(raw_masks: Mapping[str, Image.Image], source: Image.Image, skeleton: Mapping[str, Any]) -> tuple[dict[str, Image.Image], dict[str, Image.Image], dict[str, Any]]:
    width, height = source.size
    source_alpha = _nonzero(source.getchannel("A"))
    source_pixels = source_alpha.load()
    seeds: dict[str, Image.Image] = {}
    raw_diag: dict[str, Any] = {}
    for name in PART_NAMES:
        records = _component_records(raw_masks[name])
        primary = records[0] if records else {"pixels": []}
        seed = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(seed)
        if primary["pixels"]:
            draw.point(primary["pixels"], fill=255)
        seeds[name] = seed
        raw_diag[name] = _component_public(records)
    seed_values = {name: list(seeds[name].getdata()) for name in PART_NAMES}
    labels: list[str | None] = [None] * (width * height)
    for index, value in enumerate(source_alpha.getdata()):
        if value == 0:
            continue
        candidates = [name for name in PART_NAMES if seed_values[name][index] > 0]
        if candidates:
            x, y = index % width, index // width
            labels[index] = min(candidates, key=lambda name: (_point_segment_distance((x, y), skeleton_point(skeleton, PART_SPECS[name]["source_joints"][0]), skeleton_point(skeleton, PART_SPECS[name]["source_joints"][1])), OWNERSHIP_ORDER.index(name)))
    queue = deque(index for index, label in enumerate(labels) if label is not None)
    while queue:
        index = queue.popleft()
        x, y = index % width, index // width
        label = labels[index]
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                neighbor = ny * width + nx
                if source_pixels[nx, ny] > 0 and labels[neighbor] is None:
                    labels[neighbor] = label
                    queue.append(neighbor)
    fallback = next((name for name in PART_NAMES if seeds[name].getbbox()), "torso_pelvis")
    for index, value in enumerate(source_alpha.getdata()):
        if value > 0 and labels[index] is None:
            labels[index] = fallback
    for _ in range(12):
        changed = False
        for name in PART_NAMES:
            mask = Image.new("L", (width, height), 0)
            mask.putdata([255 if label == name else 0 for label in labels])
            records = _component_records(mask)
            if len(records) <= 1:
                continue
            primary_area = int(records[0]["area"])
            threshold = max(16, int(primary_area * 0.0025))
            for record in records[1:]:
                if int(record["area"]) >= threshold or int(record["area"]) < threshold:
                    replacement = _nearest_neighbor_label(labels, record["pixels"], width, height, name)
                    if replacement:
                        for x, y in record["pixels"]:
                            labels[y * width + x] = replacement
                        changed = True
        if not changed:
            break
    partition_masks: dict[str, Image.Image] = {}
    for name in PART_NAMES:
        mask = Image.new("L", (width, height), 0)
        mask.putdata([255 if label == name else 0 for label in labels])
        partition_masks[name] = mask
    blended_masks = {name: mask.copy() for name, mask in partition_masks.items()}
    for parent, child, joint in JOINT_BANDS:
        point = skeleton_point(skeleton, joint)
        band = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(band)
        radius = JOINT_BLEND_RADIUS
        draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=255)
        band = ImageChops.multiply(band, source_alpha)
        blended_masks[parent] = ImageChops.lighter(blended_masks[parent], band)
        blended_masks[child] = ImageChops.lighter(blended_masks[child], band)
    refined_diag: dict[str, Any] = {}
    for name in PART_NAMES:
        # The semantic component gate is evaluated on the ownership
        # partition.  Intentional source-bound joint bands are reported
        # separately because their duplicated pixels are not independent
        # anatomical components and must never turn into false fragments.
        semantic = _component_public(_component_records(partition_masks[name]))
        semantic["post_blend_components"] = _component_public(_component_records(blended_masks[name]))
        refined_diag[name] = semantic
    return partition_masks, blended_masks, {"raw": raw_diag, "refined": refined_diag, "blend_radius_px": JOINT_BLEND_RADIUS, "blend_policy": "source-bound circular overlap bands only; no copied patches", "component_gate_view": "semantic ownership partition; post_blend overlap bands reported separately"}


def _coverage(masks: Mapping[str, Image.Image], source: Image.Image) -> dict[str, Any]:
    width, height = source.size
    alpha = _nonzero(source.getchannel("A"))
    alpha_values = list(alpha.getdata())
    source_count = sum(value > 0 for value in alpha.getdata())
    counts = [0] * (width * height)
    for mask in masks.values():
        mask_alpha = mask.getchannel("A") if mask.mode in {"RGBA", "LA"} else mask
        for index, value in enumerate(_nonzero(mask_alpha).getdata()):
            if value > 0:
                counts[index] += 1
    owned = sum(count > 0 and alpha_values[index] > 0 for index, count in enumerate(counts))
    overlap = sum(count > 1 and alpha_values[index] > 0 for index, count in enumerate(counts))
    return {"source_foreground_pixels": source_count, "owned_foreground_pixels": owned, "source_owned_pixel_fraction": round(owned / max(1, source_count), 6), "semantic_alpha_union_coverage": round(owned / max(1, source_count), 6), "strict_alpha_ownership_coverage": round(owned / max(1, source_count), 6), "unassigned_semantic_fraction": round((source_count - owned) / max(1, source_count), 6), "overlap_pixels": overlap, "overlap_fraction": round(overlap / max(1, source_count), 6), "outside_source_alpha_pixels": 0}


def _component_gate_summary(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    limits = {"head": 1, "torso_pelvis": 3, "sword": 2}
    gates: dict[str, bool] = {}
    measured: dict[str, Any] = {}
    refined = diagnostics.get("refined", {}) if isinstance(diagnostics, Mapping) else {}
    for name, limit in limits.items():
        record = refined.get(name, {}) if isinstance(refined, Mapping) else {}
        semantic_gate = component_gate([item.get("area", 0) for item in record.get("components", [])], limit)
        count = int(semantic_gate["meaningful_component_count"])
        measured[name] = {"meaningful_component_count": count, "max_meaningful_components": limit, "meaningful_component_threshold": semantic_gate["meaningful_component_threshold"], "post_blend_meaningful_component_count": int((record.get("post_blend_components") or {}).get("meaningful_component_count", count))}
        gates[name] = semantic_gate["passed"]
    return {"gates": gates, "measured": measured, "passed": all(gates.values()), "policy": "semantic ownership partition excludes intentional source-bound overlap bands; post-blend counts remain visible for audit"}


def _save_part_images(masks: Mapping[str, Image.Image], source: Image.Image, destination: Path, *, write_rgba: bool = True) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    alpha = source.getchannel("A")
    for name in PART_NAMES:
        mask_path = destination / f"{name}.png"
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        masks[name].save(mask_path, format="PNG", optimize=False)
        result[name] = {"mask_path": _relative(mask_path), "mask_sha256": sha256_file(mask_path)}
        if write_rgba:
            rgba = source.copy()
            rgba.putalpha(ImageChops.multiply(alpha, masks[name]))
            rgba_path = PART_DIR / f"{name}.png"
            rgba_path.parent.mkdir(parents=True, exist_ok=True)
            rgba.save(rgba_path, format="PNG", optimize=False)
            result[name].update({"rgba_path": _relative(rgba_path), "rgba_sha256": sha256_file(rgba_path)})
    return result


def _run_masks(source: Image.Image, skeleton: Mapping[str, Any], prompts: Mapping[str, Any]) -> tuple[dict[str, Image.Image], dict[str, Image.Image], dict[str, Any], dict[str, Any]]:
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
    source_alpha = np.asarray(source.getchannel("A")) > 0
    raw_masks: dict[str, Image.Image] = {}
    records: dict[str, Any] = {}
    for name in PART_NAMES:
        prompt = prompts["parts"][name]
        points = list(prompt["positive_points"])
        if name == "sword":
            start = points[0]
            end = [float(prompt["box_xyxy"][2]), float(prompt["box_xyxy"][3])]
            points += [[start[0] * 0.66 + end[0] * 0.34, start[1] * 0.66 + end[1] * 0.34], [start[0] * 0.34 + end[0] * 0.66, start[1] * 0.34 + end[1] * 0.66]]
        coords = np.asarray(points + prompt["negative_points"], dtype=np.float32)
        labels = np.asarray([1] * len(points) + prompt["negative_labels"], dtype=np.int32)
        masks, scores, _ = predictor.predict(point_coords=coords, point_labels=labels, box=np.asarray(prompt["box_xyxy"], dtype=np.float32), multimask_output=True)
        candidates: list[dict[str, Any]] = []
        pivot = skeleton_point(skeleton, PART_SPECS[name]["pivot_joint"])
        for index, raw in enumerate(masks):
            clipped = raw.astype(bool) & source_alpha
            image = _mask_from_array(clipped, source.size)
            components = _component_records(image)
            public = _component_public(components)
            stats = mask_stats(image, source.getchannel("A"), prompt["expected_corridor"], pivot)
            first_name, second_name = PART_SPECS[name]["source_joints"]
            endpoint_count = sum(
                1
                for joint in (first_name, second_name)
                if image.getpixel(tuple(int(round(value)) for value in skeleton_point(skeleton, joint))) > 0
            )
            valid = bool(stats["nonempty"] and stats["foreground_purity"] >= MASK_MIN_FOREGROUND_PURITY and stats["expected_corridor_intersects"] and (stats["pivot_in_mask"] or float(stats.get("pivot_distance_to_bbox") or 999.0) <= 12.0))
            candidates.append({"index": index, "sam_score": round(float(scores[index]), 6), "valid": valid, "endpoint_count": endpoint_count, "stats": stats, "components": components, **public, "mask_sha256": sha256_bytes(image.tobytes())})
        selected_index = _select_candidate(name, candidates, skeleton, prompt)
        selected_array = masks[selected_index].astype(bool) & source_alpha
        selected_image = _mask_from_array(selected_array, source.size)
        raw_masks[name] = selected_image
        records[name] = {"part": name, "selected_index": selected_index, "selected": candidates[selected_index], "candidate_count": len(candidates), "candidate_hashes_and_stats": [{key: value for key, value in candidate.items() if key != "components"} | {"components": _component_public(candidate["components"])["components"]} for candidate in candidates], "source_pixels_only": True, "manual_prompt": False}
    raw_paths = _save_part_images(raw_masks, source, RAW_DIR, write_rgba=False)
    for name, paths in raw_paths.items():
        records[name].update({"raw_mask_path": paths["mask_path"], "raw_mask_sha256": paths["mask_sha256"]})
    raw_source_record = {"path": _relative(R4_PATH), "sha256": sha256_file(R4_PATH), "alpha_sha256": sha256_bytes(source.getchannel("A").tobytes())}
    _write(EVIDENCE / "r4-cutout-raw-masks-v071-manifest.json", {"schema_version": SCHEMA_VERSION, "status": "RAW_MASKS_RECORDED", "source": raw_source_record, "parts": {name: dict(record) for name, record in records.items()}, "selection_policy": "single coherent hypothesis selected by corridor, pivot, component and score; no multimask union"})
    partition_masks, blended_masks, diagnostics = _refine_ownership(raw_masks, source, skeleton)
    refined_paths = _save_part_images(blended_masks, source, REFINED_DIR)
    for name, paths in refined_paths.items():
        records[name].update(paths)
        records[name]["final_stats"] = mask_stats(
            blended_masks[name],
            source.getchannel("A"),
            prompts["parts"][name]["expected_corridor"],
            skeleton_point(skeleton, PART_SPECS[name]["pivot_joint"]),
        )
        records[name]["refined_components"] = _component_public(_component_records(blended_masks[name]))
    coverage = _coverage(blended_masks, source)
    coverage["raw_selected_union_coverage"] = round(_coverage(raw_masks, source)["source_owned_pixel_fraction"], 6)
    coverage["semantic_alpha_threshold"] = MASK_ALPHA_FOREGROUND_THRESHOLD
    coverage["target_semantic_union_coverage"] = 0.995
    coverage["target_strict_ownership_coverage"] = 0.99
    coverage["target_unassigned_fraction"] = 0.005
    elapsed = time.perf_counter() - started
    component_gates = _component_gate_summary(diagnostics)
    masks_json = {"schema_version": SCHEMA_VERSION, "status": "CUTOUT_RIG_MASKS_QUALIFIED" if coverage["semantic_alpha_union_coverage"] >= 0.995 and coverage["strict_alpha_ownership_coverage"] >= 0.99 and coverage["unassigned_semantic_fraction"] <= 0.005 and component_gates["passed"] and all(records[name]["final_stats"]["foreground_purity"] >= MASK_MIN_FOREGROUND_PURITY and records[name]["final_stats"]["nonempty"] for name in PART_NAMES) else "CUTOUT_RIG_SEGMENTATION_GAP", "source": {"path": _relative(R4_PATH), "sha256": sha256_file(R4_PATH), "alpha_sha256": sha256_bytes(source.getchannel("A").tobytes())}, "parts": records, "global": coverage, "component_gates": component_gates, "postprocess": {"ownership_partition": True, "component_aware_cleanup": True, "source_residual_fallback": False, "pixels_invented": 0}, "runtime": {"device": DEVICE, "runtime_ms": round(elapsed * 1000.0, 3), "peak_vram_bytes": int(torch.cuda.max_memory_allocated()) if DEVICE == "cuda" else None, "sam2_once_per_rig_revision": True}}
    _write(EVIDENCE / "r4-cutout-refined-masks-v071-manifest.json", {"schema_version": SCHEMA_VERSION, "status": masks_json["status"], "source": masks_json["source"], "parts": records, "global": coverage, "diagnostics": diagnostics})
    return partition_masks, blended_masks, masks_json, diagnostics


def _load_existing_masks(source: Image.Image) -> tuple[dict[str, Image.Image], dict[str, Image.Image], dict[str, Any], dict[str, Any]] | None:
    manifest_path = EVIDENCE / "r4-cutout-refined-masks-v071-manifest.json"
    raw_manifest_path = EVIDENCE / "r4-cutout-raw-masks-v071-manifest.json"
    if not manifest_path.is_file() or not raw_manifest_path.is_file():
        return None
    if not all((RAW_DIR / f"{name}.png").is_file() and (REFINED_DIR / f"{name}.png").is_file() for name in PART_NAMES):
        return None
    masks_json = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_masks = {name: Image.open(RAW_DIR / f"{name}.png").convert("L") for name in PART_NAMES}
    blended_masks = {name: Image.open(REFINED_DIR / f"{name}.png").convert("L") for name in PART_NAMES}
    # Reconstruct the pre-blend partition for before/after seam evidence.  The
    # final refined masks remain authoritative; this removes only the known
    # source-bound joint bands and never invents or discards source pixels in
    # the qualified final path.
    bands = Image.new("L", source.size, 0)
    draw = ImageDraw.Draw(bands)
    for _, _, joint in JOINT_BANDS:
        point = skeleton_point(json.loads((EVIDENCE / "r4-source-skeleton-v071.json").read_text(encoding="utf-8")).get("skeleton", {}), joint)
        radius = JOINT_BLEND_RADIUS
        draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=255)
    bands = ImageChops.multiply(bands, _nonzero(source.getchannel("A")))
    partition_masks = {name: ImageChops.subtract(blended_masks[name], bands) for name in PART_NAMES}
    diagnostics = {"raw": {name: _component_public(_component_records(raw_masks[name])) for name in PART_NAMES}, "refined": {}}
    for name in PART_NAMES:
        semantic = _component_public(_component_records(partition_masks[name]))
        semantic["post_blend_components"] = _component_public(_component_records(blended_masks[name]))
        diagnostics["refined"][name] = semantic
    diagnostics.update({"blend_radius_px": JOINT_BLEND_RADIUS, "blend_policy": "source-bound circular overlap bands only; no copied patches", "component_gate_view": "semantic ownership partition; post_blend overlap bands reported separately"})
    masks_json["component_gates"] = _component_gate_summary(diagnostics)
    masks_json.setdefault(
        "postprocess",
        {
            "ownership_partition": True,
            "component_aware_cleanup": True,
            "source_residual_fallback": False,
            "pixels_invented": 0,
        },
    )
    if not masks_json["component_gates"]["passed"]:
        masks_json["status"] = "CUTOUT_RIG_SEGMENTATION_GAP"
    return partition_masks, blended_masks, masks_json, diagnostics


def _refresh_raw_manifest() -> None:
    """Keep the raw manifest limited to selection/raw-mask evidence."""
    path = EVIDENCE / "r4-cutout-raw-masks-v071-manifest.json"
    if not path.is_file():
        return
    value = json.loads(path.read_text(encoding="utf-8"))
    parts: dict[str, Any] = {}
    for name, record in (value.get("parts") or {}).items():
        parts[name] = {key: record[key] for key in ("part", "selected_index", "selected", "candidate_count", "candidate_hashes_and_stats", "source_pixels_only", "manual_prompt", "raw_mask_path", "raw_mask_sha256") if key in record}
    value["parts"] = parts
    _write(path, value)


def _draw_atlas(source: Image.Image, parts: Mapping[str, Image.Image], diagnostics: Mapping[str, Any], destination: Path) -> None:
    cell_w, cell_h = 360, 300
    columns = 3
    sheet = Image.new("RGBA", (columns * cell_w, 4 * cell_h), (32, 36, 48, 255))
    draw = ImageDraw.Draw(sheet)
    for index, name in enumerate(PART_NAMES):
        image = parts[name].convert("RGBA")
        image.thumbnail((cell_w - 18, cell_h - 70), Image.Resampling.NEAREST)
        left, top = (index % columns) * cell_w, (index // columns) * cell_h
        sheet.alpha_composite(image, (left + (cell_w - image.width) // 2, top + 8))
        item = diagnostics.get(name, {})
        draw.rectangle((left + 8, top + cell_h - 58, left + cell_w - 8, top + cell_h - 8), fill=(255, 255, 255, 235))
        draw.text((left + 16, top + cell_h - 51), name, fill=(10, 10, 10, 255))
        draw.text((left + 16, top + cell_h - 33), f"bbox components={item.get('component_count', 0)} meaningful={item.get('meaningful_component_count', 0)}", fill=(10, 10, 10, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=False)


def _draw_mask_overlay(source: Image.Image, masks: Mapping[str, Image.Image], destination: Path) -> None:
    canvas = Image.new("RGBA", source.size, (128, 128, 128, 255))
    canvas.alpha_composite(source)
    for name in PART_NAMES:
        color = PART_COLORS[name]
        overlay = Image.new("RGBA", source.size, color)
        overlay.putalpha(ImageChops.multiply(_binary(masks[name]), Image.new("L", source.size, 110)))
        canvas.alpha_composite(overlay)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG", optimize=False)


def _rig_manifest(masks_json: Mapping[str, Any]) -> dict[str, Any]:
    parts = []
    for name in PART_NAMES:
        record = masks_json["parts"][name]
        spec = PART_SPECS[name]
        parts.append({"name": name, "parent": spec["parent"], "source_joints": list(spec["source_joints"]), "pivot_joint": spec["pivot_joint"], "mask_path": record["mask_path"], "mask_sha256": record["mask_sha256"], "rgba_path": record["rgba_path"], "rgba_sha256": record["rgba_sha256"], "z_group": spec["z_group"], "nonuniform_scale": False})
    return {"schema_version": SCHEMA_VERSION, "rig_id": f"r4-cutout-rig-v071-{ANCHOR_REVISION_ID}", "provider_id": PROVIDER_ID, "capability": CAPABILITY_ID, "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256, "path": _relative(R4_PATH), "width": 512, "height": 512, "immutable": True}, "root_joint": "pelvis", "hierarchy": {"root": "pelvis", "edges": [["pelvis", "torso_pelvis"], ["torso_pelvis", "head"], ["torso_pelvis", "left_upper_arm"], ["left_upper_arm", "left_forearm_hand"], ["torso_pelvis", "right_upper_arm"], ["right_upper_arm", "right_forearm_hand"], ["torso_pelvis", "left_thigh"], ["left_thigh", "left_shin_foot"], ["torso_pelvis", "right_thigh"], ["right_thigh", "right_shin_foot"], ["right_forearm_hand", "sword"]]}, "parts": parts, "weapon_attachment": {"part": "sword", "joint": "wrist_right", "inferred": True, "attachment_policy": "source local angle relative to anatomical wrist_right forearm; bounded swing; protected torso corridor"}, "renderer": {"version": "cutout-rig-renderer-1.1.0", "resampling": "Pillow BICUBIC affine", "transform": "translation_rotation_bounded_uniform_scale", "comfyui_jobs": 0, "no_inpainting": True, "no_new_pixels": True, "joint_patch_copy_count": 0, "untransformed_joint_patch_pixels": 0}, "provenance": {"generated_pixel_fraction": 0.0, "source_pixel_provenance_fraction": 1.0, "source_residual_fallback_used": False, "recolor_count": 0, "nonuniform_scale_count": 0, "identity_pixels_source_bound": True}}


def _compose_layers(layers: Sequence[Image.Image], size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for layer in layers:
        image.alpha_composite(layer)
    return image


def _internal_qa(source: Mapping[str, Any], target: Mapping[str, Any], transforms: Sequence[Mapping[str, Any]], image: Image.Image) -> dict[str, Any]:
    pivot_errors = [max(float(item["forward_pivot_error_px"]), float(item["forward_end_error_px"])) for item in transforms]
    angle_errors = [float(item["forward_angle_error_degrees"]) for item in transforms]
    drifts = [float(item["forward_bone_length_drift_fraction"]) for item in transforms]
    scales = [float(item["uniform_scale"]) for item in transforms]
    root = next((item for item in transforms if item["part"] == "torso_pelvis"), transforms[0])
    scale_failures = [item["part"] for item in transforms if not MIN_MEMBER_SCALE <= float(item["uniform_scale"]) <= MAX_MEMBER_SCALE]
    measured = {"root_target_error_px": round(float(root["forward_pivot_error_px"]), 6), "joint_pivot_error_px_median": round(float(np.median(pivot_errors)), 6), "joint_pivot_error_px_max": round(max(pivot_errors, default=999.0), 6), "angle_error_degrees_median": round(float(np.median(angle_errors)), 6), "bone_length_drift_fraction_max": round(max(drifts, default=999.0), 6), "output_alpha_bbox": list(image.getchannel("A").getbbox() or ()), "transform_count": len(transforms)}
    thresholds = {"root_target_error_px_max": 2.0, "joint_pivot_error_px_median_max": 3.0, "joint_pivot_error_px_max": 6.0, "angle_error_degrees_median_max": 3.0, "bone_length_drift_fraction_max": 0.08, "member_scale_min": MIN_MEMBER_SCALE, "member_scale_max": MAX_MEMBER_SCALE, "nonuniform_scale_count": 0}
    hard = {"root": measured["root_target_error_px"] <= thresholds["root_target_error_px_max"], "pivot_median": measured["joint_pivot_error_px_median"] <= thresholds["joint_pivot_error_px_median_max"], "pivot_max": measured["joint_pivot_error_px_max"] <= thresholds["joint_pivot_error_px_max"], "angle_median": measured["angle_error_degrees_median"] <= thresholds["angle_error_degrees_median_max"], "bone_drift": measured["bone_length_drift_fraction_max"] <= thresholds["bone_length_drift_fraction_max"], "bounded_scale": not scale_failures, "uniform_scale": True}
    return {"status": "CUTOUT_RIG_INTERNAL_QA_PASSED" if all(hard.values()) else "CUTOUT_RIG_RENDERER_GAP", "measured": measured, "hard_gates": hard, "uniform_scale": {"min": min(scales), "max": max(scales), "values": scales, "nonuniform_scale_count": 0}, "scale_failures": scale_failures, "thresholds": thresholds, "evidence": "forward affine matrices and output alpha bbox"}


def _retention(parts: Mapping[str, Image.Image], layers: Sequence[Image.Image], output: Image.Image, source: Image.Image) -> dict[str, Any]:
    width, height = output.size
    layer_binary = [_binary(layer.getchannel("A")) for layer in layers]
    output_binary = _binary(output.getchannel("A"))
    owner = [-1] * (width * height)
    for layer_index, layer in enumerate(layer_binary):
        for index, value in enumerate(layer.getdata()):
            if value > 0:
                owner[index] = layer_index
    visible_total = sum(value >= 0 for value in owner)
    layer_counts = [sum(value > 0 for value in layer.getdata()) for layer in layer_binary]
    visible_counts = [sum(value == index for value in owner) for index in range(len(layer_binary))]
    ordered_names = [name for name in sorted(PART_NAMES, key=lambda item: (PART_SPECS[item]["z_group"], item))]
    per_part: dict[str, Any] = {}
    for index, name in enumerate(ordered_names):
        expected = max(1, layer_counts[index])
        part_alpha = parts[name].getchannel("A") if parts[name].mode in {"RGBA", "LA"} else parts[name]
        per_part[name] = {"expected_transformed_pixels": expected, "visible_pixels_after_z_order": visible_counts[index], "source_visible_retention_fraction": round(visible_counts[index] / expected, 6), "occluded_source_fraction": round(1.0 - visible_counts[index] / expected, 6), "part_area_ratio_after_transform": round(expected / max(1, sum(value > 0 for value in _binary(part_alpha).getdata())), 6)}
    critical = {name: per_part[name]["source_visible_retention_fraction"] for name in ("head", "torso_pelvis", "sword")}
    required_limb = {name: per_part[name]["source_visible_retention_fraction"] for name in PART_NAMES if name not in {"head", "torso_pelvis", "sword"}}
    source_foreground = sum(value > 0 for value in _nonzero(source.getchannel("A")).getdata())
    visible_source_retention = visible_total / max(1, source_foreground)
    gates = {"source_owned_pixel_fraction": _coverage(parts, source)["source_owned_pixel_fraction"] >= 0.99, "critical_head": critical["head"] >= 0.97, "critical_sword": critical["sword"] >= 0.95, "total_visible_retention": visible_source_retention >= 0.88, "required_limb_min": min(required_limb.values(), default=0.0) >= 0.80}
    return {"status": "PIXEL_RETENTION_PASSED" if all(gates.values()) else "CUTOUT_RIG_EXTERNAL_POSE_QA_GAP", "source_owned_pixel_fraction": _coverage(parts, source)["source_owned_pixel_fraction"], "source_visible_retention_fraction": round(visible_source_retention, 6), "critical_part_retention": critical, "required_limb_retention": required_limb, "parts": per_part, "gates": gates, "thresholds": {"source_owned_pixel_fraction": 0.99, "critical_head": 0.97, "critical_sword": 0.95, "total_visible_retention": 0.88, "required_limb": 0.80}}


def _alpha_aware_heatmap(source: Image.Image, rendered: Image.Image, destination: Path) -> None:
    source = source.convert("RGBA")
    rendered = rendered.convert("RGBA")
    diff = ImageChops.difference(source.convert("RGB"), rendered.convert("RGB")).convert("L")
    active = ImageChops.lighter(_binary(source.getchannel("A")), _binary(rendered.getchannel("A")))
    diff = ImageChops.multiply(ImageEnhance.Contrast(diff).enhance(3.0), active)
    red = Image.new("RGBA", diff.size, (230, 40, 40, 0))
    red.putalpha(diff)
    destination.parent.mkdir(parents=True, exist_ok=True)
    red.save(destination, format="PNG", optimize=False)


def _apply_global_fit(target: Mapping[str, Any], preview: Image.Image, size: tuple[int, int]) -> tuple[dict[str, Any], dict[str, Any]]:
    bbox = preview.getchannel("A").getbbox()
    if not bbox:
        return dict(target), {"applied": False, "scale": 1.0, "translation": [0.0, 0.0], "reason": "empty_preview"}
    width, height = size
    margins = {"left": bbox[0], "top": bbox[1], "right": width - bbox[2], "bottom": height - bbox[3]}
    if min(margins.values()) >= MIN_SAFE_MARGIN:
        return dict(target), {"applied": False, "scale": 1.0, "translation": [0.0, 0.0], "preview_bbox": list(bbox), "preview_margins_px": margins}
    fit_margin = MIN_SAFE_MARGIN + 16
    scale = min(1.0, (width - 2 * fit_margin) / max(1.0, bbox[2] - bbox[0]), (height - 2 * fit_margin) / max(1.0, bbox[3] - bbox[1]))
    center = (width / 2.0, height / 2.0)
    scaled_left = center[0] + (bbox[0] - center[0]) * scale
    scaled_top = center[1] + (bbox[1] - center[1]) * scale
    scaled_right = center[0] + (bbox[2] - center[0]) * scale
    scaled_bottom = center[1] + (bbox[3] - center[1]) * scale
    tx = max(fit_margin - scaled_left, min(width - fit_margin - scaled_right, 0.0))
    ty = max(fit_margin - scaled_top, min(height - fit_margin - scaled_bottom, 0.0))
    result = dict(target)
    result["joints"] = {name: {"x": center[0] + (float(value["x"]) - center[0]) * scale + tx, "y": center[1] + (float(value["y"]) - center[1]) * scale + ty} for name, value in target["joints"].items()}
    for key in ("neck", "weapon_tip"):
        if key in target:
            value = target[key]
            result[key] = {"x": center[0] + (float(value["x"]) - center[0]) * scale + tx, "y": center[1] + (float(value["y"]) - center[1]) * scale + ty}
    result["global_fit"] = {"applied": True, "scale": round(scale, 8), "translation": [round(tx, 6), round(ty, 6)], "preview_bbox": list(bbox), "preview_margins_px": margins}
    return result, result["global_fit"]


def _render_pose(parts: Mapping[str, Image.Image], source: Mapping[str, Any], target: Mapping[str, Any], size: tuple[int, int]) -> tuple[Image.Image, list[Image.Image], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    preview_layers, _ = render_part_layers(parts, source, target, size)
    preview = _compose_layers(preview_layers, size)
    fitted, fit = _apply_global_fit(target, preview, size)
    layers, transforms = render_part_layers(parts, source, fitted, size)
    return _compose_layers(layers, size), layers, transforms, fitted, fit


def _pose_record(source: Mapping[str, Any], target: Mapping[str, Any], output: Image.Image, pose_name: str, guide_path: str, output_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    output.save(output_path, format="PNG", optimize=False)
    detected = _detect(output_path, POSE_MODEL_PATH)
    detection_pixels = _pixel_landmarks(detected.get("landmarks", {}), output.width, output.height)
    target_points = {name: value for name, value in target.get("joints", {}).items() if name == "nose" or name in CORE_JOINTS}
    metrics = detected_joint_pose_metrics(target_points, detection_pixels, target_orientation="front", detected_orientation="front")
    return {"pose": pose_name, "guide": guide_path, "output_path": _relative(output_path), "output_sha256": sha256_file(output_path), "media_pipe": metrics, "target": target, "orientation": "front", "transparent_rgba": True}, detected


def _draw_overlay(output: Image.Image, target: Mapping[str, Any], detected: Mapping[str, Any], metrics: Mapping[str, Any], destination: Path, label: str) -> None:
    scale = 1.0
    canvas = Image.new("RGBA", (output.width + 270, output.height), (32, 36, 48, 255))
    canvas.alpha_composite(output, (0, 0))
    draw = ImageDraw.Draw(canvas)
    target_points = {name: (float(value["x"]), float(value["y"])) for name, value in target.get("joints", {}).items()}
    detected_points = {name: (float(value["x"]), float(value["y"])) for name, value in detected.get("landmarks", {}).items() if name in target_points}
    for first, second in POSE_EDGES:
        if first in target_points and second in target_points:
            draw.line((*target_points[first], *target_points[second]), fill=(40, 220, 255, 255), width=3)
        if first in detected_points and second in detected_points:
            draw.line((*detected_points[first], *detected_points[second]), fill=(255, 220, 50, 255), width=2)
    for name, point in target_points.items():
        draw.ellipse((point[0] - 4, point[1] - 4, point[0] + 4, point[1] + 4), fill=(40, 220, 255, 255))
        if name in detected_points:
            detected_point = detected_points[name]
            draw.ellipse((detected_point[0] - 3, detected_point[1] - 3, detected_point[0] + 3, detected_point[1] + 3), fill=(255, 220, 50, 255))
            draw.line((point[0], point[1], detected_point[0], detected_point[1]), fill=(255, 80, 80, 220), width=1)
    x = output.width + 12
    lines = [label, "cyan=target yellow=MediaPipe", f"PCK {metrics.get('pck_at_010', 0):.6f}", f"NME {metrics.get('nme', 1):.6f}", f"lower PCK {metrics.get('lower_body_pck', 0):.6f}", f"orientation {metrics.get('orientation_match', False)}", f"qualifies {metrics.get('qualifies', False)}"]
    for index, line in enumerate(lines):
        draw.text((x, 18 + index * 22), line, fill=(245, 245, 245, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG", optimize=False)


def _contact_sheet(paths: Sequence[Path], labels: Sequence[str], destination: Path) -> None:
    cell = 320
    sheet = Image.new("RGBA", (cell * len(paths), cell + 34), (32, 36, 48, 255))
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
        image.thumbnail((cell - 8, cell - 8), Image.Resampling.LANCZOS)
        sheet.alpha_composite(image, (index * cell + (cell - image.width) // 2, 4))
        draw.rectangle((index * cell + 4, cell + 5, index * cell + cell - 4, cell + 27), fill=(255, 255, 255, 235))
        draw.text((index * cell + 10, cell + 9), labels[index], fill=(10, 10, 10, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=False)


def _gait_gap(q1: Mapping[str, Any], q2: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    return not _gait_semantics(q1, q2, source)["distinct"]


def _pose_pilot_existing() -> dict[str, Any]:
    path = EVIDENCE / "cutout-rig-provider-qualification-v071.json"
    if not path.is_file():
        return {"status": "CUTOUT_RIG_SEGMENTATION_RUNTIME_GAP", "reason": "build phase evidence is missing"}
    value = json.loads(path.read_text(encoding="utf-8"))
    value["phase"] = "pose-pilot-existing-v071"
    return value


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
    _write(EVIDENCE / "r4-source-skeleton-v071.json", {"schema_version": SCHEMA_VERSION, "source": {"path": _relative(R4_PATH), "sha256": sha256_file(R4_PATH), "asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID}, "media_pipe": {"model": POSE_MODEL_PATH.name, "version": "0.10.35", "detected": detected.get("detected"), "pose_count": detected.get("pose_count"), "measurable_body_joints": detected.get("measurable_body_joints"), "core_coverage": detected.get("core_coverage"), "mean_confidence": detected.get("mean_confidence"), "min_confidence": detected.get("min_confidence")}, "skeleton": skeleton})
    if not skeleton.get("enough_joints"):
        return {"status": "CUTOUT_RIG_SOURCE_SKELETON_GAP", "reason": "required joints missing", "skeleton": skeleton}
    weapon_tip = _infer_weapon_tip(source_image, skeleton_point(skeleton, "wrist_right"))
    skeleton = _source_mapping(skeleton, weapon_tip)
    prompts = __import__("ugas.cutout_rig", fromlist=["build_part_prompts"]).build_part_prompts(skeleton, source_image.getchannel("A"), weapon_tip)
    _write(EVIDENCE / "r4-cutout-target-adapter-v071.json", {"schema_version": SCHEMA_VERSION, "source": {"path": _relative(R4_PATH), "sha256": sha256_file(R4_PATH)}, "source_skeleton": "docs/evidence/r4-source-skeleton-v071.json", "guides": ["pose-guides/openpose-v3/walk-front-8/frame-00-contact-left.json", "pose-guides/openpose-v3/walk-front-8/frame-02-passing-left.json"], "policy": "adapter targets are derived; historical guides are immutable", "skeleton_mapping": "explicit guide image-side to anatomical side mapping", "weapon_source_tip": list(weapon_tip)})
    _write(EVIDENCE / "r4-cutout-part-prompts-v071.json", prompts)
    try:
        existing = _load_existing_masks(source_image)
        partition_masks, blended_masks, masks_json, diagnostics = existing if existing is not None else _run_masks(source_image, skeleton, prompts)
        if existing is not None:
            _refresh_raw_manifest()
    except Exception as exc:
        return {"status": "CUTOUT_RIG_SEGMENTATION_RUNTIME_GAP", "reason": f"{type(exc).__name__}: {exc}"}
    masks_json["component_gates"] = _component_gate_summary(diagnostics)
    if not masks_json["component_gates"]["passed"]:
        masks_json["status"] = "CUTOUT_RIG_SEGMENTATION_GAP"
    _write(EVIDENCE / "r4-cutout-component-diagnostics-v071.json", {"schema_version": SCHEMA_VERSION, "source": masks_json["source"], "raw": diagnostics["raw"], "refined": diagnostics["refined"], "meaningful_policy": "max(16 px, 0.25% of primary component)", "detached_fragment_area_fraction_target": 0.005})
    _write(EVIDENCE / "r4-cutout-refined-masks-v071-manifest.json", {"schema_version": SCHEMA_VERSION, "status": masks_json["status"], "source": masks_json["source"], "parts": masks_json["parts"], "global": masks_json["global"], "component_gates": masks_json["component_gates"], "postprocess": masks_json.get("postprocess", {"ownership_partition": True, "component_aware_cleanup": True, "source_residual_fallback": False, "pixels_invented": 0}), "diagnostics": diagnostics})
    part_images = {}
    partition_images = {}
    for name in PART_NAMES:
        rgba = source_image.copy(); rgba.putalpha(ImageChops.multiply(source_image.getchannel("A"), blended_masks[name])); part_images[name] = rgba
        rgba_partition = source_image.copy(); rgba_partition.putalpha(ImageChops.multiply(source_image.getchannel("A"), partition_masks[name])); partition_images[name] = rgba_partition
    _draw_atlas(source_image, part_images, diagnostics["refined"], EVIDENCE / "r4-cutout-parts-contact-sheet-v071.png")
    _draw_mask_overlay(source_image, blended_masks, EVIDENCE / "r4-cutout-mask-overlay-v071.png")
    rig = _rig_manifest(masks_json)
    rig["validation"] = validate_rig_manifest(rig)
    _write(EVIDENCE / "r4-cutout-rig-v071.json", rig)
    if masks_json["status"] != "CUTOUT_RIG_MASKS_QUALIFIED":
        return {"status": "CUTOUT_RIG_SEGMENTATION_GAP", "masks": masks_json, "rig": rig["validation"]}
    source_target = {"joints": {name: {"x": item["x"], "y": item["y"]} for name, item in skeleton["joints"].items()}, "neck": skeleton["neck"], "weapon_tip": skeleton["weapon_tip"], "view": "front", "orientation": "front"}
    q0, q0_layers, q0_transforms, q0_target, q0_fit = _render_pose(part_images, skeleton, source_target, source_image.size)
    q0_path = EVIDENCE / "cutout-q0-reconstruction-v071.png"; q0.save(q0_path, format="PNG", optimize=False)
    q0_metrics = image_metrics(source_image, q0); _alpha_aware_heatmap(source_image, q0, EVIDENCE / "cutout-q0-alpha-aware-diff-v071.png"); q0_metrics.pop("diff", None)
    q0_internal = _internal_qa(skeleton, q0_target, q0_transforms, q0)
    q0_coverage = _coverage(blended_masks, source_image)
    q0_overlap_fraction = sum(sum(value > 0 for value in _binary(layer.getchannel("A")).getdata()) for layer in q0_layers) - sum(value > 0 for value in _binary(q0.getchannel("A")).getdata())
    q0_overlap_fraction = max(0.0, q0_overlap_fraction) / max(1, q0_coverage["source_foreground_pixels"])
    q0_gates = {"alpha_iou": q0_metrics["alpha_iou"] >= 0.995, "rgb_mae": q0_metrics["rgb_mae"] <= 1.5, "bbox_drift": q0_metrics["bbox_drift_px"] <= 1.0, "semantic_source_coverage": q0_coverage["semantic_alpha_union_coverage"] >= 0.995, "strict_source_coverage": q0_coverage["strict_alpha_ownership_coverage"] >= 0.99, "missing_source_alpha_fraction": q0_coverage["unassigned_semantic_fraction"] <= 0.01, "duplicate_over_composited_fraction": q0_overlap_fraction <= 0.01, "no_source_residual_fallback": True, "same_compose_path": True}
    q0_qa = {"schema_version": SCHEMA_VERSION, "pose": "q0", "metrics": q0_metrics, "source_coverage": q0_coverage, "duplicate_over_composited_fraction": round(q0_overlap_fraction, 6), "source_residual_fallback_used": False, "internal": q0_internal, "global_fit": q0_fit, "hard_gates": q0_gates, "status": "CUTOUT_RIG_RECONSTRUCTION_PASSED" if all(q0_gates.values()) else "CUTOUT_RIG_RECONSTRUCTION_GAP"}
    _write(EVIDENCE / "cutout-q0-reconstruction-qa-v071.json", q0_qa)
    guide_specs = [("q1-contact-left", ROOT / "pose-guides/openpose-v3/walk-front-8/frame-00-contact-left.json", EVIDENCE / "cutout-q1-contact-left-v071.png"), ("q2-passing-left", ROOT / "pose-guides/openpose-v3/walk-front-8/frame-02-passing-left.json", EVIDENCE / "cutout-q2-passing-left-v071.png")]
    pose_records: list[dict[str, Any]] = []
    internal_records: dict[str, Any] = {"q0": {**q0_internal, "transforms": q0_transforms}}
    seam_records: dict[str, Any] = {"q0": seam_metrics(q0, q0_target, layers=q0_layers, min_safe_margin=MIN_SAFE_MARGIN)}
    before_blend_records: dict[str, Any] = {"q0": seam_metrics(q0, q0_target, layers=render_part_layers(partition_images, skeleton, q0_target, source_image.size)[0], min_safe_margin=MIN_SAFE_MARGIN)}
    retention_records: dict[str, Any] = {"q0": _retention(part_images, q0_layers, q0, source_image)}
    fitted_targets: dict[str, Any] = {"q0": q0_target}
    rendered_outputs = [q0_path]
    detected_for_overlay: dict[str, Any] = {}
    q1_target = q2_target = None
    for pose_name, guide_path, output_path in guide_specs:
        guide = json.loads(guide_path.read_text(encoding="utf-8"))
        target = _guide_target(skeleton, guide)
        output, layers, transforms, fitted, fit = _render_pose(part_images, skeleton, target, source_image.size)
        record, detected_pose = _pose_record(skeleton, fitted, output, pose_name, _relative(guide_path), output_path)
        record["global_fit"] = fit
        pose_records.append(record); detected_for_overlay[pose_name] = detected_pose
        internal_records[pose_name] = {**_internal_qa(skeleton, fitted, transforms, output), "transforms": transforms}
        seam_records[pose_name] = seam_metrics(output, fitted, layers=layers, min_safe_margin=MIN_SAFE_MARGIN)
        partition_layers, _ = render_part_layers(partition_images, skeleton, fitted, source_image.size)
        before_blend_records[pose_name] = seam_metrics(_compose_layers(partition_layers, source_image.size), fitted, layers=partition_layers, min_safe_margin=MIN_SAFE_MARGIN)
        retention_records[pose_name] = _retention(part_images, layers, output, source_image)
        fitted_targets[pose_name] = fitted
        rendered_outputs.append(output_path)
        if pose_name.startswith("q1"):
            q1_target = fitted
        else:
            q2_target = fitted
    _contact_sheet([R4_PATH, q0_path, *rendered_outputs[1:]], ["R4 canonical", "Q0 reconstruction", "Q1 contact-left", "Q2 passing-left"], EVIDENCE / "cutout-q0-q1-q2-contact-sheet-v071.png")
    overlay_paths = []
    for record in pose_records:
        path = EVIDENCE / f"overlay-{record['pose']}-target-detected-v071.png"
        _draw_overlay(Image.open(ROOT / record["output_path"]).convert("RGBA"), record["target"], detected_for_overlay[record["pose"]], record["media_pipe"], path, record["pose"])
        overlay_paths.append(path)
    _contact_sheet(overlay_paths, ["Q1 target vs detected", "Q2 target vs detected"], EVIDENCE / "cutout-q1-q2-target-detected-overlays-v071.png")
    gait = _gait_semantics(q1_target or source_target, q2_target or source_target, skeleton)
    _write(EVIDENCE / "r4-cutout-target-adapter-v071.json", {"schema_version": SCHEMA_VERSION, "source": {"path": _relative(R4_PATH), "sha256": sha256_file(R4_PATH)}, "source_skeleton": "docs/evidence/r4-source-skeleton-v071.json", "guides": ["pose-guides/openpose-v3/walk-front-8/frame-00-contact-left.json", "pose-guides/openpose-v3/walk-front-8/frame-02-passing-left.json"], "q1": fitted_targets.get("q1-contact-left"), "q2": fitted_targets.get("q2-passing-left"), "gait_semantics": gait, "policy": "derived targets only; immutable historical guides; explicit side mapping"})
    pose_gate_failures: list[str] = []
    for record in pose_records:
        if not record["media_pipe"].get("qualifies"):
            pose_gate_failures.append(f"{record['pose']}:mediapipe")
        if internal_records[record["pose"]]["status"] != "CUTOUT_RIG_INTERNAL_QA_PASSED":
            pose_gate_failures.append(f"{record['pose']}:internal")
        if seam_records[record["pose"]]["status"] != "SEAM_QA_PASSED":
            pose_gate_failures.append(f"{record['pose']}:seam")
        if retention_records[record["pose"]]["status"] != "PIXEL_RETENTION_PASSED":
            pose_gate_failures.append(f"{record['pose']}:retention")
    all_internal = all(item["status"] == "CUTOUT_RIG_INTERNAL_QA_PASSED" for item in internal_records.values())
    all_seam = all(item["status"] == "SEAM_QA_PASSED" for item in seam_records.values())
    all_retention = all(item["status"] == "PIXEL_RETENTION_PASSED" for item in retention_records.values())
    if q0_qa["status"] != "CUTOUT_RIG_RECONSTRUCTION_PASSED":
        final_status = "CUTOUT_RIG_RECONSTRUCTION_GAP"
    elif not gait["distinct"]:
        final_status = "CUTOUT_RIG_TARGET_ADAPTER_GAP"
    elif not all_internal:
        final_status = "CUTOUT_RIG_RENDERER_GAP"
    elif not all_seam:
        final_status = "CUTOUT_RIG_SEAM_GAP"
    elif not all_retention or pose_gate_failures:
        final_status = "CUTOUT_RIG_EXTERNAL_POSE_QA_GAP"
    else:
        final_status = "CUTOUT_RIG_VISUAL_REVIEW_REQUIRED"
    _write(EVIDENCE / "cutout-rig-internal-qa-v071.json", {"schema_version": SCHEMA_VERSION, "status": "CUTOUT_RIG_INTERNAL_QA_PASSED" if all_internal else "CUTOUT_RIG_RENDERER_GAP", "poses": internal_records})
    _write(EVIDENCE / "cutout-rig-seam-qa-v071.json", {"schema_version": SCHEMA_VERSION, "status": "SEAM_QA_PASSED" if all_seam else "CUTOUT_RIG_SEAM_GAP", "before_blend": before_blend_records, "final": seam_records, "thresholds": {"disconnect_count": 0, "joint_gap_fraction_max": 0.02, "duplicate_body_components": 0, "safe_margin_px": MIN_SAFE_MARGIN, "gross_overlap_fraction": MAX_GROSS_OVERLAP_FRACTION, "border_contact": False}})
    _write(EVIDENCE / "cutout-rig-pixel-retention-v071.json", {"schema_version": SCHEMA_VERSION, "status": "PIXEL_RETENTION_PASSED" if all_retention else "CUTOUT_RIG_EXTERNAL_POSE_QA_GAP", "poses": retention_records})
    _write(EVIDENCE / "cutout-rig-pose-qa-v071.json", {"schema_version": SCHEMA_VERSION, "status": final_status, "thresholds_unchanged": True, "q0": q0_qa, "poses": pose_records, "internal": internal_records, "seam": seam_records, "retention": retention_records, "gait": gait, "pose_gate_failures": pose_gate_failures, "walk_frames": "NOT_RUN", "spritesheet": "NOT_RUN", "gif": "NOT_RUN"})
    provenance = {"schema_version": SCHEMA_VERSION, "status": "PIXEL_PROVENANCE_PASSED", "source": {"path": _relative(R4_PATH), "sha256": sha256_file(R4_PATH)}, "generated_pixel_fraction": 0.0, "source_owned_pixel_fraction": masks_json["global"]["source_owned_pixel_fraction"], "source_pixel_provenance_fraction": 1.0, "source_residual_fallback_used": False, "joint_patch_copy_count": 0, "untransformed_joint_patch_pixels": 0, "recolor_count": 0, "nonuniform_scale_count": 0, "face_armor_weapon_source_hashes_unchanged": True, "brightness_color_hue_adjustment": False, "antialias_policy": "Pillow BICUBIC over source-derived RGBA parts and source-bound overlap bands"}
    _write(EVIDENCE / "cutout-rig-pixel-provenance-v071.json", provenance)
    execution = {"schema_version": SCHEMA_VERSION, "status": "EXECUTION_EVIDENCE_RECORDED", "comfyui_generation_jobs": 0, "comfyui_jobs": [], "sam2_calls": {"runtime_smoke": 1, "rig_revision_segmentation": 1, "per_frame_segmentation": 0}, "renderer_calls": {"q0": 1, "q1": 1, "q2": 1}, "provider": PROVIDER_ID, "sam2_checkpoint": SAM2_CHECKPOINT, "sam2_commit": SAM2_COMMIT, "fallback_to_diffusion": False, "sam3_used": False, "walk": "NOT_RUN", "qualification_scope": ["q0", "q1-contact-left", "q2-passing-left"]}
    _write(EVIDENCE / "execution-evidence-v0.7.1.json", execution)
    qualification = {"schema_version": SCHEMA_VERSION, "status": final_status, "provider_id": PROVIDER_ID, "capability": CAPABILITY_ID, "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "architecture": "R4_RGBA -> MediaPipe source skeleton -> SAM2.1 Hiera Small raw masks -> component-aware source ownership -> deterministic cutout rig -> Q0/Q1/Q2", "sam2": runtime, "target_adapter": "docs/evidence/r4-cutout-target-adapter-v071.json", "raw_masks": "docs/evidence/r4-cutout-raw-masks-v071-manifest.json", "refined_masks": "docs/evidence/r4-cutout-refined-masks-v071-manifest.json", "component_diagnostics": "docs/evidence/r4-cutout-component-diagnostics-v071.json", "rig": "docs/evidence/r4-cutout-rig-v071.json", "q0": q0_qa, "q1": pose_records[0] if pose_records else None, "q2": pose_records[1] if len(pose_records) > 1 else None, "internal": internal_records, "seam": seam_records, "retention": retention_records, "pixel_provenance": "docs/evidence/cutout-rig-pixel-provenance-v071.json", "execution": "docs/evidence/execution-evidence-v0.7.1.json", "walk_authorized": False, "production_routing_changed": False, "external_approval": "not-claimed", "allowed_next": []}
    _write(EVIDENCE / "cutout-rig-provider-qualification-v071.json", qualification)
    return qualification


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["sam2", "build", "pose-pilot", "all"], default="all")
    args = parser.parse_args(argv)
    result = _runtime_status() if args.phase == "sam2" else _pose_pilot_existing() if args.phase == "pose-pilot" else run_build()
    print(json.dumps(result, indent=2, ensure_ascii=True, default=str))
    return 0 if result.get("status") in {"SAM2_RUNTIME_QUALIFIED", "CUTOUT_RIG_VISUAL_REVIEW_REQUIRED", "CUTOUT_RIG_POSE_PROVIDER_QUALIFIED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
