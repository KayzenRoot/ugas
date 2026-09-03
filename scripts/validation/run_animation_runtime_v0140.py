"""Execute the v0.14.0 HIT_REACTION_FRONT runtime without rewriting v0.13.x evidence."""

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
OUT = ROOT / "docs/evidence/animation-runtime-v0140"
PACKAGE_OUT = OUT / "hit-front-v1"
SPEC_PATH = ROOT / "profiles/animation/hit-front-v1.json"
IMMUTABLE_BASE = "0beb4c23604f1e45736c3082f99d2e08fa1ac308"
RUN_APPROVED_HEAD = "f3d68faa5524392e66aee2fc2a450b9da8fa734b"
PROTECTED_HISTORICAL = [
    "profiles/animation/walk-front-v1.json",
    "profiles/animation/idle-front-v1.json",
    "profiles/animation/attack-front-v1.json",
    "profiles/animation/attack-front-v2.json",
    "docs/evidence/walk-front-v081/walk-front-spritesheet-v081.png",
    "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-front-v2-preview.gif",
]
PROTECTED_RUN_FRONT = [
    "profiles/animation/run-front-v1.json",
    "docs/evidence/animation-runtime-v0131/run-front-v1/run-front-preview-v0131.gif",
    "docs/evidence/animation-runtime-v0131/run-front-v1/run-front-spritesheet-v0131.png",
]

sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import (  # noqa: E402
    AnimationContractError,
    compile_spec,
    decode_gif_timing,
    gif_timing_within_tolerance,
    load_spec,
    package_compiled,
    qa_compiled,
)
from ugas.animation_profiles import hit_front_v1 as hit_adapter  # noqa: E402
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


def _git_rev(name: str) -> str:
    result = subprocess.run(["git", "rev-parse", name], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0 or len(result.stdout.strip()) != 40:
        raise RuntimeError(f"git_rev_unresolved:{name}")
    return result.stdout.strip()


def _merge_base(base: str, head: str) -> str:
    result = subprocess.run(["git", "merge-base", base, head], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0 or len(result.stdout.strip()) != 40:
        raise RuntimeError("merge_base_unresolved")
    return result.stdout.strip()


def _semantic_fixture(spec: dict[str, Any], context: dict[str, Any], prepared: dict[str, Any], mutate: Callable[[dict[str, Any]], None], rebuild_targets: bool = False) -> dict[str, Any]:
    fixture = copy.deepcopy(prepared)
    mutate(fixture)
    if rebuild_targets:
        base = hit_adapter._base_target(context)
        fixture["targets"] = [hit_adapter._target_for_frame(context, index, fixture["samples"][index], base) for index in range(int(spec["frame_count"]))]
    records = [{"feet": {"status": "HIT_FOOT_GROUND_QA_PASSED", "support_side": "both"}} for _ in fixture["targets"]]
    outputs = [Image.new("RGBA", (512, 512), (0, 0, 0, 0)) for _ in fixture["targets"]]
    return hit_adapter._temporal_qa(spec, context, fixture, records, outputs)


def _check_assets(paths: list[str], base_commit: str, schema_version: str) -> dict[str, Any]:
    if not base_commit or len(str(base_commit)) != 40:
        return {"schema_version": schema_version, "status": "APPROVED_ASSET_BASELINE_UNAVAILABLE", "base_commit": base_commit, "checks": [], "failures": ["immutable_baseline_missing_or_invalid"]}
    rev = subprocess.run(["git", "rev-parse", "--verify", f"{base_commit}^{{commit}}"], cwd=ROOT, capture_output=True, text=True, check=False)
    if rev.returncode != 0:
        return {"schema_version": schema_version, "status": "APPROVED_ASSET_BASELINE_UNAVAILABLE", "base_commit": base_commit, "checks": [], "failures": ["immutable_baseline_cannot_be_resolved"]}
    checks, failures = [], []
    for path in paths:
        current = ROOT / path
        shown = subprocess.run(["git", "show", f"{base_commit}:{path}"], cwd=ROOT, capture_output=True, check=False)
        if shown.returncode != 0 or not shown.stdout:
            checks.append({"path": path, "present": current.is_file(), "byte_identical_to_base": False, "current_sha256": digest(current) if current.is_file() else None, "error": "git_show_failed"})
            failures.append(f"missing_or_unreadable:{path}")
            continue
        identical = current.is_file() and current.read_bytes() == shown.stdout
        checks.append({"path": path, "present": current.is_file(), "byte_identical_to_base": identical, "current_sha256": digest(current) if current.is_file() else None, "base_sha256": digest_bytes(shown.stdout)})
        if not identical:
            failures.append(f"drift:{path}")
    status = "APPROVED_ASSETS_UNTOUCHED" if not failures else "APPROVED_ASSET_DRIFT"
    return {"schema_version": schema_version, "status": status, "base_commit": base_commit, "comparison": f"git show {base_commit}:path", "head_fallback_used": False, "checks": checks, "failures": failures}


def _approved_assets_untouched(base_commit: str | None = IMMUTABLE_BASE) -> dict[str, Any]:
    historical = _check_assets(PROTECTED_HISTORICAL, str(base_commit), "0.14.0")
    run_front = _check_assets(PROTECTED_RUN_FRONT, RUN_APPROVED_HEAD, "0.14.0")
    failures = list(historical.get("failures", [])) + [f"run_front:{item}" for item in run_front.get("failures", [])]
    status = "APPROVED_ASSETS_UNTOUCHED" if historical["status"] == "APPROVED_ASSETS_UNTOUCHED" and run_front["status"] == "APPROVED_ASSETS_UNTOUCHED" else historical["status"] if historical["status"] != "APPROVED_ASSETS_UNTOUCHED" else "APPROVED_ASSET_DRIFT"
    if historical["status"] == "APPROVED_ASSET_BASELINE_UNAVAILABLE":
        status = "APPROVED_ASSET_BASELINE_UNAVAILABLE"
    return {
        "schema_version": "0.14.0",
        "status": status,
        "base_commit": base_commit,
        "run_front_approved_head": RUN_APPROVED_HEAD,
        "head_fallback_used": False,
        "historical": historical,
        "run_front": run_front,
        "checks": historical.get("checks", []) + run_front.get("checks", []),
        "failures": failures,
    }


def _negative_controls(spec: dict[str, Any], context: dict[str, Any], prepared: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    controls: dict[str, Any] = {}

    def zero_recoil(fixture: dict[str, Any]) -> None:
        for sample in fixture["samples"]:
            sample["root_shift_x"] = 0.0
            sample["root_shift_y"] = 0.0
            sample["torso_rotation_deg"] = 0.0
            sample["torso_lean_x"] = 0.0

    zero_result = _semantic_fixture(spec, context, prepared, zero_recoil, rebuild_targets=True)
    controls["NC-01_zero_recoil"] = {"gate": "recoil_magnitude", "status": "REJECTED" if not zero_result["hard_gates"]["recoil_magnitude"] else "ACCEPTED", "hard_gates": zero_result["hard_gates"]}

    def anticipate(fixture: dict[str, Any]) -> None:
        fixture["samples"][0]["root_shift_x"] = -abs(float(fixture["samples"][2]["root_shift_x"]))
        fixture["samples"][0]["root_shift_y"] = -abs(float(fixture["samples"][2]["root_shift_y"]))
        fixture["samples"][0]["torso_rotation_deg"] = -abs(float(fixture["samples"][2]["torso_rotation_deg"]))

    anticipate_result = _semantic_fixture(spec, context, prepared, anticipate, rebuild_targets=True)
    controls["NC-02_anticipatory_motion_before_impact"] = {"gate": "impact_causality", "status": "REJECTED" if not anticipate_result["hard_gates"]["impact_causality"] else "ACCEPTED", "hard_gates": anticipate_result["hard_gates"]}

    def wrong_peak(fixture: dict[str, Any]) -> None:
        fixture["samples"][1], fixture["samples"][2] = copy.deepcopy(fixture["samples"][2]), copy.deepcopy(fixture["samples"][1])

    peak_result = _semantic_fixture(spec, context, prepared, wrong_peak, rebuild_targets=True)
    controls["NC-03_wrong_recoil_peak"] = {"gate": "unique_recoil_peak", "status": "REJECTED" if not peak_result["hard_gates"]["unique_recoil_peak"] else "ACCEPTED", "hard_gates": peak_result["hard_gates"]}

    def stuck_peak(fixture: dict[str, Any]) -> None:
        for index in (3, 4, 5):
            fixture["samples"][index] = copy.deepcopy(fixture["samples"][2])

    stuck_result = _semantic_fixture(spec, context, prepared, stuck_peak, rebuild_targets=True)
    controls["NC-04_no_recovery"] = {"gate": "recovery_convergence", "status": "REJECTED" if not stuck_result["hard_gates"]["recovery_convergence"] else "ACCEPTED", "hard_gates": stuck_result["hard_gates"]}

    slide_result = _semantic_fixture(spec, context, prepared, lambda fixture: fixture["targets"][1]["joints"]["ankle_left"].__setitem__("x", fixture["targets"][1]["joints"]["ankle_left"]["x"] + 20.0))
    controls["NC-05_foot_slide_or_teleport"] = {"gate": "foot_contact_windows", "status": "REJECTED" if not slide_result["hard_gates"]["foot_contact_windows"] else "ACCEPTED", "hard_gates": slide_result["hard_gates"]}

    jump_result = _semantic_fixture(spec, context, prepared, lambda fixture: fixture["targets"][3]["joints"]["knee_right"].__setitem__("x", fixture["targets"][3]["joints"]["knee_right"]["x"] + 80.0))
    controls["NC-06_angular_jump"] = {"gate": "angular_continuity", "status": "REJECTED" if not jump_result["hard_gates"]["angular_continuity"] else "ACCEPTED", "hard_gates": jump_result["hard_gates"]}

    weapon_result = _semantic_fixture(spec, context, prepared, lambda fixture: fixture["targets"][2]["joints"]["weapon_tip"].__setitem__("x", fixture["targets"][2]["joints"]["weapon_tip"]["x"] + 80.0))
    controls["NC-07_weapon_snap_or_wrist_break"] = {"gate": "weapon_wrist_continuity", "status": "REJECTED" if not weapon_result["hard_gates"]["weapon_wrist_continuity"] else "ACCEPTED", "hard_gates": weapon_result["hard_gates"]}

    def collapse(fixture: dict[str, Any]) -> None:
        fixture["samples"][2]["torso_rotation_deg"] = 90.0
        fixture["samples"][2]["root_shift_y"] = 80.0

    death_result = _semantic_fixture(spec, context, prepared, collapse, rebuild_targets=True)
    controls["NC-08_death_like_collapse"] = {"gate": "not_death_like_collapse", "status": "REJECTED" if not death_result["hard_gates"]["not_death_like_collapse"] else "ACCEPTED", "hard_gates": death_result["hard_gates"]}

    missing_hash = copy.deepcopy(spec)
    missing_hash["provenance"]["source_sha256"] = "0" * 64
    try:
        load_source_context(missing_hash, ROOT)
    except (OSError, ValueError, KeyError) as exc:
        controls["NC-09_source_dependency_hash_removed"] = {"gate": "source_dependency_hash", "status": "REJECTED", "error": type(exc).__name__}
    else:
        controls["NC-09_source_dependency_hash_removed"] = {"gate": "source_dependency_hash", "status": "ACCEPTED"}

    with tempfile.TemporaryDirectory(prefix="ugas-v0140-package-nc-", dir=ROOT / "tmp") as directory:
        temp = Path(directory)
        temp_manifest = temp / "compiled-manifest.json"
        temp_manifest.write_bytes(manifest_path.read_bytes())
        false_qa = read_json(PACKAGE_OUT / "qa-result.json")
        false_qa["hard_gates"]["synthetic_false_gate"] = False
        (temp / "qa-result.json").write_text(json.dumps(false_qa, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            package_compiled(temp_manifest, ROOT)
        except (AnimationContractError, SchemaValidationError, ValueError, KeyError) as exc:
            controls["NC-10_synthetic_false_gate_in_package"] = {"gate": "package_qualified_qa", "status": "REJECTED", "error": type(exc).__name__}
        else:
            controls["NC-10_synthetic_false_gate_in_package"] = {"gate": "package_qualified_qa", "status": "ACCEPTED"}

    passed = all(item["status"] == "REJECTED" for item in controls.values())
    return {"schema_version": "0.14.0", "status": "NC_01_TO_NC_10_PASSED" if passed else "NC_01_TO_NC_10_GAP", "controls": controls, "source": "scripts/validation/run_animation_runtime_v0140.py independent fixture mutations"}


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

    sheet = Image.new("RGBA", (3 * 512, 2 * 548), (18, 22, 32, 255))
    draw = ImageDraw.Draw(sheet, "RGBA")
    for index, record in enumerate(marker_records):
        with Image.open(ROOT / record["path"]) as opened:
            image = opened.convert("RGBA")
        left, top = (index % 3) * 512, (index // 3) * 548
        sheet.alpha_composite(image, (left, top + 36))
        draw.text((left + 8, top + 10), f"{record['phase']} | {'/'.join(record['events'])}", fill=(255, 255, 255, 255), font=font)
    sheet_path = OUT / "hit-front-phase-markers-v0140.png"
    sheet.save(sheet_path, format="PNG", optimize=False)
    return sheet_path, marker_records


def run() -> dict[str, Any]:
    (ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if PACKAGE_OUT.exists():
        shutil.rmtree(PACKAGE_OUT)
    implementation_base = _git_rev(IMMUTABLE_BASE)
    if implementation_base != IMMUTABLE_BASE:
        raise RuntimeError("implementation_base_mismatch")
    execution_head = _git_rev("HEAD")
    merge_base = _merge_base(IMMUTABLE_BASE, "HEAD")
    if merge_base != IMMUTABLE_BASE:
        raise RuntimeError(f"merge_base_must_be_immutable_v0124:{merge_base}")
    spec = load_spec(SPEC_PATH, ROOT)
    context = hit_adapter.load_context(spec, ROOT)
    prepared = hit_adapter.prepare(spec, context)
    manifest_path = compile_spec(SPEC_PATH, PACKAGE_OUT, ROOT)
    qa_path = qa_compiled(manifest_path, ROOT)
    qa = read_json(qa_path)
    if qa["decision"] != "QUALIFIED":
        raise RuntimeError(f"HIT_REACTION_FRONT_NOT_QUALIFIED:{qa.get('failures')}")
    package_path = package_compiled(manifest_path, ROOT)
    manifest, package = read_json(manifest_path), read_json(package_path)
    gif_path = ROOT / package["preview_gif"]["path"]
    decoded_gif = decode_gif_timing(gif_path)
    gif_check = gif_timing_within_tolerance(spec, decoded_gif)
    if gif_check["status"] != "GIF_TIMING_PASSED":
        raise RuntimeError(f"GIF_TIMING_FAILED:{gif_check}")
    negative = _negative_controls(spec, context, prepared, manifest_path)
    write_json(OUT / "hit-front-targets-v0140.json", {"schema_version": "0.14.0", "animation_id": spec["animation_id"], "phase_order": list(hit_adapter.PHASES), "targets": prepared["targets"], "target_hashes": [target["target_joint_sha256"] for target in prepared["targets"]], "key_pose_bindings": spec["key_pose_bindings"], "motion_tracks_sha256": prepared["track_hash"], "parameters_frozen_before_render": True, "source_only_pixels": True})
    write_json(OUT / "hit-front-frame-qa-v0140.json", {"schema_version": "0.14.0", "animation_id": spec["animation_id"], "status": qa["status"], "decision": qa["decision"], "frames": qa["frames"]})
    write_json(OUT / "hit-front-temporal-qa-v0140.json", {"schema_version": "0.14.0", "animation_id": spec["animation_id"], "status": qa["temporal"]["status"], "metrics": qa["temporal"]["metrics"], "hard_gates": qa["temporal"]["hard_gates"], "recoil": qa["temporal"]["recoil"], "weapon": qa["temporal"]["weapon"]})
    write_json(OUT / "hit-front-foot-ground-qa-v0140.json", {"schema_version": "0.14.0", "animation_id": spec["animation_id"], "status": qa["foot_ground"]["status"], "frames": qa["foot_ground"]["frames"], "contact": qa["foot_ground"]["contact"], "ground_reference_y": qa["foot_ground"].get("ground_reference_y")})
    write_json(OUT / "hit-front-body-mechanics-qa-v0140.json", {"schema_version": "0.14.0", "animation_id": spec["animation_id"], **qa["body_mechanics"]})
    write_json(OUT / "hit-front-weapon-qa-v0140.json", {"schema_version": "0.14.0", "animation_id": spec["animation_id"], **qa["weapon"]})
    write_json(OUT / "hit-front-continuity-qa-v0140.json", {"schema_version": "0.14.0", "animation_id": spec["animation_id"], "status": "HIT_CONTINUITY_INTERPOLATION_PASSED" if qa["temporal"]["hard_gates"]["angular_continuity"] and qa["temporal"]["hard_gates"]["angular_acceleration_continuity"] and qa["temporal"]["hard_gates"]["nonfinite_and_gap_free"] else "HIT_CONTINUITY_INTERPOLATION_GAP", "gates": {key: value for key, value in qa["temporal"]["hard_gates"].items() if key in {"angular_continuity", "angular_acceleration_continuity", "nonfinite_and_gap_free", "foreground_height_stability"}}, "metrics": {key: value for key, value in qa["temporal"]["metrics"].items() if "angle" in key or "height" in key}})
    write_json(OUT / "hit-front-gate-negative-controls-v0140.json", negative)
    assets = _approved_assets_untouched(IMMUTABLE_BASE)
    write_json(OUT / "approved-assets-untouched-v0140.json", assets)
    write_json(OUT / "hit-front-gif-timing-v0140.json", {"schema_version": "0.14.0", **gif_check, "package_metadata": {"fps": package.get("fps"), "per_frame_duration_ms": package.get("per_frame_duration_ms"), "gif_encoded_frame_durations_ms": package.get("gif_encoded_frame_durations_ms"), "gif_total_cycle_ms": package.get("gif_total_cycle_ms"), "gif_effective_fps": package.get("gif_effective_fps")}})
    marker_sheet, marker_records = _marker_sheet(manifest, qa)
    visual_images = [{"frame": index, "phase": item["phase"], "source_path": item["path"], "rgba_sha256": item["rgba_sha256"], "target_hash": item["target_hash"], "media_type": "image/png", "role": "compiled-source-only-frame", "events": [event for event in spec["event_markers"] if int(event["frame"]) == index]} for index, item in enumerate(manifest["frames"])]
    visual_images.extend([{"path": package["preview_gif"]["path"], "sha256": package["preview_gif"]["sha256"], "media_type": "image/gif", "role": "review-gif", "events": spec["event_markers"], "gif_encoded_frame_durations_ms": decoded_gif["durations_ms"], "gif_total_cycle_ms": decoded_gif["total_cycle_ms"], "gif_effective_fps": decoded_gif["effective_fps"]}, {"path": package["sprite_sheet"]["path"], "sha256": package["sprite_sheet"]["sha256"], "media_type": "image/png", "role": "compiled-rgba-spritesheet", "events": spec["event_markers"]}, {"path": relative(marker_sheet), "sha256": digest(marker_sheet), "media_type": "image/png", "role": "phase-marker-review-sheet", "events": spec["event_markers"]}])
    visual_manifest = {"schema_version": "0.14.0", "review_state": "hit-front-v1-technically-qualified", "review_subject": {"animation_id": spec["animation_id"], "direction": spec["direction"], "frame_count": spec["frame_count"], "fps": spec["fps"], "loop": spec["loop"], "source_r4_sha256": spec["provenance"]["source_sha256"]}, "event_markers": spec["event_markers"], "event_markers_sha256": manifest["event_markers_sha256"], "motion_tracks_sha256": manifest["motion_tracks_sha256"], "gif_timing": decoded_gif, "images": visual_images, "marker_frames": marker_records, "source_only_pixels": True, "external_visual": "REQUIRED", "production_routing": "BLOCKED", "package_manifest": {"path": relative(package_path), "sha256": digest(package_path)}}
    write_json(OUT / "hit-front-visual-manifest-v0140.json", visual_manifest)
    execution = {
        "schema_version": "0.14.0",
        "prompt": "UGAS-v0.14.0-HIT-REACTION-FRONT",
        "implementation_base_commit": implementation_base,
        "execution_head_commit": execution_head,
        "run_front_approved_head_sha": RUN_APPROVED_HEAD,
        "animation_id": spec["animation_id"],
        "status": qa["status"],
        "decision": qa["decision"],
        "frame_count": spec["frame_count"],
        "fps": spec["fps"],
        "loop": spec["loop"],
        "gif_encoded_frame_durations_ms": decoded_gif["durations_ms"],
        "gif_total_cycle_ms": decoded_gif["total_cycle_ms"],
        "gif_effective_fps": decoded_gif["effective_fps"],
        "motion_tracks_sha256": manifest["motion_tracks_sha256"],
        "event_markers_sha256": manifest["event_markers_sha256"],
        "source_r4_sha256": spec["provenance"]["source_sha256"],
        "source_only_pixels": True,
        "sam2_runs": 0,
        "comfyui_generation_jobs": 0,
        "diffusion_runs": 0,
        "new_generation": 0,
        "production_approved": False,
        "production_routing": "BLOCKED",
        "external_visual": "REQUIRED",
        "negative_controls": negative["status"],
        "approved_assets_untouched": assets["status"],
        "package": {"path": relative(package_path), "sha256": digest(package_path), "preview_gif": package["preview_gif"], "sprite_sheet": package["sprite_sheet"]},
        "review_artifacts": {"visual_manifest": relative(OUT / "hit-front-visual-manifest-v0140.json"), "phase_marker_sheet": relative(marker_sheet), "negative_controls": relative(OUT / "hit-front-gate-negative-controls-v0140.json")},
        "historical_v0130_preserved": True,
        "historical_v0131_preserved": True,
        "next_capability_started": False,
        "executor_does_not_claim_visual_approval": True,
    }
    write_json(OUT / "execution-evidence-v0.14.0.json", execution)
    if negative["status"] != "NC_01_TO_NC_10_PASSED" or assets["status"] != "APPROVED_ASSETS_UNTOUCHED":
        raise RuntimeError(f"V0140_GATES_FAILED:{negative['status']}:{assets['status']}")
    return {"status": "ANIMATION_RUNTIME_V0140_PASSED", "decision": qa["decision"], "animation_id": spec["animation_id"], "frames": len(manifest["frames"]), "package": relative(package_path), "preview_gif": package["preview_gif"]["path"], "negative_controls": negative["status"], "approved_assets": assets["status"], "gif_effective_fps": decoded_gif["effective_fps"], "gif_total_cycle_ms": decoded_gif["total_cycle_ms"], "external_visual": "REQUIRED", "production_routing": "BLOCKED"}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
        raise SystemExit(0)
    except Exception as exc:
        print(json.dumps({"status": "ANIMATION_RUNTIME_V0140_FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False))
        raise SystemExit(2)
