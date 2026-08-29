"""Objective v0.4.1 validation with a tracked-archive regression check."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.constants import UGAS_VERSION
from ugas.master_assets import candidate_metrics, compile_generation_prompt, reference_edit_structural_qa
from ugas.model_registry import load_model, load_registry, validate_model_workflow_compatibility
from ugas.schema_validation import SchemaValidationError, validate_instance, validate_schema_document
from ugas.workflow_registry import load_workflow, load_workflows, validate_api_workflow

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str) -> None:
    RESULTS.append((name, bool(condition), detail))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def tracked(path: str) -> bool:
    if os.environ.get("UGAS_TRACKED_SNAPSHOT") == "1" or not (ROOT / ".git").exists():
        return (ROOT / path).is_file()
    result = subprocess.run(["git", "ls-files", "--error-unmatch", "--", path], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.returncode == 0


def snapshot_check() -> None:
    if os.environ.get("UGAS_SKIP_TRACKED_SNAPSHOT") == "1":
        check("snapshot:tracked", True, "nested snapshot check skipped")
        return
    if not (ROOT / ".git").exists():
        check("snapshot:git-context", True, "SKIP_EXTERNAL_GIT_CONTEXT")
        return
    with tempfile.TemporaryDirectory(prefix="ugas-v041-snapshot-") as directory:
        snapshot = Path(directory) / "snapshot"; snapshot.mkdir()
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True, check=False)
        if archive.returncode != 0:
            check("snapshot:archive", False, archive.stderr.decode(errors="replace")[-300:]); return
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
            tar.extractall(snapshot)
        python = sys.executable; env = os.environ.copy(); env["UGAS_SKIP_TRACKED_SNAPSHOT"] = "1"; env["UGAS_SKIP_NO_GIT_REGRESSION"] = "1"; env["PYTHONUTF8"] = "1"
        commands = [
            ("snapshot:unit-tests", [python, "-m", "unittest", "discover", "-s", "tests"]),
            ("snapshot:validation", [python, "scripts/validation/run_validation.py"]),
            ("snapshot:version", [python, "-m", "ugas.cli", "--version"]),
            ("snapshot:models", [python, "-m", "ugas.cli", "models", "list"]),
        ]
        for name, command in commands:
            result = subprocess.run(command, cwd=snapshot, env=env, capture_output=True, text=True, check=False)
            check(name, result.returncode == 0, (result.stdout + result.stderr).strip()[-500:])
        if os.environ.get("UGAS_SKIP_NO_GIT_REGRESSION") != "1":
            no_git = Path(directory) / "no-git"; shutil.copytree(snapshot, no_git, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))
            no_git_env = env.copy(); no_git_env.pop("UGAS_SKIP_TRACKED_SNAPSHOT", None); no_git_env["UGAS_REVIEW_SNAPSHOT"] = "1"; no_git_env["PYTHONPATH"] = str(no_git / "src"); result = subprocess.run([python, "scripts/validation/run_validation.py"], cwd=no_git, env=no_git_env, capture_output=True, text=True, check=False)
            check("snapshot:no-git", result.returncode == 0 and "SKIP_EXTERNAL_GIT_CONTEXT" in result.stdout, (result.stdout + result.stderr).strip()[-500:])


def main() -> int:
    required = ["README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.4.1.md", "LICENSE", "package.json", "pyproject.toml", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "providers/models/registry.json", "providers/workflows/registry.json", "providers/workflows/flux2-klein-4b-distilled-text-to-image.api.json", "providers/workflows/flux2-klein-base-4b-quality-text-to-image.api.json", "providers/workflows/flux2-klein-4b-distilled-image-edit.api.json", "providers/workflows/flux2-klein-base-4b-quality-image-edit.api.json", "providers/workflows/birefnet-background-removal.api.json", "docs/evidence/quality-benchmark.json", "docs/evidence/quality-benchmark-contact-sheet.png", "docs/evidence/candidates.json", "docs/evidence/reference-edit-qa.json", "docs/evidence/review-visuals.json"]
    for item in required: check(f"path:{item}", (ROOT / item).exists(), "present" if (ROOT / item).exists() else "missing")
    for item in required:
        if (ROOT / item).exists() and item not in {"README.md", "INSTALL.md", "CHECKPOINT.md"}: check(f"tracked:{item}", tracked(item), "tracked or review snapshot")
    schema_values = {}
    for path in (ROOT / "schemas").glob("*.json"):
        try: value = load_json(path); validate_schema_document(value); schema_values[path.stem] = value; check(f"schema:{path.name}", True, "valid JSON Schema")
        except (OSError, json.JSONDecodeError, SchemaValidationError) as exc: check(f"schema:{path.name}", False, str(exc))
    try:
        registry = load_registry(ROOT); validate_instance(registry, schema_values["model-registry"]); check("registry:models", len(registry["models"]) >= 4, "FAST, QUALITY, backlog candidate and BiRefNet records")
        for model in registry["models"]:
            validate_instance(model, schema_values["model-manifest"]); semantic = model["variant"] == "distilled" and model["recommended_steps"] == 4 and model["recommended_guidance"] == 1.0 or model["variant"] == "base" and model["recommended_steps"] == 50 and model["recommended_guidance"] == 4.0 or model["family"] == "birefnet"
            check(f"model:{model['id']}", model["commercial_use_status"] == "approved" and semantic, "license and Base/Distilled metadata valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc: check("registry:models", False, str(exc))
    try:
        workflows = load_workflows(ROOT); check("registry:workflows", len(workflows) == 5, "four FLUX lanes plus BiRefNet")
        for item in workflows:
            record = load_workflow(ROOT, item["id"]); graph = validate_api_workflow(record["api"]); model = load_model(ROOT, item["required_models"][0]); compatible = validate_model_workflow_compatibility(model, record)["compatible"]
            validate_instance({key: value for key, value in item.items() if key in {"schema_version", "id", "provider", "version", "inputs", "outputs", "model_family", "model_variant", "quality_tier", "parameters"}}, schema_values["workflow-manifest"])
            check(f"workflow:{item['id']}", graph["valid_graph"] and compatible and not item["custom_nodes_required"], "API graph and model compatibility valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError, ValueError) as exc: check("registry:workflows", False, str(exc))
    try:
        prompt = compile_generation_prompt({"positive_prompt": "fantasy warrior", "visual_style": "stylized readable", "orientation": "front-facing three-quarter"}); check("prompt:visual-only", "canvas" not in prompt.casefold() and "occupancy" not in prompt.casefold() and "entire body visible" in prompt, "machine spec is separated from visual prompt")
    except Exception as exc: check("prompt:visual-only", False, str(exc))
    benchmark = load_json(ROOT / "docs/evidence/quality-benchmark.json") if (ROOT / "docs/evidence/quality-benchmark.json").exists() else {}
    results = benchmark.get("results", []); check("benchmark:shared-seeds", benchmark.get("shared_seeds") == [4301, 4302, 4303] and len(results) == 6, "three shared seeds recorded for FAST and QUALITY")
    check("benchmark:parameters", all((item.get("steps"), item.get("guidance")) in {(4, 1.0), (50, 4.0)} for item in results), "lane parameters remain explicit")
    check("benchmark:no-automatic-winner", benchmark.get("visual_winner") is None and benchmark.get("visual_review") == "required", "visual winner remains human-reviewed")
    candidates = load_json(ROOT / "docs/evidence/candidates.json") if (ROOT / "docs/evidence/candidates.json").exists() else {}; check("pilot:eligible", bool(candidates.get("best_technical_candidate")) and candidates.get("selection_status") == "eligible", "selected pilot passed hard gates")
    check("pilot:no-clipping", all(not item.get("metrics", {}).get("edge_clipping", True) for item in candidates.get("candidates", []) if item.get("eligible")), "eligible candidates are not clipped")
    reference_qa = load_json(ROOT / "docs/evidence/reference-edit-qa.json") if (ROOT / "docs/evidence/reference-edit-qa.json").exists() else {}; check("reference:structural", reference_qa.get("status") == "REFERENCE_EDIT_QA_PASSED" and reference_qa.get("metrics", {}).get("silhouette_iou", 0) >= 0.70, "reference silhouette QA passed")
    visuals = load_json(ROOT / "docs/evidence/review-visuals.json") if (ROOT / "docs/evidence/review-visuals.json").exists() else {}; required_visual_names = {"quality-benchmark-contact-sheet.png", "quality-benchmark.json", "master-selected-before-bg.png", "master-selected-transparent.png", "master-selected-checkerboard.png", "reference-edit-before-after.png", "reference-edit-transparent.png", "reference-edit-qa.json"}; listed_visuals = {name for item in visuals.get("images", []) for name in (item.get("archive_name"), item.get("metadata_archive_name"))}; check("review:visual-manifest", required_visual_names.issubset(listed_visuals), "all v0.4.1 visual evidence is listed")
    review = (ROOT / "REVIEW-v0.4.1.md").read_text(encoding="utf-8") if (ROOT / "REVIEW-v0.4.1.md").exists() else ""; headings = ["STATUS", "VERSION", "FASE", "OBJETIVO", "ESCOPO", "BASELINE AUDIT FINDINGS", "ROOT CAUSE", "MODEL LANES", "WORKFLOW COMPATIBILITY", "FAST vs QUALITY BENCHMARK", "MASTER PILOT RESULT", "TRANSPARENCY RESULT", "REFERENCE EDIT RESULT", "REFERENCE STRUCTURAL QA", "TESTS", "VALIDATION", "GITHUB", "VISUAL REVIEW STATUS", "PENDENCIAS", "BLOQUEIOS", "DECISOES", "PROXIMO PASSO", "DEFINITION OF DONE"]; check("review:headings", all(f"## {heading}" in review for heading in headings), "exact review headings present"); check("review:no-production-claim", "PRODUCTION_READY" not in review and "production_ready: true" not in review.casefold(), "review never claims production approval")
    try:
        package_version = load_json(ROOT / "package.json")["version"]
        with (ROOT / "pyproject.toml").open("rb") as stream: pyproject_version = tomllib.load(stream)["project"]["version"]
        init_version = __import__("ugas").__version__; check("version:consistency", UGAS_VERSION == package_version == pyproject_version == init_version == "0.4.1", f"runtime={UGAS_VERSION}, package={package_version}, pyproject={pyproject_version}")
    except Exception as exc: check("version:consistency", False, str(exc))
    test_run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT, capture_output=True, text=True, check=False); check("tests:unit", test_run.returncode == 0, (test_run.stdout + test_run.stderr).strip()[-500:])
    snapshot_check(); failures = 0
    for name, ok, detail in RESULTS: print(f"{'PASS' if ok else 'FAIL'} {name} - {detail}"); failures += not ok
    print(f"SUMMARY checks={len(RESULTS)} passed={len(RESULTS) - failures} failed={failures}"); return 1 if failures else 0


if __name__ == "__main__": raise SystemExit(main())
