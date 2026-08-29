"""Consumer bootstrap installer with safe, non-destructive refresh semantics."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .constants import CONSUMER_FILES
from .context import resolve_project_context
from .profiles import resolve_profile
from .constants import UGAS_VERSION


PROVIDER_IDS = ["provider-comfyui", "provider-remote-render-node", "provider-huggingface"]
POLICIES = {"local-first", "remote-first", "free-first", "paid-disabled"}
PROTECTED_FILES = {"asset-registry.json", "provenance.jsonl", "CHECKPOINT.md"}
PROTECTED_DIRECTORIES = {"references", "manifests"}


def _write_json(path: Path, value: dict, preserved: list[str]) -> None:
    if path.exists():
        preserved.append(path.name)
        return
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_or_update_json(path: Path, value: dict, preserved: list[str]) -> None:
    if path.name in PROTECTED_FILES and path.exists():
        preserved.append(path.name)
        return
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def install_consumer(
    repo_root: Path,
    consumer_root: Path,
    profile_id: str | None = None,
    policy: str = "local-first",
    force: bool = False,
) -> dict:
    if policy not in POLICIES:
        raise ValueError(f"Unknown provider policy: {policy}")
    repo_root = repo_root.resolve()
    consumer_root = consumer_root.resolve()
    consumer_root.mkdir(parents=True, exist_ok=True)
    context = resolve_project_context(consumer_root, requested_profile=profile_id)
    profile, selected_profile_id, profile_confidence, profile_evidence = resolve_profile(repo_root, profile_id, context)
    target = consumer_root / ".game-assets"
    if target.exists() and not force:
        existing = [path.name for path in target.iterdir()]
        if existing:
            raise FileExistsError(".game-assets already contains files; pass --force to refresh without destructive reset")
    target.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    preserved: list[str] = []
    profile_status = profile.get("selection_status", "selected")

    _write_or_update_json(target / "studio.json", {
        "schema_version": UGAS_VERSION,
        "studio": "UGAS",
        "installed_version": UGAS_VERSION,
        "installed_at": stamp,
        "consumer_root": ".",
        "engine": context.engine,
        "language": context.language,
        "dimension": profile["dimension"],
        "provider_policy": policy,
        "orchestrator": "game-asset-orchestrator",
        "profile_selection_status": profile_status,
        "profile_recommendation": context.profile_recommendation,
        "profile_confidence": profile_confidence,
        "profile_evidence": profile_evidence,
    }, preserved)
    _write_or_update_json(target / "profile.json", profile, preserved)
    _write_or_update_json(target / "art-dna.json", {
        "schema_version": UGAS_VERSION,
        "source_profile": selected_profile_id,
        "style_keywords": profile["artistic_parameters"]["style_keywords"],
        "palette": profile["artistic_parameters"]["palette"],
        "shape_language": profile["artistic_parameters"]["shape_language"],
        "consistency_rules": profile["artistic_parameters"]["consistency_rules"],
    }, preserved)
    _write_or_update_json(target / "asset-standards.json", {
        "schema_version": UGAS_VERSION,
        "naming": profile["naming"],
        "formats": profile["technical_parameters"]["formats"],
        "source_of_truth": "asset-registry.json",
        "raw_ids_allowed_in_registry": True,
    }, preserved)
    _write_or_update_json(target / "asset-dependencies.json", {
        "schema_version": UGAS_VERSION,
        "nodes": [],
        "edges": [],
    }, preserved)
    _write_or_update_json(target / "performance-budget.json", {
        "schema_version": UGAS_VERSION,
        "profile": selected_profile_id,
        **profile["budgets"],
    }, preserved)
    _write_or_update_json(target / "toolchain.json", {
        "schema_version": UGAS_VERSION,
        "engine": context.engine,
        "language": context.language,
        "detected_files": context.detected_files,
        "scan_summary": context.scan_summary,
        "provider_policy": policy,
        "providers": PROVIDER_IDS,
        "profile_recommendation": context.profile_recommendation,
        "profile_confidence": profile_confidence,
        "profile_evidence": profile_evidence,
        "comfyui_endpoint": "http://127.0.0.1:8188",
        "render_node_endpoint": None,
        "credentials": "environment or local secret manager only; never commit credentials",
    }, preserved)
    _write_or_update_json(target / "asset-registry.json", {
        "schema_version": UGAS_VERSION,
        "assets": [],
        "registry_policy": {"reuse_before_generate": True, "provenance_required": True},
    }, preserved)
    provenance_path = target / "provenance.jsonl"
    event = json.dumps({
        "event": "bootstrap-refreshed" if provenance_path.exists() else "bootstrap-installed",
        "timestamp": stamp,
        "profile": selected_profile_id,
        "installer": f"game-asset-installer@{UGAS_VERSION}",
    }, ensure_ascii=False)
    if provenance_path.exists():
        with provenance_path.open("a", encoding="utf-8") as stream:
            stream.write(event + "\n")
        preserved.append("provenance.jsonl (history preserved and event appended)")
    else:
        provenance_path.write_text(event + "\n", encoding="utf-8")
    checkpoint = target / "CHECKPOINT.md"
    if checkpoint.exists():
        preserved.append("CHECKPOINT.md")
    else:
        checkpoint.write_text(
            "# UGAS consumer checkpoint\n\n"
            f"- Installed: {stamp}\n"
            f"- Profile: `{selected_profile_id}`\n"
            f"- Profile confidence: `{profile_confidence}`\n"
            f"- Engine detection: `{context.engine}` ({context.confidence} confidence)\n"
            "- Status: bootstrap ready; no generated asset is claimed.\n"
            "- Next review: confirm engine-specific import conventions before production generation.\n",
            encoding="utf-8",
        )
    for directory_name, readme in {
        "references": "# Consumer references\n\nStore links and human-approved reference notes here.\n",
        "manifests": "# Consumer manifests\n\nStore asset and workflow manifests here.\n",
    }.items():
        directory = target / directory_name
        directory.mkdir(exist_ok=True)
        readme_path = directory / "README.md"
        if readme_path.exists():
            preserved.append(f"{directory_name}/")
        else:
            readme_path.write_text(readme, encoding="utf-8")
    runtime_dir = target / "tools"
    runtime_package = runtime_dir / "ugas"
    if runtime_package.exists() and not force:
        raise FileExistsError(".game-assets/tools/ugas already exists; pass --force to update the consumer runtime")
    if runtime_package.exists():
        shutil.rmtree(runtime_package)
    runtime_package.mkdir(parents=True, exist_ok=True)
    source_package = repo_root / "src" / "ugas"
    for source in source_package.glob("*.py"):
        shutil.copy2(source, runtime_package / source.name)
    shutil.copy2(repo_root / "templates" / "ugas_runtime.py", runtime_dir / "ugas_runtime.py")
    review = target / "INSTALLATION-REVIEW.md"
    review.write_text(
        "# UGAS installation review\n\n"
        f"- Status: `{'READY_FOR_REVIEW' if profile_status == 'selected' else 'PROFILE_SELECTION_PENDING'}`\n"
        f"- Profile: `{selected_profile_id}`\n"
        f"- Profile confidence: `{profile_confidence}`\n"
        f"- Engine: `{context.engine}`\n"
        f"- Dimension: `{profile['dimension']}`\n"
        f"- Scan: {context.scan_summary['files_scanned']} files, {context.scan_summary['directories_scanned']} directories, bounded={not context.scan_summary['truncated']}\n"
        f"- Generated files: {', '.join(CONSUMER_FILES)}\n"
        f"- Preserved on refresh: {', '.join(sorted(set(preserved))) if preserved else 'none'}\n"
        "- Provider state: contracts registered; live availability must be probed separately.\n"
        "- Runtime: self-contained copy under `.game-assets/tools`; no original checkout path is required.\n",
        encoding="utf-8",
    )
    return {
        "status": "installed",
        "consumer_root": str(consumer_root),
        "game_assets": str(target),
        "profile": selected_profile_id,
        "profile_selection_status": profile_status,
        "profile_recommendation": context.profile_recommendation,
        "profile_confidence": profile_confidence,
        "profile_evidence": profile_evidence,
        "engine": context.engine,
        "dimension": profile["dimension"],
        "preserved": sorted(set(preserved)),
        "files": CONSUMER_FILES + ["INSTALLATION-REVIEW.md", "tools/ugas_runtime.py", "tools/ugas/"],
    }
