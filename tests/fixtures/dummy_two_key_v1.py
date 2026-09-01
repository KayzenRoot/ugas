"""Minimal non-production adapter for generic runtime qualification tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from PIL import Image


def load_context(spec: Mapping[str, Any], root: Path) -> dict[str, Any]:
    return {"fixture": "controlled-1x-transparent-source"}


def prepare(spec: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    return {"frames": int(spec["frame_count"])}


def render_frame(spec: Mapping[str, Any], context: Mapping[str, Any], prepared: Mapping[str, Any], index: int):
    target = {"animation_id": spec["animation_id"], "frame": index, "direction": spec["direction"]}
    target_hash = hashlib.sha256(str(target).encode("utf-8")).hexdigest()
    return Image.new("RGBA", (1, 1), (0, 0, 0, 0)), {"phase": f"T{index}", "target_hash": target_hash}


def qa(spec: Mapping[str, Any], context: Mapping[str, Any], manifest: Mapping[str, Any], root: Path) -> dict[str, Any]:
    frames = manifest["frames"]
    gates = {"frame_count": len(frames) == int(spec["frame_count"]), "source_only_pixels": True}
    failures = [name for name, passed in gates.items() if not passed]
    return {"animation_id": spec["animation_id"], "decision": "QUALIFIED" if not failures else "FAILED", "status": "SYNTHETIC_FIXTURE_TECHNICALLY_OK", "frames": [{"index": item["index"], "passed": True} for item in frames], "temporal": {"timing": "per_frame_duration_ms"}, "provenance": {"source_only_pixels": True, "sam2_runs": 0, "comfyui_generation_jobs": 0, "diffusion_runs": 0}, "hard_gates": gates, "failures": failures}
