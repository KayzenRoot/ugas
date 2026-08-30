"""Optional independent pose QA estimator for UGAS v0.5.3.

MediaPipe is used only as a QA-side candidate detector. It is never imported
by a ComfyUI workflow and never participates in provider routing. The
versioned task bundle is recorded separately from the Apache-2.0 library; if
the bundle's redistribution/commercial terms cannot be established from an
authoritative source, qualification stops with a model-license gap.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

from .pose_metric_calibration import map_mediapipe_landmarks


SCHEMA_VERSION = "0.5.3"
LIBRARY_NAME = "mediapipe"
MODEL_FILENAME = "pose_landmarker_full.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
LIBRARY_REPOSITORY = "https://github.com/google-ai-edge/mediapipe"
PYTHON_API_URL = "https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/PoseLandmarker"
MODEL_LICENSE_ISSUE_URL = "https://github.com/google-ai-edge/mediapipe/issues/6306"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_model_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.cwd() / ".local"
    return base / "UGAS" / "pose-qa" / MODEL_FILENAME


def download_model(path: Path | None = None, *, timeout: int = 120) -> dict[str, Any]:
    destination = path or _default_model_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file():
        request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "UGAS-pose-qa/0.5.3"})
        with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as stream:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
    return model_metadata(destination)


def model_metadata(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "filename": MODEL_FILENAME, "url": MODEL_URL, "status": "NOT_PRESENT", "bytes": None, "sha256": None,
            "license_status": "UNDETERMINED", "license_gap": "The versioned task bundle has no authoritative redistribution terms recorded in the official API page.",
            "license_evidence_url": MODEL_LICENSE_ISSUE_URL, "outside_git": True, "outside_review_zip": True,
        }
    return {
        "filename": path.name, "path_not_published": True, "url": MODEL_URL, "status": "DOWNLOADED_FOR_LOCAL_QUALIFICATION",
        "bytes": path.stat().st_size, "sha256": _sha256(path), "license_status": "UNDETERMINED",
        "license_gap": "The official library is Apache-2.0, but the versioned .task bundle terms for commercial use and redistribution are not authoritatively determined.",
        "license_evidence_url": MODEL_LICENSE_ISSUE_URL, "outside_git": True, "outside_review_zip": True,
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
    return {"name": LIBRARY_NAME, "installed": True, "version": version, "import_status": import_status, "repository": LIBRARY_REPOSITORY, "api": PYTHON_API_URL, "license": "Apache-2.0 (library repository)"}


def _create_blocked_overlay(repo_root: Path) -> dict[str, Any]:
    from PIL import Image, ImageDraw, ImageFont
    fixture_dir = repo_root / "docs" / "evidence" / "pose-metric-fixtures"
    names = ["target", "neutral_front", "mirrored_wrong_side", "target_plus_long_vertical_sword"]
    cell = 256
    sheet = Image.new("RGBA", (cell * 2, cell * 2), (20, 24, 36, 255))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, name in enumerate(names):
        source_path = fixture_dir / f"{name}.png"
        if source_path.is_file():
            with Image.open(source_path) as source:
                image = source.convert("RGBA").resize((cell, cell))
            sheet.alpha_composite(image, ((index % 2) * cell, (index // 2) * cell))
        left, top = (index % 2) * cell, (index // 2) * cell
        draw.rectangle((left + 4, top + 4, left + cell - 4, top + 28), fill=(255, 255, 255, 225))
        draw.text((left + 8, top + 11), "MODEL DETECTION NOT RUN", fill=(12, 12, 12, 255), font=font)
    destination = repo_root / "docs" / "evidence" / "v053-pose-detection-overlay-contact.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=False)
    return {"path": str(destination.relative_to(repo_root)).replace("\\", "/"), "sha256": _sha256(destination), "status": "NOT_RUN_MODEL_LICENSE_GAP"}


def _detect(path: Path, model_path: Path) -> dict[str, Any]:
    """Run one local image detection when and only when the model is qualified."""
    mp = importlib.import_module("mediapipe")
    vision = importlib.import_module("mediapipe.tasks.python.vision")
    base_options = importlib.import_module("mediapipe.tasks.python.core.base_options")
    options = vision.PoseLandmarkerOptions(base_options=base_options.BaseOptions(model_asset_path=str(model_path)), running_mode=vision.RunningMode.IMAGE, num_poses=1, min_pose_detection_confidence=0.5, min_pose_presence_confidence=0.5, min_tracking_confidence=0.5)
    with vision.PoseLandmarker.create_from_options(options) as landmarker:
        image = mp.Image.create_from_file(str(path))
        result = landmarker.detect(image)
    if not result.pose_landmarks:
        return {"path": str(path), "sha256": _sha256(path), "detected": False, "landmarks": {}, "measurable": 0}
    landmarks = map_mediapipe_landmarks(result.pose_landmarks[0])
    return {"path": str(path), "sha256": _sha256(path), "detected": True, "landmarks": landmarks, "measurable": sum(1 for name in landmarks if name in {"nose", "shoulder_left", "shoulder_right", "elbow_left", "elbow_right", "wrist_left", "wrist_right", "hip_left", "hip_right", "knee_left", "knee_right", "ankle_left", "ankle_right"})}


def qualify_pose_estimator(repo_root: Path, *, download: bool = True) -> dict[str, Any]:
    library = library_metadata()
    model_path = _default_model_path()
    try:
        model = download_model(model_path) if download else model_metadata(model_path)
    except Exception as exc:
        model = model_metadata(None) | {"status": "DOWNLOAD_FAILED", "download_error": f"{type(exc).__name__}: {exc}"}
    overlay = _create_blocked_overlay(repo_root)
    if not library.get("installed") or not str(library.get("import_status", "")).startswith("importable"):
        status = "POSE_QA_ESTIMATOR_GAP"
        reason = "MediaPipe library is not installed or not importable"
    elif model.get("license_status") != "VERIFIED":
        status = "POSE_QA_MODEL_LICENSE_GAP"
        reason = "the MediaPipe .task bundle license/redistribution terms are not authoritatively determined"
    else:
        status = "POSE_QA_ESTIMATOR_QUALIFIED"
        reason = None
    qualification = {
        "schema_version": SCHEMA_VERSION, "status": status, "candidate": "MediaPipe Pose Landmarker",
        "library": library, "model": {key: value for key, value in model.items() if key != "path"},
        "reason": reason, "qa_only": True, "generation_graph_unchanged": True, "custom_nodes_required": False,
        "qualification_set": {"required": ["R4 anchor", "new frontal A", "new pose-controlled output"], "measured": False, "records": [], "blocked_before_detection": status == "POSE_QA_MODEL_LICENSE_GAP"},
        "detected_joint_mapping": "src/ugas/pose_metric_calibration.py:MEDIAPIPE_TO_UGAS",
        "overlay": overlay, "model_outside_git_and_zip": True, "provider_routing_used": False,
        "stop_reason": status if status != "POSE_QA_ESTIMATOR_QUALIFIED" else None,
    }
    (repo_root / "docs" / "evidence" / "pose-qa-estimator-model.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION, "library": library, "model": model, "official_sources": {"repository": LIBRARY_REPOSITORY, "python_api": PYTHON_API_URL, "model_bundle": MODEL_URL, "license_gap": MODEL_LICENSE_ISSUE_URL}}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (repo_root / "docs" / "evidence" / "pose-qa-estimator-qualification.json").write_text(json.dumps(qualification, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return qualification
