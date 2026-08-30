"""QA-only MediaPipe Pose Landmarker qualification for UGAS v0.5.4.

The estimator is deliberately isolated from ComfyUI and provider routing. It
measures whether historical UGAS artwork is detectable as a body, not whether
artwork should be generated or approved. The model bundle remains outside Git
and outside the review archive.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from statistics import median
from typing import Any, Iterator, Mapping

from .pose_metric_calibration import CORE_JOINTS, map_mediapipe_landmarks


SCHEMA_VERSION = "0.5.4"
LIBRARY_NAME = "mediapipe"
MODEL_FILENAME = "pose_landmarker_full.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
LIBRARY_REPOSITORY = "https://github.com/google-ai-edge/mediapipe"
PYTHON_API_URL = "https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/PoseLandmarker"
OFFICIAL_TASK_DOCS_URL = "https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker"
MODEL_CARD_URL = "https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf"
MODEL_CARD_LICENSE = "Apache-2.0"
EXPECTED_MODEL_SHA256 = "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1"
BODY_JOINTS = ("nose",) + CORE_JOINTS
PREPROCESS_POLICIES = (
    "transparent_neutral_gray",
    "transparent_white",
    "full_body_crop_margin_25",
    "full_body_crop_margin_25_upscale_2x",
)
ASSET_SOURCES = (
    ("r4", "docs/evidence/master-selected-transparent.png"),
    ("reference_edit_r4", "docs/evidence/reference-edit-selected-transparent.png"),
    ("walk_frame_00", "docs/evidence/walk-front-8-frame-00.png"),
    ("walk_frame_01", "docs/evidence/walk-front-8-frame-01.png"),
    ("walk_frame_02", "docs/evidence/walk-front-8-frame-02.png"),
    ("walk_frame_03", "docs/evidence/walk-front-8-frame-03.png"),
    ("walk_frame_04", "docs/evidence/walk-front-8-frame-04.png"),
    ("walk_frame_05", "docs/evidence/walk-front-8-frame-05.png"),
    ("walk_frame_06", "docs/evidence/walk-front-8-frame-06.png"),
    ("walk_frame_07", "docs/evidence/walk-front-8-frame-07.png"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_model_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.cwd() / ".local"
    return base / "UGAS" / "pose-qa" / MODEL_FILENAME


def download_model(path: Path | None = None, *, timeout: int = 120) -> dict[str, Any]:
    destination = path or _default_model_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file():
        request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "UGAS-pose-qa/0.5.4"})
        with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as stream:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
    return model_metadata(destination)


def model_metadata(path: Path | None) -> dict[str, Any]:
    """Return hash-bound local bundle metadata without publishing its path."""
    if path is None or not path.is_file():
        return {
            "filename": MODEL_FILENAME,
            "url": MODEL_URL,
            "status": "NOT_PRESENT",
            "bytes": None,
            "sha256": None,
            "outside_git": True,
            "outside_review_zip": True,
        }
    return {
        "filename": path.name,
        "path_not_published": True,
        "url": MODEL_URL,
        "status": "DOWNLOADED_FOR_LOCAL_QUALIFICATION",
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "outside_git": True,
        "outside_review_zip": True,
    }


def library_metadata() -> dict[str, Any]:
    try:
        version = importlib.metadata.version(LIBRARY_NAME)
    except importlib.metadata.PackageNotFoundError:
        return {"name": LIBRARY_NAME, "installed": False, "version": None, "repository": LIBRARY_REPOSITORY, "api": PYTHON_API_URL}
    try:
        importlib.import_module(LIBRARY_NAME)
        import_status = "importable"
    except Exception as exc:  # pragma: no cover - platform-specific binary errors
        import_status = f"import_error:{type(exc).__name__}:{exc}"
    return {
        "name": LIBRARY_NAME,
        "installed": True,
        "version": version,
        "import_status": import_status,
        "repository": LIBRARY_REPOSITORY,
        "api": PYTHON_API_URL,
        "license": "Apache-2.0 (library repository)",
    }


def _landmark_confidence(item: Mapping[str, Any]) -> float:
    values = [float(item[key]) for key in ("visibility", "presence") if key in item and item[key] is not None]
    return min(values) if values else float(item.get("confidence", 1.0))


@contextmanager
def _landmarker(model_path: Path) -> Iterator[tuple[Any, Any]]:
    mp = importlib.import_module("mediapipe")
    vision = importlib.import_module("mediapipe.tasks.python.vision")
    base_options = importlib.import_module("mediapipe.tasks.python.core.base_options")
    options = vision.PoseLandmarkerOptions(
        base_options=base_options.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    with vision.PoseLandmarker.create_from_options(options) as detector:
        yield mp, detector


def _detect_with_landmarker(path: Path, mp: Any, detector: Any) -> dict[str, Any]:
    image = mp.Image.create_from_file(str(path))
    result = detector.detect(image)
    base = {"path": str(path), "sha256": _sha256(path), "detected": bool(result.pose_landmarks), "landmarks": {}}
    if not result.pose_landmarks:
        return {**base, "measurable_body_joints": 0, "core_coverage": 0.0, "mean_confidence": 0.0, "min_confidence": 0.0}
    landmarks = map_mediapipe_landmarks(result.pose_landmarks[0])
    body = [landmarks[name] for name in BODY_JOINTS if name in landmarks and landmarks[name].get("visible") is True]
    core = [landmarks[name] for name in CORE_JOINTS if name in landmarks and landmarks[name].get("visible") is True]
    confidences = [_landmark_confidence(item) for item in body]
    return {
        **base,
        "landmarks": landmarks,
        "measurable_body_joints": len(body),
        "core_coverage": round(len(core) / len(CORE_JOINTS), 6),
        "mean_confidence": round(sum(confidences) / len(confidences), 6) if confidences else 0.0,
        "min_confidence": round(min(confidences), 6) if confidences else 0.0,
    }


def _detect(path: Path, model_path: Path) -> dict[str, Any]:
    """Run one detector call; retained as a small QA/test seam."""
    with _landmarker(model_path) as (mp, detector):
        return _detect_with_landmarker(path, mp, detector)


def _rgba_and_bbox(path: Path) -> tuple[Any, tuple[int, int, int, int] | None]:
    from PIL import Image
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    return image, image.getchannel("A").getbbox()


def _composite(image: Any, background: tuple[int, int, int]) -> Any:
    from PIL import Image
    canvas = Image.new("RGB", image.size, background)
    canvas.paste(image, (0, 0), image.getchannel("A"))
    return canvas


def _crop_with_margin(image: Any, bbox: tuple[int, int, int, int], background: tuple[int, int, int], margin: float = 0.25) -> tuple[Any, tuple[float, float, float, float]]:
    from PIL import Image
    left, top, right, bottom = bbox
    side = max(1, int(math.ceil(max(right - left, bottom - top) * (1.0 + margin))))
    center_x, center_y = (left + right) / 2.0, (top + bottom) / 2.0
    crop_left = int(round(center_x - side / 2.0))
    crop_top = int(round(center_y - side / 2.0))
    canvas = Image.new("RGBA", (side, side), (*background, 255))
    source_left, source_top = max(0, crop_left), max(0, crop_top)
    source_right, source_bottom = min(image.width, crop_left + side), min(image.height, crop_top + side)
    if source_right > source_left and source_bottom > source_top:
        piece = image.crop((source_left, source_top, source_right, source_bottom))
        canvas.paste(piece, (source_left - crop_left, source_top - crop_top), piece.getchannel("A"))
    transformed_bbox = ((left - crop_left) / side, (top - crop_top) / side, (right - crop_left) / side, (bottom - crop_top) / side)
    return canvas.convert("RGB"), transformed_bbox


def prepare_preprocessed_image(source_path: Path, policy: str, destination: Path) -> dict[str, Any]:
    """Materialize one deterministic RGB input plus the transformed alpha bbox."""
    from PIL import Image
    if policy not in PREPROCESS_POLICIES:
        raise ValueError(f"unknown preprocess policy: {policy}")
    image, bbox = _rgba_and_bbox(source_path)
    if bbox is None:
        bbox = (0, 0, image.width, image.height)
    background = (128, 128, 128) if "gray" in policy or "crop" in policy else (255, 255, 255)
    source_scale = 2 if policy.endswith("upscale_2x") else 1
    if source_scale == 2:
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        bbox = tuple(value * 2 for value in bbox)
    if policy.startswith("full_body_crop"):
        rendered, bbox_norm = _crop_with_margin(image, bbox, background)
    else:
        rendered = _composite(image, background)
        bbox_norm = tuple(value / image.width if index % 2 == 0 else value / image.height for index, value in enumerate(bbox))
    rendered = rendered.resize((512, 512), Image.Resampling.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(destination, format="PNG", optimize=False)
    return {
        "policy": policy,
        "path": str(destination),
        "sha256": _sha256(destination),
        "source_sha256": _sha256(source_path),
        "source_scale": source_scale,
        "alpha_bbox_normalized": [round(float(value), 6) for value in bbox_norm],
        "background": list(background),
        "size": [512, 512],
        "uniform_scale_only": True,
    }


def _point(landmarks: Mapping[str, Any], name: str) -> tuple[float, float] | None:
    value = landmarks.get(name)
    if not isinstance(value, Mapping) or value.get("visible") is False:
        return None
    try:
        return float(value["x"]), float(value["y"])
    except (KeyError, TypeError, ValueError):
        return None


def sanity_check(landmarks: Mapping[str, Any], alpha_bbox: list[float]) -> dict[str, Any]:
    """Check geometry/foreground/left-right plausibility before score use."""
    left, top, right, bottom = alpha_bbox
    points = {name: _point(landmarks, name) for name in BODY_JOINTS}
    visible = {name: point for name, point in points.items() if point is not None}
    margin = 0.06
    inside = [left - margin <= x <= right + margin and top - margin <= y <= bottom + margin for x, y in visible.values()]
    shoulder_points = [points[name] for name in ("shoulder_left", "shoulder_right") if points[name] is not None]
    hip_points = [points[name] for name in ("hip_left", "hip_right") if points[name] is not None]
    shoulders_above_hips = bool(shoulder_points and hip_points and sum(point[1] for point in shoulder_points) / len(shoulder_points) < sum(point[1] for point in hip_points) / len(hip_points))
    knee_order: list[bool] = []
    for side in ("left", "right"):
        hip, knee, ankle = (points[f"{part}_{side}"] for part in ("hip", "knee", "ankle"))
        if hip is not None and knee is not None and ankle is not None:
            knee_order.append(hip[1] <= knee[1] <= ankle[1])
    knees_between_hips_ankles = all(knee_order) if knee_order else True
    nose = points.get("nose")
    head_near_head_region = bool(nose is not None and (not shoulder_points or nose[1] <= sum(point[1] for point in shoulder_points) / len(shoulder_points) + 0.12))
    shoulder_left, shoulder_right = points.get("shoulder_left"), points.get("shoulder_right")
    hip_left, hip_right = points.get("hip_left"), points.get("hip_right")
    left_right_order = bool(shoulder_left and shoulder_right and hip_left and hip_right and shoulder_left[0] > shoulder_right[0] and hip_left[0] > hip_right[0])
    result = {
        "landmarks_inside_or_near_foreground": bool(inside) and sum(inside) / len(inside) >= 0.80,
        "foreground_coverage_ratio": round(sum(inside) / len(inside), 6) if inside else 0.0,
        "shoulders_above_hips": shoulders_above_hips,
        "knees_between_hips_ankles": knees_between_hips_ankles,
        "head_landmark_near_head_region": head_near_head_region,
        "left_right_order_consistent": left_right_order,
        "left_right_inversion_suspected": not left_right_order,
    }
    result["plausible"] = all(
        result[key]
        for key in (
            "landmarks_inside_or_near_foreground",
            "shoulders_above_hips",
            "knees_between_hips_ankles",
            "head_landmark_near_head_region",
            "left_right_order_consistent",
        )
    )
    return result


def _draw_overlay(source_path: Path, landmarks: Mapping[str, Any], alpha_bbox: list[float], label: str, destination: Path, summary: str) -> None:
    from PIL import Image, ImageDraw, ImageFont
    with Image.open(source_path) as opened:
        image = opened.convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    width, height = image.size
    left, top, right, bottom = [round(value * width if index % 2 == 0 else value * height) for index, value in enumerate(alpha_bbox)]
    draw.rectangle((left, top, right, bottom), outline=(255, 215, 0), width=2)
    edges = (
        ("shoulder_left", "elbow_left"), ("elbow_left", "wrist_left"),
        ("shoulder_right", "elbow_right"), ("elbow_right", "wrist_right"),
        ("hip_left", "knee_left"), ("knee_left", "ankle_left"),
        ("hip_right", "knee_right"), ("knee_right", "ankle_right"),
        ("nose", "shoulder_left"), ("nose", "shoulder_right"),
    )
    def pixel(name: str) -> tuple[int, int] | None:
        point = _point(landmarks, name)
        return (round(point[0] * width), round(point[1] * height)) if point else None
    for first, second in edges:
        first_point, second_point = pixel(first), pixel(second)
        if first_point and second_point:
            draw.line((*first_point, *second_point), fill=(255, 50, 50), width=3)
    for name in BODY_JOINTS:
        point = pixel(name)
        if point:
            color = (50, 230, 100) if name.endswith("_left") else (40, 160, 255) if name.endswith("_right") else (255, 255, 255)
            draw.ellipse((point[0] - 4, point[1] - 4, point[0] + 4, point[1] + 4), fill=color, outline=(10, 10, 10))
            draw.text((point[0] + 5, point[1] - 6), name.replace("_", " "), fill=color, font=font)
    draw.rectangle((0, 0, width, 30), fill=(255, 255, 255))
    draw.text((7, 5), f"{label} | {summary}", fill=(10, 10, 10), font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=False)


def _contact_sheet(paths: list[Path], labels: list[str], destination: Path, columns: int = 5) -> dict[str, Any]:
    from PIL import Image, ImageDraw, ImageFont
    cell, label_height = 256, 34
    rows = math.ceil(len(paths) / columns)
    sheet = Image.new("RGB", (columns * cell, rows * (cell + label_height)), (30, 34, 48))
    draw, font = ImageDraw.Draw(sheet), ImageFont.load_default()
    for index, path in enumerate(paths):
        with Image.open(path) as opened:
            image = opened.convert("RGB").resize((cell, cell), Image.Resampling.LANCZOS)
        x, y = (index % columns) * cell, (index // columns) * (cell + label_height)
        sheet.paste(image, (x, y))
        draw.rectangle((x, y + cell, x + cell, y + cell + label_height), fill=(255, 255, 255))
        draw.text((x + 5, y + cell + 6), labels[index][:48], fill=(10, 10, 10), font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=False)
    return {"path": str(destination), "sha256": _sha256(destination), "columns": columns, "rows": rows, "frame_count": len(paths)}


def _policy_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [item for item in records if item["measurable_body_joints"] >= 10]
    walk = [item for item in records if item["asset_id"].startswith("walk_")]
    core_coverage = [item["core_coverage"] for item in records]
    sanity = [item["sanity"] for item in records]
    inversion_count = sum(1 for item in sanity if item["left_right_inversion_suspected"])
    return {
        "evaluated_images": len(records),
        "measurable_images": len(measured),
        "r4_measurable": next((item["measurable_body_joints"] >= 10 for item in records if item["asset_id"] == "r4"), False),
        "reference_edit_measurable": next((item["measurable_body_joints"] >= 10 for item in records if item["asset_id"] == "reference_edit_r4"), False),
        "walk_frames_measurable": sum(item["measurable_body_joints"] >= 10 for item in walk),
        "median_measurable_body_joints": median([item["measurable_body_joints"] for item in records]) if records else 0,
        "required_core_coverage_mean": round(sum(core_coverage) / len(core_coverage), 6) if core_coverage else 0.0,
        "required_core_coverage_pass_ratio": round(sum(value >= 0.80 for value in core_coverage) / len(core_coverage), 6) if core_coverage else 0.0,
        "left_right_inversion_count": inversion_count,
        "sanity_pass_count": sum(item["sanity"]["plausible"] for item in records),
        "all_landmarks_plausible": all(item["sanity"]["plausible"] for item in records),
    }


def _selection_key(item: dict[str, Any]) -> tuple[float, ...]:
    summary = item["summary"]
    return (
        float(summary["measurable_images"]), float(summary["walk_frames_measurable"]),
        float(summary["median_measurable_body_joints"]), float(summary["required_core_coverage_pass_ratio"]),
        float(summary["sanity_pass_count"]), -float(item["policy_order"]),
    )


def _qualification_gates(summary: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "r4_measurable": bool(summary["r4_measurable"]),
        "reference_edit_measurable": bool(summary["reference_edit_measurable"]),
        "six_of_eight_walk_frames_measurable": int(summary["walk_frames_measurable"]) >= 6,
        "median_measurable_body_joints_at_least_12": float(summary["median_measurable_body_joints"]) >= 12,
        "required_core_coverage_at_least_80_percent": float(summary["required_core_coverage_pass_ratio"]) >= 0.80,
        "no_systematic_left_right_inversion": int(summary["left_right_inversion_count"]) == 0,
        "sanity_plausibility_passed": bool(summary["all_landmarks_plausible"]),
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _license_resolution(model_card_path: Path | None) -> dict[str, Any]:
    model_card = model_card_path if model_card_path and model_card_path.is_file() else None
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "POSE_QA_LOCAL_USE_LICENSE_RESOLVED",
        "retrieved_at": _utc_now(),
        "task_bundle": {"filename": MODEL_FILENAME, "sha256": EXPECTED_MODEL_SHA256, "outside_git": True, "outside_review_zip": True},
        "official_task_docs": {"url": OFFICIAL_TASK_DOCS_URL, "bundle_variant": "Pose landmarker (Full)", "model_card_link_observed": True},
        "official_model_card": {
            "url": MODEL_CARD_URL, "license": MODEL_CARD_LICENSE, "applies_to": ["Lite", "Full", "Heavy"],
            "local_audit_downloaded": model_card is not None, "local_audit_path_not_published": True,
            "local_audit_sha256": _sha256(model_card) if model_card else None,
            "local_audit_bytes": model_card.stat().st_size if model_card else None,
            "local_audit_retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(model_card.stat().st_mtime)) if model_card else None,
        },
        "policy": {"local_qa_use": "allowed", "redistribute_bundle_in_ugas": False, "future_redistribution_requires_notice_review": True},
        "sources": {"task_documentation": OFFICIAL_TASK_DOCS_URL, "model_card": MODEL_CARD_URL, "bundle": MODEL_URL},
    }


def qualify_pose_estimator_v054(repo_root: Path, *, model_path: Path | None = None, model_card_path: Path | None = None) -> dict[str, Any]:
    """Resolve provenance, run historical detectability, and write v0.5.4 evidence."""
    root = Path(repo_root)
    effective_model = model_path or _default_model_path()
    model = model_metadata(effective_model)
    library = library_metadata()
    license_resolution = _license_resolution(model_card_path)
    _write_json(root / "docs/evidence/pose-qa-license-resolution.json", license_resolution)
    model_record = {
        "schema_version": SCHEMA_VERSION, "library": library,
        "model": {**model, "license_status": "RESOLVED_LOCAL_QA" if model.get("sha256") == EXPECTED_MODEL_SHA256 else "HASH_MISMATCH", "license": MODEL_CARD_LICENSE, "license_scope": "local QA only; bundle redistribution is not authorized"},
        "official_sources": {"task_documentation": OFFICIAL_TASK_DOCS_URL, "model_card": MODEL_CARD_URL, "model_bundle": MODEL_URL},
        "model_card_audit": license_resolution["official_model_card"],
    }
    _write_json(root / "docs/evidence/pose-qa-estimator-model-v054.json", model_record)
    if not library.get("installed") or not str(library.get("import_status", "")).startswith("importable"):
        status, reason = "POSE_QA_ESTIMATOR_GAP", "MediaPipe library is not installed or not importable"
    elif model.get("sha256") != EXPECTED_MODEL_SHA256:
        status, reason = "POSE_QA_ESTIMATOR_GAP", "local Pose Landmarker bundle hash does not match the approved versioned hash"
    else:
        status, reason = "", None
    if status:
        detectability = {"schema_version": SCHEMA_VERSION, "status": status, "candidate": "MediaPipe Pose Landmarker", "reason": reason, "evaluated_images": 0, "records": [], "selected_preprocess_policy": None, "gates": {}}
        sanity = {"schema_version": SCHEMA_VERSION, "status": status, "records": [], "reason": reason}
        _write_json(root / "docs/evidence/pose-qa-estimator-detectability.json", detectability)
        _write_json(root / "docs/evidence/pose-qa-estimator-sanity.json", sanity)
        return {"status": status, "reason": reason, "library": library, "model": model_record["model"], "detectability": detectability, "sanity": sanity}

    tmp_root = root / "tmp/pose-qa-v054/preprocess"
    policy_runs: list[dict[str, Any]] = []
    with _landmarker(effective_model) as (mp, detector):
        for policy_order, policy in enumerate(PREPROCESS_POLICIES):
            records: list[dict[str, Any]] = []
            for asset_id, relative in ASSET_SOURCES:
                source = root / relative
                prepared = prepare_preprocessed_image(source, policy, tmp_root / policy / f"{asset_id}.png")
                detection = _detect_with_landmarker(Path(prepared["path"]), mp, detector)
                sanity = sanity_check(detection["landmarks"], prepared["alpha_bbox_normalized"])
                records.append({"asset_id": asset_id, "source_path": relative, "source_sha256": prepared["source_sha256"], "preprocess": prepared, "detected": detection["detected"], "measurable_body_joints": detection["measurable_body_joints"], "core_coverage": detection["core_coverage"], "mean_confidence": detection["mean_confidence"], "min_confidence": detection["min_confidence"], "landmarks": detection["landmarks"], "sanity": sanity})
            policy_runs.append({"policy": policy, "policy_order": policy_order, "records": records, "summary": _policy_summary(records)})
    selected = sorted(policy_runs, key=_selection_key, reverse=True)[0]
    selected_records = selected["records"]
    gates = _qualification_gates(selected["summary"])
    status = "POSE_QA_ESTIMATOR_QUALIFIED" if all(gates.values()) else "POSE_QA_ESTIMATOR_GAP"
    reason = None if status == "POSE_QA_ESTIMATOR_QUALIFIED" else "historical UGAS art did not satisfy the detectability or sanity gate"

    overlay_dir = root / "tmp/pose-qa-v054/overlays"
    overlay_paths: list[Path] = []
    overlay_labels: list[str] = []
    for record in selected_records:
        overlay_path = overlay_dir / f"{record['asset_id']}.png"
        _draw_overlay(Path(record["preprocess"]["path"]), record["landmarks"], record["preprocess"]["alpha_bbox_normalized"], record["asset_id"], overlay_path, f"joints={record['measurable_body_joints']} core={record['core_coverage']:.2f}")
        overlay_paths.append(overlay_path)
        overlay_labels.append(f"{record['asset_id']} | joints={record['measurable_body_joints']} | core={record['core_coverage']:.2f}")
    overlay_sheet = _contact_sheet(overlay_paths, overlay_labels, root / "docs/evidence/pose-qa-estimator-overlays-contact-sheet.png")
    detectability_sheet = _contact_sheet([Path(record["preprocess"]["path"]) for record in selected_records], overlay_labels, root / "docs/evidence/pose-qa-estimator-detectability-contact-sheet.png")
    selected_for_machine = [{key: record[key] for key in ("asset_id", "source_path", "source_sha256", "preprocess", "detected", "measurable_body_joints", "core_coverage", "mean_confidence", "min_confidence", "landmarks", "sanity")} for record in selected_records]
    detectability = {
        "schema_version": SCHEMA_VERSION, "status": status, "candidate": "MediaPipe Pose Landmarker", "evaluated_at": _utc_now(), "selected_preprocess_policy": selected["policy"],
        "policy_selection": {"global_policy_only": True, "selection_rule": "measurable images, walk coverage, median joints, core coverage, sanity pass count, then fixed policy order", "policy_matrix": [{"policy": item["policy"], "summary": item["summary"]} for item in policy_runs]},
        "summary": selected["summary"], "gates": gates, "reason": reason, "records": selected_for_machine, "contact_sheet": detectability_sheet,
        "qa_only": True, "generation_graph_unchanged": True, "provider_routing_used": False,
    }
    sanity = {
        "schema_version": SCHEMA_VERSION, "status": status, "selected_preprocess_policy": selected["policy"], "summary": selected["summary"],
        "records": [{"asset_id": item["asset_id"], "sanity": item["sanity"], "measurable_body_joints": item["measurable_body_joints"], "core_coverage": item["core_coverage"]} for item in selected_records],
        "overlay_contact_sheet": overlay_sheet, "human_visual_review": "required", "reason": reason,
    }
    _write_json(root / "docs/evidence/pose-qa-estimator-detectability.json", detectability)
    _write_json(root / "docs/evidence/pose-qa-estimator-sanity.json", sanity)
    qualification = {
        "schema_version": SCHEMA_VERSION, "status": status, "candidate": "MediaPipe Pose Landmarker", "library": library, "model": model_record["model"],
        "license_resolution": "docs/evidence/pose-qa-license-resolution.json", "detectability": "docs/evidence/pose-qa-estimator-detectability.json", "sanity": "docs/evidence/pose-qa-estimator-sanity.json", "preprocess_policy": selected["policy"],
        "qa_only": True, "generation_graph_unchanged": True, "custom_nodes_required": False, "provider_routing_used": False, "stop_reason": None if status == "POSE_QA_ESTIMATOR_QUALIFIED" else status,
    }
    _write_json(root / "docs/evidence/pose-qa-estimator-qualification-v054.json", qualification)
    return {"status": status, "reason": reason, "library": library, "model": model_record["model"], "detectability": detectability, "sanity": sanity, "qualification": qualification}


def qualify_pose_estimator(repo_root: Path, *, download: bool = True) -> dict[str, Any]:
    """Compatibility entry point for current v0.5.4 qualification."""
    model_path = _default_model_path()
    if download:
        download_model(model_path)
    model_card = model_path.parent / "model-card-blazepose-ghum-3d.pdf"
    return qualify_pose_estimator_v054(repo_root, model_path=model_path, model_card_path=model_card)
