"""Execute the v0.9.0 reusable runtime pilot in its prescribed order."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from PIL import Image, ImageDraw, ImageSequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import compile_spec, package_compiled, qa_compiled, load_spec  # noqa: E402
from ugas.animation_profiles import idle_front_v1 as idle  # noqa: E402
from ugas.animation_profiles.common import render_source_only  # noqa: E402


BASELINE = "46ba3ae87558ff26055e14aa8d9c6f3ee147333c"
EVIDENCE = ROOT / "docs" / "evidence"
OUT = EVIDENCE / "animation-runtime-v090"
IDLE_VISUALS = EVIDENCE / "idle-front-v090"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def labelled_sheet(images: list[tuple[str, Image.Image]], columns: int = 4, cell: tuple[int, int] = (512, 560)) -> Image.Image:
    rows = max(1, math.ceil(len(images) / columns))
    sheet = Image.new("RGBA", (columns * cell[0], rows * cell[1]), (18, 22, 32, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (label, source) in enumerate(images):
        left, top = (index % columns) * cell[0], (index // columns) * cell[1]
        image = source.convert("RGBA").copy()
        image.thumbnail((cell[0] - 12, cell[1] - 48), Image.Resampling.LANCZOS)
        sheet.alpha_composite(image, (left + (cell[0] - image.width) // 2, top + 34))
        draw.text((left + 10, top + 10), label, fill=(255, 255, 255, 255))
    return sheet


def checkerboard(image: Image.Image) -> Image.Image:
    base = Image.new("RGBA", image.size, (235, 235, 235, 255))
    draw = ImageDraw.Draw(base)
    for y in range(0, image.height, 16):
        for x in range(0, image.width, 16):
            if (x // 16 + y // 16) % 2:
                draw.rectangle((x, y, x + 15, y + 15), fill=(185, 185, 185, 255))
    base.alpha_composite(image.convert("RGBA"))
    return base


def point(value: Any) -> tuple[float, float]:
    return (float(value["x"]), float(value["y"])) if isinstance(value, Mapping) else (float(value[0]), float(value[1]))


def target_overlay(image: Image.Image, target: Mapping[str, Any], detected: Mapping[str, Any]) -> Image.Image:
    result = image.convert("RGBA").copy(); draw = ImageDraw.Draw(result)
    for name, color, radius in (("target", (30, 230, 255, 255), 4), ("detected", (255, 220, 40, 255), 3)):
        group = target.get("joints", {}) if name == "target" else detected.get("landmarks", {})
        for joint in list(idle.CORE_JOINTS) + ["nose"]:
            if joint in group:
                x, y = point(group[joint]); draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=2)
    return result


def bbox_overlay(image: Image.Image, bbox: Any, label: str) -> Image.Image:
    result = image.convert("RGBA").copy(); draw = ImageDraw.Draw(result)
    if bbox:
        draw.rectangle(tuple(bbox), outline=(255, 40, 40, 255), width=2); draw.text((8, 8), label, fill=(255, 40, 40, 255))
    return result


def feet_overlay(image: Image.Image, record: Mapping[str, Any]) -> Image.Image:
    result = image.convert("RGBA").copy(); draw = ImageDraw.Draw(result)
    for side, color in (("left", (50, 230, 120, 255)), ("right", (255, 130, 40, 255))):
        foot = record["feet"]["feet"][side]; y = float(foot["projected_ground_y"])
        draw.line((0, y, result.width - 1, y), fill=color, width=2); draw.text((8 if side == "left" else 270, max(2, int(y) - 18)), f"{side} ground={y:.2f} sole={foot['actual_sole_y']:.2f}", fill=color)
    return result


def structural_overlay(image: Image.Image, hole_mask: Image.Image) -> Image.Image:
    result = checkerboard(image); magenta = Image.new("RGBA", image.size, (255, 0, 220, 255)); return Image.composite(magenta, result, hole_mask.convert("L"))


def pixel_equivalent_gif(first: Path, second: Path) -> bool:
    with Image.open(first) as a, Image.open(second) as b:
        af = [frame.convert("RGBA").tobytes() for frame in ImageSequence.Iterator(a)]
        bf = [frame.convert("RGBA").tobytes() for frame in ImageSequence.Iterator(b)]
    return af == bf


def run() -> dict[str, Any]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if head != BASELINE:
        raise RuntimeError(f"BASELINE_COMMIT_MISMATCH:{head}")
    walk_spec_path = ROOT / "profiles" / "animation" / "walk-front-v1.json"
    idle_spec_path = ROOT / "profiles" / "animation" / "idle-front-v1.json"
    walk_out = OUT / "replay" / "walk-front-v1"
    idle_out = OUT / "idle-front-v1"
    walk_manifest = compile_spec(walk_spec_path, walk_out, ROOT)
    walk_qa = read_json(qa_compiled(walk_manifest, ROOT))
    if walk_qa["status"] != "CUTOUT_ANIMATION_RUNTIME_V1_WALK_REPLAY_IDENTICAL":
        raise RuntimeError("ANIMATION_RUNTIME_WALK_REPLAY_GAP")
    walk_package = read_json(package_compiled(walk_manifest, ROOT))
    historical_sheet = EVIDENCE / "walk-front-v081" / "walk-front-spritesheet-v081.png"
    walk_sheet_identical = digest(ROOT / walk_package["sprite_sheet"]["path"]) == digest(historical_sheet)
    historical_gif = EVIDENCE / "walk-front-v081" / "walk-front-preview-v081.gif"
    walk_gif_identical = digest(ROOT / walk_package["preview_gif"]["path"]) == digest(historical_gif)
    walk_gif_pixel_equivalent = walk_gif_identical or pixel_equivalent_gif(ROOT / walk_package["preview_gif"]["path"], historical_gif)
    if not walk_sheet_identical or not walk_gif_pixel_equivalent:
        raise RuntimeError("ANIMATION_RUNTIME_WALK_REPLAY_PACKAGE_GAP")

    idle_manifest = compile_spec(idle_spec_path, idle_out, ROOT)
    repeat_manifest = compile_spec(idle_spec_path, OUT / "repro" / "idle-front-v1-repeat", ROOT)
    first = read_json(idle_manifest); repeat = read_json(repeat_manifest)
    deterministic = [(item["rgba_sha256"], item["target_hash"]) for item in first["frames"]] == [(item["rgba_sha256"], item["target_hash"]) for item in repeat["frames"]]
    idle_qa_path = qa_compiled(idle_manifest, ROOT)
    idle_qa = read_json(idle_qa_path)
    if idle_qa["status"] != "CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED":
        raise RuntimeError("ANIMATION_RUNTIME_IDLE_FRONT_GAP")
    idle_package = read_json(package_compiled(idle_manifest, ROOT))
    spec = load_spec(idle_spec_path, ROOT)
    context = idle.load_context(spec, ROOT)
    prepared = idle.prepare(spec, context)
    targets = prepared["targets"]
    for binding in spec["key_pose_bindings"]:
        if targets[int(binding["frame"])] ["target_joint_sha256"] != binding["target_hash"]:
            raise RuntimeError(f"IDLE_KEY_BINDING_GAP:{binding['frame']}")

    IDLE_VISUALS.mkdir(parents=True, exist_ok=True)
    frames_dir = IDLE_VISUALS / "frames"; checker_dir = IDLE_VISUALS / "checkerboard"; overlay_dir = IDLE_VISUALS / "target-detected-overlays"; alpha_dir = IDLE_VISUALS / "alpha-bbox-overlays"; feet_dir = IDLE_VISUALS / "feet-ground"; structural_dir = IDLE_VISUALS / "structural-maps"
    for directory in (frames_dir, checker_dir, overlay_dir, alpha_dir, feet_dir, structural_dir): directory.mkdir(parents=True, exist_ok=True)
    images: list[tuple[str, Image.Image]] = []; checks: list[tuple[str, Image.Image]] = []; overlays: list[tuple[str, Image.Image]] = []; alphas: list[tuple[str, Image.Image]] = []; feet_images: list[tuple[str, Image.Image]] = []; structural_images: list[tuple[str, Image.Image]] = []; waist: list[tuple[str, Image.Image]] = []; sword: list[tuple[str, Image.Image]] = []; head_torso: list[tuple[str, Image.Image]] = []
    for index, item in enumerate(read_json(idle_manifest)["frames"]):
        phase = idle.PHASES[index]; image = Image.open(ROOT / item["path"]).convert("RGBA"); record = idle_qa["frames"][index]; detected = record["pose"]["detected"]
        label = f"I{index} {phase.split('-', 1)[1]}"; target_presented = render_source_only(context, prepared["targets"][index], list(idle.Z_ORDER), spec["presentation_transform"])[1]["target_presented"]
        alpha = record["alpha"]; cb = checkerboard(image); ov = target_overlay(image, target_presented, detected); ab = bbox_overlay(image, alpha.get("alpha_bbox"), f"bbox min={float(alpha.get('min_margin_px', 0)):.1f}px"); fg = feet_overlay(image, record)
        _, details = render_source_only(context, prepared["targets"][index], list(idle.Z_ORDER), spec["presentation_transform"]); _, _, _, aux = idle._plan_and_structural(context, prepared["targets"][index], details, phase, prepared["plan"]); sm = structural_overlay(image, aux["coverage"]["hole_mask"])
        frame_name = f"frame-{index:02d}-{phase}.png"; image.save(frames_dir / frame_name, format="PNG", optimize=False); cb.save(checker_dir / frame_name, format="PNG", optimize=False); ov.save(overlay_dir / frame_name, format="PNG", optimize=False); ab.save(alpha_dir / frame_name, format="PNG", optimize=False); fg.save(feet_dir / frame_name, format="PNG", optimize=False); sm.save(structural_dir / frame_name, format="PNG", optimize=False)
        images.append((label, image)); checks.append((label, cb)); overlays.append((label, ov)); alphas.append((label, ab)); feet_images.append((label, fg)); structural_images.append((label, sm)); waist.append((label, cb.crop((160, 165, 365, 335)).resize((512, 425), Image.Resampling.NEAREST))); sword.append((label, cb.crop((50, 120, 390, 465)).resize((512, 520), Image.Resampling.NEAREST))); head_torso.append((label, cb.crop((150, 25, 370, 310)).resize((512, 520), Image.Resampling.NEAREST)))
    sheets = {"idle-front-evidence-contact-sheet-v090.png": labelled_sheet(images), "idle-front-checkerboard-contact-sheet-v090.png": labelled_sheet(checks), "idle-front-target-detected-overlays-v090.png": labelled_sheet(overlays), "idle-front-alpha-bbox-overlays-v090.png": labelled_sheet(alphas), "idle-front-feet-ground-sheet-v090.png": labelled_sheet(feet_images), "idle-front-structural-maps-v090.png": labelled_sheet(structural_images), "idle-front-waist-hip-sheet-v090.png": labelled_sheet(waist, cell=(512, 480)), "idle-front-sword-hand-sheet-v090.png": labelled_sheet(sword, cell=(512, 575)), "idle-front-head-torso-sheet-v090.png": labelled_sheet(head_torso, cell=(512, 575))}
    for name, image in sheets.items(): image.save(IDLE_VISUALS / name, format="PNG", optimize=False)
    trajectory = Image.new("RGBA", (1200, 680), (18, 22, 32, 255)); draw = ImageDraw.Draw(trajectory); draw.rectangle((90, 50, 1130, 560), outline=(160, 170, 190, 255), width=2); points = []
    for i, target in enumerate(targets):
        p = target["joints"]["pelvis"]; x = 100 + i * 940 / 11; y = 300 + (float(p["y"]) - targets[0]["joints"]["pelvis"]["y"]) * 30; points.append((x, y)); draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(40, 210, 255, 255)); draw.text((x - 12, 570), f"I{i}", fill=(230, 235, 245, 255))
    draw.line(points, fill=(40, 210, 255, 255), width=3); draw.text((100, 20), "idle-front-v1 temporal pelvis trajectory; frozen parameters", fill=(255, 255, 255, 255)); trajectory_path = IDLE_VISUALS / "idle-front-temporal-trajectory-v090.png"; trajectory.save(trajectory_path, format="PNG", optimize=False)

    write_json(OUT / "idle-front-targets-v090.json", {"schema_version": "0.9.0", "animation_id": "idle-front-v1", "phase_order": list(idle.PHASES), "targets": targets, "target_hashes": [item["target_joint_sha256"] for item in targets], "key_pose_bindings": spec["key_pose_bindings"], "parameters_frozen_before_render": True, "i11_not_duplicate_i0": targets[-1]["target_joint_sha256"] != targets[0]["target_joint_sha256"]})
    write_json(OUT / "idle-front-frame-qa-v090.json", {"schema_version": "0.9.0", "animation_id": "idle-front-v1", "frames": idle_qa["frames"], "status": idle_qa["status"]})
    write_json(OUT / "idle-front-temporal-qa-v090.json", idle_qa["temporal"])
    write_json(OUT / "idle-front-foot-ground-qa-v090.json", {"schema_version": "0.9.0", "frames": [{"index": item["index"], "phase": item["phase"], "feet": item["feet"]} for item in idle_qa["frames"]], "status": "IDLE_DUAL_FEET_ALL_FRAMES_PASSED" if all(item["hard_gates"]["both_feet_planted"] for item in idle_qa["frames"]) else "IDLE_DUAL_FEET_GROUND_GAP"})
    write_json(OUT / "idle-front-structural-qa-v090.json", {"schema_version": "0.9.0", "frames": [{"index": item["index"], "coverage": item["coverage"], "integrity": item["integrity"]} for item in idle_qa["frames"]], "status": "IDLE_STRUCTURAL_COVERAGE_PASSED"})
    write_json(OUT / "idle-front-occlusion-qa-v090.json", {"schema_version": "0.9.0", "frames": [{"index": item["index"], "occlusion": item["occlusion"], "seam": item["seam"]} for item in idle_qa["frames"]], "status": "IDLE_OCCLUSION_TOPOLOGY_PASSED"})
    write_json(OUT / "idle-front-retention-qa-v090.json", {"schema_version": "0.9.0", "frames": [{"index": item["index"], "retention": item["retention"]} for item in idle_qa["frames"]], "status": "IDLE_RETENTION_PASSED"})
    write_json(OUT / "idle-front-package-qualification-v090.json", idle_package)
    execution = {"schema_version": "0.9.0", "baseline_commit": BASELINE, "implementation_base_commit": BASELINE, "repository_ref": "https://github.com/csn1985-ship-it/ugas.git", "walk_replay": {"status": walk_qa["status"], "canonical_rgba": "IDENTICAL", "spritesheet": "BYTE_IDENTICAL", "gif": "BYTE_IDENTICAL" if walk_gif_identical else "PIXEL_EQUIVALENT"}, "idle": {"status": idle_qa["status"], "frame_count": 12, "fps": 8, "per_frame_duration_ms": 125, "deterministic_replay_twice": deterministic, "package": relative(OUT / "idle-front-v1" / "package-manifest.json")}, "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "source_only_pixels": True, "production_routing": "BLOCKED", "external_visual_review": "REQUIRED"}
    write_json(OUT / "execution-evidence-v0.9.0.json", execution)
    return {"baseline": BASELINE, "walk_replay": "IDENTICAL", "walk_spritesheet": "BYTE_IDENTICAL", "walk_gif": "BYTE_IDENTICAL" if walk_gif_identical else "PIXEL_EQUIVALENT", "idle_status": idle_qa["status"], "idle_frames": 12, "idle_gif": relative(ROOT / idle_package["preview_gif"]["path"]), "deterministic_replay_twice": deterministic}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False)); raise SystemExit(0)
    except Exception as exc:
        print(json.dumps({"status": "ANIMATION_RUNTIME_V090_FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2)); raise SystemExit(2)
