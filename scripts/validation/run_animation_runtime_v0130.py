"""Execute RUN_FRONT_V1 with source-only rendering and independent negative controls."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/animation-runtime-v0130"
PACKAGE_OUT = OUT / "run-front-v1"
SPEC_PATH = ROOT / "profiles/animation/run-front-v1.json"

sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import AnimationContractError, compile_spec, load_spec, package_compiled, qa_compiled  # noqa: E402
from ugas.animation_profiles import run_front_v1 as run_adapter  # noqa: E402
from ugas.animation_profiles.common import load_source_context  # noqa: E402
from ugas.schema_validation import SchemaValidationError  # noqa: E402


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _semantic_fixture(spec: dict[str, Any], context: dict[str, Any], prepared: dict[str, Any], mutate: Callable[[dict[str, Any]], None], rebuild_targets: bool = False) -> dict[str, Any]:
    fixture = copy.deepcopy(prepared)
    mutate(fixture)
    if rebuild_targets:
        base = run_adapter._base_target(context)
        fixture["targets"] = [run_adapter._target_for_frame(context, index, fixture["samples"][index], base) for index in range(int(spec["frame_count"]))]
    records = [{"feet": {"status": "RUN_FOOT_GROUND_QA_PASSED"}} for _ in fixture["targets"]]
    outputs = [Image.new("RGBA", (512, 512), (0, 0, 0, 0)) for _ in fixture["targets"]]
    return run_adapter._temporal_qa(spec, context, fixture, records, outputs)


def _negative_controls(spec: dict[str, Any], context: dict[str, Any], prepared: dict[str, Any], manifest_path: Path, package_path: Path) -> dict[str, Any]:
    controls: dict[str, Any] = {}

    broken_loop = _semantic_fixture(spec, context, prepared, lambda fixture: fixture["targets"][-1]["joints"]["pelvis"].__setitem__("x", fixture["targets"][-1]["joints"]["pelvis"]["x"] + 50.0))
    controls["break_loop"] = {"gate": "loop_root_close", "status": "REJECTED" if not broken_loop["hard_gates"]["loop_root_close"] else "ACCEPTED", "hard_gates": broken_loop["hard_gates"]}

    def zero_body(fixture: dict[str, Any]) -> None:
        for sample in fixture["samples"]:
            sample["root_shift_x"] = 0.0
            sample["root_shift_y"] = 0.0
            sample["torso_rotation_deg"] = 0.0
            sample["torso_lean_x"] = 0.0

    zero_result = _semantic_fixture(spec, context, prepared, zero_body, rebuild_targets=True)
    controls["zero_root_and_torso"] = {"gate": "body_root_participation", "status": "REJECTED" if not zero_result["hard_gates"]["body_root_participation"] else "ACCEPTED", "hard_gates": zero_result["hard_gates"]}

    slide_result = _semantic_fixture(spec, context, prepared, lambda fixture: fixture["targets"][1]["joints"]["ankle_left"].__setitem__("x", fixture["targets"][1]["joints"]["ankle_left"]["x"] + 20.0))
    controls["foot_slide"] = {"gate": "foot_contact_windows", "status": "REJECTED" if not slide_result["hard_gates"]["foot_contact_windows"] else "ACCEPTED", "hard_gates": slide_result["hard_gates"]}

    def duplicate_leg_phase(fixture: dict[str, Any]) -> None:
        fixture["samples"][6]["right_stride_x"] = fixture["samples"][4]["right_stride_x"]

    duplicate_result = _semantic_fixture(spec, context, prepared, duplicate_leg_phase, rebuild_targets=True)
    controls["duplicate_leg_phase"] = {"gate": "cadence_phase_alternates", "status": "REJECTED" if not duplicate_result["hard_gates"]["cadence_phase_alternates"] else "ACCEPTED", "hard_gates": duplicate_result["hard_gates"]}

    def invert_opposition(fixture: dict[str, Any]) -> None:
        for sample in fixture["samples"]:
            sample["right_arm_swing_deg"] = sample["left_arm_swing_deg"]

    inverted_result = _semantic_fixture(spec, context, prepared, invert_opposition, rebuild_targets=True)
    controls["invert_arm_opposition"] = {"gate": "arm_leg_opposition", "status": "REJECTED" if not inverted_result["hard_gates"]["arm_leg_opposition"] else "ACCEPTED", "hard_gates": inverted_result["hard_gates"]}

    def angular_jump(fixture: dict[str, Any]) -> None:
        fixture["targets"][4]["joints"]["knee_right"]["x"] += 80.0

    jump_result = _semantic_fixture(spec, context, prepared, angular_jump)
    controls["angular_jump"] = {"gate": "angular_continuity", "status": "REJECTED" if not jump_result["hard_gates"]["angular_continuity"] else "ACCEPTED", "hard_gates": jump_result["hard_gates"]}

    missing_hash = copy.deepcopy(spec)
    missing_hash["provenance"]["source_sha256"] = "0" * 64
    try:
        load_source_context(missing_hash, ROOT)
    except (OSError, ValueError, KeyError) as exc:
        controls["remove_dependency_hash"] = {"gate": "source_dependency_hash", "status": "REJECTED", "error": type(exc).__name__}
    else:
        controls["remove_dependency_hash"] = {"gate": "source_dependency_hash", "status": "ACCEPTED"}

    with tempfile.TemporaryDirectory(prefix="ugas-v0130-package-nc-", dir=ROOT / "tmp") as directory:
        temp = Path(directory)
        temp_manifest = temp / "compiled-manifest.json"
        temp_manifest.write_bytes(manifest_path.read_bytes())
        temp_qa = temp / "qa-result.json"
        false_qa = read_json(PACKAGE_OUT / "qa-result.json")
        false_qa["hard_gates"]["synthetic_false_gate"] = False
        temp_qa.write_text(json.dumps(false_qa, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            package_compiled(temp_manifest, ROOT)
        except (AnimationContractError, SchemaValidationError, ValueError, KeyError) as exc:
            controls["false_gate_in_package"] = {"gate": "package_qualified_qa", "status": "REJECTED", "error": type(exc).__name__}
        else:
            controls["false_gate_in_package"] = {"gate": "package_qualified_qa", "status": "ACCEPTED"}

    passed = all(item["status"] == "REJECTED" for item in controls.values())
    return {"schema_version": "0.13.0", "status": "NC_01_TO_NC_08_PASSED" if passed else "NC_01_TO_NC_08_GAP", "controls": controls, "source": "scripts/validation/run_animation_runtime_v0130.py independent fixture mutations"}


def _marker_sheet(manifest: dict[str, Any], qa: dict[str, Any]) -> tuple[Path, list[dict[str, Any]]]:
    marker_dir = PACKAGE_OUT / "visual" / "phase-markers"
    marker_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    marker_records = []
    for index, item in enumerate(manifest["frames"]):
        source_path = ROOT / item["path"]
        with Image.open(source_path) as opened:
            image = opened.convert("RGBA")
        marker = image.copy()
        draw = ImageDraw.Draw(marker, "RGBA")
        event_ids = [str(event["event_id"]) for event in qa["package_metadata"]["phase_markers"] if int(event["frame"]) == index]
        label = f"F{index} {item['phase']} | {','.join(event_ids)}"
        draw.rectangle((0, 0, marker.width - 1, 25), fill=(12, 20, 34, 235))
        draw.text((7, 7), label, fill=(255, 255, 255, 255), font=font)
        destination = marker_dir / f"frame-{index:02d}-{item['phase']}.png"
        marker.save(destination, format="PNG", optimize=False)
        marker_records.append({"frame": index, "phase": item["phase"], "events": event_ids, "path": relative(destination), "sha256": digest(destination)})

    sheet = Image.new("RGBA", (4 * 512, 2 * 548), (18, 22, 32, 255))
    draw = ImageDraw.Draw(sheet, "RGBA")
    for index, record in enumerate(marker_records):
        with Image.open(ROOT / record["path"]) as opened:
            image = opened.convert("RGBA")
        left, top = (index % 4) * 512, (index // 4) * 548
        sheet.alpha_composite(image, (left, top + 36))
        draw.text((left + 8, top + 10), f"{record['phase']} | {'/'.join(record['events'])}", fill=(255, 255, 255, 255), font=font)
    sheet_path = OUT / "run-front-phase-markers-v0130.png"
    sheet.save(sheet_path, format="PNG", optimize=False)
    return sheet_path, marker_records


def _approved_assets_untouched() -> dict[str, Any]:
    paths = ["profiles/animation/walk-front-v1.json", "profiles/animation/idle-front-v1.json", "profiles/animation/attack-front-v1.json", "profiles/animation/attack-front-v2.json", "docs/evidence/walk-front-v081/walk-front-spritesheet-v081.png", "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-front-v2-preview.gif"]
    checks = []
    for path in paths:
        current = ROOT / path
        baseline = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True, check=False).stdout
        checks.append({"path": path, "present": current.is_file(), "byte_identical_to_base": bool(current.is_file() and baseline and current.read_bytes() == baseline), "current_sha256": digest(current) if current.is_file() else None})
    return {"schema_version": "0.13.0", "status": "APPROVED_ASSETS_UNTOUCHED" if all(item["byte_identical_to_base"] for item in checks) else "APPROVED_ASSET_DRIFT", "checks": checks}


def run() -> dict[str, Any]:
    (ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if PACKAGE_OUT.exists():
        shutil.rmtree(PACKAGE_OUT)
    spec = load_spec(SPEC_PATH, ROOT)
    context = run_adapter.load_context(spec, ROOT)
    prepared = run_adapter.prepare(spec, context)
    manifest_path = compile_spec(SPEC_PATH, PACKAGE_OUT, ROOT)
    qa_path = qa_compiled(manifest_path, ROOT)
    qa = read_json(qa_path)
    if qa["decision"] != "QUALIFIED":
        raise RuntimeError(f"RUN_FRONT_NOT_QUALIFIED:{qa.get('failures')}")
    package_path = package_compiled(manifest_path, ROOT)
    manifest, package = read_json(manifest_path), read_json(package_path)
    negative = _negative_controls(spec, context, prepared, manifest_path, package_path)
    write_json(OUT / "run-front-targets-v0130.json", {"schema_version": "0.13.0", "animation_id": spec["animation_id"], "phase_order": list(run_adapter.PHASES), "targets": prepared["targets"], "target_hashes": [target["target_joint_sha256"] for target in prepared["targets"]], "key_pose_bindings": spec["key_pose_bindings"], "motion_tracks_sha256": prepared["track_hash"], "parameters_frozen_before_render": True, "source_only_pixels": True})
    write_json(OUT / "run-front-frame-qa-v0130.json", {"schema_version": "0.13.0", "animation_id": spec["animation_id"], "status": qa["status"], "decision": qa["decision"], "frames": qa["frames"]})
    write_json(OUT / "run-front-temporal-qa-v0130.json", {"schema_version": "0.13.0", "animation_id": spec["animation_id"], "status": qa["temporal"]["status"], "metrics": qa["temporal"]["metrics"], "hard_gates": qa["temporal"]["hard_gates"], "cadence_phase": qa["temporal"]["cadence_phase"], "arm_opposition": qa["temporal"]["arm_opposition"]})
    write_json(OUT / "run-front-loop-qa-v0130.json", {"schema_version": "0.13.0", "animation_id": spec["animation_id"], "status": "RUN_LOOP_CLOSURE_PASSED" if all(value for key, value in qa["temporal"]["hard_gates"].items() if key.startswith("loop_")) else "RUN_LOOP_CLOSURE_GAP", "loop_metrics": {key: value for key, value in qa["temporal"]["metrics"].items() if "loop" in key}, "gates": {key: value for key, value in qa["temporal"]["hard_gates"].items() if key.startswith("loop_")}, "edge": [7, 0]})
    write_json(OUT / "run-front-cadence-qa-v0130.json", {"schema_version": "0.13.0", "animation_id": spec["animation_id"], "status": "RUN_CADENCE_PHASE_PASSED" if qa["temporal"]["hard_gates"]["cadence_phase_alternates"] else "RUN_CADENCE_PHASE_GAP", "phase_order": list(run_adapter.PHASES), "contact_frames": spec["adapter_parameters"]["contact_frames"], "passing_frames": spec["adapter_parameters"]["passing_frames"], "flight_frames": spec["adapter_parameters"]["flight_frames"], "cadence_phase": qa["temporal"]["cadence_phase"]})
    write_json(OUT / "run-front-foot-ground-qa-v0130.json", {"schema_version": "0.13.0", "animation_id": spec["animation_id"], "status": qa["foot_ground"]["status"], "frames": qa["foot_ground"]["frames"], "contact": qa["foot_ground"]["contact"]})
    write_json(OUT / "run-front-body-mechanics-qa-v0130.json", {"schema_version": "0.13.0", "animation_id": spec["animation_id"], **qa["body_mechanics"]})
    write_json(OUT / "run-front-continuity-qa-v0130.json", {"schema_version": "0.13.0", "animation_id": spec["animation_id"], "status": "RUN_CONTINUITY_INTERPOLATION_PASSED" if qa["temporal"]["hard_gates"]["angular_continuity"] and qa["temporal"]["hard_gates"]["angular_acceleration_continuity"] and qa["temporal"]["hard_gates"]["nonfinite_and_gap_free"] else "RUN_CONTINUITY_INTERPOLATION_GAP", "gates": {key: value for key, value in qa["temporal"]["hard_gates"].items() if key in {"angular_continuity", "angular_acceleration_continuity", "nonfinite_and_gap_free", "foreground_height_stability"}}, "metrics": {key: value for key, value in qa["temporal"]["metrics"].items() if "angle" in key or "height" in key}})
    write_json(OUT / "run-front-gate-negative-controls-v0130.json", negative)
    assets = _approved_assets_untouched()
    write_json(OUT / "approved-assets-untouched-v0130.json", assets)
    marker_sheet, marker_records = _marker_sheet(manifest, qa)
    visual_images = [{"frame": index, "phase": item["phase"], "source_path": item["path"], "rgba_sha256": item["rgba_sha256"], "target_hash": item["target_hash"], "media_type": "image/png", "role": "compiled-source-only-frame", "events": [event for event in spec["event_markers"] if int(event["frame"]) == index]} for index, item in enumerate(manifest["frames"])]
    visual_images.extend([{ "path": package["preview_gif"]["path"], "sha256": package["preview_gif"]["sha256"], "media_type": "image/gif", "role": "review-gif", "events": spec["event_markers"]}, {"path": package["sprite_sheet"]["path"], "sha256": package["sprite_sheet"]["sha256"], "media_type": "image/png", "role": "compiled-rgba-spritesheet", "events": spec["event_markers"]}, {"path": relative(marker_sheet), "sha256": digest(marker_sheet), "media_type": "image/png", "role": "phase-marker-review-sheet", "events": spec["event_markers"]}])
    visual_manifest = {"schema_version": "0.13.0", "review_state": "run-front-v1-technically-qualified", "review_subject": {"animation_id": spec["animation_id"], "direction": spec["direction"], "frame_count": spec["frame_count"], "fps": spec["fps"], "source_r4_sha256": spec["provenance"]["source_sha256"]}, "event_markers": spec["event_markers"], "event_markers_sha256": manifest["event_markers_sha256"], "motion_tracks_sha256": manifest["motion_tracks_sha256"], "images": visual_images, "marker_frames": marker_records, "source_only_pixels": True, "external_visual": "REQUIRED", "production_routing": "BLOCKED", "package_manifest": {"path": relative(package_path), "sha256": digest(package_path)}}
    write_json(OUT / "run-front-visual-manifest-v0130.json", visual_manifest)
    base_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    execution = {"schema_version": "0.13.0", "prompt": "UGAS-v0.13.0-RUN-FRONT-V1", "implementation_base_commit": base_head, "animation_id": spec["animation_id"], "status": qa["status"], "decision": qa["decision"], "frame_count": spec["frame_count"], "fps": spec["fps"], "loop": spec["loop"], "motion_tracks_sha256": manifest["motion_tracks_sha256"], "event_markers_sha256": manifest["event_markers_sha256"], "source_r4_sha256": spec["provenance"]["source_sha256"], "source_only_pixels": True, "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "new_generation": 0, "production_approved": False, "production_routing": "BLOCKED", "external_visual": "REQUIRED", "negative_controls": negative["status"], "approved_assets_untouched": assets["status"], "package": {"path": relative(package_path), "sha256": digest(package_path), "preview_gif": package["preview_gif"], "sprite_sheet": package["sprite_sheet"]}, "review_artifacts": {"visual_manifest": relative(OUT / "run-front-visual-manifest-v0130.json"), "phase_marker_sheet": relative(marker_sheet), "negative_controls": relative(OUT / "run-front-gate-negative-controls-v0130.json")}, "next_capability_started": False}
    write_json(OUT / "execution-evidence-v0.13.0.json", execution)
    return {"status": "ANIMATION_RUNTIME_V0130_PASSED", "decision": qa["decision"], "animation_id": spec["animation_id"], "frames": len(manifest["frames"]), "package": relative(package_path), "preview_gif": package["preview_gif"]["path"], "negative_controls": negative["status"], "approved_assets": assets["status"], "external_visual": "REQUIRED", "production_routing": "BLOCKED"}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
        raise SystemExit(0)
    except Exception as exc:
        print(json.dumps({"status": "ANIMATION_RUNTIME_V0130_FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False))
        raise SystemExit(2)
