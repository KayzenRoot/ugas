"""Run the UGAS v0.7.3 structural coverage correction qualifier.

The qualifier reuses the immutable v0.7.1 R4 rig/masks and the exact v0.7.2
K1-K4 target joints.  It writes only v0.7.3 evidence and never invokes SAM2,
ComfyUI, a diffusion provider, or the eight-frame walk.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import subprocess
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

import run_cutout_rig_v072 as v072  # noqa: E402
from ugas.cutout_occlusion import (  # noqa: E402
    PHASE_PLANS,
    build_occlusion_plan,
    compose_named_layers,
    phase_plan,
    render_part_layers_with_plan,
    topological_seam_qa,
)
from ugas.cutout_rig import (  # noqa: E402
    PART_NAMES,
    PART_SPECS,
    canonical_json,
    render_part,
    render_part_layers,
    skeleton_point,
    transform_parameters,
)
from ugas.cutout_structural import (  # noqa: E402
    SCHEMA_VERSION,
    _binary,
    _count,
    _digest_image,
    _forward_point,
    _intersection,
    build_authorized_occlusion_regions,
    build_structural_core,
    calibrate_layer_integrity_fixtures,
    compose_with_structural_core,
    exclude_protected_regions,
    layer_integrity_qa,
    pairwise_overlap_v073,
    retention_occlusion_v073,
    source_core_rgba,
    structural_core_q0_gate,
    structural_coverage_qa,
    structural_hole_overlay,
    transform_mask,
)
from ugas.identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256  # noqa: E402
from ugas.pose_metric_calibration import CORE_JOINTS, detected_joint_pose_metrics  # noqa: E402
from ugas.pose_qa_estimator import _detect  # noqa: E402


BASELINE_COMMIT = "4fd860319d01d04c7da2562431c1d522c1fd2890"
SOURCE_PATH = ROOT / "docs" / "evidence" / "reference-edit-selected-transparent.png"
SKELETON_PATH = ROOT / "docs" / "evidence" / "r4-source-skeleton-v071.json"
RIG_PATH = ROOT / "docs" / "evidence" / "r4-cutout-rig-v071.json"
RAW_PATH = ROOT / "docs" / "evidence" / "r4-cutout-raw-masks-v071-manifest.json"
REFINED_PATH = ROOT / "docs" / "evidence" / "r4-cutout-refined-masks-v071-manifest.json"
PART_DIR = ROOT / "docs" / "evidence" / "r4-cutout-parts-v071"
MASK_DIR = ROOT / "docs" / "evidence" / "r4-cutout-refined-masks-v071"
EVIDENCE = ROOT / "docs" / "evidence"
POSE_MODEL = v072.POSE_MODEL
V072_QUALIFICATION_PATH = EVIDENCE / "cutout-rig-provider-qualification-v072.json"
V072_PLAN_PATH = EVIDENCE / "cutout-occlusion-plan-v072.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_image(path: Path, image: Image.Image) -> None:
    image.convert("RGBA").save(path)


def target_digest(target: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(target.get("joints", {})).encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Image.Image):
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def contact_sheet(images: list[tuple[str, Image.Image]], cell: tuple[int, int] = (512, 560)) -> Image.Image:
    cols = 2
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell[0], rows * cell[1]), (18, 22, 32, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(images):
        left, top = (index % cols) * cell[0], (index // cols) * cell[1]
        thumb = image.convert("RGBA")
        thumb.thumbnail((cell[0] - 12, cell[1] - 42), Image.Resampling.LANCZOS)
        sheet.alpha_composite(thumb, (left + (cell[0] - thumb.width) // 2, top + 26))
        draw.text((left + 10, top + 7), label, fill=(255, 255, 255, 255))
    return sheet


def checkerboard(image: Image.Image) -> Image.Image:
    base = Image.new("RGBA", image.size, (235, 235, 235, 255))
    draw = ImageDraw.Draw(base)
    step = 16
    for y in range(0, image.height, step):
        for x in range(0, image.width, step):
            if (x // step + y // step) % 2:
                draw.rectangle((x, y, x + step - 1, y + step - 1), fill=(185, 185, 185, 255))
    base.alpha_composite(image.convert("RGBA"))
    return base


def overlay_image(output: Image.Image, target: Mapping[str, Any], detected: Mapping[str, Any]) -> Image.Image:
    image = output.copy().convert("RGBA")
    draw = ImageDraw.Draw(image)
    for name, color in (("target", (30, 230, 255, 255)), ("detected", (255, 220, 40, 255))):
        points = target.get("joints", {}) if name == "target" else detected.get("landmarks", {})
        for joint in CORE_JOINTS + ("nose",):
            if joint not in points:
                continue
            point = points[joint]
            x, y = (float(point["x"]), float(point["y"])) if isinstance(point, Mapping) else (float(point[0]), float(point[1]))
            radius = 3 if name == "target" else 2
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=2)
    return image


def waist_zoom(image: Image.Image) -> Image.Image:
    crop = image.convert("RGBA").crop((185, 185, 345, 315))
    return crop.resize((480, 390), Image.Resampling.NEAREST)


def baseline_check() -> dict[str, Any]:
    baseline = v072.baseline_check()
    failures = list(baseline.get("failures", []))
    if not V072_QUALIFICATION_PATH.is_file():
        failures.append("missing:v0.7.2 qualification")
    if not V072_PLAN_PATH.is_file():
        failures.append("missing:v0.7.2 occlusion plan")
    commit_check = subprocess.run(["git", "cat-file", "-e", f"{BASELINE_COMMIT}^{{commit}}"], cwd=ROOT, capture_output=True, check=False)
    if commit_check.returncode != 0:
        failures.append("v072-baseline-commit-not-present")
    if not (ROOT / "REVIEW-v0.7.2.md").is_file():
        failures.append("missing:REVIEW-v0.7.2.md")
    if baseline.get("source_sha256") != ANCHOR_SHA256:
        failures.append("canonical-source-hash-mismatch")
    return {
        "status": "BASELINE_V072_INTEGRITY_PASSED" if not failures else "CUTOUT_RIG_BASELINE_INTEGRITY_GAP",
        "baseline_commit": BASELINE_COMMIT,
        "v072_baseline_commit_present": commit_check.returncode == 0,
        "v071_input_status": baseline.get("status"),
        "source_sha256": baseline.get("source_sha256"),
        "revision_id": baseline.get("revision_id"),
        "v072_evidence_preserved": not failures,
        "sam2_runs": 0,
        "failures": failures,
    }


def load_inputs() -> tuple[Image.Image, dict[str, Image.Image], dict[str, Image.Image], dict[str, Any]]:
    source = Image.open(SOURCE_PATH).convert("RGBA")
    parts = {name: Image.open(PART_DIR / f"{name}.png").convert("RGBA") for name in PART_NAMES}
    masks = {name: Image.open(MASK_DIR / f"{name}.png").convert("L") for name in PART_NAMES}
    skeleton = copy.deepcopy(read_json(SKELETON_PATH)["skeleton"])
    skeleton["weapon_tip"] = v072.pvalue(v072.infer_weapon_tip(parts["sword"], skeleton_point(skeleton, "wrist_right")))
    return source, parts, masks, skeleton


def q0_record(
    source: Image.Image, parts: Mapping[str, Image.Image], skeleton: Mapping[str, Any], core: Mapping[str, Any],
) -> tuple[dict[str, Any], Image.Image, Image.Image]:
    layer_list, transforms = render_part_layers(parts, skeleton, skeleton, source.size)
    layers = {item["part"]: layer for item, layer in zip(transforms, layer_list)}
    z_order = [name for name, _ in sorted(PART_SPECS.items(), key=lambda item: (item[1]["z_group"], item[0]))]
    torso_transform = next(item for item in transforms if item["part"] == "torso_pelvis")
    core_layer = render_part(
        source_core_rgba(source, core["core_mask"]),
        tuple(torso_transform["source_pivot"]), tuple(torso_transform["target_pivot"]),
        tuple(torso_transform["source_end"]), tuple(torso_transform["target_end"]), source.size,
    )
    core_layer = exclude_protected_regions(core_layer, layers)
    output = compose_with_structural_core(layers, z_order, core_layer)
    record = structural_core_q0_gate(source, output, core_layer, core)
    record["transforms"] = transforms
    record["core_layer_sha256"] = _digest_image(core_layer.getchannel("A"))
    record["core_layer_visible_pixels"] = _count(_binary(core_layer.getchannel("A"), 0))
    return record, output, core_layer


def source_owner_at(point: tuple[int, int], masks: Mapping[str, Image.Image]) -> list[str]:
    x, y = point
    return [name for name in PART_NAMES if 0 <= x < masks[name].width and 0 <= y < masks[name].height and masks[name].getpixel((x, y)) > 127]


def inverse_point(matrix: list[list[float]], point: tuple[float, float]) -> tuple[float, float]:
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    determinant = a * e - b * d
    if abs(determinant) < 1e-9:
        raise ValueError("non-invertible affine transform")
    x, y = point[0] - c, point[1] - f
    return ((e * x - b * y) / determinant, (-d * x + a * y) / determinant)


def structural_hole_owner_diagnostics(
    coverage: Mapping[str, Any], core: Mapping[str, Any], masks: Mapping[str, Image.Image],
    target: Mapping[str, Any], transforms: list[Mapping[str, Any]], phase: str,
) -> dict[str, Any]:
    holes = coverage.get("hole_mask")
    if not isinstance(holes, Image.Image):
        return {"schema_version": SCHEMA_VERSION, "phase": phase, "holes": [], "status": "STRUCTURAL_HOLE_OWNER_DIAGNOSTICS_PASSED"}
    torso_transform = core["torso_transform"]
    transform_by_part = {str(item["part"]): item for item in transforms}
    records: list[dict[str, Any]] = []
    for y in range(holes.height):
        for x in range(holes.width):
            if holes.getpixel((x, y)) == 0:
                continue
            source = inverse_point(torso_transform["forward_affine_matrix"], (float(x), float(y)))
            source_point = (int(round(source[0])), int(round(source[1])))
            owners = source_owner_at(source_point, masks)
            destinations = {}
            for owner in owners:
                owner_transform = transform_by_part.get(owner)
                if owner_transform:
                    destinations[owner] = [round(value, 4) for value in _forward_point(owner_transform["forward_affine_matrix"], source)]
            records.append({
                "target_coordinate": [x, y],
                "source_coordinate": [source_point[0], source_point[1]],
                "owner_at_source": owners,
                "owner_target_destinations": destinations,
                "core_duplicated_source_pixel": bool(core["core_mask"].getpixel(source_point) > 0) if 0 <= source_point[0] < core["core_mask"].width and 0 <= source_point[1] < core["core_mask"].height else False,
                "reason_hole_remained_uncovered": "source_owner_moved_without_core_duplicate" if owners else "no_source_owner_at_inverse_coordinate",
            })
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": phase,
        "holes": records,
        "hole_count": len(records),
        "status": "STRUCTURAL_HOLE_OWNER_DIAGNOSTICS_PASSED" if not records else "CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualify UGAS v0.7.3 structural core, layer integrity and key poses")
    parser.add_argument("--json", action="store_true", help="emit machine-readable evidence summary")
    args = parser.parse_args(argv)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    baseline = baseline_check()
    if baseline["status"] != "BASELINE_V072_INTEGRITY_PASSED":
        execution = {"schema_version": SCHEMA_VERSION, "status": "CUTOUT_RIG_BASELINE_INTEGRITY_GAP", "baseline": baseline, "sam2_runs": 0, "comfyui_generation_jobs": 0, "walk": "NOT_RUN", "spritesheet": "NOT_RUN", "gif": "NOT_RUN"}
        write_json(EVIDENCE / "execution-evidence-v0.7.3.json", execution)
        print(json.dumps(execution, indent=2, ensure_ascii=False))
        return 2

    source, parts, masks, skeleton = load_inputs()
    source_alpha = source.getchannel("A")
    core = build_structural_core(source, source_alpha, masks["torso_pelvis"], masks, skeleton)
    core_record = _json_safe({key: value for key, value in core.items() if not isinstance(value, Image.Image)})
    core_record["canonical_source_sha256"] = v072.sha256_file(SOURCE_PATH)
    core_record["source_part_paths"] = {name: f"docs/evidence/r4-cutout-parts-v071/{name}.png" for name in PART_NAMES}
    core_record["source_mask_paths"] = {name: f"docs/evidence/r4-cutout-refined-masks-v071/{name}.png" for name in PART_NAMES}
    write_json(EVIDENCE / "cutout-structural-core-v073.json", core_record)
    write_image(EVIDENCE / "cutout-structural-core-mask-v073.png", core["core_mask"])

    calibration = calibrate_layer_integrity_fixtures()
    write_json(EVIDENCE / "cutout-layer-integrity-calibration-v073.json", calibration)
    if calibration["status"] != "LAYER_INTEGRITY_CALIBRATION_PASSED":
        execution = {"schema_version": SCHEMA_VERSION, "status": "CUTOUT_RIG_LAYER_INTEGRITY_GAP", "baseline": baseline, "calibration": calibration, "sam2_runs": 0, "comfyui_generation_jobs": 0, "walk": "NOT_RUN"}
        write_json(EVIDENCE / "execution-evidence-v0.7.3.json", execution)
        print(json.dumps(execution, indent=2, ensure_ascii=False))
        return 2

    v072_qualification = read_json(V072_QUALIFICATION_PATH)
    v072_targets = {phase: v072_qualification["poses"][phase]["target"] for phase in PHASE_PLANS}
    target_hashes = {phase: target_digest(target) for phase, target in v072_targets.items()}
    plan = build_occlusion_plan(ANCHOR_SHA256, "docs/evidence/r4-cutout-rig-v071.json")
    pose_records: dict[str, Any] = {}
    layer_records: dict[str, Any] = {}
    pair_records: dict[str, Any] = {}
    seam_records: dict[str, Any] = {}
    retention_records: dict[str, Any] = {}
    coverage_records: dict[str, Any] = {}
    owner_records: dict[str, Any] = {}
    rendered: list[tuple[str, Image.Image]] = [("R4 source", source)]
    checker: list[tuple[str, Image.Image]] = [("R4 source", checkerboard(source))]
    overlays: list[tuple[str, Image.Image]] = []
    hole_overlays: list[tuple[str, Image.Image]] = []
    waist: list[tuple[str, Image.Image]] = []
    media_pipe_all = True
    q0, q0_output, q0_core_layer = q0_record(source, parts, skeleton, core)
    write_image(EVIDENCE / "cutout-q0-regression-v073.png", q0_output)
    write_json(EVIDENCE / "cutout-q0-regression-v073-qa.json", q0)
    if q0["status"] != "CUTOUT_RIG_RECONSTRUCTION_PASSED":
        execution = {"schema_version": SCHEMA_VERSION, "status": "STOP_CUTOUT_RIG_CORE_RECONSTRUCTION_GAP", "baseline": baseline, "q0": q0, "sam2_runs": 0, "comfyui_generation_jobs": 0, "walk": "NOT_RUN"}
        write_json(EVIDENCE / "execution-evidence-v0.7.3.json", execution)
        print(json.dumps({"schema_version": SCHEMA_VERSION, "status": execution["status"], "q0": q0["status"], "walk": "NOT_RUN"}, indent=2))
        return 2
    rendered.append(("Q0 identity", q0_output))
    checker.append(("Q0 identity", checkerboard(q0_output)))

    for phase, target in v072_targets.items():
        if target_digest(target) != target_hashes[phase]:
            raise RuntimeError(f"target hash changed during qualification: {phase}")
        layers, transforms = render_part_layers_with_plan(parts, skeleton, target, phase, source.size)
        torso_transform = next(item for item in transforms if item["part"] == "torso_pelvis")
        core_for_pose = dict(core)
        core_for_pose["torso_transform"] = torso_transform
        core_layer = render_part(
            source_core_rgba(source, core["core_mask"]),
            tuple(torso_transform["source_pivot"]), tuple(torso_transform["target_pivot"]),
            tuple(torso_transform["source_end"]), tuple(torso_transform["target_end"]), source.size,
        )
        core_layer = exclude_protected_regions(core_layer, layers)
        phase_z_order = phase_plan(plan, phase)["z_order"]
        output = compose_with_structural_core(layers, phase_z_order, core_layer)
        output_path = EVIDENCE / f"cutout-{phase.lower()}-v073.png"
        write_image(output_path, output)
        try:
            detected = _detect(output_path, POSE_MODEL)
            detected_points = detected.get("landmarks", {})
            pose_metric = detected_joint_pose_metrics(
                target["joints"], detected_points, target_orientation="front", detected_orientation="front",
                visibility={name: float(value.get("visibility", value.get("confidence", 0))) for name, value in detected_points.items()},
            )
        except Exception as exc:  # fail closed without fabricating pose evidence
            detected = {"detected": False, "error": f"{type(exc).__name__}: {exc}", "landmarks": {}}
            pose_metric = {"measurement_status": "UNMEASURABLE", "qualifies": False, "failure_reasons": ["media_pipe_exception"]}
        media_pipe_all = media_pipe_all and pose_metric.get("qualifies") is True
        integrity = layer_integrity_qa(parts, layers, transforms, source.size)
        regions = build_authorized_occlusion_regions(target, phase, plan, source.size)
        pair = pairwise_overlap_v073(layers, phase, target, plan, regions)
        legacy_seam = topological_seam_qa(layers, phase, target, plan)
        seam = {"schema_version": SCHEMA_VERSION, "phase": phase, "plan_sha256": plan["plan_sha256"], "pairs": legacy_seam["pairs"], "hard_gates": legacy_seam["hard_gates"], "status": legacy_seam["status"]}
        retention = retention_occlusion_v073(parts, layers, output, phase, pair, seam, integrity, plan)
        coverage = structural_coverage_qa(core_layer, output, target, phase, core_for_pose)
        owner = structural_hole_owner_diagnostics(coverage, core_for_pose, masks, target, transforms, phase)
        for record in (coverage,):
            record.pop("hole_mask", None)
            record.pop("expected_mask", None)
        layer_records[phase] = integrity
        pair_records[phase] = pair
        seam_records[phase] = seam
        retention_records[phase] = retention
        coverage_records[phase] = coverage
        owner_records[phase] = owner
        rendered.append((phase, output))
        checker.append((phase, checkerboard(output)))
        overlays.append((phase, overlay_image(output, target, detected)))
        hole_overlays.append((phase, structural_hole_overlay(checkerboard(output), coverage.get("hole_mask", Image.new("L", output.size, 0)))))
        waist.append((phase, waist_zoom(checkerboard(output))))
        pose_records[phase] = {
            "schema_version": SCHEMA_VERSION,
            "phase": phase,
            "target_joint_sha256": target_hashes[phase],
            "target": target,
            "media_pipe": detected,
            "metrics": pose_metric,
            "layer_integrity_status": integrity["status"],
            "pairwise_status": pair["status"],
            "seam_status": seam["status"],
            "retention_status": retention["status"],
            "structural_coverage_status": coverage["status"],
            "structural_hole_owner_diagnostics_status": owner["status"],
            "core_layer_sha256": _digest_image(core_layer.getchannel("A")),
            "core_protected_head_overlap_pixels": _count(_intersection(_binary(core_layer.getchannel("A"), 0), _binary(layers["head"].getchannel("A"), 0))),
            "core_protected_sword_overlap_pixels": _count(_intersection(_binary(core_layer.getchannel("A"), 0), _binary(layers["sword"].getchannel("A"), 0))),
        }

    write_image(EVIDENCE / "cutout-key-poses-checkerboard-v073.png", contact_sheet(checker))
    write_image(EVIDENCE / "cutout-key-poses-waist-zoom-v073.png", contact_sheet(waist, cell=(480, 420)))
    write_image(EVIDENCE / "cutout-structural-hole-overlay-v073.png", contact_sheet(hole_overlays))
    write_image(EVIDENCE / "cutout-key-poses-target-detected-overlays-v073.png", contact_sheet(overlays))
    write_image(EVIDENCE / "cutout-k1-contact-left-v073.png", rendered[2][1])
    write_image(EVIDENCE / "cutout-k2-passing-left-v073.png", rendered[3][1])
    write_image(EVIDENCE / "cutout-k3-contact-right-v073.png", rendered[4][1])
    write_image(EVIDENCE / "cutout-k4-passing-right-v073.png", rendered[5][1])

    write_json(EVIDENCE / "cutout-authorized-occlusion-regions-v073.json", _json_safe({"schema_version": SCHEMA_VERSION, "plan_sha256": plan["plan_sha256"], "poses": {phase: build_authorized_occlusion_regions(v072_targets[phase], phase, plan, source.size) for phase in PHASE_PLANS}, "status": "AUTHORIZED_OCCLUSION_REGIONS_DERIVED"}))
    write_json(EVIDENCE / "cutout-layer-integrity-v073.json", {"schema_version": SCHEMA_VERSION, "calibration": calibration, "poses": layer_records, "status": "LAYER_INTEGRITY_PASSED" if all(item["status"] == "LAYER_INTEGRITY_PASSED" for item in layer_records.values()) else "CUTOUT_RIG_LAYER_INTEGRITY_GAP"})
    write_json(EVIDENCE / "cutout-structural-coverage-v073.json", {"schema_version": SCHEMA_VERSION, "poses": coverage_records, "status": "STRUCTURAL_COVERAGE_PASSED" if all(item["status"] == "STRUCTURAL_COVERAGE_PASSED" for item in coverage_records.values()) else "CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP"})
    write_json(EVIDENCE / "cutout-structural-hole-owner-diagnostics-v073.json", {"schema_version": SCHEMA_VERSION, "poses": owner_records, "status": "STRUCTURAL_HOLE_OWNER_DIAGNOSTICS_PASSED" if all(item["status"] == "STRUCTURAL_HOLE_OWNER_DIAGNOSTICS_PASSED" for item in owner_records.values()) else "CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP"})
    write_json(EVIDENCE / "cutout-pairwise-overlap-matrix-v073.json", {"schema_version": SCHEMA_VERSION, "plan_sha256": plan["plan_sha256"], "poses": pair_records, "status": "OCCLUSION_QA_PASSED" if all(item["status"] == "OCCLUSION_QA_PASSED" for item in pair_records.values()) else "CUTOUT_RIG_OCCLUSION_REGION_GAP"})
    write_json(EVIDENCE / "cutout-seam-topology-qa-v073.json", {"schema_version": SCHEMA_VERSION, "plan_sha256": plan["plan_sha256"], "poses": seam_records, "status": "SEAM_TOPOLOGY_PASSED" if all(item["status"] == "SEAM_TOPOLOGY_PASSED" for item in seam_records.values()) else "CUTOUT_RIG_TOPOLOGY_SEAM_GAP"})
    write_json(EVIDENCE / "cutout-retention-occlusion-v073.json", {"schema_version": SCHEMA_VERSION, "plan_sha256": plan["plan_sha256"], "poses": retention_records, "status": "RETENTION_OCCLUSION_PASSED" if all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in retention_records.values()) else "CUTOUT_RIG_RETENTION_GAP"})

    statuses = {
        "q0": q0["status"] == "CUTOUT_RIG_RECONSTRUCTION_PASSED",
        "integrity": layer_records and all(item["status"] == "LAYER_INTEGRITY_PASSED" for item in layer_records.values()),
        "coverage": coverage_records and all(item["status"] == "STRUCTURAL_COVERAGE_PASSED" for item in coverage_records.values()),
        "pairwise": pair_records and all(item["status"] == "OCCLUSION_QA_PASSED" for item in pair_records.values()),
        "seam": seam_records and all(item["status"] == "SEAM_TOPOLOGY_PASSED" for item in seam_records.values()),
        "retention": retention_records and all(item["status"] == "RETENTION_OCCLUSION_PASSED" for item in retention_records.values()),
        "media_pipe": media_pipe_all,
        "core_protected": all(item["core_protected_head_overlap_pixels"] == 0 and item["core_protected_sword_overlap_pixels"] == 0 for item in pose_records.values()),
    }
    if not statuses["q0"]:
        final_status = "STOP_CUTOUT_RIG_CORE_RECONSTRUCTION_GAP"
    elif not statuses["integrity"]:
        final_status = "CUTOUT_RIG_LAYER_INTEGRITY_GAP"
    elif not statuses["coverage"]:
        final_status = "CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP"
    elif not statuses["pairwise"]:
        final_status = "CUTOUT_RIG_OCCLUSION_REGION_GAP"
    elif not statuses["seam"]:
        final_status = "CUTOUT_RIG_TOPOLOGY_SEAM_GAP"
    elif not statuses["retention"]:
        final_status = "CUTOUT_RIG_RETENTION_GAP"
    elif not statuses["media_pipe"]:
        final_status = "CUTOUT_RIG_EXTERNAL_POSE_QA_GAP"
    elif not statuses["core_protected"]:
        final_status = "CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP"
    else:
        final_status = "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED"

    write_json(EVIDENCE / "cutout-rig-provider-qualification-v073.json", {
        "schema_version": SCHEMA_VERSION,
        "status": final_status,
        "provider_id": "deterministic-cutout-rig-2d",
        "capability": "pose_character_front_2d",
        "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256},
        "baseline": baseline,
        "historical_v072_target_joint_hashes": target_hashes,
        "v072_target_evidence": "docs/evidence/cutout-rig-provider-qualification-v072.json",
        "core": "docs/evidence/cutout-structural-core-v073.json",
        "layer_integrity": "docs/evidence/cutout-layer-integrity-v073.json",
        "structural_coverage": "docs/evidence/cutout-structural-coverage-v073.json",
        "structural_hole_owner_diagnostics": "docs/evidence/cutout-structural-hole-owner-diagnostics-v073.json",
        "authorized_occlusion_regions": "docs/evidence/cutout-authorized-occlusion-regions-v073.json",
        "pairwise": "docs/evidence/cutout-pairwise-overlap-matrix-v073.json",
        "seams": "docs/evidence/cutout-seam-topology-qa-v073.json",
        "retention": "docs/evidence/cutout-retention-occlusion-v073.json",
        "q0": q0,
        "poses": pose_records,
        "calibration": calibration,
        "walk_authorized": False,
        "generation_provider_change_authorized": False,
        "sam2_runs": 0,
        "comfyui_generation_jobs": 0,
        "walk": "NOT_RUN",
        "spritesheet": "NOT_RUN",
        "gif": "NOT_RUN",
        "external_visual_review": "REQUIRED",
        "external_approval": "not-claimed",
        "allowed_next": ["external_review_then_run_8_frame_walk_prompt"] if final_status == "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED" else ["repair_current_gate_then_rerun_v073"],
    })
    execution = {
        "schema_version": SCHEMA_VERSION,
        "status": final_status,
        "baseline_commit": BASELINE_COMMIT,
        "source": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256},
        "sam2_runs": 0,
        "sam2_calls": {"runtime_smoke": 0, "rig_revision_segmentation": 0, "per_frame_segmentation": 0},
        "comfyui_generation_jobs": 0,
        "walk": "NOT_RUN",
        "spritesheet": "NOT_RUN",
        "gif": "NOT_RUN",
        "key_poses": list(PHASE_PLANS),
        "historical_v072_target_joint_hashes": target_hashes,
        "external_visual_review": "REQUIRED",
        "external_approval": "not-claimed",
        "source_masks_unchanged": True,
    }
    write_json(EVIDENCE / "execution-evidence-v0.7.3.json", execution)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": final_status,
        "baseline": baseline["status"],
        "q0": q0["status"],
        "poses": list(PHASE_PLANS),
        "layer_integrity": "LAYER_INTEGRITY_PASSED" if statuses["integrity"] else "CUTOUT_RIG_LAYER_INTEGRITY_GAP",
        "structural_coverage": "STRUCTURAL_COVERAGE_PASSED" if statuses["coverage"] else "CUTOUT_RIG_STRUCTURAL_COVERAGE_GAP",
        "pairwise": "OCCLUSION_QA_PASSED" if statuses["pairwise"] else "CUTOUT_RIG_OCCLUSION_REGION_GAP",
        "seams": "SEAM_TOPOLOGY_PASSED" if statuses["seam"] else "CUTOUT_RIG_TOPOLOGY_SEAM_GAP",
        "retention": "RETENTION_OCCLUSION_PASSED" if statuses["retention"] else "CUTOUT_RIG_RETENTION_GAP",
        "media_pipe_all_qualified": media_pipe_all,
        "sam2_runs": 0,
        "comfyui_generation_jobs": 0,
        "walk": "NOT_RUN",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if final_status == "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
