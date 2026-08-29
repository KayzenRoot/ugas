"""Objective v0.4.2 validation, historical coverage and tracked-snapshot checks."""

from __future__ import annotations

import io
import json
import os
import re
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
from ugas.master_assets import candidate_metrics, compile_generation_prompt, reference_edit_structural_qa, verify_asset_integrity
from ugas.model_registry import load_model, load_registry, validate_model_workflow_compatibility
from ugas.review import validate_review_visual_manifest
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


def _run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=timeout)


def snapshot_check() -> None:
    if os.environ.get("UGAS_SKIP_TRACKED_SNAPSHOT") == "1":
        check("snapshot:tracked", True, "nested snapshot check skipped")
        return
    if not (ROOT / ".git").exists():
        check("snapshot:git-context", True, "SKIP_EXTERNAL_GIT_CONTEXT")
        return
    with tempfile.TemporaryDirectory(prefix="ugas-v042-snapshot-") as directory:
        snapshot = Path(directory) / "snapshot"
        snapshot.mkdir()
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True, check=False)
        if archive.returncode != 0:
            check("snapshot:archive", False, archive.stderr.decode(errors="replace")[-500:])
            return
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
            try:
                tar.extractall(snapshot, filter="data")
            except TypeError:
                tar.extractall(snapshot)
        python = sys.executable
        env = os.environ.copy()
        env.update({"UGAS_SKIP_TRACKED_SNAPSHOT": "1", "UGAS_SKIP_NO_GIT_REGRESSION": "1", "PYTHONUTF8": "1"})
        commands = [
            ("snapshot:compileall", [python, "-m", "compileall", "-q", "src", "scripts", "tests"]),
            ("snapshot:unit-tests", [python, "-m", "unittest", "discover", "-s", "tests"]),
            ("snapshot:validation", [python, "scripts/validation/run_validation.py"]),
            ("snapshot:version", [python, "-m", "ugas.cli", "--version"]),
            ("snapshot:models", [python, "-m", "ugas.cli", "models", "list"]),
        ]
        for name, command in commands:
            result = _run(command, snapshot, env=env)
            check(name, result.returncode == 0, (result.stdout + result.stderr).strip()[-800:])
        if os.environ.get("UGAS_SKIP_NO_GIT_REGRESSION") != "1":
            no_git = Path(directory) / "no-git"
            shutil.copytree(snapshot, no_git, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))
            no_git_env = env.copy()
            no_git_env.pop("UGAS_SKIP_TRACKED_SNAPSHOT", None)
            no_git_env["UGAS_REVIEW_SNAPSHOT"] = "1"
            no_git_env["PYTHONPATH"] = str(no_git / "src")
            result = _run([python, "scripts/validation/run_validation.py"], no_git, env=no_git_env)
            check("snapshot:no-git", result.returncode == 0 and "SKIP_EXTERNAL_GIT_CONTEXT" in result.stdout, (result.stdout + result.stderr).strip()[-800:])


def _historical_coverage_checks() -> None:
    matrix = ROOT / "docs" / "test-coverage-matrix-v0.4.2.md"
    text = matrix.read_text(encoding="utf-8") if matrix.is_file() else ""
    historical_test_rows = sum(1 for line in text.splitlines() if line.startswith("| ") and "v0.4.0 intent" not in line and "---" not in line)
    check("coverage:historical-matrix", historical_test_rows >= 26, f"mapped rows={historical_test_rows}")
    test_file_text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py"))
    historical_names = [
        "test_expected_directories_and_documents_exist", "test_every_skill_has_valid_agent_skills_frontmatter", "test_profiles_and_schema_documents_validate", "test_templates_provider_and_workflow_instances_validate",
        "test_engine_markers_and_dimension_evidence", "test_context_scan_is_bounded_and_skips_heavy_directories", "test_installer_auto_selection_and_refresh_preserve_history",
        "test_default_availability_is_unknown", "test_asset_and_non_asset_classification", "test_3d_final_never_falls_back_to_2d_provider", "test_paid_disabled_keeps_self_hosted_remote_eligible", "test_qualified_2d_evidence_selects_comfyui_for_master_sprite", "test_partial_mmorpg_plan_exposes_animation_gap", "test_capability_gap_skips_preferred_provider_and_uses_capable_fallback",
        "test_local_and_remote_dry_runs_are_separate", "test_version_surfaces_are_consistent", "test_alpha_and_transparency_stats_distinguish_rgb_and_rgba", "test_client_api_flow_and_output_retrieval", "test_reference_upload_and_official_workflow_injection", "test_client_error_and_route_evidence", "test_client_timeout_is_structured", "test_capability_state_and_image_pipeline", "test_job_transitions_are_bounded", "test_sprite_pilot_allows_only_qualified_1x1_master", "test_prompt_compiler_is_reproducible", "test_candidate_metrics_and_visual_gate_are_distinct",
    ]
    check("coverage:historical-tests-restored", all(name in test_file_text for name in historical_names), "all 26 v0.4.0 test intents have named coverage")


def _v042_revision_checks() -> None:
    chain_path = ROOT / "docs" / "evidence" / "revision-chain.json"
    chain = load_json(chain_path) if chain_path.is_file() else {}
    revisions = chain.get("revisions", [])
    ids = [item.get("revision_id") for item in revisions]
    paths = [item.get("output_path") for item in revisions]
    hashes = [item.get("output_sha256") for item in revisions]
    check("revision-chain:four-revisions", len(revisions) == 4 and ids == ["R1", "R2", "R3", "R4"], f"revisions={ids}")
    check("revision-chain:paths-unique", len(set(paths)) == 4, "R1-R4 paths are distinct")
    check("revision-chain:hashes-recorded", all(isinstance(value, str) and len(value) == 64 for value in hashes), "all R1-R4 SHA-256 values are recorded")
    check("revision-chain:transparent-distinct", chain.get("r2_path_distinct_from_r4") is True and chain.get("r2_sha256_distinct_from_r4") is True, "R2/R4 logical roles are distinct")
    check("revision-chain:integrity", chain.get("revision_integrity") == "PASS", "pilot revision audit passed")
    for name in ("transparency-qa-master.json", "transparency-qa-reference-edit.json"):
        path = ROOT / "docs" / "evidence" / name
        value = load_json(path) if path.is_file() else {}
        check(f"transparency:{name}", value.get("status") == "passed" and value.get("rgb_preservation", {}).get("passed") is True and value.get("alpha_metrics", {}).get("near_opaque_foreground_fraction", 0) >= 0.85, "alpha and RGB preservation passed")
    qa = load_json(ROOT / "docs" / "evidence" / "reference-edit-qa.json") if (ROOT / "docs" / "evidence" / "reference-edit-qa.json").is_file() else {}
    physical_r2 = revisions[1].get("asset_revision_id") if len(revisions) > 1 else None
    physical_r4 = revisions[3].get("asset_revision_id") if len(revisions) > 3 else None
    source_is_r2 = qa.get("source_revision_id") in {"R2", physical_r2}
    output_is_r4 = qa.get("output_revision_id") in {"R4", physical_r4}
    check("reference:immutable-structural", qa.get("status") == "REFERENCE_EDIT_QA_PASSED" and qa.get("checks", {}).get("immutable_inputs") is True and source_is_r2 and output_is_r4, "structural QA compares immutable R2/R4")
    candidates = load_json(ROOT / "docs" / "evidence" / "candidates.json") if (ROOT / "docs" / "evidence" / "candidates.json").is_file() else {}
    eligible = [item for item in candidates.get("candidates", []) if item.get("eligible")]
    check("pilot:safe-margin", bool(eligible) and all(item.get("metrics", {}).get("safe_margin_ok") is True for item in eligible), "selected candidates respect declared margins")
    check("pilot:no-v041-reuse", candidates.get("schema_version") == UGAS_VERSION and candidates.get("pilot_id", "").startswith("v0.4.2"), "fresh pilot evidence is versioned")


def _review_checks() -> None:
    manifest_path = ROOT / "docs" / "evidence" / "review-visuals.json"
    manifest = load_json(manifest_path) if manifest_path.is_file() else {}
    result = validate_review_visual_manifest(manifest, ROOT) if manifest else {"status": "failed", "failures": ["manifest missing"]}
    check("review:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "all required roles are distinct and hash-valid")
    review_path = ROOT / "REVIEW-v0.4.2.md"
    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "FASE", "OBJETIVO", "ESCOPO", "AUDIT FINDINGS FIXED", "REVISION STORAGE", "REVISION INTEGRITY", "SAFE MARGINS", "TRANSPARENCY / RGB PRESERVATION", "REFERENCE EDIT REVISION CHAIN", "REFERENCE STRUCTURAL QA", "REAL RTX 5050 PILOT", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "VISUAL REVIEW STATUS", "PENDENCIAS", "BLOQUEIOS", "DECISOES", "PROXIMO PASSO", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("review:headings", all(f"## {heading}" in review for heading in headings), "exact v0.4.2 headings present")
    check("review:no-automatic-approval", "automatic visual approval" not in review.casefold() or "not inferred" in review.casefold(), "human review remains separate")


def main() -> int:
    required = [
        "README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.4.2.md", "LICENSE", "package.json", "pyproject.toml",
        "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "docs/test-coverage-matrix-v0.4.2.md",
        "providers/models/registry.json", "providers/workflows/registry.json", "schemas/asset-revision.json",
        "providers/workflows/flux2-klein-4b-distilled-text-to-image.api.json", "providers/workflows/flux2-klein-base-4b-quality-text-to-image.api.json",
        "providers/workflows/flux2-klein-4b-distilled-image-edit.api.json", "providers/workflows/flux2-klein-base-4b-quality-image-edit.api.json", "providers/workflows/birefnet-background-removal.api.json",
        "docs/evidence/quality-benchmark.json", "docs/evidence/quality-benchmark-contact-sheet.png", "docs/evidence/candidates.json", "docs/evidence/reference-edit-qa.json", "docs/evidence/review-visuals.json",
        "docs/evidence/revision-chain.json", "docs/evidence/transparency-qa-master.json", "docs/evidence/transparency-qa-reference-edit.json",
    ]
    for item in required:
        check(f"path:{item}", (ROOT / item).exists(), "present" if (ROOT / item).exists() else "missing")
        if (ROOT / item).exists() and item not in {"README.md", "INSTALL.md", "CHECKPOINT.md"}:
            check(f"tracked:{item}", tracked(item), "tracked or present in review snapshot")

    schemas: dict[str, dict] = {}
    for path in (ROOT / "schemas").glob("*.json"):
        try:
            value = load_json(path); validate_schema_document(value); schemas[path.stem] = value; check(f"schema:{path.name}", True, "valid JSON Schema")
        except (OSError, json.JSONDecodeError, SchemaValidationError) as exc:
            check(f"schema:{path.name}", False, str(exc))
    try:
        models = load_registry(ROOT); validate_instance(models, schemas["model-registry"]); check("registry:models", len(models.get("models", [])) >= 4, "explicit FAST, QUALITY, backlog and BiRefNet records")
        for model in models["models"]:
            validate_instance(model, schemas["model-manifest"])
            semantic = model["family"] == "birefnet" or (model["variant"] == "distilled" and model.get("recommended_steps") == 4 and model.get("recommended_guidance") == 1.0) or (model["variant"] == "base" and model.get("recommended_steps") == 50 and model.get("recommended_guidance") == 4.0)
            check(f"model:{model['id']}", model["commercial_use_status"] == "approved" and semantic, "license and lane semantics valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc:
        check("registry:models", False, str(exc))
    try:
        workflows = load_workflows(ROOT); check("registry:workflows", len(workflows) == 5, "four FLUX lanes plus BiRefNet")
        for item in workflows:
            record = load_workflow(ROOT, item["id"]); graph = validate_api_workflow(record["api"]); model = load_model(ROOT, item["required_models"][0]); compatible = validate_model_workflow_compatibility(model, record)["compatible"]
            check(f"workflow:{item['id']}", graph["valid_graph"] and compatible and not item["custom_nodes_required"] and item["schema_version"] == UGAS_VERSION, "native graph and model compatibility valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError, ValueError) as exc:
        check("registry:workflows", False, str(exc))
    try:
        prompt = compile_generation_prompt({"positive_prompt": "fantasy warrior", "visual_style": "stylized readable", "orientation": "front-facing three-quarter"}); check("prompt:visual-only", "canvas" not in prompt.casefold() and "occupancy" not in prompt.casefold() and "entire body visible" in prompt, "machine spec is separated from visual language")
    except Exception as exc:
        check("prompt:visual-only", False, str(exc))

    benchmark = load_json(ROOT / "docs/evidence/quality-benchmark.json") if (ROOT / "docs/evidence/quality-benchmark.json").is_file() else {}
    check("benchmark:historical-lanes", benchmark.get("shared_seeds") == [4301, 4302, 4303] and len(benchmark.get("results", [])) == 6, "FAST and QUALITY remain evidenced")
    check("benchmark:parameters", all((item.get("steps"), item.get("guidance")) in {(4, 1.0), (50, 4.0)} for item in benchmark.get("results", [])), "lane parameters remain explicit")
    check("benchmark:no-automatic-winner", benchmark.get("visual_winner") is None and benchmark.get("visual_review") == "required", "visual winner remains human-reviewed")
    _historical_coverage_checks()
    _v042_revision_checks()
    _review_checks()

    try:
        package_version = load_json(ROOT / "package.json")["version"]
        with (ROOT / "pyproject.toml").open("rb") as stream: pyproject_version = tomllib.load(stream)["project"]["version"]
        init_version = __import__("ugas").__version__
        check("version:consistency", UGAS_VERSION == package_version == pyproject_version == init_version == "0.4.2", f"runtime={UGAS_VERSION}, package={package_version}, pyproject={pyproject_version}")
    except Exception as exc:
        check("version:consistency", False, str(exc))
    docs = ["README.md", "INSTALL.md", "CHECKPOINT.md", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md"]
    check("docs:version", all(UGAS_VERSION in (ROOT / path).read_text(encoding="utf-8") for path in docs), "current operational docs identify 0.4.2")
    check("docs:animation-boundary", all(word in (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8").casefold() for word in ("animation", "no animation")), "checkpoint does not authorize animation")
    check("security:weights-not-tracked", not any(path.suffix.casefold() in {".safetensors", ".ckpt", ".gguf", ".onnx"} for path in ROOT.joinpath(".git").glob("**/*") if path.is_file()) if (ROOT / ".git").exists() else True, "model weights are outside Git")

    compile_run = _run([sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"], ROOT)
    check("tests:compileall", compile_run.returncode == 0, (compile_run.stdout + compile_run.stderr).strip()[-500:])
    test_run = _run([sys.executable, "-m", "unittest", "-q"], ROOT, timeout=240)
    test_text = test_run.stdout + test_run.stderr
    match = re.search(r"Ran (\d+) tests", test_text)
    check("tests:unit", test_run.returncode == 0 and match is not None and int(match.group(1)) >= 58, test_text.strip()[-800:])
    snapshot_check()
    failures = 0
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'} {name} - {detail}")
        failures += not ok
    print(f"SUMMARY checks={len(RESULTS)} passed={len(RESULTS) - failures} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
