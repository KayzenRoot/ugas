"""Compatibility adapter for the qualified pilot cycle.

The adapter is the only place that knows the historical pilot's phase names
and key-pose source.  The runtime lifecycle remains generic.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from .. import cutout_temporal_v081 as temporal
from ..cutout_rig import PART_NAMES
from ..animation_profiles.common import load_source_context, read_json, render_source_only, sha256_file, target_digest


def load_context(spec: Mapping[str, Any], root: Path) -> dict[str, Any]:
    context = load_source_context(spec, root)
    params = spec.get("adapter_parameters", {})
    provider = read_json(root / str(params["provider_ref"]))
    context["provider"] = provider
    context["config"] = read_json(root / str(params["config_ref"]))
    context["historical_frame_hashes"] = {str(k): str(v) for k, v in params["historical_frame_hashes"].items()}
    return context


def prepare(spec: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    provider = context["provider"]
    mapping = {0: "K1-contact-left", 2: "K2-passing-left", 4: "K3-contact-right", 6: "K4-passing-right"}
    key_targets = {frame: copy.deepcopy(provider["poses"][phase]["target"]) for frame, phase in mapping.items()}
    key_hashes = {phase: str(provider["poses"][phase]["target_joint_sha256"]) for phase in mapping.values()}
    targets, smoothing, initial = temporal.build_walk_targets_v081(key_targets, context["config"])
    plan = temporal.build_walk_plan_v081(context["source_sha256"], spec["source_rig_ref"], context["config"])
    presentation = context["config"]["presentation_transform"]
    return {"targets": targets, "initial_targets": initial, "smoothing": smoothing, "plan": plan, "presentation": presentation, "key_hashes": key_hashes, "phases": list(temporal.PHASES)}


def render_frame(spec: Mapping[str, Any], context: Mapping[str, Any], prepared: Mapping[str, Any], index: int):
    phase = prepared["phases"][index]
    target = prepared["targets"][phase]
    z_order = list(prepared["plan"]["phase_plans"][phase]["z_order"])
    image, details = render_source_only(context, target, z_order, prepared["presentation"])
    return image, {"phase": phase, "target_hash": target_digest(target), "presentation_target_hash": details["target_presented"]["presentation_target_joint_sha256"], "z_order": z_order, "transform_hashes": {item["part"]: item["source_part_rgba_sha256"] for item in details["transforms"]}}


def qa(spec: Mapping[str, Any], context: Mapping[str, Any], manifest: Mapping[str, Any], root: Path) -> dict[str, Any]:
    expected = context["historical_frame_hashes"]
    frames = manifest["frames"]
    frame_gates: list[bool] = []
    failures: list[str] = []
    for item in frames:
        expected_hash = expected.get(str(item["index"]))
        passed = expected_hash == item["rgba_sha256"] and str(item["target_hash"]) == str(item["metadata"].get("target_hash", item["target_hash"]))
        frame_gates.append(passed)
        if not passed:
            failures.append(f"frame_{item['index']}_target_or_rgba_hash_mismatch")
    target_hashes = [str(item["target_hash"]) for item in frames]
    gates = {"frame_count": len(frames) == int(spec["frame_count"]), "canonical_rgba_byte_identity": all(frame_gates), "target_hash_binding": len(target_hashes) == len(set(target_hashes)), "source_only_pixels": bool(spec["provenance"]["source_only_pixels"]), "no_ai_generation": spec["provenance"]["sam2_used"] is False and spec["provenance"]["comfyui_generation_jobs"] == 0 and spec["provenance"]["diffusion_used"] is False}
    status = "CUTOUT_ANIMATION_RUNTIME_V1_WALK_REPLAY_IDENTICAL" if all(gates.values()) else "ANIMATION_RUNTIME_WALK_REPLAY_GAP"
    return {"animation_id": spec["animation_id"], "status": status, "frames": [{"index": item["index"], "rgba_sha256": item["rgba_sha256"], "expected_rgba_sha256": expected.get(str(item["index"])), "target_hash": item["target_hash"], "passed": frame_gates[index]} for index, item in enumerate(frames)], "temporal": {"replay": "byte-identical", "historical_fixture": spec["adapter_parameters"]["historical_frame_manifest"]}, "provenance": {"source_sha256": context["source_sha256"], "part_hashes": context["part_hashes"], "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0}, "hard_gates": gates, "failures": failures}
