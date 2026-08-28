"""Deterministic dry-run request classification and provider routing."""

from __future__ import annotations

import re
from typing import Mapping


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

    if _has(normalized, "boss 3d", "boss 3d", "3d stylized", "3d estilizado", "modelo 3d"):
        return {
            "asset_studio_relevant": True,
            "reason": "3D character/encounter asset request.",
            "dimension": "3d",
            "asset_types": ["model", "material", "animation", "lod"],
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


def route_request(
    request: str,
    *,
    policy: str = "local-first",
    providers: Mapping[str, bool] | None = None,
    engine: str = "unknown",
) -> dict:
    classification = classify_request(request)
    if not classification["asset_studio_relevant"]:
        return {**classification, "engine": engine, "policy": policy, "provider": None, "fallbacks": []}

    availability = {
        "provider-comfyui": True,
        "provider-remote-render-node": True,
        "provider-huggingface": True,
    }
    if providers is not None:
        availability.update(providers)
    order = _provider_order(policy)
    candidates = [provider for provider in order if availability.get(provider, False)]
    if policy == "paid-disabled":
        candidates = [provider for provider in candidates if provider != "provider-remote-render-node"]
    provider = candidates[0] if candidates else None
    return {
        **classification,
        "engine": engine,
        "policy": policy,
        "provider": provider,
        "fallbacks": candidates[1:],
        "routing_status": "resolved" if provider else "unavailable",
    }


def compact_request_id(request: str) -> str:
    """Return a stable, readable slug for logs without persisting user prose."""
    slug = re.sub(r"[^a-z0-9]+", "-", request.casefold()).strip("-")
    return slug[:64] or "asset-request"
