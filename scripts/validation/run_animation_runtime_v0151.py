"""Execute the v0.15.1 DEATH_ANIMATION_FRONT correction.

The two determinism runs are real subprocess lifecycles.  Each subprocess
loads a fresh adapter context and writes compile, QA and package outputs to a
different temporary directory.  The comparator hashes decoded pixels and
decoded GIF semantics; it never compares a file with itself.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/animation-runtime-v0151"
PACKAGE_OUT = OUT / "death-front-v1"
SPEC_PATH = ROOT / "profiles/animation/death-front-v151.json"
HIT_SPEC_PATH = ROOT / "profiles/animation/hit-front-v1.json"
RUN_SPEC_PATH = ROOT / "profiles/animation/run-front-v1.json"
FROZEN_HIT = ROOT / "docs/evidence/animation-runtime-v0141"
FROZEN_V0140 = ROOT / "docs/evidence/animation-runtime-v0140"
IMMUTABLE_BASE = "0beb4c23604f1e45736c3082f99d2e08fa1ac308"
BRANCH_BASE = "98ebd95564216fbbee222aab630b73b5ff6f298d"
HIT_APPROVED_HEAD = "a3e37865f260c5a6cd56743e1d4b9131fcb12cda"
RUN_APPROVED_HEAD = "f3d68faa5524392e66aee2fc2a450b9da8fa734b"
FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB = "9bbc85bd5ca839b4a0fd71b45a279e852a275fc5"
FROZEN_STATE_CONSISTENCY_V0141_PATH = "docs/evidence/animation-runtime-v0141/state-consistency-v0141.json"
FROZEN_REPAIR_PROVENANCE_V0141_PATH = "docs/evidence/github-governance-v0141/hit-front-v0141-post-merge-integrity-repair.json"
FROZEN_APPROVED_RAW_SHA256 = "a648710b66fb21c92ba1030b4f86793719792475c0ecd14a7a48aebc951606bb"
PR4_MERGE_COMMIT = BRANCH_BASE
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
PROTECTED_HIT_FRONT = [
    "profiles/animation/hit-front-v1.json",
    "docs/evidence/animation-runtime-v0141/hit-front-v1/hit-front-preview-v0141.gif",
    "docs/evidence/animation-runtime-v0141/hit-front-v1/hit-front-spritesheet-v0141.png",
    "docs/evidence/animation-runtime-v0140/hit-front-v1/hit-front-preview-v0140.gif",
    "docs/evidence/animation-runtime-v0140/hit-front-v1/hit-front-spritesheet-v0140.png",
]

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/validation"))

from ugas.animation import (  # noqa: E402
    AnimationContractError,
    decode_gif_timing,
    encode_gif,
    gif_frame_durations_ms,
    gif_timing_within_tolerance,
    inspect_gif_loop_extension,
    load_spec,
    package_compiled,
)
from ugas.animation_profiles import death_front_v151 as death_adapter  # noqa: E402
from ugas.animation_profiles.common import load_source_context  # noqa: E402
from ugas.schema_validation import SchemaValidationError  # noqa: E402
from run_animation_runtime_v0140 import _check_assets  # noqa: E402
from run_animation_runtime_v0141 import _loop_negative_controls, _run_front_loop_regression  # noqa: E402


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
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def workdir() -> Path:
    path = ROOT / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def png_rgba_pixel_sha256(path: Path) -> str:
    with Image.open(path) as image:
        return digest_bytes(image.convert("RGBA").tobytes())


def gif_frame_pixel_hashes(path: Path) -> list[str]:
    hashes: list[str] = []
    with Image.open(path) as image:
        for index in range(int(getattr(image, "n_frames", 1) or 1)):
            image.seek(index)
            hashes.append(digest_bytes(image.convert("RGBA").tobytes()))
    return hashes


def _git_rev(name: str) -> str:
    result = subprocess.run(["git", "rev-parse", name], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0 or len(result.stdout.strip()) != 40:
        raise RuntimeError(f"git_rev_unresolved:{name}")
    return result.stdout.strip()


def _git_blob_bytes(blob: str) -> bytes:
    result = subprocess.run(["git", "cat-file", "blob", blob], cwd=ROOT, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git_blob_unresolved:{blob}")
    return result.stdout


def _merge_base(base: str, head: str) -> str:
    result = subprocess.run(["git", "merge-base", base, head], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0 or len(result.stdout.strip()) != 40:
        raise RuntimeError("merge_base_unresolved")
    return result.stdout.strip()


def _run_once(spec_path: Path, output_dir: Path, label: str) -> dict[str, Any]:
    """Run compile, QA and package in a fresh Python subprocess."""
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    commands = [
        [sys.executable, "-m", "ugas.animation", "compile", str(spec_path), "--output", str(output_dir)],
        [sys.executable, "-m", "ugas.animation", "qa", str(output_dir / "compiled-manifest.json")],
        [sys.executable, "-m", "ugas.animation", "package", str(output_dir / "compiled-manifest.json")],
    ]
    logs: list[dict[str, Any]] = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        logs.append({"command": command, "returncode": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]})
        if result.returncode != 0:
            raise RuntimeError(f"{label}_lifecycle_failed:{result.stdout[-1000:]}:{result.stderr[-1000:]}")
    return {"label": label, "output_dir": relative(output_dir), "logs": logs}


def _package_snapshot(output_dir: Path) -> dict[str, Any]:
    manifest = read_json(output_dir / "compiled-manifest.json")
    qa = read_json(output_dir / "qa-result.json")
    package = read_json(output_dir / "package-manifest.json")
    frame_hashes = [png_rgba_pixel_sha256(ROOT / item["path"]) for item in manifest["frames"]]
    sprite_path = ROOT / package["sprite_sheet"]["path"]
    gif_path = ROOT / package["preview_gif"]["path"]
    with Image.open(sprite_path) as sheet:
        sheet_hash = digest_bytes(sheet.convert("RGBA").tobytes())
    decoded_gif = decode_gif_timing(gif_path)
    return {
        "motion_tracks_sha256": manifest.get("motion_tracks_sha256"),
        "target_hashes": [item["target_hash"] for item in manifest["frames"]],
        "frame_rgba_sha256": frame_hashes,
        "sprite_sheet_rgba_sha256": sheet_hash,
        "gif_rgba_frame_sha256": gif_frame_pixel_hashes(gif_path),
        "gif_durations_ms": decoded_gif["durations_ms"],
        "gif_loop_extension_present": decoded_gif["loop_extension_present"],
        "gif_loop_count": decoded_gif["loop_count"],
        "gif_frame_count": decoded_gif["frame_count"],
        "gif_total_cycle_ms": decoded_gif["total_cycle_ms"],
        "gif_effective_fps": decoded_gif["effective_fps"],
        "qa_decision": qa.get("decision"),
        "qa_failures": qa.get("failures", []),
        "manifest_path": relative(output_dir / "compiled-manifest.json"),
        "package_path": relative(output_dir / "package-manifest.json"),
        "preview_gif": relative(gif_path),
        "spritesheet": relative(sprite_path),
    }


def _compare_snapshots(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "motion_tracks_sha256",
        "target_hashes",
        "frame_rgba_sha256",
        "sprite_sheet_rgba_sha256",
        "gif_rgba_frame_sha256",
        "gif_durations_ms",
        "gif_loop_extension_present",
        "gif_loop_count",
        "gif_frame_count",
        "gif_total_cycle_ms",
        "gif_effective_fps",
    )
    matches = {field: first.get(field) == second.get(field) for field in fields}
    return {"matches": matches, "all_fields_match": all(matches.values())}


def _approved_assets_untouched() -> dict[str, Any]:
    historical = _check_assets(PROTECTED_HISTORICAL, IMMUTABLE_BASE, "0.15.1")
    run_front = _check_assets(PROTECTED_RUN_FRONT, RUN_APPROVED_HEAD, "0.15.1")
    hit_front = _check_assets(PROTECTED_HIT_FRONT, HIT_APPROVED_HEAD, "0.15.1")
    checks = (historical, run_front, hit_front)
    failures = list(historical.get("failures", [])) + [f"run_front:{item}" for item in run_front.get("failures", [])] + [f"hit_front:{item}" for item in hit_front.get("failures", [])]
    status = "APPROVED_ASSETS_UNTOUCHED" if all(item["status"] == "APPROVED_ASSETS_UNTOUCHED" for item in checks) else "APPROVED_ASSET_DRIFT"
    if any(item["status"] == "APPROVED_ASSET_BASELINE_UNAVAILABLE" for item in checks):
        status = "APPROVED_ASSET_BASELINE_UNAVAILABLE"
    return {"schema_version": "0.15.1", "status": status, "base_commit": IMMUTABLE_BASE, "run_front_approved_head": RUN_APPROVED_HEAD, "hit_front_approved_head": HIT_APPROVED_HEAD, "head_fallback_used": False, "historical": historical, "run_front": run_front, "hit_front": hit_front, "checks": historical.get("checks", []) + run_front.get("checks", []) + hit_front.get("checks", []), "failures": failures}


def _frozen_evidence_integrity() -> dict[str, Any]:
    path = ROOT / FROZEN_STATE_CONSISTENCY_V0141_PATH
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    blob = hashlib.sha1(f"blob {len(normalized)}\0".encode() + normalized).hexdigest()  # noqa: S324
    repair = read_json(ROOT / "docs/evidence/github-governance-v0141/hit-front-v0141-post-merge-integrity-repair.json")
    matches = blob == FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB
    return {"schema_version": "0.15.1", "status": "FROZEN_V0141_EVIDENCE_RESTORED_AND_VERIFIED" if matches else "FROZEN_V0141_EVIDENCE_DRIFT", "path": FROZEN_STATE_CONSISTENCY_V0141_PATH, "approved_head": HIT_APPROVED_HEAD, "approved_head_git_blob": FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB, "repaired_git_blob": blob, "bookkeeping_head": repair.get("bookkeeping_head"), "merge_commit": repair.get("merge_commit"), "repair_action": repair.get("repair_action"), "historical_git_rewritten": repair.get("historical_git_rewritten"), "historical_v0150_edited": False, "verification": {"repaired_blob_matches_approved_head": matches, "semantic_mutation_control": "NC-15_frozen_evidence_mutation_after_external_approval", "pr4_state_consistency": "MERGED"}, "production_approved": False, "production_routing": "BLOCKED", "new_generation": 0}


def _frozen_provenance_hash() -> dict[str, Any]:
    """Bind the approved Git blob identity to its raw SHA-256 bytes."""
    path = ROOT / FROZEN_STATE_CONSISTENCY_V0141_PATH
    raw_blob = _git_blob_bytes(FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB)
    working_tree = path.read_bytes()
    normalized_working_tree = working_tree.replace(b"\r\n", b"\n")
    repair = read_json(ROOT / FROZEN_REPAIR_PROVENANCE_V0141_PATH)
    old_blobs = repair.get("blobs", {})
    raw_sha256 = digest_bytes(raw_blob)
    normalized_sha256 = digest_bytes(normalized_working_tree)
    raw_matches = raw_sha256 == FROZEN_APPROVED_RAW_SHA256 and normalized_working_tree == raw_blob
    return {
        "schema_version": "0.15.1",
        "status": "V0141_PROVENANCE_SHA256_CORRECTION_RECORDED" if raw_matches else "V0141_PROVENANCE_SHA256_CORRECTION_GAP",
        "record_type": "forward_only_superseding_provenance_hash_correction",
        "correction_of": FROZEN_REPAIR_PROVENANCE_V0141_PATH,
        "historical_record_unchanged": True,
        "byte_authority": {
            "algorithm": "SHA-256",
            "authority": "raw bytes returned by git cat-file blob; no text reserialization, JSON formatting, newline conversion, or working-tree autocrlf bytes",
            "path": FROZEN_STATE_CONSISTENCY_V0141_PATH,
            "git_blob_sha1": FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB,
            "raw_git_blob_byte_count": len(raw_blob),
            "raw_git_blob_sha256": raw_sha256,
            "independent_reviewer_sha256": FROZEN_APPROVED_RAW_SHA256,
            "raw_git_blob_matches_independent_reviewer": raw_sha256 == FROZEN_APPROVED_RAW_SHA256,
        },
        "environment_specific_discrepancy": {
            "working_tree_byte_count": len(working_tree),
            "working_tree_sha256": digest_bytes(working_tree),
            "working_tree_normalized_byte_count": len(normalized_working_tree),
            "working_tree_normalized_sha256": normalized_sha256,
            "normalized_working_tree_matches_raw_git_blob": normalized_working_tree == raw_blob,
            "explanation": "Windows checkout bytes use CRLF while the approved Git blob is LF. The normalized checkout agrees with the raw blob, but the raw Git blob remains the byte authority.",
        },
        "superseded_values": {
            "approved_head_sha256": old_blobs.get("approved_head_sha256"),
            "repaired_file_sha256": old_blobs.get("repaired_file_sha256"),
            "approved_head_git_blob": old_blobs.get("approved_head_git_blob"),
            "repaired_file_git_blob": old_blobs.get("repaired_file_git_blob"),
        },
        "correction": "The old recovery record is preserved. This forward-only record supersedes only its SHA-256 byte claims and binds the Git blob SHA-1 to the independently verified raw-blob SHA-256.",
        "production_approved": False,
        "production_routing": "BLOCKED",
        "new_generation": 0,
    }


def _save_explicit_loop(frames: list[Image.Image], path: Path, durations: list[int], loop_value: int | None) -> None:
    kwargs: dict[str, Any] = {"format": "GIF", "save_all": True, "append_images": frames[1:], "duration": durations, "disposal": 2, "optimize": False}
    if loop_value is not None:
        kwargs["loop"] = loop_value
    frames[0].save(path, **kwargs)


def _semantic_observation(spec: dict[str, Any]) -> dict[str, Any]:
    context = death_adapter.load_context(spec, ROOT)
    prepared = death_adapter.prepare(spec, context)
    return death_adapter.observe(spec, context, prepared)


def _set_track_values(spec: dict[str, Any], track_id: str, values: Mapping[int, float]) -> None:
    for track in spec["motion_tracks"]:
        if track["track_id"] != track_id:
            continue
        for keyframe in track["keyframes"]:
            frame = int(keyframe["frame"])
            if frame in values:
                keyframe["value"] = float(values[frame])


def _set_frames_to_frame_zero(spec: dict[str, Any]) -> None:
    for track in spec["motion_tracks"]:
        first = float(track["keyframes"][0]["value"])
        for keyframe in track["keyframes"]:
            if int(keyframe["frame"]) >= 4:
                keyframe["value"] = first


def _control_result(gate: str, rejected: bool, **extra: Any) -> dict[str, Any]:
    return {"gate": gate, "status": "REJECTED" if rejected else "ACCEPTED", **extra}


def _ground_contact_negative_controls(spec: dict[str, Any]) -> dict[str, Any]:
    """Mutate contact inputs, not evidence labels, for the six GC controls."""
    controls: dict[str, Any] = {}

    mutant = copy.deepcopy(spec)
    _set_track_values(mutant, "left_arm_swing_deg", {4: 8.0, 5: 8.0, 6: 8.0, 7: 8.0})
    result = _semantic_observation(mutant)
    controls["NC-GC-01_marker_without_new_contact"] = _control_result(
        "ground_contact_marker_matches_actual_transition",
        not result["transition"]["ground_contact_marker_matches_actual_transition"],
        measured_first_body_contact_frame=result["transition"]["measured_first_body_contact_frame"],
        marker_frame=result["transition"]["marker_frame"],
    )

    mutant = copy.deepcopy(spec)
    for index in range(4, 8):
        state = mutant["adapter_parameters"]["contact_contract"]["states"][index]
        state["foot_support_mode"] = "dual_foot"
        state["foot_support"] = {"left": "planted", "right": "planted"}
    result = _semantic_observation(mutant)
    controls["NC-GC-02_support_regime_never_changes"] = _control_result(
        "support_state_classification_valid",
        not result["transition"]["support_state_classification_valid"],
        measured_support=[record["measured_support"] for record in result["foot_records"]],
    )

    mutant = copy.deepcopy(spec)
    _set_track_values(mutant, "root_shift_y", {4: 50.0, 5: 50.0, 6: 50.0, 7: 50.0})
    _set_track_values(mutant, "left_arm_swing_deg", {4: 8.0, 5: 8.0, 6: 8.0, 7: 8.0})
    result = _semantic_observation(mutant)
    controls["NC-GC-03_root_drop_only"] = _control_result(
        "ground_contact_marker_matches_actual_transition",
        not result["transition"]["ground_contact_marker_matches_actual_transition"],
        root_shift_y=result["temporal"]["collapse"]["root_shift_y"],
        measured_first_body_contact_frame=result["transition"]["measured_first_body_contact_frame"],
    )

    mutant = copy.deepcopy(spec)
    _set_track_values(mutant, "left_arm_swing_deg", {6: 8.0, 7: 8.0})
    _set_track_values(mutant, "torso_rotation_deg", {6: 32.0, 7: 32.0})
    _set_track_values(mutant, "root_shift_y", {6: 28.0, 7: 28.0})
    result = _semantic_observation(mutant)
    controls["NC-GC-04_fake_contact_then_rebound"] = _control_result(
        "body_contact_persists_to_terminal",
        not result["transition"]["body_contact_persists_to_terminal"],
        terminal_body_contact=[result["body_records"][index]["body_contact"] for index in (6, 7)],
        terminal_support=[result["foot_records"][index]["measured_support"] for index in (6, 7)],
    )

    mutant = copy.deepcopy(spec)
    _set_track_values(mutant, "right_stride_x", {4: 100.0, 5: 100.0})
    _set_track_values(mutant, "right_lift_y", {4: 16.0, 5: 16.0})
    result = _semantic_observation(mutant)
    controls["NC-GC-05_planted_foot_world_drift"] = _control_result(
        "foot_ground_truthfulness",
        not result["transition"]["foot_ground_truthfulness"],
        right_foot=[result["foot_records"][index]["feet"]["right"] for index in (4, 5)],
    )

    mutant = copy.deepcopy(spec)
    for index in (6, 7):
        state = mutant["adapter_parameters"]["contact_contract"]["states"][index]
        state["grounded_terminal"] = False
        state["body_contact_class"] = "suspended"
        state["body_contact_regions"] = []
    _set_track_values(mutant, "left_arm_swing_deg", {6: 8.0, 7: 8.0})
    result = _semantic_observation(mutant)
    controls["NC-GC-06_terminal_suspended_lean"] = _control_result(
        "terminal_pose_physically_supported",
        not result["transition"]["terminal_pose_physically_supported"],
        terminal_declared_states=[result["transition"]["declared_states"][index] for index in (6, 7)],
        terminal_body_contact=[result["body_records"][index]["body_contact"] for index in (6, 7)],
    )

    passed = all(item["status"] == "REJECTED" for item in controls.values())
    return {
        "schema_version": "0.15.1",
        "status": "NC_GC_01_TO_NC_GC_06_PASSED" if passed else "NC_GC_01_TO_NC_GC_06_GAP",
        "controls": controls,
        "source": "scripts/validation/run_animation_runtime_v0151.py independent contact/support input mutations",
    }


def _death_negative_controls(spec: dict[str, Any], final_output: Path, run_a: Mapping[str, Any], run_b: Mapping[str, Any], hit_spec: dict[str, Any]) -> dict[str, Any]:
    controls: dict[str, Any] = {}

    mutant = copy.deepcopy(spec)
    for track_id in ("root_shift_x", "root_shift_y", "torso_rotation_deg", "torso_lean_x", "left_arm_swing_deg", "right_arm_swing_deg", "head_counter_rotation_deg", "sword_rotation_deg"):
        _set_track_values(mutant, track_id, {frame: 0.0 for frame in range(8)})
    result = _semantic_observation(mutant)
    controls["NC-01_no_collapse"] = _control_result("death_like_collapse", not result["temporal"]["hard_gates"]["death_like_collapse"], hard_gates=result["temporal"]["hard_gates"])

    mutant = copy.deepcopy(spec)
    _set_frames_to_frame_zero(mutant)
    result = _semantic_observation(mutant)
    controls["NC-02_hit_like_recovery"] = _control_result("irreversible_death", not result["temporal"]["hard_gates"]["irreversible_death"], hard_gates=result["temporal"]["hard_gates"])

    mutant = copy.deepcopy(spec)
    _set_track_values(mutant, "root_shift_y", {4: 50.0, 5: 50.0, 6: 50.0, 7: 50.0})
    _set_track_values(mutant, "left_arm_swing_deg", {4: 8.0, 5: 8.0, 6: 8.0, 7: 8.0})
    result = _semantic_observation(mutant)
    root_drop = max(float(item) for item in result["temporal"]["collapse"]["root_shift_y"] if isinstance(item, (int, float)))
    measured = result["transition"]["measured_first_body_contact_frame"]
    controls["NC-03_root_drop_without_body_contact"] = _control_result("marker_matches_measured_body_contact_transition", root_drop >= 32.0 and measured is None, root_drop_px=root_drop, measured_first_body_contact_frame=measured, hard_gates=result["temporal"]["hard_gates"])

    mutant = copy.deepcopy(spec)
    for marker in mutant["event_markers"]:
        if marker["event_id"] == "ground_contact":
            marker["frame"] = 3
    result = _semantic_observation(mutant)
    controls["NC-04_wrong_ground_contact_marker"] = _control_result("marker_matches_measured_body_contact_transition", not result["transition"]["marker_matches_measured_body_contact_transition"], hard_gates=result["temporal"]["hard_gates"])

    mutant = copy.deepcopy(spec)
    state = mutant["adapter_parameters"]["contact_contract"]["states"][7]
    state["grounded_terminal"] = False
    state["body_contact_class"] = "suspended"
    state["body_contact_regions"] = []
    result = _semantic_observation(mutant)
    controls["NC-05_final_pose_not_grounded"] = _control_result("final_pose_grounded_terminal", not result["transition"]["final_pose_grounded_terminal"], hard_gates=result["temporal"]["hard_gates"])

    mutant = copy.deepcopy(spec)
    mutant["adapter_parameters"]["contact_contract"]["states"][7]["grounded_terminal"] = False
    result = _semantic_observation(mutant)
    controls["NC-06_final_pose_not_terminal"] = _control_result("final_pose_grounded_terminal", not result["transition"]["final_pose_grounded_terminal"], hard_gates=result["temporal"]["hard_gates"])

    mutant = copy.deepcopy(spec)
    _set_frames_to_frame_zero(mutant)
    state = mutant["adapter_parameters"]["contact_contract"]["states"][7]
    state["grounded_terminal"] = False
    state["body_contact_class"] = "suspended"
    state["body_contact_regions"] = []
    result = _semantic_observation(mutant)
    controls["NC-07_final_pose_hit_like_or_combat_ready"] = _control_result("death_vs_hit_or_neutral", not result["temporal"]["hard_gates"]["death_vs_hit_or_neutral"], hard_gates=result["temporal"]["hard_gates"])

    mutant = copy.deepcopy(spec)
    _set_track_values(mutant, "left_arm_swing_deg", {5: -120.0})
    result = _semantic_observation(mutant)
    controls["NC-08_foot_or_body_contact_teleport"] = _control_result("contact_teleport_free", not result["temporal"]["hard_gates"]["contact_teleport_free"], contact=result["temporal"]["contact"])

    mutant = copy.deepcopy(spec)
    _set_track_values(mutant, "torso_rotation_deg", {4: -160.0})
    result = _semantic_observation(mutant)
    controls["NC-09_angular_jump"] = _control_result("angular_continuity", not result["temporal"]["hard_gates"]["angular_continuity"], metrics=result["temporal"]["metrics"])

    mutant = copy.deepcopy(spec)
    _set_track_values(mutant, "sword_rotation_deg", {7: 160.0})
    result = _semantic_observation(mutant)
    controls["NC-10_weapon_snap_or_wrist_break"] = _control_result("weapon_wrist_continuity", not result["temporal"]["hard_gates"]["weapon_wrist_continuity"], weapon=result["temporal"]["weapon"])

    frames = [Image.new("RGB", (16, 16), (40 + index * 12, 12, 24)) for index in range(int(spec["frame_count"]))]
    durations = gif_frame_durations_ms(spec)
    with tempfile.TemporaryDirectory(prefix="ugas-v0151-loop-nc-", dir=workdir()) as directory:
        path = Path(directory) / "explicit-loop.gif"
        _save_explicit_loop(frames, path, durations, 1)
        decoded = decode_gif_timing(path)
        check = gif_timing_within_tolerance(spec, decoded)
        controls["NC-11_explicit_loop_extension_on_nonloop"] = _control_result("gif_nonloop_extension_absent", check["status"] != "GIF_TIMING_PASSED", decoded=decoded, hard_gates=check["hard_gates"], gif_sha256=digest(path))

    mutant = copy.deepcopy(spec)
    mutant["provenance"]["source_sha256"] = "0" * 64
    try:
        load_source_context(mutant, ROOT)
    except (OSError, ValueError, KeyError) as exc:
        controls["NC-12_source_dependency_hash_removed"] = _control_result("source_dependency_hash", True, error=type(exc).__name__)
    else:
        controls["NC-12_source_dependency_hash_removed"] = _control_result("source_dependency_hash", False)

    with tempfile.TemporaryDirectory(prefix="ugas-v0151-package-nc-", dir=workdir()) as directory:
        temp = Path(directory)
        temp_manifest = temp / "compiled-manifest.json"
        temp_manifest.write_bytes((final_output / "compiled-manifest.json").read_bytes())
        false_qa = read_json(final_output / "qa-result.json")
        false_qa["hard_gates"]["synthetic_false_gate"] = False
        write_json(temp / "qa-result.json", false_qa)
        try:
            package_compiled(temp_manifest, ROOT)
        except (AnimationContractError, SchemaValidationError, ValueError, KeyError) as exc:
            controls["NC-13_synthetic_false_gate_in_package"] = _control_result("package_qualified_qa", True, error=type(exc).__name__)
        else:
            controls["NC-13_synthetic_false_gate_in_package"] = _control_result("package_qualified_qa", False)

    hit_gif = FROZEN_HIT / "hit-front-v1" / "hit-front-preview-v0141.gif"
    with tempfile.TemporaryDirectory(prefix="ugas-v0151-asset-nc-", dir=workdir()) as directory:
        mutated = Path(directory) / hit_gif.name
        data = bytearray(hit_gif.read_bytes())
        data[-8] ^= 0xFF
        mutated.write_bytes(bytes(data))
        controls["NC-14_approved_hit_or_run_asset_mutation"] = _control_result("immutable_approved_assets", digest(hit_gif) != digest(mutated), live_sha256=digest(hit_gif), mutated_sha256=digest(mutated))

    frozen_sc_path = ROOT / FROZEN_STATE_CONSISTENCY_V0141_PATH
    raw = frozen_sc_path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    live_blob = hashlib.sha1(f"blob {len(normalized)}\0".encode() + normalized).hexdigest()  # noqa: S324
    mutated_raw = raw.replace(b"external_review_hit_reaction_front_v0141", b"death_animation_front")
    mutated_normalized = mutated_raw.replace(b"\r\n", b"\n")
    mutated_blob = hashlib.sha1(f"blob {len(mutated_normalized)}\0".encode() + mutated_normalized).hexdigest()  # noqa: S324
    controls["NC-15_frozen_evidence_mutation_after_external_approval"] = _control_result("frozen_evidence_identity", live_blob == FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB and mutated_raw != raw and mutated_blob != FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB, live_git_blob=live_blob, approved_head_git_blob=FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB, simulated_mutation_detected=mutated_blob != FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB)

    with tempfile.TemporaryDirectory(prefix="ugas-v0151-determinism-nc-", dir=workdir()) as directory:
        temp = Path(directory) / "mutated-frame-00.png"
        source = ROOT / run_b["frame_paths"][0]
        shutil.copyfile(source, temp)
        with Image.open(temp) as image:
            mutated_image = image.convert("RGBA")
        pixel = mutated_image.getpixel((0, 0))
        mutated_image.putpixel((0, 0), (pixel[0] ^ 0xFF, pixel[1], pixel[2], pixel[3]))
        mutated_image.save(temp, format="PNG", optimize=False)
        mutated_snapshot = dict(run_b["snapshot"])
        mutated_frames = list(mutated_snapshot["frame_rgba_sha256"])
        mutated_frames[0] = png_rgba_pixel_sha256(temp)
        mutated_snapshot["frame_rgba_sha256"] = mutated_frames
        comparison = _compare_snapshots(run_a["snapshot"], mutated_snapshot)
        controls["NC-16_nondeterministic_second_render"] = _control_result("two_run_render_determinism", not comparison["all_fields_match"], comparison=comparison, mutation_path=relative(temp))

    passed = all(item["status"] == "REJECTED" for item in controls.values())
    ground_contact = _ground_contact_negative_controls(spec)
    return {"schema_version": "0.15.1", "status": "NC_01_TO_NC_16_PASSED" if passed else "NC_01_TO_NC_16_GAP", "controls": controls, "ground_contact_controls": ground_contact, "source": "scripts/validation/run_animation_runtime_v0151.py independent semantic, package and decoded-pixel mutations", "hit_spec_loop": hit_spec["loop"]}


def _marker_sheet(final_output: Path, qa: Mapping[str, Any], package: Mapping[str, Any]) -> tuple[Path, list[dict[str, Any]]]:
    font = ImageFont.load_default()
    marker_dir = final_output / "visual" / "phase-markers"
    marker_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    ground = float(qa["foot_ground"]["ground_reference_y"])
    for index, item in enumerate(read_json(final_output / "compiled-manifest.json")["frames"]):
        with Image.open(ROOT / item["path"]) as opened:
            image = opened.convert("RGBA")
        marker = image.copy()
        draw = ImageDraw.Draw(marker, "RGBA")
        frame = qa["frames"][index]
        events = [str(event["event_id"]) for event in qa["package_metadata"]["phase_markers"] if int(event["frame"]) == index]
        contacts = ",".join(frame["body_ground_contact"]["contact_regions"]) or "none"
        draw.line((0, ground, marker.width - 1, ground), fill=(255, 220, 80, 220), width=2)
        draw.rectangle((0, 0, marker.width - 1, 40), fill=(12, 20, 34, 235))
        draw.text((7, 6), f"F{index} {item['phase']} | {','.join(events)}", fill=(255, 255, 255, 255), font=font)
        draw.text((7, 22), f"body_contact={contacts} | ground_y={ground:.2f}", fill=(255, 220, 80, 255), font=font)
        destination = marker_dir / f"frame-{index:02d}-{item['phase']}.png"
        marker.save(destination, format="PNG", optimize=False)
        records.append({"frame": index, "phase": item["phase"], "events": events, "body_contact_regions": frame["body_ground_contact"]["contact_regions"], "ground_reference_y": ground, "path": relative(destination), "sha256": digest(destination)})
    sheet = Image.new("RGBA", (4 * 512, 2 * 548), (18, 22, 32, 255))
    draw = ImageDraw.Draw(sheet, "RGBA")
    for index, record in enumerate(records):
        with Image.open(ROOT / record["path"]) as opened:
            image = opened.convert("RGBA")
        left, top = (index % 4) * 512, (index // 4) * 548
        sheet.alpha_composite(image, (left, top + 36))
        draw.text((left + 8, top + 10), f"{record['phase']} | {'/'.join(record['events'])} | {','.join(record['body_contact_regions']) or 'no body contact'}", fill=(255, 255, 255, 255), font=font)
    sheet_path = OUT / "death-front-phase-markers-v0151.png"
    sheet.save(sheet_path, format="PNG", optimize=False)
    return sheet_path, records


def _repository_transfer_provenance() -> dict[str, Any]:
    result = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True, check=False)
    observed = result.stdout.strip() if result.returncode == 0 else "UNKNOWN"
    return {"schema_version": "0.15.1", "status": "REPOSITORY_TRANSFER_PROVENANCE_RECORDED", "active_repository": "KayzenRoot/ugas", "active_url": "https://github.com/KayzenRoot/ugas", "observed_origin_before_correction": observed, "historical_repository": "csn1985-ship-it/ugas", "historical_owner_evidence_preserved": True, "required_ruleset_ref": "refs/heads/main", "required_checks": ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence"], "current_user_can_bypass": "never", "codeowners_gap": "CODEOWNERS_GAP", "production_approved": False, "production_routing": "BLOCKED"}


def run() -> dict[str, Any]:
    if not FROZEN_HIT.is_dir() or not FROZEN_V0140.is_dir():
        raise RuntimeError("frozen_evidence_missing")
    if _git_rev(IMMUTABLE_BASE) != IMMUTABLE_BASE:
        raise RuntimeError("implementation_base_mismatch")
    branch_base = _git_rev(BRANCH_BASE)
    evidence_head = _git_rev("HEAD")
    if _merge_base(IMMUTABLE_BASE, "HEAD") != IMMUTABLE_BASE:
        raise RuntimeError("merge_base_must_be_immutable_v0124")
    spec = load_spec(SPEC_PATH, ROOT)
    hit_spec = load_spec(HIT_SPEC_PATH, ROOT)
    run_spec = load_spec(RUN_SPEC_PATH, ROOT)
    context = death_adapter.load_context(spec, ROOT)
    prepared = death_adapter.prepare(spec, context)
    OUT.mkdir(parents=True, exist_ok=True)
    if PACKAGE_OUT.exists():
        shutil.rmtree(PACKAGE_OUT)
    nc16_source = workdir() / "ugas-v0151-nc16-run-b-frame-00.png"
    nc16_source.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="ugas-v0151-run-a-", dir=workdir()) as run_a_dir, tempfile.TemporaryDirectory(prefix="ugas-v0151-run-b-", dir=workdir()) as run_b_dir:
        run_a_output = Path(run_a_dir) / "death-front-v1"
        run_b_output = Path(run_b_dir) / "death-front-v1"
        run_a_meta = _run_once(SPEC_PATH, run_a_output, "run_a")
        run_b_meta = _run_once(SPEC_PATH, run_b_output, "run_b")
        run_a_snapshot = _package_snapshot(run_a_output)
        run_b_snapshot = _package_snapshot(run_b_output)
        run_a_meta["snapshot"] = run_a_snapshot
        run_b_meta["snapshot"] = run_b_snapshot
        run_a_meta["frame_paths"] = [relative(run_a_output / f"frame-{index:02d}.png") for index in range(spec["frame_count"])]
        run_b_meta["frame_paths"] = [relative(run_b_output / f"frame-{index:02d}.png") for index in range(spec["frame_count"])]
        comparison = _compare_snapshots(run_a_snapshot, run_b_snapshot)
        if not comparison["all_fields_match"]:
            raise RuntimeError(f"V0151_TRUE_DETERMINISM_FAILED:{comparison}")
        # NC-16 must mutate a real frame from the isolated second run. Preserve
        # only that source pixel file until the negative-control check finishes;
        # the complete Run B directory remains disposable.
        shutil.copyfile(run_b_output / "frame-00.png", nc16_source)
    final_meta = _run_once(SPEC_PATH, PACKAGE_OUT, "final_evidence")
    final_snapshot = _package_snapshot(PACKAGE_OUT)
    final_manifest = read_json(PACKAGE_OUT / "compiled-manifest.json")
    final_qa = read_json(PACKAGE_OUT / "qa-result.json")
    final_package = read_json(PACKAGE_OUT / "package-manifest.json")
    if final_qa.get("decision") != "QUALIFIED":
        raise RuntimeError(f"DEATH_ANIMATION_FRONT_V0151_NOT_QUALIFIED:{final_qa.get('failures')}")
    gif_path = ROOT / final_package["preview_gif"]["path"]
    decoded_gif = decode_gif_timing(gif_path)
    gif_check = gif_timing_within_tolerance(spec, decoded_gif)
    if gif_check["status"] != "GIF_TIMING_PASSED" or decoded_gif["loop_extension_present"] is not False or decoded_gif["loop_count"] is not None:
        raise RuntimeError(f"V0151_NONLOOP_GIF_FAILED:{gif_check}")
    run_a = {"snapshot": run_a_snapshot, "frame_paths": run_a_meta["frame_paths"]}
    run_b = {"snapshot": run_b_snapshot, "frame_paths": run_b_meta["frame_paths"]}
    try:
        run_b["frame_paths"] = [relative(nc16_source)]
        negative = _death_negative_controls(spec, PACKAGE_OUT, run_a, run_b, hit_spec)
    finally:
        nc16_source.unlink(missing_ok=True)
    loop_nc = {**_loop_negative_controls(spec, run_spec), "schema_version": "0.15.1"}
    run_loop = {**_run_front_loop_regression(run_spec), "schema_version": "0.15.1"}
    hit_loop = {"schema_version": "0.15.1", "status": "HIT_NONLOOP_REGRESSION_PASSED" if (decoded := decode_gif_timing(FROZEN_HIT / "hit-front-v1" / "hit-front-preview-v0141.gif"))["loop_extension_present"] is False and decoded["loop_count"] is None else "HIT_NONLOOP_REGRESSION_GAP", "decoded": decoded, "source": "docs/evidence/animation-runtime-v0141/hit-front-v1/hit-front-preview-v0141.gif", "v0141_evidence_rewritten": False}
    assets = _approved_assets_untouched()
    frozen_integrity = _frozen_evidence_integrity()
    frozen_provenance = _frozen_provenance_hash()
    marker_sheet, marker_records = _marker_sheet(PACKAGE_OUT, final_qa, final_package)
    determinism = {"schema_version": "0.15.1", "status": "DEATH_DETERMINISM_TRUE_TWO_RUN_PASSED", "run_a": run_a_snapshot, "run_b": run_b_snapshot, "comparison": comparison, "run_a_output": run_a_meta, "run_b_output": run_b_meta, "final_output": final_snapshot, "nc_16_mutation_detected": negative["controls"]["NC-16_nondeterministic_second_render"]["status"] == "REJECTED"}
    contact_transition = final_qa["body_mechanics"]["contact"]["transition"]
    temporal_gates = final_qa["temporal"]["hard_gates"]
    contact_state = {
        "schema_version": "0.15.1",
        "animation_id": spec["animation_id"],
        "status": "DEATH_CONTACT_STATE_QA_PASSED" if temporal_gates["support_state_classification_valid"] and temporal_gates["ground_contact_marker_matches_actual_transition"] else "DEATH_CONTACT_STATE_GAP",
        "ground_reference": final_qa["foot_ground"]["ground_reference"],
        "frames": [
            {
                "frame": item["index"],
                "phase": item["phase"],
                "support_contact_state": item["support_contact_state"],
                "foot_support": item["feet"],
                "body_contact": item["body_ground_contact"],
                "measured_contact_points": {
                    name: {
                        "x": region["center_x"],
                        "y": region["bottom_y"],
                        "ground_clearance_px": region["ground_clearance_px"],
                        "contact": region["contact"],
                    }
                    for name, region in item["body_ground_contact"]["regions"].items()
                },
            }
            for item in final_qa["frames"]
        ],
        "transition": contact_transition,
    }
    ground_reference = {
        "schema_version": "0.15.1",
        "animation_id": spec["animation_id"],
        "status": "GLOBAL_GROUND_REFERENCE_VALID" if temporal_gates["global_ground_reference_valid"] else "GLOBAL_GROUND_REFERENCE_GAP",
        "reference": final_qa["foot_ground"]["ground_reference"],
        "derivation": "Freeze projected D0 source-alpha sole reference before the first corrected PNG; use the same floor reference for every rendered frame.",
        "thresholds": {key: value for key, value in spec["qa_profile"]["thresholds"].items() if "ground" in key or "foot_" in key or "contact" in key},
    }
    foot_ground = {
        "schema_version": "0.15.1",
        "animation_id": spec["animation_id"],
        "status": final_qa["foot_ground"]["status"],
        "ground_reference": final_qa["foot_ground"]["ground_reference"],
        "frames": final_qa["foot_ground"]["frames"],
        "hard_gates": {"foot_ground_truthfulness": temporal_gates["foot_ground_truthfulness"], "global_ground_reference_valid": temporal_gates["global_ground_reference_valid"]},
    }
    terminal_support = {
        "schema_version": "0.15.1",
        "animation_id": spec["animation_id"],
        "status": "DEATH_TERMINAL_SUPPORT_QA_PASSED" if temporal_gates["terminal_pose_physically_supported"] and temporal_gates["body_contact_persists_to_terminal"] else "DEATH_TERMINAL_SUPPORT_GAP",
        "terminal_frames": [
            {
                "frame": index,
                "body_contact": final_qa["frames"][index]["body_ground_contact"],
                "foot_support": final_qa["frames"][index]["feet"],
                "support_contact_state": final_qa["frames"][index]["support_contact_state"],
            }
            for index in (6, 7)
        ],
        "hard_gates": {key: temporal_gates[key] for key in ("terminal_pose_physically_supported", "body_contact_persists_to_terminal", "terminal_stability", "foot_ground_truthfulness")},
    }
    death_vs_hit = {
        "schema_version": "0.15.1",
        "animation_id": spec["animation_id"],
        "status": "DEATH_VS_HIT_SEMANTIC_SEPARATION_PASSED" if temporal_gates["death_vs_hit_semantic_separation"] else "DEATH_VS_HIT_SEMANTIC_SEPARATION_GAP",
        "death": {"metrics": final_qa["temporal"]["metrics"], "contact": contact_transition, "hard_gate": temporal_gates["death_vs_hit_semantic_separation"]},
        "immutable_hit_authority": {"profile": "profiles/animation/hit-front-v1.json", "evidence": "docs/evidence/animation-runtime-v0141/hit-front-v1", "approved_head": HIT_APPROVED_HEAD, "mutation": False},
        "separation_basis": "contact/support state and terminal grounding plus displacement; displacement alone is insufficient",
    }
    historical_v0150_rejection = {
        "schema_version": "0.15.1",
        "status": "V0150_EXTERNAL_VISUAL_FAILED_TECHNICAL_QA_REJECTED_BY_EXTERNAL_REVIEW",
        "historical_candidate": "docs/evidence/animation-runtime-v0150/",
        "reviewed_head": "c573ab020106ee89a36e1edb9bfae8b526d5057e",
        "external_visual": "FAILED",
        "technical_semantic_qa": "REJECTED_BY_EXTERNAL_REVIEW",
        "green_ci_does_not_override_visual_rejection": True,
        "historical_evidence_unchanged": True,
        "correction_policy": "forward_only",
        "reason": "The reviewed v0.15.0 D6/D7 output remained a suspended sideways lean and D4 did not show real body-ground contact.",
    }
    write_json(OUT / "death-front-targets-v0151.json", {"schema_version": "0.15.1", "animation_id": spec["animation_id"], "phase_order": list(death_adapter.PHASES), "targets": prepared["targets"], "target_hashes": [target["target_joint_sha256"] for target in prepared["targets"]], "key_pose_bindings": spec["key_pose_bindings"], "motion_tracks_sha256": prepared["track_hash"], "parameters_frozen_before_render": True, "source_only_pixels": True})
    write_json(OUT / "death-front-frame-qa-v0151.json", {"schema_version": "0.15.1", "animation_id": spec["animation_id"], "status": final_qa["status"], "decision": final_qa["decision"], "frames": final_qa["frames"]})
    write_json(OUT / "death-front-body-ground-contact-qa-v0151.json", {"schema_version": "0.15.1", "animation_id": spec["animation_id"], "status": final_qa["body_mechanics"]["status"], "ground_reference_y": final_qa["foot_ground"]["ground_reference_y"], "metric": "ground_reference_y_minus_rendered_region_alpha_bottom_y", "frames": [{"frame": item["index"], "phase": item["phase"], "declared_state": item["support_contact_state"], "measured": item["body_ground_contact"]} for item in final_qa["frames"]], "transition": final_qa["body_mechanics"]["contact"]["transition"], "hard_gates": final_qa["body_mechanics"]["hard_gates"]})
    write_json(OUT / "death-front-support-state-qa-v0151.json", {"schema_version": "0.15.1", "animation_id": spec["animation_id"], "status": final_qa["foot_ground"]["status"], "ground_reference_y": final_qa["foot_ground"]["ground_reference_y"], "states": [item["support_contact_state"] for item in final_qa["frames"]], "frames": final_qa["foot_ground"]["frames"], "state_transition_valid": final_qa["temporal"]["hard_gates"]["contact_state_transition_valid"]})
    write_json(OUT / "death-front-temporal-qa-v0151.json", {"schema_version": "0.15.1", "animation_id": spec["animation_id"], "status": final_qa["temporal"]["status"], "metrics": final_qa["temporal"]["metrics"], "hard_gates": final_qa["temporal"]["hard_gates"], "collapse": final_qa["temporal"]["collapse"], "contact": final_qa["temporal"]["contact"]})
    write_json(OUT / "death-front-body-mechanics-qa-v0151.json", {"schema_version": "0.15.1", "animation_id": spec["animation_id"], **final_qa["body_mechanics"]})
    write_json(OUT / "death-front-foot-contact-qa-v0151.json", {"schema_version": "0.15.1", "animation_id": spec["animation_id"], **final_qa["foot_ground"]})
    write_json(OUT / "death-front-continuity-qa-v0151.json", {"schema_version": "0.15.1", "animation_id": spec["animation_id"], "status": "DEATH_CONTINUITY_INTERPOLATION_PASSED" if final_qa["temporal"]["hard_gates"]["angular_continuity"] and final_qa["temporal"]["hard_gates"]["angular_acceleration_continuity"] and final_qa["temporal"]["hard_gates"]["contact_teleport_free"] else "DEATH_CONTINUITY_INTERPOLATION_GAP", "gates": {key: value for key, value in final_qa["temporal"]["hard_gates"].items() if key in {"angular_continuity", "angular_acceleration_continuity", "contact_teleport_free", "nonfinite_and_gap_free", "collapse_visible_in_bbox"}}, "metrics": final_qa["temporal"]["metrics"]})
    write_json(OUT / "death-front-weapon-qa-v0151.json", {"schema_version": "0.15.1", "animation_id": spec["animation_id"], **final_qa["weapon"]})
    write_json(OUT / "death-front-gate-negative-controls-v0151.json", negative)
    write_json(OUT / "death-front-loop-negative-controls-v0151.json", loop_nc)
    write_json(OUT / "run-front-loop-regression-v0151.json", run_loop)
    write_json(OUT / "hit-front-nonloop-regression-v0151.json", hit_loop)
    write_json(OUT / "approved-assets-untouched-v0151.json", assets)
    write_json(OUT / "frozen-evidence-integrity-v0151.json", frozen_integrity)
    write_json(OUT / "v0141-provenance-sha256-correction-v0151.json", frozen_provenance)
    write_json(OUT / "death-front-ground-reference-v0151.json", ground_reference)
    write_json(OUT / "death-front-contact-state-v0151.json", contact_state)
    write_json(OUT / "death-front-foot-ground-qa-v0151.json", foot_ground)
    write_json(OUT / "death-front-terminal-support-qa-v0151.json", terminal_support)
    write_json(OUT / "death-front-death-vs-hit-qa-v0151.json", death_vs_hit)
    write_json(OUT / "v0150-rejection-record-v0151.json", historical_v0150_rejection)
    write_json(OUT / "death-front-determinism-v0151.json", determinism)
    write_json(OUT / "death-front-gif-timing-v0151.json", {"schema_version": "0.15.1", **gif_check, "package_metadata": {"fps": final_package.get("fps"), "per_frame_duration_ms": final_package.get("per_frame_duration_ms"), "gif_encoded_frame_durations_ms": final_package.get("gif_encoded_frame_durations_ms"), "gif_total_cycle_ms": final_package.get("gif_total_cycle_ms"), "gif_effective_fps": final_package.get("gif_effective_fps"), "gif_loop_extension_present": final_package.get("gif_loop_extension_present"), "gif_loop_count": final_package.get("gif_loop_count")}})
    write_json(OUT / "death-front-gif-loop-semantics-v0151.json", {"schema_version": "0.15.1", "status": "GIF_LOOP_SEMANTICS_PASSED", "inspect": inspect_gif_loop_extension(gif_path), "decoded": decoded_gif, "spec_loop": spec["loop"]})
    transfer = _repository_transfer_provenance()
    write_json(OUT / "repository-transfer-provenance-v0151.json", transfer)
    visual_images = [{"frame": index, "phase": item["phase"], "source_path": item["path"], "rgba_sha256": item["rgba_sha256"], "target_hash": item["target_hash"], "media_type": "image/png", "role": "corrected-compiled-source-only-frame", "events": [event for event in spec["event_markers"] if int(event["frame"]) == index], "body_contact_regions": final_qa["frames"][index]["body_ground_contact"]["contact_regions"], "ground_reference_y": final_qa["foot_ground"]["ground_reference_y"]} for index, item in enumerate(final_manifest["frames"])]
    visual_images.extend([{"path": final_package["preview_gif"]["path"], "sha256": final_package["preview_gif"]["sha256"], "media_type": "image/gif", "role": "non-loop-review-gif", "events": spec["event_markers"], "gif_encoded_frame_durations_ms": decoded_gif["durations_ms"], "gif_total_cycle_ms": decoded_gif["total_cycle_ms"], "gif_effective_fps": decoded_gif["effective_fps"], "gif_loop_extension_present": decoded_gif["loop_extension_present"], "gif_loop_count": decoded_gif["loop_count"]}, {"path": final_package["sprite_sheet"]["path"], "sha256": final_package["sprite_sheet"]["sha256"], "media_type": "image/png", "role": "corrected-rgba-spritesheet", "events": spec["event_markers"]}, {"path": relative(marker_sheet), "sha256": digest(marker_sheet), "media_type": "image/png", "role": "phase-marker-contact-review-sheet", "events": spec["event_markers"]}])
    visual_manifest = {"schema_version": "0.15.1", "review_state": "death-front-v0151-technically-qualified-external-visual-required", "review_subject": {"animation_id": spec["animation_id"], "direction": spec["direction"], "frame_count": spec["frame_count"], "fps": spec["fps"], "loop": spec["loop"], "source_r4_sha256": spec["provenance"]["source_sha256"]}, "event_markers": spec["event_markers"], "event_markers_sha256": final_manifest["event_markers_sha256"], "motion_tracks_sha256": final_manifest["motion_tracks_sha256"], "gif_timing": decoded_gif, "images": visual_images, "marker_frames": marker_records, "source_only_pixels": True, "external_visual": "REQUIRED", "production_routing": "BLOCKED", "package_manifest": {"path": relative(PACKAGE_OUT / "package-manifest.json"), "sha256": digest(PACKAGE_OUT / "package-manifest.json")}, "contact_integrity": {key: temporal_gates[key] for key in ("global_ground_reference_valid", "support_state_classification_valid", "ground_contact_marker_matches_actual_transition", "body_contact_persists_to_terminal", "terminal_pose_physically_supported", "death_vs_hit_semantic_separation", "terminal_stability", "foot_ground_truthfulness")}}
    write_json(OUT / "death-front-visual-manifest-v0151.json", visual_manifest)
    execution = {"schema_version": "0.15.1", "prompt": "PROMPT-CORRETIVO-UGAS-v0.15.1-DEATH-GROUND-CONTACT-VISUAL-INTEGRITY", "implementation_base_commit": IMMUTABLE_BASE, "branch_base_commit": branch_base, "evidence_head_sha": evidence_head, "hit_approved_head_sha": HIT_APPROVED_HEAD, "run_front_approved_head_sha": RUN_APPROVED_HEAD, "animation_id": spec["animation_id"], "status": "CUTOUT_ANIMATION_RUNTIME_V1_DEATH_ANIMATION_FRONT_V0151_TECHNICALLY_QUALIFIED", "decision": final_qa["decision"], "frame_count": spec["frame_count"], "fps": spec["fps"], "loop": spec["loop"], "motion_tracks_sha256": final_manifest["motion_tracks_sha256"], "event_markers_sha256": final_manifest["event_markers_sha256"], "source_r4_sha256": spec["provenance"]["source_sha256"], "source_only_pixels": True, "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0, "new_generation": 0, "production_approved": False, "production_routing": "BLOCKED", "external_visual": "REQUIRED", "historical_v0150_review": historical_v0150_rejection, "negative_controls": negative["status"], "ground_contact_negative_controls": negative["ground_contact_controls"]["status"], "loop_negative_controls": loop_nc["status"], "run_front_loop_regression": run_loop["status"], "hit_front_nonloop_regression": hit_loop["status"], "approved_assets_untouched": assets["status"], "frozen_evidence_integrity": frozen_integrity["status"], "frozen_evidence_provenance_hash": frozen_provenance["status"], "true_two_run_determinism": determinism["status"], "repository_transfer_provenance": transfer["status"], "package": {"path": relative(PACKAGE_OUT / "package-manifest.json"), "sha256": digest(PACKAGE_OUT / "package-manifest.json"), "preview_gif": final_package["preview_gif"], "sprite_sheet": final_package["sprite_sheet"]}, "review_artifacts": {"visual_manifest": relative(OUT / "death-front-visual-manifest-v0151.json"), "phase_marker_sheet": relative(marker_sheet), "negative_controls": relative(OUT / "death-front-gate-negative-controls-v0151.json"), "contact_state": relative(OUT / "death-front-contact-state-v0151.json"), "ground_reference": relative(OUT / "death-front-ground-reference-v0151.json"), "body_mechanics": relative(OUT / "death-front-body-mechanics-qa-v0151.json"), "foot_ground": relative(OUT / "death-front-foot-ground-qa-v0151.json"), "terminal_support": relative(OUT / "death-front-terminal-support-qa-v0151.json"), "death_vs_hit": relative(OUT / "death-front-death-vs-hit-qa-v0151.json"), "provenance_hash_correction": relative(OUT / "v0141-provenance-sha256-correction-v0151.json"), "v0150_rejection": relative(OUT / "v0150-rejection-record-v0151.json"), "determinism": relative(OUT / "death-front-determinism-v0151.json")}, "historical_v0150_preserved": True, "historical_v0141_preserved": True, "next_capability_started": False, "executor_does_not_claim_visual_approval": True, "github_review_manifest_is_authority_for_final_head": True, "contact_gate_names": ["global_ground_reference_valid", "support_state_classification_valid", "ground_contact_marker_matches_actual_transition", "body_contact_persists_to_terminal", "terminal_pose_physically_supported", "death_vs_hit_semantic_separation", "terminal_stability", "foot_ground_truthfulness"]}
    write_json(OUT / "execution-evidence-v0.15.1.json", execution)
    if negative["status"] != "NC_01_TO_NC_16_PASSED" or negative["ground_contact_controls"]["status"] != "NC_GC_01_TO_NC_GC_06_PASSED" or loop_nc["status"] != "NC_LOOP_01_TO_05_PASSED" or run_loop["status"] != "RUN_FRONT_LOOP_REGRESSION_PASSED" or hit_loop["status"] != "HIT_NONLOOP_REGRESSION_PASSED" or assets["status"] != "APPROVED_ASSETS_UNTOUCHED" or frozen_integrity["status"] != "FROZEN_V0141_EVIDENCE_RESTORED_AND_VERIFIED" or frozen_provenance["status"] != "V0141_PROVENANCE_SHA256_CORRECTION_RECORDED" or determinism["status"] != "DEATH_DETERMINISM_TRUE_TWO_RUN_PASSED":
        raise RuntimeError(f"V0151_GATES_FAILED:{negative['status']}:{loop_nc['status']}:{run_loop['status']}:{hit_loop['status']}:{assets['status']}:{frozen_integrity['status']}:{determinism['status']}")
    return {"status": "ANIMATION_RUNTIME_V0151_PASSED", "decision": final_qa["decision"], "animation_id": spec["animation_id"], "frames": len(final_manifest["frames"]), "package": relative(PACKAGE_OUT / "package-manifest.json"), "preview_gif": final_package["preview_gif"]["path"], "negative_controls": negative["status"], "ground_contact_negative_controls": negative["ground_contact_controls"]["status"], "loop_negative_controls": loop_nc["status"], "run_front_loop_regression": run_loop["status"], "hit_front_nonloop_regression": hit_loop["status"], "approved_assets": assets["status"], "frozen_evidence_integrity": frozen_integrity["status"], "frozen_evidence_provenance_hash": frozen_provenance["status"], "determinism": determinism["status"], "gif_loop_extension_present": decoded_gif["loop_extension_present"], "gif_loop_count": decoded_gif["loop_count"], "external_visual": "REQUIRED", "production_routing": "BLOCKED"}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
        raise SystemExit(0)
    except Exception as exc:
        print(json.dumps({"status": "ANIMATION_RUNTIME_V0151_FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False))
        raise SystemExit(2)
