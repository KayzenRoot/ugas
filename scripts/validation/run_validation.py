"""Objective V0.2 repository validation with human-readable evidence."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.constants import CONSUMER_FILES, PROFILES, PROVIDERS, SCHEMAS, SKILLS
from ugas.installer import install_consumer
from ugas.providers import comfyui_healthcheck, detect_render_capability
from ugas.router import route_request


results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str) -> None:
    results.append((name, condition, detail))


def main() -> int:
    for path in ["README.md", "INSTALL.md", "REVIEW-v0.2.md", "LICENSE", "package.json", "pyproject.toml", "docs", "skills", "profiles", "templates", "schemas", "providers", "scripts", "examples", "tests"]:
        check(f"path:{path}", (ROOT / path).exists(), "present" if (ROOT / path).exists() else "missing")

    for skill in SKILLS:
        path = ROOT / "skills" / skill / "SKILL.md"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        lower = text.casefold()
        ok = path.exists() and "trigger" in lower and "when not" in lower and "limits" in lower
        check(f"skill:{skill}", ok, "SKILL.md has trigger, non-use, and limits sections" if ok else "contract headings missing")

    profile_required = {"id", "name", "dimension", "description", "use_cases", "artistic_parameters", "technical_parameters", "asset_structure", "budgets", "provider_guidance", "naming", "animation", "limitations"}
    for profile_id in PROFILES:
        path = ROOT / "profiles" / f"{profile_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            ok = profile_required.issubset(value) and value["id"] == profile_id
            detail = "JSON parsed and profile contract present" if ok else "required profile fields missing"
        except (OSError, json.JSONDecodeError) as exc:
            ok, detail = False, str(exc)
        check(f"profile:{profile_id}", ok, detail)

    for schema in SCHEMAS:
        path = ROOT / "schemas" / f"{schema}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            ok = isinstance(value, dict) and value.get("$schema") and value.get("required")
            detail = "valid JSON schema" if ok else "schema metadata missing"
        except (OSError, json.JSONDecodeError) as exc:
            ok, detail = False, str(exc)
        check(f"schema:{schema}", ok, detail)

    for template in ["studio.json", "profile.json", "art-dna.json", "asset-standards.json", "performance-budget.json", "toolchain.json", "asset-registry.json", "asset-dependencies.json"]:
        path = ROOT / "templates" / template
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            check(f"template:{template}", isinstance(value, dict), "valid JSON template")
        except (OSError, json.JSONDecodeError) as exc:
            check(f"template:{template}", False, str(exc))
    provenance_template = ROOT / "templates" / "provenance.jsonl"
    try:
        lines = [line for line in provenance_template.read_text(encoding="utf-8").splitlines() if line.strip()]
        check("template:provenance.jsonl", all(isinstance(json.loads(line), dict) for line in lines), "valid JSON Lines template")
    except (OSError, json.JSONDecodeError) as exc:
        check("template:provenance.jsonl", False, str(exc))

    for provider in PROVIDERS:
        path = ROOT / "providers" / "manifests" / f"{provider}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            ok = value.get("id") == provider and value.get("capabilities") and value.get("credential_policy")
            detail = "manifest parsed with capability and credential policy" if ok else "provider contract incomplete"
        except (OSError, json.JSONDecodeError) as exc:
            ok, detail = False, str(exc)
        check(f"provider:{provider}", ok, detail)

    with tempfile.TemporaryDirectory(prefix="ugas-validation-") as directory:
        consumer = Path(directory) / "game"
        (consumer).mkdir()
        (consumer / "project.godot").write_text("[application]\nconfig/name=Validation Game\n", encoding="utf-8")
        result = install_consumer(ROOT, consumer, "topdown-rpg-mmorpg-2d", "local-first")
        generated = consumer / ".game-assets"
        check("installer:smoke", result["status"] == "installed" and all((generated / name).exists() for name in CONSUMER_FILES), "consumer .game-assets contract created")

    for example in ["consumer-godot-2d", "consumer-space-idle-2d", "consumer-generic-3d"]:
        target = ROOT / "examples" / example / ".game-assets"
        check(f"example:{example}", target.exists() and all((target / name).exists() for name in CONSUMER_FILES), "tracked example has the consumer contract")

    cases = [
        ("Criar vila humana 2D de MMORPG", ["sprite", "tileset", "animation"], "provider-comfyui"),
        ("Criar planetas e naves de jogo idle espacial", ["sprite", "background", "ui", "vfx"], "provider-comfyui"),
        ("Criar boss 3D stylized", ["model", "material", "animation", "lod"], "provider-comfyui"),
    ]
    for request, expected_types, expected_provider in cases:
        route = route_request(request, policy="local-first")
        check(f"routing:{request}", route["asset_types"] == expected_types and route["provider"] == expected_provider, json.dumps(route, ensure_ascii=False))
    irrelevant = route_request("Ajustar matchmaking do jogo")
    check("routing:non-asset", not irrelevant["asset_studio_relevant"] and irrelevant["provider"] is None, json.dumps(irrelevant, ensure_ascii=False))
    fallback = route_request("Criar boss 3D stylized", providers={"provider-comfyui": False, "provider-remote-render-node": False})
    check("routing:render-node-fallback", fallback["provider"] == "provider-huggingface", json.dumps(fallback, ensure_ascii=False))

    comfy = comfyui_healthcheck(dry_run=True)
    check("comfyui:dry-run", comfy["status"] == "dry-run-ready", json.dumps(comfy, ensure_ascii=False))
    node = detect_render_capability(dry_run=True)
    check("render-node:dry-run", node["status"] == "contract-ready" and "RTX 5050" in node["gpu"], json.dumps(node, ensure_ascii=False))

    failures = 0
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {name} - {detail}")
        failures += not ok
    print(f"SUMMARY checks={len(results)} passed={len(results) - failures} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
