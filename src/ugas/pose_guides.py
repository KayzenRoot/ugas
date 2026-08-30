"""Source-controlled deterministic pose/view guides for the v0.5 pilot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .constants import UGAS_VERSION

CANVAS = 512
BASELINE_Y = 478
CENTERLINE_X = 256
VIEW_NAMES = ("front", "left", "right", "back")
WALK_NAMES = (
    "frame-00-contact-left", "frame-01-down-left", "frame-02-passing-left",
    "frame-03-up-left", "frame-04-contact-right", "frame-05-down-right",
    "frame-06-passing-right", "frame-07-high-right",
)


class PoseGuideError(ValueError):
    pass


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _keypoints(*, lean: float = 0.0, stride: float = 0.0, arm: float = 0.0, weapon_side: str = "right") -> dict[str, list[float]]:
    """Return normalized, human-readable skeleton coordinates in 512px space."""
    hip_x = CENTERLINE_X + lean
    return {
        "head": [hip_x, 112], "neck": [hip_x, 160], "pelvis": [hip_x, 286],
        "shoulder_left": [hip_x - 48, 172], "shoulder_right": [hip_x + 48, 172],
        "elbow_left": [hip_x - 58 - arm, 226], "elbow_right": [hip_x + 58 + arm, 226],
        "hand_left": [hip_x - 50 - arm, 286], "hand_right": [hip_x + 50 + arm, 286],
        "knee_left": [hip_x - 34 - stride, 374], "knee_right": [hip_x + 34 + stride, 374],
        "foot_left": [hip_x - 38 - stride, BASELINE_Y], "foot_right": [hip_x + 38 + stride, BASELINE_Y],
        "weapon_tip": [hip_x + (102 if weapon_side == "right" else -102), 392],
        "weapon_grip": [hip_x + (42 if weapon_side == "right" else -42), 272],
    }


def view_guide(view: str) -> dict[str, Any]:
    if view not in VIEW_NAMES:
        raise PoseGuideError(f"unknown view: {view}")
    return {
        "schema_version": UGAS_VERSION, "guide_type": "view", "guide_id": f"view-{view}", "view": view,
        "canvas": {"width": CANVAS, "height": CANVAS}, "baseline_y": BASELINE_Y, "centerline_x": CENTERLINE_X,
        "keypoints": _keypoints(lean={"left": -5, "right": 5}.get(view, 0), arm=8 if view in {"left", "right"} else 0, weapon_side="left" if view == "left" else "right"),
        "orientation_cue": {"facing": view, "camera": "orthographic gameplay reference", "mirror_allowed": False},
        "ground_policy": "both feet rest on baseline_y; no guide pixels below baseline",
        "pivot_policy": "pelvis centerline is stable; x pivot is centerline_x and y pivot is baseline_y",
        "source_controlled": True, "generated_ai_content": False, "deterministic": True,
    }


def walk_guide(index: int) -> dict[str, Any]:
    if index < 0 or index >= len(WALK_NAMES):
        raise PoseGuideError(f"walk frame index must be 0..7: {index}")
    name = WALK_NAMES[index]
    stride = (18, 8, -8, -18, -18, -8, 8, 18)[index]
    lean = (-9, -5, -2, 2, 9, 5, 2, -2)[index]
    arm = (16, 10, 4, 18, 16, 10, 4, 18)[index]
    return {
        "schema_version": UGAS_VERSION, "guide_type": "walk", "guide_id": f"walk-front-8-{name}",
        "animation": "walk", "view": "front", "frame_index": index, "frame_name": name,
        "phase": ("contact", "down", "passing", "up", "contact", "down", "passing", "high")[index],
        "foot_contact": "left" if index < 4 else "right", "canvas": {"width": CANVAS, "height": CANVAS},
        "baseline_y": BASELINE_Y, "centerline_x": CENTERLINE_X, "keypoints": _keypoints(lean=lean, stride=stride, arm=arm),
        "orientation_cue": {"facing": "front", "camera": "orthographic gameplay reference", "mirror_allowed": False},
        "ground_policy": "contact foot is on baseline_y; no guide pixels below baseline",
        "pivot_policy": "pelvis centerline remains stable; x pivot is centerline_x and y pivot is baseline_y",
        "source_controlled": True, "generated_ai_content": False, "deterministic": True,
    }


def validate_pose_guide(guide: dict[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "guide_type", "guide_id", "canvas", "baseline_y", "centerline_x", "keypoints", "ground_policy", "pivot_policy", "source_controlled", "generated_ai_content", "deterministic"}
    missing = sorted(required - set(guide))
    failures: list[str] = []
    if missing: failures.extend(f"missing:{item}" for item in missing)
    canvas = guide.get("canvas", {})
    if canvas.get("width") != CANVAS or canvas.get("height") != CANVAS: failures.append("canvas_must_be_512x512")
    if guide.get("baseline_y") != BASELINE_Y or guide.get("centerline_x") != CENTERLINE_X: failures.append("stable_ground_and_centerline_required")
    points = guide.get("keypoints", {})
    if not isinstance(points, dict) or not {"head", "pelvis", "foot_left", "foot_right", "weapon_tip", "weapon_grip"}.issubset(points): failures.append("explicit_keypoints_incomplete")
    for name, point in (points.items() if isinstance(points, dict) else []):
        if not isinstance(point, list) or len(point) != 2 or not all(isinstance(value, (int, float)) for value in point): failures.append(f"invalid_keypoint:{name}")
        elif not (0 <= point[0] <= CANVAS and 0 <= point[1] <= CANVAS): failures.append(f"keypoint_out_of_canvas:{name}")
    if guide.get("generated_ai_content") is not False or guide.get("source_controlled") is not True or guide.get("deterministic") is not True: failures.append("guide_provenance_invalid")
    return {"status": "POSE_GUIDE_VALID" if not failures else "POSE_GUIDE_INVALID", "guide_id": guide.get("guide_id"), "sha256": _hash(guide), "failures": failures}


def ensure_pose_guides(repo_root: Path) -> dict[str, Any]:
    root = repo_root / "pose-guides"
    views_dir, walk_dir = root / "views", root / "walk-front-8"
    views_dir.mkdir(parents=True, exist_ok=True); walk_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for view in VIEW_NAMES:
        path = views_dir / f"{view}.json"; path.write_text(json.dumps(view_guide(view), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); paths.append(path)
    for index in range(8):
        guide = walk_guide(index); path = walk_dir / f"{guide['frame_name']}.json"; path.write_text(json.dumps(guide, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); paths.append(path)
    validations = [validate_pose_guide(json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    return {"schema_version": UGAS_VERSION, "status": "POSE_GUIDES_VALID" if all(item["status"] == "POSE_GUIDE_VALID" for item in validations) else "POSE_GUIDES_INVALID", "views": [str(path.relative_to(repo_root)) for path in paths[:4]], "walk_frames": [str(path.relative_to(repo_root)) for path in paths[4:]], "guides": validations}


def render_pose_guide(guide: dict[str, Any], destination: Path) -> dict[str, Any]:
    from PIL import Image, ImageDraw
    validation = validate_pose_guide(guide)
    if validation["status"] != "POSE_GUIDE_VALID": raise PoseGuideError("cannot render invalid pose guide")
    image = Image.new("RGBA", (CANVAS, CANVAS), (246, 247, 250, 255)); draw = ImageDraw.Draw(image)
    draw.line((CENTERLINE_X, 24, CENTERLINE_X, BASELINE_Y), fill=(155, 170, 190, 180), width=1)
    draw.line((24, BASELINE_Y, 488, BASELINE_Y), fill=(90, 110, 90, 255), width=2)
    links = [("head", "neck"), ("neck", "pelvis"), ("shoulder_left", "elbow_left"), ("elbow_left", "hand_left"), ("shoulder_right", "elbow_right"), ("elbow_right", "hand_right"), ("pelvis", "knee_left"), ("knee_left", "foot_left"), ("pelvis", "knee_right"), ("knee_right", "foot_right"), ("hand_right", "weapon_grip"), ("weapon_grip", "weapon_tip")]
    points = guide["keypoints"]
    for left, right in links: draw.line((*points[left], *points[right]), fill=(38, 89, 140, 255), width=4)
    for name, point in points.items():
        radius = 6 if name not in {"weapon_tip", "weapon_grip"} else 4
        draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=(210, 74, 76, 255) if "foot" in name else (45, 105, 175, 255))
    label = str(guide.get("frame_name") or guide.get("view") or guide.get("guide_id"))
    draw.text((20, 18), f"UGAS pose guide | {label}", fill=(28, 33, 40, 255))
    destination.parent.mkdir(parents=True, exist_ok=True); image.save(destination, format="PNG", optimize=False)
    return {"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "guide_id": guide["guide_id"], "validation": validation}


def render_pose_guides(repo_root: Path, kind: str = "walk-front-8") -> dict[str, Any]:
    manifest = ensure_pose_guides(repo_root)
    root = repo_root / "tmp" / "pose-guides" / kind
    root.mkdir(parents=True, exist_ok=True)
    paths = [repo_root / path for path in (manifest["walk_frames"] if kind == "walk-front-8" else manifest["views"])]
    rendered = []
    for path in paths:
        guide = json.loads(path.read_text(encoding="utf-8")); rendered.append(render_pose_guide(guide, root / f"{path.stem}.png"))
    from .image_utils import compose_sheet
    sheet = compose_sheet([Path(item["path"]) for item in rendered], root / "contact-sheet.png", 4)
    return {"schema_version": UGAS_VERSION, "status": "POSE_GUIDES_RENDERED", "kind": kind, "guides": rendered, "contact_sheet": sheet}
