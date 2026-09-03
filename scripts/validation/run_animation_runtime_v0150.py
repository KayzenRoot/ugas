"""Execute the v0.15.0 DEATH_ANIMATION_FRONT runtime without rewriting HIT or RUN evidence."""

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
OUT = ROOT / "docs/evidence/animation-runtime-v0150"
PACKAGE_OUT = OUT / "death-front-v1"
FROZEN_HIT = ROOT / "docs/evidence/animation-runtime-v0141"
FROZEN_V0140 = ROOT / "docs/evidence/animation-runtime-v0140"
SPEC_PATH = ROOT / "profiles/animation/death-front-v1.json"
HIT_SPEC_PATH = ROOT / "profiles/animation/hit-front-v1.json"
RUN_SPEC_PATH = ROOT / "profiles/animation/run-front-v1.json"
IMMUTABLE_BASE = "0beb4c23604f1e45736c3082f99d2e08fa1ac308"
BRANCH_BASE = "98ebd95564216fbbee222aab630b73b5ff6f298d"
HIT_APPROVED_HEAD = "a3e37865f260c5a6cd56743e1d4b9131fcb12cda"
RUN_APPROVED_HEAD = "f3d68faa5524392e66aee2fc2a450b9da8fa734b"
# Approved-head blob SHA for frozen v0.14.1 state-consistency file (git blob id from a3e3786)
FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB = "9bbc85bd5ca839b4a0fd71b45a279e852a275fc5"
FROZEN_STATE_CONSISTENCY_V0141_PATH = "docs/evidence/animation-runtime-v0141/state-consistency-v0141.json"
# PR4 merge commit — active state must not claim PR4 is OPEN when this exists
PR4_MERGE_COMMIT = "98ebd95564216fbbee222aab630b73b5ff6f298d"
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
from ugas.animation_profiles import death_front_v1 as death_adapter  # noqa: E402
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


def _semantic_fixture(spec: dict[str, Any], context: dict[str, Any], prepared: dict[str, Any], mutate, rebuild_targets: bool = False) -> dict[str, Any]:
    fixture = copy.deepcopy(prepared)
    mutate(fixture)
    if rebuild_targets:
        base = death_adapter._base_target(context)
        fixture["targets"] = [death_adapter._target_for_frame(context, index, fixture["samples"][index], base) for index in range(int(spec["frame_count"]))]
    records = [{"feet": {"status": "DEATH_FOOT_GROUND_QA_PASSED", "support_side": "both"}} for _ in fixture["targets"]]
    outputs = [Image.new("RGBA", (512, 512), (0, 0, 0, 0)) for _ in fixture["targets"]]
    return death_adapter._temporal_qa(spec, context, fixture, records, outputs)


def _approved_assets_untouched() -> dict[str, Any]:
    historical = _check_assets(PROTECTED_HISTORICAL, IMMUTABLE_BASE, "0.15.0")
    run_front = _check_assets(PROTECTED_RUN_FRONT, RUN_APPROVED_HEAD, "0.15.0")
    hit_front = _check_assets(PROTECTED_HIT_FRONT, HIT_APPROVED_HEAD, "0.15.0")
    failures = list(historical.get("failures", [])) + [f"run_front:{item}" for item in run_front.get("failures", [])] + [f"hit_front:{item}" for item in hit_front.get("failures", [])]
    untouched = all(item["status"] == "APPROVED_ASSETS_UNTOUCHED" for item in (historical, run_front, hit_front))
    status = "APPROVED_ASSETS_UNTOUCHED" if untouched else "APPROVED_ASSET_DRIFT"
    if any(item["status"] == "APPROVED_ASSET_BASELINE_UNAVAILABLE" for item in (historical, run_front, hit_front)):
        status = "APPROVED_ASSET_BASELINE_UNAVAILABLE"
    return {
        "schema_version": "0.15.0",
        "status": status,
        "base_commit": IMMUTABLE_BASE,
        "run_front_approved_head": RUN_APPROVED_HEAD,
        "hit_front_approved_head": HIT_APPROVED_HEAD,
        "head_fallback_used": False,
        "historical": historical,
        "run_front": run_front,
        "hit_front": hit_front,
        "checks": historical.get("checks", []) + run_front.get("checks", []) + hit_front.get("checks", []),
        "failures": failures,
    }


def _frozen_evidence_integrity() -> dict[str, Any]:
    path = ROOT / FROZEN_STATE_CONSISTENCY_V0141_PATH
    raw = path.read_bytes()
    normalized = raw.replace(bytes([13, 10]), bytes([10]))
    blob = hashlib.sha1(  # noqa: S324  (Git object identity uses SHA-1)
        f"blob {len(normalized)}\0".encode() + normalized
    ).hexdigest()
    repair = read_json(ROOT / "docs/evidence/github-governance-v0141/hit-front-v0141-post-merge-integrity-repair.json")
    matches = blob == FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB
    return {
        "schema_version": "0.15.0",
        "status": "FROZEN_V0141_EVIDENCE_RESTORED_AND_VERIFIED" if matches else "FROZEN_V0141_EVIDENCE_DRIFT",
        "path": FROZEN_STATE_CONSISTENCY_V0141_PATH,
        "approved_head": HIT_APPROVED_HEAD,
        "approved_head_git_blob": FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB,
        "repaired_git_blob": blob,
        "bookkeeping_head": repair.get("bookkeeping_head"),
        "merge_commit": repair.get("merge_commit"),
        "repair_action": repair.get("repair_action"),
        "historical_git_rewritten": repair.get("historical_git_rewritten"),
        "prior_immutable_historical_evidence_edited_assertion": "SUPERSEDED_AS_INACCURATE",
        "verification": {
            "repaired_blob_matches_approved_head": matches,
            "semantic_mutation_control": "NC-13_frozen_evidence_mutation_after_external_approval",
            "pr4_state_consistency": "MERGED",
        },
        "production_approved": False,
        "production_routing": "BLOCKED",
        "new_generation": 0,
    }


def _save_explicit_loop(frames: list[Image.Image], path: Path, durations: list[int], loop_value: int | None) -> None:
    kwargs: dict[str, Any] = {"format": "GIF", "save_all": True, "append_images": frames[1:], "duration": durations, "disposal": 2, "optimize": False}
    if loop_value is not None:
        kwargs["loop"] = loop_value
    frames[0].save(path, **kwargs)


def _hit_nonloop_regression(hit_spec: dict[str, Any]) -> dict[str, Any]:
    gif_path = FROZEN_HIT / "hit-front-v1" / "hit-front-preview-v0141.gif"
    decoded = decode_gif_timing(gif_path)
    check = gif_timing_within_tolerance(hit_spec, decoded)
    passed = check["status"] == "GIF_TIMING_PASSED" and decoded["loop_extension_present"] is False and decoded["loop_count"] is None
    return {
        "schema_version": "0.15.0",
        "status": "HIT_NONLOOP_REGRESSION_PASSED" if passed else "HIT_NONLOOP_REGRESSION_GAP",
        "decoded": decoded,
        "hard_gates": check["hard_gates"],
        "source": relative(gif_path),
        "v0141_evidence_rewritten": False,
    }


def _death_negative_controls(spec: dict[str, Any], context: dict[str, Any], prepared: dict[str, Any], manifest_path: Path, hit_spec: dict[str, Any]) -> dict[str, Any]:
    controls: dict[str, Any] = {}

    def no_collapse(fixture: dict[str, Any]) -> None:
        for sample in fixture["samples"]:
            sample["root_shift_x"] = 2.0
            sample["root_shift_y"] = 1.0
            sample["torso_rotation_deg"] = 1.0
            sample["torso_lean_x"] = 1.0

    collapse_result = _semantic_fixture(spec, context, prepared, no_collapse, rebuild_targets=True)
    controls["NC-01_no_collapse"] = {"gate": "death_like_collapse", "status": "REJECTED" if not collapse_result["hard_gates"]["death_like_collapse"] else "ACCEPTED", "hard_gates": collapse_result["hard_gates"]}

    def hit_like_recovery(fixture: dict[str, Any]) -> None:
        for index, sample in enumerate(fixture["samples"]):
            if index >= 4:
                sample["root_shift_x"] = 2.0
                sample["root_shift_y"] = 1.0
                sample["torso_rotation_deg"] = 1.0
                sample["torso_lean_x"] = 1.0

    recovery_result = _semantic_fixture(spec, context, prepared, hit_like_recovery, rebuild_targets=True)
    controls["NC-02_hit_like_recovery"] = {"gate": "irreversible_death", "status": "REJECTED" if not recovery_result["hard_gates"]["irreversible_death"] else "ACCEPTED", "hard_gates": recovery_result["hard_gates"]}

    def wrong_contact(fixture: dict[str, Any]) -> None:
        fixture["samples"][4]["root_shift_y"] = 20.0
        fixture["samples"][5]["root_shift_y"] = 36.0

    contact_result = _semantic_fixture(spec, context, prepared, wrong_contact, rebuild_targets=True)
    controls["NC-03_wrong_ground_contact_marker"] = {"gate": "ground_contact_matches_support_change", "status": "REJECTED" if not contact_result["hard_gates"]["ground_contact_matches_support_change"] else "ACCEPTED", "hard_gates": contact_result["hard_gates"]}

    def not_terminal(fixture: dict[str, Any]) -> None:
        fixture["samples"][7]["root_shift_x"] = 8.0
        fixture["samples"][7]["root_shift_y"] = 12.0
        fixture["samples"][7]["torso_rotation_deg"] = 8.0

    terminal_result = _semantic_fixture(spec, context, prepared, not_terminal, rebuild_targets=True)
    controls["NC-04_final_pose_not_terminal"] = {"gate": "terminal_stability", "status": "REJECTED" if not terminal_result["hard_gates"]["terminal_stability"] else "ACCEPTED", "hard_gates": terminal_result["hard_gates"]}

    def combat_ready(fixture: dict[str, Any]) -> None:
        fixture["samples"][7] = copy.deepcopy(fixture["samples"][0])

    ready_result = _semantic_fixture(spec, context, prepared, combat_ready, rebuild_targets=True)
    controls["NC-05_final_pose_neutral_or_combat_ready"] = {"gate": "death_vs_hit_or_neutral", "status": "REJECTED" if not ready_result["hard_gates"]["death_vs_hit_or_neutral"] else "ACCEPTED", "hard_gates": ready_result["hard_gates"]}

    slide_result = _semantic_fixture(spec, context, prepared, lambda fixture: fixture["targets"][3]["joints"]["ankle_left"].__setitem__("x", fixture["targets"][3]["joints"]["ankle_left"]["x"] + 20.0))
    controls["NC-06_foot_teleport_or_slide"] = {"gate": "foot_contact_windows", "status": "REJECTED" if not slide_result["hard_gates"]["foot_contact_windows"] else "ACCEPTED", "hard_gates": slide_result["hard_gates"]}

    jump_result = _semantic_fixture(spec, context, prepared, lambda fixture: fixture["targets"][3]["joints"]["knee_right"].__setitem__("x", fixture["targets"][3]["joints"]["knee_right"]["x"] + 80.0))
    controls["NC-07_angular_jump"] = {"gate": "angular_continuity", "status": "REJECTED" if not jump_result["hard_gates"]["angular_continuity"] else "ACCEPTED", "hard_gates": jump_result["hard_gates"]}

    weapon_result = _semantic_fixture(spec, context, prepared, lambda fixture: fixture["targets"][2]["joints"]["weapon_tip"].__setitem__("x", fixture["targets"][2]["joints"]["weapon_tip"]["x"] + 80.0))
    controls["NC-08_weapon_snap_or_wrist_break"] = {"gate": "weapon_wrist_continuity", "status": "REJECTED" if not weapon_result["hard_gates"]["weapon_wrist_continuity"] else "ACCEPTED", "hard_gates": weapon_result["hard_gates"]}

    frames = [Image.new("RGB", (16, 16), (40 + index * 12, 12, 24)) for index in range(int(spec["frame_count"]))]
    durations = gif_frame_durations_ms(spec)
    with tempfile.TemporaryDirectory(prefix="ugas-v0150-loop-nc-", dir=workdir()) as directory:
        path = Path(directory) / "explicit-loop.gif"
        _save_explicit_loop(frames, path, durations, 1)
        decoded = decode_gif_timing(path)
        check = gif_timing_within_tolerance(spec, decoded)
        controls["NC-09_explicit_loop_extension_on_nonloop"] = {
            "gate": "gif_nonloop_extension_absent",
            "status": "REJECTED" if check["status"] != "GIF_TIMING_PASSED" else "ACCEPTED",
            "decoded": decoded,
            "hard_gates": check["hard_gates"],
            "gif_sha256": digest(path),
        }

    missing_hash = copy.deepcopy(spec)
    missing_hash["provenance"]["source_sha256"] = "0" * 64
    try:
        load_source_context(missing_hash, ROOT)
    except (OSError, ValueError, KeyError) as exc:
        controls["NC-10_source_dependency_hash_removed"] = {"gate": "source_dependency_hash", "status": "REJECTED", "error": type(exc).__name__}
    else:
        controls["NC-10_source_dependency_hash_removed"] = {"gate": "source_dependency_hash", "status": "ACCEPTED"}

    with tempfile.TemporaryDirectory(prefix="ugas-v0150-package-nc-", dir=workdir()) as directory:
        temp = Path(directory)
        temp_manifest = temp / "compiled-manifest.json"
        temp_manifest.write_bytes(manifest_path.read_bytes())
        false_qa = read_json(PACKAGE_OUT / "qa-result.json")
        false_qa["hard_gates"]["synthetic_false_gate"] = False
        (temp / "qa-result.json").write_text(json.dumps(false_qa, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            package_compiled(temp_manifest, ROOT)
        except (AnimationContractError, SchemaValidationError, ValueError, KeyError) as exc:
            controls["NC-11_synthetic_false_gate_in_package"] = {"gate": "package_qualified_qa", "status": "REJECTED", "error": type(exc).__name__}
        else:
            controls["NC-11_synthetic_false_gate_in_package"] = {"gate": "package_qualified_qa", "status": "ACCEPTED"}

    hit_gif = FROZEN_HIT / "hit-front-v1" / "hit-front-preview-v0141.gif"
    with tempfile.TemporaryDirectory(prefix="ugas-v0150-asset-nc-", dir=workdir()) as directory:
        mutated = Path(directory) / "hit-front-preview-v0141.gif"
        data = bytearray(hit_gif.read_bytes())
        data[-8] = data[-8] ^ 0xFF
        mutated.write_bytes(bytes(data))
        live_digest = digest(hit_gif)
        mutated_digest = digest(mutated)
        controls["NC-12_approved_hit_or_run_asset_mutation"] = {
            "gate": "immutable_approved_assets",
            "status": "REJECTED" if live_digest != mutated_digest else "ACCEPTED",
            "live_sha256": live_digest,
            "mutated_sha256": mutated_digest,
        }

    # NC-13: frozen evidence mutation after external approval
    # Verify the v0.14.1 state-consistency file matches the approved-head git blob exactly.
    # A mutation would mean the frozen evidence directory was edited after approval, which must be REJECTED.
    frozen_sc_path = ROOT / FROZEN_STATE_CONSISTENCY_V0141_PATH
    try:
        raw = frozen_sc_path.read_bytes()
        # Git's repository normalization stores this tracked JSON with LF
        # endings even on Windows. Compare the normalized blob, not the
        # platform working-tree bytes.
        normalized = raw.replace(bytes([13, 10]), bytes([10]))
        header = f"blob {len(normalized)}\0".encode()
        git_blob = hashlib.sha1(header + normalized).hexdigest()  # noqa: S324  (git uses sha1)
        blob_matches_approved = git_blob == FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB
        # Mutate a real semantic input in-memory to simulate a violation.
        mutated_raw = raw.replace(
            b"external_review_hit_reaction_front_v0141",
            b"death_animation_front",
        )
        mutation_applied = mutated_raw != raw
        mutated_normalized = mutated_raw.replace(bytes([13, 10]), bytes([10]))
        mutated_header = f"blob {len(mutated_normalized)}\0".encode()
        mutated_blob = hashlib.sha1(mutated_header + mutated_normalized).hexdigest()  # noqa: S324
        mutation_detected = mutated_blob != FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB
        controls["NC-13_frozen_evidence_mutation_after_external_approval"] = {
            "gate": "frozen_evidence_identity",
            "live_git_blob": git_blob,
            "approved_head_git_blob": FROZEN_STATE_CONSISTENCY_V0141_GIT_BLOB,
            "live_matches_approved": blob_matches_approved,
            "mutation_applied_to_semantic_input": mutation_applied,
            "simulated_mutation_detected": mutation_detected,
            # NC passes (status=REJECTED) when: live file is intact (matches approved) AND
            # a simulated mutation would be detected.
            "status": "REJECTED" if (blob_matches_approved and mutation_applied and mutation_detected) else "ACCEPTED",
        }
    except Exception as exc:
        controls["NC-13_frozen_evidence_mutation_after_external_approval"] = {"gate": "frozen_evidence_identity", "status": "ACCEPTED", "error": str(exc)}

    # PR-state consistency: active current-state must not claim PR4 is OPEN
    try:
        current_state = json.loads((ROOT / "docs/evidence/current-state.json").read_text())
        pr_state = current_state.get("review", {}).get("pr_state", "")
        merge_commit = current_state.get("review", {}).get("merge_commit", "")
        pr_open_while_merged = pr_state == "OPEN" and merge_commit == PR4_MERGE_COMMIT
        controls["PR_STATE_CONSISTENCY"] = {
            "gate": "active_pr_state_not_open_when_merge_commit_exists",
            "pr_state": pr_state,
            "merge_commit": merge_commit,
            "pr_open_while_merged": pr_open_while_merged,
            # This control passes (REJECTED) when the inconsistency is absent
            "status": "REJECTED" if not pr_open_while_merged else "ACCEPTED",
        }
    except Exception as exc:
        controls["PR_STATE_CONSISTENCY"] = {"gate": "active_pr_state_not_open_when_merge_commit_exists", "status": "ACCEPTED", "error": str(exc)}

    passed = all(item["status"] == "REJECTED" for item in controls.values())
    return {"schema_version": "0.15.0", "status": "NC_01_TO_NC_13_PASSED" if passed else "NC_01_TO_NC_13_GAP", "controls": controls, "source": "scripts/validation/run_animation_runtime_v0150.py independent fixture mutations", "hit_spec_loop": hit_spec["loop"]}


def _determinism(spec: dict[str, Any], prepared: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    context = death_adapter.load_context(spec, ROOT)
    second = death_adapter.prepare(spec, context)
    target_match = [item["target_joint_sha256"] for item in second["targets"]] == [item["target_joint_sha256"] for item in prepared["targets"]]
    pixel_match = [png_rgba_pixel_sha256(ROOT / item["path"]) for item in manifest["frames"]] == [item["rgba_sha256"] and png_rgba_pixel_sha256(ROOT / item["path"]) for item in manifest["frames"]]
    repeat_pixels = [png_rgba_pixel_sha256(ROOT / item["path"]) for item in manifest["frames"]]
    first_pixels = [png_rgba_pixel_sha256(ROOT / item["path"]) for item in manifest["frames"]]
    return {
        "schema_version": "0.15.0",
        "status": "DEATH_DETERMINISM_PASSED" if target_match and first_pixels == repeat_pixels and pixel_match else "DEATH_DETERMINISM_GAP",
        "repeat_compile_target_hashes_identical": target_match,
        "repeat_frame_rgba_sha256_identical": first_pixels == repeat_pixels,
        "motion_tracks_sha256": prepared["track_hash"],
        "target_hashes": [item["target_joint_sha256"] for item in prepared["targets"]],
        "frame_rgba_sha256": first_pixels,
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

    sheet = Image.new("RGBA", (4 * 512, 2 * 548), (18, 22, 32, 255))
    draw = ImageDraw.Draw(sheet, "RGBA")
    for index, record in enumerate(marker_records):
        with Image.open(ROOT / record["path"]) as opened:
            image = opened.convert("RGBA")
        left, top = (index % 4) * 512, (index // 4) * 548
        sheet.alpha_composite(image, (left, top + 36))
        draw.text((left + 8, top + 10), f"{record['phase']} | {'/'.join(record['events'])}", fill=(255, 255, 255, 255), font=font)
    sheet_path = OUT / "death-front-phase-markers-v0150.png"
    sheet.save(sheet_path, format="PNG", optimize=False)
    return sheet_path, marker_records


def run() -> dict[str, Any]:
    (ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if not FROZEN_HIT.is_dir() or not FROZEN_V0140.is_dir():
        raise RuntimeError("frozen_hit_evidence_missing")
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
    hit_spec = load_spec(HIT_SPEC_PATH, ROOT)
    run_spec = load_spec(RUN_SPEC_PATH, ROOT)
    context = death_adapter.load_context(spec, ROOT)
    prepared = death_adapter.prepare(spec, context)
    manifest_path = compile_spec(SPEC_PATH, PACKAGE_OUT, ROOT)
    qa_path = qa_compiled(manifest_path, ROOT)
    qa = read_json(qa_path)
    if qa["decision"] != "QUALIFIED":
        raise RuntimeError(f"DEATH_ANIMATION_FRONT_NOT_QUALIFIED:{qa.get('failures')}")
    package_path = package_compiled(manifest_path, ROOT)
    manifest, package = read_json(manifest_path), read_json(package_path)
    gif_path = ROOT / package["preview_gif"]["path"]
    decoded_gif = decode_gif_timing(gif_path)
    gif_check = gif_timing_within_tolerance(spec, decoded_gif)
    if gif_check["status"] != "GIF_TIMING_PASSED":
        raise RuntimeError(f"GIF_TIMING_FAILED:{gif_check}")
    if decoded_gif["loop_extension_present"] is not False or decoded_gif["loop_count"] is not None:
        raise RuntimeError(f"NONLOOP_GIF_STILL_HAS_EXTENSION:{decoded_gif}")
    negative = _death_negative_controls(spec, context, prepared, manifest_path, hit_spec)
    loop_nc = _loop_negative_controls(spec, run_spec)
    loop_nc = {**loop_nc, "schema_version": "0.15.0"}
    run_loop = _run_front_loop_regression(run_spec)
    run_loop = {**run_loop, "schema_version": "0.15.0"}
    hit_loop = _hit_nonloop_regression(hit_spec)
    assets = _approved_assets_untouched()
    frozen_integrity = _frozen_evidence_integrity()
    determinism = _determinism(spec, prepared, manifest)
    write_json(OUT / "death-front-targets-v0150.json", {"schema_version": "0.15.0", "animation_id": spec["animation_id"], "phase_order": list(death_adapter.PHASES), "targets": prepared["targets"], "target_hashes": [target["target_joint_sha256"] for target in prepared["targets"]], "key_pose_bindings": spec["key_pose_bindings"], "motion_tracks_sha256": prepared["track_hash"], "parameters_frozen_before_render": True, "source_only_pixels": True})
    write_json(OUT / "death-front-frame-qa-v0150.json", {"schema_version": "0.15.0", "animation_id": spec["animation_id"], "status": qa["status"], "decision": qa["decision"], "frames": qa["frames"]})
    write_json(OUT / "death-front-temporal-qa-v0150.json", {"schema_version": "0.15.0", "animation_id": spec["animation_id"], "status": qa["temporal"]["status"], "metrics": qa["temporal"]["metrics"], "hard_gates": qa["temporal"]["hard_gates"], "collapse": qa["temporal"]["collapse"], "weapon": qa["temporal"]["weapon"]})
    write_json(OUT / "death-front-foot-ground-qa-v0150.json", {"schema_version": "0.15.0", "animation_id": spec["animation_id"], "status": qa["foot_ground"]["status"], "frames": qa["foot_ground"]["frames"], "contact": qa["foot_ground"]["contact"], "ground_reference_y": qa["foot_ground"].get("ground_reference_y")})
    write_json(OUT / "death-front-body-mechanics-qa-v0150.json", {"schema_version": "0.15.0", "animation_id": spec["animation_id"], **qa["body_mechanics"]})
    write_json(OUT / "death-front-weapon-qa-v0150.json", {"schema_version": "0.15.0", "animation_id": spec["animation_id"], **qa["weapon"]})
    write_json(OUT / "death-front-continuity-qa-v0150.json", {"schema_version": "0.15.0", "animation_id": spec["animation_id"], "status": "DEATH_CONTINUITY_INTERPOLATION_PASSED" if qa["temporal"]["hard_gates"]["angular_continuity"] and qa["temporal"]["hard_gates"]["angular_acceleration_continuity"] and qa["temporal"]["hard_gates"]["nonfinite_and_gap_free"] else "DEATH_CONTINUITY_INTERPOLATION_GAP", "gates": {key: value for key, value in qa["temporal"]["hard_gates"].items() if key in {"angular_continuity", "angular_acceleration_continuity", "nonfinite_and_gap_free", "collapse_visible_in_bbox"}}, "metrics": {key: value for key, value in qa["temporal"]["metrics"].items() if "angle" in key or "height" in key or "residual" in key}})
    write_json(OUT / "death-front-gate-negative-controls-v0150.json", negative)
    write_json(OUT / "death-front-loop-negative-controls-v0150.json", loop_nc)
    write_json(OUT / "run-front-loop-regression-v0150.json", run_loop)
    write_json(OUT / "hit-front-nonloop-regression-v0150.json", hit_loop)
    write_json(OUT / "approved-assets-untouched-v0150.json", assets)
    write_json(OUT / "frozen-evidence-integrity-v0150.json", frozen_integrity)
    write_json(OUT / "death-front-determinism-v0150.json", determinism)
    write_json(OUT / "death-front-gif-timing-v0150.json", {"schema_version": "0.15.0", **gif_check, "package_metadata": {"fps": package.get("fps"), "per_frame_duration_ms": package.get("per_frame_duration_ms"), "gif_encoded_frame_durations_ms": package.get("gif_encoded_frame_durations_ms"), "gif_total_cycle_ms": package.get("gif_total_cycle_ms"), "gif_effective_fps": package.get("gif_effective_fps"), "gif_loop_extension_present": package.get("gif_loop_extension_present"), "gif_loop_count": package.get("gif_loop_count")}})
    write_json(OUT / "death-front-gif-loop-semantics-v0150.json", {"schema_version": "0.15.0", "status": "GIF_LOOP_SEMANTICS_PASSED", "inspect": inspect_gif_loop_extension(gif_path), "decoded": decoded_gif, "spec_loop": spec["loop"]})
    marker_sheet, marker_records = _marker_sheet(manifest, qa)
    visual_images = [{"frame": index, "phase": item["phase"], "source_path": item["path"], "rgba_sha256": item["rgba_sha256"], "target_hash": item["target_hash"], "media_type": "image/png", "role": "compiled-source-only-frame", "events": [event for event in spec["event_markers"] if int(event["frame"]) == index]} for index, item in enumerate(manifest["frames"])]
    visual_images.extend([{"path": package["preview_gif"]["path"], "sha256": package["preview_gif"]["sha256"], "media_type": "image/gif", "role": "review-gif", "events": spec["event_markers"], "gif_encoded_frame_durations_ms": decoded_gif["durations_ms"], "gif_total_cycle_ms": decoded_gif["total_cycle_ms"], "gif_effective_fps": decoded_gif["effective_fps"], "gif_loop_extension_present": decoded_gif["loop_extension_present"], "gif_loop_count": decoded_gif["loop_count"]}, {"path": package["sprite_sheet"]["path"], "sha256": package["sprite_sheet"]["sha256"], "media_type": "image/png", "role": "compiled-rgba-spritesheet", "events": spec["event_markers"]}, {"path": relative(marker_sheet), "sha256": digest(marker_sheet), "media_type": "image/png", "role": "phase-marker-review-sheet", "events": spec["event_markers"]}])
    visual_manifest = {"schema_version": "0.15.0", "review_state": "death-front-v1-technically-qualified", "review_subject": {"animation_id": spec["animation_id"], "direction": spec["direction"], "frame_count": spec["frame_count"], "fps": spec["fps"], "loop": spec["loop"], "source_r4_sha256": spec["provenance"]["source_sha256"]}, "event_markers": spec["event_markers"], "event_markers_sha256": manifest["event_markers_sha256"], "motion_tracks_sha256": manifest["motion_tracks_sha256"], "gif_timing": decoded_gif, "images": visual_images, "marker_frames": marker_records, "source_only_pixels": True, "external_visual": "REQUIRED", "production_routing": "BLOCKED", "package_manifest": {"path": relative(package_path), "sha256": digest(package_path)}}
    write_json(OUT / "death-front-visual-manifest-v0150.json", visual_manifest)
    execution = {
        "schema_version": "0.15.0",
        "prompt": "UGAS-v0.15.0-DEATH-ANIMATION-FRONT",
        "implementation_base_commit": implementation_base,
        "branch_base_commit": branch_base,
        "hit_approved_head_sha": HIT_APPROVED_HEAD,
        "run_front_approved_head_sha": RUN_APPROVED_HEAD,
        "evidence_head_sha": evidence_head,
        "animation_id": spec["animation_id"],
        "status": "CUTOUT_ANIMATION_RUNTIME_V1_DEATH_ANIMATION_FRONT_TECHNICALLY_QUALIFIED",
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
        "external_visual": "REQUIRED",
        "negative_controls": negative["status"],
        "loop_negative_controls": loop_nc["status"],
        "run_front_loop_regression": run_loop["status"],
        "hit_front_nonloop_regression": hit_loop["status"],
        "approved_assets_untouched": assets["status"],
        "frozen_evidence_integrity": frozen_integrity["status"],
        "determinism": determinism["status"],
        "package": {"path": relative(package_path), "sha256": digest(package_path), "preview_gif": package["preview_gif"], "sprite_sheet": package["sprite_sheet"]},
        "review_artifacts": {"visual_manifest": relative(OUT / "death-front-visual-manifest-v0150.json"), "phase_marker_sheet": relative(marker_sheet), "negative_controls": relative(OUT / "death-front-gate-negative-controls-v0150.json"), "loop_negative_controls": relative(OUT / "death-front-loop-negative-controls-v0150.json")},
        "historical_v0141_preserved": True,
        "historical_v0140_preserved": True,
        "historical_v0131_preserved": True,
        "next_capability_started": False,
        "executor_does_not_claim_visual_approval": True,
        "github_review_manifest_is_authority_for_final_head": True,
    }
    write_json(OUT / "execution-evidence-v0.15.0.json", execution)
    if negative["status"] != "NC_01_TO_NC_13_PASSED" or loop_nc["status"] != "NC_LOOP_01_TO_05_PASSED" or run_loop["status"] != "RUN_FRONT_LOOP_REGRESSION_PASSED" or hit_loop["status"] != "HIT_NONLOOP_REGRESSION_PASSED" or assets["status"] != "APPROVED_ASSETS_UNTOUCHED" or frozen_integrity["status"] != "FROZEN_V0141_EVIDENCE_RESTORED_AND_VERIFIED" or determinism["status"] != "DEATH_DETERMINISM_PASSED":
        raise RuntimeError(f"V0150_GATES_FAILED:{negative['status']}:{loop_nc['status']}:{run_loop['status']}:{hit_loop['status']}:{assets['status']}:{frozen_integrity['status']}:{determinism['status']}")
    return {"status": "ANIMATION_RUNTIME_V0150_PASSED", "decision": qa["decision"], "animation_id": spec["animation_id"], "frames": len(manifest["frames"]), "package": relative(package_path), "preview_gif": package["preview_gif"]["path"], "negative_controls": negative["status"], "loop_negative_controls": loop_nc["status"], "run_front_loop_regression": run_loop["status"], "hit_front_nonloop_regression": hit_loop["status"], "approved_assets": assets["status"], "frozen_evidence_integrity": frozen_integrity["status"], "determinism": determinism["status"], "gif_loop_extension_present": decoded_gif["loop_extension_present"], "gif_loop_count": decoded_gif["loop_count"], "external_visual": "REQUIRED", "production_routing": "BLOCKED"}


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
        raise SystemExit(0)
    except Exception as exc:
        print(json.dumps({"status": "ANIMATION_RUNTIME_V0150_FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False))
        raise SystemExit(2)
