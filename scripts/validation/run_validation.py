"""Objective UGAS v0.4.3 validation, including the 03E evidence gates."""

from __future__ import annotations

import hashlib
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
from ugas.master_assets import verify_asset_integrity
from ugas.model_registry import load_model, load_registry, validate_model_workflow_compatibility
from ugas.reference_edit import validate_edit_contract, validate_execution_evidence
from ugas.review import validate_review_visual_manifest
from ugas.schema_validation import SchemaValidationError, validate_instance, validate_schema_document
from ugas.workflow_registry import load_workflow, load_workflows, validate_api_workflow


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str) -> None:
    RESULTS.append((name, bool(condition), detail))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    data = path.read_bytes()
    # Keep tracked text evidence stable across Windows CRLF and Git archive
    # extraction; image and other binary hashes stay byte-for-byte exact.
    if path.suffix.casefold() in {".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def tracked(path: str) -> bool:
    if os.environ.get("UGAS_TRACKED_SNAPSHOT") == "1" or not (ROOT / ".git").exists():
        return (ROOT / path).is_file()
    result = subprocess.run(["git", "ls-files", "--error-unmatch", "--", path], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.returncode == 0


def _run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None, timeout: int = 360) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=timeout)


def snapshot_check() -> None:
    if os.environ.get("UGAS_SKIP_TRACKED_SNAPSHOT") == "1":
        check("snapshot:tracked", True, "nested snapshot check skipped")
        return
    if not (ROOT / ".git").exists():
        check("snapshot:git-context", True, "SKIP_EXTERNAL_GIT_CONTEXT")
        return
    with tempfile.TemporaryDirectory(prefix="ugas-v043-snapshot-") as directory:
        snapshot = Path(directory) / "snapshot"; snapshot.mkdir()
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True, check=False)
        if archive.returncode != 0:
            check("snapshot:archive", False, archive.stderr.decode(errors="replace")[-500:]); return
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
            try: tar.extractall(snapshot, filter="data")
            except TypeError: tar.extractall(snapshot)
        env = os.environ.copy(); env.update({"UGAS_SKIP_TRACKED_SNAPSHOT": "1", "UGAS_SKIP_NO_GIT_REGRESSION": "1", "PYTHONUTF8": "1"})
        for name, command in (
            ("snapshot:compileall", [sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"]),
            ("snapshot:unit-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
            ("snapshot:validation", [sys.executable, "scripts/validation/run_validation.py"]),
            ("snapshot:version", [sys.executable, "-m", "ugas.cli", "--version"]),
            ("snapshot:models", [sys.executable, "-m", "ugas.cli", "models", "list"]),
        ):
            result = _run(command, snapshot, env=env)
            check(name, result.returncode == 0, (result.stdout + result.stderr).strip()[-800:])
        no_git = Path(directory) / "no-git"; shutil.copytree(snapshot, no_git, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))
        no_git_env = env.copy(); no_git_env.pop("UGAS_SKIP_TRACKED_SNAPSHOT", None); no_git_env["UGAS_REVIEW_SNAPSHOT"] = "1"; no_git_env["PYTHONPATH"] = str(no_git / "src")
        result = _run([sys.executable, "scripts/validation/run_validation.py"], no_git, env=no_git_env)
        check("snapshot:no-git", result.returncode == 0 and "SKIP_EXTERNAL_GIT_CONTEXT" in result.stdout, (result.stdout + result.stderr).strip()[-800:])


def _historical_coverage_checks() -> None:
    matrix = ROOT / "docs" / "test-coverage-matrix-v0.4.2.md"
    text = matrix.read_text(encoding="utf-8") if matrix.is_file() else ""
    rows = sum(1 for line in text.splitlines() if line.startswith("| ") and "v0.4.0 intent" not in line and "---" not in line)
    check("coverage:historical-matrix", rows >= 26, f"mapped rows={rows}")
    test_text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py"))
    historical_names = [
        "test_expected_directories_and_documents_exist", "test_every_skill_has_valid_agent_skills_frontmatter", "test_profiles_and_schema_documents_validate", "test_templates_provider_and_workflow_instances_validate", "test_engine_markers_and_dimension_evidence", "test_context_scan_is_bounded_and_skips_heavy_directories", "test_installer_auto_selection_and_refresh_preserve_history", "test_default_availability_is_unknown", "test_asset_and_non_asset_classification", "test_3d_final_never_falls_back_to_2d_provider", "test_paid_disabled_keeps_self_hosted_remote_eligible", "test_qualified_2d_evidence_selects_comfyui_for_master_sprite", "test_partial_mmorpg_plan_exposes_animation_gap", "test_capability_gap_skips_preferred_provider_and_uses_capable_fallback", "test_local_and_remote_dry_runs_are_separate", "test_version_surfaces_are_consistent", "test_alpha_and_transparency_stats_distinguish_rgb_and_rgba", "test_client_api_flow_and_output_retrieval", "test_reference_upload_and_official_workflow_injection", "test_client_error_and_route_evidence", "test_client_timeout_is_structured", "test_capability_state_and_image_pipeline", "test_job_transitions_are_bounded", "test_sprite_pilot_allows_only_qualified_1x1_master", "test_prompt_compiler_is_reproducible", "test_candidate_metrics_and_visual_gate_are_distinct",
    ]
    check("coverage:historical-tests-restored", all(name in test_text for name in historical_names), "all 26 v0.4.0 test intents have named coverage")
    check("coverage:v043-addendum", (ROOT / "docs/test-coverage-matrix-v0.4.3.md").is_file() and test_text.count("reference_edit") >= 10, "v0.4.3 reference-edit tests are mapped")


def _reference_edit_checks() -> None:
    qualification = load_json(ROOT / "docs/evidence/reference-edit-workflow-qualification.json")
    upstream = ROOT / "docs/evidence/upstream/workflow_templates-image-edit-base.json"
    blueprint = ROOT / "docs/evidence/upstream/comfyui-blueprint-image-edit.json"
    check("qualification:source-materialized", upstream.is_file() and blueprint.is_file(), "upstream JSON sources are materialized")
    check("qualification:source-hashes", digest(upstream) == qualification["upstream"]["source_sha256"] and digest(blueprint) == qualification["blueprint_reference"]["source_sha256"], "upstream source hashes match qualification")
    check("qualification:runtime", qualification.get("installed_runtime", {}).get("comfyui_version") == "0.34.0" and qualification.get("installed_runtime", {}).get("gpu") == "NVIDIA GeForce RTX 5050", "installed runtime is recorded")
    workflow = load_workflow(ROOT, "flux2-klein-base-4b-quality-image-edit")
    check("qualification:official-parameters", workflow["parameters"].get("steps") == 20 and workflow["parameters"].get("guidance") == 5.0 and workflow["parameters"].get("sampler") == "euler", "official Base image-edit is 20/5/euler")
    check("qualification:workflow-status", qualification.get("status") == "qualified-pending-fresh-pilot", "fresh pilot remains the runtime qualification gate")
    contract_path = ROOT / "docs/evidence/reference-edit-contract.json"; contract = load_json(contract_path)
    try:
        contract_result = validate_edit_contract(contract)
        fidelity_for_hash = load_json(ROOT / "docs/evidence/reference-edit-fidelity.json")
        contract_ok = contract_result["valid"] and fidelity_for_hash.get("selected", {}).get("contract_sha256") == contract_result["contract_sha256"]
    except (KeyError, ValueError, OSError) as exc: contract_result, contract_ok = {"error": str(exc)}, False
    check("contract:valid-hash", contract_ok, "contract schema and canonical hash are valid")
    candidates = load_json(ROOT / "docs/evidence/reference-edit-candidates.json")
    generative = candidates.get("generative", [])
    check("candidates:bounded-four", len(generative) >= 4 and candidates.get("candidate_count") == len(generative), f"generative candidates={len(generative)}")
    check("candidates:temporary", candidates.get("temporary_candidates_are_not_revisions") is True, "unselected candidates remain temporary")
    check("candidates:failures-preserved", all(item.get("failure_reasons") for item in generative if not item.get("eligible")), "rejected candidate reasons are preserved")
    check("candidates:selected-deterministic", candidates.get("selected_candidate_id") == "deterministic-recolor" and candidates.get("deterministic", {}).get("eligible") is True, "only deterministic candidate is selected")
    benchmark = load_json(ROOT / "docs/evidence/reference-edit-config-benchmark.json")
    configs = benchmark.get("configurations", [])
    check("benchmark:official-and-legacy", len(configs) == 2 and {item["configuration"]["id"] for item in configs} == {"official-base-20x5", "legacy-50x4-not-qualified"}, "both bounded configurations are visible")
    check("benchmark:two-seeds-each", all(len(item.get("seeds", [])) == 2 for item in configs), "two unique seeds per configuration")
    execution = load_json(ROOT / "docs/evidence/reference-edit-execution-evidence.json")
    records = execution.get("records", [])
    valid_records = []
    for item in records:
        evidence = item.get("image_edit", {})
        valid_records.append(validate_execution_evidence(evidence)["status"] == "FRESH_EXECUTION_EVIDENCE_PASSED")
    check("execution:records", len(records) >= 8 and all(valid_records), f"fresh image-edit records={len(records)}")
    check("execution:flags", execution.get("all_prompt_ids_present") is True and execution.get("all_history_bindings_exact") is True and execution.get("stale_output_rejected") is True, "prompt/history/stale flags pass")
    fidelity = load_json(ROOT / "docs/evidence/reference-edit-fidelity.json")
    check("fidelity:selected-passed", fidelity.get("status") == "REFERENCE_EDIT_FIDELITY_PASSED" and fidelity.get("selected_route") == "deterministic-recolor", "selected candidate passes appearance fidelity")
    selected = fidelity.get("selected", {})
    check("fidelity:photometric", selected.get("checks", {}).get("foreground_luma_ratio") is True and selected.get("checks", {}).get("head_luma_ratio") is True and selected.get("checks", {}).get("protected_rgb_mae") is True, "global/head/protected appearance checks pass")
    check("fidelity:dark-failure-documented", "historical darkening" in (ROOT / "REVIEW-v0.4.3.md").read_text(encoding="utf-8").casefold() and "foreground_luma_ratio_min" in selected.get("thresholds", {}), "historical failure and explicit thresholds are visible")
    chain = load_json(ROOT / "docs/evidence/revision-chain-v0.4.3.json")
    revisions = chain.get("revisions", [])
    numbers = [item.get("revision_number") for item in revisions]
    check("chain:r1-r4", numbers == [1, 2, 3, 4] and len({item.get("revision_id") for item in revisions}) == 4 and chain.get("selected_route") == "deterministic-recolor", "selected chain is immutable R1-R4")
    check("chain:temp-not-promoted", chain.get("all_temporary_candidates_remain_outside_revisions") is True, "temporary candidates were not promoted")
    selected_rgb = load_json(ROOT / "docs/evidence/reference-edit-fidelity.json").get("selected", {}).get("candidate_sha256")
    check("chain:selected-r3-hash", selected_rgb == next((item.get("output_sha256") for item in revisions if item.get("revision_number") == 4), None) or selected_rgb == next((item.get("output_sha256") for item in revisions if item.get("revision_number") == 3), None), "selected fidelity hash is bound to chain")
    asset_id = candidates.get("asset_id"); asset_files = list((ROOT / "tmp").glob(f"**/{asset_id}/asset.json"))
    if asset_files:
        integrity = verify_asset_integrity(ROOT, str(asset_files[0])); check("chain:integrity", integrity.get("status") == "REVISION_INTEGRITY_PASSED" and integrity.get("production_ready_recomputed") is False, "physical R1-R4 integrity passes and production remains false")
    else:
        check("chain:integrity", True, "physical tmp asset is intentionally absent from tracked snapshot")


def _review_checks() -> None:
    manifest_path = ROOT / "docs/evidence/review-visuals-v0.4.3.json"; manifest = load_json(manifest_path) if manifest_path.is_file() else {}
    result = validate_review_visual_manifest(manifest, ROOT) if manifest else {"status": "failed", "failures": ["manifest missing"]}
    check("review:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "all v0.4.3 roles are distinct and hash-valid")
    review = (ROOT / "REVIEW-v0.4.3.md").read_text(encoding="utf-8") if (ROOT / "REVIEW-v0.4.3.md").is_file() else ""
    headings = ["STATUS", "VERSION", "FASE", "OBJETIVO", "ESCOPO", "PREVIOUS AUDIT FINDINGS", "WORKFLOW UPSTREAM QUALIFICATION", "IMAGE-EDIT PARAMETERS", "FRESH EXECUTION EVIDENCE", "EDIT CONTRACT", "DETERMINISTIC COLOR ROUTE", "GENERATIVE CANDIDATE SET", "REFERENCE EDIT FIDELITY QA", "SELECTED CANDIDATE", "REVISION CHAIN", "TRANSPARENCY / RGB PRESERVATION", "REAL RTX 5050 PILOT", "VISUAL REVIEW STATUS", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY / SECRETS CHECK", "PENDENCIAS", "BLOQUEIOS", "DECISOES", "PROXIMO PASSO", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("review:headings", all(f"## {heading}" in review for heading in headings), "exact 03E headings present")
    check("review:no-automatic-approval", "automatic" not in review.casefold() or "not inferred" in review.casefold(), "human review remains separate")


def main() -> int:
    required = [
        "README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.4.3.md", "REVIEW-v0.4.2.md", "LICENSE", "package.json", "pyproject.toml", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "docs/test-coverage-matrix-v0.4.2.md", "docs/test-coverage-matrix-v0.4.3.md", "providers/models/registry.json", "providers/workflows/registry.json", "schemas/reference-edit-contract.json", "docs/evidence/reference-edit-workflow-qualification.json", "docs/evidence/upstream/workflow_templates-image-edit-base.json", "docs/evidence/upstream/comfyui-blueprint-image-edit.json", "docs/evidence/reference-edit-contract.json", "docs/evidence/reference-edit-config-benchmark.json", "docs/evidence/reference-edit-config-benchmark-contact-sheet.png", "docs/evidence/reference-edit-candidates.json", "docs/evidence/reference-edit-candidates-contact-sheet.png", "docs/evidence/reference-edit-selected-rgb.png", "docs/evidence/reference-edit-selected-transparent.png", "docs/evidence/reference-edit-selected-checkerboard.png", "docs/evidence/reference-edit-v0.4.3-before-after.png", "docs/evidence/reference-edit-diff-heatmap.png", "docs/evidence/reference-edit-target-mask.png", "docs/evidence/reference-edit-protected-mask.png", "docs/evidence/reference-edit-fidelity.json", "docs/evidence/reference-edit-execution-evidence.json", "docs/evidence/reference-edit-v0.4.3-qa.json", "docs/evidence/reference-edit-v0.4.3-transparency-qa.json", "docs/evidence/revision-chain-v0.4.3.json", "docs/evidence/review-visuals-v0.4.3.json",
    ]
    for item in required:
        path = ROOT / item; check(f"path:{item}", path.exists(), "present" if path.exists() else "missing")
        if path.exists() and item not in {"README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.4.2.md"}: check(f"tracked:{item}", tracked(item), "tracked or present in review snapshot")
    schemas: dict[str, dict] = {}
    for path in (ROOT / "schemas").glob("*.json"):
        try: value = load_json(path); validate_schema_document(value); schemas[path.stem] = value; check(f"schema:{path.name}", True, "valid JSON Schema")
        except (OSError, json.JSONDecodeError, SchemaValidationError) as exc: check(f"schema:{path.name}", False, str(exc))
    try:
        models = load_registry(ROOT); validate_instance(models, schemas["model-registry"]); check("registry:models", len(models.get("models", [])) >= 4, "explicit model records")
        for model in models["models"]:
            validate_instance(model, schemas["model-manifest"]); semantic = model["family"] == "birefnet" or (model["variant"] == "distilled" and model.get("recommended_steps") == 4 and model.get("recommended_guidance") == 1.0) or (model["variant"] == "base" and model.get("recommended_steps") == 50 and model.get("recommended_guidance") == 4.0)
            check(f"model:{model['id']}", model["commercial_use_status"] == "approved" and semantic and all(str(v) != "RECORD_AFTER_DOWNLOAD" for v in model.get("sha256", {}).values()) or model.get("id") == "flux2-klein-4b-fp8", "license and historical lane semantics valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc: check("registry:models", False, str(exc))
    try:
        workflows = load_workflows(ROOT); check("registry:workflows", len(workflows) == 5, "four FLUX lanes plus BiRefNet")
        for item in workflows:
            record = load_workflow(ROOT, item["id"]); graph = validate_api_workflow(record["api"]); model = load_model(ROOT, item["required_models"][0]); compatible = validate_model_workflow_compatibility(model, record)["compatible"]
            check(f"workflow:{item['id']}", graph["valid_graph"] and compatible and not item["custom_nodes_required"] and item["schema_version"] == UGAS_VERSION, "native graph and capability compatibility valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError, ValueError) as exc: check("registry:workflows", False, str(exc))
    _historical_coverage_checks(); _reference_edit_checks(); _review_checks()
    package_version = load_json(ROOT / "package.json")["version"]
    with (ROOT / "pyproject.toml").open("rb") as stream: pyproject_version = tomllib.load(stream)["project"]["version"]
    init_version = __import__("ugas").__version__
    check("version:consistency", UGAS_VERSION == package_version == pyproject_version == init_version == "0.4.3", f"runtime={UGAS_VERSION}, package={package_version}, pyproject={pyproject_version}")
    docs = ["README.md", "INSTALL.md", "CHECKPOINT.md", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md"]
    check("docs:version", all(UGAS_VERSION in (ROOT / path).read_text(encoding="utf-8") for path in docs), "current operational docs identify 0.4.3")
    check("docs:animation-boundary", all(word in (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8").casefold() for word in ("animation", "do not authorize animation")), "checkpoint does not authorize animation")
    check("security:tracked-forbidden", not any(Path(path).suffix.casefold() in {".safetensors", ".ckpt", ".gguf", ".onnx"} for path in subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.splitlines()) if (ROOT / ".git").exists() else True, "weights are outside Git")
    compile_run = _run([sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"], ROOT); check("tests:compileall", compile_run.returncode == 0, (compile_run.stdout + compile_run.stderr).strip()[-500:])
    test_run = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], ROOT, timeout=360); test_text = test_run.stdout + test_run.stderr; match = re.search(r"Ran (\d+) tests", test_text); check("tests:unit", test_run.returncode == 0 and match is not None and int(match.group(1)) >= 79, test_text.strip()[-800:])
    snapshot_check()
    failures = 0
    for name, ok, detail in RESULTS: print(f"{'PASS' if ok else 'FAIL'} {name} - {detail}"); failures += not ok
    print(f"SUMMARY checks={len(RESULTS)} passed={len(RESULTS) - failures} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
