"""Capability evidence state machine; health alone can never become ready."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .comfyui_client import ComfyUIClient, ComfyUIError
from .model_registry import load_model, inventory_matches
from .workflow_registry import load_workflow, validate_api_workflow

STATES = {"unknown", "unavailable", "declared", "ready", "verified"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def declared_evidence(repo_root: Path, provider: str = "provider-comfyui", capability: str = "2d") -> dict:
    return {
        "schema_version": "0.3.0",
        "provider": provider,
        "capability": capability,
        "state": "declared",
        "endpoint": None,
        "server_version": None,
        "devices": [],
        "required_nodes": [],
        "required_models": [],
        "workflow": {},
        "model": {},
        "transport_capabilities": ["workflow-submit", "polling", "output-retrieval", "system-stats"],
        "asset_capabilities_declared": [capability],
        "asset_capabilities_qualified": [],
        "smoke_test": {"status": "not-run"},
        "failure_reason": None,
        "observed_at": _now(),
    }


def probe_comfy_capability(repo_root: Path, client: ComfyUIClient, model_id: str, workflow_id: str, capability: str = "2d") -> dict:
    evidence = declared_evidence(repo_root, capability=capability)
    evidence["endpoint"] = client.base_url
    try:
        stats = client.health()
        features = client.features()
        node_info = client.node_info()
        model_types = client.list_model_types()
        inventories = {folder: client.list_models(folder) for folder in model_types if isinstance(folder, str)}
        model = load_model(repo_root, model_id)
        workflow = load_workflow(repo_root, workflow_id)
        model_check = inventory_matches(model, inventories)
        workflow_check = validate_api_workflow(workflow["api"], node_info=node_info, model_names={name for values in inventories.values() for name in values})
        qualified_capabilities = workflow.get("qualified_capabilities") or (["2d", "sprite-master", "sprite-generation"] if workflow.get("capability") == "2d" else [workflow.get("capability")])
        evidence.update({"server_version": stats.get("system", {}).get("comfyui_version") or stats.get("version"), "devices": stats.get("devices", []), "required_nodes": [{"class_type": n, "present": n in node_info} for n in workflow["api"].values() for n in [n.get("class_type")] if n], "required_models": model_check["files"], "workflow": {"id": workflow_id, "version": workflow.get("version"), "sha256": workflow["sha256"], "validation": workflow_check, "qualified_capabilities": qualified_capabilities}, "model": {"id": model_id, "license": model.get("license"), "sha256": model.get("sha256"), "inventory": model_check}, "asset_capabilities_declared": qualified_capabilities, "asset_capabilities_qualified": qualified_capabilities if model.get("status") == "qualified" and model_check["inventory_complete"] and workflow_check["live_valid"] else [], "features": features})
        if model.get("commercial_use_status") != "approved":
            evidence["state"] = "unavailable"
            evidence["failure_reason"] = "model license is not approved for commercial use"
        elif model.get("status") != "qualified" or not model.get("qualification_evidence", {}).get("hashes_verified", False):
            evidence["state"] = "unavailable"
            evidence["failure_reason"] = "model manifest is not hash-qualified"
        elif not model_check["inventory_complete"] or not workflow_check["live_valid"]:
            evidence["state"] = "unavailable"
            evidence["failure_reason"] = "required model files or native nodes are missing"
        else:
            evidence["state"] = "ready"
    except (ComfyUIError, OSError, ValueError, KeyError) as exc:
        evidence["state"] = "unavailable"
        evidence["failure_reason"] = str(exc)[:500]
    return evidence


def mark_verified(evidence: dict, smoke: dict) -> dict:
    result = dict(evidence)
    result["smoke_test"] = smoke
    if evidence.get("state") == "ready" and smoke.get("status") == "passed":
        result["state"] = "verified"
        result["failure_reason"] = None
    elif evidence.get("state") == "ready":
        result["state"] = "ready"
        result["failure_reason"] = smoke.get("error") or "smoke test did not pass"
    return result
