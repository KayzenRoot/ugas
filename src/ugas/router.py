"""Deterministic request classification and evidence-based provider routing.

Routing deliberately treats an unprobed provider as ``unknown``. A provider is
selected only when its availability is explicit and its declared capabilities
cover the request.
"""

from __future__ import annotations

import re
from typing import Mapping


PROVIDER_IDS = (
    "provider-comfyui",
    "provider-remote-render-node",
    "provider-huggingface",
)

DEFAULT_PROVIDER_COST_CLASSES = {
    "provider-comfyui": "local",
    "provider-remote-render-node": "self-hosted",
    "provider-huggingface": "free-tier",
}

DEFAULT_PROVIDER_CAPABILITIES = {
    "provider-comfyui": frozenset(
        {
            "2d",
            "sprite-generation",
            "background-generation",
            "ui-generation",
            "vfx-generation",
            "3d-reference",
            "3d-model",
            "material",
            "animation",
            "lod",
        }
    ),
    "provider-remote-render-node": frozenset(
        {
            "2d",
            "sprite-generation",
            "background-generation",
            "ui-generation",
            "vfx-generation",
            "3d-reference",
            "3d-model",
            "material",
            "animation",
            "lod",
        }
    ),
    "provider-huggingface": frozenset(
        {"2d", "sprite-generation", "background-generation", "ui-generation", "vfx-generation", "model-metadata"}
    ),
}

AVAILABILITY_STATES = {"available", "unavailable", "unknown"}


def _has(text: str, *terms: str) -> bool:
    return any(term in text for term in terms)


def classify_request(request: str) -> dict:
    normalized = request.casefold()
    if _has(normalized, "matchmaking", "match making", "servidor", "database", "backend") and not _has(
        normalized, "asset", "sprite", "modelo", "textura", "ícone", "icon"
    ):
        return {
            "asset_studio_relevant": False,
            "reason": "The request is gameplay/backend work, not asset production.",
            "dimension": "unknown",
            "asset_types": [],
            "profile_hint": None,
        }

    if _has(normalized, "boss 3d", "3d stylized", "3d estilizado", "modelo 3d"):
        reference_only = _has(normalized, "concept", "conceito", "referência", "reference")
        return {
            "asset_studio_relevant": True,
            "reason": "3D character/encounter asset request.",
            "dimension": "3d",
            "asset_types": ["reference" if reference_only else "model", "material", "animation", "lod"],
            "profile_hint": "stylized-3d",
        }
    if _has(normalized, "planetas", "naves", "space", "espacial", "idle strategy", "ogame"):
        return {
            "asset_studio_relevant": True,
            "reason": "Space idle/strategy asset request.",
            "dimension": "2d",
            "asset_types": ["sprite", "background", "ui", "vfx"],
            "profile_hint": "space-idle-strategy-2d",
        }
    if _has(normalized, "vila", "village", "mmorpg", "top-down", "topdown", "rpg"):
        return {
            "asset_studio_relevant": True,
            "reason": "Top-down RPG/MMORPG asset request.",
            "dimension": "2d",
            "asset_types": ["sprite", "tileset", "animation"],
            "profile_hint": "topdown-rpg-mmorpg-2d",
        }
    if _has(normalized, "asset", "sprite", "tileset", "texture", "ícone", "icon", "modelo", "material"):
        dimension = "3d" if _has(normalized, "3d", "modelo", "material") else "2d"
        return {
            "asset_studio_relevant": True,
            "reason": "Generic game asset request.",
            "dimension": dimension,
            "asset_types": ["model" if dimension == "3d" else "sprite"],
            "profile_hint": "stylized-3d" if dimension == "3d" else "generic-2d",
        }
    return {
        "asset_studio_relevant": False,
        "reason": "No asset-production intent was detected.",
        "dimension": "unknown",
        "asset_types": [],
        "profile_hint": None,
    }


def _provider_order(policy: str) -> list[str]:
    orders = {
        "free-first": ["provider-huggingface", "provider-comfyui", "provider-remote-render-node"],
        "local-first": ["provider-comfyui", "provider-remote-render-node", "provider-huggingface"],
        "remote-first": ["provider-remote-render-node", "provider-comfyui", "provider-huggingface"],
        "paid-disabled": ["provider-comfyui", "provider-remote-render-node", "provider-huggingface"],
    }
    if policy not in orders:
        raise ValueError(f"Unknown provider policy: {policy}")
    return orders[policy]


def _normalize_availability(value: object) -> str:
    if isinstance(value, bool):
        return "available" if value else "unavailable"
    if isinstance(value, str) and value in AVAILABILITY_STATES:
        return value
    return "unknown"


def _required_capabilities(classification: Mapping[str, object]) -> set[str]:
    dimension = classification["dimension"]
    asset_types = set(classification["asset_types"])
    if dimension == "3d":
        # A final model is intentionally stronger than a concept/reference image.
        required = {"3d-model"} if "model" in asset_types else {"3d-reference"}
    else:
        required = {"2d"}
    type_capabilities = {
        "sprite": "sprite-generation",
        "background": "background-generation",
        "ui": "ui-generation",
        "vfx": "vfx-generation",
        "material": "material",
        "animation": "animation",
        "lod": "lod",
    }
    required.update(type_capabilities[item] for item in asset_types if item in type_capabilities)
    return required


def _result_for_non_asset(classification: Mapping[str, object], policy: str, engine: str) -> dict:
    return {
        **classification,
        "engine": engine,
        "policy": policy,
        "provider": None,
        "fallbacks": [],
        "preferred_providers": [],
        "available_providers": [],
        "unknown_providers": [],
        "required_capabilities": [],
        "capability_gaps": {},
        "routing_status": "not-applicable",
    }


def route_request(
    request: str,
    *,
    policy: str = "local-first",
    providers: Mapping[str, object] | None = None,
    availability: Mapping[str, object] | None = None,
    capabilities: Mapping[str, object] | None = None,
    cost_classes: Mapping[str, str] | None = None,
    engine: str = "unknown",
) -> dict:
    classification = classify_request(request)
    if not classification["asset_studio_relevant"]:
        return _result_for_non_asset(classification, policy, engine)

    raw_availability: dict[str, object] = dict(providers or {})
    raw_availability.update(availability or {})
    normalized_availability = {
        provider_id: _normalize_availability(raw_availability.get(provider_id, "unknown"))
        for provider_id in PROVIDER_IDS
    }
    provider_capabilities = {
        provider_id: set(DEFAULT_PROVIDER_CAPABILITIES[provider_id]) for provider_id in PROVIDER_IDS
    }
    for provider_id, declared in (capabilities or {}).items():
        if provider_id in provider_capabilities:
            provider_capabilities[provider_id] = set(declared)
    provider_cost = {**DEFAULT_PROVIDER_COST_CLASSES, **(cost_classes or {})}

    order = _provider_order(policy)
    if policy == "paid-disabled":
        order = [provider_id for provider_id in order if provider_cost.get(provider_id) != "paid"]
    required = _required_capabilities(classification)
    available = [provider_id for provider_id in order if normalized_availability[provider_id] == "available"]
    unknown = [provider_id for provider_id in order if normalized_availability[provider_id] == "unknown"]
    gaps = {
        provider_id: sorted(required - provider_capabilities[provider_id])
        for provider_id in order
        if required - provider_capabilities[provider_id]
    }
    capable_available = [
        provider_id for provider_id in available if not (required - provider_capabilities[provider_id])
    ]
    capable_unknown = [
        provider_id for provider_id in unknown if not (required - provider_capabilities[provider_id])
    ]
    provider = capable_available[0] if capable_available else None
    if provider:
        status = "resolved"
        fallbacks = capable_available[1:]
    elif capable_unknown:
        status = "unknown"
        fallbacks = []
    elif gaps:
        status = "capability_gap"
        fallbacks = []
    else:
        status = "unavailable"
        fallbacks = []

    return {
        **classification,
        "engine": engine,
        "policy": policy,
        "provider": provider,
        "fallbacks": fallbacks,
        "preferred_providers": order,
        "available_providers": available,
        "unknown_providers": unknown,
        "required_capabilities": sorted(required),
        "capability_gaps": gaps,
        "routing_status": status,
    }


def compact_request_id(request: str) -> str:
    """Return a stable, readable slug for logs without persisting user prose."""
    slug = re.sub(r"[^a-z0-9]+", "-", request.casefold()).strip("-")
    return slug[:64] or "asset-request"
