"""Contracts for the v0.6.2 P-only SDXL OpenPose model-card calibration."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from .workflow_registry import bind_workflow, validate_api_workflow, workflow_hash


PROMPT_ID = "PROMPT-05D-UGAS-SDXL-OPENPOSE-MODEL-CARD-CALIBRATION-v0.6.2"
PHASE = "SDXL_OPENPOSE_MODEL_CARD_CALIBRATION"
SEED = 62701
CONFIRMATION_SEEDS = (62711, 62712, 62713)
WORKFLOW_ID = "sdxl-openpose-controlnet-p"
MODEL_CARD_URL = "https://huggingface.co/xinsir/controlnet-openpose-sdxl-1.0"
MODEL_CARD_REVISION = "23f966cd5cfdd3f7729c903e243d87152162d2b7"
MODEL_CARD_LICENSE = "Apache-2.0"
MODEL_ID = "sdxl-base-1.0"
CONTROLNET_MODEL_ID = "xinsir-controlnet-openpose-sdxl-1.0"
GUIDE_JSON_RELATIVE = "pose-guides/openpose-v3/challenges/multiref-strong-left-arm-up.json"
WORKFLOW_TEMPLATE_RELATIVE = "providers/workflows/sdxl-openpose-controlnet-p.api.json"
PROMPT_SHA256 = "b7dd93c9383533014a17955efa229e9197a3c18d1705a4290207a18106a88cc0"
NEGATIVE_PROMPT_SHA256 = "7a5a7d4c29f153c8ce09a917b86dd3565a1649bca33225d37f44c6b282940aad"

# The P0 values are the v0.6.1 baseline. P1/P2 are the model-card-like
# operating point, translated only through values observed in KSampler's
# live object_info response.
CALIBRATION_MATRIX: tuple[dict[str, Any], ...] = (
    {
        "id": "P0",
        "label": "CURRENT_BASELINE",
        "width": 512,
        "height": 512,
        "steps": 20,
        "sampler_name": "euler",
        "scheduler": "normal",
        "controlnet_strength": 0.9,
        "model_card_like": False,
    },
    {
        "id": "P1",
        "label": "RECOMMENDED_LIKE_MID_RESOLUTION",
        "width": 768,
        "height": 768,
        "steps": 30,
        "sampler_name": "euler_ancestral",
        "scheduler": "normal",
        "controlnet_strength": 1.0,
        "model_card_like": True,
    },
    {
        "id": "P2",
        "label": "MODEL_CARD_TARGET",
        "width": 1024,
        "height": 1024,
        "steps": 30,
        "sampler_name": "euler_ancestral",
        "scheduler": "normal",
        "controlnet_strength": 1.0,
        "model_card_like": True,
    },
)

MODEL_CARD_CONFIGURATION = {
    "controlnet_conditioning_scale": 1.0,
    "num_inference_steps": 30,
    "scheduler": "EulerAncestralDiscreteScheduler",
    "resolution_guidance": "approximately 1024x1024 or same bucket resolution",
}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def validate_calibration_matrix(matrix: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = CALIBRATION_MATRIX) -> list[str]:
    failures: list[str] = []
    expected = (("P0", 512, 20, "euler", "normal", 0.9), ("P1", 768, 30, "euler_ancestral", "normal", 1.0), ("P2", 1024, 30, "euler_ancestral", "normal", 1.0))
    if len(matrix) != 3:
        failures.append("matrix_must_have_exactly_three_configs")
    for item, expected_item in zip(matrix, expected):
        if tuple(item.get(key) for key in ("id", "width", "steps", "sampler_name", "scheduler", "controlnet_strength")) != expected_item:
            failures.append(f"matrix_config_invalid:{item.get('id')}")
        if item.get("height") != item.get("width"):
            failures.append(f"matrix_config_not_square:{item.get('id')}")
    if [item.get("id") for item in matrix] != ["P0", "P1", "P2"]:
        failures.append("matrix_order_must_be_p0_p1_p2")
    return failures


def derive_p_workflow(
    template: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    prompt: str,
    negative_prompt: str,
    seed: int,
    guide_filename: str,
    model_names: Mapping[str, str],
    node_info: Mapping[str, Any] | None = None,
    available_models: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive a P graph while preserving topology and the two model inputs."""
    workflow = bind_workflow(
        dict(template),
        prompt=prompt,
        negative_prompt=negative_prompt,
        seed=seed,
        width=int(config["width"]),
        height=int(config["height"]),
        model_names=dict(model_names),
        image_filenames=[None, guide_filename],
    )
    samplers = [node for node in workflow.values() if node.get("class_type") == "KSampler"]
    controls = [node for node in workflow.values() if node.get("class_type") == "ControlNetApplyAdvanced"]
    if len(samplers) != 1 or len(controls) != 1:
        raise ValueError("P template must contain exactly one KSampler and one ControlNetApplyAdvanced")
    samplers[0]["inputs"].update({"steps": int(config["steps"]), "sampler_name": str(config["sampler_name"]), "scheduler": str(config["scheduler"])})
    controls[0]["inputs"]["strength"] = float(config["controlnet_strength"])
    forbidden = []
    for node_id, node in workflow.items():
        serialized = json.dumps(node, ensure_ascii=False).casefold()
        if "ipadapter" in serialized or "ip-adapter" in serialized:
            forbidden.append(str(node_id))
    if forbidden:
        raise ValueError(f"P-only graph contains forbidden IP-Adapter content: {forbidden}")
    graph = validate_api_workflow(workflow, node_info=node_info, model_names=available_models)
    graph = {
        **graph,
        "ipadapter_nodes": forbidden,
        "p_only": not forbidden,
        "dimensions": [int(config["width"]), int(config["height"])],
        "steps": int(config["steps"]),
        "sampler_name": str(config["sampler_name"]),
        "scheduler": str(config["scheduler"]),
        "controlnet_strength": float(config["controlnet_strength"]),
    }
    return workflow, {"graph": graph, "workflow_sha256": workflow_hash(workflow)}


def choose_best_stage_a(records: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """Rank only executable, technically passing P configurations by pose."""
    candidates = [item for item in records if item.get("stage_a_pass") is True and item.get("raw_output_path")]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            float((item.get("raw_pose_qa") or {}).get("pose", {}).get("pck_at_010", 0.0)),
            -float((item.get("raw_pose_qa") or {}).get("pose", {}).get("nme", 1.0)),
            -float((item.get("raw_pose_qa") or {}).get("pose", {}).get("limb_angle_mae_degrees", 180.0)),
            float((item.get("raw_pose_qa") or {}).get("pose", {}).get("lower_body_pck", 0.0)),
            -float(item.get("runtime_ms") or 1e12),
        ),
        reverse=True,
    )[0]


def is_oom_error(value: object) -> bool:
    if isinstance(value, MemoryError):
        return True
    text = str(value).casefold()
    return any(token in text for token in ("out of memory", "cuda out of memory", "oom", "memoryerror", "vram"))


def qualification_status(*, selected_id: str | None, confirmation_pass: bool, p2_hardware_gap: bool) -> str:
    if confirmation_pass and selected_id == "P1" and p2_hardware_gap:
        return "SDXL_OPENPOSE_P_LANE_QUALIFIED_768"
    if confirmation_pass:
        return "SDXL_OPENPOSE_P_LANE_QUALIFIED"
    return "SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS"


__all__ = [
    "CALIBRATION_MATRIX", "CONFIRMATION_SEEDS", "CONTROLNET_MODEL_ID", "GUIDE_JSON_RELATIVE",
    "MODEL_CARD_CONFIGURATION", "MODEL_CARD_LICENSE", "MODEL_CARD_REVISION", "MODEL_CARD_URL",
    "MODEL_ID", "NEGATIVE_PROMPT_SHA256", "PHASE", "PROMPT_ID", "PROMPT_SHA256", "SEED",
    "WORKFLOW_ID", "WORKFLOW_TEMPLATE_RELATIVE", "canonical_hash", "choose_best_stage_a",
    "derive_p_workflow", "is_oom_error", "qualification_status", "validate_calibration_matrix",
]
