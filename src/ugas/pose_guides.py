"""Source-controlled deterministic mannequin pose/view guides for UGAS v0.5.1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .constants import UGAS_VERSION

CANVAS = 512
BASELINE_Y = 478
CENTERLINE_X = 256
POSE_GUIDE_RENDERER_VERSION = "2.0.0"
VIEW_NAMES = ("front", "left", "right", "back")
WALK_NAMES = (
    "frame-00-contact-left", "frame-01-down-left", "frame-02-passing-left",
    "frame-03-up-left", "frame-04-contact-right", "frame-05-down-right",
    "frame-06-passing-right", "frame-07-up-right",
)
CHALLENGE_NAME = "multiref-strong-left-arm-up"


class PoseGuideError(ValueError):
    pass


def guide_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _mirror_x(value: float) -> float:
    return round(CANVAS - value, 3)


def _front_points(*, lean: float = 0.0, stride: float = 0.0, arm: float = 0.0) -> dict[str, list[float]]:
    hip_x = CENTERLINE_X + lean
    return {
        "head": [hip_x, 112], "nose": [hip_x, 98], "neck": [hip_x, 158], "pelvis": [hip_x, 286],
        "shoulder_left": [hip_x - 48, 172], "shoulder_right": [hip_x + 48, 172],
        "elbow_left": [hip_x - 66 - arm, 224], "elbow_right": [hip_x + 66 + arm, 224],
        "hand_left": [hip_x - 56 - arm, 286], "hand_right": [hip_x + 56 + arm, 286],
        "knee_left": [hip_x - 34 - stride, 372], "knee_right": [hip_x + 34 + stride, 366],
        "foot_left": [hip_x - 42 - stride, BASELINE_Y], "foot_right": [hip_x + 42 + stride, BASELINE_Y],
        "foot_left_toe": [hip_x - 60 - stride, BASELINE_Y], "foot_right_toe": [hip_x + 60 + stride, BASELINE_Y],
        "weapon_grip": [hip_x + 42, 270], "weapon_tip": [hip_x + 132, 180],
    }


def _profile_points(*, facing: str = "left", arm_up: bool = False, stride: float = 0.0) -> dict[str, list[float]]:
    """A narrow side silhouette with a nose, single-depth shoulders and oriented feet."""
    left = {
        "head": [244, 112], "nose": [216, 111], "neck": [248, 158], "pelvis": [250, 286],
        "shoulder_left": [233, 172], "shoulder_right": [258, 176],
        "elbow_left": [222, 220] if not arm_up else [218, 116],
        "elbow_right": [260, 232],
        "hand_left": [214, 278] if not arm_up else [206, 64],
        "hand_right": [258, 282],
        "knee_left": [230 - stride, 372], "knee_right": [265 + stride, 366],
        "foot_left": [214 - stride, BASELINE_Y], "foot_right": [280 + stride, BASELINE_Y],
        "foot_left_toe": [190 - stride, BASELINE_Y], "foot_right_toe": [256 + stride, BASELINE_Y],
        "weapon_grip": [224, 274] if arm_up else [216, 278],
        "weapon_tip": [164, 28] if arm_up else [140, 230],
    }
    if facing == "left":
        return left
    return {name: [_mirror_x(point[0]), point[1]] for name, point in left.items()}


def view_guide(view: str) -> dict[str, Any]:
    if view not in VIEW_NAMES:
        raise PoseGuideError(f"unknown view: {view}")
    points = _profile_points(facing=view) if view in {"left", "right"} else _front_points()
    return {
        "schema_version": UGAS_VERSION, "guide_type": "view", "guide_id": f"view-{view}", "view": view,
        "canvas": {"width": CANVAS, "height": CANVAS}, "baseline_y": BASELINE_Y, "centerline_x": CENTERLINE_X,
        "keypoints": points,
        "orientation_cue": {"facing": view, "camera": "orthographic gameplay reference", "mirror_allowed": False, "profile_strict": view in {"left", "right"}},
        "ground_policy": "both feet rest on baseline_y; no guide pixels below baseline_y",
        "pivot_policy": "pelvis centerline is stable; x pivot is centerline_x and y pivot is baseline_y",
        "source_controlled": True, "generated_ai_content": False, "deterministic": True,
        "renderer": {"version": POSE_GUIDE_RENDERER_VERSION, "control_background": [238, 239, 242, 255], "body_color": [105, 112, 122, 255], "joint_color": [74, 81, 91, 255], "weapon_color": [137, 143, 151, 255]},
    }


def walk_guide(index: int) -> dict[str, Any]:
    if index < 0 or index >= len(WALK_NAMES):
        raise PoseGuideError(f"walk frame index must be 0..7: {index}")
    name = WALK_NAMES[index]
    stride = (30, 20, 8, -20, -30, -20, 8, 20)[index]
    lean = (-8, -5, -2, 2, 8, 5, 2, -2)[index]
    arm = (32, 20, 8, 24, 32, 20, 8, 24)[index]
    points = _front_points(lean=lean, stride=stride, arm=arm)
    if index in {1, 2, 3, 5, 6, 7}:
        lifted = "foot_right" if index < 4 else "foot_left"
        lifted_toe = "foot_right_toe" if index < 4 else "foot_left_toe"
        points[lifted][1] = 448; points[lifted_toe][1] = 448
    return {
        "schema_version": UGAS_VERSION, "guide_type": "walk", "guide_id": f"walk-front-8-{name}",
        "animation": "walk", "view": "front", "frame_index": index, "frame_name": name,
        "phase": ("contact", "down", "passing", "up", "contact", "down", "passing", "up")[index],
        "foot_contact": "left" if index < 4 else "right", "canvas": {"width": CANVAS, "height": CANVAS},
        "baseline_y": BASELINE_Y, "centerline_x": CENTERLINE_X, "keypoints": points,
        "orientation_cue": {"facing": "front", "camera": "orthographic gameplay reference", "mirror_allowed": False, "profile_strict": False},
        "ground_policy": "contact foot is on baseline_y; no guide pixels below baseline_y",
        "pivot_policy": "pelvis centerline remains stable; x pivot is centerline_x and y pivot is baseline_y",
        "source_controlled": True, "generated_ai_content": False, "deterministic": True,
        "renderer": {"version": POSE_GUIDE_RENDERER_VERSION, "control_background": [238, 239, 242, 255], "body_color": [105, 112, 122, 255], "joint_color": [74, 81, 91, 255], "weapon_color": [137, 143, 151, 255]},
    }


def challenge_guide() -> dict[str, Any]:
    points = _profile_points(facing="left", arm_up=True, stride=28)
    return {
        "schema_version": UGAS_VERSION, "guide_type": "qualification-challenge", "guide_id": CHALLENGE_NAME,
        "view": "left", "challenge": "strict-left-profile-arm-above-head-forward-leg", "canvas": {"width": CANVAS, "height": CANVAS},
        "baseline_y": BASELINE_Y, "centerline_x": CENTERLINE_X, "keypoints": points,
        "orientation_cue": {"facing": "left", "camera": "orthographic gameplay reference", "mirror_allowed": False, "profile_strict": True},
        "ground_policy": "contact foot rests on baseline_y; no guide pixels below baseline_y",
        "pivot_policy": "pelvis centerline is stable; x pivot is centerline_x and y pivot is baseline_y",
        "source_controlled": True, "generated_ai_content": False, "deterministic": True,
        "renderer": {"version": POSE_GUIDE_RENDERER_VERSION, "control_background": [238, 239, 242, 255], "body_color": [105, 112, 122, 255], "joint_color": [74, 81, 91, 255], "weapon_color": [137, 143, 151, 255]},
    }


def validate_pose_guide(guide: dict[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "guide_type", "guide_id", "canvas", "baseline_y", "centerline_x", "keypoints", "ground_policy", "pivot_policy", "source_controlled", "generated_ai_content", "deterministic", "renderer"}
    missing = sorted(required - set(guide)); failures: list[str] = [f"missing:{item}" for item in missing]
    canvas = guide.get("canvas", {})
    if canvas.get("width") != CANVAS or canvas.get("height") != CANVAS: failures.append("canvas_must_be_512x512")
    if guide.get("baseline_y") != BASELINE_Y or guide.get("centerline_x") != CENTERLINE_X: failures.append("stable_ground_and_centerline_required")
    points = guide.get("keypoints", {}); required_points = {"head", "neck", "pelvis", "foot_left", "foot_right", "weapon_tip", "weapon_grip"}
    if not isinstance(points, dict) or not required_points.issubset(points): failures.append("explicit_keypoints_incomplete")
    for name, point in (points.items() if isinstance(points, dict) else []):
        if not isinstance(point, list) or len(point) != 2 or not all(isinstance(value, (int, float)) for value in point): failures.append(f"invalid_keypoint:{name}")
        elif not (0 <= point[0] <= CANVAS and 0 <= point[1] <= CANVAS): failures.append(f"keypoint_out_of_canvas:{name}")
    if guide.get("generated_ai_content") is not False or guide.get("source_controlled") is not True or guide.get("deterministic") is not True: failures.append("guide_provenance_invalid")
    if guide.get("renderer", {}).get("version") != POSE_GUIDE_RENDERER_VERSION: failures.append("renderer_version_invalid")
    if isinstance(points, dict) and any(points.get(name, [0, 0])[1] > BASELINE_Y + 1 for name in ("foot_left", "foot_right")): failures.append("foot_below_baseline")
    return {"status": "POSE_GUIDE_VALID" if not failures else "POSE_GUIDE_INVALID", "guide_id": guide.get("guide_id"), "sha256": guide_hash(guide), "failures": failures}


def _guide_items() -> list[tuple[str, dict[str, Any]]]:
    return [(f"views/{view}.json", view_guide(view)) for view in VIEW_NAMES] + [(f"walk-front-8/{walk_guide(index)['frame_name']}.json", walk_guide(index)) for index in range(8)] + [(f"challenges/{CHALLENGE_NAME}.json", challenge_guide())]


def ensure_pose_guides(repo_root: Path) -> dict[str, Any]:
    root = repo_root / "pose-guides"; paths: list[Path] = []
    expected = {relative for relative, _ in _guide_items()}
    for stale in root.rglob("*.json"):
        if str(stale.relative_to(root)).replace("\\", "/") not in expected:
            stale.unlink()
    for relative, guide in _guide_items():
        path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(guide, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); paths.append(path)
    validations = [validate_pose_guide(json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    return {"schema_version": UGAS_VERSION, "renderer_version": POSE_GUIDE_RENDERER_VERSION, "status": "POSE_GUIDES_VALID" if all(item["status"] == "POSE_GUIDE_VALID" for item in validations) else "POSE_GUIDES_INVALID", "views": [str(path.relative_to(repo_root)).replace("\\", "/") for path in paths[:4]], "walk_frames": [str(path.relative_to(repo_root)).replace("\\", "/") for path in paths[4:12]], "challenge": str(paths[12].relative_to(repo_root)).replace("\\", "/"), "guides": validations}


def _scaled(point: Iterable[float], size: int = CANVAS) -> tuple[float, float]:
    x, y = point; scale = size / CANVAS; return x * scale, y * scale


def _draw_mannequin(draw: Any, guide: dict[str, Any], *, size: int = CANVAS, review: bool = False) -> None:
    points = guide["keypoints"]; view = str(guide.get("view", "front")); profile = view in {"left", "right"} or guide.get("guide_type") == "qualification-challenge"
    body = (105, 112, 122, 255); joints = (74, 81, 91, 255); weapon = (137, 143, 151, 255)
    def p(name: str) -> tuple[float, float]: return _scaled(points[name], size)
    head_x, head_y = p("head"); head_rx, head_ry = (18, 23) if profile else (24, 24)
    draw.ellipse((head_x - head_rx, head_y - head_ry, head_x + head_rx, head_y + head_ry), fill=body)
    draw.line((*p("neck"), *p("pelvis")), fill=body, width=max(1, round(34 * size / CANVAS)))
    shoulder_l, shoulder_r, pelvis = p("shoulder_left"), p("shoulder_right"), p("pelvis")
    torso_width = 26 if profile else 42
    draw.polygon([(shoulder_l[0] - torso_width, shoulder_l[1]), (shoulder_r[0] + torso_width, shoulder_r[1]), (pelvis[0] + 25, pelvis[1] + 30), (pelvis[0] - 25, pelvis[1] + 30)], fill=body)
    links = [("shoulder_left", "elbow_left"), ("elbow_left", "hand_left"), ("shoulder_right", "elbow_right"), ("elbow_right", "hand_right"), ("pelvis", "knee_left"), ("knee_left", "foot_left"), ("pelvis", "knee_right"), ("knee_right", "foot_right")]
    width = max(1, round((15 if profile else 18) * size / CANVAS))
    for left, right in links: draw.line((*p(left), *p(right)), fill=body, width=width, joint="curve")
    for name in ("shoulder_left", "shoulder_right", "elbow_left", "elbow_right", "hand_left", "hand_right", "pelvis", "knee_left", "knee_right"):
        x, y = p(name); radius = max(2, round(10 * size / CANVAS)); draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=joints)
    for foot, toe in (("foot_left", "foot_left_toe"), ("foot_right", "foot_right_toe")):
        draw.line((*p(foot), *p(toe)), fill=joints, width=max(1, round(13 * size / CANVAS)))
    draw.line((*p("weapon_grip"), *p("weapon_tip")), fill=weapon, width=max(1, round(8 * size / CANVAS)))
    if review:
        draw.line((CENTERLINE_X * size / CANVAS, 18 * size / CANVAS, CENTERLINE_X * size / CANVAS, BASELINE_Y * size / CANVAS), fill=(160, 170, 180, 180), width=max(1, round(size / 512)))
        draw.line((20 * size / CANVAS, BASELINE_Y * size / CANVAS, 492 * size / CANVAS, BASELINE_Y * size / CANVAS), fill=(85, 120, 90, 255), width=max(1, round(2 * size / CANVAS)))


def render_pose_guide(guide: dict[str, Any], destination: Path, *, review: bool = False) -> dict[str, Any]:
    from PIL import Image, ImageDraw
    validation = validate_pose_guide(guide)
    if validation["status"] != "POSE_GUIDE_VALID": raise PoseGuideError("cannot render invalid pose guide")
    background = tuple(guide.get("renderer", {}).get("control_background", [238, 239, 242, 255]))
    image = Image.new("RGBA", (CANVAS, CANVAS), background); draw = ImageDraw.Draw(image); _draw_mannequin(draw, guide, review=review)
    if review:
        label = str(guide.get("frame_name") or guide.get("view") or guide.get("guide_id")); draw.rectangle((12, 12, 500, 40), fill=(255, 255, 255, 235)); draw.text((20, 20), f"UGAS pose guide v2 | {label}", fill=(28, 33, 40, 255))
    destination.parent.mkdir(parents=True, exist_ok=True); image.save(destination, format="PNG", optimize=False)
    return {"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "guide_id": guide["guide_id"], "guide_sha256": validation["sha256"], "renderer_version": POSE_GUIDE_RENDERER_VERSION, "render_parameters": {"size": CANVAS, "review_overlay": review, "background": list(background)}, "validation": validation}


def render_pose_guides(repo_root: Path, kind: str = "walk-front-8") -> dict[str, Any]:
    manifest = ensure_pose_guides(repo_root); root = repo_root / "tmp" / "pose-guides" / "v2" / kind; root.mkdir(parents=True, exist_ok=True)
    relative_paths = manifest["walk_frames"] if kind == "walk-front-8" else manifest["views"]
    rendered = []
    for relative in relative_paths:
        path = repo_root / relative; guide = json.loads(path.read_text(encoding="utf-8")); rendered.append({"control": render_pose_guide(guide, root / f"{path.stem}-control.png"), "review": render_pose_guide(guide, root / f"{path.stem}-review.png", review=True)})
    from .image_utils import compose_sheet
    controls = [Path(item["control"]["path"]) for item in rendered]; reviews = [Path(item["review"]["path"]) for item in rendered]
    control_sheet = compose_sheet(controls, root / "control-contact-sheet.png", 4); review_sheet = compose_sheet(reviews, root / "review-contact-sheet.png", 4)
    return {"schema_version": UGAS_VERSION, "renderer_version": POSE_GUIDE_RENDERER_VERSION, "status": "POSE_GUIDES_RENDERED", "kind": kind, "guides": rendered, "contact_sheet": control_sheet, "review_contact_sheet": review_sheet}


def render_challenge_guide(repo_root: Path) -> dict[str, Any]:
    ensure_pose_guides(repo_root); path = repo_root / "pose-guides" / "challenges" / f"{CHALLENGE_NAME}.json"; guide = json.loads(path.read_text(encoding="utf-8")); root = repo_root / "tmp" / "pose-guides" / "v2" / "challenge"; return {"guide": guide, "control": render_pose_guide(guide, root / f"{CHALLENGE_NAME}-control.png"), "review": render_pose_guide(guide, root / f"{CHALLENGE_NAME}-review.png", review=True)}
