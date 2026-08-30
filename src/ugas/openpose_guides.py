"""Deterministic OpenPose-style COCO-18 controls for the v0.5.2 escalation."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable

from .constants import UGAS_VERSION
from .pose_guides import CHALLENGE_NAME, VIEW_NAMES, WALK_NAMES, challenge_guide, view_guide, walk_guide

CANVAS = 512
BASELINE_Y = 478
OPENPOSE_GUIDE_RENDERER_VERSION = "3.0.0"
OPENPOSE_GUIDE_TYPE = "openpose-coco18"
COCO18_JOINTS = (
    "nose", "neck", "shoulder_right", "elbow_right", "wrist_right",
    "shoulder_left", "elbow_left", "wrist_left", "hip_right", "knee_right",
    "ankle_right", "hip_left", "knee_left", "ankle_left", "eye_right",
    "eye_left", "ear_right", "ear_left",
)
COCO18_LIMBS = (
    ("neck", "shoulder_right"), ("shoulder_right", "elbow_right"), ("elbow_right", "wrist_right"),
    ("neck", "shoulder_left"), ("shoulder_left", "elbow_left"), ("elbow_left", "wrist_left"),
    ("neck", "hip_right"), ("hip_right", "knee_right"), ("knee_right", "ankle_right"),
    ("neck", "hip_left"), ("hip_left", "knee_left"), ("knee_left", "ankle_left"),
    ("nose", "neck"), ("nose", "eye_right"), ("eye_right", "ear_right"),
    ("nose", "eye_left"), ("eye_left", "ear_left"),
)
# Fixed, review-friendly BGR-like OpenPose palette expressed as RGB values.
COCO18_LIMB_COLORS = (
    [255, 0, 0, 255], [255, 85, 0, 255], [255, 170, 0, 255], [255, 255, 0, 255],
    [170, 255, 0, 255], [85, 255, 0, 255], [0, 255, 0, 255], [0, 255, 85, 255],
    [0, 255, 170, 255], [0, 255, 255, 255], [0, 170, 255, 255], [0, 85, 255, 255],
    [0, 0, 255, 255], [85, 0, 255, 255], [170, 0, 255, 255], [255, 0, 255, 255],
    [255, 0, 170, 255],
)
JOINT_COLOR = [255, 255, 255, 255]
HIDDEN_JOINT_COLOR = [58, 58, 58, 255]


class OpenPoseGuideError(ValueError):
    pass


def guide_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _joint(source: dict[str, list[float]], source_name: str | None, *, visible: bool = True) -> dict[str, Any]:
    if source_name is None:
        return {"x": 0.0, "y": 0.0, "visible": False, "source": None}
    point = source[source_name]
    return {"x": float(point[0]), "y": float(point[1]), "visible": visible, "source": source_name}


def _convert_legacy(legacy: dict[str, Any], *, guide_id: str, guide_type: str) -> dict[str, Any]:
    points = legacy["keypoints"]
    joints = {
        "nose": _joint(points, "nose"),
        "neck": _joint(points, "neck"),
        "shoulder_right": _joint(points, "shoulder_right"),
        "elbow_right": _joint(points, "elbow_right"),
        "wrist_right": _joint(points, "hand_right"),
        "shoulder_left": _joint(points, "shoulder_left"),
        "elbow_left": _joint(points, "elbow_left"),
        "wrist_left": _joint(points, "hand_left"),
        # The source mannequin has a single pelvis pivot.  Both COCO hip
        # joints intentionally resolve to that same deterministic point.
        "hip_right": _joint(points, "pelvis"),
        "knee_right": _joint(points, "knee_right"),
        "ankle_right": _joint(points, "foot_right"),
        "hip_left": _joint(points, "pelvis"),
        "knee_left": _joint(points, "knee_left"),
        "ankle_left": _joint(points, "foot_left"),
        "eye_right": _joint(points, None),
        "eye_left": _joint(points, None),
        "ear_right": _joint(points, None),
        "ear_left": _joint(points, None),
    }
    return {
        "schema_version": UGAS_VERSION,
        "guide_type": guide_type,
        "guide_id": guide_id,
        "source_guide_id": legacy["guide_id"],
        "source_guide_sha256": guide_hash(legacy),
        "view": legacy.get("view"),
        "animation": legacy.get("animation"),
        "frame_index": legacy.get("frame_index"),
        "frame_name": legacy.get("frame_name"),
        "phase": legacy.get("phase"),
        "foot_contact": legacy.get("foot_contact"),
        "canvas": {"width": CANVAS, "height": CANVAS},
        "baseline_y": BASELINE_Y,
        "joint_schema": "COCO-18",
        "joints": joints,
        "limbs": [{"from": left, "to": right, "color": COCO18_LIMB_COLORS[index]} for index, (left, right) in enumerate(COCO18_LIMBS)],
        "weapon": {
            "grip": {"x": float(points["weapon_grip"][0]), "y": float(points["weapon_grip"][1]), "visible": True},
            "tip": {"x": float(points["weapon_tip"][0]), "y": float(points["weapon_tip"][1]), "visible": True},
        },
        "orientation_cue": legacy.get("orientation_cue", {}),
        "ground_policy": legacy.get("ground_policy"),
        "pivot_policy": legacy.get("pivot_policy"),
        "source_controlled": True,
        "generated_ai_content": False,
        "deterministic": True,
        "renderer": {
            "version": OPENPOSE_GUIDE_RENDERER_VERSION,
            "control_background": [0, 0, 0, 255],
            "limb_colors": list(COCO18_LIMB_COLORS),
            "joint_color": JOINT_COLOR,
            "hidden_joint_color": HIDDEN_JOINT_COLOR,
            "limb_thickness": 8,
            "joint_radius": 9,
            "weapon_color": [255, 255, 255, 255],
        },
    }


def view_openpose_guide(view: str) -> dict[str, Any]:
    if view not in VIEW_NAMES:
        raise OpenPoseGuideError(f"unknown view: {view}")
    return _convert_legacy(view_guide(view), guide_id=f"openpose-v3-view-{view}", guide_type="view")


def walk_openpose_guide(index: int) -> dict[str, Any]:
    if index < 0 or index >= len(WALK_NAMES):
        raise OpenPoseGuideError(f"walk frame index must be 0..7: {index}")
    legacy = walk_guide(index)
    return _convert_legacy(legacy, guide_id=f"openpose-v3-{legacy['guide_id']}", guide_type="walk")


def challenge_openpose_guide() -> dict[str, Any]:
    return _convert_legacy(challenge_guide(), guide_id=f"openpose-v3-{CHALLENGE_NAME}", guide_type="qualification-challenge")


def validate_openpose_guide(guide: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if guide.get("schema_version") not in {"0.5.2", UGAS_VERSION}:
        failures.append("schema_version_invalid")
    if guide.get("guide_type") not in {"view", "walk", "qualification-challenge"}:
        failures.append("guide_type_invalid")
    if guide.get("joint_schema") != "COCO-18":
        failures.append("joint_schema_invalid")
    canvas = guide.get("canvas", {})
    if canvas.get("width") != CANVAS or canvas.get("height") != CANVAS:
        failures.append("canvas_must_be_512x512")
    if guide.get("baseline_y") != BASELINE_Y:
        failures.append("baseline_invalid")
    joints = guide.get("joints")
    if not isinstance(joints, dict) or tuple(joints) != COCO18_JOINTS or len(joints) != 18:
        failures.append("exactly_coco18_joints_required")
    for name in COCO18_JOINTS:
        item = joints.get(name) if isinstance(joints, dict) else None
        if not isinstance(item, dict) or set(item) != {"x", "y", "visible", "source"}:
            failures.append(f"joint_contract_invalid:{name}")
            continue
        if not isinstance(item["visible"], bool):
            failures.append(f"joint_visibility_invalid:{name}")
        if item["visible"] and not (0 <= float(item["x"]) <= CANVAS and 0 <= float(item["y"]) <= CANVAS):
            failures.append(f"joint_out_of_canvas:{name}")
        if not item["visible"] and item["source"] is not None:
            failures.append(f"hidden_joint_source_must_be_null:{name}")
    if guide.get("source_controlled") is not True or guide.get("generated_ai_content") is not False or guide.get("deterministic") is not True:
        failures.append("guide_provenance_invalid")
    renderer = guide.get("renderer", {})
    if renderer.get("version") != OPENPOSE_GUIDE_RENDERER_VERSION or renderer.get("control_background") != [0, 0, 0, 255]:
        failures.append("renderer_contract_invalid")
    if len(guide.get("limbs", [])) != len(COCO18_LIMBS):
        failures.append("coco18_topology_invalid")
    for limb in guide.get("limbs", []):
        if limb.get("from") not in COCO18_JOINTS or limb.get("to") not in COCO18_JOINTS or not isinstance(limb.get("color"), list):
            failures.append("limb_contract_invalid")
    return {"status": "OPENPOSE_GUIDE_VALID" if not failures else "OPENPOSE_GUIDE_INVALID", "guide_id": guide.get("guide_id"), "sha256": guide_hash(guide), "failures": failures}


def _items() -> list[tuple[str, dict[str, Any]]]:
    return (
        [(f"views/{view}.json", view_openpose_guide(view)) for view in VIEW_NAMES]
        + [(f"walk-front-8/{WALK_NAMES[index]}.json", walk_openpose_guide(index)) for index in range(8)]
        + [(f"challenges/{CHALLENGE_NAME}.json", challenge_openpose_guide())]
    )


def ensure_openpose_guides(repo_root: Path) -> dict[str, Any]:
    root = repo_root / "pose-guides" / "openpose-v3"
    root.mkdir(parents=True, exist_ok=True)
    expected = {relative for relative, _ in _items()}
    for stale in root.rglob("*.json"):
        if str(stale.relative_to(root)).replace("\\", "/") not in expected:
            stale.unlink()
    paths: list[Path] = []
    for relative, guide in _items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(guide, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(path)
    validations = [validate_openpose_guide(json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    return {
        "schema_version": UGAS_VERSION,
        "renderer_version": OPENPOSE_GUIDE_RENDERER_VERSION,
        "joint_schema": "COCO-18",
        "status": "OPENPOSE_GUIDES_VALID" if all(item["status"] == "OPENPOSE_GUIDE_VALID" for item in validations) else "OPENPOSE_GUIDES_INVALID",
        "views": [str(path.relative_to(repo_root)).replace("\\", "/") for path in paths[:4]],
        "walk_frames": [str(path.relative_to(repo_root)).replace("\\", "/") for path in paths[4:12]],
        "challenge": str(paths[12].relative_to(repo_root)).replace("\\", "/"),
        "guides": validations,
    }


def _scaled(point: dict[str, Any], size: int) -> tuple[float, float]:
    return float(point["x"]) * size / CANVAS, float(point["y"]) * size / CANVAS


def render_openpose_guide_at_resolution(
    guide: dict[str, Any],
    destination: Path,
    *,
    width: int,
    height: int,
    review: bool = False,
) -> dict[str, Any]:
    """Render the JSON COCO-18 guide directly at a requested resolution.

    Coordinates are scaled from the canonical 512x512 JSON; the source raster
    is never resized. Primitive widths scale with the target bucket so the
    control signal remains legible at model-card resolutions.
    """
    from PIL import Image, ImageDraw, ImageFont

    validation = validate_openpose_guide(guide)
    if validation["status"] != "OPENPOSE_GUIDE_VALID":
        raise OpenPoseGuideError("cannot render invalid OpenPose guide")
    if width < 1 or height < 1:
        raise OpenPoseGuideError("guide dimensions must be positive")
    scale = max(width, height) / CANVAS
    image = Image.new("RGBA", (width, height), tuple(guide["renderer"]["control_background"]))
    draw = ImageDraw.Draw(image)
    radius = max(1, round(int(guide["renderer"]["joint_radius"]) * scale))
    limb_width = max(1, round(int(guide["renderer"]["limb_thickness"]) * scale))
    joints = guide["joints"]
    for limb in guide["limbs"]:
        left, right = joints[limb["from"]], joints[limb["to"]]
        if left["visible"] and right["visible"]:
            x1, y1 = float(left["x"]) * width / CANVAS, float(left["y"]) * height / CANVAS
            x2, y2 = float(right["x"]) * width / CANVAS, float(right["y"]) * height / CANVAS
            draw.line((x1, y1, x2, y2), fill=tuple(limb["color"]), width=limb_width)
    for name in COCO18_JOINTS:
        joint = joints[name]
        if joint["visible"]:
            x, y = float(joint["x"]) * width / CANVAS, float(joint["y"]) * height / CANVAS
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=tuple(guide["renderer"]["joint_color"]))
    weapon = guide.get("weapon", {})
    if weapon.get("grip", {}).get("visible") and weapon.get("tip", {}).get("visible"):
        grip = (float(weapon["grip"]["x"]) * width / CANVAS, float(weapon["grip"]["y"]) * height / CANVAS)
        tip = (float(weapon["tip"]["x"]) * width / CANVAS, float(weapon["tip"]["y"]) * height / CANVAS)
        draw.line((*grip, *tip), fill=tuple(guide["renderer"]["weapon_color"]), width=max(3, limb_width // 2))
    if review:
        draw.line((width // 2, round(16 * scale), width // 2, round(BASELINE_Y * height / CANVAS)), fill=(160, 160, 160, 200), width=max(1, round(2 * scale)))
        draw.line((round(16 * scale), round(BASELINE_Y * height / CANVAS), width - round(16 * scale), round(BASELINE_Y * height / CANVAS)), fill=(80, 210, 100, 255), width=max(1, round(2 * scale)))
        label = str(guide.get("frame_name") or guide.get("view") or guide.get("guide_id"))
        draw.rectangle((round(12 * scale), round(12 * scale), width - round(12 * scale), round(40 * scale)), fill=(255, 255, 255, 235))
        draw.text((round(20 * scale), round(20 * scale)), f"UGAS OpenPose COCO-18 v3 | {label}", fill=(20, 20, 20, 255), font=ImageFont.load_default())
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=False)
    return {
        "path": str(destination),
        "sha256": file_sha256(destination),
        "guide_id": guide["guide_id"],
        "guide_sha256": validation["sha256"],
        "renderer_version": OPENPOSE_GUIDE_RENDERER_VERSION,
        "control_image": not review,
        "review_overlay": review,
        "render_parameters": {"width": width, "height": height, "source_canvas": CANVAS, "background": guide["renderer"]["control_background"], "limb_thickness": limb_width, "joint_radius": radius, "derived_from_json": True, "raster_upscale": False},
    }


def render_openpose_guide(guide: dict[str, Any], destination: Path, *, review: bool = False) -> dict[str, Any]:
    """Compatibility wrapper for the canonical 512x512 renderer."""
    return render_openpose_guide_at_resolution(guide, destination, width=CANVAS, height=CANVAS, review=review)


def render_openpose_guides(repo_root: Path, kind: str = "challenge") -> dict[str, Any]:
    from .image_utils import compose_sheet

    manifest = ensure_openpose_guides(repo_root)
    if kind == "challenge":
        relative_paths = [manifest["challenge"]]
        output_name = "openpose-guide-v3-control-example.png"
    elif kind == "views":
        relative_paths = manifest["views"]
        output_name = "openpose-guides-v3-contact-sheet.png"
    elif kind == "walk-front-8":
        relative_paths = manifest["walk_frames"]
        output_name = "openpose-guides-v3-contact-sheet.png"
    else:
        raise OpenPoseGuideError(f"unknown render kind: {kind}")
    tmp_root = repo_root / "tmp" / "pose-guides" / "v3" / kind
    rendered = []
    for relative in relative_paths:
        path = repo_root / relative
        guide = json.loads(path.read_text(encoding="utf-8"))
        rendered.append(render_openpose_guide(guide, tmp_root / f"{path.stem}-control.png"))
    if len(rendered) == 1:
        destination = repo_root / "docs" / "evidence" / output_name
        shutil.copy2(rendered[0]["path"], destination)
        contact = {"path": str(destination), "sha256": file_sha256(destination)}
    else:
        sheet = compose_sheet([Path(item["path"]) for item in rendered], tmp_root / "control-contact-sheet.png", 4)
        destination = repo_root / "docs" / "evidence" / output_name
        shutil.copy2(sheet["path"], destination)
        contact = {"path": str(destination), "sha256": file_sha256(destination), "source": sheet}
    return {"schema_version": UGAS_VERSION, "renderer_version": OPENPOSE_GUIDE_RENDERER_VERSION, "joint_schema": "COCO-18", "status": "OPENPOSE_GUIDES_RENDERED", "kind": kind, "guides": rendered, "contact_sheet": contact}


def render_openpose_evidence(repo_root: Path) -> dict[str, Any]:
    manifest = render_openpose_guides(repo_root, "challenge")
    views = render_openpose_guides(repo_root, "views")
    challenge_path = repo_root / "pose-guides" / "openpose-v3" / "challenges" / f"{CHALLENGE_NAME}.json"
    challenge = json.loads(challenge_path.read_text(encoding="utf-8"))
    review_path = repo_root / "tmp" / "pose-guides" / "v3" / "challenge" / f"{CHALLENGE_NAME}-review.png"
    review = render_openpose_guide(challenge, review_path, review=True)
    evidence = {
        "schema_version": UGAS_VERSION,
        "status": "OPENPOSE_EVIDENCE_RENDERED",
        "renderer_version": OPENPOSE_GUIDE_RENDERER_VERSION,
        "joint_schema": "COCO-18",
        "control_contract": {"background": [0, 0, 0, 255], "text": False, "limb_thickness": 8, "joint_radius": 9},
        "guide_manifest": ensure_openpose_guides(repo_root),
        "control_example": manifest,
        "contact_sheet": views,
        "review_overlay": review,
    }
    (repo_root / "docs" / "evidence" / "openpose-guide-v3-manifest.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return evidence
