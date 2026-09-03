"""Execute the v0.14.1 HIT_REACTION_FRONT package-integrity correction without rewriting v0.14.0 evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/animation-runtime-v0141"
PACKAGE_OUT = OUT / "hit-front-v1"
FROZEN_V0140 = ROOT / "docs/evidence/animation-runtime-v0140"
SPEC_PATH = ROOT / "profiles/animation/hit-front-v1.json"
RUN_SPEC_PATH = ROOT / "profiles/animation/run-front-v1.json"
IMMUTABLE_BASE = "0beb4c23604f1e45736c3082f99d2e08fa1ac308"
BRANCH_BASE = "ebcf0b587628dcd33c316378fb2815f616172ffa"
REJECTED_REVIEWED_HEAD = "c059e24a4fa215882fac4b36991f7860f185a920"
RUN_APPROVED_HEAD = "f3d68faa5524392e66aee2fc2a450b9da8fa734b"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/validation"))

from ugas.animation import (  # noqa: E402
    AnimationContractError,
    compile_spec,
    decode_gif_timing,
    encode_gif,
    gif_frame_durations_ms,
    gif_timing_within_tolerance,
    inspect_gif_loop_extension,
    load_spec,
    package_compiled,
    qa_compiled,
)
from ugas.animation_profiles import hit_front_v1 as hit_adapter  # noqa: E402
from ugas.animation_profiles.common import load_source_context  # noqa: E402
from ugas.schema_validation import SchemaValidationError  # noqa: E402
from run_animation_runtime_v0140 import (  # noqa: E402
    _approved_assets_untouched as _approved_assets_v0140,
    _semantic_fixture,
)


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


def workdir() -> Path:
    path = ROOT / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def png_rgba_pixel_sha256(path: Path) -> str:
    with Image.open(path) as image:
        return digest_bytes(image.convert("RGBA").tobytes())


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


def gif_frame_pixel_hashes(path: Path) -> list[str]:
    hashes: list[str] = []
    with Image.open(path) as image:
        count = int(getattr(image, "n_frames", 1) or 1)
        for index in range(count):
            image.seek(index)
            hashes.append(digest_bytes(image.convert("RGB").tobytes()))
    return hashes


def _record_v0140_baseline() -> dict[str, Any]:
    frozen_pkg = FROZEN_V0140 / "hit-front-v1"
    manifest = read_json(frozen_pkg / "compiled-manifest.json")
    targets = read_json(FROZEN_V0140 / "hit-front-targets-v0140.json")
    gif_path = frozen_pkg / "hit-front-preview-v0140.gif"
    decoded = decode_gif_timing(gif_path)
    return {
        "schema_version": "0.14.1",
        "rejected_reviewed_head": REJECTED_REVIEWED_HEAD,
        "motion_tracks_sha256": targets["motion_tracks_sha256"],
        "target_hashes": [item["target_joint_sha256"] for item in targets["targets"]],
        "frame_png_file_sha256": [item["rgba_sha256"] for item in manifest["frames"]],
        "frame_rgba_sha256": [png_rgba_pixel_sha256(ROOT / item["path"]) for item in manifest["frames"]],
        "spritesheet_file_sha256": digest(frozen_pkg / "hit-front-spritesheet-v0140.png"),
        "spritesheet_sha256": png_rgba_pixel_sha256(frozen_pkg / "hit-front-spritesheet-v0140.png"),
        "gif_sha256": digest(gif_path),
        "gif_durations_ms": decoded["durations_ms"],
        "gif_frame_pixel_sha256": gif_frame_pixel_hashes(gif_path),
        "gif_loop_extension_present": decoded["loop_extension_present"],
        "gif_loop_count": decoded["loop_count"],
        "defect": "explicit_netscape_loop_count_1_on_nonloop_spec",
    }


def _hit_negative_controls(spec: dict[str, Any], context: dict[str, Any], prepared: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
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

    with tempfile.TemporaryDirectory(prefix="ugas-v0141-package-nc-", dir=workdir()) as directory:
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
    return {"schema_version": "0.14.1", "status": "NC_01_TO_NC_10_PASSED" if passed else "NC_01_TO_NC_10_GAP", "controls": controls, "source": "scripts/validation/run_animation_runtime_v0141.py independent fixture mutations"}


def _save_explicit_loop(frames: list[Image.Image], path: Path, durations: list[int], loop_value: int | None) -> None:
    kwargs: dict[str, Any] = {"format": "GIF", "save_all": True, "append_images": frames[1:], "duration": durations, "disposal": 2, "optimize": False}
    if loop_value is not None:
        kwargs["loop"] = loop_value
    frames[0].save(path, **kwargs)


def _loop_negative_controls(hit_spec: dict[str, Any], run_spec: dict[str, Any]) -> dict[str, Any]:
    frames = [Image.new("RGB", (16, 16), (40 + index * 20, 12, 24)) for index in range(int(hit_spec["frame_count"]))]
    durations = gif_frame_durations_ms(hit_spec)
    run_frames = [Image.new("RGB", (16, 16), (20, 40 + index * 15, 18)) for index in range(int(run_spec["frame_count"]))]
    run_durations = gif_frame_durations_ms(run_spec)
    controls: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="ugas-v0141-loop-nc-", dir=workdir()) as directory:
        temp = Path(directory)
        cases = [
            ("NC-LOOP-01_infinite_extension_on_nonloop", hit_spec, frames, durations, 0, "REJECTED"),
            ("NC-LOOP-02_explicit_loop1_on_nonloop", hit_spec, frames, durations, 1, "REJECTED"),
            ("NC-LOOP-03_no_extension_on_nonloop", hit_spec, frames, durations, None, "PASSED"),
            ("NC-LOOP-04_missing_extension_on_loop", run_spec, run_frames, run_durations, None, "REJECTED"),
            ("NC-LOOP-05_infinite_extension_on_loop", run_spec, run_frames, run_durations, 0, "PASSED"),
        ]
        for name, spec, gif_frames, gif_durations, loop_value, expected in cases:
            path = temp / f"{name}.gif"
            if expected == "PASSED" and loop_value == 0:
                encode_gif(gif_frames, path, gif_durations, loop=True)
            elif expected == "PASSED" and loop_value is None:
                encode_gif(gif_frames, path, gif_durations, loop=False)
            else:
                _save_explicit_loop(gif_frames, path, gif_durations, loop_value)
            decoded = decode_gif_timing(path)
            check = gif_timing_within_tolerance(spec, decoded)
            actual = "PASSED" if check["status"] == "GIF_TIMING_PASSED" else "REJECTED"
            controls[name] = {
                "expected": expected,
                "status": actual,
                "match": actual == expected,
                "encoded_with_pillow_loop": loop_value,
                "inspect": inspect_gif_loop_extension(path),
                "decoded": decoded,
                "hard_gates": check["hard_gates"],
                "gif_sha256": digest(path),
            }
    passed = all(item["match"] for item in controls.values())
    return {"schema_version": "0.14.1", "status": "NC_LOOP_01_TO_05_PASSED" if passed else "NC_LOOP_01_TO_05_GAP", "controls": controls, "source": "real encoded GIF fixtures after save"}


def _run_front_loop_regression(run_spec: dict[str, Any]) -> dict[str, Any]:
    frozen_frames = sorted((ROOT / "docs/evidence/animation-runtime-v0131/run-front-v1").glob("frame-*.png"))
    if len(frozen_frames) != int(run_spec["frame_count"]):
        raise RuntimeError("run_front_frozen_frames_missing")
    from ugas.animation import _checkerboard

    gif_frames = [_checkerboard(Image.open(path).convert("RGBA")).convert("RGB") for path in frozen_frames]
    durations = gif_frame_durations_ms(run_spec)
    with tempfile.TemporaryDirectory(prefix="ugas-v0141-run-loop-", dir=workdir()) as directory:
        gif_path = Path(directory) / "run-front-loop-regression.gif"
        encode_gif(gif_frames, gif_path, durations, loop=True)
        decoded = decode_gif_timing(gif_path)
        check = gif_timing_within_tolerance(run_spec, decoded)
    return {
        "schema_version": "0.14.1",
        "status": "RUN_FRONT_LOOP_REGRESSION_PASSED" if check["status"] == "GIF_TIMING_PASSED" and decoded["loop_extension_present"] is True and decoded["loop_count"] == 0 else "RUN_FRONT_LOOP_REGRESSION_GAP",
        "decoded": decoded,
        "hard_gates": check["hard_gates"],
        "source_frames": [relative(path) for path in frozen_frames],
        "v0131_evidence_rewritten": False,
    }


def _visual_preservation(baseline: dict[str, Any], manifest: dict[str, Any], package: dict[str, Any], prepared: dict[str, Any], gif_path: Path) -> dict[str, Any]:
    new_frame_pixels = [png_rgba_pixel_sha256(ROOT / item["path"]) for item in manifest["frames"]]
    new_frame_files = [item["rgba_sha256"] for item in manifest["frames"]]
    new_targets = [item["target_joint_sha256"] for item in prepared["targets"]]
    sheet_path = ROOT / package["sprite_sheet"]["path"]
    new_sheet_pixels = png_rgba_pixel_sha256(sheet_path)
    new_sheet_file = package["sprite_sheet"]["sha256"]
    new_gif = decode_gif_timing(gif_path)
    new_gif_pixels = gif_frame_pixel_hashes(gif_path)
    comparisons = {
        "frame_rgba_sha256_identical": new_frame_pixels == baseline["frame_rgba_sha256"],
        "target_hashes_identical": new_targets == baseline["target_hashes"],
        "motion_tracks_sha256_identical": prepared["track_hash"] == baseline["motion_tracks_sha256"],
        "spritesheet_sha256_identical": new_sheet_pixels == baseline["spritesheet_sha256"],
        "gif_frame_pixel_sequence_identical": new_gif_pixels == baseline["gif_frame_pixel_sha256"],
        "gif_durations_identical": new_gif["durations_ms"] == baseline["gif_durations_ms"],
        "gif_repeat_extension_changed": (not new_gif["loop_extension_present"]) and baseline["gif_loop_extension_present"] is True,
        "frame_png_file_sha256_identical": new_frame_files == baseline.get("frame_png_file_sha256"),
        "spritesheet_file_sha256_identical": new_sheet_file == baseline.get("spritesheet_file_sha256"),
    }
    content_keys = (
        "frame_rgba_sha256_identical",
        "target_hashes_identical",
        "motion_tracks_sha256_identical",
        "spritesheet_sha256_identical",
        "gif_frame_pixel_sequence_identical",
        "gif_durations_identical",
    )
    content_preserved = all(comparisons[key] for key in content_keys)
    return {
        "schema_version": "0.14.1",
        "status": "HIT_VISUAL_PRESERVED" if content_preserved else "VISUAL_REVIEW_INVALIDATED",
        "comparisons": comparisons,
        "baseline": {key: baseline[key] for key in ("motion_tracks_sha256", "target_hashes", "frame_rgba_sha256", "spritesheet_sha256", "gif_durations_ms", "gif_loop_extension_present", "gif_loop_count")},
        "corrected": {
            "motion_tracks_sha256": prepared["track_hash"],
            "target_hashes": new_targets,
            "frame_rgba_sha256": new_frame_pixels,
            "spritesheet_sha256": new_sheet_pixels,
            "gif_durations_ms": new_gif["durations_ms"],
            "gif_loop_extension_present": new_gif["loop_extension_present"],
            "gif_loop_count": new_gif["loop_count"],
        },
        "png_container_note": "Decoded RGBA pixels are authoritative. PNG file bytes may differ across Pillow/zlib platforms.",
        "invalidated": not content_preserved,
    }


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
    sheet_path = OUT / "hit-front-phase-markers-v0141.png"
    sheet.save(sheet_path, format="PNG", optimize=False)
    return sheet_path, marker_records


def run() -> dict[str, Any]:
    (ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if not FROZEN_V0140.is_dir():
        raise RuntimeError("v0140_evidence_missing")
    baseline = _record_v0140_baseline()
    if PACKAGE_OUT.exists():
        shutil.rmtree(PACKAGE_OUT)
    implementation_base = _git_rev(IMMUTABLE_BASE)
    if implementation_base != IMMUTABLE_BASE:
        raise RuntimeError("implementation_base_mismatch")
    branch_base = _git_rev(BRANCH_BASE)
    evidence_head = _git_rev("HEAD")
    merge_base = _merge_base(IMMUTABLE_BASE, "HEAD")
    if merge_base != IMMUTABLE_BASE:
        raise RuntimeError(f"merge_base_must_be_immutable_v0124:{merge_base}")
    spec = load_spec(SPEC_PATH, ROOT)
    run_spec = load_spec(RUN_SPEC_PATH, ROOT)
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
    if decoded_gif["loop_extension_present"] is not False or decoded_gif["loop_count"] is not None:
        raise RuntimeError(f"NONLOOP_GIF_STILL_HAS_EXTENSION:{decoded_gif}")
    preservation = _visual_preservation(baseline, manifest, package, prepared, gif_path)
    if preservation["status"] == "VISUAL_REVIEW_INVALIDATED":
        write_json(OUT / "hit-front-visual-preservation-v0141.json", preservation)
        raise RuntimeError("VISUAL_REVIEW_INVALIDATED")
    negative = _hit_negative_controls(spec, context, prepared, manifest_path)
    loop_nc = _loop_negative_controls(spec, run_spec)
    run_loop = _run_front_loop_regression(run_spec)
    write_json(OUT / "hit-front-targets-v0141.json", {"schema_version": "0.14.1", "animation_id": spec["animation_id"], "phase_order": list(hit_adapter.PHASES), "targets": prepared["targets"], "target_hashes": [target["target_joint_sha256"] for target in prepared["targets"]], "key_pose_bindings": spec["key_pose_bindings"], "motion_tracks_sha256": prepared["track_hash"], "parameters_frozen_before_render": True, "source_only_pixels": True})
    write_json(OUT / "hit-front-frame-qa-v0141.json", {"schema_version": "0.14.1", "animation_id": spec["animation_id"], "status": qa["status"], "decision": qa["decision"], "frames": qa["frames"]})
    write_json(OUT / "hit-front-temporal-qa-v0141.json", {"schema_version": "0.14.1", "animation_id": spec["animation_id"], "status": qa["temporal"]["status"], "metrics": qa["temporal"]["metrics"], "hard_gates": qa["temporal"]["hard_gates"], "recoil": qa["temporal"]["recoil"], "weapon": qa["temporal"]["weapon"]})
    write_json(OUT / "hit-front-foot-ground-qa-v0141.json", {"schema_version": "0.14.1", "animation_id": spec["animation_id"], "status": qa["foot_ground"]["status"], "frames": qa["foot_ground"]["frames"], "contact": qa["foot_ground"]["contact"], "ground_reference_y": qa["foot_ground"].get("ground_reference_y")})
    write_json(OUT / "hit-front-body-mechanics-qa-v0141.json", {"schema_version": "0.14.1", "animation_id": spec["animation_id"], **qa["body_mechanics"]})
    write_json(OUT / "hit-front-weapon-qa-v0141.json", {"schema_version": "0.14.1", "animation_id": spec["animation_id"], **qa["weapon"]})
    write_json(OUT / "hit-front-continuity-qa-v0141.json", {"schema_version": "0.14.1", "animation_id": spec["animation_id"], "status": "HIT_CONTINUITY_INTERPOLATION_PASSED" if qa["temporal"]["hard_gates"]["angular_continuity"] and qa["temporal"]["hard_gates"]["angular_acceleration_continuity"] and qa["temporal"]["hard_gates"]["nonfinite_and_gap_free"] else "HIT_CONTINUITY_INTERPOLATION_GAP", "gates": {key: value for key, value in qa["temporal"]["hard_gates"].items() if key in {"angular_continuity", "angular_acceleration_continuity", "nonfinite_and_gap_free", "foreground_height_stability"}}, "metrics": {key: value for key, value in qa["temporal"]["metrics"].items() if "angle" in key or "height" in key}})
    write_json(OUT / "hit-front-gate-negative-controls-v0141.json", negative)
    write_json(OUT / "hit-front-loop-negative-controls-v0141.json", loop_nc)
    write_json(OUT / "run-front-loop-regression-v0141.json", run_loop)
    assets = _approved_assets_v0140(IMMUTABLE_BASE)
    assets = {**assets, "schema_version": "0.14.1"}
    write_json(OUT / "approved-assets-untouched-v0141.json", assets)
    write_json(OUT / "hit-front-gif-timing-v0141.json", {"schema_version": "0.14.1", **gif_check, "package_metadata": {"fps": package.get("fps"), "per_frame_duration_ms": package.get("per_frame_duration_ms"), "gif_encoded_frame_durations_ms": package.get("gif_encoded_frame_durations_ms"), "gif_total_cycle_ms": package.get("gif_total_cycle_ms"), "gif_effective_fps": package.get("gif_effective_fps"), "gif_loop_extension_present": package.get("gif_loop_extension_present"), "gif_loop_count": package.get("gif_loop_count")}})
    write_json(OUT / "hit-front-gif-loop-semantics-v0141.json", {"schema_version": "0.14.1", "status": "GIF_LOOP_SEMANTICS_PASSED", "inspect": inspect_gif_loop_extension(gif_path), "decoded": decoded_gif, "spec_loop": spec["loop"], "rejected_v0140_gif": {"path": "docs/evidence/animation-runtime-v0140/hit-front-v1/hit-front-preview-v0140.gif", "inspect": inspect_gif_loop_extension(FROZEN_V0140 / "hit-front-v1/hit-front-preview-v0140.gif"), "decoded": decode_gif_timing(FROZEN_V0140 / "hit-front-v1/hit-front-preview-v0140.gif")}})
    write_json(OUT / "hit-front-visual-preservation-v0141.json", preservation)
    marker_sheet, marker_records = _marker_sheet(manifest, qa)
    visual_images = [{"frame": index, "phase": item["phase"], "source_path": item["path"], "rgba_sha256": item["rgba_sha256"], "target_hash": item["target_hash"], "media_type": "image/png", "role": "compiled-source-only-frame", "events": [event for event in spec["event_markers"] if int(event["frame"]) == index]} for index, item in enumerate(manifest["frames"])]
    visual_images.extend([{"path": package["preview_gif"]["path"], "sha256": package["preview_gif"]["sha256"], "media_type": "image/gif", "role": "review-gif", "events": spec["event_markers"], "gif_encoded_frame_durations_ms": decoded_gif["durations_ms"], "gif_total_cycle_ms": decoded_gif["total_cycle_ms"], "gif_effective_fps": decoded_gif["effective_fps"], "gif_loop_extension_present": decoded_gif["loop_extension_present"], "gif_loop_count": decoded_gif["loop_count"]}, {"path": package["sprite_sheet"]["path"], "sha256": package["sprite_sheet"]["sha256"], "media_type": "image/png", "role": "compiled-rgba-spritesheet", "events": spec["event_markers"]}, {"path": relative(marker_sheet), "sha256": digest(marker_sheet), "media_type": "image/png", "role": "phase-marker-review-sheet", "events": spec["event_markers"]}])
    visual_manifest = {"schema_version": "0.14.1", "review_state": "hit-front-v1-package-integrity-correction", "review_subject": {"animation_id": spec["animation_id"], "direction": spec["direction"], "frame_count": spec["frame_count"], "fps": spec["fps"], "loop": spec["loop"], "source_r4_sha256": spec["provenance"]["source_sha256"]}, "event_markers": spec["event_markers"], "event_markers_sha256": manifest["event_markers_sha256"], "motion_tracks_sha256": manifest["motion_tracks_sha256"], "gif_timing": decoded_gif, "images": visual_images, "marker_frames": marker_records, "source_only_pixels": True, "external_visual": "APPROVED_PILOT_CONTENT_PENDING_PACKAGE_INTEGRITY", "production_routing": "BLOCKED", "package_manifest": {"path": relative(package_path), "sha256": digest(package_path)}}
    write_json(OUT / "hit-front-visual-manifest-v0141.json", visual_manifest)
    execution = {
        "schema_version": "0.14.1",
        "prompt": "PROMPT-CORRETIVO-UGAS-v0.14.1-NONLOOP-GIF-PACKAGE-INTEGRITY",
        "implementation_base_commit": implementation_base,
        "branch_base_commit": branch_base,
        "rejected_reviewed_head": REJECTED_REVIEWED_HEAD,
        "evidence_head_sha": evidence_head,
        "run_front_approved_head_sha": RUN_APPROVED_HEAD,
        "animation_id": spec["animation_id"],
        "status": "HIT_REACTION_FRONT_PACKAGE_INTEGRITY_TECHNICALLY_QUALIFIED",
        "decision": qa["decision"],
        "frame_count": spec["frame_count"],
        "fps": spec["fps"],
        "loop": spec["loop"],
        "gif_encoded_frame_durations_ms": decoded_gif["durations_ms"],
        "gif_total_cycle_ms": decoded_gif["total_cycle_ms"],
        "gif_effective_fps": decoded_gif["effective_fps"],
        "gif_loop_extension_present": decoded_gif["loop_extension_present"],
        "gif_loop_count": decoded_gif["loop_count"],
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
        "external_visual": "APPROVED_PILOT_CONTENT_PENDING_PACKAGE_INTEGRITY",
        "hit_reaction_front_visual_content": "APPROVED_PILOT_CONTENT_PENDING_PACKAGE_INTEGRITY_REVIEW",
        "negative_controls": negative["status"],
        "loop_negative_controls": loop_nc["status"],
        "run_front_loop_regression": run_loop["status"],
        "visual_preservation": preservation["status"],
        "approved_assets_untouched": assets["status"],
        "package": {"path": relative(package_path), "sha256": digest(package_path), "preview_gif": package["preview_gif"], "sprite_sheet": package["sprite_sheet"]},
        "review_artifacts": {"visual_manifest": relative(OUT / "hit-front-visual-manifest-v0141.json"), "phase_marker_sheet": relative(marker_sheet), "negative_controls": relative(OUT / "hit-front-gate-negative-controls-v0141.json"), "loop_negative_controls": relative(OUT / "hit-front-loop-negative-controls-v0141.json")},
        "historical_v0140_preserved": True,
        "historical_v0131_preserved": True,
        "historical_v0130_preserved": True,
        "next_capability_started": False,
        "executor_does_not_claim_visual_approval": True,
        "github_review_manifest_is_authority_for_final_head": True,
    }
    write_json(OUT / "execution-evidence-v0.14.1.json", execution)
    if negative["status"] != "NC_01_TO_NC_10_PASSED" or loop_nc["status"] != "NC_LOOP_01_TO_05_PASSED" or run_loop["status"] != "RUN_FRONT_LOOP_REGRESSION_PASSED" or assets["status"] != "APPROVED_ASSETS_UNTOUCHED":
        raise RuntimeError(f"V0141_GATES_FAILED:{negative['status']}:{loop_nc['status']}:{run_loop['status']}:{assets['status']}")
    return {"status": "ANIMATION_RUNTIME_V0141_PASSED", "decision": qa["decision"], "animation_id": spec["animation_id"], "frames": len(manifest["frames"]), "package": relative(package_path), "preview_gif": package["preview_gif"]["path"], "negative_controls": negative["status"], "loop_negative_controls": loop_nc["status"], "run_front_loop_regression": run_loop["status"], "visual_preservation": preservation["status"], "approved_assets": assets["status"], "gif_loop_extension_present": decoded_gif["loop_extension_present"], "gif_loop_count": decoded_gif["loop_count"], "external_visual": "APPROVED_PILOT_CONTENT_PENDING_PACKAGE_INTEGRITY", "production_routing": "BLOCKED"}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
        raise SystemExit(0)
    except Exception as exc:
        print(json.dumps({"status": "ANIMATION_RUNTIME_V0141_FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False))
        raise SystemExit(2)
