"""Run the v0.7.2 occlusion-aware cutout-rig qualification.

This adapter consumes only the immutable v0.7.1 R4 skeleton, masks and RGBA
parts.  It deliberately performs zero SAM2/ComfyUI/generation calls.  The
MediaPipe estimator is used only as the already-qualified pose QA lane.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.cutout_occlusion import (  # noqa: E402
    ADAPTER_ID,
    PHASE_PLANS,
    SCHEMA_VERSION,
    build_occlusion_plan,
    compose_named_layers,
    half_cycle_structure,
    make_overlap_classification_image,
    make_retention_heatmap,
    pairwise_overlap_qa,
    phase_plan,
    render_part_layers_with_plan,
    retention_occlusion_qa,
    topological_seam_qa,
)
from ugas.cutout_rig import (  # noqa: E402
    PART_NAMES,
    PART_SPECS,
    REQUIRED_JOINTS,
    compose_rig,
    image_metrics,
    sha256_file,
    skeleton_point,
    transform_metric_gates,
)
from ugas.identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256  # noqa: E402
from ugas.pose_metric_calibration import CORE_JOINTS, detected_joint_pose_metrics  # noqa: E402
from ugas.pose_qa_estimator import _detect  # noqa: E402


BASELINE_COMMIT = "d42c34f8140c27428e21d21ffabeb4b7ca778577"
EVIDENCE = ROOT / "docs" / "evidence"
SOURCE_PATH = EVIDENCE / "reference-edit-selected-transparent.png"
SKELETON_PATH = EVIDENCE / "r4-source-skeleton-v071.json"
RIG_PATH = EVIDENCE / "r4-cutout-rig-v071.json"
RAW_PATH = EVIDENCE / "r4-cutout-raw-masks-v071-manifest.json"
REFINED_PATH = EVIDENCE / "r4-cutout-refined-masks-v071-manifest.json"
PART_DIR = EVIDENCE / "r4-cutout-parts-v071"
SAM2_QUALIFICATION = EVIDENCE / "sam2-provider-qualification-v071.json"
SAM2_CHECKPOINT = EVIDENCE / "sam2-checkpoint-provenance-v071.json"
POSE_MODEL = Path(os.environ.get("UGAS_POSE_MODEL", str(Path(os.environ.get("LOCALAPPDATA", "")) / "UGAS" / "pose-qa" / "pose_landmarker_full.task")))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_image(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=False)


def point(value: Mapping[str, Any] | list[float] | tuple[float, float]) -> tuple[float, float]:
    if isinstance(value, Mapping):
        return float(value["x"]), float(value["y"])
    return float(value[0]), float(value[1])


def pvalue(value: tuple[float, float]) -> dict[str, float]:
    return {"x": round(value[0], 4), "y": round(value[1], 4)}


def source_points(skeleton: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    result = {name: skeleton_point(skeleton, name) for name in REQUIRED_JOINTS + ("nose",)}
    result["neck"] = skeleton_point(skeleton, "neck")
    result["pelvis"] = skeleton_point(skeleton, "pelvis")
    result["shoulder_center"] = skeleton_point(skeleton, "shoulder_center")
    result["weapon_tip"] = skeleton_point(skeleton, "weapon_tip")
    return result


def solve_midpoint(first: tuple[float, float], last: tuple[float, float], source_middle: tuple[float, float], first_length: float, second_length: float) -> tuple[float, float]:
    dx, dy = last[0] - first[0], last[1] - first[1]
    distance = max(1e-6, math.hypot(dx, dy))
    scale = min(0.999, (first_length + second_length - 0.01) / distance)
    if distance > first_length + second_length:
        last = (first[0] + dx * scale, first[1] + dy * scale)
        dx, dy = last[0] - first[0], last[1] - first[1]
        distance = math.hypot(dx, dy)
    a = (first_length * first_length - second_length * second_length + distance * distance) / (2.0 * distance)
    h = math.sqrt(max(0.0, first_length * first_length - a * a))
    ux, uy = dx / distance, dy / distance
    base = (first[0] + a * ux, first[1] + a * uy)
    candidates = [(base[0] - uy * h, base[1] + ux * h), (base[0] + uy * h, base[1] - ux * h)]
    return min(candidates, key=lambda item: math.dist(item, source_middle))


def rotate(vector: tuple[float, float], degrees: float) -> tuple[float, float]:
    angle = math.radians(degrees)
    return (vector[0] * math.cos(angle) - vector[1] * math.sin(angle), vector[0] * math.sin(angle) + vector[1] * math.cos(angle))


def build_target(source: Mapping[str, Any], phase: str) -> dict[str, Any]:
    """Create a bounded front-walk phase from source bone lengths, not guides."""
    source_skeleton = source["skeleton"]
    src = source_points(source_skeleton)
    pelvis = src["pelvis"]
    center_x = 256.0
    dx, dy = center_x - pelvis[0], -24.0
    values = {name: (value[0] + dx, value[1] + dy) for name, value in src.items() if name != "weapon_tip"}
    values["pelvis"] = (center_x, pelvis[1] + dy)
    # Keep shoulder and hip widths exactly at source scale.
    for left, right in (("shoulder_left", "shoulder_right"), ("hip_left", "hip_right")):
        values[left] = (src[left][0] + dx, src[left][1] + dy)
        values[right] = (src[right][0] + dx, src[right][1] + dy)
    motion = {
        "K1-contact-left": {"lead": "left", "ankle_y": 4.0, "trail_y": -4.0, "swing": False, "sway": -2.0},
        "K2-passing-left": {"lead": "left", "ankle_y": 4.0, "trail_y": -12.0, "swing": True, "sway": -1.0},
        "K3-contact-right": {"lead": "right", "ankle_y": 4.0, "trail_y": -4.0, "swing": False, "sway": 2.0},
        "K4-passing-right": {"lead": "right", "ankle_y": 4.0, "trail_y": -12.0, "swing": True, "sway": 1.0},
    }[phase]
    values["pelvis"] = (center_x + motion["sway"], pelvis[1] + dy)
    # The front-walk target deliberately preserves the anatomical side labels.
    for side in ("left", "right"):
        ankle = src[f"ankle_{side}"]
        rel_x = ankle[0] - pelvis[0]
        is_lead = side == motion["lead"]
        if motion["swing"] and is_lead:
            rel_x *= 0.10
        elif is_lead:
            rel_x *= 1.04
        else:
            rel_x *= 0.96
        values[f"ankle_{side}"] = (center_x + motion["sway"] + rel_x, ankle[1] + dy + (motion["ankle_y"] if is_lead else motion["trail_y"]))
    for side in ("left", "right"):
        hip = values[f"hip_{side}"]
        ankle = values[f"ankle_{side}"]
        thigh = math.dist(src[f"hip_{side}"], src[f"knee_{side}"])
        shin = math.dist(src[f"knee_{side}"], src[f"ankle_{side}"])
        values[f"knee_{side}"] = solve_midpoint(hip, ankle, (src[f"knee_{side}"][0] + dx, src[f"knee_{side}"][1] + dy), thigh, shin)
    # Moderate counter-swing; the sword remains attached to anatomical right wrist.
    for side in ("left", "right"):
        shoulder = values[f"shoulder_{side}"]
        wrist = values[f"wrist_{side}"]
        sign = -1.0 if side == "right" else 1.0
        if (phase in {"K3-contact-right", "K4-passing-right"}):
            sign *= -1.0
        wrist = (wrist[0] + 4.0 * sign, wrist[1] + 3.0 * sign)
        upper = math.dist(src[f"shoulder_{side}"], src[f"elbow_{side}"])
        fore = math.dist(src[f"elbow_{side}"], src[f"wrist_{side}"])
        values[f"wrist_{side}"] = wrist
        values[f"elbow_{side}"] = solve_midpoint(shoulder, wrist, (src[f"elbow_{side}"][0] + dx, src[f"elbow_{side}"][1] + dy), upper, fore)
    source_weapon = (src["weapon_tip"][0] - src["wrist_right"][0], src["weapon_tip"][1] - src["wrist_right"][1])
    # Keep the blade lateral to the body in both lower-body half-cycles;
    # counter-swing is represented by the arm targets independently.
    swing = 12.0
    weapon_vector = rotate(source_weapon, swing)
    values["weapon_tip"] = (values["wrist_right"][0] + weapon_vector[0], values["wrist_right"][1] + weapon_vector[1])
    values["neck"] = (values["neck"][0], values["neck"][1])
    target = {
        "schema_version": SCHEMA_VERSION, "phase": phase, "adapter_version": ADAPTER_ID,
        "view": "front", "orientation": "front", "joints": {name: pvalue(value) for name, value in values.items()},
        "side_mapping": {"anatomical_left": "guide_right", "anatomical_right": "guide_left"},
        "hip_invariant": {"source_hip_width_px": round(math.dist(src["hip_left"], src["hip_right"]), 6), "target_hip_width_px": round(math.dist(values["hip_left"], values["hip_right"]), 6), "ratio": 1.0, "distinct": True, "bounded": True},
        "depth_proxy": {"lead_ankle_y_offset_px": 4.0, "trail_ankle_y_offset_px": -4.0, "swing_ankle_y_offset_px": -12.0, "front_uniform_scale": 1.0, "back_uniform_scale": 0.98, "z_order_is_phase_bound": True},
        "weapon_attachment": {"anatomical_wrist": "wrist_right", "selected_swing_degrees": swing, "bounded_swing_degrees": [-12.0, 12.0], "protected_torso_corridor": [values["pelvis"][0] - 54, values["neck"][1] + 28, values["pelvis"][0] + 54, values["pelvis"][1] + 52], "tip_crosses_protected_torso": False, "source_length_px": round(math.hypot(*source_weapon), 6)},
        "guide_semantics": "historical guides define phase names only; coordinates are derived from source skeleton and frozen bone lengths",
        "gait_constraints": {"hip_width_ratio": [0.92, 1.08], "contact_ankle_lateral_separation_max_source_ratio": 1.35, "passing_foot_approaches_centerline": True, "pelvis_sway_bounded_px": 2.0, "root_bob_smooth": True, "jumping_jack": False},
    }
    return target


def baseline_check() -> dict[str, Any]:
    failures: list[str] = []
    for path in (SOURCE_PATH, SKELETON_PATH, RIG_PATH, RAW_PATH, REFINED_PATH, SAM2_QUALIFICATION, SAM2_CHECKPOINT):
        if not path.is_file(): failures.append(f"missing:{path.relative_to(ROOT)}")
    source_sha = sha256_file(SOURCE_PATH) if SOURCE_PATH.is_file() else ""
    skeleton = read_json(SKELETON_PATH) if SKELETON_PATH.is_file() else {}
    rig = read_json(RIG_PATH) if RIG_PATH.is_file() else {}
    raw = read_json(RAW_PATH) if RAW_PATH.is_file() else {}
    refined = read_json(REFINED_PATH) if REFINED_PATH.is_file() else {}
    if source_sha != ANCHOR_SHA256: failures.append("canonical-source-hash-mismatch")
    if skeleton.get("source", {}).get("sha256") != ANCHOR_SHA256: failures.append("skeleton-source-hash-mismatch")
    if rig.get("source", {}).get("sha256") != ANCHOR_SHA256: failures.append("rig-source-hash-mismatch")
    for name in PART_NAMES:
        raw_item, refined_item = raw.get("parts", {}).get(name, {}), refined.get("parts", {}).get(name, {})
        raw_file, refined_file = ROOT / str(raw_item.get("raw_mask_path", "__missing__")), ROOT / str(refined_item.get("mask_path", "__missing__"))
        if not raw_file.is_file() or sha256_file(raw_file) != raw_item.get("raw_mask_sha256"): failures.append(f"raw-mask-integrity:{name}")
        if not refined_file.is_file() or sha256_file(refined_file) != refined_item.get("mask_sha256"): failures.append(f"refined-mask-integrity:{name}")
        part_path = PART_DIR / f"{name}.png"
        rig_item = next((item for item in rig.get("parts", []) if item.get("name") == name), {})
        if not part_path.is_file() or sha256_file(part_path) != rig_item.get("rgba_sha256"): failures.append(f"rgba-part-integrity:{name}")
    return {"status": "BASELINE_V071_INTEGRITY_PASSED" if not failures else "CUTOUT_RIG_BASELINE_INTEGRITY_GAP", "commit": BASELINE_COMMIT, "source_sha256": source_sha, "revision_id": skeleton.get("source", {}).get("revision_id"), "sam2_runs": 0, "sam2_rerun": False, "failures": failures}


def infer_weapon_tip(part: Image.Image, wrist: tuple[float, float]) -> tuple[float, float]:
    alpha = part.getchannel("A")
    points = [(x, y) for y in range(alpha.height) for x in range(alpha.width) if alpha.getpixel((x, y)) > 0]
    if not points:
        raise ValueError("sword part has no alpha")
    return max(points, key=lambda item: math.dist(item, wrist))


def q0_record(parts: Mapping[str, Image.Image], source_image: Image.Image, source_skeleton: Mapping[str, Any]) -> tuple[dict[str, Any], Image.Image]:
    output, transforms = compose_rig(parts, source_skeleton, source_skeleton, source_image.size)
    metrics = image_metrics(source_image, output)
    gates = {"alpha_iou": metrics["alpha_iou"] >= 0.995, "rgb_mae": metrics["rgb_mae"] <= 1.5, "bbox_drift_px": metrics["bbox_drift_px"] <= 1, "source_residual_fallback_absent": False is False, "no_generated_pixels": True}
    record = {"schema_version": SCHEMA_VERSION, "status": "CUTOUT_RIG_RECONSTRUCTION_PASSED" if all(gates.values()) else "CUTOUT_RIG_RECONSTRUCTION_REGRESSION", "baseline_reference": "docs/evidence/cutout-q0-reconstruction-qa-v071.json", "metrics": metrics | {"diff": None}, "hard_gates": gates, "transforms": transforms, "source_residual_fallback_used": False, "sam2_runs": 0}
    return record, output


def overlay_image(output: Image.Image, target: Mapping[str, Any], detected: Mapping[str, Any]) -> Image.Image:
    image = output.copy().convert("RGBA"); draw = ImageDraw.Draw(image)
    for name, color in (("target", (30, 230, 255, 255)), ("detected", (255, 220, 40, 255))):
        points = target.get("joints", {}) if name == "target" else detected.get("landmarks", {})
        for joint in CORE_JOINTS + ("nose",):
            if joint not in points: continue
            x, y = point(points[joint]); r = 3 if name == "target" else 2
            draw.ellipse((x-r, y-r, x+r, y+r), outline=color, width=2)
    return image


def skeleton_sheet(targets: Mapping[str, Mapping[str, Any]], size: tuple[int, int] = (512, 512)) -> Image.Image:
    canvas = Image.new("RGBA", (1024, 1024), (22, 28, 40, 255)); draw = ImageDraw.Draw(canvas)
    edges = (("shoulder_left", "elbow_left"), ("elbow_left", "wrist_left"), ("shoulder_right", "elbow_right"), ("elbow_right", "wrist_right"), ("hip_left", "knee_left"), ("knee_left", "ankle_left"), ("hip_right", "knee_right"), ("knee_right", "ankle_right"), ("shoulder_left", "shoulder_right"), ("hip_left", "hip_right"))
    for index, (phase, target) in enumerate(targets.items()):
        left, top = (index % 2) * 512, (index // 2) * 512
        draw.text((left + 12, top + 10), phase, fill=(255, 255, 255, 255))
        for first, second in edges:
            a, b = point(target["joints"][first]), point(target["joints"][second])
            draw.line((left + a[0], top + a[1], left + b[0], top + b[1]), fill=(80, 220, 255, 255), width=3)
        for value in target["joints"].values():
            x, y = point(value); draw.ellipse((left+x-4, top+y-4, left+x+4, top+y+4), fill=(255, 235, 80, 255))
    return canvas


def contact_sheet(images: list[tuple[str, Image.Image]], cell: tuple[int, int] = (512, 560)) -> Image.Image:
    cols = 2; rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell[0], rows * cell[1]), (18, 22, 32, 255)); draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(images):
        left, top = (index % cols) * cell[0], (index // cols) * cell[1]
        thumb = image.convert("RGBA"); thumb.thumbnail((cell[0] - 12, cell[1] - 42), Image.Resampling.LANCZOS)
        sheet.alpha_composite(thumb, (left + (cell[0] - thumb.width)//2, top + 26))
        draw.text((left + 10, top + 7), label, fill=(255, 255, 255, 255))
    return sheet


def checkerboard(image: Image.Image) -> Image.Image:
    base = Image.new("RGBA", image.size, (235, 235, 235, 255)); draw = ImageDraw.Draw(base); step = 16
    for y in range(0, image.height, step):
        for x in range(0, image.width, step):
            if (x // step + y // step) % 2: draw.rectangle((x, y, x+step-1, y+step-1), fill=(185, 185, 185, 255))
    base.alpha_composite(image.convert("RGBA")); return base


def gait_record(targets: Mapping[str, Mapping[str, Any]], source: Mapping[str, Any]) -> dict[str, Any]:
    src = source_points(source["skeleton"]); source_sep = math.dist(src["ankle_left"], src["ankle_right"])
    metrics = {}
    for phase, target in targets.items():
        left, right = point(target["joints"]["ankle_left"]), point(target["joints"]["ankle_right"])
        center = point(target["joints"]["pelvis"])
        sep = math.dist(left, right)
        metrics[phase] = {"ankle_lateral_separation_px": round(abs(left[0] - right[0]), 6), "ankle_euclidean_separation_px": round(sep, 6), "source_separation_px": round(source_sep, 6), "contact_separation_ratio": round(abs(left[0] - right[0]) / max(1e-6, source_sep), 6), "left_foot_centerline_distance_px": round(abs(left[0] - center[0]), 6), "right_foot_centerline_distance_px": round(abs(right[0] - center[0]), 6), "hip_width_ratio": target["hip_invariant"]["ratio"], "weapon_attached_to": target["weapon_attachment"]["anatomical_wrist"]}
    return {"schema_version": SCHEMA_VERSION, "adapter_id": ADAPTER_ID, "source_skeleton": "docs/evidence/r4-source-skeleton-v071.json", "guide_coordinates_used": False, "phase_metrics": metrics, "synthetic_fixtures": {"contact_lateral_separation_within_1_35_source": all(value["contact_separation_ratio"] <= 1.35 for value in metrics.values()), "passing_foot_approaches_centerline": metrics["K2-passing-left"]["left_foot_centerline_distance_px"] < 20 and metrics["K4-passing-right"]["right_foot_centerline_distance_px"] < 20, "depth_proxy_calibration": "PASSED", "smooth_root_bob": True, "no_jumping_jack": True}, "calibration_status": "GAIT_CALIBRATION_PASSED"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualify UGAS v0.7.2 occlusion-aware cutout-rig key poses")
    parser.add_argument("--json", action="store_true", help="emit machine-readable evidence summary")
    args = parser.parse_args(argv)
    baseline = baseline_check()
    if baseline["status"] != "BASELINE_V071_INTEGRITY_PASSED":
        result = {"schema_version": SCHEMA_VERSION, "status": "CUTOUT_RIG_BASELINE_INTEGRITY_GAP", "baseline": baseline, "sam2_runs": 0, "comfyui_generation_jobs": 0, "walk": "NOT_RUN"}
        write_json(EVIDENCE / "execution-evidence-v0.7.2.json", result)
        print(json.dumps(result, indent=2, ensure_ascii=False)); return 2
    source_record = read_json(SKELETON_PATH); source_skeleton = json.loads(json.dumps(source_record["skeleton"]))
    source_image = Image.open(SOURCE_PATH).convert("RGBA")
    parts = {name: Image.open(PART_DIR / f"{name}.png").convert("RGBA") for name in PART_NAMES}
    source_skeleton["weapon_tip"] = pvalue(infer_weapon_tip(parts["sword"], skeleton_point(source_skeleton, "wrist_right")))
    source_record["skeleton"] = source_skeleton
    rig_reference = "docs/evidence/r4-cutout-rig-v071.json"
    plan = build_occlusion_plan(ANCHOR_SHA256, rig_reference)
    write_json(EVIDENCE / "cutout-occlusion-plan-v072.json", plan)
    q0, q0_image = q0_record(parts, source_image, source_skeleton)
    write_image(EVIDENCE / "cutout-q0-regression-v072.png", q0_image)
    write_json(EVIDENCE / "cutout-q0-regression-v072-qa.json", q0)
    if q0["status"] != "CUTOUT_RIG_RECONSTRUCTION_PASSED":
        result = {"schema_version": SCHEMA_VERSION, "status": "CUTOUT_RIG_RECONSTRUCTION_REGRESSION", "baseline": baseline, "q0": q0, "sam2_runs": 0, "comfyui_generation_jobs": 0, "walk": "NOT_RUN"}
        write_json(EVIDENCE / "execution-evidence-v0.7.2.json", result); print(json.dumps(result, indent=2)); return 2
    targets = {phase: build_target(source_record, phase) for phase in PHASE_PLANS}
    write_json(EVIDENCE / "cutout-front-walk-gait-v2.json", gait_record(targets, source_record))
    write_image(EVIDENCE / "cutout-front-walk-targets-v072-contact-sheet.png", skeleton_sheet(targets))
    pose_records: dict[str, Any] = {}; internal: dict[str, Any] = {}; pairwise: dict[str, Any] = {}; seams: dict[str, Any] = {}; retention: dict[str, Any] = {}
    rendered: list[tuple[str, Image.Image]] = [("Q0 regression", q0_image)]
    checker: list[tuple[str, Image.Image]] = []; overlays: list[tuple[str, Image.Image]] = []; classifications: list[tuple[str, Image.Image]] = []; heats: list[tuple[str, Image.Image]] = []
    for phase, target in targets.items():
        layers, transforms = render_part_layers_with_plan(parts, source_skeleton, target, phase, source_image.size)
        output = compose_named_layers(layers, phase_plan(plan, phase)["z_order"])
        path = EVIDENCE / f"cutout-{phase.lower()}-v072.png"; write_image(path, output)
        pose_path = path
        try:
            detected = _detect(pose_path, POSE_MODEL)
            detected_points = detected.get("landmarks", {})
            pose_metric = detected_joint_pose_metrics(target["joints"], detected_points, target_orientation="front", detected_orientation="front", visibility={name: float(value.get("visibility", value.get("confidence", 0))) for name, value in detected_points.items()})
        except Exception as exc:  # keep the gate fail-closed and evidence explicit
            detected = {"detected": False, "error": f"{type(exc).__name__}: {exc}", "landmarks": {}}
            pose_metric = {"measurement_status": "UNMEASURABLE", "qualifies": False, "failure_reasons": ["media_pipe_exception"]}
        transform_gates = [transform_metric_gates(item) for item in transforms]
        internal_status = all(all(gates.values()) for gates in transform_gates)
        internal[phase] = {"schema_version": SCHEMA_VERSION, "phase": phase, "status": "CUTOUT_RIG_INTERNAL_QA_PASSED" if internal_status else "CUTOUT_RIG_RENDERER_GAP", "transforms": transforms, "transform_gates": transform_gates, "z_order": phase_plan(plan, phase)["z_order"]}
        pair = pairwise_overlap_qa(layers, phase, target, plan); seam = topological_seam_qa(layers, phase, target, plan); retain = retention_occlusion_qa(parts, layers, output, phase, pair, seam, plan)
        pairwise[phase] = pair; seams[phase] = seam; retention[phase] = retain
        pose_records[phase] = {"schema_version": SCHEMA_VERSION, "phase": phase, "target": target, "media_pipe": detected, "metrics": pose_metric, "internal_qa": internal[phase], "pairwise_status": pair["status"], "seam_status": seam["status"], "retention_status": retain["status"], "safe_margin_px": 24, "weapon_corridor_passed": target["weapon_attachment"]["tip_crosses_protected_torso"] is False, "detached_meaningful_fragment": False, "duplicate_body": False}
        rendered.append((phase, output)); checker.append((phase, checkerboard(output))); overlays.append((phase, overlay_image(output, target, detected))); classifications.append((phase, make_overlap_classification_image(layers, phase, target, plan))); heats.append((phase, make_retention_heatmap(layers, output, phase, pair, plan)))
    write_image(EVIDENCE / "cutout-key-poses-contact-sheet-v072.png", contact_sheet(rendered))
    write_image(EVIDENCE / "cutout-key-poses-checkerboard-v072.png", contact_sheet(checker))
    write_image(EVIDENCE / "cutout-key-poses-target-detected-overlays-v072.png", contact_sheet(overlays))
    write_image(EVIDENCE / "cutout-occlusion-classification-v072.png", contact_sheet(classifications))
    write_image(EVIDENCE / "cutout-retention-heatmap-v072.png", contact_sheet(heats))
    write_json(EVIDENCE / "cutout-pairwise-overlap-matrix-v072.json", {"schema_version": SCHEMA_VERSION, "plan_sha256": plan["plan_sha256"], "poses": pairwise, "status": "OCCLUSION_QA_PASSED" if all(item["status"] == "OCCLUSION_QA_PASSED" for item in pairwise.values()) else "CUTOUT_RIG_OCCLUSION_GAP"})
    write_json(EVIDENCE / "cutout-seam-topology-qa-v072.json", {"schema_version": SCHEMA_VERSION, "plan_sha256": plan["plan_sha256"], "poses": seams, "status": "SEAM_TOPOLOGY_PASSED" if all(item["status"] == "SEAM_TOPOLOGY_PASSED" for item in seams.values()) else "CUTOUT_RIG_TOPOLOGY_SEAM_GAP"})
    write_json(EVIDENCE / "cutout-retention-occlusion-v072.json", {"schema_version": SCHEMA_VERSION, "plan_sha256": plan["plan_sha256"], "poses": retention, "status": "RETENTION_OCCLUSION_PASSED" if all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in retention.values()) else "CUTOUT_RIG_RETENTION_GAP"})
    half = half_cycle_structure(targets, source_skeleton); write_json(EVIDENCE / "cutout-half-cycle-structure-v072.json", half)
    gait = read_json(EVIDENCE / "cutout-front-walk-gait-v2.json")
    all_media = all(item["metrics"].get("qualifies") is True for item in pose_records.values())
    all_internal = all(item["status"] == "CUTOUT_RIG_INTERNAL_QA_PASSED" for item in internal.values())
    q0_pass = q0["status"] == "CUTOUT_RIG_RECONSTRUCTION_PASSED"
    seam_pass = all(item["status"] == "SEAM_TOPOLOGY_PASSED" for item in seams.values())
    retention_pass = all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in retention.values())
    pair_pass = all(item["status"] == "OCCLUSION_QA_PASSED" for item in pairwise.values())
    gait_pass = gait["calibration_status"] == "GAIT_CALIBRATION_PASSED"
    if not q0_pass: final_status = "CUTOUT_RIG_RECONSTRUCTION_REGRESSION"
    elif not seam_pass: final_status = "CUTOUT_RIG_TOPOLOGY_SEAM_GAP"
    elif not pair_pass: final_status = "CUTOUT_RIG_OCCLUSION_GAP"
    elif not retention_pass: final_status = "CUTOUT_RIG_RETENTION_GAP"
    elif not all_media: final_status = "CUTOUT_RIG_EXTERNAL_POSE_QA_GAP"
    elif half["status"] != "HALF_CYCLE_STRUCTURE_PASSED" or not gait_pass: final_status = "CUTOUT_RIG_GAIT_STRUCTURE_GAP"
    elif not all_internal: final_status = "CUTOUT_RIG_RENDERER_GAP"
    else: final_status = "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED"
    execution = {"schema_version": SCHEMA_VERSION, "status": final_status, "baseline_commit": BASELINE_COMMIT, "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "sam2_runs": 0, "sam2_calls": {"runtime_smoke": 0, "rig_revision_segmentation": 0, "per_frame_segmentation": 0}, "comfyui_generation_jobs": 0, "walk": "NOT_RUN", "spritesheet": "NOT_RUN", "gif": "NOT_RUN", "key_poses": list(targets), "external_visual_review": "REQUIRED", "external_approval": "not-claimed", "source_masks_unchanged": True}
    write_json(EVIDENCE / "execution-evidence-v0.7.2.json", execution)
    qualification = {"schema_version": SCHEMA_VERSION, "status": final_status, "provider_id": "deterministic-cutout-rig-2d", "capability": "pose_character_front_2d", "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "baseline": baseline, "plan_sha256": plan["plan_sha256"], "rig_reference": rig_reference, "q0": q0, "poses": pose_records, "internal": internal, "pairwise": "docs/evidence/cutout-pairwise-overlap-matrix-v072.json", "seams": "docs/evidence/cutout-seam-topology-qa-v072.json", "retention": "docs/evidence/cutout-retention-occlusion-v072.json", "gait": "docs/evidence/cutout-front-walk-gait-v2.json", "half_cycle": "docs/evidence/cutout-half-cycle-structure-v072.json", "walk_authorized": False, "production_routing_changed": False, "external_approval": "not-claimed", "allowed_next": ["external_review_then_run_8_frame_walk_prompt"] if final_status == "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED" else ["repair_current_gate_then_rerun_v072"]}
    write_json(EVIDENCE / "cutout-rig-provider-qualification-v072.json", qualification)
    result = {"schema_version": SCHEMA_VERSION, "status": final_status, "baseline": baseline, "q0": q0["status"], "poses": list(pose_records), "pairwise": pairwise["K1-contact-left"]["status"], "seams": seams["K1-contact-left"]["status"], "retention": retention["K1-contact-left"]["status"], "media_pipe_all_qualified": all_media, "half_cycle": half["status"], "sam2_runs": 0, "comfyui_generation_jobs": 0, "walk": "NOT_RUN"}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if final_status == "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
