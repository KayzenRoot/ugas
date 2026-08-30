"""API-format workflow registry and live node/model validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class WorkflowRegistryError(RuntimeError):
    pass


def workflow_hash(workflow: dict) -> str:
    encoded = json.dumps(workflow, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_workflows(repo_root: Path) -> list[dict]:
    registry = repo_root / "providers" / "workflows" / "registry.json"
    if registry.exists():
        return json.loads(registry.read_text(encoding="utf-8")).get("workflows", [])
    return []


def load_workflow(repo_root: Path, workflow_id: str) -> dict:
    for item in load_workflows(repo_root):
        if item.get("id") == workflow_id:
            path = repo_root / item["api_json"]
            value = json.loads(path.read_text(encoding="utf-8"))
            return {**item, "api": value, "sha256": workflow_hash(value)}
    raise WorkflowRegistryError(f"Unknown workflow id: {workflow_id}")


def validate_api_workflow(workflow: dict, node_info: dict | None = None, model_names: set[str] | None = None) -> dict:
    if not isinstance(workflow, dict) or not workflow:
        raise WorkflowRegistryError("Workflow must be a non-empty API graph")
    missing_nodes: list[str] = []
    missing_models: list[str] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict) or "class_type" not in node or "inputs" not in node:
            raise WorkflowRegistryError(f"Invalid API node: {node_id}")
        class_type = node["class_type"]
        if node_info is not None and class_type not in node_info:
            missing_nodes.append(class_type)
        if model_names is not None:
            for key, value in node.get("inputs", {}).items():
                if key in {"unet_name", "clip_name", "vae_name", "bg_removal_name", "ckpt_name", "control_net_name", "ipadapter_file"} and isinstance(value, str) and value in {"__MODEL__", "__CLIP__", "__VAE__", "__BG_MODEL__", "__SDXL_CHECKPOINT__", "__CONTROLNET__", "__IPADAPTER__", "__CLIP_VISION__"}:
                    continue
                if key in {"unet_name", "clip_name", "vae_name", "bg_removal_name", "ckpt_name", "control_net_name", "ipadapter_file"} and isinstance(value, str) and value not in model_names:
                    missing_models.append(value)
    return {"valid_graph": True, "node_count": len(workflow), "missing_nodes": sorted(set(missing_nodes)), "missing_models": sorted(set(missing_models)), "live_valid": not missing_nodes and not missing_models}


def bind_workflow(template: dict, *, prompt: str, negative_prompt: str = "", seed: int = 1, width: int = 512, height: int = 512, model_names: dict[str, str] | None = None, image_filename: str | None = None, image_filenames: list[str] | None = None, lora_name: str | None = None, lora_strength: float | None = None) -> dict:
    """Bind stable public inputs without altering graph topology.

    ``image_filename`` remains the v0.4 compatibility input.  v0.5 workflows
    use explicit ``__IMAGE__`` and ``__GUIDE__`` markers so the binding order
    is auditable: reference zero is the canonical identity anchor and reference
    one is the deterministic pose/view guide.
    """
    value = json.loads(json.dumps(template))
    filenames = list(image_filenames or ([] if image_filename is None else [image_filename]))
    marker_map = {
        "__IMAGE__": filenames[0] if len(filenames) > 0 else None,
        "__GUIDE__": filenames[1] if len(filenames) > 1 else None,
        "__IDENTITY__": filenames[0] if len(filenames) > 0 else None,
        "__POSE__": filenames[1] if len(filenames) > 1 else None,
        "__REFERENCE_0__": filenames[0] if len(filenames) > 0 else None,
        "__REFERENCE_1__": filenames[1] if len(filenames) > 1 else None,
        "__LORA__": lora_name,
    }
    for node in value.values():
        if node.get("class_type") == "CLIPTextEncode":
            text = node.setdefault("inputs", {}).get("text")
            node["inputs"]["text"] = negative_prompt if text == "__NEGATIVE__" else prompt
        inputs = node.setdefault("inputs", {})
        for key, marker in (("unet_name", "__MODEL__"), ("clip_name", "__CLIP__"), ("vae_name", "__VAE__"), ("ckpt_name", "__SDXL_CHECKPOINT__"), ("control_net_name", "__CONTROLNET__"), ("ipadapter_file", "__IPADAPTER__")):
            if inputs.get(key) == marker and model_names and marker in model_names:
                inputs[key] = model_names[marker]
        if inputs.get("clip_name") == "__CLIP_VISION__" and model_names and "__CLIP_VISION__" in model_names:
            inputs["clip_name"] = model_names["__CLIP_VISION__"]
        if inputs.get("bg_removal_name") == "__BG_MODEL__" and model_names and "__BG_MODEL__" in model_names:
            inputs["bg_removal_name"] = model_names["__BG_MODEL__"]
        if inputs.get("lora_name") == "__LORA__" and lora_name:
            inputs["lora_name"] = lora_name
        if inputs.get("strength_model") == "__LORA_STRENGTH__" and lora_strength is not None:
            inputs["strength_model"] = float(lora_strength)
        if inputs.get("seed") == "__SEED__":
            inputs["seed"] = int(seed)
        for key, marker in (("strength", "__CONTROLNET_STRENGTH__"), ("weight", "__IP_STRENGTH__")):
            if inputs.get(key) == marker and model_names and marker in model_names:
                inputs[key] = float(model_names[marker])
        for key in ("filename", "image"):
            marker = inputs.get(key)
            if isinstance(marker, str) and marker in marker_map and marker_map[marker]:
                inputs[key] = marker_map[marker]
        if "noise_seed" in inputs and inputs["noise_seed"] == "__SEED__":
            inputs["noise_seed"] = int(seed)
        for key in ("width", "height"):
            if inputs.get(key) == "__DIMENSION__":
                inputs[key] = int(width if key == "width" else height)
            if inputs.get(key) == "__WIDTH__":
                inputs[key] = int(width)
            if inputs.get(key) == "__HEIGHT__":
                inputs[key] = int(height)
    return value


def output_nodes(workflow: dict) -> list[str]:
    return [node_id for node_id, node in workflow.items() if node.get("class_type") in {"SaveImage", "PreviewImage"}]
