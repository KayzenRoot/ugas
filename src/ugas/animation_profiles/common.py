"""Shared source-only cutout loading and rendering primitives.

The generic runtime owns lifecycle and packaging; this module owns only the
qualified R4 cutout adapter primitives shared by the profile adapters.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from ..cutout_rig import PART_NAMES, render_part, skeleton_point, transform_parameters
from ..cutout_structural import build_structural_core, compose_with_structural_core, exclude_protected_regions, source_core_rgba
from ..cutout_temporal_v081 import apply_presentation_transform, target_digest, transform_target_for_presentation


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def weapon_tip_from_alpha(part: Image.Image, wrist: tuple[float, float]) -> dict[str, float]:
    """Use the same deterministic farthest-alpha rule as the qualified rig."""
    alpha = part.convert("RGBA").getchannel("A")
    points = [(x, y) for y in range(alpha.height) for x in range(alpha.width) if alpha.getpixel((x, y)) > 0]
    if not points:
        raise ValueError("empty_weapon_source")
    point = max(points, key=lambda xy: (math.dist(wrist, xy), xy[1], xy[0]))
    return {"x": round(float(point[0]), 4), "y": round(float(point[1]), 4)}


def load_source_context(spec: Mapping[str, Any], root: Path) -> dict[str, Any]:
    provenance = spec["provenance"]
    source_path = root / str(provenance["source_image"])
    skeleton_path = root / str(provenance["source_skeleton"])
    parts_dir = root / str(provenance["source_parts_dir"])
    masks_dir = root / str(provenance["source_masks_dir"])
    for path in (source_path, skeleton_path, parts_dir, masks_dir):
        if not path.exists():
            raise ValueError(f"missing_source_provenance:{path}")
    source = Image.open(source_path).convert("RGBA")
    if sha256_file(source_path) != str(provenance["source_sha256"]):
        raise ValueError("source_sha256_mismatch")
    parts = {name: Image.open(parts_dir / f"{name}.png").convert("RGBA") for name in PART_NAMES}
    masks = {name: Image.open(masks_dir / f"{name}.png").convert("L") for name in PART_NAMES}
    skeleton_doc = read_json(skeleton_path)
    skeleton = copy.deepcopy(skeleton_doc.get("skeleton", skeleton_doc))
    skeleton["weapon_tip"] = weapon_tip_from_alpha(parts["sword"], skeleton_point(skeleton, "wrist_right"))
    core = build_structural_core(source, source.getchannel("A"), masks["torso_pelvis"], masks, skeleton)
    return {"source": source, "parts": parts, "masks": masks, "skeleton": skeleton, "core": core, "source_path": source_path, "source_sha256": sha256_file(source_path), "part_hashes": {name: sha256_bytes(parts[name].tobytes()) for name in PART_NAMES}, "mask_hashes": {name: sha256_bytes(masks[name].tobytes()) for name in PART_NAMES}}


def render_source_only(context: Mapping[str, Any], target: Mapping[str, Any], z_order: list[str], presentation: Mapping[str, Any]) -> tuple[Image.Image, dict[str, Any]]:
    source = context["source"]
    parts = context["parts"]
    skeleton = context["skeleton"]
    layers: dict[str, Image.Image] = {}
    transforms: list[dict[str, Any]] = []
    for name in z_order:
        params = transform_parameters(skeleton, target, name)
        layers[name] = render_part(parts[name], tuple(params["source_pivot"]), tuple(params["target_pivot"]), tuple(params["source_end"]), tuple(params["target_end"]), source.size)
        transforms.append({"part": name, **params, "z_order_index": z_order.index(name), "source_part_rgba_sha256": context["part_hashes"][name], "pixel_operation": "source_affine_resample"})
    torso_transform = next(item for item in transforms if item["part"] == "torso_pelvis")
    core_layer = render_part(source_core_rgba(source, context["core"]["core_mask"]), tuple(torso_transform["source_pivot"]), tuple(torso_transform["target_pivot"]), tuple(torso_transform["source_end"]), tuple(torso_transform["target_end"]), source.size)
    core_layer = exclude_protected_regions(core_layer, layers)
    canonical = compose_with_structural_core(layers, z_order, core_layer)
    presented_layers = {name: apply_presentation_transform(layer, presentation) for name, layer in layers.items()}
    presented_core = apply_presentation_transform(core_layer, presentation)
    output = apply_presentation_transform(canonical, presentation)
    return output, {"layers": layers, "presented_layers": presented_layers, "core_layer": core_layer, "presented_core": presented_core, "canonical": canonical, "transforms": transforms, "target_presented": transform_target_for_presentation(target, presentation)}


def image_digest(image: Image.Image) -> str:
    return sha256_bytes(image.convert("RGBA").tobytes())
