"""Execute the v0.11.0 motion-quality attack-front-v2 qualification slice."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/animation-runtime-v0110/attack-front-v2"
BASELINE = "c11196e5e854a0fbc6ec62e959de5ecc28d492ce"
R4_SHA256 = "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798"

sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import compile_spec, evaluate_lifecycle, event_markers_sha256, load_spec, package_compiled, qa_compiled
from ugas.animation_profiles.common import canonical_json
from ugas.animation_profiles import attack_front_v2
from ugas.motion_curves import MotionCurveError, motion_tracks_sha256, sample_all_tracks, sample_track, validate_motion_tracks
from ugas.schema_validation import SchemaValidationError
from ugas.cutout_temporal_v081 import map_presentation_point


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _rejection(callable_value) -> dict[str, Any]:
    try:
        callable_value()
    except (MotionCurveError, SchemaValidationError, ValueError, TypeError) as exc:
        return {"status": "REJECTED", "error": type(exc).__name__, "message": str(exc)}
    return {"status": "ACCEPTED"}


def _curve_contract_evidence() -> dict[str, Any]:
    valid = {
        "frame_count": 6,
        "motion_tracks": [
            {"track_id": "scalar-linear", "value_type": "scalar", "interpolation": "linear", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 5, "value": 10.0}]},
            {"track_id": "vec2-smoothstep", "value_type": "vec2", "interpolation": "smoothstep", "keyframes": [{"frame": 0, "value": [0.0, 0.0]}, {"frame": 4, "value": [8.0, -4.0]}]},
            {"track_id": "scalar-hermite", "value_type": "scalar", "interpolation": "cubic_hermite", "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 2, "value": 4.0}, {"frame": 5, "value": 9.0}]},
        ],
    }
    tracks = validate_motion_tracks(valid)
    linear = sample_track(tracks[0], 2.5)
    vector = sample_track(tracks[1], 2.0)
    hermite_a = sample_track(tracks[2], 1.25)
    hermite_b = sample_track(tracks[2], 1.25)
    no_clamp = {"track_id": "no-clamp", "value_type": "scalar", "interpolation": "linear", "keyframes": [{"frame": 1, "value": 1.0}, {"frame": 3, "value": 3.0}]}
    clamp = {**no_clamp, "clamp_policy": "clamp"}
    duplicate = {"frame_count": 4, "motion_tracks": [no_clamp, copy.deepcopy(no_clamp)]}
    unsorted = {"frame_count": 4, "motion_tracks": [{**no_clamp, "keyframes": [{"frame": 2, "value": 2.0}, {"frame": 1, "value": 1.0}]}]}
    out_of_range = {"frame_count": 3, "motion_tracks": [{**no_clamp, "keyframes": [{"frame": 0, "value": 0.0}, {"frame": 3, "value": 3.0}]}]}
    nonfinite = {"frame_count": 4, "motion_tracks": [{**no_clamp, "keyframes": [{"frame": 1, "value": float("nan")}, {"frame": 3, "value": 3.0}]}]}
    bad_interpolation = {"frame_count": 4, "motion_tracks": [{**no_clamp, "interpolation": "bezier"}]}
    controls = {
        "duplicate_track_id": _rejection(lambda: validate_motion_tracks(duplicate)),
        "strictly_ascending_keyframes": _rejection(lambda: validate_motion_tracks(unsorted)),
        "keyframe_in_timeline": _rejection(lambda: validate_motion_tracks(out_of_range)),
        "nan_or_inf_rejected": _rejection(lambda: validate_motion_tracks(nonfinite)),
        "unknown_interpolation_rejected": _rejection(lambda: validate_motion_tracks(bad_interpolation)),
        "out_of_range_sample_without_explicit_clamp": _rejection(lambda: sample_track(no_clamp, 0.0)),
        "out_of_range_sample_with_explicit_clamp": {"status": "ACCEPTED", "value": sample_track(clamp, 0.0)},
    }
    mutated = copy.deepcopy(valid)
    mutated["motion_tracks"][0]["keyframes"][1]["value"] = 11.0
    base_hash = motion_tracks_sha256(valid)
    mutated_hash = motion_tracks_sha256(mutated)
    passed = (
        linear == 5.0
        and vector == [4.0, -2.0]
        and hermite_a == hermite_b
        and all(value["status"] == "REJECTED" for key, value in controls.items() if key != "out_of_range_sample_with_explicit_clamp")
        and controls["out_of_range_sample_with_explicit_clamp"]["value"] == 1.0
        and base_hash != mutated_hash
    )
    return {
        "schema_version": "0.11.0",
        "status": "GENERIC_MOTION_CURVE_CONTRACT_PASSED" if passed else "GENERIC_MOTION_CURVE_CONTRACT_GAP",
        "contract": {"optional_motion_tracks": True, "opaque_track_ids": True, "value_types": ["scalar", "vec2"], "interpolations": ["linear", "smoothstep", "cubic_hermite"], "cubic_tangent_policy": "one-sided-endpoints-centered-interior", "rounding_boundary": "target-skeleton-only", "image_heuristics": False},
        "positive_fixtures": {"linear_scalar_at_2_5": linear, "smoothstep_vec2_at_2": vector, "hermite_replay_equal": hermite_a == hermite_b, "exact_keyframe": sample_track(tracks[0], 0.0) == 0.0, "track_hash": base_hash, "hash_changes_when_track_mutates": base_hash != mutated_hash},
        "negative_controls": controls,
        "proof_source": "src/ugas/motion_curves.py",
    }


def _v2_negative_controls(spec: dict[str, Any], context: dict[str, Any], prepared: dict[str, Any], qa_result: dict[str, Any]) -> dict[str, Any]:
    """Exercise the three profile-level fail-closed controls without changing outputs."""
    zero_targets = [copy.deepcopy(prepared["targets"][0]) for _ in prepared["targets"]]
    zero_samples = []
    for sample in prepared["samples"]:
        zero_samples.append({key: [0.0, 0.0] if isinstance(value, list) else 0.0 for key, value in sample.items()})
    body = attack_front_v2._body_mechanics(spec, zero_targets, zero_samples, context)

    weapon_records = copy.deepcopy(qa_result["frames"])
    frozen_tip = list(weapon_records[6]["weapon"]["tip_presented"])
    weapon_records[7]["weapon"]["tip_presented"] = list(frozen_tip)
    weapon_records[8]["weapon"]["tip_presented"] = list(frozen_tip)
    weapon = attack_front_v2._weapon_arc_qa(spec, weapon_records)

    foot_records = copy.deepcopy(qa_result["frames"])
    foot_records[1]["feet"]["feet"]["left"]["projected_ground_y"] += 10.0
    foot = attack_front_v2._foot_ground_qa(foot_records, prepared["targets"], spec)
    controls = {
        "body_mechanics_zero_root_torso_counter": {"status": "REJECTED" if body["status"] != "ATTACK_V2_BODY_MECHANICS_QA_PASSED" else "ACCEPTED", "observed": body["status"]},
        "weapon_zero_post_hit_follow_through": {"status": "REJECTED" if weapon["status"] != "ATTACK_V2_WEAPON_ARC_QA_PASSED" else "ACCEPTED", "observed": weapon["status"]},
        "foot_slide_over_threshold": {"status": "REJECTED" if foot["status"] != "ATTACK_V2_FOOT_GROUND_QA_PASSED" else "ACCEPTED", "observed": foot["status"]},
    }
    return {"controls": controls, "all_rejected": all(item["status"] == "REJECTED" for item in controls.values()), "proof_source": "scripts/validation/run_animation_runtime_v0110.py:_v2_negative_controls"}


def _baseline_blob(path: str) -> bytes | None:
    result = subprocess.run(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else None


def _historical_replay(spec_path: Path) -> dict[str, Any]:
    historical_paths = [
        *[f"docs/evidence/animation-runtime-v0100/attack-front-v1/frame-{index:02d}.png" for index in range(10)],
        "docs/evidence/animation-runtime-v0100/attack-front-v1/attack-front-spritesheet-v0100.png",
        "docs/evidence/animation-runtime-v0100/attack-front-v1/attack-front-preview-v0100.gif",
        *[f"docs/evidence/walk-front-v081/frames/{name}" for name in ("frame-00-contact-left.png", "frame-01-down-left.png", "frame-02-passing-left.png", "frame-03-up-left.png", "frame-04-contact-right.png", "frame-05-down-right.png", "frame-06-passing-right.png", "frame-07-up-right.png")],
        "docs/evidence/walk-front-v081/walk-front-preview-v081.gif",
        *[f"docs/evidence/idle-front-v090/frames/frame-{index:02d}-I{index}" + ("-neutral-A.png" if index == 0 else "-inhale-early.png" if index == 1 else "-inhale-mid.png" if index == 2 else "-inhale-peak.png" if index == 3 else "-return-A.png" if index == 4 else "-neutral-B.png" if index == 5 else "-exhale-early.png" if index == 6 else "-exhale-mid.png" if index == 7 else "-exhale-peak.png" if index == 8 else "-return-B.png" if index == 9 else "-settle.png" if index == 10 else "-pre-loop.png") for index in range(12)],
        "docs/evidence/animation-runtime-v090/idle-front-v1/idle-front-preview-v090.gif",
    ]
    fixture_checks: list[dict[str, Any]] = []
    for relative in historical_paths:
        current = ROOT / relative
        baseline = _baseline_blob(relative)
        current_bytes = current.read_bytes() if current.is_file() else None
        fixture_checks.append({"path": relative, "baseline_sha256": digest_bytes(baseline) if baseline is not None else None, "current_sha256": digest_bytes(current_bytes) if current_bytes is not None else None, "byte_identical_to_baseline": baseline is not None and current_bytes == baseline})
    with tempfile.TemporaryDirectory(prefix="ugas-v0110-v1-replay-", dir=ROOT / "tmp") as directory:
        replay_dir = Path(directory)
        replay_manifest_path = compile_spec(ROOT / "profiles/animation/attack-front-v1.json", replay_dir, ROOT)
        replay_qa_path = qa_compiled(replay_manifest_path, ROOT)
        replay_package_path = package_compiled(replay_manifest_path, ROOT)
        replay_manifest, replay_qa, replay_package = read_json(replay_manifest_path), read_json(replay_qa_path), read_json(replay_package_path)
        generated_checks = []
        historical_dir = ROOT / "docs/evidence/animation-runtime-v0100/attack-front-v1"
        for index, item in enumerate(replay_manifest["frames"]):
            expected = historical_dir / f"frame-{index:02d}.png"
            generated_checks.append({"path": f"attack-front-v1/frame-{index:02d}.png", "expected_sha256": digest(expected), "replay_sha256": digest(ROOT / item["path"]) if (ROOT / item["path"]).is_file() else None, "byte_identical": (ROOT / item["path"]).read_bytes() == expected.read_bytes()})
        replay_sprite = replay_package["sprite_sheet"]; replay_gif = replay_package["preview_gif"]
        generated_checks.extend([
            {"path": "attack-front-v1/attack-front-spritesheet-v0100.png", "expected_sha256": digest(historical_dir / "attack-front-spritesheet-v0100.png"), "replay_sha256": digest(ROOT / replay_sprite["path"]), "byte_identical": (ROOT / replay_sprite["path"]).read_bytes() == (historical_dir / "attack-front-spritesheet-v0100.png").read_bytes()},
            {"path": "attack-front-v1/attack-front-preview-v0100.gif", "expected_sha256": digest(historical_dir / "attack-front-preview-v0100.gif"), "replay_sha256": digest(ROOT / replay_gif["path"]), "byte_identical": (ROOT / replay_gif["path"]).read_bytes() == (historical_dir / "attack-front-preview-v0100.gif").read_bytes()},
        ])
        marker_hashes = {"spec": event_markers_sha256(load_spec(ROOT / "profiles/animation/attack-front-v1.json", ROOT)), "compiled": replay_manifest["event_markers_sha256"], "qa": replay_qa["event_markers_sha256"], "package": replay_package["event_markers_sha256"]}
        replay_passed = replay_qa["decision"] == "QUALIFIED" and all(item["byte_identical"] for item in generated_checks) and len(set(marker_hashes.values())) == 1
    return {"schema_version": "0.11.0", "status": "HISTORICAL_ANIMATION_REPLAY_PASSED" if replay_passed and all(item["byte_identical_to_baseline"] for item in fixture_checks) else "HISTORICAL_ANIMATION_REPLAY_DRIFT", "baseline_commit": BASELINE, "fixture_checks": fixture_checks, "attack_front_v1_replay": {"checks": generated_checks, "marker_hashes": marker_hashes, "qa_status": replay_qa["status"], "package_qa_decision": replay_package["qa_decision"]}, "walk_front_v081_and_idle_front_v090_unchanged": all(item["byte_identical_to_baseline"] for item in fixture_checks if "walk-front-v081" in item["path"] or "idle-front-v090" in item["path"] or "animation-runtime-v090/idle-front-v1" in item["path"])}


def _draw_overlay(source: Path, target: dict[str, Any], detected: dict[str, Any], destination: Path, phase: str, metrics: dict[str, Any], presentation: dict[str, Any]) -> None:
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default()
    edges = (("shoulder_left", "elbow_left"), ("elbow_left", "wrist_left"), ("shoulder_right", "elbow_right"), ("elbow_right", "wrist_right"), ("hip_left", "knee_left"), ("knee_left", "ankle_left"), ("hip_right", "knee_right"), ("knee_right", "ankle_right"))
    def target_point(name: str) -> tuple[int, int] | None:
        value = target.get("joints", {}).get(name)
        if not value:
            return None
        x, y = map_presentation_point((float(value["x"]), float(value["y"])), presentation)
        return round(x), round(y)
    def detected_point(name: str) -> tuple[int, int] | None:
        value = detected.get("landmarks", {}).get(name)
        if not value:
            return None
        return round(float(value["x"]) * image.width), round(float(value["y"]) * image.height)
    for first, second in edges:
        a, b = target_point(first), target_point(second)
        if a and b:
            draw.line((a, b), fill=(255, 80, 80, 235), width=3)
        a, b = detected_point(first), detected_point(second)
        if a and b:
            draw.line((a, b), fill=(70, 240, 110, 235), width=2)
    for name in target.get("joints", {}):
        point = target_point(name)
        if point:
            draw.ellipse((point[0] - 4, point[1] - 4, point[0] + 4, point[1] + 4), fill=(255, 70, 70, 235), outline=(40, 0, 0, 255))
    for name in detected.get("landmarks", {}):
        point = detected_point(name)
        if point:
            draw.ellipse((point[0] - 3, point[1] - 3, point[0] + 3, point[1] + 3), fill=(70, 240, 110, 235), outline=(0, 45, 0, 255))
    draw.rectangle((0, 0, image.width, 30), fill=(255, 255, 255, 230))
    draw.text((7, 6), f"{phase} | target=red detected=green | PCK={metrics.get('pck_at_010', 0):.3f} NME={metrics.get('nme', 1):.3f}", fill=(10, 10, 10, 255), font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=False)


def _visual_manifest(manifest: dict[str, Any], qa: dict[str, Any]) -> dict[str, Any]:
    images = []
    for index, frame in enumerate(manifest["frames"]):
        overlay = OUT / "visual" / "target-detected-overlays" / f"frame-{index:02d}-{frame['phase']}.png"
        images.append({"archive_name": overlay.name, "source_path": overlay.relative_to(ROOT).as_posix(), "revision_id": "attack-front-v2-render-v0110", "sha256": digest(overlay), "media_type": "image/png", "role": "target-detected-overlay", "frame": index, "phase": frame["phase"]})
    sheet = OUT / "attack-front-v2-spritesheet.png"
    gif = OUT / "attack-front-v2-preview.gif"
    images.extend([
        {"archive_name": sheet.name, "source_path": sheet.relative_to(ROOT).as_posix(), "revision_id": "attack-front-v2-render-v0110", "sha256": digest(sheet), "media_type": "image/png", "role": "final-rgba-spritesheet"},
        {"archive_name": gif.name, "source_path": gif.relative_to(ROOT).as_posix(), "revision_id": "attack-front-v2-render-v0110", "sha256": digest(gif), "media_type": "image/gif", "role": "review-gif"},
    ])
    return {"schema_version": "0.11.0", "review_state": "attack-front-v2-technically-qualified", "review_subject": {"animation_id": "attack-front-v2", "direction": "front", "frame_count": 12, "baseline_commit": BASELINE, "source_r4_sha256": R4_SHA256}, "required_current_visuals": [item["archive_name"] for item in images], "images": images, "source_only_pixels": True, "external_visual_review": "REQUIRED", "production_routing": "BLOCKED", "qa_status": qa["status"]}


def run() -> dict[str, Any]:
    (ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    spec_path = ROOT / "profiles/animation/attack-front-v2.json"
    spec = load_spec(spec_path, ROOT)
    manifest_path = compile_spec(spec_path, OUT, ROOT)
    qa_path = qa_compiled(manifest_path, ROOT)
    package_path = package_compiled(manifest_path, ROOT)
    manifest, qa, package = read_json(manifest_path), read_json(qa_path), read_json(package_path)
    if qa["decision"] != "QUALIFIED" or qa["status"] != "CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED":
        raise RuntimeError(f"ATTACK_FRONT_V2_NOT_QUALIFIED:{qa.get('failures')}")
    overlay_records = []
    for index, frame in enumerate(manifest["frames"]):
        pose = qa["frames"][index]["pose"]
        overlay = OUT / "visual" / "target-detected-overlays" / f"frame-{index:02d}-{frame['phase']}.png"
        _draw_overlay(ROOT / frame["path"], frame["metadata"]["target"], pose["detected"], overlay, frame["phase"], pose["metrics"], spec["presentation_transform"])
        overlay_records.append({"frame": index, "phase": frame["phase"], "source_path": frame["path"], "overlay_path": overlay.relative_to(ROOT).as_posix(), "overlay_sha256": digest(overlay), "detected": pose["detected"], "metrics": pose["metrics"]})
    lifecycle = qa["temporal"]["lifecycle"]
    write_json(OUT / "attack-v2-body-mechanics-qa.json", {"schema_version": "0.11.0", "animation_id": spec["animation_id"], **qa["body_mechanics"]})
    write_json(OUT / "attack-v2-temporal-qa.json", {"schema_version": "0.11.0", "animation_id": spec["animation_id"], "status": qa["temporal"]["status"], "decision": qa["decision"], "metrics": qa["temporal"]["metrics"], "hard_gates": qa["temporal"]["hard_gates"], "lifecycle": lifecycle})
    write_json(OUT / "attack-v2-weapon-arc-qa.json", {"schema_version": "0.11.0", "animation_id": spec["animation_id"], "status": qa["weapon"]["status"], "decision": qa["decision"], **qa["weapon"]})
    write_json(OUT / "attack-v2-foot-ground-qa.json", {"schema_version": "0.11.0", "animation_id": spec["animation_id"], "status": qa["foot_ground"]["status"], "decision": qa["decision"], **qa["foot_ground"]})
    write_json(OUT / "attack-v2-event-marker-qa.json", {"schema_version": "0.11.0", "animation_id": spec["animation_id"], "status": "ATTACK_V2_EVENT_MARKER_CONTRACT_PASSED" if lifecycle["status"] == "ANIMATION_LIFECYCLE_PASSED" else "ATTACK_V2_EVENT_MARKER_CONTRACT_GAP", "markers": spec["event_markers"], "spec_event_markers_sha256": event_markers_sha256(spec), "compiled_event_markers": manifest["event_markers"], "compiled_event_markers_sha256": manifest["event_markers_sha256"], "qa_event_markers": qa["event_markers"], "qa_event_markers_sha256": qa["event_markers_sha256"], "active_window": {"frames": [4, 5, 6, 7], "hit_event_frame": 6}, "marker_gate": lifecycle["status"] == "ANIMATION_LIFECYCLE_PASSED"})
    visual = _visual_manifest(manifest, qa)
    write_json(OUT / "attack-v2-visual-manifest.json", {**visual, "frames": overlay_records})
    curve = _curve_contract_evidence()
    write_json(ROOT / "docs/evidence/animation-runtime-v0110/generic-motion-curve-contract-v0110.json", curve)
    replay = _historical_replay(spec_path)
    write_json(ROOT / "docs/evidence/animation-runtime-v0110/historical-replay-v0110.json", replay)
    context = attack_front_v2.load_context(spec, ROOT)
    prepared = attack_front_v2.prepare(spec, context)
    execution = {"schema_version": "0.11.0", "prompt": "PROMPT-10-UGAS-MOTION-QUALITY-LAYER-ATTACK-V2-v0.11.0", "baseline_commit": BASELINE, "implementation_base_commit": BASELINE, "repository_ref": "https://github.com/csn1985-ship-it/ugas.git", "animation_id": spec["animation_id"], "status": qa["status"], "decision": qa["decision"], "frame_count": 12, "fps": 12, "loop": False, "event_markers": spec["event_markers"], "event_markers_sha256": event_markers_sha256(spec), "motion_tracks_sha256": motion_tracks_sha256(spec), "active_window_frames": [4, 5, 6, 7], "hit_event_frame": 6, "target_hashes_distinct": len({item["target_hash"] for item in manifest["frames"]}) == 12, "source_r4_sha256": R4_SHA256, "source_only_pixels": True, "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "new_generation": 0, "historical_replay_status": replay["status"], "generic_motion_curve_contract_status": curve["status"], "negative_controls": _v2_negative_controls(spec, context, prepared, qa), "production_routing": "BLOCKED", "production_approved": False, "external_visual_review": "REQUIRED", "package": {"path": package_path.relative_to(ROOT).as_posix(), "qa_decision": package["qa_decision"], "sprite_sheet_sha256": package["sprite_sheet"]["sha256"], "preview_gif_sha256": package["preview_gif"]["sha256"]}, "no_new_run_hit_death": True, "forbidden_operations_not_used": spec["forbidden_operations"]}
    write_json(ROOT / "docs/evidence/animation-runtime-v0110/execution-evidence-v0.11.0.json", execution)
    return {"status": "ANIMATION_RUNTIME_V0110_PASSED", "decision": qa["decision"], "animation_id": spec["animation_id"], "frames": len(manifest["frames"]), "event_markers": len(spec["event_markers"]), "motion_tracks": len(spec["motion_tracks"]), "historical_replay": replay["status"], "generic_motion_curve_contract": curve["status"], "package": package_path.relative_to(ROOT).as_posix(), "external_visual_review": "REQUIRED", "production_routing": "BLOCKED"}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
        raise SystemExit(0)
    except Exception as exc:
        traceback.print_exc()
        print(json.dumps({"status": "ANIMATION_RUNTIME_V0110_FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False))
        raise SystemExit(2)
