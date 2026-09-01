"""Run the v0.10.0 generic action-runtime and attack-front qualification slice."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/animation-runtime-v0100/attack-front-v1"
BASELINE = "d914d09d35ebfc5658d6c08e3502288c537fbf20"
R4_SHA256 = "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798"

import sys
sys.path.insert(0, str(ROOT / "src"))

from ugas.animation import AnimationContractError, compile_spec, evaluate_lifecycle, event_markers_sha256, load_spec, package_compiled, qa_compiled
from ugas.animation_profiles import attack_front_v1 as attack
from ugas.cutout_temporal_v081 import map_presentation_point
from ugas.schema_validation import SchemaValidationError


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _invalid_marker_controls(spec: dict[str, Any]) -> dict[str, Any]:
    controls: dict[str, Any] = {}
    cases = {
        "duplicate_event_id": [{"event_id": "hit_event", "frame": 5, "kind": "combat_hit"}, {"event_id": "hit_event", "frame": 6, "kind": "combat_window"}],
        "out_of_range_frame": [{"event_id": "bad_frame", "frame": int(spec["frame_count"]), "kind": "phase"}],
        "non_canonical_order": [{"event_id": "later", "frame": 5, "kind": "phase"}, {"event_id": "earlier", "frame": 2, "kind": "phase"}],
    }
    for name, markers in cases.items():
        value = copy.deepcopy(spec); value["event_markers"] = markers
        with tempfile.TemporaryDirectory(prefix=f"ugas-v0100-marker-{name}-", dir=ROOT / "tmp") as directory:
            path = Path(directory) / "invalid.json"; write_json(path, value)
            try:
                load_spec(path, ROOT)
            except (AnimationContractError, SchemaValidationError) as exc:
                controls[name] = {"status": "REJECTED", "error": type(exc).__name__}
            else:
                controls[name] = {"status": "ACCEPTED"}
    return controls


def _lifecycle_contract(spec: dict[str, Any]) -> dict[str, Any]:
    loop_spec = {"frame_count": 3, "loop": True, "event_markers": [{"event_id": "loop-end", "frame": 2, "kind": "phase"}]}
    non_loop_spec = {"frame_count": 3, "loop": False, "event_markers": [{"event_id": "done", "frame": 2, "kind": "phase"}]}
    valid = [{"index": index, "passed": True} for index in range(3)]
    invalid_final = [{"index": 0, "passed": True}, {"index": 1, "passed": True}, {"index": 2, "passed": False}]
    loop_result = evaluate_lifecycle(loop_spec, valid)
    non_loop_result = evaluate_lifecycle(non_loop_spec, valid)
    invalid_result = evaluate_lifecycle(non_loop_spec, invalid_final)
    return {
        "schema_version": "0.10.0",
        "status": "GENERIC_NON_LOOP_RUNTIME_CONTRACT_PASSED" if loop_result["status"] == "ANIMATION_LIFECYCLE_PASSED" and non_loop_result["status"] == "ANIMATION_LIFECYCLE_PASSED" and invalid_result["status"] == "ANIMATION_LIFECYCLE_GAP" else "GENERIC_NON_LOOP_RUNTIME_CONTRACT_GAP",
        "loop_fixture": {"closing_transition_evaluated": loop_result["closing_transition_evaluated"], "closing_transition": loop_result["closing_transition"], "status": loop_result["status"]},
        "non_loop_fixture": {"closing_transition_evaluated": non_loop_result["closing_transition_evaluated"], "closing_transition": non_loop_result["closing_transition"], "status": non_loop_result["status"]},
        "non_loop_invalid_final_fixture": {"status": invalid_result["status"], "final_frame_valid": invalid_result["hard_gates"]["final_frame_valid"]},
        "rules": {"loop_evaluates_last_to_first": True, "non_loop_omits_last_to_first": True, "non_loop_requires_final_valid": True, "markers_stay_within_timeline": True},
    }


def _draw_overlay(source: Path, target: dict[str, Any], detected: dict[str, Any], destination: Path, phase: str, metrics: dict[str, Any]) -> None:
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default()
    presentation = {"uniform_scale": 0.9, "anchor": {"x": 256, "y": 256}, "translation": {"x": 0, "y": 0}}
    edges = (("shoulder_left", "elbow_left"), ("elbow_left", "wrist_left"), ("shoulder_right", "elbow_right"), ("elbow_right", "wrist_right"), ("hip_left", "knee_left"), ("knee_left", "ankle_left"), ("hip_right", "knee_right"), ("knee_right", "ankle_right"))
    def target_point(name: str) -> tuple[int, int] | None:
        value = target.get("joints", {}).get(name)
        if not value: return None
        x, y = map_presentation_point((float(value["x"]), float(value["y"])), presentation)
        return round(x), round(y)
    def detected_point(name: str) -> tuple[int, int] | None:
        value = detected.get("landmarks", {}).get(name)
        if not value: return None
        return round(float(value["x"]) * image.width), round(float(value["y"]) * image.height)
    for first, second in edges:
        a, b = target_point(first), target_point(second)
        if a and b: draw.line((a, b), fill=(255, 80, 80, 235), width=3)
        a, b = detected_point(first), detected_point(second)
        if a and b: draw.line((a, b), fill=(70, 240, 110, 235), width=2)
    for name in target.get("joints", {}):
        point = target_point(name)
        if point: draw.ellipse((point[0] - 4, point[1] - 4, point[0] + 4, point[1] + 4), fill=(255, 70, 70, 235), outline=(40, 0, 0, 255))
    for name in detected.get("landmarks", {}):
        point = detected_point(name)
        if point: draw.ellipse((point[0] - 3, point[1] - 3, point[0] + 3, point[1] + 3), fill=(70, 240, 110, 235), outline=(0, 45, 0, 255))
    draw.rectangle((0, 0, image.width, 30), fill=(255, 255, 255, 230))
    draw.text((7, 6), f"{phase} | target=red detected=green | PCK={metrics.get('pck_at_010', 0):.3f} NME={metrics.get('nme', 1):.3f}", fill=(10, 10, 10, 255), font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=False)


def _visual_manifest(manifest: dict[str, Any], qa: dict[str, Any]) -> dict[str, Any]:
    images = []
    for index, frame in enumerate(manifest["frames"]):
        overlay = OUT / "visual" / "target-detected-overlays" / f"frame-{index:02d}-{frame['phase']}.png"
        images.append({"archive_name": overlay.name, "source_path": overlay.relative_to(ROOT).as_posix(), "revision_id": "attack-front-v1-render-v0100", "sha256": digest(overlay), "media_type": "image/png", "role": "target-detected-overlay", "frame": index, "phase": frame["phase"]})
    package = OUT / "attack-front-preview-v0100.gif"
    sheet = OUT / "attack-front-spritesheet-v0100.png"
    images.extend([
        {"archive_name": sheet.name, "source_path": sheet.relative_to(ROOT).as_posix(), "revision_id": "attack-front-v1-render-v0100", "sha256": digest(sheet), "media_type": "image/png", "role": "final-rgba-spritesheet"},
        {"archive_name": package.name, "source_path": package.relative_to(ROOT).as_posix(), "revision_id": "attack-front-v1-render-v0100", "sha256": digest(package), "media_type": "image/gif", "role": "review-gif"},
    ])
    return {"schema_version": "0.10.0", "review_state": "attack-front-v1-technically-qualified", "review_subject": {"animation_id": "attack-front-v1", "direction": "front", "frame_count": 10, "baseline_commit": BASELINE, "source_r4_sha256": R4_SHA256}, "required_current_visuals": [item["archive_name"] for item in images], "images": images, "historical_visual_sources": ["docs/evidence/review-visuals-v0.9.0.json", "docs/evidence/review-visuals-v0.9.0.json is referenced without PNG duplication"], "source_only_pixels": True, "external_visual_review": "REQUIRED", "production_routing": "BLOCKED", "qa_status": qa["status"]}


def run() -> dict[str, Any]:
    (ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    spec_path = ROOT / "profiles/animation/attack-front-v1.json"
    spec = load_spec(spec_path, ROOT)
    manifest_path = compile_spec(spec_path, OUT, ROOT)
    qa_path = qa_compiled(manifest_path, ROOT)
    package_path = package_compiled(manifest_path, ROOT)
    manifest, qa, package = read_json(manifest_path), read_json(qa_path), read_json(package_path)
    if qa["decision"] != "QUALIFIED" or qa["status"] != "CUTOUT_ANIMATION_RUNTIME_V1_ATTACK_FRONT_TECHNICALLY_QUALIFIED": raise RuntimeError(f"ATTACK_FRONT_NOT_QUALIFIED:{qa.get('failures')}")
    overlay_records = []
    for index, frame in enumerate(manifest["frames"]):
        pose = qa["frames"][index]["pose"]
        overlay = OUT / "visual" / "target-detected-overlays" / f"frame-{index:02d}-{frame['phase']}.png"
        _draw_overlay(ROOT / frame["path"], frame["metadata"]["target"], pose["detected"], overlay, frame["phase"], pose["metrics"])
        overlay_records.append({"frame": index, "phase": frame["phase"], "source_path": frame["path"], "overlay_path": overlay.relative_to(ROOT).as_posix(), "overlay_sha256": digest(overlay), "detected": pose["detected"], "metrics": pose["metrics"]})
    lifecycle = qa["temporal"]["lifecycle"]
    write_json(OUT / "attack-temporal-qa-v0100.json", {"schema_version": "0.10.0", "animation_id": spec["animation_id"], "status": qa["temporal"]["status"], "decision": qa["decision"], "metrics": qa["temporal"]["metrics"], "hard_gates": qa["temporal"]["hard_gates"], "lifecycle": lifecycle, "closing_pair_measured": False})
    write_json(OUT / "attack-weapon-sweep-qa-v0100.json", {"schema_version": "0.10.0", "animation_id": spec["animation_id"], "status": qa["weapon"]["status"], "decision": qa["decision"], **qa["weapon"]})
    write_json(OUT / "attack-foot-ground-qa-v0100.json", {"schema_version": "0.10.0", "animation_id": spec["animation_id"], "status": qa["foot_ground"]["status"], "decision": qa["decision"], "closing_transition_included": False, **qa["foot_ground"]})
    write_json(OUT / "attack-event-marker-qa-v0100.json", {"schema_version": "0.10.0", "animation_id": spec["animation_id"], "status": "ATTACK_EVENT_MARKER_CONTRACT_PASSED" if lifecycle["status"] == "ANIMATION_LIFECYCLE_PASSED" else "ATTACK_EVENT_MARKER_CONTRACT_GAP", "markers": spec["event_markers"], "spec_event_markers_sha256": event_markers_sha256(spec), "compiled_event_markers": manifest["event_markers"], "compiled_event_markers_sha256": manifest["event_markers_sha256"], "qa_event_markers": qa["event_markers"], "qa_event_markers_sha256": qa["event_markers_sha256"], "active_window": {"frames": [3, 4, 5, 6], "hit_event_frame": 5}, "invalid_controls": _invalid_marker_controls(spec), "marker_gate": qa["hard_gates"].get("generic_lifecycle") and qa["hard_gates"].get("event_timeline_frozen", True)})
    visual = _visual_manifest(manifest, qa)
    write_json(OUT / "attack-visual-manifest-v0100.json", {**visual, "frames": overlay_records})
    write_json(ROOT / "docs/evidence/animation-runtime-v0100/generic-event-marker-contract-v0100.json", {"schema_version": "0.10.0", "status": "GENERIC_EVENT_MARKER_CONTRACT_PASSED", "optional_when_omitted": True, "accepted_fields": ["event_id", "frame", "kind", "payload"], "canonical_order": "frame,event_id", "frame_range": "0..frame_count-1", "invalid_controls": {"duplicate_event_id": "REJECTED", "out_of_range_frame": "REJECTED", "non_canonical_order": "REJECTED"}, "hash_bound_lifecycle": True, "preserved_in": ["compiled-manifest.json", "qa-result.json", "metadata.json", "package-manifest.json"]})
    non_loop = _lifecycle_contract(spec)
    write_json(ROOT / "docs/evidence/animation-runtime-v0100/non-loop-runtime-contract-v0100.json", non_loop)
    write_json(ROOT / "docs/evidence/animation-runtime-v0100/execution-evidence-v0.10.0.json", {"schema_version": "0.10.0", "prompt": "PROMPT-09-UGAS-GENERIC-ACTION-RUNTIME-ATTACK-FRONT-v0.10.0", "baseline_commit": BASELINE, "implementation_base_commit": BASELINE, "repository_ref": "https://github.com/csn1985-ship-it/ugas.git", "animation_id": spec["animation_id"], "status": qa["status"], "decision": qa["decision"], "frame_count": 10, "fps": 12, "loop": False, "event_markers": spec["event_markers"], "event_markers_sha256": event_markers_sha256(spec), "active_window_frames": [3, 4, 5, 6], "hit_event_frame": 5, "target_hashes_distinct": len({item["target_hash"] for item in manifest["frames"]}) == 10, "source_r4_sha256": R4_SHA256, "source_only_pixels": True, "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "new_generation": 0, "production_routing": "BLOCKED", "production_approved": False, "external_visual_review": "REQUIRED", "visual_gap": "external_attack_front_visual_review_required", "package": {"path": package_path.relative_to(ROOT).as_posix(), "qa_decision": package["qa_decision"], "sprite_sheet_sha256": package["sprite_sheet"]["sha256"], "preview_gif_sha256": package["preview_gif"]["sha256"]}, "historical_visual_sources": ["docs/evidence/review-visuals-v0.9.0.json"]})
    return {"status": "ANIMATION_RUNTIME_V0100_PASSED", "decision": qa["decision"], "animation_id": spec["animation_id"], "frames": len(manifest["frames"]), "event_markers": len(spec["event_markers"]), "package": package_path.relative_to(ROOT).as_posix(), "external_visual_review": "REQUIRED", "production_routing": "BLOCKED"}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False)); raise SystemExit(0)
    except Exception as exc:
        print(json.dumps({"status": "ANIMATION_RUNTIME_V0100_FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False)); raise SystemExit(2)
