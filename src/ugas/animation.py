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
    adapter_name = str(value["runtime_adapter"])
    if any(part in adapter_name for part in ("__", "/", "\\")):
        raise AnimationContractError("runtime_adapter_import_invalid")
    return value


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
        "frames": frames, "compile_status": "COMPILED", "runtime_adapter": spec["runtime_adapter"],
        "determinism": {"pixel_operation": "source-affine-resample-and-alpha-composite", "parameters_frozen_before_render": True, "source_only_pixels": True, "replay_rule": "same spec source hashes adapter and Pillow encoder produce same RGBA bytes"},
    }
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
    adapter = _adapter(spec)
    context = adapter.load_context(spec, root)
    result = adapter.qa(spec, context, manifest, root)
    required = {"animation_id", "decision", "status", "frames", "temporal", "provenance", "hard_gates", "failures"}
    missing = sorted(required.difference(result))
    if missing:
        raise AnimationContractError(f"qa_result_contract_missing:{','.join(missing)}")
    if result["animation_id"] != spec["animation_id"]:
        raise AnimationContractError("qa_animation_id_mismatch")
    result = {"schema_version": "animation-qa-result-1.1", **result, "spec_sha256": digest_file(spec_path), "compiled_manifest_sha256": digest_file(manifest_path)}
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
    metadata = {"schema_version": "animation-package-1.0", "animation_id": spec["animation_id"], "direction": spec["direction"], "frame_count": len(images), "fps": fps, "per_frame_duration_ms": duration, "loop": bool(spec["loop"]), "cell_size": {"width": cell_w, "height": cell_h}, "sheet_size": {"width": columns * cell_w, "height": rows * cell_h}, "format": "RGBA", "frames": manifest["frames"], "parameters_frozen_before_render": True}
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    package = {"schema_version": "animation-package-1.0", "package_id": f"ugas-{spec['animation_id']}-package", "animation_id": spec["animation_id"], "direction": spec["direction"], "frame_count": len(images), "fps": fps, "per_frame_duration_ms": duration, "loop": bool(spec["loop"]), "format": "RGBA", "cell_size": {"width": cell_w, "height": cell_h}, "sheet_size": {"width": columns * cell_w, "height": rows * cell_h}, "sprite_sheet": {"path": _relative(sprite_path, root), "sha256": digest_file(sprite_path)}, "metadata": {"path": _relative(metadata_path, root), "sha256": digest_file(metadata_path)}, "preview_gif": {"path": _relative(gif_path, root), "sha256": digest_file(gif_path)}, "registry_state": "pilot/technical-qualified", "production_approved": False, "production_routing": "BLOCKED", "qa_status": qa["status"], "qa_decision": qa["decision"], "source_rig_revision": spec["asset_revision_id"], "source_rig_sha256": digest_file(root / spec["source_rig_ref"]), "r4_source_sha256": spec["provenance"]["source_sha256"]}
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
