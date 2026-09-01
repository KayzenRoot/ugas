"""Reusable deterministic animation runtime v1.

This module is deliberately profile-agnostic.  It validates a declarative
specification, delegates asset semantics to a named adapter, and performs
deterministic compile/QA/package lifecycle operations.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw

from .motion_curves import motion_tracks_sha256, validate_motion_tracks
from .schema_validation import SchemaValidationError, validate_instance, validate_schema_document


class AnimationContractError(ValueError):
    """Raised when a lifecycle operation cannot satisfy the runtime contract."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest_bytes(value: bytes) -> str:
    import hashlib
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _schema(root: Path, name: str) -> dict[str, Any]:
    value = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
    validate_schema_document(value)
    return value


def load_spec(path: Path, root: Path | None = None) -> dict[str, Any]:
    root = (root or _root()).resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_instance(value, _schema(root, "animation-spec-v1.json"))
    if value.get("schema_version") != "animation-spec-1.0":
        raise AnimationContractError("spec_schema_version_invalid")
    count = value.get("frame_count")
    if not isinstance(count, int) or not 2 <= count <= 64:
        raise AnimationContractError("frame_count_must_be_between_2_and_64")
    has_fps, has_duration = "fps" in value, "per_frame_duration_ms" in value
    if has_fps == has_duration:
        raise AnimationContractError("exactly_one_timing_representation_required")
    bindings = value.get("key_pose_bindings", [])
    if len(bindings) < 2 or len({int(item["frame"]) for item in bindings}) != len(bindings):
        raise AnimationContractError("key_pose_bindings_must_have_two_or_more_unique_frames")
    if any(int(item["frame"]) >= count for item in bindings):
        raise AnimationContractError("key_pose_binding_out_of_range")
    if not value["presentation_transform"].get("frozen_before_render") or not value["interpolation_profile"].get("parameters_frozen_before_render", False):
        raise AnimationContractError("render_parameters_must_be_frozen_before_render")
    if value["provenance"]["sam2_used"] or value["provenance"]["comfyui_generation_jobs"] != 0 or value["provenance"]["diffusion_used"] or not value["provenance"]["source_only_pixels"]:
        raise AnimationContractError("forbidden_generation_or_non_source_pixels")
    _validate_event_markers(value)
    validate_motion_tracks(value)
    adapter_name = str(value["runtime_adapter"])
    if any(part in adapter_name for part in ("__", "/", "\\")):
        raise AnimationContractError("runtime_adapter_import_invalid")
    return value


def motion_track_fields(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Return optional hash-bound motion-track fields without changing legacy output."""
    tracks = validate_motion_tracks(spec)
    if not tracks:
        return {}
    return {"motion_tracks": tracks, "motion_tracks_sha256": motion_tracks_sha256(spec)}


def _assert_motion_track_binding(value: Mapping[str, Any], expected: Mapping[str, Any], label: str) -> None:
    for key in ("motion_tracks", "motion_tracks_sha256"):
        if key in expected and value.get(key) != expected[key]:
            raise AnimationContractError(f"{label}_motion_track_binding_mismatch")
        if key not in expected and key in value:
            raise AnimationContractError(f"{label}_unexpected_motion_track_fields")


def normalized_timing(spec: Mapping[str, Any]) -> dict[str, float]:
    """Return the runtime timing pair without changing the source spec."""
    has_fps, has_duration = "fps" in spec, "per_frame_duration_ms" in spec
    if has_fps == has_duration:
        raise AnimationContractError("exactly_one_timing_representation_required")
    if has_fps:
        fps = float(spec["fps"])
        if fps <= 0:
            raise AnimationContractError("fps_must_be_positive")
        return {"fps": fps, "per_frame_duration_ms": 1000.0 / fps}
    duration = float(spec["per_frame_duration_ms"])
    if duration <= 0:
        raise AnimationContractError("per_frame_duration_ms_must_be_positive")
    return {"fps": 1000.0 / duration, "per_frame_duration_ms": duration}


def event_markers_for_spec(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the frozen, profile-agnostic timeline markers."""
    markers = spec.get("event_markers", [])
    if not isinstance(markers, list):
        raise AnimationContractError("event_markers_must_be_an_array")
    return [dict(marker) for marker in markers]


def event_markers_sha256(spec: Mapping[str, Any]) -> str:
    """Hash marker metadata independently so every lifecycle artifact is bound."""
    return digest_bytes(canonical_json(event_markers_for_spec(spec)).encode("utf-8"))


def _validate_event_markers(spec: Mapping[str, Any]) -> None:
    markers = event_markers_for_spec(spec)
    count = int(spec["frame_count"])
    event_ids: set[str] = set()
    for marker in markers:
        event_id = str(marker.get("event_id", ""))
        if event_id in event_ids:
            raise AnimationContractError("event_id_must_be_unique")
        event_ids.add(event_id)
        frame = marker.get("frame")
        if not isinstance(frame, int) or not 0 <= frame < count:
            raise AnimationContractError("event_marker_frame_out_of_range")
    canonical = sorted(markers, key=lambda item: (int(item["frame"]), str(item["event_id"])))
    if markers != canonical:
        raise AnimationContractError("event_markers_must_be_canonical_by_frame_and_event_id")


def _frame_is_valid(record: Mapping[str, Any]) -> bool:
    if isinstance(record.get("passed"), bool):
        return bool(record["passed"])
    if isinstance(record.get("valid"), bool):
        return bool(record["valid"])
    gates = record.get("hard_gates")
    if isinstance(gates, Mapping) and gates and all(isinstance(value, bool) for value in gates.values()):
        return all(value is True for value in gates.values())
    status = str(record.get("status", ""))
    return status.endswith("_PASSED") or status.endswith("_QUALIFIED")


def evaluate_lifecycle(spec: Mapping[str, Any], frame_records: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply loop/non-loop lifecycle rules without knowing profile semantics."""
    expected = list(range(int(spec["frame_count"])))
    actual = [int(record.get("index", -1)) for record in frame_records]
    frame_validity = [{"index": int(record.get("index", -1)), "valid": _frame_is_valid(record)} for record in frame_records]
    sequential = [{"from_frame": index - 1, "to_frame": index} for index in range(1, len(frame_records))]
    loop = bool(spec["loop"])
    if loop and frame_records:
        transitions = [*sequential, {"from_frame": len(frame_records) - 1, "to_frame": 0, "closing": True}]
        closing_evaluated = True
        closing_valid = _frame_is_valid(frame_records[-1]) and _frame_is_valid(frame_records[0])
    else:
        transitions = sequential
        closing_evaluated = False
        closing_valid = None
    markers = event_markers_for_spec(spec)
    gates = {
        "frame_indices_are_sequential": actual == expected,
        "all_frames_valid": bool(frame_records) and all(item["valid"] for item in frame_validity),
        "final_frame_valid": bool(frame_records) and frame_validity[-1]["valid"],
        "event_markers_within_timeline": all(0 <= int(item["frame"]) < len(frame_records) for item in markers),
        "closing_transition_evaluated_for_loop": closing_evaluated if loop else True,
        "closing_transition_omitted_for_non_loop": not closing_evaluated if not loop else True,
        "closing_transition_valid": closing_valid if loop else True,
    }
    return {
        "loop": loop,
        "frame_validity": frame_validity,
        "transitions": transitions,
        "closing_transition_evaluated": closing_evaluated,
        "closing_transition": {"from_frame": len(frame_records) - 1, "to_frame": 0, "evaluated": closing_evaluated, "valid": closing_valid},
        "event_markers": markers,
        "event_markers_sha256": event_markers_sha256(spec),
        "hard_gates": gates,
        "status": "ANIMATION_LIFECYCLE_PASSED" if all(gates.values()) else "ANIMATION_LIFECYCLE_GAP",
    }


def _adapter(spec: Mapping[str, Any]):
    return importlib.import_module(str(spec["runtime_adapter"]))


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def compile_spec(spec_path: Path, output_dir: Path, root: Path | None = None) -> Path:
    root = (root or _root()).resolve()
    spec_path = spec_path.resolve()
    spec = load_spec(spec_path, root)
    adapter = _adapter(spec)
    context = adapter.load_context(spec, root)
    prepared = adapter.prepare(spec, context)
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    for index in range(int(spec["frame_count"])):
        image, metadata = adapter.render_frame(spec, context, prepared, index)
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        frame_path = output_dir / f"frame-{index:02d}.png"
        image.save(frame_path, format="PNG", optimize=False)
        frames.append({"index": index, "phase": str(metadata.get("phase", f"frame-{index:02d}")), "path": _relative(frame_path, root), "rgba_sha256": digest_file(frame_path), "target_hash": str(metadata["target_hash"]), "metadata": {key: value for key, value in metadata.items() if key != "image"}})
    manifest = {
        "schema_version": "animation-compiled-manifest-1.0", "animation_id": spec["animation_id"], "spec_path": _relative(spec_path, root), "spec_sha256": digest_file(spec_path),
        "source": {"asset_revision_id": spec["asset_revision_id"], "direction": spec["direction"], "source_sha256": spec["provenance"]["source_sha256"], "source_rig_ref": spec["source_rig_ref"]},
        "frames": frames, "event_markers": event_markers_for_spec(spec), "event_markers_sha256": event_markers_sha256(spec), "compile_status": "COMPILED", "runtime_adapter": spec["runtime_adapter"],
        "determinism": {"pixel_operation": "source-affine-resample-and-alpha-composite", "parameters_frozen_before_render": True, "source_only_pixels": True, "replay_rule": "same spec source hashes adapter and Pillow encoder produce same RGBA bytes"},
    }
    manifest.update(motion_track_fields(spec))
    manifest_path = output_dir / "compiled-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    validate_instance(manifest, _schema(root, "animation-compiled-manifest-v1.json"))
    return manifest_path


def qa_compiled(manifest_path: Path, root: Path | None = None) -> Path:
    root = (root or _root()).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_instance(manifest, _schema(root, "animation-compiled-manifest-v1.json"))
    spec_path = root / manifest["spec_path"]
    spec = load_spec(spec_path, root)
    if manifest["animation_id"] != spec["animation_id"] or manifest["spec_sha256"] != digest_file(spec_path):
        raise AnimationContractError("compiled_manifest_spec_binding_mismatch")
    _assert_motion_track_binding(manifest, motion_track_fields(spec), "compiled_manifest")
    adapter = _adapter(spec)
    context = adapter.load_context(spec, root)
    result = adapter.qa(spec, context, manifest, root)
    required = {"animation_id", "decision", "status", "frames", "temporal", "provenance", "hard_gates", "failures"}
    missing = sorted(required.difference(result))
    if missing:
        raise AnimationContractError(f"qa_result_contract_missing:{','.join(missing)}")
    if result["animation_id"] != spec["animation_id"]:
        raise AnimationContractError("qa_animation_id_mismatch")
    lifecycle = evaluate_lifecycle(spec, list(result["frames"]))
    result["temporal"] = {**dict(result["temporal"]), "lifecycle": lifecycle}
    result["hard_gates"] = {**dict(result["hard_gates"]), "generic_lifecycle": lifecycle["status"] == "ANIMATION_LIFECYCLE_PASSED"}
    result["failures"] = [*list(result["failures"]), *[f"lifecycle_{name}" for name, passed in lifecycle["hard_gates"].items() if not passed]]
    result = {"schema_version": "animation-qa-result-1.1", **result, "event_markers": event_markers_for_spec(spec), "event_markers_sha256": event_markers_sha256(spec), "spec_sha256": digest_file(spec_path), "compiled_manifest_sha256": digest_file(manifest_path)}
    result.update(motion_track_fields(spec))
    validate_instance(result, _schema(root, "animation-qa-result-v1.json"))
    output = manifest_path.parent / "qa-result.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def _checkerboard(image: Image.Image) -> Image.Image:
    base = Image.new("RGBA", image.size, (235, 235, 235, 255))
    draw = ImageDraw.Draw(base)
    for y in range(0, image.height, 16):
        for x in range(0, image.width, 16):
            if (x // 16 + y // 16) % 2:
                draw.rectangle((x, y, x + 15, y + 15), fill=(185, 185, 185, 255))
    base.alpha_composite(image.convert("RGBA"))
    return base


def package_compiled(manifest_path: Path, root: Path | None = None) -> Path:
    root = (root or _root()).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_instance(manifest, _schema(root, "animation-compiled-manifest-v1.json"))
    spec = load_spec(root / manifest["spec_path"], root)
    if manifest["animation_id"] != spec["animation_id"] or manifest["spec_sha256"] != digest_file(root / manifest["spec_path"]):
        raise AnimationContractError("compiled_manifest_spec_binding_mismatch")
    expected_motion_tracks = motion_track_fields(spec)
    _assert_motion_track_binding(manifest, expected_motion_tracks, "compiled_manifest")
    qa_path = manifest_path.parent / "qa-result.json"
    if not qa_path.is_file():
        raise AnimationContractError("package_requires_qa_result")
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    validate_instance(qa, _schema(root, "animation-qa-result-v1.json"))
    if qa.get("animation_id") != spec["animation_id"]:
        raise AnimationContractError("qa_animation_id_mismatch")
    if qa.get("spec_sha256") != digest_file(root / manifest["spec_path"]):
        raise AnimationContractError("qa_spec_hash_mismatch")
    if qa.get("compiled_manifest_sha256") != digest_file(manifest_path):
        raise AnimationContractError("qa_compiled_manifest_hash_mismatch")
    _assert_motion_track_binding(qa, expected_motion_tracks, "qa")
    expected_markers = event_markers_for_spec(spec)
    expected_marker_hash = event_markers_sha256(spec)
    if manifest.get("event_markers", expected_markers) != expected_markers or manifest.get("event_markers_sha256", expected_marker_hash) != expected_marker_hash:
        raise AnimationContractError("compiled_manifest_event_markers_mismatch")
    if qa.get("event_markers", expected_markers) != expected_markers or qa.get("event_markers_sha256", expected_marker_hash) != expected_marker_hash:
        raise AnimationContractError("qa_event_markers_mismatch")
    hard_gates = qa.get("hard_gates")
    if qa.get("decision") != "QUALIFIED" or not isinstance(hard_gates, dict) or not hard_gates or any(value is not True for value in hard_gates.values()) or qa.get("failures") != []:
        raise AnimationContractError("package_requires_qualified_qa")
    profile = spec["package_profile"]
    cell_w, cell_h = int(profile["cell_size"]["width"]), int(profile["cell_size"]["height"])
    columns, rows = int(profile["columns"]), int(profile["rows"])
    images = [Image.open(root / item["path"]).convert("RGBA") for item in manifest["frames"]]
    sheet = Image.new("RGBA", (columns * cell_w, rows * cell_h), (0, 0, 0, 0))
    for index, image in enumerate(images):
        sheet.alpha_composite(image.resize((cell_w, cell_h), Image.Resampling.LANCZOS), ((index % columns) * cell_w, (index // columns) * cell_h))
    sprite_path = manifest_path.parent / str(profile.get("sprite_name", "spritesheet.png"))
    sheet.save(sprite_path, format="PNG", optimize=False)
    timing = normalized_timing(spec)
    fps, duration = timing["fps"], timing["per_frame_duration_ms"]
    gif_path = manifest_path.parent / str(profile.get("gif_name", "preview.gif"))
    gif_frames = [_checkerboard(image).convert("RGB") for image in images]
    gif_frames[0].save(gif_path, format="GIF", save_all=True, append_images=gif_frames[1:], duration=int(round(duration)), loop=0, disposal=2, optimize=False)
    metadata_path = manifest_path.parent / "metadata.json"
    metadata = {"schema_version": "animation-package-1.0", "animation_id": spec["animation_id"], "direction": spec["direction"], "frame_count": len(images), "fps": fps, "per_frame_duration_ms": duration, "loop": bool(spec["loop"]), "event_markers": expected_markers, "event_markers_sha256": expected_marker_hash, "cell_size": {"width": cell_w, "height": cell_h}, "sheet_size": {"width": columns * cell_w, "height": rows * cell_h}, "format": "RGBA", "frames": manifest["frames"], "parameters_frozen_before_render": True, "adapter_metadata": dict(qa.get("package_metadata", {}))}
    metadata.update(expected_motion_tracks)
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    package = {"schema_version": "animation-package-1.0", "package_id": f"ugas-{spec['animation_id']}-package", "animation_id": spec["animation_id"], "direction": spec["direction"], "frame_count": len(images), "fps": fps, "per_frame_duration_ms": duration, "loop": bool(spec["loop"]), "event_markers": expected_markers, "event_markers_sha256": expected_marker_hash, "format": "RGBA", "cell_size": {"width": cell_w, "height": cell_h}, "sheet_size": {"width": columns * cell_w, "height": rows * cell_h}, "sprite_sheet": {"path": _relative(sprite_path, root), "sha256": digest_file(sprite_path)}, "metadata": {"path": _relative(metadata_path, root), "sha256": digest_file(metadata_path)}, "preview_gif": {"path": _relative(gif_path, root), "sha256": digest_file(gif_path)}, "registry_state": "pilot/technical-qualified", "production_approved": False, "production_routing": "BLOCKED", "qa_status": qa["status"], "qa_decision": qa["decision"], "adapter_metadata": dict(qa.get("package_metadata", {})), "source_rig_revision": spec["asset_revision_id"], "source_rig_sha256": digest_file(root / spec["source_rig_ref"]), "r4_source_sha256": spec["provenance"]["source_sha256"]}
    package.update(expected_motion_tracks)
    package_path = manifest_path.parent / "package-manifest.json"
    package_path.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    validate_instance(package, _schema(root, "animation-package-v1.json"))
    return package_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ugas.animation")
    sub = parser.add_subparsers(dest="action", required=True)
    validate = sub.add_parser("validate-spec"); validate.add_argument("spec", type=Path)
    compile_parser = sub.add_parser("compile"); compile_parser.add_argument("spec", type=Path); compile_parser.add_argument("--output", required=True, type=Path)
    qa = sub.add_parser("qa"); qa.add_argument("manifest", type=Path)
    package = sub.add_parser("package"); package.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "validate-spec":
            spec = load_spec(args.spec); print(json.dumps({"status": "ANIMATION_SPEC_VALID", "animation_id": spec["animation_id"], "frame_count": spec["frame_count"]}, indent=2)); return 0
        if args.action == "compile":
            print(compile_spec(args.spec, args.output)); return 0
        if args.action == "qa":
            path = qa_compiled(args.manifest); print(path); return 0
        path = package_compiled(args.manifest); print(path); return 0
    except (OSError, KeyError, TypeError, ValueError, SchemaValidationError, AnimationContractError) as exc:
        print(json.dumps({"status": "ANIMATION_RUNTIME_FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
