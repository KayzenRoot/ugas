"""Objective v0.3.1 repository validation with public-snapshot evidence."""

from __future__ import annotations

import json
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from unittest.mock import patch
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
from ugas.constants import UGAS_VERSION
from ugas.model_registry import load_registry, load_model
from ugas.workflow_registry import load_workflows, load_workflow, validate_api_workflow
from ugas.image_utils import inspect_png
from ugas.qa import validate_output
from ugas.generation import GenerationError, sprite_pilot


results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str) -> None:
    results.append((name, bool(condition), detail))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git_tracked(relative: str) -> bool:
    if os.environ.get("UGAS_TRACKED_SNAPSHOT") == "1":
        return True
    result = subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.returncode == 0 and bool(result.stdout.strip())


def run_snapshot_check() -> None:
    """Run the required install/CLI/tests from an exact ``git archive HEAD``."""
    if os.environ.get("UGAS_SKIP_TRACKED_SNAPSHOT") == "1":
        check("snapshot:tracked", True, "nested validation skipped inside the isolated archive")
        return
    with tempfile.TemporaryDirectory(prefix="ugas-tracked-snapshot-") as directory:
        snapshot = Path(directory) / "snapshot"
        snapshot.mkdir()
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True, check=False)
        if archive.returncode != 0:
            check("snapshot:git-archive", False, archive.stderr.decode(errors="replace")[:300])
            return
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
            tar.extractall(snapshot)
        venv = snapshot / ".venv"
        create_venv = subprocess.run([sys.executable, "-m", "venv", str(venv)], cwd=snapshot, capture_output=True, text=True, check=False)
        check("snapshot:venv", create_venv.returncode == 0, create_venv.stderr[-300:])
        if create_venv.returncode != 0:
            return
        python_exe = venv / "Scripts" / "python.exe"
        ugas_exe = venv / "Scripts" / "ugas.exe"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["UGAS_SKIP_TRACKED_SNAPSHOT"] = "1"
        env["UGAS_TRACKED_SNAPSHOT"] = "1"
        env["PYTHONUTF8"] = "1"
        commands = [
            ("snapshot:pip-install", [str(python_exe), "-m", "pip", "install", "-e", "."]),
            ("snapshot:ugas-version", [str(ugas_exe), "--version"]),
            ("snapshot:models-list", [str(ugas_exe), "models", "list"]),
            ("snapshot:workflows-list", [str(ugas_exe), "workflows", "list"]),
            ("snapshot:unit-tests", [str(python_exe), "scripts/tests/run_tests.py"]),
            ("snapshot:validation", [str(python_exe), "scripts/validation/run_validation.py"]),
            ("snapshot:capability-controlled-gap", [str(ugas_exe), "capability", "--url", "http://127.0.0.1:1"]),
        ]
        for name, command in commands:
            result = subprocess.run(command, cwd=snapshot, env=env, capture_output=True, text=True, check=False)
            expected = result.returncode == 0
            if name == "snapshot:capability-controlled-gap":
                expected = result.returncode == 0 and '"state": "unavailable"' in result.stdout
            detail = (result.stdout + result.stderr).strip().replace("\n", " ")[-400:]
            check(name, expected, detail or f"exit={result.returncode}")
            if not expected and name == "snapshot:pip-install":
                break


def main() -> int:
    required_paths = [
        "README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.2.md", "REVIEW-v0.2.1.md", "REVIEW-v0.3.1.md", "LICENSE", "package.json", "pyproject.toml",
        "docs", "skills", "profiles", "templates", "schemas", "providers", "scripts", "examples", "tests",
        "providers/models/registry.json", "providers/workflows/registry.json",
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
            safe = not {"3d-model", "animation", "material", "lod"}.intersection(manifest.get("capabilities", []))
            source_ok = not manifest.get("asset_capabilities_qualified", [])
            check(f"provider:{provider}", manifest["id"] == provider and manifest["cost_class"] in {"local", "self-hosted", "free-tier", "paid"} and safe and source_ok, "manifest validates; asset readiness is evidence-derived, not static")
        except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc:
            check(f"provider:{provider}", False, str(exc))
    for workflow in (ROOT / "providers" / "workflows").glob("*.json"):
        if workflow.name in {"registry.json", "flux2-klein-4b-text-to-image.api.json"}:
            continue
        try:
            validate_instance(load_json(workflow), schemas["workflow-manifest"])
            check(f"workflow:{workflow.name}", True, "workflow manifest validates")
        except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc:
            check(f"workflow:{workflow.name}", False, str(exc))
    try:
        model_registry = load_registry(ROOT)
        validate_instance(model_registry, schemas["model-registry"])
        check("registry:models", len(model_registry.get("models", [])) >= 2, "two explicit FLUX.2 Klein candidates with license/hash gates")
        for model in model_registry["models"]:
            validate_instance(model, schemas["model-manifest"])
            qualified = model["status"] == "qualified" and model.get("qualification_evidence", {}).get("hashes_verified") is True
            candidate = model["status"] == "candidate"
            check(f"model:{model['id']}", model["commercial_use_status"] == "approved" and (qualified or candidate), "approved license; exact hashes/smoke gate recorded" if qualified else "approved license; qualification remains gated by exact hashes and smoke")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc:
        check("registry:models", False, str(exc))
    check("tracked:providers/models/registry.json", (ROOT / "providers" / "models" / "registry.json").is_file() and git_tracked("providers/models/registry.json"), "public model registry is tracked")
    try:
        workflow_registry = {"schema_version": "0.3.0", "workflows": load_workflows(ROOT)}
        check("registry:workflows", len(workflow_registry["workflows"]) >= 1, "native API workflow registry present")
        for item in workflow_registry["workflows"]:
            record = load_workflow(ROOT, item["id"])
            graph = validate_api_workflow(record["api"])
            check(f"workflow-api:{item['id']}", graph["valid_graph"] and not item["custom_nodes_required"], "API graph is statically valid and custom-node-free")
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        check("registry:workflows", False, str(exc))
    check("tracked:providers/workflows/registry.json", (ROOT / "providers" / "workflows" / "registry.json").is_file() and git_tracked("providers/workflows/registry.json"), "public workflow registry is tracked")
    check("tracked:workflow-api-json", any(git_tracked(path.relative_to(ROOT).as_posix()) for path in (ROOT / "providers" / "workflows").glob("*.api.json")), "native API workflow JSON is tracked")
    evidence_path = ROOT / "docs" / "evidence" / "comfyui-smoke.json"
    try:
        evidence = load_json(evidence_path)
        validate_instance(evidence, schemas["capability-evidence"])
        check("evidence:comfyui-smoke", evidence["state"] == "verified" and evidence["smoke_test"]["status"] == "passed" and evidence.get("asset_capabilities_qualified") == ["2d", "sprite-master", "sprite-generation"], "real local RTX 5050 smoke evidence is recorded as the qualification source")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc:
        check("evidence:comfyui-smoke", False, str(exc))
    sprite_evidence_path = ROOT / "docs" / "evidence" / "sprite-pilot.json"
    try:
        sprite_evidence = load_json(sprite_evidence_path)
        validate_instance(sprite_evidence, schemas["sprite-sheet"])
        qa = sprite_evidence["qa"]
        check("evidence:sprite-pilot", qa["technical_status"] == "TECHNICAL_VALID" and qa["visual_review"] == "required" and qa["production_ready"] is False, "real sprite-pilot sheet evidence is recorded without production claim")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc:
        check("evidence:sprite-pilot", False, str(exc))
    declared_route = route_request("Criar sprite de inventário", capability_evidence={"provider-comfyui": {"state": "declared", "capability": "2d"}})
    check("routing:declared-not-selected", declared_route["provider"] is None and declared_route["routing_status"] == "unknown", "declared capability is not treated as ready")
    check("docs:clone-directory", "cd universal-game-asset-studio" not in (ROOT / "INSTALL.md").read_text(encoding="utf-8"), "installation docs use actual clone directory")

    try:
        package_version = load_json(ROOT / "package.json")["version"]
        with (ROOT / "pyproject.toml").open("rb") as stream:
            pyproject_version = tomllib.load(stream)["project"]["version"]
        init_version = __import__("ugas").__version__
        version_ok = UGAS_VERSION == package_version == pyproject_version == init_version == "0.3.1"
        docs_ok = all("0.3.1" in (ROOT / name).read_text(encoding="utf-8") for name in ("README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.3.1.md"))
        check("version:consistency", version_ok and docs_ok, f"runtime={UGAS_VERSION}, package={package_version}, pyproject={pyproject_version}, docs={docs_ok}")
    except (OSError, json.JSONDecodeError, KeyError, tomllib.TOMLDecodeError) as exc:
        check("version:consistency", False, str(exc))

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
        runtime = generated / "tools" / "ugas_runtime.py"
        fresh = subprocess.run([sys.executable, str(runtime), "--version"], cwd=temp_root, capture_output=True, text=True, check=False)
        check("installer:fresh-consumer-runtime", fresh.returncode == 0 and fresh.stdout.strip() == UGAS_VERSION, "copied runtime executes from a different cwd")

    for example in ["consumer-godot-2d", "consumer-space-idle-2d", "consumer-generic-3d"]:
        target = ROOT / "examples" / example / ".game-assets"
        check(f"example:{example}", target.exists() and all((target / name).exists() for name in CONSUMER_FILES), "tracked example has the consumer contract")

    available_all = {provider: "available" for provider in ("provider-comfyui", "provider-remote-render-node", "provider-huggingface")}
    two_d = route_request("Criar vila humana 2D de MMORPG", availability=available_all)
    check("routing:2d-unqualified-gap", two_d["provider"] is None and two_d["routing_status"] == "capability_gap" and "2d" in two_d["capability_gaps"]["provider-comfyui"], json.dumps(two_d, ensure_ascii=False))
    qualified_2d = route_request("Criar um master sprite 2D do guerreiro", capability_evidence={"provider-comfyui": {"state": "verified", "asset_capabilities_qualified": ["2d", "sprite-master", "sprite-generation"]}})
    check("routing:2d-qualified-evidence", qualified_2d["provider"] == "provider-comfyui" and qualified_2d["routing_status"] == "resolved", json.dumps(qualified_2d, ensure_ascii=False))
    three_d = route_request("Criar boss 3D stylized", availability=available_all)
    check("routing:3d-capability-gap", three_d["provider"] is None and three_d["routing_status"] == "capability_gap" and "3d-model" in three_d["required_capabilities"], json.dumps(three_d, ensure_ascii=False))
    animation = route_request("Criar animação completa de caminhada 8 frames", availability=available_all)
    check("routing:animation-capability-gap", animation["provider"] is None and animation["routing_status"] == "capability_gap" and "animation" in animation["capability_gaps"]["provider-comfyui"], json.dumps(animation, ensure_ascii=False))
    gap = route_request("Criar boss 3D stylized", availability={"provider-comfyui": "unavailable", "provider-remote-render-node": "unavailable", "provider-huggingface": "available"})
    check("routing:3d-no-2d-fallback", gap["provider"] is None and gap["routing_status"] == "capability_gap", json.dumps(gap, ensure_ascii=False))
    remote = route_request("Criar boss 3D stylized", policy="paid-disabled", availability={"provider-comfyui": "unavailable", "provider-remote-render-node": "available", "provider-huggingface": "available"})
    check("routing:self-hosted-needs-qualified-evidence", remote["provider"] is None and remote["routing_status"] == "capability_gap", json.dumps(remote, ensure_ascii=False))
    unknown = route_request("Criar sprite de inventário")
    check("routing:unknown-without-probe", unknown["provider"] is None and unknown["routing_status"] == "unknown", json.dumps(unknown, ensure_ascii=False))
    irrelevant = route_request("Ajustar matchmaking do jogo")
    check("routing:non-asset", not irrelevant["asset_studio_relevant"] and irrelevant["provider"] is None, json.dumps(irrelevant, ensure_ascii=False))

    try:
        from PIL import Image
        with tempfile.TemporaryDirectory(prefix="ugas-alpha-") as directory:
            alpha_root = Path(directory)
            rgb_path = alpha_root / "rgb.png"
            opaque_path = alpha_root / "opaque.png"
            transparent_path = alpha_root / "transparent.png"
            Image.new("RGB", (2, 2), (255, 0, 0)).save(rgb_path)
            Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(opaque_path)
            transparent = Image.new("RGBA", (2, 2), (255, 0, 0, 255)); transparent.putpixel((0, 0), (255, 0, 0, 0)); transparent.save(transparent_path)
            rgb_info, opaque_info, transparent_info = (inspect_png(path) for path in (rgb_path, opaque_path, transparent_path))
            check("qa:alpha-rgb", rgb_info["source_mode"] == "RGB" and not rgb_info["has_alpha_channel"] and not rgb_info["has_transparent_pixels"], json.dumps(rgb_info))
            check("qa:alpha-rgba-opaque", opaque_info["has_alpha_channel"] and not opaque_info["has_transparent_pixels"] and opaque_info["alpha_min"] == 255, json.dumps(opaque_info))
            check("qa:alpha-rgba-transparent", transparent_info["has_alpha_channel"] and transparent_info["has_transparent_pixels"] and transparent_info["alpha_min"] == 0, json.dumps(transparent_info))
            check("qa:transparency-requirement", validate_output(rgb_path, requires_transparency=True)["status"] == "failed" and validate_output(transparent_path, requires_transparency=True)["status"] == "TECHNICAL_VALID", "transparency is a separate requirement from non-empty content")
            with patch("ugas.generation.generate_image", return_value={"output": str(rgb_path), "job": {"job_id": "validation-job"}}):
                pilot = sprite_pilot(ROOT, endpoint="http://127.0.0.1:1", prompt="master", output_dir=alpha_root / "pilot", columns=1, rows=1)
            check("sprite-pilot:1x1", Path(pilot["sprite_sheet"]).is_file(), "master-only pilot materializes a 1x1 sheet")
            try:
                sprite_pilot(ROOT, endpoint="http://127.0.0.1:1", prompt="grid", output_dir=alpha_root / "pilot", columns=2, rows=1)
                grid_error = False
            except GenerationError as exc:
                grid_error = str(exc) == "sprite-grid workflow not qualified in v0.3.1"
            check("sprite-pilot:grid-rejected", grid_error, "grid > 1 fails closed until a qualified sprite-grid workflow exists")
    except (ImportError, OSError, ValueError, KeyError) as exc:
        for name in ("qa:alpha-rgb", "qa:alpha-rgba-opaque", "qa:alpha-rgba-transparent", "qa:transparency-requirement", "sprite-pilot:1x1", "sprite-pilot:grid-rejected"):
            check(name, False, str(exc))

    comfy = comfyui_healthcheck(dry_run=True)
    node = remote_render_node_healthcheck(dry_run=True)
    local_gpu = detect_local_gpu_capability(dry_run=True)
    check("probe:comfyui-local", comfy["scope"] == "local" and comfy["status"] == "dry-run-ready", json.dumps(comfy, ensure_ascii=False))
    check("probe:render-node-remote", node["scope"] == "remote" and node["status"] == "dry-run-ready" and "no local nvidia-smi" in node["checks"], json.dumps(node, ensure_ascii=False))
    check("probe:gpu-local", local_gpu["scope"] == "local" and local_gpu["status"] == "dry-run-ready", json.dumps(local_gpu, ensure_ascii=False))

    run_snapshot_check()

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
