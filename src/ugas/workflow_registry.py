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
                if key in {"unet_name", "clip_name", "vae_name"} and isinstance(value, str) and value in {"__MODEL__", "__CLIP__", "__VAE__"}:
                    continue
                if key in {"unet_name", "clip_name", "vae_name"} and isinstance(value, str) and value not in model_names:
                    missing_models.append(value)
    return {"valid_graph": True, "node_count": len(workflow), "missing_nodes": sorted(set(missing_nodes)), "missing_models": sorted(set(missing_models)), "live_valid": not missing_nodes and not missing_models}


def bind_workflow(template: dict, *, prompt: str, negative_prompt: str = "", seed: int = 1, width: int = 512, height: int = 512, model_names: dict[str, str] | None = None) -> dict:
    """Bind the stable public inputs without altering graph topology."""
    value = json.loads(json.dumps(template))
    for node in value.values():
        if node.get("class_type") == "CLIPTextEncode":
            text = node.setdefault("inputs", {}).get("text")
            node["inputs"]["text"] = negative_prompt if text == "__NEGATIVE__" else prompt
        inputs = node.setdefault("inputs", {})
        for key, marker in (("unet_name", "__MODEL__"), ("clip_name", "__CLIP__"), ("vae_name", "__VAE__")):
            if inputs.get(key) == marker and model_names and marker in model_names:
                inputs[key] = model_names[marker]
        if "noise_seed" in inputs and inputs["noise_seed"] == "__SEED__":
            inputs["noise_seed"] = int(seed)
        for key in ("width", "height"):
            if inputs.get(key) == "__DIMENSION__":
                inputs[key] = int(width if key == "width" else height)
    return value


def output_nodes(workflow: dict) -> list[str]:
    return [node_id for node_id, node in workflow.items() if node.get("class_type") in {"SaveImage", "PreviewImage"}]
