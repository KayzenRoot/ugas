"""Objective v0.2.1 repository validation with human-readable evidence."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.constants import CONSUMER_FILES, PROFILES, PROVIDERS, SCHEMAS, SKILLS
from ugas.context import resolve_project_context
from ugas.installer import install_consumer
from ugas.providers import comfyui_healthcheck, detect_local_gpu_capability, remote_render_node_healthcheck
from ugas.router import route_request
from ugas.schema_validation import SchemaValidationError, validate_instance, validate_schema_document
from ugas.skills import validate_skill_frontmatter


results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str) -> None:
    results.append((name, bool(condition), detail))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    required_paths = [
        "README.md", "INSTALL.md", "REVIEW-v0.2.md", "REVIEW-v0.2.1.md", "LICENSE", "package.json", "pyproject.toml",
        "docs", "skills", "profiles", "templates", "schemas", "providers", "scripts", "examples", "tests",
    ]
    for path in required_paths:
        check(f"path:{path}", (ROOT / path).exists(), "present" if (ROOT / path).exists() else "missing")

    for skill in SKILLS:
        path = ROOT / "skills" / skill / "SKILL.md"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        valid, errors, _ = validate_skill_frontmatter(text, skill)
        lower = text.casefold()
        valid = valid and "disable-model-invocation" not in text and all(token in lower for token in ("trigger", "when not", "limits"))
        check(f"skill:{skill}", valid, "frontmatter + operational sections valid" if valid else "; ".join(errors) or "skill contract headings missing")

    schemas: dict[str, dict] = {}
    for schema_name in SCHEMAS:
        path = ROOT / "schemas" / f"{schema_name}.json"
        try:
            value = load_json(path)
            validate_schema_document(value)
            schemas[schema_name] = value
            check(f"schema:{schema_name}", True, "Draft 2020-12 schema document is structurally valid")
        except (OSError, json.JSONDecodeError, SchemaValidationError) as exc:
            check(f"schema:{schema_name}", False, str(exc))

    for profile_id in PROFILES:
        path = ROOT / "profiles" / f"{profile_id}.json"
        try:
            value = load_json(path)
            validate_instance(value, schemas["profile"])
            ok = value["id"] == profile_id and value["schema_version"] == "0.2.1"
            check(f"profile:{profile_id}", ok, "instance validates against profile schema v0.2.1" if ok else "profile id/version mismatch")
        except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc:
            check(f"profile:{profile_id}", False, str(exc))

    template_pairs = {
        "art-dna.json": "art-dna",
        "asset-registry.json": "asset-registry",
        "performance-budget.json": "performance-budget",
        "profile.json": "profile",
        "toolchain.json": "toolchain",
    }
    for filename, schema_name in template_pairs.items():
        try:
            validate_instance(load_json(ROOT / "templates" / filename), schemas[schema_name])
            check(f"template:{filename}", True, f"valid {schema_name} instance")
        except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc:
            check(f"template:{filename}", False, str(exc))
    try:
        lines = [line for line in (ROOT / "templates" / "provenance.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        check("template:provenance.jsonl", all(isinstance(json.loads(line), dict) for line in lines), "valid JSON Lines template")
    except (OSError, json.JSONDecodeError) as exc:
        check("template:provenance.jsonl", False, str(exc))

    for provider in PROVIDERS:
        try:
            manifest = load_json(ROOT / "providers" / "manifests" / f"{provider}.json")
            validate_instance(manifest, schemas["provider-manifest"])
            check(f"provider:{provider}", manifest["id"] == provider and manifest["cost_class"] in {"local", "self-hosted", "free-tier", "paid"}, "manifest validates with cost class")
        except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc:
            check(f"provider:{provider}", False, str(exc))
    for workflow in (ROOT / "providers" / "workflows").glob("*.json"):
        try:
            validate_instance(load_json(workflow), schemas["workflow-manifest"])
            check(f"workflow:{workflow.name}", True, "workflow manifest validates")
        except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc:
            check(f"workflow:{workflow.name}", False, str(exc))

    with tempfile.TemporaryDirectory(prefix="ugas-validation-") as directory:
        temp_root = Path(directory)
        consumer = temp_root / "game"
        consumer.mkdir()
        default_install = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "bootstrap" / "install_skills.py"), str(consumer)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        installed_skills = list((consumer / ".agents" / "skills").glob("*/SKILL.md")) if (consumer / ".agents" / "skills").exists() else []
        check("installation:default-full", default_install.returncode == 0 and len(installed_skills) == len(SKILLS), f"exit={default_install.returncode}, skills={len(installed_skills)}/{len(SKILLS)}")

        (consumer / "project.godot").write_text("[application]\nconfig/name=Validation Game\n", encoding="utf-8")
        result = install_consumer(ROOT, consumer, "topdown-rpg-mmorpg-2d", "local-first", force=True)
        generated = consumer / ".game-assets"
        check("installer:smoke", result["status"] == "installed" and all((generated / name).exists() for name in CONSUMER_FILES), "consumer .game-assets contract created")
        check("installer:profile-fields", bool(result["profile_recommendation"] or result["profile"]), json.dumps(result, ensure_ascii=False))
        for filename, schema_name in {"profile.json": "profile", "asset-registry.json": "asset-registry", "toolchain.json": "toolchain", "performance-budget.json": "performance-budget"}.items():
            try:
                validate_instance(load_json(generated / filename), schemas[schema_name])
                check(f"installer:schema:{filename}", True, "generated instance validates")
            except (OSError, json.JSONDecodeError, SchemaValidationError) as exc:
                check(f"installer:schema:{filename}", False, str(exc))

        registry = generated / "asset-registry.json"
        registry.write_text(json.dumps({"schema_version": "0.2.1", "assets": [{"id": "preserve", "status": "draft"}]}), encoding="utf-8")
        provenance = generated / "provenance.jsonl"
        with provenance.open("a", encoding="utf-8") as stream:
            stream.write('{"event":"history-preserved"}\n')
        reference = generated / "references" / "user-reference.txt"
        reference.write_text("preserve", encoding="utf-8")
        refreshed = install_consumer(ROOT, consumer, "pixel-rpg-2d", "local-first", force=True)
        refresh_ok = "preserve" in registry.read_text(encoding="utf-8") and "history-preserved" in provenance.read_text(encoding="utf-8") and reference.exists()
        check("installer:safe-refresh", refresh_ok and "asset-registry.json" in refreshed["preserved"], "registry/provenance/references survived --force refresh")

    for example in ["consumer-godot-2d", "consumer-space-idle-2d", "consumer-generic-3d"]:
        target = ROOT / "examples" / example / ".game-assets"
        check(f"example:{example}", target.exists() and all((target / name).exists() for name in CONSUMER_FILES), "tracked example has the consumer contract")

    available_all = {provider: "available" for provider in ("provider-comfyui", "provider-remote-render-node", "provider-huggingface")}
    two_d = route_request("Criar vila humana 2D de MMORPG", availability=available_all)
    check("routing:2d-capability", two_d["provider"] == "provider-comfyui" and "2d" in two_d["required_capabilities"], json.dumps(two_d, ensure_ascii=False))
    three_d = route_request("Criar boss 3D stylized", availability=available_all)
    check("routing:3d-capability", three_d["provider"] == "provider-comfyui" and "3d-model" in three_d["required_capabilities"], json.dumps(three_d, ensure_ascii=False))
    gap = route_request("Criar boss 3D stylized", availability={"provider-comfyui": "unavailable", "provider-remote-render-node": "unavailable", "provider-huggingface": "available"})
    check("routing:3d-no-2d-fallback", gap["provider"] is None and gap["routing_status"] == "capability_gap", json.dumps(gap, ensure_ascii=False))
    remote = route_request("Criar boss 3D stylized", policy="paid-disabled", availability={"provider-comfyui": "unavailable", "provider-remote-render-node": "available", "provider-huggingface": "available"})
    check("routing:self-hosted-not-paid", remote["provider"] == "provider-remote-render-node", json.dumps(remote, ensure_ascii=False))
    unknown = route_request("Criar sprite de inventário")
    check("routing:unknown-without-probe", unknown["provider"] is None and unknown["routing_status"] == "unknown", json.dumps(unknown, ensure_ascii=False))
    irrelevant = route_request("Ajustar matchmaking do jogo")
    check("routing:non-asset", not irrelevant["asset_studio_relevant"] and irrelevant["provider"] is None, json.dumps(irrelevant, ensure_ascii=False))

    comfy = comfyui_healthcheck(dry_run=True)
    node = remote_render_node_healthcheck(dry_run=True)
    local_gpu = detect_local_gpu_capability(dry_run=True)
    check("probe:comfyui-local", comfy["scope"] == "local" and comfy["status"] == "dry-run-ready", json.dumps(comfy, ensure_ascii=False))
    check("probe:render-node-remote", node["scope"] == "remote" and node["status"] == "dry-run-ready" and "no local nvidia-smi" in node["checks"], json.dumps(node, ensure_ascii=False))
    check("probe:gpu-local", local_gpu["scope"] == "local" and local_gpu["status"] == "dry-run-ready", json.dumps(local_gpu, ensure_ascii=False))

    skills_ref = shutil.which("skills-ref")
    print(f"INFO skills-ref={'available' if skills_ref else 'unavailable'}; internal frontmatter validator is authoritative for this dependency-free checkout")
    failures = 0
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {name} - {detail}")
        failures += not ok
    print(f"SUMMARY checks={len(results)} passed={len(results) - failures} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
