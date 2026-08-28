"""Consumer bootstrap installer for the local .game-assets contract."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .constants import CONSUMER_FILES
from .context import resolve_project_context
from .profiles import load_profile


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def install_consumer(
    repo_root: Path,
    consumer_root: Path,
    profile_id: str = "generic-2d",
    policy: str = "local-first",
    force: bool = False,
) -> dict:
    repo_root = repo_root.resolve()
    consumer_root = consumer_root.resolve()
    consumer_root.mkdir(parents=True, exist_ok=True)
    context = resolve_project_context(consumer_root)
    profile = load_profile(repo_root, profile_id)
    target = consumer_root / ".game-assets"
    if target.exists() and not force:
        existing = [path.name for path in target.iterdir()]
        if existing:
            raise FileExistsError(".game-assets already contains files; pass --force to replace the bootstrap files")
    target.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    _write_json(target / "studio.json", {
        "schema_version": "0.2",
        "studio": "UGAS",
        "installed_version": "0.2.0",
        "installed_at": stamp,
        "consumer_root": ".",
        "engine": context.engine,
        "language": context.language,
        "dimension": profile["dimension"],
        "provider_policy": policy,
        "orchestrator": "game-asset-orchestrator",
    })
    _write_json(target / "profile.json", {"schema_version": "0.2", **profile})
    _write_json(target / "art-dna.json", {
        "schema_version": "0.2",
        "source_profile": profile_id,
        "style_keywords": profile["artistic_parameters"]["style_keywords"],
        "palette": profile["artistic_parameters"]["palette"],
        "shape_language": profile["artistic_parameters"]["shape_language"],
        "consistency_rules": profile["artistic_parameters"]["consistency_rules"],
    })
    _write_json(target / "asset-standards.json", {
        "schema_version": "0.2",
        "naming": profile["naming"],
        "formats": profile["technical_parameters"]["formats"],
        "source_of_truth": "asset-registry.json",
        "raw_ids_allowed_in_registry": True,
    })
    _write_json(target / "performance-budget.json", {
        "schema_version": "0.2",
        "profile": profile_id,
        **profile["budgets"],
    })
    _write_json(target / "toolchain.json", {
        "schema_version": "0.2",
        "engine": context.engine,
        "language": context.language,
        "detected_files": context.detected_files,
        "provider_policy": policy,
        "providers": ["provider-comfyui", "provider-remote-render-node", "provider-huggingface"],
        "comfyui_endpoint": "http://127.0.0.1:8188",
        "render_node_endpoint": None,
        "credentials": "environment or local secret manager only; never commit credentials",
    })
    _write_json(target / "asset-registry.json", {
        "schema_version": "0.2",
        "assets": [],
        "registry_policy": {"reuse_before_generate": True, "provenance_required": True},
    })
    _write_json(target / "asset-dependencies.json", {"schema_version": "0.2", "nodes": [], "edges": []})
    (target / "provenance.jsonl").write_text(json.dumps({
        "event": "bootstrap-installed",
        "timestamp": stamp,
        "profile": profile_id,
        "installer": "game-asset-installer@0.2.0",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    (target / "CHECKPOINT.md").write_text(
        "# UGAS consumer checkpoint\n\n"
        f"- Installed: {stamp}\n"
        f"- Profile: `{profile_id}`\n"
        f"- Engine detection: `{context.engine}` ({context.confidence} confidence)\n"
        "- Status: bootstrap ready; no generated asset is claimed.\n"
        "- Next review: confirm engine-specific import conventions before production generation.\n",
        encoding="utf-8",
    )
    (target / "references").mkdir(exist_ok=True)
    (target / "manifests").mkdir(exist_ok=True)
    (target / "references" / "README.md").write_text("# Consumer references\n\nStore links and human-approved reference notes here.\n", encoding="utf-8")
    (target / "manifests" / "README.md").write_text("# Consumer manifests\n\nStore asset and workflow manifests here.\n", encoding="utf-8")
    review = target / "INSTALLATION-REVIEW.md"
    review.write_text(
        "# UGAS installation review\n\n"
        "- Status: `READY_FOR_REVIEW`\n"
        f"- Profile: `{profile_id}`\n"
        f"- Engine: `{context.engine}`\n"
        f"- Dimension: `{profile['dimension']}`\n"
        f"- Generated files: {', '.join(CONSUMER_FILES)}\n"
        "- Provider state: contracts registered; external health is not asserted by bootstrap.\n",
        encoding="utf-8",
    )
    return {
        "status": "installed",
        "consumer_root": str(consumer_root),
        "game_assets": str(target),
        "profile": profile_id,
        "engine": context.engine,
        "dimension": profile["dimension"],
        "files": CONSUMER_FILES + ["INSTALLATION-REVIEW.md"],
    }
