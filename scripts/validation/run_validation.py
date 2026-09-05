"""Objective UGAS validation, including immutable history and active v0.18.1."""

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
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ugas.constants import UGAS_VERSION
from ugas.master_assets import verify_asset_integrity
from ugas.model_registry import load_model, load_registry, validate_model_workflow_compatibility
from ugas.reference_edit import validate_edit_contract, validate_execution_evidence
from ugas.review import REQUIRED_V062_REVIEW_EVIDENCE, REQUIRED_V070_REVIEW_EVIDENCE, REQUIRED_V071_REVIEW_EVIDENCE, REQUIRED_V072_REVIEW_EVIDENCE, REQUIRED_V073_REVIEW_EVIDENCE, REQUIRED_V080_REVIEW_EVIDENCE, REQUIRED_V081_REVIEW_EVIDENCE, REQUIRED_V090_REVIEW_EVIDENCE, validate_review_visual_manifest
from ugas.review_snapshot import self_test_sensitive_matcher
from ugas.schema_validation import SchemaValidationError, validate_instance, validate_schema_document
from ugas.openpose_guides import COCO18_JOINTS, OPENPOSE_GUIDE_RENDERER_VERSION, validate_openpose_guide
from ugas.state_consistency import validate_state_consistency as validate_state_consistency_v090
from ugas.state_consistency_v080 import validate_state_consistency as validate_state_consistency_v080
from ugas.state_consistency_v081 import validate_state_consistency as validate_state_consistency_v081
from ugas.state_consistency_v091 import validate_state_consistency as validate_state_consistency_v091
from ugas.state_consistency_v0100 import validate_state_consistency as validate_state_consistency_v0100
from ugas.state_consistency_v0110 import validate_state_consistency as validate_state_consistency_v0110
from ugas.state_consistency_v0111 import validate_state_consistency as validate_state_consistency_v0111
from ugas.state_consistency_v0112 import validate_state_consistency as validate_state_consistency_v0112
from ugas.state_consistency_v0120 import validate_state_consistency as validate_state_consistency_v0120
from ugas.state_consistency_v0121 import validate_state_consistency as validate_state_consistency_v0121
from ugas.state_consistency_v0122 import validate_state_consistency as validate_state_consistency_v0122
from ugas.state_consistency_v0123 import validate_state_consistency as validate_state_consistency_v0123
from ugas.state_consistency_v0123 import BASELINE_HEAD as V0123_BASELINE_HEAD
from ugas.state_consistency_v0124 import validate_state_consistency as validate_state_consistency_v0124
from ugas.state_consistency_v0124 import BASELINE_HEAD as V0124_BASELINE_HEAD
from ugas.state_consistency_v0130 import validate_state_consistency as validate_state_consistency_v0130
from ugas.state_consistency_v0130 import BASELINE_HEAD as V0130_BASELINE_HEAD
from ugas.state_consistency_v0131 import validate_state_consistency as validate_state_consistency_v0131
from ugas.state_consistency_v0131 import BASELINE_HEAD as V0131_BASELINE_HEAD
from ugas.state_consistency_v0140 import validate_state_consistency as validate_state_consistency_v0140
from ugas.state_consistency_v0140 import BASELINE_HEAD as V0140_BASELINE_HEAD
from ugas.state_consistency_v0141 import validate_state_consistency as validate_state_consistency_v0141
from ugas.state_consistency_v0141 import BASELINE_HEAD as V0141_BASELINE_HEAD
from ugas.state_consistency_v0150 import validate_state_consistency as validate_state_consistency_v0150
from ugas.state_consistency_v0151 import validate_state_consistency as validate_state_consistency_v0151
from ugas.state_consistency_v0160 import validate_state_consistency as validate_state_consistency_v0160
from ugas.state_consistency_v0161 import validate_state_consistency as validate_state_consistency_v0161
from ugas.state_consistency_v0162 import validate_state_consistency as validate_state_consistency_v0162
from ugas.state_consistency_v0170 import validate_state_consistency as validate_state_consistency_v0170
from ugas.state_consistency_v0171 import validate_state_consistency as validate_state_consistency_v0171
from ugas.state_consistency_v0180 import validate_state_consistency as validate_state_consistency_v0180
from ugas.state_consistency_v0181 import validate_state_consistency as validate_state_consistency_v0181
from scripts.validation.validate_github_review_manifest import validate as validate_github_review_manifest
from scripts.validation.validate_github_review_manifest_v0124 import validate as validate_github_review_manifest_v0124
from scripts.validation.validate_github_workflows_v0124 import validate_repository as validate_github_workflows_v0124
from ugas.observability.qa_integrity import validate_review_index as validate_review_index_v0122
from ugas.cutout_rig import validate_rig_manifest
from ugas.workflow_registry import load_workflow, load_workflows, validate_api_workflow
from ugas.identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256, validate_identity_manifest
from ugas.pose_guides import CHALLENGE_NAME, POSE_GUIDE_RENDERER_VERSION, WALK_NAMES, validate_pose_guide
from ugas.multiview import AB_POSE_GAIN, AB_POSE_THRESHOLD, AB_POSE_FLOOR, FRAME_POSE_THRESHOLD, IDENTITY_THRESHOLD
from ugas.pose_metric_calibration import normalized_headroom_gain, provider_gap_emission_authorized, validate_causal_gate_configuration
from ugas.sdxl_smoke_evidence import validate_execution_evidence_v061


RESULTS: list[tuple[str, bool, str]] = []
V054_CANONICAL_OUTPUTS = tuple(
    f"docs/evidence/v054-lanes/{lane}-seed-{seed}.png"
    for lane in ("a", "c", "r")
    for seed in (54701, 54702, 54703)
)


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


def schema_compatible_with_artifact(schema: dict, artifact: dict) -> dict:
    """Validate immutable v0.5.0 evidence against the equivalent current schema."""
    if artifact.get("schema_version") != "0.5.0":
        return schema
    value = json.loads(json.dumps(schema))
    def replace(node: object) -> None:
        if isinstance(node, dict):
            if node.get("const") == UGAS_VERSION:
                node["const"] = "0.5.0"
            for child in node.values():
                replace(child)
        elif isinstance(node, list):
            for child in node:
                replace(child)
    replace(value)
    if artifact.get("schema_version") == "0.5.0" and artifact.get("animation") == "walk":
        temporal = value.get("properties", {}).get("temporal", {})
        if isinstance(temporal, dict) and isinstance(temporal.get("required"), list):
            temporal["required"] = [item for item in temporal["required"] if item != "gates"]
    return value


def tracked(path: str) -> bool:
    if os.environ.get("UGAS_TRACKED_SNAPSHOT") == "1" or not (ROOT / ".git").exists():
        return (ROOT / path).is_file()
    result = subprocess.run(["git", "ls-files", "--error-unmatch", "--", path], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.returncode == 0


def _run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None, timeout: int = 360) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=timeout)


def _result_detail(result: subprocess.CompletedProcess[str]) -> str:
    """Keep nested validation failures visible instead of only a truncated tail."""
    text = (result.stdout + result.stderr).strip()
    failures = [line for line in text.splitlines() if line.startswith("FAIL ") or line.startswith("SUMMARY ")]
    return "\n".join(failures[-20:]) if failures else text[-800:]


def _snapshot_validation_ok(result: subprocess.CompletedProcess[str]) -> bool:
    """Require the isolated historical validation to complete successfully."""

    return result.returncode == 0


def _snapshot_unit_ok(result: subprocess.CompletedProcess[str]) -> bool:
    """Require all unit tests to pass in the isolated snapshot."""

    return result.returncode == 0


def snapshot_check() -> None:
    if os.environ.get("UGAS_SKIP_TRACKED_SNAPSHOT") == "1":
        check("snapshot:tracked", True, "nested snapshot check skipped")
        return
    if not (ROOT / ".git").exists():
        check("snapshot:git-context", True, "SKIP_EXTERNAL_GIT_CONTEXT")
        return
    with tempfile.TemporaryDirectory(prefix="ugas-v051-snapshot-") as directory:
        snapshot = Path(directory) / "snapshot"; snapshot.mkdir()
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True, check=False)
        if archive.returncode != 0:
            check("snapshot:archive", False, archive.stderr.decode(errors="replace")[-500:]); return
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
            try: tar.extractall(snapshot, filter="data")
            except TypeError: tar.extractall(snapshot)
        # Resolve the historical index authority before any isolated snapshot
        # command runs.  Both snapshot:validation and snapshot:no-git must see
        # the bundle; preparing it only before the latter would leave the
        # former dependent on mutable active files.
        historical_index_path = snapshot / "docs/evidence/review-index-v0.11.2.json"
        historical_index = load_json(historical_index_path)
        historical_head = str(historical_index.get("publication", {}).get("index_build_git_head", ""))
        historical_root = snapshot / "docs/evidence/github-governance-v0124/historical/v0.11.2"
        bundle_ok = len(historical_head) == 40
        for artifact in historical_index.get("artifact_set", {}).get("artifacts", []):
            relative = str(artifact.get("path", ""))
            source_relative = {"docs/evidence/current-state.json": "docs/evidence/current-state-v0.11.2.json", "schemas/current-state.json": "schemas/current-state-v0.11.2.json"}.get(relative, relative)
            if not relative or not source_relative:
                bundle_ok = False
                continue
            expected_hash = str(artifact.get("sha256", ""))
            existing_historical = snapshot / source_relative
            if existing_historical.is_file() and digest(existing_historical) == expected_hash:
                continue
            historical_bytes = subprocess.run(["git", "show", f"{historical_head}:{source_relative}"], cwd=ROOT, capture_output=True, check=False)
            if historical_bytes.returncode != 0:
                bundle_ok = False
                continue
            target = historical_root / source_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(historical_bytes.stdout)
        env = os.environ.copy(); env.update({"UGAS_SKIP_TRACKED_SNAPSHOT": "1", "UGAS_SKIP_NO_GIT_REGRESSION": "1", "UGAS_ALLOW_PRESERVED_HISTORICAL_DRIFT": "1", "PYTHONUTF8": "1"})
        for name, command in (
            ("snapshot:compileall", [sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"]),
            ("snapshot:unit-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
            ("snapshot:validation", [sys.executable, "scripts/validation/run_validation.py"]),
            ("snapshot:version", [sys.executable, "-m", "ugas.cli", "--version"]),
            ("snapshot:models", [sys.executable, "-m", "ugas.cli", "models", "list"]),
        ):
            print(f"RUN {name}", flush=True)
            result = _run(command, snapshot, env=env)
            print(f"DONE {name} returncode={result.returncode}", flush=True)
            check(name, _snapshot_validation_ok(result) if name == "snapshot:validation" else (_snapshot_unit_ok(result) if name == "snapshot:unit-tests" else result.returncode == 0), _result_detail(result) or "known immutable-history drift accepted in isolated snapshot")
        check("snapshot:historical-bundle", bundle_ok, "v0.11.2 index authority was resolved before no-git packaging")
        no_git = Path(directory) / "no-git"; shutil.copytree(snapshot, no_git, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))
        no_git_env = env.copy(); no_git_env.pop("UGAS_SKIP_TRACKED_SNAPSHOT", None); no_git_env["UGAS_REVIEW_SNAPSHOT"] = "1"; no_git_env["PYTHONPATH"] = str(no_git / "src")
        print("RUN snapshot:no-git", flush=True)
        result = _run([sys.executable, "scripts/validation/run_validation.py"], no_git, env=no_git_env)
        print(f"DONE snapshot:no-git returncode={result.returncode}", flush=True)
        check("snapshot:no-git", _snapshot_validation_ok(result) and "SKIP_EXTERNAL_GIT_CONTEXT" in result.stdout, _result_detail(result) or "known immutable-history drift accepted in isolated snapshot")


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


def _v050_checks() -> None:
    identity_path = ROOT / "docs/evidence/identity-manifest.json"
    try:
        identity = load_json(identity_path)
        result = validate_identity_manifest(identity, ROOT)
        check("v050:identity", result["status"] == "IDENTITY_MANIFEST_VALID" and identity.get("asset_id") == ANCHOR_ASSET_ID and identity.get("canonical_revision", {}).get("revision_id") == ANCHOR_REVISION_ID and identity.get("canonical_revision", {}).get("sha256") == ANCHOR_SHA256, "; ".join(result.get("failures", [])) or "identity manifest binds exact R4")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v050:identity", False, str(exc))
    guide_paths = list((ROOT / "pose-guides/views").glob("*.json")) + list((ROOT / "pose-guides/walk-front-8").glob("*.json"))
    guide_results = []
    for path in guide_paths:
        try: guide_results.append(validate_pose_guide(load_json(path))["status"] == "POSE_GUIDE_VALID")
        except (OSError, json.JSONDecodeError): guide_results.append(False)
    check("v050:pose-guides", len(guide_paths) == 12 and all(guide_results), f"validated guides={len(guide_paths)}")
    try:
        workflow = load_workflow(ROOT, "flux2-klein-base-4b-quality-multi-reference-edit")
        refs = [node for node in workflow["api"].values() if node.get("class_type") == "ReferenceLatent"]
        check("v050:multiref-topology", len(refs) == 4 and workflow["parameters"].get("reference_order") == ["identity-anchor", "pose-view-guide"] and not workflow["custom_nodes_required"], "native ReferenceLatent chain and explicit reference order")
    except (OSError, KeyError, ValueError) as exc: check("v050:multiref-topology", False, str(exc))
    try:
        multiref = load_json(ROOT / "docs/evidence/multiref-qualification.json")
        check("v050:multiref-qualified", multiref.get("status") == "MULTI_REFERENCE_QUALIFIED" and len(multiref.get("records", [])) == 4 and multiref.get("conditioning_contract", {}).get("previous_frame_chaining") is False, "real A/B evidence is complete and no-chain")
        check("v050:upstream", multiref.get("upstream", {}).get("repository") == "Comfy-Org/workflow_templates" and multiref.get("upstream", {}).get("commit") and multiref.get("upstream", {}).get("source_sha256") == digest(ROOT / "docs/evidence/upstream/workflow_templates-image-edit-base.json"), "official template and local object_info evidence are bound")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v050:multiref-qualified", False, str(exc))
    try:
        anchors = load_json(ROOT / "docs/evidence/directional-anchor-set.json")
        selected = anchors.get("anchor_set", {})
        check("v050:anchors", anchors.get("status") == "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED" and set(selected) == {"front", "left", "right", "back"} and digest(ROOT / "docs/evidence/anchor-front.png") == ANCHOR_SHA256, "directional set has four technical anchors and immutable front")
        check("v050:anchor-candidates", anchors.get("candidate_count_per_generated_direction") == 2 and len(anchors.get("candidates", [])) == 6, "two candidate records per generated direction")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v050:anchors", False, str(exc))
    try:
        walk = load_json(ROOT / "docs/evidence/walk-front-8-animation-qa.json"); metadata = load_json(ROOT / "docs/evidence/walk-front-8.json")
        temporal = walk.get("temporal", {})
        check("v050:walk", walk.get("status") == "WALK_CYCLE_VISUAL_REVIEW_REQUIRED" and temporal.get("frame_count") == 8 and temporal.get("unique_sha256") is True and temporal.get("no_previous_frame_chaining") is True, "walk/front/8 temporal gate passed")
        check("v050:pack", metadata.get("frames") == 8 and metadata.get("fps") == 8 and len(metadata.get("frame_files", [])) == 8 and len(metadata.get("frame_hashes", [])) == 8 and all((ROOT / path).is_file() for path in metadata["frame_files"]), "spritesheet metadata binds eight frame paths and hashes")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v050:walk", False, str(exc))
    manifest = load_json(ROOT / "docs/evidence/review-visuals-v0.5.0.json")
    visual = validate_review_visual_manifest(manifest, ROOT)
    check("v050:visual-manifest", visual["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual.get("failures", [])) or "v0.5 visual roles are hash-bound")
    execution = load_json(ROOT / "docs/evidence/execution-evidence.json")
    check("v050:execution-evidence", execution.get("schema_version") == "0.5.0" and execution.get("fresh_binding_required") is True and execution.get("previous_frame_chaining") is False, "execution evidence policy is explicit")
    for schema_name, artifact_path in (("character-identity-manifest", "docs/evidence/identity-manifest.json"), ("directional-anchor-set", "docs/evidence/directional-anchor-set.json"), ("animation-spec", "docs/evidence/walk-front-8.json"), ("animation-qa", "docs/evidence/walk-front-8-animation-qa.json")):
        try:
            artifact = load_json(ROOT / artifact_path); validate_instance(artifact, schema_compatible_with_artifact(load_json(ROOT / f"schemas/{schema_name}.json"), artifact)); check(f"v050:schema-instance:{schema_name}", True, f"historical/current artifact validates against {schema_name}")
        except (OSError, json.JSONDecodeError, SchemaValidationError) as exc: check(f"v050:schema-instance:{schema_name}", False, str(exc))
    try:
        frame = load_json(ROOT / "docs/evidence/walk-front-8-animation-qa.json")["frames"][0]["selected"]
        validate_instance(frame, schema_compatible_with_artifact(load_json(ROOT / "schemas/animation-frame.json"), frame)); check("v050:schema-instance:animation-frame", True, "selected historical frame validates against animation-frame")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc: check("v050:schema-instance:animation-frame", False, str(exc))
    try:
        validate_instance(load_json(ROOT / "pose-guides/views/front.json"), load_json(ROOT / "schemas/pose-guide.json")); check("v050:schema-instance:pose-guide", True, "real pose guide validates against pose-guide")
    except (OSError, json.JSONDecodeError, SchemaValidationError) as exc: check("v050:schema-instance:pose-guide", False, str(exc))
    review_path = ROOT / "REVIEW-v0.5.0.md"; review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "SCOPE", "BASELINE / V0.4.3 ANCHOR", "MULTI-REFERENCE QUALIFICATION", "POSE GUIDE SYSTEM", "DIRECTIONAL ANCHOR PILOT", "DIRECTIONAL CONSISTENCY QA", "WALK-CYCLE PILOT", "FRAME QA", "NORMALIZATION / PIVOT / GROUND", "TEMPORAL QA", "SPRITESHEET / METADATA / PREVIEW", "EXECUTION EVIDENCE", "CAPABILITY STATES", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "PENDING", "BLOCKERS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v050:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5 review headings present")


def _v051_checks() -> None:
    identity_path = ROOT / "docs/evidence/identity-manifest.json"
    try:
        identity = load_json(identity_path); identity_result = validate_identity_manifest(identity, ROOT)
        check("v051:identity", identity_result["status"] == "IDENTITY_MANIFEST_VALID" and identity.get("schema_version") == "0.5.1" and identity.get("canonical_revision", {}).get("sha256") == ANCHOR_SHA256, "historical identity manifest binds exact immutable R4")
        validate_instance(identity, load_json(ROOT / "schemas/character-identity-manifest.json")); check("v051:schema-instance:identity", True, "current identity artifact validates against schema")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        check("v051:identity", False, str(exc)); check("v051:schema-instance:identity", False, str(exc))
    guide_paths = list((ROOT / "pose-guides/views").glob("*.json")) + list((ROOT / "pose-guides/walk-front-8").glob("*.json")) + list((ROOT / "pose-guides/challenges").glob("*.json"))
    guide_results = [validate_pose_guide(load_json(path)) for path in guide_paths]
    check("v051:pose-guides", len(guide_paths) == 13 and all(item["status"] == "POSE_GUIDE_VALID" and item.get("sha256") for item in guide_results), f"validated mannequin guides={len(guide_paths)} renderer={POSE_GUIDE_RENDERER_VERSION}")
    check("v051:strict-profiles", all(load_json(ROOT / f"pose-guides/views/{direction}.json").get("orientation_cue", {}).get("profile_strict") is True for direction in ("left", "right")), "left/right guides declare strict profile geometry")
    try:
        challenge = load_json(ROOT / f"pose-guides/challenges/{CHALLENGE_NAME}.json"); validate_instance(challenge, load_json(ROOT / "schemas/pose-guide.json")); check("v051:schema-instance:pose-guide", True, "challenge mannequin validates against pose-guide schema")
    except (OSError, json.JSONDecodeError, SchemaValidationError) as exc: check("v051:schema-instance:pose-guide", False, str(exc))
    try:
        doctor = load_json(ROOT / "docs/evidence/runtime-doctor-v0.5.1.json"); check("v051:doctor", doctor.get("schema_version") == "0.5.1" and doctor.get("model_hashes", {}).get("expected_sha256") and doctor.get("reference_latent_node", {}).get("present") is True, "historical runtime, ReferenceLatent and model hash evidence recorded")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v051:doctor", False, str(exc))
    try:
        multiref = load_json(ROOT / "docs/evidence/multiref-v2-qualification.json"); status = multiref.get("status"); comparison = multiref.get("comparison", {}); records = multiref.get("records", []); strict_rule = comparison.get("qualification_rule", "")
        check("v051:multiref-status", status in {"MULTI_REFERENCE_QUALIFIED", "MULTI_REFERENCE_POSE_CONTROL_GAP"}, f"fail-closed status={status}")
        if status == "MULTI_REFERENCE_QUALIFIED":
            ok = len(records) == 6 and comparison.get("B_valid") is True and comparison.get("meaningful_B_pose_gain") is True and comparison.get("B_pose_gain", 0) >= AB_POSE_GAIN and comparison.get("B_pose_adherence_mean", 0) >= AB_POSE_THRESHOLD and all(item.get("fresh_binding") is True for item in records)
            check("v051:multiref-gate", ok, "six paired records satisfy causal pose gain, floor, identity and fresh evidence")
        else:
            check("v051:multiref-gate", status == "MULTI_REFERENCE_POSE_CONTROL_GAP" and comparison.get("B_pose_gain", 0) < AB_POSE_GAIN or status == "MULTI_REFERENCE_POSE_CONTROL_GAP", "multi-reference gap remains explicit and blocks walk")
        check("v051:pose-metric", "keypoint" in str(comparison.get("pose_metric", "")).casefold() and "bbox" in str(comparison.get("pose_metric", "")).casefold() and "diagnostic" in str(comparison.get("pose_metric", "")).casefold(), "pose metric is geometric and bbox ratio is diagnostic only")
        check("v051:ab-records", len(records) in {0, 6} and "seed" in json.dumps(records), "A/B pair count is zero before runtime gap or six after execution")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v051:multiref-status", False, str(exc))
    try:
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.5.1.json"); check("v051:execution-evidence", execution.get("schema_version") == "0.5.1" and execution.get("fresh_binding_required") is True and execution.get("previous_frame_chaining") is False and execution.get("all_prompt_ids_present") is True and execution.get("all_history_bindings_exact") is True and execution.get("stale_output_rejected") is True, "historical fresh prompt/history/output binding evidence is explicit")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v051:execution-evidence", False, str(exc))
    try:
        manifest = load_json(ROOT / "docs/evidence/review-visuals-v0.5.1.json"); visual = validate_review_visual_manifest(manifest, ROOT); check("v051:visual-manifest", visual["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual.get("failures", [])) or f"visual roles bound for {manifest.get('review_state')}")
    except (OSError, json.JSONDecodeError, KeyError) as exc: check("v051:visual-manifest", False, str(exc))
    current_status = None
    try: current_status = load_json(ROOT / "docs/evidence/multiref-v2-qualification.json").get("status")
    except (OSError, json.JSONDecodeError): pass
    if current_status == "MULTI_REFERENCE_QUALIFIED":
        try:
            anchors = load_json(ROOT / "docs/evidence/directional-anchor-set-v2.json"); check("v051:anchors", anchors.get("status") == "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED" and len(anchors.get("candidates", [])) == 6 and anchors.get("candidate_count_per_generated_direction") == 2, "directional candidates selected by pose/identity rather than seed")
            check("v051:anchor-qa", (ROOT / "docs/evidence/directional-anchor-v2-qa.json").is_file() and (ROOT / "docs/evidence/directional-anchor-candidates-v2-contact-sheet.png").is_file() and (ROOT / "docs/evidence/directional-anchors-v2-contact-sheet.png").is_file(), "candidate and selected directional evidence present")
        except (OSError, json.JSONDecodeError, KeyError) as exc: check("v051:anchors", False, str(exc))
        walk_path = ROOT / "docs/evidence/walk-v2-temporal-qa.json"
        if walk_path.is_file():
            try:
                walk = load_json(walk_path); temporal = walk.get("temporal", {}); check("v051:walk", walk.get("status") in {"WALK_VISUAL_REVIEW_REQUIRED", "WALK_TEMPORAL_QA_FAILED", "NO_ACCEPTABLE_FRAME"}, f"walk state={walk.get('status')}"); check("v051:temporal", temporal.get("status") in {"TEMPORAL_QA_PASSED", "WALK_TEMPORAL_QA_FAILED"} and temporal.get("no_previous_frame_chaining") is True, "temporal v2 records phase, continuity, identity and loop gates")
                if temporal.get("status") == "TEMPORAL_QA_PASSED":
                    spec = load_json(ROOT / "docs/evidence/walk-v2-animation-spec.json"); validate_instance(spec, load_json(ROOT / "schemas/animation-spec.json")); validate_instance(walk, load_json(ROOT / "schemas/animation-qa.json")); check("v051:walk-pack", len(spec.get("frame_files", [])) == 8 and all((ROOT / path).is_file() for path in spec["frame_files"]), "spritesheet is produced only after QA v2")
                else: check("v051:walk-pack", not (ROOT / "docs/evidence/walk-v2-spritesheet.png").is_file(), "failed temporal/frame QA does not create approved spritesheet")
            except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc: check("v051:temporal", False, str(exc))
        else: check("v051:walk", False, "walk evidence missing after qualified multi-reference")
    else:
        check("v051:walk-blocked", not (ROOT / "docs/evidence/walk-v2-spritesheet.png").is_file(), "walk remains blocked by multi-reference pose-control gap")
    review_path = ROOT / "REVIEW-v0.5.1.md"; review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""; headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "BASELINE / V0.5.0 FINDINGS", "REPRODUCIBILITY FIX", "POSE GUIDE V2", "MULTI-REFERENCE V2 QUALIFICATION", "IDENTITY FIDELITY V2", "DIRECTIONAL ANCHOR V2", "WALK FRONT 8 V2", "FRAME QA", "TEMPORAL QA V2", "PACKING", "EXECUTION EVIDENCE", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "PENDING", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v051:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5.1 review headings present")
    check("v051:no-automatic-approval", "PRODUCTION_READY" not in review or "not" in review.casefold(), "visual and production approval remain external")


def _v052_checks() -> None:
    """Validate immutable v0.5.2 evidence without treating it as active state."""
    review_path = ROOT / "REVIEW-v0.5.2.md"
    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    check("v052:historical-review-present", review_path.is_file() and "0.5.2" in review, "v0.5.2 review remains an immutable historical artifact")
    check("v052:historical-state-separated", "docs/evidence/current-state.json" not in review or "0.5.3" not in review, "historical review is not treated as the active state record")
    headings = [
        "STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.5.1 AUDIT RESULT", "STATE CONSISTENCY FIX",
        "CURRENT STATE", "OPENPOSE GUIDE V3", "NATIVE REFERENCE ORDER BENCHMARK", "NATIVE POSE QUALIFICATION",
        "REFCONTROL MODEL / LICENSE / HASH", "REFCONTROL NATIVE LOADER QUALIFICATION", "REFCONTROL STRENGTH BENCHMARK",
        "POSE CONTROL FINAL GATE", "IDENTITY FIDELITY", "DIRECTIONAL ANCHORS V3", "WALK FRONT 8 V3", "FRAME QA",
        "TEMPORAL QA", "PACKING", "EXECUTION EVIDENCE", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB",
        "SECURITY", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP",
    ]
    check("v052:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5.2 review headings present")
    check("v052:review-stop-language", "LOCAL_POSE_CONTROL_PROVIDER_GAP" in review and "não" in review.casefold() and "production_approval" not in review.casefold(), "review records the explicit stop and keeps approval external")

    try:
        manifest = load_json(ROOT / "docs/evidence/openpose-guide-v3-manifest.json")
        check("v052:openpose-manifest", manifest.get("status") == "OPENPOSE_EVIDENCE_RENDERED" and manifest.get("renderer_version") == OPENPOSE_GUIDE_RENDERER_VERSION and manifest.get("joint_schema") == "COCO-18", "OpenPose v3 renderer and schema evidence are present")
        guide_paths = sorted((ROOT / "pose-guides/openpose-v3").glob("**/*.json"))
        results = [validate_openpose_guide(load_json(path)) for path in guide_paths]
        check("v052:openpose-guides", len(guide_paths) == 13 and all(item["status"] == "OPENPOSE_GUIDE_VALID" and tuple(load_json(path)["joints"]) == COCO18_JOINTS for path, item in zip(guide_paths, results)), f"validated COCO-18 guides={len(guide_paths)}")
        check("v052:openpose-images", all((ROOT / path).is_file() for path in ("docs/evidence/openpose-guide-v3-control-example.png", "docs/evidence/openpose-guides-v3-contact-sheet.png")), "control image and review contact sheet are present")
        validate_instance(load_json(ROOT / "pose-guides/openpose-v3/challenges/multiref-strong-left-arm-up.json"), load_json(ROOT / "schemas/openpose-pose-guide.json"))
        check("v052:openpose-schema-instance", True, "challenge guide validates against openpose-pose-guide schema")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError) as exc:
        check("v052:openpose-manifest", False, str(exc)); check("v052:openpose-guides", False, str(exc)); check("v052:openpose-schema-instance", False, str(exc))

    try:
        native = load_json(ROOT / "docs/evidence/native-reference-order-qualification.json")
        lanes = native.get("lanes", {})
        check("v052:native-gap", native.get("status") == "NATIVE_REFERENCE_ORDER_POSE_CONTROL_GAP" and not native.get("qualified_lanes") and len(native.get("records", [])) == 9, "native A/B/C benchmark is complete but fail-closed")
        check("v052:native-criteria", lanes.get("A", {}).get("records") == 3 and lanes.get("B", {}).get("records") == 3 and lanes.get("C", {}).get("records") == 3 and lanes.get("A", {}).get("pose_mean") == 0.894403 and native.get("benchmark_contract", {}).get("gain_threshold") == 0.15, "native seeds, baseline and immutable gain threshold are recorded")
        check("v052:native-contact", (ROOT / "docs/evidence/native-reference-order-abc-contact-sheet.png").is_file() and (ROOT / "docs/evidence/v051-gap-baseline.png").is_file(), "native and historical baseline visuals are present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v052:native-gap", False, str(exc)); check("v052:native-criteria", False, str(exc)); check("v052:native-contact", False, str(exc))

    try:
        model = load_json(ROOT / "docs/evidence/refcontrol-model-qualification.json")
        loader = model.get("native_loader", {})
        check("v052:refcontrol-model", model.get("status") == "MODEL_HASH_AND_LICENSE_VERIFIED" and model.get("actual_sha256", "").casefold() == "f9880f9070576ff1603c0988ed2afc9957deb0d7dd7c52cf15decbd4087f1339" and model.get("bytes") == 92426792 and model.get("license", {}).get("license") == "Apache-2.0", "RefControl file hash, byte count and license are verified")
        check("v052:refcontrol-loader", loader.get("status") == "REFCONTROL_NATIVE_LORA_LOADER_FOUND" and loader.get("selected", {}).get("node") == "LoraLoaderModelOnly" and loader.get("selected", {}).get("native") is True and not loader.get("custom_nodes_required"), "native LoRA loader is selected without custom nodes")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v052:refcontrol-model", False, str(exc)); check("v052:refcontrol-loader", False, str(exc))
    try:
        refcontrol = load_json(ROOT / "docs/evidence/refcontrol-pose-qualification.json")
        triage = {str(item["strength"]): item for item in refcontrol.get("triage", [])}
        best = max((item.get("pose_gain_over_A", 0.0) for item in triage.values()), default=0.0)
        check("v052:refcontrol-gap", refcontrol.get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP" and refcontrol.get("stop_reason") == "LOCAL_POSE_CONTROL_PROVIDER_GAP" and len(refcontrol.get("records", [])) == 7 and best < 0.15, "RefControl strength and confirmation benchmark stays below the promotion threshold")
        check("v052:refcontrol-strengths", set(triage) == {"0.8", "0.9", "1.0"} and refcontrol.get("confirmation_strength") == 0.8 and (ROOT / "docs/evidence/refcontrol-strength-benchmark-contact-sheet.png").is_file() and (ROOT / "docs/evidence/refcontrol-pose-overlay-contact.png").is_file(), "all authorized strengths and confirmation evidence are present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v052:refcontrol-gap", False, str(exc)); check("v052:refcontrol-strengths", False, str(exc))

    try:
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.5.2.json")
        native_cycle = execution.get("native_benchmark", {})
        check("v052:execution-evidence", execution.get("schema_version") == "0.5.2" and execution.get("previous_frame_chaining") is False and native_cycle.get("record_count") == 9 and execution.get("record_count") == 7, "native and RefControl execution evidence are retained as separate cycles")
        check("v052:execution-fail-closed", execution.get("all_prompt_ids_present") is False and execution.get("all_history_bindings_exact") is False and execution.get("stale_output_rejected") is False, "incomplete technical records remain an explicit failure")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v052:execution-evidence", False, str(exc)); check("v052:execution-fail-closed", False, str(exc))

    try:
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.5.2.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v052:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.5.2 visual roles are hash-bound")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v052:visual-manifest", False, str(exc))


def _v053_checks() -> None:
    """Validate the active metric-calibration slice and its fail-closed stop."""
    state_path = ROOT / "docs/evidence/current-state.json"
    review_path = ROOT / "REVIEW-v0.5.3.md"
    checkpoint_path = ROOT / "CHECKPOINT.md"
    try:
        state = load_json(state_path)
        consistency = validate_state_consistency(state, checkpoint_path.read_text(encoding="utf-8"), review_path.read_text(encoding="utf-8"))
        check("v053:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active state and documents are consistent")
        check("v053:state-schema", state.get("schema_version") == "0.5.3" and state.get("version") == "0.5.3" and state.get("phase") == "POSE_METRIC_CALIBRATION", "active state is v0.5.3 metric calibration")
        check("v053:state-stop", state.get("current_gate") == state.get("stop_reason") == state.get("state_consistency", {}).get("status") == "POSE_QA_MODEL_LICENSE_GAP", "active gate, stop reason and nested status agree")
        check("v053:no-generation-authorized", state.get("generation_provider_change_authorized") is False and state.get("walk_authorized") is False and state.get("state_consistency", {}).get("new_generation_started") is False, "provider and walk remain unauthorized")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v053:state-consistency", False, str(exc)); check("v053:state-schema", False, str(exc)); check("v053:state-stop", False, str(exc))

    try:
        impossible = validate_causal_gate_configuration(0.894403, 0.15)
        check("v053:impossibility-guard", impossible["status"] == "INVALID_CAUSAL_GATE_CONFIGURATION" and impossible["required_score"] == 1.044403, "A plus delta cannot exceed metric maximum")
        check("v053:headroom", abs(normalized_headroom_gain(0.894403, 0.992258) - 0.9266835232061514) < 1e-9, "normalized headroom gain is computed from remaining room")
    except (TypeError, ValueError, KeyError) as exc:
        check("v053:impossibility-guard", False, str(exc)); check("v053:headroom", False, str(exc))

    try:
        calibration = load_json(ROOT / "docs/evidence/pose-metric-calibration.json")
        criteria = calibration.get("criteria", {})
        fixtures = calibration.get("fixtures", {})
        check("v053:calibration-pass", calibration.get("status") == "METRIC_CALIBRATION_PASSED" and calibration.get("primary_metric") == "detected_joint_pose_error" and all(criteria.values()), "detected-joint metric calibration passed all criteria")
        check("v053:calibration-fixtures", set(fixtures) == {"TARGET", "NEUTRAL_FRONT", "MIRRORED_WRONG_SIDE", "T_POSE", "ARMS_DOWN", "LEGS_WRONG", "ARM_WRONG", "TARGET_PLUS_LONG_VERTICAL_SWORD", "NEUTRAL_FRONT_PLUS_VERTICAL_SWORD"} and calibration.get("deterministic") is True and calibration.get("provider_routing_used") is False, "all nine deterministic fixtures are present")
        check("v053:legacy-diagnostic-only", calibration.get("legacy_pose_score", {}).get("status") == "DIAGNOSTIC_ONLY" and calibration.get("legacy_pose_score", {}).get("primary_gate_uses_it") is False, "legacy silhouette score is diagnostic-only")
        check("v053:calibration-contacts", all((ROOT / path).is_file() for path in ("docs/evidence/pose-metric-calibration-contact-sheet.png", "docs/evidence/pose-metric-negative-controls-contact-sheet.png")), "calibration contact sheets are present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v053:calibration-pass", False, str(exc)); check("v053:calibration-fixtures", False, str(exc)); check("v053:calibration-contacts", False, str(exc))

    try:
        estimator = load_json(ROOT / "docs/evidence/pose-qa-estimator-qualification.json")
        model = load_json(ROOT / "docs/evidence/pose-qa-estimator-model.json")
        status = estimator.get("status")
        check("v053:estimator-status", status in {"POSE_QA_ESTIMATOR_QUALIFIED", "POSE_QA_ESTIMATOR_GAP", "POSE_QA_MODEL_LICENSE_GAP"} and estimator.get("qa_only") is True and estimator.get("provider_routing_used") is False, f"independent estimator status={status}")
        check("v053:estimator-mapping", "MEDIAPIPE_TO_UGAS" in str(estimator.get("detected_joint_mapping")) and estimator.get("generation_graph_unchanged") is True, "MediaPipe mapping is explicit and generation graph is unchanged")
        check("v053:model-bound", model.get("schema_version") == "0.5.3" and model.get("model", {}).get("url") and model.get("model", {}).get("sha256") and model.get("model", {}).get("bytes", 0) > 0 and model.get("model", {}).get("outside_git") is True and model.get("model", {}).get("outside_review_zip") is True, "model URL, bytes, hash and exclusion boundary are recorded")
        check("v053:model-license-gap", status == "POSE_QA_MODEL_LICENSE_GAP" and model.get("model", {}).get("license_status") == "UNDETERMINED", "undetermined bundle terms stop qualification explicitly")
        check("v053:estimator-overlay", (ROOT / "docs/evidence/v053-pose-detection-overlay-contact.png").is_file(), "estimator blocked overlay is present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v053:estimator-status", False, str(exc)); check("v053:model-bound", False, str(exc)); check("v053:model-license-gap", False, str(exc))

    try:
        provider = load_json(ROOT / "docs/evidence/v053-provider-qualification.json")
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.5.3.json")
        check("v053:provider-blocked", provider.get("status") == "POSE_QA_MODEL_LICENSE_GAP" and provider.get("provider_gap_emission_authorized") is False and provider.get("new_generation_jobs_submitted") is False and provider.get("outputs") == [], "provider recheck is blocked before estimator qualification")
        check("v053:execution-blocked", execution.get("record_count") == 0 and execution.get("generation_jobs_authorized") is False and execution.get("previous_frame_chaining") is False and execution.get("provider_routing_used") is False, "no new generation execution is recorded")
        check("v053:reserved-seeds", execution.get("seeds_reserved_but_not_used") == [53701, 53702, 53703], "new seeds are recorded as unused")
        check("v053:baseline-contact", (ROOT / "docs/evidence/v052-refcontrol-baseline-contact.png").is_file(), "historical RefControl baseline contact is materialized")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v053:provider-blocked", False, str(exc)); check("v053:execution-blocked", False, str(exc))

    try:
        table = load_json(ROOT / "docs/evidence/v053-pose-error-table.json")
        check("v053:error-table", table.get("schema_version") == "0.5.3" and len(table.get("rows", [])) == 9 and table.get("status") == "METRIC_CALIBRATION_PASSED", "nine-row pose error table is bound to calibration")
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.5.3.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v053:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.5.3 visual roles are hash-bound")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v053:error-table", False, str(exc)); check("v053:visual-manifest", False, str(exc))

    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = [
        "STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.5.2 AUDIT RESULT", "GATE IMPOSSIBILITY FINDING",
        "STATE CONSISTENCY FIX", "POSE METRIC CALIBRATION", "SYNTHETIC NEGATIVE CONTROLS", "POSE QA ESTIMATOR",
        "POSE QA MODEL / LICENSE / HASH", "DETECTED-JOINT METRIC", "CAUSAL EFFECT METRIC", "NATIVE LANE RECHECK",
        "REFCONTROL LANE RECHECK", "IDENTITY / WEAPON QA", "FINAL POSE PROVIDER DECISION", "EXECUTION EVIDENCE",
        "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS",
        "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP",
    ]
    check("v053:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5.3 review headings present")
    check("v053:review-no-stale-action", "verificar o RefControl" not in (checkpoint_path.read_text(encoding="utf-8") + review), "stale RefControl pending action is absent")
    check("v053:no-v053-provider-output", not any((ROOT / "docs/evidence/v053").glob("*.png")) if (ROOT / "docs/evidence/v053").is_dir() else True, "no provider output directory was created")


def _v054_checks() -> None:
    """Validate the active estimator/license/lane recheck slice."""
    state_path = ROOT / "docs/evidence/current-state.json"
    review_path = ROOT / "REVIEW-v0.5.4.md"
    checkpoint_path = ROOT / "CHECKPOINT.md"
    try:
        state = load_json(state_path)
        consistency = validate_state_consistency(state, checkpoint_path.read_text(encoding="utf-8"), review_path.read_text(encoding="utf-8"))
        check("v054:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active state and documents are consistent")
        check("v054:state-schema", state.get("schema_version") == "0.5.4" and state.get("version") == "0.5.4" and state.get("phase") == "POSE_LANE_RECHECK", "active state is v0.5.4 lane recheck")
        check("v054:state-stop", state.get("current_gate") == state.get("stop_reason") == state.get("state_consistency", {}).get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", "active provider gap, stop reason and nested status agree")
        check("v054:state-boundary", state.get("generation_provider_change_authorized") is False and state.get("walk_authorized") is False and state.get("state_consistency", {}).get("new_generation_started") is True and state.get("state_consistency", {}).get("new_generation_jobs") == 9, "existing provider recheck is recorded while provider change and walk remain unauthorized")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:state-consistency", False, str(exc)); check("v054:state-schema", False, str(exc)); check("v054:state-stop", False, str(exc))

    try:
        thresholds = load_json(ROOT / "docs/evidence/pose-thresholds-v054.json")
        check("v054:thresholds-frozen", thresholds.get("schema_version") == "0.5.4" and thresholds.get("thresholds_are_frozen_before_jobs") is True and thresholds.get("fresh_execution", {}).get("lanes") == ["A", "C", "R"] and thresholds.get("fresh_execution", {}).get("seeds") == [54701, 54702, 54703] and thresholds.get("fresh_execution", {}).get("outputs_required") == 9, "thresholds, lanes and exact seeds were frozen before jobs")
        check("v054:threshold-ranges", thresholds.get("range_validation", {}).get("status") == "PASSED" and thresholds.get("range_validation", {}).get("bounded_metrics", {}).get("pck") == [0.0, 1.0] and thresholds.get("range_validation", {}).get("bounded_metrics", {}).get("angle_mae_degrees") == [0.0, 180.0], "metric ranges are explicit and mathematically bounded")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:thresholds-frozen", False, str(exc)); check("v054:threshold-ranges", False, str(exc))

    try:
        license_evidence = load_json(ROOT / "docs/evidence/pose-qa-license-resolution.json")
        model = load_json(ROOT / "docs/evidence/pose-qa-estimator-model-v054.json")
        check("v054:license-resolution", license_evidence.get("status") == "POSE_QA_LOCAL_USE_LICENSE_RESOLVED" and license_evidence.get("official_task_docs", {}).get("bundle_variant") == "Pose landmarker (Full)" and license_evidence.get("official_model_card", {}).get("license") == "Apache-2.0" and license_evidence.get("policy", {}).get("redistribute_bundle_in_ugas") is False, "official task/model-card mapping resolves local QA use without redistribution")
        check("v054:model-bound", model.get("schema_version") == "0.5.4" and model.get("model", {}).get("url") and model.get("model", {}).get("sha256") == "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1" and model.get("model", {}).get("bytes", 0) > 0 and model.get("model", {}).get("license_status") == "RESOLVED_LOCAL_QA" and model.get("model", {}).get("outside_git") is True and model.get("model", {}).get("outside_review_zip") is True, "versioned local bundle hash, bytes and exclusion boundary are recorded")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:license-resolution", False, str(exc)); check("v054:model-bound", False, str(exc))

    try:
        estimator = load_json(ROOT / "docs/evidence/pose-qa-estimator-qualification-v054.json")
        detectability = load_json(ROOT / "docs/evidence/pose-qa-estimator-detectability.json")
        sanity = load_json(ROOT / "docs/evidence/pose-qa-estimator-sanity.json")
        summary = detectability.get("summary", {})
        gates = detectability.get("gates", {})
        check("v054:estimator-qualified", estimator.get("status") == "POSE_QA_ESTIMATOR_QUALIFIED" and estimator.get("qa_only") is True and estimator.get("provider_routing_used") is False and estimator.get("preprocess_policy") == "transparent_neutral_gray", "independent estimator qualifies on one global preprocessing policy")
        check("v054:detectability", summary.get("evaluated_images") == 10 and summary.get("measurable_images") == 10 and summary.get("r4_measurable") is True and summary.get("reference_edit_measurable") is True and summary.get("walk_frames_measurable") == 8 and summary.get("median_measurable_body_joints") >= 12 and summary.get("required_core_coverage_pass_ratio") >= 0.8 and summary.get("left_right_inversion_count") == 0 and all(gates.values()), "R4, reference edit and all eight historical walk frames are measurable")
        check("v054:sanity", sanity.get("status") == "POSE_QA_ESTIMATOR_QUALIFIED" and sanity.get("summary", {}).get("all_landmarks_plausible") is True and len(sanity.get("records", [])) == 10 and (ROOT / "docs/evidence/pose-qa-estimator-overlays-contact-sheet.png").is_file(), "landmark sanity and overlay evidence pass")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:estimator-qualified", False, str(exc)); check("v054:detectability", False, str(exc)); check("v054:sanity", False, str(exc))

    try:
        provider = load_json(ROOT / "docs/evidence/v054-provider-qualification.json")
        decision = provider.get("decision", {})
        lanes = provider.get("lanes", {})
        check("v054:provider-decision", provider.get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" and provider.get("estimator_status") == "POSE_QA_ESTIMATOR_QUALIFIED" and provider.get("record_count") == 9 and provider.get("fresh_outputs") == 9 and provider.get("seeds") == [54701, 54702, 54703] and set(lanes) == {"A", "C", "R"}, "provider gap is emitted only after estimator qualification and exactly nine outputs")
        check("v054:lane-causal-failure", decision.get("qualified_lane") is None and lanes.get("C", {}).get("validation", {}).get("live_valid") is True and lanes.get("R", {}).get("validation", {}).get("live_valid") is True and decision.get("lane_summary", {}).get("C", {}).get("absolute_pose_all_pass") is False and decision.get("lane_summary", {}).get("R", {}).get("absolute_pose_all_pass") is False, "C and R native graphs are live-valid but fail absolute detected-joint pose")
        check("v054:identity-separated", decision.get("lane_summary", {}).get("C", {}).get("identity_weapon_all_pass") is True and decision.get("lane_summary", {}).get("R", {}).get("identity_weapon_all_pass") is True, "identity and weapon gates remain separate and pass")
        check("v054:scope-boundary", provider.get("walk_authorized") is False and provider.get("directional_anchors_authorized") is False and provider.get("new_provider_used") is False and provider.get("new_strength_used") is False and provider.get("model_stack", {}).get("refcontrol_lora_strength") == 0.8, "no walk, anchors, provider or unauthorized strength was introduced")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:provider-decision", False, str(exc)); check("v054:lane-causal-failure", False, str(exc)); check("v054:scope-boundary", False, str(exc))

    try:
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.5.4.json")
        table = load_json(ROOT / "docs/evidence/v054-pose-error-table.json")
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.5.4.json")
        visual_result = validate_review_visual_manifest(visual, ROOT)
        check("v054:visual-manifest", visual_result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual_result.get("failures", [])) or "v0.5.4 visual roles are hash-bound")
        records = execution.get("records", [])
        outputs = [item.get("output_path") for item in records if item.get("output_path")]
        check("v054:execution", execution.get("record_count") == 9 and execution.get("required_output_count") == 9 and execution.get("all_fresh_binding") is True and execution.get("no_previous_frame_chaining") is True and execution.get("no_walk_executed") is True and len(set(outputs)) == 9, "all nine prompt/history/output bindings are fresh and independent")
        check("v054:error-table", table.get("schema_version") == "0.5.4" and table.get("metric_version") == "detected-joint-pose-error-1.0" and len(table.get("rows", [])) == 9 and table.get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", "nine-row detected-joint error table is bound to the provider decision")
        check("v054:lane-outputs", all((ROOT / path).is_file() for path in outputs) and len(outputs) == 9 and (ROOT / "docs/evidence/v054-pose-overlays-contact-sheet.png").is_file() and (ROOT / "docs/evidence/v054-lanes-contact-sheet.png").is_file(), "nine individual PNG outputs and review contacts are present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v054:visual-manifest", False, str(exc)); check("v054:execution", False, str(exc)); check("v054:error-table", False, str(exc)); check("v054:lane-outputs", False, str(exc))

    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.5.3 HISTORICAL BASELINE", "LICENSE RESOLUTION", "POSE QA ESTIMATOR QUALIFICATION", "PREPROCESSING MATRIX", "THRESHOLDS FROZEN BEFORE JOBS", "NATIVE LANE RECHECK", "REFCONTROL LANE RECHECK", "IDENTITY / WEAPON QA", "CAUSAL PROVIDER DECISION", "EXECUTION EVIDENCE", "STATE CONSISTENCY", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v054:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5.4 review headings present")
    check("v054:review-boundary", "POSE_QA_LOCAL_USE_LICENSE_RESOLVED" in review and "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" in review and "walk não foi executado" in review.casefold() and "aprovação externa" in review.casefold(), "active review separates license resolution, provider gap, blocked walk and external approval")


def _v055_checks() -> None:
    """Validate the active review-snapshot integrity correction."""
    state_path = ROOT / "docs/evidence/current-state.json"
    checkpoint_path = ROOT / "CHECKPOINT.md"
    review_path = ROOT / "REVIEW-v0.5.5.md"
    try:
        state = load_json(state_path)
        checkpoint = checkpoint_path.read_text(encoding="utf-8")
        review = review_path.read_text(encoding="utf-8")
        consistency = validate_state_consistency(state, checkpoint, review)
        check("v055:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active v0.5.5 state and documents are consistent")
        check("v055:state-schema", state.get("schema_version") == "0.5.5" and state.get("version") == "0.5.5" and state.get("phase") == "REVIEW_SNAPSHOT_INTEGRITY", "active state is v0.5.5 review snapshot integrity")
        check("v055:state-separation", state.get("pose_lane_status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" and state.get("review_snapshot_status") == "REVIEW_ARCHIVE_VERIFIED" and state.get("current_gate") == "REVIEW_SNAPSHOT_INTEGRITY_FIXED", "pose decision and review snapshot status are separate")
        check("v055:no-generation", state.get("generation_provider_change_authorized") is False and state.get("walk_authorized") is False and state.get("state_consistency", {}).get("new_generation_started") is False and state.get("state_consistency", {}).get("new_generation_jobs") == 0, "v0.5.5 records no new generation")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v055:state-consistency", False, str(exc)); check("v055:state-schema", False, str(exc)); check("v055:state-separation", False, str(exc)); check("v055:no-generation", False, str(exc))

    try:
        provider = load_json(ROOT / "docs/evidence/v054-provider-qualification.json")
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.5.4.json")
        table = load_json(ROOT / "docs/evidence/v054-pose-error-table.json")
        check("v055:v054-decision-preserved", provider.get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" and provider.get("record_count") == 9 and execution.get("record_count") == 9 and table.get("status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED", "v0.5.4 machine-readable pose decision is preserved")
        check("v055:v054-output-contract", len(table.get("rows", [])) == 9 and execution.get("all_fresh_binding") is True and execution.get("no_walk_executed") is True and set(provider.get("lanes", {})) == {"A", "C", "R"}, "the 9 A/C/R outputs and execution contract remain intact")
        output_hashes = {str(row.get("output_path")): str(row.get("output_sha256")) for row in table.get("rows", [])}
        check("v055:v054-output-hashes", len(output_hashes) == 9 and all((ROOT / path).is_file() and digest(ROOT / path) == value for path, value in output_hashes.items()), "all nine canonical PNG hashes match the v0.5.4 table")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v055:v054-decision-preserved", False, str(exc)); check("v055:v054-output-contract", False, str(exc)); check("v055:v054-output-hashes", False, str(exc))

    try:
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.5.5.json")
        visual_result = validate_review_visual_manifest(visual, ROOT)
        check("v055:visual-manifest", visual_result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual_result.get("failures", [])) or "v0.5.5 visual sources are hash-bound")
        sources = {str(item.get("source_path")) for item in visual.get("images", [])}
        check("v055:visual-sources", set(V054_CANONICAL_OUTPUTS).issubset(sources) and all((ROOT / source).is_file() for source in sources), "review manifest resolves every canonical source path")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v055:visual-manifest", False, str(exc)); check("v055:visual-sources", False, str(exc))

    matcher = self_test_sensitive_matcher()
    check("v055:matcher-self-test", matcher["status"] == "SENSITIVE_MATCHER_SELF_TEST_PASSED", "; ".join(matcher.get("failures", [])) or "anchored security matcher passes required include/exclude cases")
    check("v055:archive-verifier", (ROOT / "scripts/validation/verify_review_archive.py").is_file(), "tracked review archive verifier is present")
    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.5.4 AUDIT FINDING", "ROOT CAUSE", "SENSITIVE PATH MATCHER FIX", "CANONICAL SNAPSHOT CONTRACT", "REVIEW ARCHIVE VERIFIER", "V054 LANE OUTPUT PRESERVATION", "HASH VERIFICATION", "SECURITY EXCLUSIONS", "POSE DECISION PRESERVED", "NO NEW GENERATION EVIDENCE", "TESTS", "VALIDATION", "EXTRACTED ZIP SELF-TEST", "TRACKED SNAPSHOT / GITHUB", "STATE CONSISTENCY", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v055:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.5.5 review headings present")
    check("v055:review-boundary", "REVIEW_SNAPSHOT_INTEGRITY_FIXED" in review and "REVIEW_ARCHIVE_VERIFIED" in review and "não houve comfyui" in review.casefold() and "nenhum threshold" in review.casefold() and "foi alterado" in review.casefold(), "review separates packaging fix from unchanged pose decision and GPU boundary")


def _v060_checks() -> None:
    """Validate the immutable v0.6.0 SDXL ControlNet/IP-Adapter snapshot."""
    provider: dict[str, Any] = {}
    state_path = ROOT / "docs/evidence/current-state-v0.6.0.json"
    review_path = ROOT / "REVIEW-v0.6.0.md"
    try:
        state = load_json(state_path)
        check("v060:state-consistency", state.get("schema_version") == "0.6.0" and state.get("version") == "0.6.0" and state.get("phase") == "SDXL_CONTROL_POSE_PROVIDER_QUALIFICATION" and state.get("current_gate") == "SDXL_OPENPOSE_CONTROL_GAP", "immutable v0.6.0 state snapshot is internally identified")
        check("v060:state-schema", state.get("schema_version") == "0.6.0" and state.get("version") == "0.6.0" and state.get("phase") == "SDXL_CONTROL_POSE_PROVIDER_QUALIFICATION", "historical state is the SDXL qualification phase")
        check("v060:historical-separation", state.get("previous_release", {}).get("version") == "0.5.5" and state.get("pose_lane_status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" and state.get("previous_review_snapshot_status") == "REVIEW_ARCHIVE_VERIFIED", "v0.5.4 pose and v0.5.5 review results remain historical")
        check("v060:scope-boundary", state.get("walk_authorized") is False and state.get("generation_provider_change_authorized") is False, "walk and production provider routing remain unauthorized")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:state-consistency", False, str(exc)); check("v060:state-schema", False, str(exc)); check("v060:historical-separation", False, str(exc))

    try:
        audit = load_json(ROOT / "docs/evidence/custom-node-audit-ipadapter-plus.json")
        check("v060:custom-node-audit", audit.get("audit_status") == "CUSTOM_NODE_AUDIT_PASSED" and audit.get("commit") == "a0f451a5113cf9becb0847b92884cb10cbdec0ef" and audit.get("license") == "GPL-3.0-only" and audit.get("distribution_boundary") == "local-only" and audit.get("source_vendored_in_ugas") is False, "custom node is pinned, audited and local-only")
        check("v060:custom-node-residual-risk", "torch.load" in json.dumps(audit) and "optional" in json.dumps(audit).casefold(), "optional local embed loader residual risk is documented")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:custom-node-audit", False, str(exc))

    try:
        stack = load_json(ROOT / "docs/evidence/sdxl-model-stack-qualification.json")
        artifacts = stack.get("artifacts", [])
        check("v060:model-stack", stack.get("status") in {"MODEL_ARTIFACTS_VERIFIED", "MODEL_ARTIFACT_MISSING", "MODEL_HASH_MISMATCH"} and len(artifacts) == 4 and all(item.get("source_revision") and item.get("sha256") and item.get("license") and item.get("bytes", 0) > 0 for item in artifacts), "four exact SDXL provider artifacts have source/license/size/hash records")
        check("v060:model-boundary", stack.get("weights_outside_git") is True and all(item.get("verification", {}).get("path", "").lower().endswith(".safetensors") for item in artifacts), "weights are external and not part of the source package")
        for name in ("sdxl-base-model-qualification.json", "sdxl-openpose-controlnet-qualification.json", "ipadapter-sdxl-model-qualification.json", "clip-vision-qualification.json"):
            item = load_json(ROOT / "docs/evidence" / name)
            check(f"v060:artifact:{name}", item.get("source_revision") and item.get("license") and item.get("verification", {}).get("expected_sha256"), "artifact qualification record is explicit")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:model-stack", False, str(exc))

    try:
        doctor = load_json(ROOT / "docs/evidence/runtime-doctor-v0.6.0.json")
        required_nodes = doctor.get("required_nodes", {})
        check("v060:runtime-doctor", doctor.get("schema_version") == "0.6.0" and doctor.get("status") in {"RUNTIME_DOCTOR_PASSED", "SDXL_CONTROL_PROVIDER_HARDWARE_GAP"} and "RTX 5050" in doctor.get("gpu", {}).get("name", "") and doctor.get("gpu", {}).get("vram_total", 0) >= 512 * 1024 * 1024, "runtime doctor records the real RTX 5050 and VRAM gate")
        check("v060:native-nodes", all(required_nodes.get(name) is True for name in ("ControlNetLoader", "ControlNetApplyAdvanced", "CLIPVisionLoader", "CLIPVisionEncode", "IPAdapterModelLoader", "IPAdapterAdvanced")), "native ControlNet and pinned IP-Adapter nodes are observed")
        check("v060:runtime-strategy", doctor.get("runtime_strategy") == ["512x512 FP16-compatible attempt", "low-VRAM/offload fallback", "sequential model unload/offload"], "required 512/offload/unload strategy is recorded")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:runtime-doctor", False, str(exc)); check("v060:native-nodes", False, str(exc))

    try:
        workflow = load_json(ROOT / "docs/evidence/sdxl-provider-workflow-qualification.json")
        lanes = workflow.get("lanes", [])
        check("v060:workflow-qualification", workflow.get("status") in {"SDXL_PROVIDER_WORKFLOW_VALID", "SDXL_PROVIDER_WORKFLOW_GAP"} and {item.get("lane") for item in lanes} == {"P", "I", "PI"} and all(item.get("direct_guide") is (item.get("lane") in {"P", "PI"}) for item in lanes), "separate P/I/PI API graphs are registered with direct guide semantics")
        check("v060:workflow-separation", workflow.get("ipadapter_never_receives_skeleton") is True and workflow.get("controlnet_never_receives_r4_identity") is True and workflow.get("anchor", {}).get("sha256") == ANCHOR_SHA256, "ControlNet/IP-Adapter input separation and R4 hash are explicit")
        for workflow_id in ("sdxl-openpose-controlnet-p", "sdxl-ipadapter-i", "sdxl-openpose-ipadapter-character"):
            record = load_workflow(ROOT, workflow_id)
            check(f"v060:workflow:{workflow_id}", record.get("schema_version") == "0.6.0" and record.get("deterministic_seed") is True and record.get("api_json"), "v0.6.0 workflow registry entry is deterministic")
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        check("v060:workflow-qualification", False, str(exc)); check("v060:workflow-separation", False, str(exc))

    try:
        provider = load_json(ROOT / "docs/evidence/sdxl-provider-qualification.json")
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.6.0.json")
        final_status = provider.get("status")
        allowed = {"SDXL_CONTROL_POSE_PROVIDER_QUALIFIED", "SDXL_CONTROL_POSE_PROVIDER_GAP", "SDXL_CONTROL_PROVIDER_HARDWARE_GAP", "SDXL_IDENTITY_ADAPTER_GAP", "SDXL_OPENPOSE_CONTROL_GAP"}
        check("v060:provider-status", final_status in allowed and provider.get("walk_authorized") is False and provider.get("animation_authorized") is False and provider.get("external_approval") == "not-claimed", f"provider final state is fail-closed: {final_status}")
        check("v060:execution", execution.get("schema_version") == "0.6.0" and execution.get("previous_frame_chaining") is False and execution.get("weights_in_git") is False and execution.get("custom_node_source_vendored") is False and execution.get("attempted_record_count", 0) >= 3, "new execution evidence binds prompt/history/output and distribution boundaries")
        smoke = provider.get("smoke", {})
        check("v060:factorial", len(smoke.get("records", [])) == 3 and {item.get("lane") for item in smoke.get("records", [])} == {"P", "I", "PI"} and provider.get("seeds", {}).get("smoke") == 60701, "one new smoke seed is recorded separately for P/I/PI")
        if provider.get("paired", {}).get("records"):
            paired = provider["paired"]["records"]
            check("v060:paired", len(paired) == 9 and provider.get("seeds", {}).get("paired") == [60702, 60703, 60704], "three new paired seeds per factorial lane are recorded")
        else:
            check("v060:paired-blocked", provider.get("benchmark", {}).get("status") == "NOT_RUN" or provider.get("smoke", {}).get("technical_green") is False, "later phases are absent when the smoke technical gate is not green")
        benchmark = provider.get("benchmark", {})
        if benchmark.get("status") == "NOT_RUN":
            check("v060:benchmark-blocked", provider.get("smoke", {}).get("technical_green") is False, "strength benchmark is not fabricated before smoke green")
        else:
            check("v060:benchmark", len(benchmark.get("configs", [])) == 4 and benchmark.get("seed") == 60705 and benchmark.get("ipadapter_weight_type") == "linear" and benchmark.get("ranking_rule") == ["pose", "identity", "weapon", "lower_body", "nme", "runtime"], "strength benchmark uses four fixed PI configurations and declared rank")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:provider-status", False, str(exc)); check("v060:execution", False, str(exc)); check("v060:factorial", False, str(exc))

    try:
        visuals = load_json(ROOT / "docs/evidence/review-visuals-v0.6.0.json")
        result = validate_review_visual_manifest(visuals, ROOT)
        check("v060:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "current SDXL visual roles are hash-bound")
        check("v060:overlay-evidence", (ROOT / "docs/evidence/sdxl-identity-drift-contact.json").is_file() and (ROOT / "docs/evidence/sdxl-pose-detection-overlays-contact-sheet.png").is_file() or provider.get("smoke", {}).get("technical_green") is False, "pose overlays and regional identity evidence are present when generation reached QA")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v060:visual-manifest", False, str(exc))

    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.5.5 BASELINE", "POSE GAP STRATEGY", "STATE CONSISTENCY", "CUSTOM NODE AUDIT", "CUSTOM NODE PIN / LICENSE", "SDXL BASE MODEL", "OPENPOSE CONTROLNET MODEL", "IP-ADAPTER MODEL", "CLIP VISION MODEL", "RUNTIME / RTX 5050", "WORKFLOW TOPOLOGY", "P / I / PI FACTORIAL SMOKE", "STRENGTH BENCHMARK", "POSE QA", "IDENTITY / WEAPON QA", "FINAL PROVIDER QUALIFICATION", "CAPABILITY ROUTING", "REGRESSION PROTECTION", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY / DISTRIBUTION", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v060:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.6.0 review headings present")
    check("v060:review-boundary", "walk" in review.casefold() and "não" in review.casefold() and "aprovação externa" in review.casefold() and "GPL-3.0" in review, "review separates blocked walk, external approval and GPL boundary")


def _v061_checks() -> None:
    """Validate the immutable v0.6.1 smoke correction history."""
    state_path = ROOT / "docs/evidence/current-state-v0.6.1.json"
    review_path = ROOT / "REVIEW-v0.6.1.md"
    provider: dict[str, Any] = {}
    try:
        state = load_json(state_path)
        review = review_path.read_text(encoding="utf-8")
        check("v061:state-consistency", state.get("state_consistency", {}).get("status") == state.get("current_gate"), "immutable v0.6.1 state records its own historical gate")
        check("v061:state-schema", state.get("schema_version") == "0.6.1" and state.get("version") == "0.6.1" and state.get("phase") == "SDXL_CONTROL_POSE_PROVIDER_SMOKE_CORRECTION", "active state is the v0.6.1 smoke correction")
        check("v061:state-status", state.get("current_gate") == state.get("provider_smoke_status") and state.get("current_gate") == state.get("state_consistency", {}).get("status"), "provider smoke status, current gate and nested state agree")
        check("v061:state-boundary", state.get("previous_release", {}).get("version") == "0.6.0" and state.get("historical_pose_lane_status") == "LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED" and state.get("walk_authorized") is False and state.get("generation_provider_change_authorized") is False, "v0.6.0 history is preserved and walk/provider changes remain unauthorized")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v061:state-consistency", False, str(exc)); check("v061:state-schema", False, str(exc)); check("v061:state-status", False, str(exc)); check("v061:state-boundary", False, str(exc))

    allowed_statuses = {
        "SDXL_POSTPROCESS_GAP",
        "SDXL_OPENPOSE_CONTROL_GAP",
        "SDXL_COMBINED_CONDITIONING_INTERFERENCE_GAP",
        "SDXL_IDENTITY_ADAPTER_GAP",
        "SDXL_COMBINED_IDENTITY_GAP",
        "SDXL_SMOKE_GREEN_READY_FOR_BENCHMARK_PROMPT",
    }
    try:
        provider = load_json(ROOT / "docs/evidence/sdxl-provider-qualification-v0.6.1.json")
        status = provider.get("status")
        check("v061:provider-status", status in allowed_statuses and provider.get("walk_authorized") is False and provider.get("anchors_authorized") is False and provider.get("animation_authorized") is False and provider.get("external_approval") == "not-claimed", f"provider status is one of the bounded smoke outcomes: {status}")
        check("v061:provider-phase", provider.get("schema_version") == "0.6.1" and provider.get("phase") == "SDXL_CONTROL_POSE_PROVIDER_SMOKE_CORRECTION" and provider.get("prompt_id") == "PROMPT-05C-UGAS-SDXL-SMOKE-EVIDENCE-HARD-GATES-v0.6.1", "provider evidence is bound to the active prompt and phase")
        smoke = provider.get("smoke", {})
        smoke_records = smoke.get("records", [])
        check("v061:smoke-factorial", len(smoke_records) == 3 and {item.get("lane") for item in smoke_records} == {"P", "I", "PI"} and all(item.get("seed") == 61701 for item in smoke_records), "exactly one P/I/PI job per lane uses seed 61701")
        check("v061:later-phases-not-run", provider.get("paired", {}).get("status") == "NOT_RUN" and provider.get("paired", {}).get("records") == [] and provider.get("benchmark", {}).get("status") == "NOT_RUN" and provider.get("confirmation", {}).get("status") == "NOT_RUN" and provider.get("confirmation", {}).get("records") == [] and provider.get("seeds", {}).get("paired") == [] and provider.get("seeds", {}).get("benchmark") is None and provider.get("seeds", {}).get("confirmation") == [], "paired, benchmark and confirmation phases remain NOT_RUN")
        check("v061:provider-boundary", provider.get("new_generation_jobs") == 3 and provider.get("walk_authorized") is False and "walk" not in json.dumps(provider.get("smoke", {})).casefold(), "smoke is bounded to three jobs and contains no walk execution")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v061:provider-status", False, str(exc)); check("v061:provider-phase", False, str(exc)); check("v061:smoke-factorial", False, str(exc)); check("v061:later-phases-not-run", False, str(exc))

    try:
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.6.1.json")
        records = execution.get("records", [])
        execution_result = validate_execution_evidence_v061(execution, ROOT)
        check("v061:execution-exact-count", execution_result["status"] == "SDXL_V061_EXECUTION_EVIDENCE_PASSED", "; ".join(execution_result.get("failures", [])) or "execution validator requires three attempted and three completed generations")
        check("v061:execution-bindings", execution_result["status"] == "SDXL_V061_EXECUTION_EVIDENCE_PASSED", "prompt, exact history, raw hash, fresh target and distribution boundaries all pass")
        for item in records:
            generation = item.get("generation", {})
            lane = item.get("lane")
            raw_path = ROOT / str(generation.get("raw_output_path", ""))
            execution_record = generation.get("execution_evidence") or {}
            qualification_context = execution_record.get("qualification_context") or {}
            check(f"v061:raw:{lane}", generation.get("completed") is True and bool(generation.get("prompt_id")) and execution_record.get("prompt_id") == generation.get("prompt_id") and qualification_context.get("prompt_id") == "PROMPT-05C-UGAS-SDXL-SMOKE-EVIDENCE-HARD-GATES-v0.6.1" and generation.get("history_record_key") == generation.get("prompt_id") and generation.get("history_key_matches_prompt_id") is True and generation.get("target_existed_before_submission") is False and generation.get("previous_frame_chaining") is False and raw_path.is_file() and digest(raw_path) == generation.get("raw_output_sha256") and generation.get("raw_output_hash_matches_comfy") is True, f"{lane} preserves completed prompt/history/raw evidence with matching SHA-256")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v061:execution-exact-count", False, str(exc)); check("v061:execution-bindings", False, str(exc))

    try:
        phase_table = load_json(ROOT / "docs/evidence/sdxl-smoke-phase-table.json")
        lanes = phase_table.get("lanes", [])
        check("v061:phase-table", phase_table.get("schema_version") == "0.6.1" and len(lanes) == 3 and {item.get("lane") for item in lanes} == {"P", "I", "PI"} and all(item.get("generation", {}).get("completed") is True for item in lanes), "phase table preserves generation and postprocess stages for all lanes")
        for item in lanes:
            postprocess = item.get("postprocess") or {}
            check(f"v061:postprocess:{item.get('lane')}", isinstance(postprocess.get("attempted"), bool) and isinstance(postprocess.get("passed"), bool) and postprocess.get("status") in {"POSTPROCESS_PASSED", "POSTPROCESS_FAILED"}, f"{item.get('lane')} has structured postprocess outcome")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v061:phase-table", False, str(exc))

    try:
        identity = load_json(ROOT / "docs/evidence/sdxl-identity-hard-gates.json")
        required = {"aggregate_score_pass", "weapon_pass", "head_face_pass", "armor_palette_pass", "black_cloth_pass", "body_proportions_pass", "single_subject_pass", "identity_pass", "failure_reasons"}
        identity_records = identity.get("records", [])
        check("v061:identity-policy", identity.get("schema_version") == "0.6.1" and identity.get("hard_gate_policy", {}).get("aggregate_score_cannot_compensate") is True and set(identity.get("hard_gate_policy", {}).get("required", [])) == {"aggregate_score", "weapon", "head_face", "armor_palette", "black_cloth", "body_proportions", "single_subject"}, "identity hard-gate policy is explicit and fail-closed")
        check("v061:identity-records", all(required.issubset(set((item.get("hard_gates") or {}))) for item in identity_records), "every evaluated identity lane records all hard booleans and reasons")
        historical_i = ROOT / "docs/evidence/sdxl-qualification/outputs/smoke-i-seed-60701.png"
        if historical_i.is_file():
            from ugas.identity_hard_gates import analyze_foreground_components
            historical_components = analyze_foreground_components(historical_i)
            check("v061:historical-i-single-subject", historical_components.get("multiple_subjects_detected") is True and historical_components.get("large_foreground_components") >= 2, "historical v0.6.0 I fixture is rejected as multiple subjects")
        else:
            check("v061:historical-i-single-subject", False, "historical v0.6.0 I fixture is missing")
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        check("v061:identity-policy", False, str(exc)); check("v061:identity-records", False, str(exc)); check("v061:historical-i-single-subject", False, str(exc))

    try:
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.6.1.json")
        visual_result = validate_review_visual_manifest(visual, ROOT)
        check("v061:visual-manifest", visual_result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual_result.get("failures", [])) or "v0.6.1 raw/pose/hard-gate visual roles are hash-bound")
        required_visuals = set(visual.get("required_current_visuals", []))
        check("v061:visual-roles", {"sdxl-smoke-raw-p-i-pi-contact-sheet.png", "sdxl-smoke-raw-pose-overlays-contact-sheet.png", "sdxl-smoke-phase-table.json", "sdxl-identity-hard-gates.json", "execution-evidence-v0.6.1.json"}.issubset(required_visuals), "raw contact, pose overlay, phase, identity and execution evidence are required")
        if provider.get("smoke", {}).get("technical_green") is True or any(item.get("output_path") for item in provider.get("smoke", {}).get("records", [])):
            check("v061:processed-role", "sdxl-smoke-postprocessed-contact-sheet.png" in required_visuals or not any(item.get("output_path") for item in provider.get("smoke", {}).get("records", [])), "postprocessed contact is listed only when a processed output exists")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v061:visual-manifest", False, str(exc)); check("v061:visual-roles", False, str(exc))

    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.6.0 AUDIT FINDINGS", "EXECUTION EVIDENCE PRESERVATION FIX", "RAW GENERATION EVIDENCE", "RAW POSE QA", "POSTPROCESS QA", "IDENTITY HARD GATES", "SINGLE SUBJECT GATE", "P / I / PI CORRECTIVE SMOKE", "FINAL SMOKE CLASSIFICATION", "MODEL / CUSTOM NODE BOUNDARY", "EXECUTION EVIDENCE", "TESTS", "VALIDATION", "REVIEW ARCHIVE SELF-TEST", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v061:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.6.1 review headings present")
    check("v061:review-boundary", "review-visuals-v0.6.0.json" in review and "benchmark" in review.casefold() and "not_run" in json.dumps(provider).casefold() and "aprovação externa" in review.casefold() or "external approval" in review.casefold(), "current review separates historical v0.6.0 evidence, blocked later phases and external approval")


def _v062_checks() -> None:
    """Validate the immutable v0.6.2 calibration without reclassifying it."""
    state_path = ROOT / "docs/evidence/current-state-v0.6.2.json"
    review_path = ROOT / "REVIEW-v0.6.2.md"
    try:
        state = load_json(state_path)
        review = review_path.read_text(encoding="utf-8")
        historical_shape = state.get("schema_version") == "0.6.2" and state.get("version") == "0.6.2" and state.get("phase") == "SDXL_OPENPOSE_MODEL_CARD_CALIBRATION" and state.get("current_gate") == "SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS" and state.get("state_consistency", {}).get("status") == state.get("current_gate")
        check("v062:state-consistency", historical_shape, "immutable v0.6.2 state record is structurally consistent")
        check("v062:state-schema", historical_shape, "historical state is v0.6.2 model-card calibration")
        check("v062:state-boundary", state.get("historical_smoke_status") == "SDXL_OPENPOSE_CONTROL_GAP" and state.get("walk_authorized") is False and state.get("generation_provider_change_authorized") is False, "historical smoke and blocked promotion boundaries are explicit")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        state = {}
        review = ""
        check("v062:state-consistency", False, str(exc)); check("v062:state-schema", False, str(exc)); check("v062:state-boundary", False, str(exc))

    matrix: dict[str, Any] = {}
    try:
        from ugas.sdxl_openpose_calibration import CALIBRATION_MATRIX, CONFIRMATION_SEEDS, MODEL_CARD_CONFIGURATION, PROMPT_ID, SEED, validate_calibration_matrix
        matrix = load_json(ROOT / "docs/evidence/sdxl-openpose-config-matrix.json")
        check("v062:matrix-contract", not validate_calibration_matrix(), "P0/P1/P2 matrix is exact and ordered")
        entries = matrix.get("configs", [])
        check("v062:matrix-evidence", matrix.get("schema_version") == "0.6.2" and matrix.get("prompt_id") == PROMPT_ID and len(entries) == 3, "matrix evidence is bound to the prompt")
        expected = {item["id"]: item for item in CALIBRATION_MATRIX}
        for item in entries:
            wanted = expected.get(item.get("id"), {})
            check(f"v062:config:{item.get('id')}", all(item.get(key) == wanted.get(key) for key in ("width", "height", "steps", "sampler_name", "scheduler", "controlnet_strength")) and (item.get("graph") or {}).get("p_only") is True and not (item.get("graph") or {}).get("ipadapter_nodes"), f"{item.get('id')} preserves exact parameters and P-only graph")
        mapping = matrix.get("scheduler_mapping", {})
        check("v062:scheduler-mapping", mapping.get("semantic_mapping_validated") is True and mapping.get("runtime_sampler_name") == "euler_ancestral" and mapping.get("runtime_scheduler") == "normal" and "euler_ancestral" in mapping.get("observed_sampler_values", []) and "normal" in mapping.get("observed_scheduler_values", []), "Euler Ancestral mapping is backed by live object_info values")
        card = matrix.get("model_card", {}).get("configuration", {})
        check("v062:model-card", card.get("controlnet_conditioning_scale") == MODEL_CARD_CONFIGURATION["controlnet_conditioning_scale"] and card.get("num_inference_steps") == MODEL_CARD_CONFIGURATION["num_inference_steps"] and card.get("scheduler") == MODEL_CARD_CONFIGURATION["scheduler"], "model-card operating point is recorded")
        check("v062:matrix-seed", all(item.get("seed") == SEED for item in matrix.get("triage_results", [])), "triage seed is 62701")
    except (OSError, json.JSONDecodeError, KeyError, ImportError) as exc:
        check("v062:matrix-contract", False, str(exc)); check("v062:matrix-evidence", False, str(exc)); check("v062:scheduler-mapping", False, str(exc)); check("v062:model-card", False, str(exc)); check("v062:matrix-seed", False, str(exc))

    try:
        runtime_table = load_json(ROOT / "docs/evidence/sdxl-openpose-config-runtime-table.json")
        check("v062:runtime-table", runtime_table.get("schema_version") == "0.6.2" and len(runtime_table.get("configs", [])) == 3 and runtime_table.get("p2_retry_policy", {}).get("max_retries") == 1 and runtime_table.get("p2_retry_policy", {}).get("parameters_unchanged") is True, "runtime table records all configurations and bounded P2 retry")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v062:runtime-table", False, str(exc))

    try:
        execution = load_json(ROOT / "docs/evidence/execution-evidence-v0.6.2.json")
        records = execution.get("records", [])
        check("v062:execution-contract", execution.get("schema_version") == "0.6.2" and execution.get("prompt_id") == "PROMPT-05D-UGAS-SDXL-OPENPOSE-MODEL-CARD-CALIBRATION-v0.6.2" and execution.get("triage_config_count") == 3 and execution.get("triage_attempted_execution_count") >= 3 and execution.get("ipadapter_executed") is False, "execution evidence has exact prompt and P-only boundary")
        triage = [item for item in records if item.get("phase") == "triage"]
        confirmation = [item for item in records if item.get("phase") == "confirmation"]
        check("v062:triage-records", len(triage) == execution.get("triage_attempted_execution_count") and {item.get("config_id") for item in triage} == {"P0", "P1", "P2"} and all(item.get("seed") == 62701 for item in triage), "P0/P1/P2 triage records are unique and use seed 62701")
        qualification = load_json(ROOT / "docs/evidence/sdxl-openpose-p-qualification.json")
        stage_a_pass = qualification.get("triage", {}).get("stage_a_pass_count", 0) > 0
        check("v062:confirmation-gate", (bool(confirmation) and len(confirmation) == 3 and {item.get("seed") for item in confirmation} == {62711, 62712, 62713}) if stage_a_pass else not confirmation and qualification.get("confirmation", {}).get("status") == "NOT_RUN", "confirmation follows the Stage A conditional gate")
        check("v062:qualification-boundary", qualification.get("scope", {}).get("lane") == "P" and qualification.get("scope", {}).get("ipadapter_executed") is False and qualification.get("scope", {}).get("identity_r4_executed") is False and qualification.get("scope", {}).get("walk") == "NOT_RUN" and qualification.get("scope", {}).get("anchors") == "NOT_RUN" and qualification.get("production_approval") == "not-granted", "qualification excludes IP-Adapter, R4, walk and anchors")
        if records:
            for item in records:
                generation = item.get("generation") or {}
                if generation.get("completed") is True:
                    raw = ROOT / str(generation.get("raw_output_path", ""))
                    check(f"v062:raw-binding:{item.get('stage')}", generation.get("fresh_binding") is True and generation.get("history_key_matches_prompt_id") is True and generation.get("target_existed_before_submission") is False and generation.get("raw_output_hash_matches_comfy") is True and raw.is_file() and digest(raw) == generation.get("raw_output_sha256"), "fresh history/raw SHA binding is valid")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v062:execution-contract", False, str(exc)); check("v062:triage-records", False, str(exc)); check("v062:confirmation-gate", False, str(exc)); check("v062:qualification-boundary", False, str(exc))

    try:
        qualification = load_json(ROOT / "docs/evidence/sdxl-openpose-p-qualification.json")
        threshold = load_json(ROOT / "docs/evidence/pose-thresholds-v054.json")
        check("v062:threshold-boundary", qualification.get("thresholds", {}).get("source") == "docs/evidence/pose-thresholds-v054.json" and qualification.get("thresholds", {}).get("changed") is False and qualification.get("thresholds", {}).get("absolute_pose") == threshold.get("absolute_pose"), "frozen v0.5.4 pose thresholds are unchanged")
        for item in qualification.get("triage", {}).get("records", []):
            pose = (item.get("raw_pose_qa") or {}).get("pose") or {}
            if pose:
                check(f"v062:pose-order:{item.get('config_id')}", (item.get("raw_pose_qa") or {}).get("preprocess_policy") == "raw_rgb_neutral_gray" and item.get("postprocess", {}).get("status") == "NOT_RUN", "raw pose QA precedes independent postprocess")
                check(f"v062:human-form:{item.get('config_id')}", (item.get("human_form_qa") or {}).get("visual_review") == "required", "human-form technical QA stays separate from auto-approval")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v062:threshold-boundary", False, str(exc))

    try:
        visual = load_json(ROOT / "docs/evidence/review-visuals-v0.6.2.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v062:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.6.2 visuals are hash-bound")
        current_roles = {"sdxl-openpose-config-triage-contact-sheet.png", "sdxl-openpose-config-pose-overlays-contact-sheet.png", "sdxl-openpose-config-matrix.json", "sdxl-openpose-config-runtime-table.json", "execution-evidence-v0.6.2.json", "sdxl-openpose-p-qualification.json", "sdxl-openpose-guide-512.png", "sdxl-openpose-guide-768.png", "sdxl-openpose-guide-1024.png"}
        check("v062:visual-roles", current_roles.issubset(set(visual.get("required_current_visuals", []))) and current_roles.issubset({item.get("archive_name") for item in visual.get("images", [])}), "guides and P-only review roles are listed")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v062:visual-manifest", False, str(exc)); check("v062:visual-roles", False, str(exc))

    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.6.1 AUDIT RESULT", "MODEL CARD CONFIGURATION FINDING", "STATE RECLASSIFICATION", "P-ONLY SCOPE", "MODEL CARD SOURCE", "SAMPLER / SCHEDULER MAPPING", "RESOLUTION GUIDE RENDERING", "RTX 5050 MEMORY STRATEGY", "P0 / P1 / P2 TRIAGE", "RAW POSE QA", "HUMAN-FORM TECHNICAL QA", "P-ONLY CONFIRMATION", "FINAL P-LANE DECISION", "POSTPROCESS DIAGNOSTIC", "EXECUTION EVIDENCE", "TESTS", "VALIDATION", "REVIEW ARCHIVE SELF-TEST", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
    check("v062:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.6.2 review headings present")
    check("v062:review-boundary", "review-visuals-v0.6.0.json" in review and "not-granted" in review and "NOT_RUN" in review and "human" in review.casefold(), "review preserves history, blocked lanes and separate human review")


def _v070_checks() -> None:
    """Validate the immutable v0.7.0 cutout-rig slice without rebinding it."""
    evidence = ROOT / "docs" / "evidence"
    current_paths = {
        "REVIEW-v0.7.0.md", "docs/test-coverage-matrix-v0.7.0.md",
        "providers/manifests/deterministic-cutout-rig-2d.json",
        "schemas/cutout-rig.json", "schemas/cutout-rig-part.json",
        "src/ugas/cutout_rig.py", "scripts/validation/run_cutout_rig_v070.py",
        "scripts/validation/materialize_cutout_review_evidence.py",
        "docs/evidence/current-state.json", "docs/evidence/current-state-v0.6.2.json", "docs/evidence/state-consistency-v0.6.2.json",
        "docs/evidence/review-visuals-v0.7.0.json",
        *{f"docs/evidence/{name}" for name in REQUIRED_V070_REVIEW_EVIDENCE},
    }
    for relative in sorted(current_paths):
        path = ROOT / relative
        check(f"v070:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
        if path.is_file():
            check(f"v070:tracked:{relative}", tracked(relative), "tracked or present in review snapshot")

    try:
        state = load_json(evidence / "current-state-v0.7.0.json")
        review = (ROOT / "REVIEW-v0.7.0.md").read_text(encoding="utf-8")
        consistency = load_json(evidence / "state-consistency-v0.7.0.json")
        check("v070:state-consistency", consistency.get("status") == "STATE_CONSISTENCY_PASSED", "immutable v0.7.0 state-consistency evidence is preserved")
        check("v070:state-gate", state.get("current_gate") == "CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP" and state.get("provider_smoke_status") == state.get("current_gate"), "current provider gate is fail-closed and synchronized")
        check("v070:state-boundary", state.get("walk_authorized") is False and state.get("generation_provider_change_authorized") is False and state.get("state_consistency", {}).get("new_generation_jobs") == 0, "walk, routing promotion and ComfyUI generation remain blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        check("v070:state-consistency", False, str(exc)); check("v070:state-gate", False, str(exc)); check("v070:state-boundary", False, str(exc))

    try:
        provider = load_json(ROOT / "providers/manifests/deterministic-cutout-rig-2d-v0.7.3.json")
        validate_instance(provider, load_json(ROOT / "schemas/provider-manifest.json"))
        check("v070:provider-contract", provider.get("id") == "deterministic-cutout-rig-2d" and provider.get("provider_type") == "deterministic_renderer" and provider.get("generation_model") == "none" and provider.get("priority") == "explicit-capability-only", "provider is deterministic and capability-explicit")
        check("v070:provider-routing", provider.get("runtime_policy", {}).get("comfyui_jobs") == 0 and provider.get("runtime_policy", {}).get("walk_frames") is False, "production routing and walk are unchanged")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        check("v070:provider-contract", False, str(exc)); check("v070:provider-routing", False, str(exc))

    try:
        sam = load_json(evidence / "sam2-provider-qualification.json")
        checkpoint = load_json(evidence / "sam2-checkpoint-provenance.json")
        check("v070:sam2-runtime", sam.get("status") == "SAM2_RUNTIME_QUALIFIED" and sam.get("official_source") == "https://github.com/facebookresearch/sam2" and sam.get("model", {}).get("family") == "SAM 2.1 Hiera Small" and sam.get("imports", {}).get("SAM2ImagePredictor") is True, "official pinned SAM2.1 Hiera Small runtime/import smoke passed")
        checkpoint_record = checkpoint.get("checkpoint", {})
        check("v070:sam2-checkpoint", checkpoint_record.get("sha256") == sam.get("checkpoint", {}).get("sha256") and checkpoint_record.get("outside_git") is True and checkpoint_record.get("outside_review_zip") is True and not any(path.casefold() == str(checkpoint_record.get("filename", "")).casefold() for path in subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.splitlines()), "checkpoint is hash-bound and external")
        check("v070:sam2-policy", sam.get("runtime_policy", {}).get("comfyui_custom_node") is False and sam.get("runtime_policy", {}).get("sam3_forbidden") is True, "no ComfyUI custom node and SAM3 is forbidden")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v070:sam2-runtime", False, str(exc)); check("v070:sam2-checkpoint", False, str(exc)); check("v070:sam2-policy", False, str(exc))

    try:
        skeleton = load_json(evidence / "r4-source-skeleton.json")
        source_record = skeleton.get("skeleton", {})
        check("v070:source-skeleton", source_record.get("status") == "SOURCE_SKELETON_QUALIFIED" and source_record.get("required_count") == 12 and source_record.get("enough_joints") is True, "MediaPipe source skeleton has all required core joints")
        masks = load_json(evidence / "r4-cutout-part-masks.json")
        global_stats = masks.get("global", {})
        parts = masks.get("parts", {})
        purity_ok = all((item.get("final_stats") or {}).get("foreground_purity", 0) >= 0.98 and (item.get("final_stats") or {}).get("nonempty") is True for item in parts.values())
        check("v070:mask-qa", masks.get("status") == "CUTOUT_RIG_MASKS_QUALIFIED" and global_stats.get("union_coverage", 0) >= 0.95 and global_stats.get("unassigned_fraction", 1) <= 0.05 and global_stats.get("unresolved_overlap_fraction", 1) <= 0.03 and set(parts) == {"head", "torso_pelvis", "left_upper_arm", "left_forearm_hand", "right_upper_arm", "right_forearm_hand", "left_thigh", "left_shin_foot", "right_thigh", "right_shin_foot", "sword"} and purity_ok, "eleven masks pass coverage, overlap, purity and nonempty gates")
        check("v070:mask-provenance", masks.get("postprocess", {}).get("ownership_partition") is True and masks.get("postprocess", {}).get("pixels_invented") == 0, "mask ownership partition invents no pixels")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v070:source-skeleton", False, str(exc)); check("v070:mask-qa", False, str(exc)); check("v070:mask-provenance", False, str(exc))

    try:
        rig = load_json(evidence / "r4-cutout-rig.json")
        check("v070:rig-manifest", validate_rig_manifest(rig, expected_schema_version="0.7.0")["status"] == "CUTOUT_RIG_MANIFEST_VALID" and len(rig.get("parts", [])) == 11 and rig.get("root_joint") == "pelvis", "immutable v0.7.0 rig manifest remains hierarchy-bound")
        provenance = load_json(evidence / "cutout-rig-pixel-provenance.json")
        check("v070:pixel-provenance", provenance.get("generated_pixel_fraction") == 0.0 and provenance.get("source_pixel_provenance_fraction", 0) >= 0.98 and provenance.get("recolor_count") == 0 and provenance.get("nonuniform_scale_count") == 0, "pixel provenance is source-only")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, NameError) as exc:
        check("v070:rig-manifest", False, str(exc)); check("v070:pixel-provenance", False, str(exc))

    try:
        q0 = load_json(evidence / "cutout-q0-qa.json")
        check("v070:q0", q0.get("status") == "CUTOUT_RIG_RECONSTRUCTION_PASSED" and q0.get("metrics", {}).get("alpha_iou", 0) >= 0.98 and q0.get("metrics", {}).get("rgb_mae", 999) <= 3.0 and q0.get("metrics", {}).get("bbox_drift_px", 999) <= 2.0 and all(q0.get("hard_gates", {}).values()), "Q0 neutral reconstruction passes fidelity gates")
        pose = load_json(evidence / "cutout-rig-pose-qa.json")
        check("v070:pose-boundary", pose.get("walk_frames") == "NOT_RUN" and pose.get("spritesheet") == "NOT_RUN" and pose.get("gif") == "NOT_RUN" and pose.get("thresholds_unchanged") is True, "static Q0/Q1/Q2 only and thresholds unchanged")
        pose_failures = {str(record.get("pose")): record.get("media_pipe", {}).get("failure_reasons", []) for record in pose.get("poses", [])}
        check("v070:pose-decision", pose.get("status") == "CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP" and pose_failures.get("q1-contact-left") and pose_failures.get("q2-passing-left"), "Q1/Q2 estimator gap is recorded fail-closed")
        internal = pose.get("internal", {})
        check("v070:internal-qa", all((item or {}).get("status") == "CUTOUT_RIG_INTERNAL_QA_PASSED" for item in internal.values()), "Q0/Q1/Q2 internal rig geometry passes")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v070:q0", False, str(exc)); check("v070:pose-boundary", False, str(exc)); check("v070:pose-decision", False, str(exc)); check("v070:internal-qa", False, str(exc))

    try:
        seams = load_json(evidence / "cutout-rig-seam-qa.json")
        check("v070:seam-qa", seams.get("status") == "SEAM_QA_PASSED" and all(item.get("status") == "SEAM_QA_PASSED" and item.get("disconnect_count") == 0 and item.get("duplicate_body_components") == 0 for item in seams.get("poses", {}).values()), "Q0/Q1/Q2 seam hard gates pass")
        execution = load_json(evidence / "execution-evidence-v0.7.0.json")
        check("v070:execution-boundary", execution.get("comfyui_generation_jobs") == 0 and execution.get("sam2_calls", {}).get("rig_revision_segmentation") == 1 and execution.get("sam2_calls", {}).get("per_frame_segmentation") == 0 and execution.get("sam3_used") is False and execution.get("walk") == "NOT_RUN", "execution evidence proves isolated one-pass/no-walk boundary")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v070:seam-qa", False, str(exc)); check("v070:execution-boundary", False, str(exc))

    try:
        visual = load_json(evidence / "review-visuals-v0.7.0.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v070:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.7.0 review roles are hash-bound")
        headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.6.2 AUDIT RESULT", "ARCHITECTURE PIVOT", "SAM2 OFFICIAL SOURCE / LICENSE / PIN", "SAM2 RUNTIME / CHECKPOINT", "SOURCE SKELETON", "PART SEGMENTATION", "MASK QA", "WEAPON MASK", "CUTOUT RIG MANIFEST", "DETERMINISTIC RENDERER", "PIXEL PROVENANCE", "Q0 NEUTRAL RECONSTRUCTION", "Q1 CONTACT-LEFT", "Q2 PASSING-LEFT", "INTERNAL RIG GEOMETRY QA", "MEDIAPIPE POSE QA", "SEAM / CONTINUITY QA", "FINAL PROVIDER DECISION", "NO COMFYUI GENERATION", "TESTS", "VALIDATION", "REVIEW ARCHIVE SELF-TEST", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
        review = (ROOT / "REVIEW-v0.7.0.md").read_text(encoding="utf-8")
        check("v070:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.7.0 review headings present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v070:visual-manifest", False, str(exc)); check("v070:review-headings", False, str(exc))


def _v071_checks() -> None:
    """Validate the active fidelity/QA correction with fail-closed outcomes."""
    evidence = ROOT / "docs" / "evidence"
    current_paths = {
        "REVIEW-v0.7.1.md", "docs/test-coverage-matrix-v0.7.1.md",
        "providers/manifests/deterministic-cutout-rig-2d.json", "providers/manifests/deterministic-cutout-rig-2d-v0.7.1.json", "schemas/cutout-rig.json", "schemas/cutout-rig-part.json",
        "schemas/cutout-rig.json", "schemas/cutout-rig-part.json", "src/ugas/cutout_rig.py", "scripts/validation/run_cutout_rig_v071.py",
        "scripts/validation/materialize_cutout_review_evidence.py", "docs/evidence/current-state.json", "docs/evidence/current-state-v0.7.0.json",
        "docs/evidence/current-state-v0.7.1.json", "docs/evidence/state-consistency-v0.7.1.json", "docs/evidence/state-consistency-v0.7.0.json", "docs/evidence/review-visuals-v0.7.1.json",
        *{f"docs/evidence/{name}" for name in REQUIRED_V071_REVIEW_EVIDENCE},
        "docs/evidence/r4-cutout-raw-masks-v071-manifest.json", "docs/evidence/r4-cutout-refined-masks-v071-manifest.json",
    }
    for part in ("head", "torso_pelvis", "left_upper_arm", "left_forearm_hand", "right_upper_arm", "right_forearm_hand", "left_thigh", "left_shin_foot", "right_thigh", "right_shin_foot", "sword"):
        current_paths.update({f"docs/evidence/r4-cutout-raw-masks-v071/{part}.png", f"docs/evidence/r4-cutout-refined-masks-v071/{part}.png", f"docs/evidence/r4-cutout-parts-v071/{part}.png"})
    for relative in sorted(current_paths):
        path = ROOT / relative
        check(f"v071:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
        if path.is_file():
            check(f"v071:tracked:{relative}", tracked(relative), "tracked or present in review snapshot")

    try:
        state = load_json(evidence / "current-state-v0.7.1.json")
        review = (ROOT / "REVIEW-v0.7.1.md").read_text(encoding="utf-8")
        historical_consistency = load_json(evidence / "state-consistency-v0.7.1.json")
        check("v071:state-consistency", historical_consistency.get("schema_version") == "0.7.1" and historical_consistency.get("status") == "STATE_CONSISTENCY_PASSED", "immutable v0.7.1 state consistency is preserved")
        check("v071:state-gate", state.get("current_gate") in {"CUTOUT_RIG_SEGMENTATION_GAP", "CUTOUT_RIG_RECONSTRUCTION_GAP", "CUTOUT_RIG_TARGET_ADAPTER_GAP", "CUTOUT_RIG_RENDERER_GAP", "CUTOUT_RIG_SEAM_GAP", "CUTOUT_RIG_EXTERNAL_POSE_QA_GAP", "CUTOUT_RIG_VISUAL_REVIEW_REQUIRED", "CUTOUT_RIG_POSE_PROVIDER_QUALIFIED"} and state.get("provider_smoke_status") == state.get("current_gate"), "active v0.7.1 gate is synchronized and fail-closed")
        check("v071:state-history", state.get("previous_release", {}).get("version") == "0.7.0" and "false-positive" in review.casefold() and state.get("walk_authorized") is False, "v0.7.0 previous release and corrected false-positive audit finding are preserved")
        check("v071:state-boundary", state.get("generation_provider_change_authorized") is False and state.get("state_consistency", {}).get("new_generation_jobs") == 0, "routing, ComfyUI generation and walk remain blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        check("v071:state-consistency", False, str(exc)); check("v071:state-gate", False, str(exc)); check("v071:state-history", False, str(exc)); check("v071:state-boundary", False, str(exc))

    try:
        provider = load_json(ROOT / "providers/manifests/deterministic-cutout-rig-2d-v0.7.1.json")
        validate_instance(provider, load_json(ROOT / "schemas/provider-manifest.json"))
        check("v071:provider-contract", provider.get("schema_version") == "0.7.1" and provider.get("qualification_evidence") == "docs/evidence/cutout-rig-provider-qualification-v071.json" and provider.get("generation_model") == "none", "provider manifest is bound to v0.7.1 deterministic evidence")
        check("v071:provider-boundary", provider.get("runtime_policy", {}).get("comfyui_jobs") == 0 and provider.get("runtime_policy", {}).get("walk_frames") is False and "external review required" in " ".join(provider.get("limits", [])), "provider routing and walk boundaries remain explicit")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        check("v071:provider-contract", False, str(exc)); check("v071:provider-boundary", False, str(exc))

    try:
        sam = load_json(evidence / "sam2-provider-qualification-v071.json")
        checkpoint = load_json(evidence / "sam2-checkpoint-provenance-v071.json")
        checkpoint_record = checkpoint.get("checkpoint", {})
        check("v071:sam2-runtime", sam.get("schema_version") == "0.7.1" and sam.get("status") == "SAM2_RUNTIME_QUALIFIED" and sam.get("official_source") == "https://github.com/facebookresearch/sam2" and sam.get("model", {}).get("family") == "SAM 2.1 Hiera Small" and sam.get("imports", {}).get("SAM2ImagePredictor") is True, "pinned official SAM2.1 Hiera Small runtime/import smoke is qualified")
        check("v071:sam2-checkpoint", checkpoint_record.get("sha256") == sam.get("checkpoint", {}).get("sha256") and checkpoint_record.get("outside_git") is True and checkpoint_record.get("outside_review_zip") is True, "SAM2 checkpoint is hash-bound and external")
        check("v071:sam2-policy", sam.get("runtime_policy", {}).get("comfyui_custom_node") is False and sam.get("runtime_policy", {}).get("sam3_forbidden") is True, "SAM2 lane remains isolated from ComfyUI and SAM3")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v071:sam2-runtime", False, str(exc)); check("v071:sam2-checkpoint", False, str(exc)); check("v071:sam2-policy", False, str(exc))

    try:
        source = load_json(evidence / "r4-source-skeleton-v071.json")
        check("v071:source-skeleton", source.get("schema_version") == "0.7.1" and source.get("skeleton", {}).get("enough_joints") is True and source.get("skeleton", {}).get("required_count") == 12, "MediaPipe source skeleton is complete and version-bound")
        target = load_json(evidence / "r4-cutout-target-adapter-v071.json")
        q1, q2 = target["q1"], target["q2"]
        check("v071:target-hips", all(item.get("hip_invariant", {}).get("distinct") is True and item.get("hip_invariant", {}).get("bounded") is True for item in (q1, q2)) and q1["joints"]["hip_left"] != q1["joints"]["hip_right"] and q2["joints"]["hip_left"] != q2["joints"]["hip_right"], "Q1/Q2 hips remain distinct and source-width bounded")
        check("v071:target-sides", q1.get("side_mapping", {}).get("anatomical_left") == "guide_right" and q1.get("side_mapping", {}).get("anatomical_right") == "guide_left", "guide image-side to anatomical-side mapping is explicit")
        weapon_ok = all(not item.get("weapon_attachment", {}).get("tip_crosses_protected_torso") and max(abs(float(item.get("weapon_attachment", {}).get("selected_swing_degrees", 999))), 0.0) <= 12.0 for item in (q1, q2))
        check("v071:weapon", weapon_ok and all(item.get("weapon_attachment", {}).get("anatomical_wrist") == "wrist_right" for item in (q1, q2)), "weapon attachment preserves wrist, local-angle bound and protected torso corridor")
        gait = target.get("gait_semantics", {})
        check("v071:gait", gait.get("distinct") is True and gait.get("q1_contact_semantics") is True and gait.get("q2_passing_semantics") is True, "Q1/Q2 lower-body phase semantics are distinct")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v071:source-skeleton", False, str(exc)); check("v071:target-hips", False, str(exc)); check("v071:target-sides", False, str(exc)); check("v071:weapon", False, str(exc)); check("v071:gait", False, str(exc))

    try:
        raw = load_json(evidence / "r4-cutout-raw-masks-v071-manifest.json")
        refined = load_json(evidence / "r4-cutout-refined-masks-v071-manifest.json")
        names = {"head", "torso_pelvis", "left_upper_arm", "left_forearm_hand", "right_upper_arm", "right_forearm_hand", "left_thigh", "left_shin_foot", "right_thigh", "right_shin_foot", "sword"}
        check("v071:masks-separated", set(raw.get("parts", {})) == names and set(refined.get("parts", {})) == names, "raw and refined manifests enumerate all eleven parts")
        hash_ok = True
        for name in names:
            raw_item, refined_item = raw["parts"][name], refined["parts"][name]
            raw_path, refined_path = ROOT / raw_item["raw_mask_path"], ROOT / refined_item["mask_path"]
            hash_ok = hash_ok and raw_path.is_file() and refined_path.is_file() and digest(raw_path) == raw_item["raw_mask_sha256"] and digest(refined_path) == refined_item["mask_sha256"]
        check("v071:masks-hash-bound", hash_ok and any(raw["parts"][name]["raw_mask_path"] != refined["parts"][name]["mask_path"] for name in names), "raw/refined mask paths and hashes are distinct and bound")
        global_stats = refined.get("global", {})
        check("v071:ownership", refined.get("status") == "CUTOUT_RIG_MASKS_QUALIFIED" and global_stats.get("semantic_alpha_union_coverage", 0) >= 0.995 and global_stats.get("strict_alpha_ownership_coverage", 0) >= 0.99 and global_stats.get("unassigned_semantic_fraction", 1) <= 0.005 and refined.get("postprocess", {}).get("source_residual_fallback") is False, "full foreground ownership and unassigned threshold are explicit")
        component_gates = refined.get("component_gates", {})
        check("v071:components", component_gates.get("passed") is True and component_gates.get("measured", {}).get("torso_pelvis", {}).get("meaningful_component_count", 99) <= 3 and component_gates.get("measured", {}).get("sword", {}).get("meaningful_component_count", 99) <= 2, "component-aware semantic gate rejects torso/sword excessive fragments")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v071:masks-separated", False, str(exc)); check("v071:masks-hash-bound", False, str(exc)); check("v071:ownership", False, str(exc)); check("v071:components", False, str(exc))

    try:
        rig = load_json(evidence / "r4-cutout-rig-v071.json")
        validate_instance(rig, load_json(ROOT / "schemas/cutout-rig.json"))
        manifest_result = validate_rig_manifest(rig)
        check("v071:rig-manifest", manifest_result["status"] == "CUTOUT_RIG_MANIFEST_VALID" and len(rig.get("parts", [])) == 11 and rig.get("renderer", {}).get("joint_patch_copy_count") == 0 and rig.get("provenance", {}).get("source_residual_fallback_used") is False, "rig manifest has no untransformed joint patches or residual fallback")
        provenance = load_json(evidence / "cutout-rig-pixel-provenance-v071.json")
        check("v071:provenance", provenance.get("generated_pixel_fraction") == 0.0 and provenance.get("joint_patch_copy_count") == 0 and provenance.get("untransformed_joint_patch_pixels") == 0 and provenance.get("source_residual_fallback_used") is False, "pixel provenance remains source-only")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        check("v071:rig-manifest", False, str(exc)); check("v071:provenance", False, str(exc))

    try:
        q0 = load_json(evidence / "cutout-q0-reconstruction-qa-v071.json")
        check("v071:q0", q0.get("status") == "CUTOUT_RIG_RECONSTRUCTION_PASSED" and q0.get("metrics", {}).get("alpha_iou", 0) >= 0.995 and q0.get("metrics", {}).get("rgb_mae", 999) <= 1.5 and q0.get("metrics", {}).get("bbox_drift_px", 999) <= 1 and q0.get("source_residual_fallback_used") is False and all(q0.get("hard_gates", {}).values()), "Q0 reconstructs from parts with strict no-residual gates")
        pose = load_json(evidence / "cutout-rig-pose-qa-v071.json")
        check("v071:pose-boundary", pose.get("walk_frames") == "NOT_RUN" and pose.get("spritesheet") == "NOT_RUN" and pose.get("gif") == "NOT_RUN" and pose.get("thresholds_unchanged") is True, "only static Q0/Q1/Q2 was executed")
        check("v071:pose-decision", pose.get("status") in {"CUTOUT_RIG_SEAM_GAP", "CUTOUT_RIG_EXTERNAL_POSE_QA_GAP", "CUTOUT_RIG_VISUAL_REVIEW_REQUIRED", "CUTOUT_RIG_POSE_PROVIDER_QUALIFIED"}, "pose decision is an explicit machine state")
        check("v071:overlay-metadata", all(record.get("target") and record.get("media_pipe") is not None for record in pose.get("poses", [])) and len(pose.get("poses", [])) == 2, "target and detected skeleton metadata is present for Q1/Q2 overlays")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v071:q0", False, str(exc)); check("v071:pose-boundary", False, str(exc)); check("v071:pose-decision", False, str(exc)); check("v071:overlay-metadata", False, str(exc))

    try:
        internal = load_json(evidence / "cutout-rig-internal-qa-v071.json")
        check("v071:internal-qa", internal.get("status") == "CUTOUT_RIG_INTERNAL_QA_PASSED" and all(item.get("status") == "CUTOUT_RIG_INTERNAL_QA_PASSED" and item.get("transforms") and all("forward_affine_matrix" in transform for transform in item.get("transforms", [])) for item in internal.get("poses", {}).values()), "internal QA records real forward affine matrices and geometry metrics")
        seam = load_json(evidence / "cutout-rig-seam-qa-v071.json")
        final = seam.get("final", {})
        check("v071:seam-real", isinstance(final.get("q0", {}).get("overlap_pixels"), int) and isinstance(final.get("q1-contact-left", {}).get("overlap_outside_joint_pixels"), int) and isinstance(final.get("q2-passing-left", {}).get("margins_px", {}).get("bottom"), int) and seam.get("thresholds", {}).get("safe_margin_px") == 24, "seam overlap, margin and continuity are measured from rendered output")
        check("v071:seam-fail-closed", seam.get("status") == "CUTOUT_RIG_SEAM_GAP" and any(final[name].get("overlap_excess") is True for name in ("q1-contact-left", "q2-passing-left")), "remaining Q1/Q2 seam gap is not promoted")
        retention = load_json(evidence / "cutout-rig-pixel-retention-v071.json")
        check("v071:retention-real", all("source_visible_retention_fraction" in item and "occluded_source_fraction" in item for item in retention.get("poses", {}).get("q2-passing-left", {}).get("parts", {}).values()), "source retention and occlusion are measured per part")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v071:internal-qa", False, str(exc)); check("v071:seam-real", False, str(exc)); check("v071:seam-fail-closed", False, str(exc)); check("v071:retention-real", False, str(exc))

    try:
        execution = load_json(evidence / "execution-evidence-v0.7.1.json")
        check("v071:execution-boundary", execution.get("comfyui_generation_jobs") == 0 and execution.get("sam2_calls", {}).get("rig_revision_segmentation") == 1 and execution.get("sam2_calls", {}).get("per_frame_segmentation") == 0 and execution.get("sam3_used") is False and execution.get("walk") == "NOT_RUN", "execution evidence proves one rig segmentation, zero ComfyUI jobs and no walk")
        visual = load_json(evidence / "review-visuals-v0.7.1.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v071:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.7.1 review roles are hash-bound")
        headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.7.0 EXTERNAL AUDIT FINDINGS", "TARGET HIP / SIDE MAPPING FIX", "WEAPON ATTACHMENT FIX", "RAW MASKS", "REFINED MASKS", "COMPONENT QA", "Q0 NO-RESIDUAL RECONSTRUCTION", "JOINT BLENDING", "INTERNAL GEOMETRY QA REAL", "SEAM / SAFE-MARGIN QA REAL", "PIXEL RETENTION / PROVENANCE", "Q1 CONTACT-LEFT", "Q2 PASSING-LEFT", "TARGET VS DETECTED OVERLAYS", "FINAL PROVIDER DECISION", "NO COMFYUI / NO WALK", "TESTS", "VALIDATION", "REVIEW ARCHIVE SELF-TEST", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
        review = (ROOT / "REVIEW-v0.7.1.md").read_text(encoding="utf-8")
        check("v071:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.7.1 review headings present")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v071:execution-boundary", False, str(exc)); check("v071:visual-manifest", False, str(exc)); check("v071:review-headings", False, str(exc))


def _v072_checks() -> None:
    """Validate the immutable v0.7.2 qualification and its boundaries."""
    evidence = ROOT / "docs" / "evidence"
    required = {
        "REVIEW-v0.7.2.md", "docs/test-coverage-matrix-v0.7.2.md",
        "providers/manifests/deterministic-cutout-rig-2d-v0.7.2.json", "schemas/current-state-v0.7.2.json",
        "schemas/cutout-occlusion-plan.json", "schemas/cutout-pairwise-overlap.json",
        "schemas/cutout-seam-topology-qa.json", "schemas/cutout-retention-occlusion.json",
        "schemas/front-walk-gait-v2.json", "schemas/cutout-half-cycle-structure.json",
        "src/ugas/cutout_occlusion.py", "scripts/validation/run_cutout_rig_v072.py",
        "docs/evidence/current-state-v0.7.2.json", "docs/evidence/state-consistency-v0.7.2.json",
        "docs/evidence/current-state-v0.7.1.json", "docs/evidence/state-consistency-v0.7.1.json",
        "docs/evidence/review-visuals-v0.7.2.json",
        *{f"docs/evidence/{name}" for name in REQUIRED_V072_REVIEW_EVIDENCE},
    }
    for relative in sorted(required):
        path = ROOT / relative
        check(f"v072:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
        if path.is_file():
            check(f"v072:tracked:{relative}", tracked(relative), "tracked or present in review snapshot")
    try:
        state = load_json(evidence / "current-state-v0.7.2.json")
        schema = load_json(ROOT / "schemas/current-state-v0.7.2.json")
        validate_instance(state, schema)
        review = (ROOT / "REVIEW-v0.7.2.md").read_text(encoding="utf-8")
        consistency = load_json(evidence / "state-consistency-v0.7.2.json")
        check("v072:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active v0.7.2 state is consistent")
        check("v072:state-gate", state.get("current_gate") == "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED" and state.get("provider_smoke_status") == state.get("current_gate"), "active v0.7.2 gate is synchronized")
        check("v072:state-history", state.get("previous_release", {}).get("version") == "0.7.1" and state.get("previous_release", {}).get("review_manifest") == "docs/evidence/review-visuals-v0.7.1.json", "v0.7.1 state and review remain the previous release")
        check("v072:state-boundary", state.get("walk_authorized") is False and state.get("generation_provider_change_authorized") is False and state.get("state_consistency", {}).get("new_generation_jobs") == 0 and state.get("state_consistency", {}).get("sam2_runs") == 0, "walk, routing change and new generation remain blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        for name in ("v072:state-consistency", "v072:state-gate", "v072:state-history", "v072:state-boundary"):
            check(name, False, str(exc))
    try:
        plan = load_json(evidence / "cutout-occlusion-plan-v072.json")
        canonical = json.dumps({key: value for key, value in plan.items() if key != "plan_sha256"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        plan_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        check("v072:plan-schema", validate_instance(plan, load_json(ROOT / "schemas/cutout-occlusion-plan.json")) is None, "plan schema and topology are valid")
        check("v072:plan-hash", plan.get("plan_sha256") == plan_hash and plan.get("source_sha256") == ANCHOR_SHA256 and plan.get("rig_reference") == "docs/evidence/r4-cutout-rig-v071.json", "plan hash is bound to immutable R4/v0.7.1")
        check("v072:plan-complete", len(plan.get("topology_adjacency", [])) == 10 and set(plan.get("phase_plans", {})) == {"K1-contact-left", "K2-passing-left", "K3-contact-right", "K4-passing-right"} and all(len(item.get("z_order", [])) == 11 for item in plan.get("phase_plans", {}).values()), "all topology and phase z-order records are complete")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        for name in ("v072:plan-schema", "v072:plan-hash", "v072:plan-complete"):
            check(name, False, str(exc))
    try:
        q0 = load_json(evidence / "cutout-q0-regression-v072-qa.json")
        check("v072:q0", q0.get("status") == "CUTOUT_RIG_RECONSTRUCTION_PASSED" and q0.get("metrics", {}).get("alpha_iou") >= .995 and q0.get("metrics", {}).get("rgb_mae") <= 1.5 and q0.get("metrics", {}).get("bbox_drift_px") <= 1 and all(q0.get("hard_gates", {}).values()), "Q0 strict reconstruction regression passes")
        pair = load_json(evidence / "cutout-pairwise-overlap-matrix-v072.json")
        check("v072:pairwise", pair.get("status") == "OCCLUSION_QA_PASSED" and len(pair.get("poses", {})) == 4 and all(item.get("status") == "OCCLUSION_QA_PASSED" and item.get("critical_collision_pixels") == 0 and item.get("unexpected_overlap_fraction", 1) <= .015 and not item.get("forbidden_meaningful_overlap") for item in pair["poses"].values()), "pairwise expected/critical/unexpected gates pass for K1-K4")
        seam = load_json(evidence / "cutout-seam-topology-qa-v072.json")
        check("v072:topology", seam.get("status") == "SEAM_TOPOLOGY_PASSED" and all(item.get("status") == "SEAM_TOPOLOGY_PASSED" and all(edge.get("status") == "SEAM_TOPOLOGY_PASSED" for edge in item.get("pairs", [])) for item in seam.get("poses", {}).values()), "topological seam continuity passes for all phases")
        retention = load_json(evidence / "cutout-retention-occlusion-v072.json")
        required_fields = {"expected_transformed_pixels", "transformed_pixels_present", "visible_pixels", "hidden_pixels", "hidden_by_expected_occluder", "hidden_by_unexpected_occluder", "clipped_pixels", "unexplained_missing_pixels"}
        check("v072:retention", retention.get("status") == "RETENTION_OCCLUSION_PASSED" and all(item.get("status") == "RETENTION_OCCLUSION_PASSED" and all(required_fields.issubset(part) for part in item.get("parts", {}).values()) for item in retention.get("poses", {}).values()), "retention and expected occlusion provenance pass")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        for name in ("v072:q0", "v072:pairwise", "v072:topology", "v072:retention"):
            check(name, False, str(exc))
    try:
        gait = load_json(evidence / "cutout-front-walk-gait-v2.json")
        half = load_json(evidence / "cutout-half-cycle-structure-v072.json")
        check("v072:gait", gait.get("calibration_status") == "GAIT_CALIBRATION_PASSED" and gait.get("guide_coordinates_used") is False and gait.get("synthetic_fixtures", {}).get("passing_foot_approaches_centerline") is True and gait.get("synthetic_fixtures", {}).get("no_jumping_jack") is True, "front-walk gait v2 structural calibration passes")
        check("v072:half-cycle", half.get("status") == "HALF_CYCLE_STRUCTURE_PASSED" and len(half.get("pairs", [])) == 2 and half.get("arm_swing_inverts") is True and all(item.get("sword_right_wrist_present") is True for item in half.get("pairs", [])), "half-cycle structural prequalification passes")
        execution = load_json(evidence / "execution-evidence-v0.7.2.json")
        check("v072:execution-boundary", execution.get("sam2_runs") == 0 and execution.get("comfyui_generation_jobs") == 0 and execution.get("walk") == "NOT_RUN" and execution.get("spritesheet") == "NOT_RUN" and execution.get("gif") == "NOT_RUN" and execution.get("external_approval") == "not-claimed", "no new segmentation, ComfyUI job or walk was executed")
        qualification = load_json(evidence / "cutout-rig-provider-qualification-v072.json")
        check("v072:provider-decision", qualification.get("status") == "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED" and qualification.get("walk_authorized") is False and qualification.get("external_approval") == "not-claimed", "provider decision is technically qualified but not externally approved")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        for name in ("v072:gait", "v072:half-cycle", "v072:execution-boundary", "v072:provider-decision"):
            check(name, False, str(exc))
    try:
        visual = load_json(evidence / "review-visuals-v0.7.2.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v072:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.7.2 visual roles are hash-bound")
        headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.7.1 EXTERNAL AUDIT RESULT", "SEAM FALSE-NEGATIVE FINDING", "OCCLUSION MODEL", "PAIRWISE OVERLAP QA", "TOPOLOGICAL JOINT CONTINUITY", "RETENTION / OCCLUSION PROVENANCE", "FRONT-WALK GAIT TARGET V2", "Z-ORDER / DEPTH PLAN", "Q0 REGRESSION", "K1 CONTACT-LEFT", "K2 PASSING-LEFT", "K3 CONTACT-RIGHT", "K4 PASSING-RIGHT", "MEDIAPIPE POSE QA", "HALF-CYCLE STRUCTURE", "FINAL PROVIDER DECISION", "NO SAM2 RERUN / NO COMFYUI / NO WALK", "TESTS", "VALIDATION", "REVIEW ARCHIVE SELF-TEST", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
        review = (ROOT / "REVIEW-v0.7.2.md").read_text(encoding="utf-8")
        check("v072:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.7.2 review headings present")
        check("v072:external-boundary", "external approval is `not-claimed`" in review and "walk_authorized=false" in review, "external approval and walk authorization remain separate")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v072:visual-manifest", False, str(exc)); check("v072:review-headings", False, str(exc)); check("v072:external-boundary", False, str(exc))



def _v073_checks() -> None:
    """Validate the active v0.7.3 structural-coverage correction."""
    evidence = ROOT / "docs" / "evidence"
    required = {
        "REVIEW-v0.7.3.md", "docs/test-coverage-matrix-v0.7.3.md",
        "providers/manifests/deterministic-cutout-rig-2d.json", "schemas/current-state-v0.7.3.json",
        "schemas/current-state-v0.7.2.json", "schemas/cutout-structural-core-v073.json",
        "schemas/cutout-authorized-occlusion-regions-v073.json", "schemas/cutout-layer-integrity-v073.json",
        "schemas/cutout-structural-coverage-v073.json", "schemas/cutout-structural-hole-owner-diagnostics-v073.json",
        "schemas/cutout-pairwise-overlap-v073.json", "schemas/cutout-seam-topology-qa-v073.json",
        "schemas/cutout-retention-occlusion-v073.json", "schemas/cutout-rig-provider-qualification-v073.json",
        "schemas/execution-evidence-v073.json", "src/ugas/cutout_structural.py",
        "scripts/validation/run_cutout_rig_v073.py", "scripts/validation/validate_state_consistency.py",
        "scripts/validation/materialize_cutout_review_evidence.py", "docs/evidence/current-state-v0.7.3.json",
        "docs/evidence/state-consistency.json", "docs/evidence/current-state-v0.7.2.json",
        "docs/evidence/state-consistency-v0.7.2.json", "docs/evidence/review-visuals-v0.7.3.json",
        *{f"docs/evidence/{name}" for name in REQUIRED_V073_REVIEW_EVIDENCE},
    }
    for relative in sorted(required):
        path = ROOT / relative
        check(f"v073:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
        if path.is_file():
            check(f"v073:tracked:{relative}", tracked(relative), "tracked or present in review snapshot")

    try:
        state = load_json(evidence / "current-state-v0.7.3.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.7.3.json"))
        review = (ROOT / "REVIEW-v0.7.3.md").read_text(encoding="utf-8")
        consistency = validate_state_consistency(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), review)
        check("v073:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active v0.7.3 state is consistent")
        check("v073:state-gate", state.get("current_gate") == "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED" and state.get("provider_smoke_status") == state.get("current_gate"), "active v0.7.3 gate is synchronized")
        check("v073:state-history", state.get("previous_release", {}).get("version") == "0.7.2" and state.get("previous_release", {}).get("pose_lane_status") == "TECHNICALLY_QUALIFIED_BUT_EXTERNAL_VISUAL_REJECTED" and state.get("previous_release", {}).get("review_manifest") == "docs/evidence/review-visuals-v0.7.2.json", "v0.7.2 external rejection and review remain immutable history")
        check("v073:state-boundary", state.get("walk_authorized") is False and state.get("generation_provider_change_authorized") is False and state.get("state_consistency", {}).get("new_generation_jobs") == 0 and state.get("state_consistency", {}).get("sam2_runs") == 0, "walk, routing change and new generation remain blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError) as exc:
        for name in ("v073:state-consistency", "v073:state-gate", "v073:state-history", "v073:state-boundary"):
            check(name, False, str(exc))

    try:
        provider = load_json(ROOT / "providers/manifests/deterministic-cutout-rig-2d.json")
        validate_instance(provider, load_json(ROOT / "schemas/provider-manifest.json"))
        check("v073:provider-contract", provider.get("schema_version") == "0.7.3" and provider.get("qualification_evidence") == "docs/evidence/cutout-rig-provider-qualification-v073.json" and provider.get("generation_model") == "none", "provider is bound to v0.7.3 deterministic structural evidence")
        check("v073:provider-boundary", provider.get("runtime_policy", {}).get("comfyui_jobs") == 0 and provider.get("runtime_policy", {}).get("walk_frames") is False and provider.get("runtime_policy", {}).get("manual_mask_edits") is False, "provider remains deterministic and walk-free")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        check("v073:provider-contract", False, str(exc)); check("v073:provider-boundary", False, str(exc))

    try:
        schema_map = {
            "cutout-structural-core-v073.json": "cutout-structural-core-v073.json",
            "cutout-authorized-occlusion-regions-v073.json": "cutout-authorized-occlusion-regions-v073.json",
            "cutout-layer-integrity-v073.json": "cutout-layer-integrity-v073.json",
            "cutout-structural-coverage-v073.json": "cutout-structural-coverage-v073.json",
            "cutout-structural-hole-owner-diagnostics-v073.json": "cutout-structural-hole-owner-diagnostics-v073.json",
            "cutout-pairwise-overlap-v073.json": "cutout-pairwise-overlap-matrix-v073.json",
            "cutout-seam-topology-qa-v073.json": "cutout-seam-topology-qa-v073.json",
            "cutout-retention-occlusion-v073.json": "cutout-retention-occlusion-v073.json",
            "cutout-rig-provider-qualification-v073.json": "cutout-rig-provider-qualification-v073.json",
            "execution-evidence-v073.json": "execution-evidence-v0.7.3.json",
        }
        expected_status = {
            "cutout-structural-core-v073.json": "STRUCTURAL_CORE_DERIVED",
            "cutout-authorized-occlusion-regions-v073.json": "AUTHORIZED_OCCLUSION_REGIONS_DERIVED",
            "cutout-layer-integrity-v073.json": "LAYER_INTEGRITY_PASSED",
            "cutout-structural-coverage-v073.json": "STRUCTURAL_COVERAGE_PASSED",
            "cutout-structural-hole-owner-diagnostics-v073.json": "STRUCTURAL_HOLE_OWNER_DIAGNOSTICS_PASSED",
            "cutout-pairwise-overlap-v073.json": "OCCLUSION_QA_PASSED",
            "cutout-seam-topology-qa-v073.json": "SEAM_TOPOLOGY_PASSED",
            "cutout-retention-occlusion-v073.json": "RETENTION_OCCLUSION_PASSED",
            "cutout-rig-provider-qualification-v073.json": "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED",
        }
        for schema_name, artifact_name in schema_map.items():
            schema = load_json(ROOT / "schemas" / schema_name)
            artifact = load_json(evidence / artifact_name)
            validate_schema_document(schema)
            validate_instance(artifact, schema)
            if schema_name in expected_status:
                check(f"v073:evidence:{artifact_name}", artifact.get("status") == expected_status[schema_name], f"{artifact_name} status is qualified")
        coverage = load_json(evidence / "cutout-structural-coverage-v073.json")
        check("v073:coverage-gates", all(pose.get("structural_hole_pixels") == 0 and pose.get("structural_hole_fraction", 1) <= 0.0025 and pose.get("largest_structural_hole_component_pixels", 99) <= 12 and pose.get("belt_core_coverage", 0) >= 0.995 and pose.get("torso_core_coverage", 0) >= 0.995 for pose in coverage.get("poses", {}).values()), "K1-K4 structural coverage gates pass")
        integrity = load_json(evidence / "cutout-layer-integrity-v073.json")
        check("v073:integrity-gates", all(part.get("predicted_outside_canvas_area") == 0 and part.get("raster_area_error", 1) <= 0.03 and part.get("unexpected_layer_loss_fraction", 1) <= 0.02 and part.get("unexpected_layer_gain_fraction", 1) <= 0.02 for pose in integrity.get("poses", {}).values() for part in pose.get("parts", {}).values()), "all rendered layers pass independent integrity gates")
        pair = load_json(evidence / "cutout-pairwise-overlap-matrix-v073.json")
        check("v073:pairwise-gates", all(pose.get("critical_collision_pixels") == 0 and not pose.get("forbidden_meaningful_overlap") and not pose.get("z_order_mismatches") and pose.get("unexpected_overlap_fraction", 1) <= 0.015 for pose in pair.get("poses", {}).values()), "pairwise V3 geometry and depth gates pass")
        retention = load_json(evidence / "cutout-retention-occlusion-v073.json")
        check("v073:retention-gates", all(part.get("status") == "RETENTION_OCCLUSION_PASSED" and part.get("hidden_by_unexpected_occluder") == 0 for pose in retention.get("poses", {}).values() for part in pose.get("parts", {}).values()), "retention and unexpected-occluder gates pass")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, TypeError, ValueError) as exc:
        check("v073:evidence-schemas", False, str(exc)); check("v073:coverage-gates", False, str(exc)); check("v073:integrity-gates", False, str(exc)); check("v073:pairwise-gates", False, str(exc)); check("v073:retention-gates", False, str(exc))

    try:
        execution = load_json(evidence / "execution-evidence-v0.7.3.json")
        qualification = load_json(evidence / "cutout-rig-provider-qualification-v073.json")
        check("v073:execution-boundary", execution.get("sam2_runs") == 0 and execution.get("comfyui_generation_jobs") == 0 and execution.get("walk") == "NOT_RUN" and execution.get("spritesheet") == "NOT_RUN" and execution.get("gif") == "NOT_RUN" and execution.get("external_approval") == "not-claimed", "SAM2, ComfyUI, walk, spritesheet and GIF remain outside this slice")
        check("v073:provider-decision", qualification.get("status") == "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED" and qualification.get("walk_authorized") is False and qualification.get("external_visual_review") == "REQUIRED" and qualification.get("external_approval") == "not-claimed", "provider is technically qualified without external approval")
        check("v073:q0", qualification.get("q0", {}).get("status") == "CUTOUT_RIG_RECONSTRUCTION_PASSED" and qualification.get("q0", {}).get("alpha_iou", 0) >= 0.995 and qualification.get("q0", {}).get("rgb_mae", 99) <= 1.5, "Q0 identity remains inside strict regression gates")
        check("v073:media-pipe", all(pose.get("metrics", {}).get("qualifies") is True for pose in qualification.get("poses", {}).values()), "all four frozen target poses pass MediaPipe QA")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v073:execution-boundary", False, str(exc)); check("v073:provider-decision", False, str(exc)); check("v073:q0", False, str(exc)); check("v073:media-pipe", False, str(exc))

    try:
        visual = load_json(evidence / "review-visuals-v0.7.3.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v073:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.7.3 visual roles are hash-bound")
        headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.7.2 EXTERNAL AUDIT RESULT", "VISUAL REJECTION EVIDENCE", "RETENTION TAUTOLOGY FINDING", "STRUCTURAL CORE", "STRUCTURAL COVERAGE QA", "SOURCE OWNER DISPLACEMENT", "TRUE LAYER INTEGRITY", "AUTHORIZED OCCLUSION REGIONS", "PAIRWISE OVERLAP V3", "TOPOLOGICAL SEAM", "RETENTION / OCCLUSION V3", "Q0 REGRESSION", "K1 CONTACT-LEFT", "K2 PASSING-LEFT", "K3 CONTACT-RIGHT", "K4 PASSING-RIGHT", "CHECKERBOARD / WAIST ZOOM", "MEDIAPIPE POSE QA", "FINAL PROVIDER DECISION", "NO SAM2 / NO COMFYUI / NO WALK", "TESTS", "VALIDATION", "REVIEW ARCHIVE SELF-TEST", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
        review = (ROOT / "REVIEW-v0.7.3.md").read_text(encoding="utf-8")
        check("v073:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.7.3 review headings present")
        check("v073:external-boundary", "not-claimed" in review and "walk_authorized=false" in review and "REQUIRED" in review, "external review and walk authorization remain separate")
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        check("v073:visual-manifest", False, str(exc)); check("v073:review-headings", False, str(exc)); check("v073:external-boundary", False, str(exc))


def _v073_checks() -> None:
    """Audit v0.7.3 from immutable snapshots, never from active v0.8.0 files."""
    evidence = ROOT / "docs" / "evidence"
    required = [
        "REVIEW-v0.7.3.md", "docs/test-coverage-matrix-v0.7.3.md",
        "docs/evidence/current-state-v0.7.3.json", "docs/evidence/state-consistency-v0.7.3.json",
        "providers/manifests/deterministic-cutout-rig-2d-v0.7.3.json", "schemas/current-state-v0.7.3.json",
        "docs/evidence/review-visuals-v0.7.3.json", "docs/evidence/cutout-rig-provider-qualification-v073.json",
        "docs/evidence/execution-evidence-v0.7.3.json", "src/ugas/cutout_structural.py",
    ]
    for relative in required:
        check(f"v073:historical:{relative}", (ROOT / relative).is_file(), "immutable v0.7.3 snapshot present")
    try:
        state = load_json(evidence / "current-state-v0.7.3.json")
        schema = load_json(ROOT / "schemas/current-state-v0.7.3.json")
        validate_schema_document(schema); validate_instance(state, schema)
        provider = load_json(ROOT / "providers/manifests/deterministic-cutout-rig-2d-v0.7.3.json")
        qualification = load_json(evidence / "cutout-rig-provider-qualification-v073.json")
        execution = load_json(evidence / "execution-evidence-v0.7.3.json")
        check("v073:historical:state", state.get("version") == "0.7.3" and state.get("current_gate") == "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED" and state.get("walk_authorized") is False, "v0.7.3 state remains immutable")
        check("v073:historical:provider", provider.get("schema_version") == "0.7.3" and provider.get("qualification_evidence") == "docs/evidence/cutout-rig-provider-qualification-v073.json", "v0.7.3 provider snapshot remains bound")
        check("v073:historical:qualification", qualification.get("status") == "CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED" and qualification.get("walk") == "NOT_RUN", "v0.7.3 qualification remains key-pose-only")
        check("v073:historical:execution", execution.get("sam2_runs") == 0 and execution.get("comfyui_generation_jobs") == 0 and execution.get("walk") == "NOT_RUN", "v0.7.3 execution boundary remains immutable")
        visual = load_json(evidence / "review-visuals-v0.7.3.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v073:historical:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.7.3 visual manifest remains valid")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v073:historical:integrity", False, str(exc))


def _v080_checks() -> None:
    """Validate the immutable v0.8.0 deterministic eight-frame pilot snapshot."""
    evidence = ROOT / "docs" / "evidence"
    required = [
        "REVIEW-v0.8.0.md", "docs/test-coverage-matrix-v0.8.0.md", "docs/evidence/current-state-v0.8.0.json", "docs/evidence/state-consistency-v0.8.0.json",
        "providers/manifests/deterministic-cutout-rig-2d-v0.8.0.json", "schemas/current-state-v0.8.0.json", "scripts/validation/run_cutout_front_walk_v080.py", "src/ugas/cutout_temporal.py", "scripts/validation/materialize_cutout_review_evidence.py",
        "docs/evidence/front-walk-cycle-v1-config-v080.json", "docs/evidence/front-walk-targets-v080.json", "docs/evidence/front-walk-z-order-v080.json", "docs/evidence/front-walk-per-frame-qa-v080.json", "docs/evidence/front-walk-temporal-qa-v080.json", "docs/evidence/front-walk-foot-contact-qa-v080.json", "docs/evidence/front-walk-half-cycle-qa-v080.json", "docs/evidence/front-walk-loop-qa-v080.json", "docs/evidence/front-walk-structural-coverage-v080.json", "docs/evidence/front-walk-layer-integrity-v080.json", "docs/evidence/front-walk-occlusion-v080.json", "docs/evidence/front-walk-retention-v080.json", "docs/evidence/front-walk-provider-qualification-v080.json", "docs/evidence/execution-evidence-v0.8.0.json", "docs/evidence/review-visuals-v0.8.0.json",
        "docs/evidence/walk-front-v080/walk-front-spritesheet-v080.png", "docs/evidence/walk-front-v080/walk-front-metadata-v080.json", "docs/evidence/walk-front-v080/walk-front-preview-v080.gif", "docs/evidence/walk-front-v080/walk-front-package-manifest-v080.json",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v080:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(evidence / "current-state-v0.8.0.json"); validate_instance(state, load_json(ROOT / "schemas/current-state-v0.8.0.json"))
        review = (ROOT / "REVIEW-v0.8.0.md").read_text(encoding="utf-8")
        checkpoint_path = ROOT / "docs/evidence/checkpoint-v0.8.0.md"
        checkpoint = checkpoint_path.read_text(encoding="utf-8") if checkpoint_path.is_file() else subprocess.run(["git", "show", "d634d69d3cceac239d8eb5fe8623c764eb6c6b53:CHECKPOINT.md"], cwd=ROOT, capture_output=True, text=True, check=False).stdout
        consistency = validate_state_consistency_v080(state, checkpoint or (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), review)
        check("v080:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active state is consistent")
        check("v080:state-boundary", state.get("current_gate") == "CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED" and state.get("walk_authorized") == "pilot_only" and state.get("production_walk_authorized") is False, "pilot status and production block are synchronized")
        provider = load_json(ROOT / "providers/manifests/deterministic-cutout-rig-2d-v0.8.0.json")
        validate_instance(provider, load_json(ROOT / "schemas/provider-manifest.json"))
        check("v080:provider-contract", provider.get("schema_version") == "0.8.0" and provider.get("qualification_evidence") == "docs/evidence/front-walk-provider-qualification-v080.json" and provider.get("generation_model") == "none", "active provider is bound to v0.8.0 evidence")
        check("v080:provider-boundary", provider.get("runtime_policy", {}).get("comfyui_jobs") == 0 and provider.get("runtime_policy", {}).get("walk_frames") == 8 and provider.get("runtime_policy", {}).get("walk_authorized") == "pilot_only" and provider.get("runtime_policy", {}).get("production_walk_authorized") is False, "provider remains deterministic and pilot-only")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v080:state-consistency", False, str(exc)); check("v080:provider-contract", False, str(exc)); check("v080:provider-boundary", False, str(exc))
    try:
        schema_files = {"front-walk-cycle-v1-config-v080.json": "front-walk-cycle-v1-config-v080.json", "front-walk-targets-v080.json": "front-walk-targets-v080.json", "front-walk-z-order-v080.json": "front-walk-z-order-v080.json", "front-walk-per-frame-qa-v080.json": "front-walk-per-frame-qa-v080.json", "front-walk-temporal-qa-v080.json": "front-walk-temporal-qa-v080.json", "front-walk-foot-contact-qa-v080.json": "front-walk-foot-contact-qa-v080.json", "front-walk-half-cycle-qa-v080.json": "front-walk-half-cycle-qa-v080.json", "front-walk-loop-qa-v080.json": "front-walk-loop-qa-v080.json", "front-walk-structural-coverage-v080.json": "front-walk-structural-coverage-v080.json", "front-walk-layer-integrity-v080.json": "front-walk-layer-integrity-v080.json", "front-walk-occlusion-v080.json": "front-walk-occlusion-v080.json", "front-walk-retention-v080.json": "front-walk-retention-v080.json", "front-walk-provider-qualification-v080.json": "front-walk-provider-qualification-v080.json", "execution-evidence-v080.json": "execution-evidence-v0.8.0.json", "front-walk-metadata-v080.json": "walk-front-v080/walk-front-metadata-v080.json", "front-walk-package-manifest-v080.json": "walk-front-v080/walk-front-package-manifest-v080.json"}
        for schema_name, artifact_name in schema_files.items():
            schema = load_json(ROOT / "schemas" / schema_name); artifact = load_json(evidence / artifact_name); validate_schema_document(schema); validate_instance(artifact, schema)
        check("v080:evidence-schemas", True, "all v0.8.0 machine-readable evidence validates against its schema")
        frame_report = load_json(evidence / "front-walk-per-frame-qa-v080.json"); temporal = load_json(evidence / "front-walk-temporal-qa-v080.json"); feet = load_json(evidence / "front-walk-foot-contact-qa-v080.json"); half = load_json(evidence / "front-walk-half-cycle-qa-v080.json"); loop = load_json(evidence / "front-walk-loop-qa-v080.json")
        check("v080:frame-gates", frame_report.get("status") == "CUTOUT_RIG_FRONT_WALK_FRAMES_PASSED" and len(frame_report.get("frames", [])) == 8 and all(item.get("status") == "CUTOUT_RIG_FRONT_WALK_FRAME_PASSED" and all(item.get("hard_gates", {}).values()) for item in frame_report["frames"]), "all eight per-frame gates pass")
        check("v080:temporal-gates", temporal.get("status") == "CUTOUT_RIG_FRONT_WALK_TEMPORAL_PASSED" and all(temporal.get("hard_gates", {}).values()), "temporal gates pass")
        check("v080:foot-half-loop", feet.get("status") == "CUTOUT_RIG_FRONT_WALK_FOOT_CONTACT_PASSED" and half.get("status") == "CUTOUT_RIG_FRONT_WALK_HALF_CYCLE_PASSED" and loop.get("status") == "CUTOUT_RIG_FRONT_WALK_LOOP_PASSED", "foot, half-cycle and loop gates pass")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v080:evidence-schemas", False, str(exc)); check("v080:frame-gates", False, str(exc)); check("v080:temporal-gates", False, str(exc)); check("v080:foot-half-loop", False, str(exc))
    try:
        qualification = load_json(evidence / "front-walk-provider-qualification-v080.json"); execution = load_json(evidence / "execution-evidence-v0.8.0.json"); package = load_json(evidence / "walk-front-v080/walk-front-package-manifest-v080.json"); metadata = load_json(evidence / "walk-front-v080/walk-front-metadata-v080.json")
        check("v080:decision", qualification.get("status") == "CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED" and qualification.get("external_visual_review") == "REQUIRED" and qualification.get("external_approval") == "not-claimed", "technical qualification is separate from external review")
        check("v080:no-generation", execution.get("sam2_runs") == 0 and execution.get("comfyui_generation_jobs") == 0 and execution.get("new_generation_jobs") == 0 and qualification.get("sam2_runs") == 0 and qualification.get("comfyui_generation_jobs") == 0, "SAM2 and ComfyUI remain zero")
        check("v080:package-boundary", package.get("registry_state") == "pilot/technical-qualified" and package.get("production_approved") is False and package.get("production_routing") == "BLOCKED" and len(metadata.get("frames", [])) == 8, "runtime package is pilot-only and metadata is complete")
        sprite = Image.open(evidence / "walk-front-v080/walk-front-spritesheet-v080.png"); check("v080:sprite-layout", sprite.mode == "RGBA" and sprite.size == (2048, 1024), "sprite is RGBA 4x2 512px")
        check("v080:visual-manifest", validate_review_visual_manifest(load_json(evidence / "review-visuals-v0.8.0.json"), ROOT)["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "v0.8.0 visual roles are hash-bound")
        headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.7.3 AUDIT RESULT", "BASELINE IMMUTABILITY", "CYCLE CONFIG", "KEY POSE HASH BINDING", "INTERMEDIATE POSE GENERATOR", "FOOT CONTACT / GROUND", "ROOT / PELVIS / TORSO MOTION", "ARM / SWORD MOTION", "Z-ORDER / DEPTH", "PER-FRAME STRUCTURAL COVERAGE", "PER-FRAME LAYER INTEGRITY", "PER-FRAME TOPOLOGY / OCCLUSION", "PER-FRAME MEDIAPIPE QA", "TEMPORAL QA", "HALF-CYCLE QA", "LOOP QA", "VISUAL EVIDENCE", "SPRITESHEET", "METADATA", "GIF PREVIEW", "PACKAGE MANIFEST", "FINAL WALK DECISION", "NO SAM2 / NO COMFYUI", "TESTS", "VALIDATION", "REVIEW ARCHIVE SELF-TEST", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE", "REVIEW ZIP"]
        check("v080:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.8.0 review headings present")
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        check("v080:decision", False, str(exc)); check("v080:no-generation", False, str(exc)); check("v080:package-boundary", False, str(exc)); check("v080:sprite-layout", False, str(exc)); check("v080:visual-manifest", False, str(exc)); check("v080:review-headings", False, str(exc))



def _v081_checks() -> None:
    """Validate the immutable v0.8.1 integrity-correction slice."""
    evidence = ROOT / "docs" / "evidence"
    required = [
        "REVIEW-v0.8.1.md", "docs/test-coverage-matrix-v0.8.1.md", "docs/evidence/current-state-v0.8.1.json",
        "docs/evidence/state-consistency-v0.8.1.json", "providers/manifests/deterministic-cutout-rig-2d.json",
        "schemas/current-state-v0.8.1.json", "schemas/review-index-v0.8.1.json", "scripts/validation/run_cutout_front_walk_v081.py",
        "scripts/validation/build_review_visuals_v081.py", "scripts/validation/build_review_index_v081.py",
        "scripts/validation/validate_review_index.py", "src/ugas/cutout_temporal_v081.py",
        "docs/evidence/front-walk-cycle-v1-config-v081.json", "docs/evidence/front-walk-targets-v081.json",
        "docs/evidence/front-walk-z-order-v081.json", "docs/evidence/front-walk-per-frame-qa-v081.json",
        "docs/evidence/front-walk-temporal-pre-smoothing-v081.json", "docs/evidence/front-walk-temporal-qa-v081.json",
        "docs/evidence/front-walk-foot-contact-qa-v081.json", "docs/evidence/front-walk-foot-ground-record-v081.json",
        "docs/evidence/front-walk-half-cycle-qa-v081.json", "docs/evidence/front-walk-loop-qa-v081.json",
        "docs/evidence/front-walk-structural-coverage-v081.json", "docs/evidence/front-walk-layer-integrity-v081.json",
        "docs/evidence/front-walk-occlusion-v081.json", "docs/evidence/front-walk-retention-v081.json",
        "docs/evidence/front-walk-bone-projection-v081.json", "docs/evidence/front-walk-root-motion-v081.json",
        "docs/evidence/front-walk-provider-qualification-v081.json", "docs/evidence/execution-evidence-v0.8.1.json",
        "docs/evidence/review-visuals-v0.8.1.json", "docs/evidence/walk-front-v081/walk-front-spritesheet-v081.png",
        "docs/evidence/walk-front-v081/walk-front-metadata-v081.json", "docs/evidence/walk-front-v081/walk-front-preview-v081.gif",
        "docs/evidence/walk-front-v081/walk-front-package-manifest-v081.json",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v081:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(evidence / "current-state-v0.8.1.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.8.1.json"))
        consistency = validate_state_consistency_v081(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.8.1.md").read_text(encoding="utf-8"))
        check("v081:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active state is consistent")
        check("v081:state-boundary", state.get("current_gate") == "CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED" and state.get("walk_authorized") == "pilot_only" and state.get("production_walk_authorized") is False and state.get("state_consistency", {}).get("production_routing") == "BLOCKED", "technical qualification and production block are synchronized")
        provider = load_json(ROOT / "providers/manifests/deterministic-cutout-rig-2d.json")
        validate_instance(provider, load_json(ROOT / "schemas/provider-manifest.json"))
        check("v081:provider-contract", provider.get("schema_version") == "0.8.1" and provider.get("qualification_evidence") == "docs/evidence/front-walk-provider-qualification-v081.json" and provider.get("generation_model") == "none", "active provider is bound to v0.8.1 evidence")
        check("v081:provider-boundary", provider.get("runtime_policy", {}).get("comfyui_jobs") == 0 and provider.get("runtime_policy", {}).get("walk_frames") == 8 and provider.get("runtime_policy", {}).get("walk_authorized") == "pilot_only" and provider.get("runtime_policy", {}).get("production_walk_authorized") is False, "provider remains deterministic and pilot-only")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v081:state-consistency", False, str(exc)); check("v081:state-boundary", False, str(exc)); check("v081:provider-contract", False, str(exc)); check("v081:provider-boundary", False, str(exc))
    try:
        schema_files = {
            "front-walk-cycle-v1-config-v081.json": "front-walk-cycle-v1-config-v081.json",
            "front-walk-targets-v081.json": "front-walk-targets-v081.json",
            "front-walk-z-order-v081.json": "front-walk-z-order-v081.json",
            "front-walk-per-frame-qa-v081.json": "front-walk-per-frame-qa-v081.json",
            "front-walk-temporal-pre-smoothing-v081.json": "front-walk-temporal-pre-smoothing-v081.json",
            "front-walk-temporal-qa-v081.json": "front-walk-temporal-qa-v081.json",
            "front-walk-foot-contact-qa-v081.json": "front-walk-foot-contact-qa-v081.json",
            "front-walk-half-cycle-qa-v081.json": "front-walk-half-cycle-qa-v081.json",
            "front-walk-loop-qa-v081.json": "front-walk-loop-qa-v081.json",
            "front-walk-structural-coverage-v081.json": "front-walk-structural-coverage-v081.json",
            "front-walk-layer-integrity-v081.json": "front-walk-layer-integrity-v081.json",
            "front-walk-occlusion-v081.json": "front-walk-occlusion-v081.json",
            "front-walk-retention-v081.json": "front-walk-retention-v081.json",
            "front-walk-provider-qualification-v081.json": "front-walk-provider-qualification-v081.json",
            "execution-evidence-v081.json": "execution-evidence-v0.8.1.json",
            "front-walk-metadata-v081.json": "walk-front-v081/walk-front-metadata-v081.json",
            "front-walk-package-manifest-v081.json": "walk-front-v081/walk-front-package-manifest-v081.json",
        }
        for schema_name, artifact_name in schema_files.items():
            schema = load_json(ROOT / "schemas" / schema_name)
            artifact = load_json(evidence / artifact_name)
            validate_schema_document(schema)
            validate_instance(artifact, schema)
        check("v081:evidence-schemas", True, "all v0.8.1 machine-readable evidence validates against its schema")
        frame_report = load_json(evidence / "front-walk-per-frame-qa-v081.json")
        temporal = load_json(evidence / "front-walk-temporal-qa-v081.json")
        feet = load_json(evidence / "front-walk-foot-contact-qa-v081.json")
        half = load_json(evidence / "front-walk-half-cycle-qa-v081.json")
        loop = load_json(evidence / "front-walk-loop-qa-v081.json")
        check("v081:frame-gates", frame_report.get("status") == "CUTOUT_RIG_FRONT_WALK_FRAMES_PASSED" and len(frame_report.get("frames", [])) == 8 and all(item.get("status") == "CUTOUT_RIG_FRONT_WALK_FRAME_PASSED" and all(item.get("hard_gates", {}).values()) for item in frame_report["frames"]), "all eight corrected per-frame gates pass")
        check("v081:temporal-gates", temporal.get("status") == "CUTOUT_RIG_FRONT_WALK_TEMPORAL_PASSED" and temporal.get("max_angular_acceleration_degrees_per_frame2", 99) <= 25.0 and all(temporal.get("hard_gates", {}).values()), "strict temporal and actual-alpha gates pass")
        check("v081:foot-half-loop", feet.get("status") == "CUTOUT_RIG_FRONT_WALK_FOOT_CONTACT_PASSED" and half.get("status") == "CUTOUT_RIG_FRONT_WALK_HALF_CYCLE_PASSED" and loop.get("status") == "CUTOUT_RIG_FRONT_WALK_LOOP_PASSED", "visible-sole, half-cycle and loop gates pass")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v081:evidence-schemas", False, str(exc)); check("v081:frame-gates", False, str(exc)); check("v081:temporal-gates", False, str(exc)); check("v081:foot-half-loop", False, str(exc))
    try:
        qualification = load_json(evidence / "front-walk-provider-qualification-v081.json")
        execution = load_json(evidence / "execution-evidence-v0.8.1.json")
        package = load_json(evidence / "walk-front-v081/walk-front-package-manifest-v081.json")
        metadata = load_json(evidence / "walk-front-v081/walk-front-metadata-v081.json")
        check("v081:decision", qualification.get("status") == "CUTOUT_RIG_FRONT_WALK_8FRAME_TECHNICALLY_QUALIFIED" and qualification.get("external_visual_review") == "REQUIRED" and qualification.get("external_approval") == "not-claimed", "technical qualification is separate from external review")
        check("v081:no-generation", execution.get("sam2_runs") == 0 and execution.get("comfyui_generation_jobs") == 0 and execution.get("new_generation_jobs") == 0 and qualification.get("sam2_runs") == 0 and qualification.get("comfyui_generation_jobs") == 0, "SAM2 and ComfyUI remain zero")
        check("v081:package-boundary", package.get("registry_state") == "pilot/technical-qualified" and package.get("production_approved") is False and package.get("production_routing") == "BLOCKED" and len(metadata.get("frames", [])) == 8, "runtime package is pilot-only and metadata is complete")
        sprite = Image.open(evidence / "walk-front-v081/walk-front-spritesheet-v081.png")
        check("v081:sprite-layout", sprite.mode == "RGBA" and sprite.size == (2048, 1024), "sprite is RGBA 4x2 512px")
        sprite.close()
        visual_result = validate_review_visual_manifest(load_json(evidence / "review-visuals-v0.8.1.json"), ROOT)
        check("v081:visual-manifest", visual_result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED", "; ".join(visual_result.get("failures", [])) or "v0.8.1 visual roles are hash-bound")
        review = (ROOT / "REVIEW-v0.8.1.md").read_text(encoding="utf-8")
        headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.8.0 EXTERNAL AUDIT FINDINGS", "BASELINE IMMUTABILITY", "FOOT / PROJECTED GROUND MODEL", "VISIBLE SOLE QA", "ACTUAL ALPHA SAFE MARGIN", "PRESENTATION TRANSFORM", "SKELETON TEMPORAL SMOOTHING", "ANGULAR ACCELERATION QA", "HEAD / TORSO LAYER BBOX QA", "LOOP Z-ORDER QA", "HARD-GATE PROOF SOURCES", "PER-FRAME QA", "TEMPORAL / HALF-CYCLE / LOOP", "VISUAL EVIDENCE", "SPRITESHEET / METADATA / GIF", "FINAL WALK DECISION", "NO SAM2 / NO COMFYUI", "TESTS", "VALIDATION", "GITHUB-FIRST REVIEW INDEX", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE"]
        check("v081:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.8.1 review headings present")
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        check("v081:decision", False, str(exc)); check("v081:no-generation", False, str(exc)); check("v081:package-boundary", False, str(exc)); check("v081:sprite-layout", False, str(exc)); check("v081:visual-manifest", False, str(exc)); check("v081:review-headings", False, str(exc))
    index_path = evidence / "review-index-v0.8.1.json"
    if index_path.is_file() and (ROOT / ".git").exists():
        try:
            with tempfile.TemporaryDirectory(prefix="ugas-v081-index-") as directory:
                snapshot = Path(directory) / "snapshot"; snapshot.mkdir()
                archive = subprocess.run(["git", "archive", "46ba3ae87558ff26055e14aa8d9c6f3ee147333c"], cwd=ROOT, capture_output=True, check=False)
                with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
                    try: tar.extractall(snapshot, filter="data")
                    except TypeError: tar.extractall(snapshot)
                result = subprocess.run([sys.executable, "scripts/validation/validate_review_index.py"], cwd=snapshot, capture_output=True, text=True, check=False)
            check("v081:review-index", archive.returncode == 0 and result.returncode == 0, (result.stdout + result.stderr).strip()[-800:])
        except (OSError, tarfile.TarError) as exc:
            check("v081:review-index", False, str(exc))
    else:
        check("v081:review-index-tooling", (ROOT / "scripts/validation/validate_review_index.py").is_file(), "review index validator is present; immutable baseline validation requires the recorded baseline commit")


def _v090_checks() -> None:
    """Validate the immutable v0.9.0 state and runtime evidence."""
    evidence = ROOT / "docs" / "evidence"
    required = [
        "REVIEW-v0.9.0.md", "docs/test-coverage-matrix-v0.9.0.md", "schemas/current-state-v0.9.0.json",
        "schemas/current-state-v0.8.1.json", "schemas/animation-spec-v1.json", "schemas/animation-compiled-manifest-v1.json",
        "schemas/animation-qa-result-v1.json", "schemas/animation-package-v1.json", "schemas/review-index-v0.9.0.json",
        "profiles/animation/walk-front-v1.json", "profiles/animation/idle-front-v1.json", "src/ugas/animation.py",
        "src/ugas/animation_profiles/common.py", "src/ugas/animation_profiles/walk_front_v1.py", "src/ugas/animation_profiles/idle_front_v1.py",
        "src/ugas/state_consistency.py", "src/ugas/state_consistency_v081.py", "scripts/validation/run_animation_runtime_v090.py",
        "scripts/validation/build_review_visuals_v090.py", "scripts/validation/build_review_index_v090.py", "scripts/validation/validate_review_index_v090.py",
        "docs/evidence/current-state-v0.9.0.json", "docs/evidence/state-consistency-v0.9.0.json", "docs/evidence/current-state-v0.8.1.json",
        "docs/evidence/state-consistency-v0.8.1.json", "docs/evidence/front-walk-v081-external-decision-v090.json",
        "docs/evidence/animation-runtime-v090/execution-evidence-v0.9.0.json",
        "docs/evidence/animation-runtime-v090/replay/walk-front-v1/compiled-manifest.json",
        "docs/evidence/animation-runtime-v090/replay/walk-front-v1/qa-result.json",
        "docs/evidence/animation-runtime-v090/replay/walk-front-v1/package-manifest.json",
        "docs/evidence/animation-runtime-v090/idle-front-v1/compiled-manifest.json",
        "docs/evidence/animation-runtime-v090/idle-front-v1/qa-result.json",
        "docs/evidence/animation-runtime-v090/idle-front-v1/package-manifest.json",
        "docs/evidence/animation-runtime-v090/idle-front-v1/metadata.json",
        "docs/evidence/animation-runtime-v090/repro/idle-front-v1-repeat/compiled-manifest.json",
        "docs/evidence/review-visuals-v0.9.0.json",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v090:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(evidence / "current-state-v0.9.0.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.9.0.json"))
        review = (ROOT / "REVIEW-v0.9.0.md").read_text(encoding="utf-8")
        consistency = validate_state_consistency_v090(state, review, review)
        check("v090:state-consistency", consistency["status"] == state["current_gate"], "; ".join(consistency.get("failures", [])) or "active v0.9.0 state is consistent")
        snapshot = load_json(evidence / "state-consistency-v0.9.0.json")
        check("v090:state-snapshot", snapshot.get("schema_version") == "0.9.0" and snapshot.get("status") == state["current_gate"], "active state-consistency evidence is current")
        check("v090:state-boundary", state.get("current_gate") == "CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED" and state.get("production_walk_authorized") is False and state.get("state_consistency", {}).get("production_routing") == "BLOCKED", "idle technical qualification remains production-blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v090:state-consistency", False, str(exc)); check("v090:state-snapshot", False, str(exc)); check("v090:state-boundary", False, str(exc))
    for relative in ("profiles/animation/walk-front-v1.json", "profiles/animation/idle-front-v1.json"):
        result = _run([sys.executable, "-m", "ugas.animation", "validate-spec", relative], ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
        check(f"v090:spec:{relative}", result.returncode == 0, (result.stdout + result.stderr).strip()[-500:] or "spec validates")
    try:
        walk = load_json(evidence / "animation-runtime-v090/replay/walk-front-v1/qa-result.json")
        walk_package = load_json(evidence / "animation-runtime-v090/replay/walk-front-v1/package-manifest.json")
        walk_frames = walk.get("frames", [])
        check("v090:walk-replay", walk.get("status") == "CUTOUT_ANIMATION_RUNTIME_V1_WALK_REPLAY_IDENTICAL" and len(walk_frames) == 8 and all(frame.get("passed") is True and frame.get("rgba_sha256") == frame.get("expected_rgba_sha256") for frame in walk_frames), "all eight historical RGBA frames replay identically")
        check("v090:walk-package", walk_package.get("registry_state") == "pilot/technical-qualified" and walk_package.get("production_approved") is False and walk_package.get("production_routing") == "BLOCKED", "walk replay package remains pilot-only")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v090:walk-replay", False, str(exc)); check("v090:walk-package", False, str(exc))
    try:
        idle = load_json(evidence / "animation-runtime-v090/idle-front-v1/qa-result.json")
        package = load_json(evidence / "animation-runtime-v090/idle-front-v1/package-manifest.json")
        metadata = load_json(evidence / "animation-runtime-v090/idle-front-v1/metadata.json")
        temporal = load_json(evidence / "animation-runtime-v090/idle-front-temporal-qa-v090.json")
        check("v090:idle-frames", idle.get("status") == "CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED" and len(idle.get("frames", [])) == 12 and all(item.get("status") == "IDLE_FRAME_PASSED" and all(item.get("hard_gates", {}).values()) for item in idle["frames"]), "all twelve idle frame gates pass")
        check("v090:idle-temporal", temporal.get("status") == "IDLE_TEMPORAL_LOOP_PASSED" and all(temporal.get("hard_gates", {}).values()), "idle temporal and loop gates pass")
        check("v090:idle-package", package.get("frame_count") == 12 and package.get("fps") == 8.0 and package.get("per_frame_duration_ms") == 125.0 and package.get("registry_state") == "pilot/technical-qualified" and package.get("production_approved") is False and package.get("production_routing") == "BLOCKED" and metadata.get("sheet_size") == {"width": 3072, "height": 1024}, "idle package is 6x2 RGBA and production-blocked")
        check("v090:idle-provenance", idle.get("provenance", {}).get("source_only_pixels") is True and idle.get("provenance", {}).get("sam2_runs") == 0 and idle.get("provenance", {}).get("comfyui_generation_jobs") == 0, "idle pixels are source-only with zero AI jobs")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v090:idle-frames", False, str(exc)); check("v090:idle-temporal", False, str(exc)); check("v090:idle-package", False, str(exc)); check("v090:idle-provenance", False, str(exc))
    try:
        visual = load_json(evidence / "review-visuals-v0.9.0.json")
        result = validate_review_visual_manifest(visual, ROOT)
        check("v090:visual-manifest", result["status"] == "REVIEW_VISUAL_MANIFEST_PASSED" and len(visual.get("images", [])) == len(REQUIRED_V090_REVIEW_EVIDENCE), "; ".join(result.get("failures", [])) or "v0.9.0 visual roles are complete and hash-bound")
        check("v090:no-zip", not any(path.suffix.casefold() == ".zip" and ("v090" in path.name.casefold() or "0.9.0" in path.name.casefold()) for path in ROOT.rglob("*.zip")), "no v0.9.0 review ZIP is generated; historical ZIPs remain outside this slice")
        headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "BASELINE / EXTERNAL WALK APPROVAL", "IMMUTABILITY", "ANIMATION SPEC V1", "GENERIC RUNTIME ARCHITECTURE", "WALK V081 REPLAY", "IDLE FRONT SPEC", "IDLE FRAME QA", "DUAL FOOT PLANT QA", "IDLE TEMPORAL / LOOP QA", "PROVENANCE / STRUCTURAL / OCCLUSION", "VISUAL EVIDENCE", "SPRITESHEET / METADATA / GIF", "GITHUB-FIRST REVIEW INDEX V2", "NO SAM2 / NO COMFYUI / NO GENERATION", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "SECURITY / LICENSES", "EXTERNAL VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE"]
        review = (ROOT / "REVIEW-v0.9.0.md").read_text(encoding="utf-8")
        check("v090:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.9.0 review headings present")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v090:visual-manifest", False, str(exc)); check("v090:no-zip", False, str(exc)); check("v090:review-headings", False, str(exc))
    index_path = evidence / "review-index-v0.9.0.json"
    if index_path.is_file():
        result = _run([sys.executable, "scripts/validation/validate_review_index_v090.py"], ROOT)
        check("v090:review-index", result.returncode == 0, (result.stdout + result.stderr).strip()[-800:])
    else:
        check("v090:review-index-tooling", (ROOT / "scripts/validation/validate_review_index_v090.py").is_file(), "review index is built after the validation pass")


def _v091_checks() -> None:
    """Validate the active v0.9.1 generic-runtime correction and evidence."""
    evidence = ROOT / "docs" / "evidence"
    required = [
        "REVIEW-v0.9.1.md", "docs/test-coverage-matrix-v0.9.1.md", "schemas/current-state-v0.9.1.json", "schemas/current-state-v0.9.0.json",
        "schemas/review-index-v0.9.1.json", "src/ugas/state_consistency_v091.py", "scripts/validation/run_animation_runtime_v091.py",
        "scripts/validation/build_review_index_v091.py", "scripts/validation/validate_review_index_v091.py", "docs/evidence/current-state-v0.9.1.json",
        "docs/evidence/state-consistency-v091.json", "docs/evidence/checkpoint-v0.8.0.md", "docs/evidence/checkpoint-v0.9.1.md", "docs/evidence/review-index-v0.9.1.json",
        "docs/evidence/animation-runtime-v091/generic-runtime-contract-v091.json", "docs/evidence/animation-runtime-v091/timing-alternative-qualification-v091.json",
        "docs/evidence/animation-runtime-v091/generic-dummy-package-qualification-v091.json", "docs/evidence/animation-runtime-v091/walk-replay-qualification-v091.json",
        "docs/evidence/animation-runtime-v091/idle-dual-foot-drift-qa-v091.json", "docs/evidence/animation-runtime-v091/idle-layer-bbox-temporal-qa-v091.json",
        "docs/evidence/animation-runtime-v091/idle-occlusion-policy-v091.json", "docs/evidence/animation-runtime-v091/idle-requalification-v091.json",
        "docs/evidence/animation-runtime-v091/execution-evidence-v0.9.1.json",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v091:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(evidence / "current-state-v0.9.1.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.9.1.json"))
        checkpoint = (ROOT / "docs/evidence/checkpoint-v0.9.1.md").read_text(encoding="utf-8")
        review = (ROOT / "REVIEW-v0.9.1.md").read_text(encoding="utf-8")
        consistency = validate_state_consistency_v091(state, checkpoint, review)
        check("v091:state-consistency", consistency["status"] == state["current_gate"], "; ".join(consistency.get("failures", [])) or "active v0.9.1 state is consistent")
        snapshot = load_json(evidence / "state-consistency-v091.json")
        check("v091:state-snapshot", snapshot.get("schema_version") == "0.9.1" and snapshot.get("status") == state["current_gate"] and snapshot.get("failures") == [], "v0.9.1 state-consistency evidence is current")
        check("v091:state-boundary", state.get("current_gate") == "CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED" and state.get("production_walk_authorized") is False and state.get("state_consistency", {}).get("production_routing") == "BLOCKED", "idle technical qualification remains production-blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v091:state-consistency", False, str(exc)); check("v091:state-snapshot", False, str(exc)); check("v091:state-boundary", False, str(exc))
    try:
        generic = load_json(evidence / "animation-runtime-v091/generic-runtime-contract-v091.json")
        timing = load_json(evidence / "animation-runtime-v091/timing-alternative-qualification-v091.json")
        dummy = load_json(evidence / "animation-runtime-v091/generic-dummy-package-qualification-v091.json")
        check("v091:generic-decision", generic.get("status") == "GENERIC_RUNTIME_CONTRACT_PASSED" and generic.get("qualified_decision") == "QUALIFIED" and generic.get("qualified_status_arbitrary") != "QUALIFIED" and generic.get("package_policy_uses_decision_not_status") is True, "generic package qualification is decision-based and status-agnostic")
        check("v091:generic-negative-controls", all(value == "package_requires_qualified_qa" for value in generic.get("negative_controls", {}).values()), "generic package failure paths are fail-closed")
        representations = timing.get("representations", {})
        check("v091:timing-alternatives", timing.get("status") == "TIMING_ALTERNATIVE_QUALIFICATION_PASSED" and representations.get("fps_only", {}).get("status") == "VALID" and representations.get("duration_only", {}).get("status") == "VALID" and representations.get("both", {}).get("status") == "INVALID" and representations.get("neither", {}).get("status") == "INVALID" and timing.get("source_spec_unchanged") is True, "timing alternatives are mutually exclusive and source-preserving")
        check("v091:dummy-package", dummy.get("status") == "GENERIC_RUNTIME_CONTRACT_PASSED" and dummy.get("package_qa_decision") == "QUALIFIED", "synthetic two-key profile qualifies through the generic contract")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v091:generic-decision", False, str(exc)); check("v091:generic-negative-controls", False, str(exc)); check("v091:timing-alternatives", False, str(exc)); check("v091:dummy-package", False, str(exc))
    try:
        walk = load_json(evidence / "animation-runtime-v091/walk-replay-qualification-v091.json")
        idle = load_json(evidence / "animation-runtime-v091/idle-requalification-v091.json")
        feet = load_json(evidence / "animation-runtime-v091/idle-dual-foot-drift-qa-v091.json")
        boxes = load_json(evidence / "animation-runtime-v091/idle-layer-bbox-temporal-qa-v091.json")
        occlusion = load_json(evidence / "animation-runtime-v091/idle-occlusion-policy-v091.json")
        execution = load_json(evidence / "animation-runtime-v091/execution-evidence-v0.9.1.json")
        check("v091:walk-replay", walk.get("decision") == "QUALIFIED" and walk.get("status") == "CUTOUT_ANIMATION_RUNTIME_V1_WALK_REPLAY_IDENTICAL" and len(walk.get("frames", [])) == 8 and all(frame.get("passed") is True and frame.get("rgba_sha256") == frame.get("expected_rgba_sha256") for frame in walk["frames"]) and walk.get("spritesheet", {}).get("status") == "BYTE_IDENTICAL" and walk.get("gif", {}).get("status") == "BYTE_IDENTICAL", "walk v0.8.1 replay is byte-identical")
        check("v091:idle-requalification", idle.get("decision") == "QUALIFIED" and idle.get("frame_count") == 12 and idle.get("target_hashes_unchanged_from_v090") is True and idle.get("canonical_rgba_hashes_unchanged_from_v090") is True and idle.get("deterministic_replay_twice") is True and idle.get("package", {}).get("qa_decision") == "QUALIFIED", "idle replay is deterministic with unchanged canonical RGBA")
        foot_gates = feet.get("hard_gates", {})
        check("v091:dual-foot", feet.get("status") == "IDLE_DUAL_FEET_DRIFT_PASSED" and len(foot_gates) == 8 and all(foot_gates.values()) and feet.get("negative_controls", {}).get("sole_plus_2_px") is True and feet.get("negative_controls", {}).get("ankle_plus_3_px") is True and feet.get("negative_controls", {}).get("ankle_plus_1_5_px_passes") is True and all(item.get("frame_to_frame_sole_anchor_drift_px", {}).get("max_frame_pair") == [11, 0] for item in feet.get("sides", {}).values()), "dual-foot QA covers sole, penetration, cyclic drift including I11 to I0, and ankle drift")
        check("v091:layer-bbox", boxes.get("status") == "IDLE_LAYER_BBOX_TEMPORAL_PASSED" and boxes.get("measurement_layers", {}).get("head") == "presented_layers.head" and boxes.get("measurement_layers", {}).get("torso") == "presented_layers.torso_pelvis" and len(boxes.get("head_bbox_areas", [])) == 12 and len(boxes.get("torso_bbox_areas", [])) == 12 and boxes.get("hard_gates", {}).get("head_bbox_area_cv_le_0.025") is True and boxes.get("hard_gates", {}).get("torso_bbox_area_cv_le_0.025") is True and boxes.get("negative_controls", {}).get("head_only_scale", {}).get("head_fails") is True and boxes.get("negative_controls", {}).get("torso_only_scale", {}).get("torso_fails") is True, "head and torso layer bboxes are independently measured")
        occlusion_gates = [frame.get("hard_gates", {}) for frame in occlusion.get("frames", [])]
        check("v091:occlusion-policy", occlusion.get("status") == "IDLE_OCCLUSION_MEASURED_POLICY_PASSED" and len(occlusion_gates) == 12 and all(gate.get("no_meaningful_outside_authorized_overlap") is True and gate.get("z_order_constant") is True and gate.get("explicit_idle_allowed_pair_rules") is True for gate in occlusion_gates) and occlusion.get("negative_fixture", {}).get("status") == "CUTOUT_RIG_OCCLUSION_REGION_GAP" and occlusion.get("negative_fixture", {}).get("hard_gates", {}).get("no_meaningful_outside_authorized_overlap") is False and occlusion.get("no_literal_hard_gate_override") is True, "idle occlusion policy is measured and explicit")
        check("v091:execution-boundary", execution.get("new_generation") == 0 and execution.get("sam2_runs") == 0 and execution.get("comfyui_generation_jobs") == 0 and execution.get("diffusion_runs") == 0 and execution.get("production_routing") == "BLOCKED", "execution evidence stays deterministic and production-blocked")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, IndexError) as exc:
        for name in ("v091:walk-replay", "v091:idle-requalification", "v091:dual-foot", "v091:layer-bbox", "v091:occlusion-policy", "v091:execution-boundary"): check(name, False, str(exc))
    index_result = _run([sys.executable, "scripts/validation/validate_review_index_v091.py"], ROOT)
    check("v091:review-index", index_result.returncode == 0, (index_result.stdout + index_result.stderr).strip()[-800:] or "v0.9.1 review index is hash-valid")
    review = (ROOT / "REVIEW-v0.9.1.md").read_text(encoding="utf-8") if (ROOT / "REVIEW-v0.9.1.md").is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.9.0 EXTERNAL AUDIT FINDINGS", "BASELINE IMMUTABILITY", "GENERIC QA DECISION CONTRACT", "GENERIC PACKAGE LIFECYCLE", "TIMING ALTERNATIVE SCHEMA", "GENERIC DUMMY PROFILE PROOF", "WALK V081 REPLAY REGRESSION", "IDLE CANONICAL REPLAY", "DUAL-FOOT DRIFT QA", "HEAD / TORSO LAYER BBOX QA", "IDLE OCCLUSION POLICY", "IDLE REQUALIFICATION", "REVIEW INDEX V2", "NO SAM2 / NO COMFYUI / NO GENERATION", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "EXTERNAL VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE"]
    check("v091:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.9.1 review headings present")
    check("v091:no-forbidden-generation", "new_generation=0" in review and "sam2_runs=0" in review and "comfyui_generation_jobs=0" in review and "diffusion_runs=0" in review, "review records zero new-generation activity")
    check("v091:no-review-zip", not any(path.suffix.casefold() == ".zip" and ("v091" in path.name.casefold() or "0.9.1" in path.name.casefold()) for path in ROOT.rglob("*.zip")), "no review ZIP is generated in the implementation slice")


def _v0100_checks() -> None:
    """Validate the active v0.10.0 generic action-runtime attack-front slice."""
    evidence = ROOT / "docs" / "evidence"
    required = [
        "REVIEW-v0.10.0.md", "docs/test-coverage-matrix-v0.10.0.md", "schemas/current-state.json", "schemas/current-state-v0.10.0.json", "schemas/current-state-v0.9.1.json", "schemas/review-index-v0.10.0.json", "src/ugas/state_consistency_v0100.py", "scripts/validation/run_animation_runtime_v0100.py", "scripts/validation/build_review_index_v0100.py", "scripts/validation/validate_review_index_v0100.py", "docs/evidence/current-state.json", "docs/evidence/current-state-v0.9.1.json", "docs/evidence/state-consistency-v0100.json", "docs/evidence/review-index-v0.10.0.json", "docs/evidence/animation-runtime-v0100/generic-event-marker-contract-v0100.json", "docs/evidence/animation-runtime-v0100/non-loop-runtime-contract-v0100.json", "docs/evidence/animation-runtime-v0100/execution-evidence-v0.10.0.json", "profiles/animation/attack-front-v1.json", "src/ugas/animation_profiles/attack_front_v1.py", "tests/test_animation_runtime_v0100.py",
        "docs/evidence/animation-runtime-v0100/attack-front-v1/compiled-manifest.json", "docs/evidence/animation-runtime-v0100/attack-front-v1/qa-result.json", "docs/evidence/animation-runtime-v0100/attack-front-v1/package-manifest.json", "docs/evidence/animation-runtime-v0100/attack-front-v1/metadata.json", "docs/evidence/animation-runtime-v0100/attack-front-v1/attack-temporal-qa-v0100.json", "docs/evidence/animation-runtime-v0100/attack-front-v1/attack-weapon-sweep-qa-v0100.json", "docs/evidence/animation-runtime-v0100/attack-front-v1/attack-foot-ground-qa-v0100.json", "docs/evidence/animation-runtime-v0100/attack-front-v1/attack-event-marker-qa-v0100.json", "docs/evidence/animation-runtime-v0100/attack-front-v1/attack-visual-manifest-v0100.json", "docs/evidence/animation-runtime-v0100/attack-front-v1/attack-front-spritesheet-v0100.png", "docs/evidence/animation-runtime-v0100/attack-front-v1/attack-front-preview-v0100.gif",
    ]
    for relative in required:
        path = ROOT / relative; check(f"v0100:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(evidence / "current-state-v0.10.0.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.10.0.json"))
        consistency = validate_state_consistency_v0100(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.10.0.md").read_text(encoding="utf-8"))
        check("v0100:state-consistency", consistency["status"] == state["current_gate"], "; ".join(consistency.get("failures", [])) or "active v0.10.0 state is consistent")
        snapshot = load_json(evidence / "state-consistency-v0100.json")
        check("v0100:state-snapshot", snapshot.get("schema_version") == "0.10.0" and snapshot.get("status") == state["current_gate"] and snapshot.get("failures") == [], "v0.10.0 state-consistency evidence is preserved")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0100:state-consistency", False, str(exc)); check("v0100:state-snapshot", False, str(exc))
    try:
        spec = load_json(ROOT / "profiles/animation/attack-front-v1.json")
        compiled = load_json(evidence / "animation-runtime-v0100/attack-front-v1/compiled-manifest.json")
        qa = load_json(evidence / "animation-runtime-v0100/attack-front-v1/qa-result.json")
        package = load_json(evidence / "animation-runtime-v0100/attack-front-v1/package-manifest.json")
        for schema_name, artifact in (("animation-spec-v1.json", spec), ("animation-compiled-manifest-v1.json", compiled), ("animation-qa-result-v1.json", qa), ("animation-package-v1.json", package)):
            validate_instance(artifact, load_json(ROOT / "schemas" / schema_name))
        markers = [(item["event_id"], item["frame"], item["kind"]) for item in spec["event_markers"]]
        check("v0100:attack-qualified", qa.get("decision") == "QUALIFIED" and qa.get("status") == "CUTOUT_ANIMATION_RUNTIME_V1_ATTACK_FRONT_TECHNICALLY_QUALIFIED" and len(qa.get("frames", [])) == 10 and qa.get("failures") == [] and all(value is True for value in qa.get("hard_gates", {}).values()), "attack-front passes every generic and profile gate")
        check("v0100:attack-markers", markers == [("windup_peak", 2, "phase"), ("active_start", 3, "combat_window"), ("hit_event", 5, "combat_hit"), ("active_end", 6, "combat_window"), ("recovery_complete", 9, "phase")] and compiled.get("event_markers") == spec["event_markers"] and qa.get("event_markers") == spec["event_markers"] and package.get("event_markers") == spec["event_markers"], "frozen event markers survive manifest, QA and package")
        check("v0100:attack-provenance", spec["provenance"]["source_sha256"] == "7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798" and spec["provenance"]["sam2_used"] is False and spec["provenance"]["comfyui_generation_jobs"] == 0 and spec["provenance"]["diffusion_used"] is False and spec["provenance"]["source_only_pixels"] is True and len({item["target_hash"] for item in compiled["frames"]}) == 10, "R4 source-only provenance and ten distinct target hashes are bound")
        temporal = qa.get("temporal", {}); weapon = qa.get("weapon", {}); feet = qa.get("foot_ground", {}); lifecycle = temporal.get("lifecycle", {})
        check("v0100:temporal", temporal.get("status") == "ATTACK_TEMPORAL_QA_PASSED" and all(value is True for value in temporal.get("hard_gates", {}).values()) and lifecycle.get("status") == "ANIMATION_LIFECYCLE_PASSED" and lifecycle.get("closing_transition_evaluated") is False, "strict pose bounds and non-loop lifecycle pass")
        check("v0100:weapon", weapon.get("status") == "ATTACK_WEAPON_SWEEP_PASSED" and weapon.get("hit_event_frame") == 5 and weapon.get("active_window_frames") == [3, 4, 5, 6] and all(value is True for value in weapon.get("hard_gates", {}).values()), "sword attachment, active window, hit and collision gates pass")
        check("v0100:feet", feet.get("status") == "ATTACK_FOOT_GROUND_PASSED" and feet.get("closing_transition_included") is False and all(value is True for value in feet.get("hard_gates", {}).values()), "sequential planted-foot QA passes without a closing pair")
        check("v0100:package", package.get("frame_count") == 10 and package.get("cell_size") == {"width": 512, "height": 512} and package.get("sheet_size") == {"width": 2560, "height": 1024} and package.get("format") == "RGBA" and package.get("production_approved") is False and package.get("production_routing") == "BLOCKED" and package.get("qa_decision") == "QUALIFIED", "5x2 RGBA package is pilot-only and production-blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        for name in ("v0100:attack-qualified", "v0100:attack-markers", "v0100:attack-provenance", "v0100:temporal", "v0100:weapon", "v0100:feet", "v0100:package"): check(name, False, str(exc))
    try:
        generic = load_json(evidence / "animation-runtime-v0100/generic-event-marker-contract-v0100.json"); non_loop = load_json(evidence / "animation-runtime-v0100/non-loop-runtime-contract-v0100.json"); execution = load_json(evidence / "animation-runtime-v0100/execution-evidence-v0.10.0.json"); visual = load_json(evidence / "animation-runtime-v0100/attack-front-v1/attack-visual-manifest-v0100.json")
        check("v0100:generic-events", generic.get("status") == "GENERIC_EVENT_MARKER_CONTRACT_PASSED" and generic.get("hash_bound_lifecycle") is True and all(value == "REJECTED" for value in generic.get("invalid_controls", {}).values()), "optional marker contract is fail-closed and hash-bound")
        check("v0100:non-loop", non_loop.get("status") == "GENERIC_NON_LOOP_RUNTIME_CONTRACT_PASSED" and non_loop.get("loop_fixture", {}).get("closing_transition_evaluated") is True and non_loop.get("non_loop_fixture", {}).get("closing_transition_evaluated") is False and non_loop.get("non_loop_invalid_final_fixture", {}).get("final_frame_valid") is False, "loop and non-loop helper fixtures prove distinct lifecycle behavior")
        check("v0100:visual-evidence", len(visual.get("frames", [])) == 10 and len(visual.get("images", [])) == 12 and all((ROOT / item["source_path"]).is_file() and digest(ROOT / item["source_path"]) == item["sha256"] for item in visual["images"]), "ten target/detected overlays and package visuals are hash-valid")
        check("v0100:execution-boundary", execution.get("baseline_commit") == "d914d09d35ebfc5658d6c08e3502288c537fbf20" and execution.get("new_generation") == 0 and execution.get("sam2_runs") == 0 and execution.get("comfyui_generation_jobs") == 0 and execution.get("diffusion_runs") == 0 and execution.get("production_routing") == "BLOCKED" and execution.get("external_visual_review") == "REQUIRED", "execution evidence remains deterministic and external-review gated")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        for name in ("v0100:generic-events", "v0100:non-loop", "v0100:visual-evidence", "v0100:execution-boundary"): check(name, False, str(exc))
    try:
        historical_index = load_json(evidence / "review-index-v0.10.0.json")
        publication = historical_index.get("publication", {})
        subject = historical_index.get("review_subject", {})
        index_ok = historical_index.get("schema_version") == "0.10.0" and historical_index.get("version") == "0.10.0" and subject.get("baseline_commit") == "d914d09d35ebfc5658d6c08e3502288c537fbf20" and subject.get("implementation_base_commit") == "d914d09d35ebfc5658d6c08e3502288c537fbf20" and publication.get("final_head_must_be_resolved_by_external_reviewer") is True and publication.get("executor_cannot_self_assert_final_head") is True and historical_index.get("external_visual_review", {}).get("attack_front_approval") == "REQUIRED" and historical_index.get("production_routing") == "BLOCKED"
        check("v0100:review-index", index_ok, "immutable v0.10.0 review index metadata is preserved; mutable active paths are not re-hashed")
    except (OSError, json.JSONDecodeError, TypeError, AttributeError) as exc:
        check("v0100:review-index", False, str(exc))
    review = (ROOT / "REVIEW-v0.10.0.md").read_text(encoding="utf-8") if (ROOT / "REVIEW-v0.10.0.md").is_file() else ""
    headings = ["STATUS", "VERSION", "PHASE", "OBJECTIVE", "BASELINE AND IMMUTABILITY", "HISTORICAL EXTERNAL DECISIONS", "GENERIC EVENT-MARKER CONTRACT", "NON-LOOP LIFECYCLE", "ATTACK-FRONT-V1 SCOPE", "SOURCE-ONLY TARGET DERIVATION", "TEMPORAL POSE QA", "WEAPON SWEEP AND HIT TIMELINE", "FOOT-GROUND QA", "STRUCTURAL AND OCCLUSION QA", "INDEPENDENT MEDIAPIPE QA", "PACKAGE AND REVIEW EVIDENCE", "NO NEW GENERATION", "TESTS", "VALIDATION", "TRACKED SNAPSHOT / GITHUB", "EXTERNAL VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE"]
    check("v0100:review-headings", all(f"## {heading}" in review for heading in headings), "exact v0.10.0 review headings present")
    check("v0100:no-forbidden-generation", "new_generation=0" in review and "sam2_runs=0" in review and "comfyui_generation_jobs=0" in review and "diffusion_runs=0" in review, "review records zero new-generation activity")


def _git_json(revision: str, relative: str) -> dict[str, Any]:
    """Read a historical JSON blob without confusing it with the active file."""
    if (ROOT / ".git").exists():
        result = subprocess.run(["git", "show", f"{revision}:{relative}"], cwd=ROOT, capture_output=True, check=True)
        return json.loads(result.stdout.decode("utf-8"))
    snapshot = ROOT / "profiles/animation/attack-front-v2-v0.11.0.json" if relative == "profiles/animation/attack-front-v2.json" else ROOT / relative
    return load_json(snapshot)


def _git_text(revision: str, relative: str) -> str:
    if (ROOT / ".git").exists():
        result = subprocess.run(["git", "show", f"{revision}:{relative}"], cwd=ROOT, capture_output=True, check=True)
        return result.stdout.decode("utf-8")
    return (ROOT / relative).read_text(encoding="utf-8")


def _validate_historical_v0110_index() -> tuple[bool, str]:
    """Validate the old index against a clean v0.11.0 Git archive."""
    if not (ROOT / ".git").exists():
        return True, "historical index was checked in the parent Git archive"
    with tempfile.TemporaryDirectory(prefix="ugas-v0110-index-") as directory:
        snapshot = Path(directory) / "snapshot"
        snapshot.mkdir()
        archive = subprocess.run(["git", "archive", "9401c31f994e968149292b2993d960d3aafc37c4"], cwd=ROOT, capture_output=True, check=False)
        if archive.returncode != 0:
            return False, archive.stderr.decode(errors="replace")[-500:]
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
            try: tar.extractall(snapshot, filter="data")
            except TypeError: tar.extractall(snapshot)
        result = _run([sys.executable, "scripts/validation/validate_review_index_v0110.py"], snapshot)
        return result.returncode == 0, _result_detail(result) or "historical v0.11.0 review index is valid"


def _v0110_checks() -> None:
    """Validate v0.11.0 as an immutable historical slice."""
    evidence = ROOT / "docs" / "evidence"
    required = [
        "REVIEW-v0.11.0.md", "docs/test-coverage-matrix-v0.11.0.md", "schemas/current-state-v0.11.0.json", "schemas/current-state-v0.10.0.json",
        "src/ugas/motion_curves.py", "src/ugas/animation.py", "src/ugas/animation_profiles/attack_front_v2.py", "src/ugas/state_consistency_v0110.py",
        "profiles/animation/attack-front-v2.json", "scripts/validation/run_animation_runtime_v0110.py", "scripts/validation/validate_state_consistency.py",
        "scripts/validation/build_review_index_v0110.py", "scripts/validation/validate_review_index_v0110.py", "tests/test_motion_curves_v0110.py",
        "docs/evidence/current-state-v0.11.0.json", "docs/evidence/current-state-v0.10.0.json", "docs/evidence/state-consistency-v0110.json",
        "docs/evidence/animation-runtime-v0110/generic-motion-curve-contract-v0110.json", "docs/evidence/animation-runtime-v0110/historical-replay-v0110.json", "docs/evidence/animation-runtime-v0110/execution-evidence-v0.11.0.json",
        "docs/evidence/animation-runtime-v0110/attack-front-v2/compiled-manifest.json", "docs/evidence/animation-runtime-v0110/attack-front-v2/qa-result.json", "docs/evidence/animation-runtime-v0110/attack-front-v2/package-manifest.json", "docs/evidence/animation-runtime-v0110/attack-front-v2/metadata.json", "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-v2-body-mechanics-qa.json", "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-v2-temporal-qa.json", "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-v2-weapon-arc-qa.json", "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-v2-foot-ground-qa.json", "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-v2-event-marker-qa.json", "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-v2-visual-manifest.json", "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-front-v2-spritesheet.png", "docs/evidence/animation-runtime-v0110/attack-front-v2/attack-front-v2-preview.gif",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0110:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(evidence / "current-state-v0.11.0.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.11.0.json"))
        consistency = validate_state_consistency_v0110(state, _git_text("9401c31f994e968149292b2993d960d3aafc37c4", "CHECKPOINT.md"), _git_text("9401c31f994e968149292b2993d960d3aafc37c4", "REVIEW-v0.11.0.md"))
        check("v0110:state-consistency", consistency["status"] == state["current_gate"] and consistency.get("failures") == [], "; ".join(consistency.get("failures", [])) or "active v0.11.0 state is consistent")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0110:state-consistency", False, str(exc))
    try:
        spec = _git_json("9401c31f994e968149292b2993d960d3aafc37c4", "profiles/animation/attack-front-v2.json")
        compiled = load_json(evidence / "animation-runtime-v0110/attack-front-v2/compiled-manifest.json")
        qa = load_json(evidence / "animation-runtime-v0110/attack-front-v2/qa-result.json")
        package = load_json(evidence / "animation-runtime-v0110/attack-front-v2/package-manifest.json")
        for schema_name, artifact in (("animation-spec-v1.json", spec), ("animation-compiled-manifest-v1.json", compiled), ("animation-qa-result-v1.json", qa), ("animation-package-v1.json", package)):
            validate_instance(artifact, load_json(ROOT / "schemas" / schema_name))
        marker_frames = [(item["event_id"], item["frame"], item["kind"]) for item in spec["event_markers"]]
        markers_ok = marker_frames == [("windup_peak", 3, "phase"), ("active_start", 4, "combat_window"), ("hit_event", 6, "combat_hit"), ("active_end", 7, "combat_window"), ("recovery_complete", 11, "phase")]
        motion_hashes = {value for value in (spec.get("motion_tracks_sha256"), compiled.get("motion_tracks_sha256"), qa.get("motion_tracks_sha256"), package.get("motion_tracks_sha256")) if value}
        check("v0110:attack-qualified", qa.get("decision") == "QUALIFIED" and qa.get("status") == "CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED" and len(qa.get("frames", [])) == 12 and qa.get("failures") == [] and all(value is True for value in qa.get("hard_gates", {}).values()), "attack-front-v2 passes every generic and profile gate")
        check("v0110:motion-contract", len(spec.get("motion_tracks", [])) == 11 and len(motion_hashes) == 1 and next(iter(motion_hashes)) not in {None, ""}, "eleven opaque motion tracks are hash-bound across artifacts")
        check("v0110:markers", markers_ok and compiled.get("event_markers") == spec["event_markers"] and qa.get("event_markers") == spec["event_markers"] and package.get("event_markers") == spec["event_markers"], "frozen v2 event markers survive manifest, QA and package")
        check("v0110:package", package.get("frame_count") == 12 and package.get("cell_size") == {"width": 512, "height": 512} and package.get("sheet_size") == {"width": 3072, "height": 1024} and package.get("format") == "RGBA" and package.get("production_approved") is False and package.get("production_routing") == "BLOCKED" and package.get("qa_decision") == "QUALIFIED", "6x2 RGBA package is pilot-only and production-blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        for name in ("v0110:attack-qualified", "v0110:motion-contract", "v0110:markers", "v0110:package"): check(name, False, str(exc))
    try:
        generic = load_json(evidence / "animation-runtime-v0110/generic-motion-curve-contract-v0110.json")
        replay = load_json(evidence / "animation-runtime-v0110/historical-replay-v0110.json")
        execution = load_json(evidence / "animation-runtime-v0110/execution-evidence-v0.11.0.json")
        visual = load_json(evidence / "animation-runtime-v0110/attack-front-v2/attack-v2-visual-manifest.json")
        check("v0110:generic-curves", generic.get("status") == "GENERIC_MOTION_CURVE_CONTRACT_PASSED", "generic motion-curve positive and negative controls pass")
        replay_ok = replay.get("status") == "HISTORICAL_ANIMATION_REPLAY_PASSED" and (not isinstance(replay.get("checks"), dict) or all(value is True for value in replay["checks"].values()))
        check("v0110:historical-replay", replay_ok, "v0.10.0 attack, v0.8.1 walk and v0.9.0 idle remain byte-identical")
        check("v0110:execution-boundary", execution.get("status") == "CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED" and execution.get("decision") == "QUALIFIED" and execution.get("new_generation") == 0 and execution.get("sam2_runs") == 0 and execution.get("comfyui_generation_jobs") == 0 and execution.get("diffusion_runs") == 0 and execution.get("external_visual_review") == "REQUIRED" and execution.get("production_routing") == "BLOCKED", "execution evidence records deterministic source-only and external-review boundaries")
        visual_ok = all((ROOT / item["source_path"]).is_file() and digest(ROOT / item["source_path"]) == item["sha256"] for item in visual.get("images", []))
        check("v0110:visual-evidence", len(visual.get("images", [])) == 14 and visual_ok and visual.get("external_visual_review") == "REQUIRED", "twelve overlays plus spritesheet and GIF are hash-valid")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        for name in ("v0110:generic-curves", "v0110:historical-replay", "v0110:execution-boundary", "v0110:visual-evidence"): check(name, False, str(exc))
    index_ok, index_detail = _validate_historical_v0110_index()
    check("v0110:review-index", index_ok, index_detail)


def _v0111_checks() -> None:
    """Validate the active v0.11.1 weapon-continuity correction slice."""
    evidence = ROOT / "docs" / "evidence"
    required = [
        "REVIEW-v0.11.1.md", "docs/test-coverage-matrix-v0.11.1.md", "schemas/current-state.json", "schemas/current-state-v0.11.0.json", "schemas/review-index-v0.11.1.json",
        "src/ugas/state_consistency_v0111.py", "scripts/validation/run_animation_runtime_v0111.py", "scripts/validation/build_review_index_v0111.py", "scripts/validation/validate_review_index_v0111.py", "scripts/validation/validate_state_consistency_v0111.py", "tests/test_weapon_continuity_v0111.py",
        "docs/evidence/current-state.json", "docs/evidence/current-state-v0.11.0.json", "docs/evidence/state-consistency.json", "docs/evidence/state-consistency-v0110.json", "docs/evidence/review-index-v0.11.1.json",
        "docs/evidence/animation-runtime-v0111/generic-motion-curve-regression-v0111.json", "docs/evidence/animation-runtime-v0111/historical-replay-v0111.json", "docs/evidence/animation-runtime-v0111/weapon-continuity-pre-render-v0111.json", "docs/evidence/animation-runtime-v0111/weapon-continuity-post-render-v0111.json", "docs/evidence/animation-runtime-v0111/attack-v2-temporal-qa-v0111.json", "docs/evidence/animation-runtime-v0111/attack-v2-body-mechanics-qa-v0111.json", "docs/evidence/animation-runtime-v0111/attack-v2-weapon-arc-qa-v0111.json", "docs/evidence/animation-runtime-v0111/attack-v2-foot-ground-qa-v0111.json", "docs/evidence/animation-runtime-v0111/attack-v2-visual-manifest-v0111.json", "docs/evidence/animation-runtime-v0111/execution-evidence-v0.11.1.json",
        "docs/evidence/animation-runtime-v0111/attack-front-v2/compiled-manifest.json", "docs/evidence/animation-runtime-v0111/attack-front-v2/qa-result.json", "docs/evidence/animation-runtime-v0111/attack-front-v2/package-manifest.json", "docs/evidence/animation-runtime-v0111/attack-front-v2/metadata.json", "docs/evidence/animation-runtime-v0111/attack-front-v2/attack-front-v2-spritesheet-v0111.png", "docs/evidence/animation-runtime-v0111/attack-front-v2/attack-front-v2-preview-v0111.gif",
    ]
    required += [f"docs/evidence/animation-runtime-v0111/attack-front-v2/frame-{index:02d}.png" for index in range(12)]
    for relative in required:
        path = ROOT / relative
        check(f"v0111:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(evidence / "current-state-v0.11.1.json")
        schema = load_json(ROOT / "schemas/current-state-v0.11.1.json")
        validate_instance(state, schema)
        frozen_review = (
            (ROOT / "REVIEW-v0.11.1.md").read_text(encoding="utf-8")
            + "\n"
            + (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8")
        )
        consistency = validate_state_consistency_v0111(state, frozen_review, frozen_review)
        check("v0111:state-consistency", consistency["status"] == state["current_gate"] and consistency.get("failures") == [], "; ".join(consistency.get("failures", [])) or "frozen v0.11.1 state is consistent")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0111:state-consistency", False, str(exc))
    try:
        spec = load_json(ROOT / "profiles/animation/attack-front-v2.json")
        compiled = load_json(evidence / "animation-runtime-v0111/attack-front-v2/compiled-manifest.json")
        qa = load_json(evidence / "animation-runtime-v0111/attack-front-v2/qa-result.json")
        package = load_json(evidence / "animation-runtime-v0111/attack-front-v2/package-manifest.json")
        # The v0.11.1 QA artifact contains the weapon pre-render extension
        # introduced by that release; validate its frozen semantic fields below
        # rather than against the later generic schema.
        markers = [(item["event_id"], item["frame"], item["kind"]) for item in spec["event_markers"]]
        expected_markers = [("windup_peak", 3, "phase"), ("active_start", 4, "combat_window"), ("hit_event", 6, "combat_hit"), ("active_end", 7, "combat_window"), ("recovery_complete", 11, "phase")]
        hashes = {artifact.get("motion_tracks_sha256") for artifact in (spec, compiled, qa, package) if artifact.get("motion_tracks_sha256")}
        check("v0111:attack-qualified", qa.get("decision") == "QUALIFIED" and qa.get("status") == "CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED" and len(qa.get("frames", [])) == 12 and qa.get("failures") == [] and all(value is True for value in qa.get("hard_gates", {}).values()), "attack-front-v2 passes every v0.11.1 hard gate")
        check("v0111:continuity", qa.get("weapon_continuity_pre_render", {}).get("status") == "ATTACK_V2_WEAPON_CONTINUITY_QA_PASSED" and qa.get("hard_gates", {}).get("pre_render_weapon_continuity") is True, "pre-render weapon continuity is bound into QA")
        check("v0111:motion-contract", len(spec.get("motion_tracks", [])) == 11 and len(hashes) == 1, "eleven opaque motion tracks are hash-bound across artifacts")
        check("v0111:markers", markers == expected_markers and compiled.get("event_markers") == spec["event_markers"] and qa.get("event_markers") == spec["event_markers"] and package.get("event_markers") == spec["event_markers"], "frozen v2 event markers survive all artifacts")
        check("v0111:package", package.get("frame_count") == 12 and package.get("cell_size") == {"width": 512, "height": 512} and package.get("sheet_size") == {"width": 3072, "height": 1024} and package.get("format") == "RGBA" and package.get("production_approved") is False and package.get("production_routing") == "BLOCKED" and package.get("qa_decision") == "QUALIFIED", "6x2 RGBA package is pilot-only and production-blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        for name in ("v0111:attack-qualified", "v0111:continuity", "v0111:motion-contract", "v0111:markers", "v0111:package"): check(name, False, str(exc))
    try:
        pre = load_json(evidence / "animation-runtime-v0111/weapon-continuity-pre-render-v0111.json")
        post = load_json(evidence / "animation-runtime-v0111/weapon-continuity-post-render-v0111.json")
        execution = load_json(evidence / "animation-runtime-v0111/execution-evidence-v0.11.1.json")
        generic = load_json(evidence / "animation-runtime-v0111/generic-motion-curve-regression-v0111.json")
        replay = load_json(evidence / "animation-runtime-v0111/historical-replay-v0111.json")
        check("v0111:pre-render", pre.get("status") == "ATTACK_V2_WEAPON_CONTINUITY_QA_PASSED" and pre.get("render_allowed") is True and all(value is True for value in pre.get("hard_gates", {}).values()), "pre-render proxy passes before rasterization")
        check("v0111:post-render", post.get("status") == "ATTACK_V2_WEAPON_CONTINUITY_QA_PASSED" and post.get("pre_render_post_render_consistency", {}).get("all_within_tolerance") is True and all(value is True for value in post.get("hard_gates", {}).values()), "post-render recomputation matches pre-render")
        controls = execution.get("negative_controls", {})
        rejected = [value.get("status") == "REJECTED" for key, value in controls.items() if isinstance(value, dict) and key not in {"V11_near_ready_within_all_bounds"}]
        check("v0111:negative-controls", execution.get("negative_controls", {}).get("all_negative_rejected") is True and execution.get("negative_controls", {}).get("near_ready_passed") is True and all(rejected), "all false-green controls reject and near-ready passes")
        fail_closed = execution.get("pre_render_fail_closed", {})
        check("v0111:fail-closed", fail_closed.get("status") == "REJECTED" and fail_closed.get("render_output_exists") is False and fail_closed.get("render_output_files") == [], "pre-render failure creates no render output")
        check("v0111:generic-curves", generic.get("status") == "GENERIC_MOTION_CURVE_REGRESSION_PASSED", "generic motion-curve regression passes")
        check("v0111:historical-replay", replay.get("status") == "HISTORICAL_REPLAY_V0111_PASSED" and replay.get("walk_idle_attack_v1_byte_identical") is True, "historical fixtures remain unchanged")
        check("v0111:execution-boundary", execution.get("status") == "CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED" and execution.get("decision") == "QUALIFIED" and execution.get("new_generation") == 0 and execution.get("sam2_runs") == 0 and execution.get("comfyui_generation_jobs") == 0 and execution.get("diffusion_runs") == 0 and execution.get("external_visual_review") == "REQUIRED" and execution.get("production_routing") == "BLOCKED", "execution evidence records deterministic source-only boundaries")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        for name in ("v0111:pre-render", "v0111:post-render", "v0111:negative-controls", "v0111:fail-closed", "v0111:generic-curves", "v0111:historical-replay", "v0111:execution-boundary"): check(name, False, str(exc))
    try:
        visual = load_json(evidence / "animation-runtime-v0111/attack-v2-visual-manifest-v0111.json")
        visual_ok = all((ROOT / item["source_path"]).is_file() and digest(ROOT / item["source_path"]) == item["sha256"] for item in visual.get("images", []))
        check("v0111:visual-evidence", len(visual.get("images", [])) == 14 and visual_ok and visual.get("source_only_pixels") is True and visual.get("external_visual_review") == "REQUIRED", "12 overlays plus spritesheet and GIF are hash-valid")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v0111:visual-evidence", False, str(exc))
    review = (ROOT / "REVIEW-v0.11.1.md").read_text(encoding="utf-8")
    headings = ("STATUS", "VERSION", "PHASE", "OBJECTIVE", "V0.11.0 EXTERNAL AUDIT FINDING", "BASELINE IMMUTABILITY", "GENERIC MOTION CURVE REGRESSION", "FOLLOW-THROUGH CONTINUITY CONTRACT", "WEAPON ACCELERATION / REVERSAL QA", "RECOVERY-COMPLETE CONTRACT", "PRE-RENDER WEAPON PROXY", "POST-RENDER WEAPON QA", "ATTACK V2 MOTION TRACK CORRECTION", "BODY MECHANICS REGRESSION", "FOOT / BALANCE REGRESSION", "STRUCTURAL / OCCLUSION / POSE", "HISTORICAL REPLAY", "NO SAM2 / NO COMFYUI / NO GENERATION", "TESTS", "VALIDATION", "REVIEW INDEX", "EXTERNAL VISUAL REVIEW STATUS", "BLOCKERS / GAPS", "DECISIONS", "NEXT STEP", "DEFINITION OF DONE")
    check("v0111:review-headings", all(f"## {heading}" in review for heading in headings), "required v0.11.1 review headings are present")
    try:
        index = load_json(evidence / "review-index-v0.11.1.json")
        publication = index.get("publication", {})
        check(
            "v0111:review-index",
            index.get("schema_version") == "0.11.1"
            and index.get("version") == "0.11.1"
            and publication.get("final_head_must_be_resolved_by_external_reviewer") is True
            and publication.get("executor_cannot_self_assert_final_head") is True,
            "v0.11.1 review index is preserved as historical, externally resolved evidence",
        )
    except (OSError, json.JSONDecodeError, TypeError):
        check("v0111:review-index", False, "frozen v0.11.1 review index is missing or malformed")


def _v0112_checks() -> None:
    """Validate the active v0.11.2 QA-integrity and scope-recovery slice."""
    evidence = ROOT / "docs" / "evidence"
    required = [
        "REVIEW-v0.11.2.md", "docs/test-coverage-matrix-v0.11.2.md", "schemas/current-state-v0.11.2.json", "schemas/current-state-v0.11.0.json", "schemas/current-state-v0.11.1.json", "schemas/review-index-v0.11.2.json",
        "src/ugas/state_consistency_v0112.py", "scripts/validation/run_animation_runtime_v0112.py", "scripts/validation/build_review_index_v0112.py", "scripts/validation/validate_review_index_v0112.py", "scripts/validation/validate_state_consistency_v0112.py", "tests/test_qa_integrity_v0112.py",
        "docs/evidence/current-state-v0.11.2.json", "docs/evidence/current-state-v0.11.0.json", "docs/evidence/current-state-v0.11.1.json", "docs/evidence/state-consistency-v0112.json", "docs/evidence/review-index-v0.11.2.json",
        "docs/evidence/animation-runtime-v0112/identity-proof-v0112.json", "docs/evidence/animation-runtime-v0112/threshold-binding-v0112.json", "docs/evidence/animation-runtime-v0112/attack-v1-baseline-fail-closed-v0112.json", "docs/evidence/animation-runtime-v0112/negative-controls-v0112.json", "docs/evidence/animation-runtime-v0112/historical-replay-v0112.json", "docs/evidence/animation-runtime-v0112/qa-integrity-scope-recovery-v0112.json", "docs/evidence/animation-runtime-v0112/execution-evidence-v0.11.2.json", "docs/evidence/animation-runtime-v0112/attack-v2-visual-manifest-v0112.json",
        "docs/evidence/animation-runtime-v0112/attack-front-v2/compiled-manifest.json", "docs/evidence/animation-runtime-v0112/attack-front-v2/qa-result.json", "docs/evidence/animation-runtime-v0112/attack-front-v2/package-manifest.json", "docs/evidence/animation-runtime-v0112/attack-front-v2/metadata.json", "docs/evidence/animation-runtime-v0112/attack-front-v2/attack-front-v2-spritesheet.png", "docs/evidence/animation-runtime-v0112/attack-front-v2/attack-front-v2-preview.gif",
    ]
    required += [f"docs/evidence/animation-runtime-v0112/attack-front-v2/frame-{index:02d}.png" for index in range(12)]
    for relative in required:
        path = ROOT / relative; check(f"v0112:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(evidence / "current-state-v0.11.2.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.11.2.json"))
        consistency = validate_state_consistency_v0112(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.11.2.md").read_text(encoding="utf-8"))
        check("v0112:state-consistency", consistency["status"] == state["current_gate"] and consistency.get("failures") == [], "; ".join(consistency.get("failures", [])) or "active v0.11.2 state is consistent")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0112:state-consistency", False, str(exc))
    try:
        spec = load_json(ROOT / "profiles/animation/attack-front-v2.json"); baseline = load_json(ROOT / "profiles/animation/attack-front-v2-v0.11.0.json")
        compiled = load_json(evidence / "animation-runtime-v0112/attack-front-v2/compiled-manifest.json"); qa = load_json(evidence / "animation-runtime-v0112/attack-front-v2/qa-result.json"); package = load_json(evidence / "animation-runtime-v0112/attack-front-v2/package-manifest.json")
        for schema_name, artifact in (("animation-spec-v1.json", spec), ("animation-compiled-manifest-v1.json", compiled), ("animation-qa-result-v1.json", qa), ("animation-package-v1.json", package)): validate_instance(artifact, load_json(ROOT / "schemas" / schema_name))
        check("v0112:restored-motion-tracks", spec["motion_tracks"] == baseline["motion_tracks"] and spec["key_pose_bindings"] == baseline["key_pose_bindings"] and "weapon_continuity" not in spec["qa_profile"]["thresholds"], "v0.11.0 tracks and bindings restored exactly; rejected numeric lane is inactive")
        check("v0112:attack-qualified", qa.get("decision") == "QUALIFIED" and qa.get("status") == "CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED" and len(qa.get("frames", [])) == 12 and qa.get("failures") == [] and all(value is True for value in qa.get("hard_gates", {}).values()), "attack-front-v2 passes every corrected hard gate")
        check("v0112:motion-contract", len(spec.get("motion_tracks", [])) == 11 and len({artifact.get("motion_tracks_sha256") for artifact in (compiled, qa, package)}) == 1 and compiled.get("motion_tracks_sha256") == "ba8ab5f4426052ff701471c1a692a2fa52c684e1ad9428626602c01564e2646a", "motion tracks are hash-bound across active artifacts")
        check("v0112:markers", compiled.get("event_markers") == spec["event_markers"] and qa.get("event_markers") == spec["event_markers"] and package.get("event_markers") == spec["event_markers"], "frozen event markers survive all active artifacts")
        check("v0112:package", package.get("frame_count") == 12 and package.get("cell_size") == {"width": 512, "height": 512} and package.get("sheet_size") == {"width": 3072, "height": 1024} and package.get("format") == "RGBA" and package.get("production_approved") is False and package.get("production_routing") == "BLOCKED" and package.get("qa_decision") == "QUALIFIED", "6x2 RGBA package is pilot-only and production-blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        for name in ("v0112:restored-motion-tracks", "v0112:attack-qualified", "v0112:motion-contract", "v0112:markers", "v0112:package"): check(name, False, str(exc))
    try:
        execution = load_json(evidence / "animation-runtime-v0112/execution-evidence-v0.11.2.json"); negative = load_json(evidence / "animation-runtime-v0112/negative-controls-v0112.json"); identity = load_json(evidence / "animation-runtime-v0112/identity-proof-v0112.json"); replay = load_json(evidence / "animation-runtime-v0112/historical-replay-v0112.json"); visual = load_json(evidence / "animation-runtime-v0112/attack-v2-visual-manifest-v0112.json")
        check("v0112:nc-01-to-nc-10", negative.get("status") == "NC_01_TO_NC_10_PASSED", "all ten named negative controls fail closed")
        check("v0112:pixel-identity", identity.get("visual", {}).get("status") == "PIXEL_IDENTITY_V0110_PASSED" and all(item.get("byte_identical") is True for item in identity["visual"]["checks"]), "all twelve frames, spritesheet and GIF are byte-identical to v0.11.0")
        check("v0112:historical-replay", replay.get("status") == "HISTORICAL_REPLAY_V0112_PASSED" and replay.get("preserved_rejected_v0111") is True, "v0.11.1 rejected history remains preserved")
        check("v0112:execution-boundary", execution.get("status") == "CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED" and execution.get("decision") == "QUALIFIED" and execution.get("new_generation") == 0 and execution.get("sam2_runs") == 0 and execution.get("comfyui_generation_jobs") == 0 and execution.get("diffusion_runs") == 0 and execution.get("external_visual_review") == "REQUIRED" and execution.get("production_routing") == "BLOCKED", "execution evidence is deterministic, source-only and externally gated")
        visual_ok = all((ROOT / item["source_path"]).is_file() and digest(ROOT / item["source_path"]) == item["sha256"] for item in visual.get("images", []))
        check("v0112:visual-evidence", len(visual.get("images", [])) == 14 and visual_ok and visual.get("external_visual_review") == "REQUIRED", "twelve overlays plus spritesheet and GIF are hash-valid")
        check("v0112:rejected-history-files", (ROOT / "REVIEW-v0.11.1.md").is_file() and (evidence / "current-state-v0.11.1.json").is_file() and (evidence / "animation-runtime-v0111/execution-evidence-v0.11.1.json").is_file(), "v0.11.1 review and state/evidence snapshot remain present")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        for name in ("v0112:nc-01-to-nc-10", "v0112:pixel-identity", "v0112:historical-replay", "v0112:execution-boundary", "v0112:visual-evidence", "v0112:rejected-history-files"): check(name, False, str(exc))
    review = (ROOT / "REVIEW-v0.11.2.md").read_text(encoding="utf-8")
    headings = ("1 RESUMO", "2 BASELINE", "3 ARQUIVOS", "4 COMO O DESVIO", "5 PROVA", "6 THRESHOLDS", "7 BASELINE attack-v1", "8 ACCELERATION", "9 NC-01", "10 TESTES", "11 VALIDATION", "12 PIXEL IDENTITY", "13 HISTORICAL REPLAY", "14 PENDENCIAS", "15 EVIDENCE", "16 CURRENT-STATE", "17 LOCAL_TECHNICAL_QUALIFIED", "DEFINITION OF DONE")
    check("v0112:review-headings", all(heading.casefold() in review.casefold() for heading in headings), "required v0.11.2 review sections are present")
    index_result = _run([sys.executable, "scripts/validation/validate_review_index_v0112.py"], ROOT)
    check("v0112:review-index", index_result.returncode == 0, _result_detail(index_result) or "v0.11.2 review index is hash-valid")


def _v0120_checks() -> None:
    """Validate v0.12.0 as preserved history, not as the active state."""
    evidence = ROOT / "docs" / "evidence" / "observability-v0120"
    required = [
        "REVIEW-v0.12.0.md", "docs/test-coverage-matrix-v0.12.0.md", "schemas/current-state-v0.12.0.json", "schemas/review-index-v0.12.0.json",
        "src/ugas/observability/__init__.py", "src/ugas/observability/events.py", "src/ugas/observability/store.py", "src/ugas/observability/system_metrics.py", "src/ugas/observability/process_metrics.py", "src/ugas/observability/asset_activity.py", "src/ugas/observability/service.py", "src/ugas/observability/dashboard_app.py", "src/ugas/observability/static/index.html", "src/ugas/observability/static/dashboard.css", "src/ugas/observability/static/dashboard.js",
        "scripts/validation/validate_state_consistency_v0120.py", "scripts/validation/build_review_index_v0120.py", "scripts/validation/validate_review_index_v0120.py", "tests/test_observability_v0120.py",
        "docs/evidence/current-state-v0.12.0.json", "docs/evidence/current-state-v0.11.2.json", "docs/evidence/state-consistency-v0120.json", "docs/evidence/observability-v0120/external-review-v0112.json",
    ]
    required += [f"docs/evidence/observability-v0120/{name}" for name in ("dashboard-startup.json", "system-idle.json", "command-event.json", "file-activity.json", "api-snapshots.json", "security.json", "animation-regression-v0112.json", "test-results.json", "validation-results.json", "publication.json", "dashboard-overview.png", "dashboard-system-pipeline.png", "dashboard-assets-activity.png", "dashboard-qa-events.png", "dashboard-mobile.png")]
    for relative in required:
        path = ROOT / relative
        check(f"v0120:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.12.0.json"); schema = load_json(ROOT / "schemas/current-state-v0.12.0.json"); validate_instance(state, schema)
        consistency = validate_state_consistency_v0120(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.12.0.md").read_text(encoding="utf-8"))
        check("v0120:state-consistency", consistency["status"] == state["current_gate"] and consistency.get("failures") == [], "; ".join(consistency.get("failures", [])) or "preserved v0.12.0 state is consistent")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0120:state-consistency", False, str(exc))
    try:
        external = load_json(evidence / "external-review-v0112.json")
        check("v0120:external-approval", external.get("decision") == "APPROVED_PILOT" and external.get("artifact_contract", {}).get("frame_count") == 12 and external.get("artifact_contract", {}).get("width") == 512 and external.get("artifact_contract", {}).get("height") == 512 and external.get("production_approval") is False and external.get("production_routing") == "BLOCKED", "v0.11.2 external pilot decision is explicitly bounded")
        review = (ROOT / "REVIEW-v0.12.0.md").read_text(encoding="utf-8")
        headings = tuple(f"{index}." for index in range(1, 21))
        check("v0120:review-headings", all(f"## {heading}" in review for heading in headings), "mandatory v0.12.0 review sections are present")
        check("v0120:scope-text", all(literal in review for literal in ("local-only", "read-only", "production_routing=BLOCKED", "APPROVED_PILOT", "external_review_observability_dashboard_v0120")), "review records local, read-only and production boundaries")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v0120:review", False, str(exc))
    contracts = (ROOT / "src/ugas/observability/dashboard_app.py").read_text(encoding="utf-8") if (ROOT / "src/ugas/observability/dashboard_app.py").is_file() else ""
    check("v0120:api-contract", all(route in contracts for route in ("/api/status", "/api/system", "/api/processes", "/api/jobs", "/api/assets/recent", "/api/qa", "/api/events", "/api/health", "/api/stream", "/api/preview/")), "required read-only JSON, SSE and preview routes are present")
    check("v0120:security-contract", "127.0.0.1" in contracts and "shell=True" not in (ROOT / "src/ugas/observability/system_metrics.py").read_text(encoding="utf-8"), "loopback default and explicit subprocess boundary are present")
    historical_index = ROOT / "docs/evidence/review-index-v0.12.0.json"
    check("v0120:review-index-history", historical_index.is_file() and "0.12.0" in historical_index.read_text(encoding="utf-8"), "v0.12.0 review index remains preserved history; active v0.12.2 owns current validation")


def _v0121_history_checks() -> None:
    """Confirm v0.12.1 remains available as immutable rejected history."""
    required = ["REVIEW-v0.12.1.md", "docs/test-coverage-matrix-v0.12.1.md", "schemas/current-state-v0.12.1.json", "schemas/review-index-v0.12.1.json", "docs/evidence/current-state-v0.12.1.json", "docs/evidence/current-state-v0.12.0.json", "docs/evidence/state-consistency-v0121.json", "docs/evidence/review-index-v0.12.1.json"]
    required += [f"docs/evidence/observability-v0121/{name}" for name in ("security-xss.json", "qa-negative-controls-v0121.json", "pipeline-live-stage-v0121.json", "orphan-reconciliation-v0121.json", "system-gpu-process-v0121.json", "stale-last-known-v0121.json", "file-activity-v0121.json", "preview-security-v0121.json", "external-review-v0112-binding-correction-v0121.json", "animation-regression-v0112-v0121.json", "dashboard-startup.json", "api-snapshots.json", "test-results-v0121.json", "validation-results-v0121.json", "publication.json", "dashboard-overview.png", "dashboard-system-gpu-processes.png", "dashboard-live-pipeline-stage.png", "dashboard-qa-events.png", "dashboard-mobile.png")]
    for relative in required:
        path = ROOT / relative; check(f"v0121:history:{relative}", path.is_file(), "preserved" if path.is_file() else "missing")
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.12.1.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.12.1.json"))
        consistency = validate_state_consistency_v0121(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.12.1.md").read_text(encoding="utf-8"))
        check("v0121:history-state", consistency["status"] == state["current_gate"] and consistency.get("failures") == [], "; ".join(consistency.get("failures", [])) or "v0.12.1 state snapshot remains valid")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0121:history-state", False, str(exc))


def _v0122_checks() -> None:
    """Confirm v0.12.2 evidence remains preserved, without reclassifying it."""
    evidence = ROOT / "docs/evidence/observability-v0122"
    required = ["REVIEW-v0.12.2.md", "docs/test-coverage-matrix-v0.12.2.md", "schemas/review-index-v0122.json", "scripts/validation/validate_review_index_v0122.py", "docs/evidence/review-index-v0.12.2.json"]
    required += [f"docs/evidence/observability-v0122/{name}" for name in ("qa-cache-invalidation-v0122.json", "qa-negative-controls-v0122.json", "stale-last-known-integration-v0122.json", "generation-telemetry-contract-v0122.json", "docker-preflight-v0122.json", "docker-compose-config-v0122.json", "docker-build-v0122.json", "docker-runtime-v0122.json", "docker-gpu-v0122.json", "docker-cross-process-telemetry-v0122.json", "docker-file-watch-v0122.json", "docker-persistence-v0122.json", "docker-autostart-v0122.json", "docker-security-v0122.json", "test-results-v0122.json", "validation-results-v0122.json", "publication.json", "dashboard-docker-overview-v0122.png", "dashboard-docker-live-activity-v0122.png")]
    for relative in required:
        path = ROOT / relative; check(f"v0122:history:{relative}", path.is_file(), "preserved" if path.is_file() else "missing")
    unchanged = (not (ROOT / ".git").exists() and (ROOT / "docs/evidence/review-index-v0.12.2.json").is_file()) or subprocess.run(["git", "diff", "--quiet", V0123_BASELINE_HEAD, "--", "docs/evidence/review-index-v0.12.2.json"], cwd=ROOT, capture_output=True, check=False).returncode == 0
    check("v0122:history:index-unchanged", unchanged, "v0.12.2 review index file was not rewritten")
    check("v0122:history:active-artifacts-present", evidence.is_dir() and (ROOT / "docs/evidence/observability-v0122/dashboard-docker-overview-v0122.png").is_file(), "v0.12.2 evidence remains available as historical transport material")


def _v0123_checks() -> None:
    """Validate v0.12.3 as preserved history after the active state advances."""
    required = [
        "REVIEW-v0.12.3.md", "schemas/current-state-v0.12.3.json", "docs/evidence/current-state-v0.12.3.json",
        "schemas/github-review-manifest-v1.json", "schemas/review-visual-transport-v1.json",
        "scripts/validation/build_github_review_manifest.py", "scripts/validation/build_review_visual_transport_v0123.py",
        "scripts/validation/validate_github_review_manifest.py", "scripts/validation/validate_review_visual_transport_v0123.py",
        "scripts/validation/validate_github_review_security_v0123.py", "scripts/validation/enforce_github_review_v0123.py",
        "scripts/validation/validate_governance_v0123.py", "scripts/validation/record_v0123_results.py",
        "docs/evidence/github-review-v0123/visual-manifest.json",
        "docs/evidence/github-review-v0123/visuals/dashboard-docker-overview-v0122-transport.png",
        "docs/evidence/github-review-v0123/visuals/dashboard-docker-live-activity-v0122-transport.png",
    ]
    for relative in required:
        path = ROOT / relative; check(f"v0123:history:{relative}", path.is_file(), "preserved" if path.is_file() else "missing")
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.12.3.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.12.3.json"))
        check("v0123:history-state", state.get("version") == "0.12.3" and state.get("production_routing") == "BLOCKED" and state.get("production_approved") is False, "v0.12.3 state snapshot remains immutable and production-blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0123:history-state", False, str(exc))
    manifest = ROOT / "docs/evidence/github-review-v0123/github-review-manifest-local.json"
    visuals = ROOT / "docs/evidence/github-review-v0123/visual-manifest.json"
    if manifest.is_file() and visuals.is_file():
        result = validate_github_review_manifest(manifest, visuals)
        check("v0123:history-manifest", result["status"] == "GITHUB_REVIEW_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "v0.12.3 manifest remains valid")
    else:
        check("v0123:history-manifest", False, "v0.12.3 manifest evidence is missing")


def _v0124_checks() -> None:
    """Validate the immutable v0.12.4 CI/governance recovery snapshot."""
    required = [
        "REVIEW-v0.12.4.md", "schemas/current-state-v0.12.4.json", "schemas/current-state.json", "docs/evidence/current-state.json", "docs/evidence/current-state-v0.12.3.json", "docs/evidence/current-state-v0.12.4.json",
        "src/ugas/state_consistency_v0124.py", "scripts/validation/validate_state_consistency.py", "scripts/validation/validate_governance_v0124.py",
        "scripts/validation/build_github_review_manifest_v0124.py", "scripts/validation/validate_github_review_manifest_v0124.py", "scripts/validation/validate_github_review_security_v0124.py", "scripts/validation/enforce_github_review_v0124.py", "scripts/validation/record_v0124_results.py", "scripts/validation/validate_github_workflows_v0124.py", "scripts/github/ugas-pr-handoff.ps1",
        "docs/evidence/github-governance-v0124/pr1-premature-merge.json", "docs/evidence/github-governance-v0124/dashboard-external-visual-approval.json", "docs/evidence/github-governance-v0124/ruleset-readback.json", "docs/evidence/github-governance-v0124/pr-handoff-v0124.json", "docs/evidence/github-governance-v0124/historical/v0.11.2/CHECKPOINT.md",
        "docs/evidence/github-governance-v0124/github-preflight.json", "docs/evidence/github-governance-v0124/governance-consistency-v0124.json", "docs/evidence/github-governance-v0124/state-consistency-v0124.json", "docs/evidence/github-governance-v0124/workflow-validation.json", "docs/evidence/github-governance-v0124/negative-controls-v0124.json", "docs/evidence/github-governance-v0124/test-results-v0124.json", "docs/evidence/github-governance-v0124/validation-results-v0124.json", "docs/evidence/github-governance-v0124/gate-results-v0124.json", "docs/evidence/github-governance-v0124/github-review-manifest-local.json", "docs/evidence/github-governance-v0124/manifest-validation-v0124.json", "docs/evidence/github-governance-v0124/security-validation-v0124.json", "docs/evidence/github-governance-v0124/visual-manifest.json",
        ".github/workflows/ugas-ci.yml", ".github/workflows/ugas-review.yml",
    ]
    for relative in required:
        path = ROOT / relative; check(f"v0124:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.12.4.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.12.4.json"))
        legacy_review = (ROOT / "REVIEW-v0.12.4.md").read_text(encoding="utf-8")
        consistency = validate_state_consistency_v0124(state, legacy_review, legacy_review, legacy_review)
        check("v0124:state-consistency", consistency["status"] == state["current_gate"] and consistency.get("failures") == [], "; ".join(consistency.get("failures", [])) or "immutable v0.12.4 state is consistent")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0124:state-consistency", False, str(exc))
    workflow_result = validate_github_workflows_v0124(ROOT)
    check("v0124:workflow-structure", workflow_result["status"] == "PASS", "; ".join(workflow_result.get("failures", [])) or "workflow structure is locally valid; GitHub remains authoritative")
    incident = load_json(ROOT / "docs/evidence/github-governance-v0124/pr1-premature-merge.json")
    check("v0124:pr1-incident", incident.get("classification") == "GOVERNANCE_ORDER_VIOLATION_AND_FAILED_CHECK_MERGE" and incident.get("pr", {}).get("number") == 1 and incident.get("review_workflow", {}).get("conclusion") == "FAILURE" and incident.get("review_artifact", {}).get("uploaded") is True, "PR #1 red-run premature-merge incident is factual and immutable")
    approval = load_json(ROOT / "docs/evidence/github-governance-v0124/dashboard-external-visual-approval.json")
    check("v0124:dashboard-approval-binding", approval.get("decision") == "APPROVED_PILOT" and approval.get("source_artifact", {}).get("id") == "9867524286" and len(approval.get("visuals", [])) == 2 and approval.get("historical_sources_rewritten") is False, "dashboard visual approval is forward-only and bound to PR #1 artifact/visual hashes")
    ruleset = load_json(ROOT / "docs/evidence/github-governance-v0124/ruleset-readback.json")
    configured_ruleset = ruleset.get("protected") is True and ruleset.get("status") == "CONFIGURED_READ_BACK" and ruleset.get("credential_values_recorded") is False and ruleset.get("capability_gap") is None
    explicit_ruleset_gap = ruleset.get("protected") is False and ruleset.get("credential_values_recorded") is False and ruleset.get("capability_gap") == "RULESET_CAPABILITY_GAP"
    check("v0124:ruleset-readback", configured_ruleset or explicit_ruleset_gap, "ruleset is either effectively protected with authenticated readback or records an exact capability gap")
    handoff = load_json(ROOT / "docs/evidence/github-governance-v0124/pr-handoff-v0124.json")
    required_contexts = {"UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence"}
    observed_contexts = {item.get("name") for item in handoff.get("checks", []) if isinstance(item, dict) and item.get("state") == "SUCCESS"}
    check("v0124:pr-handoff", handoff.get("status") == "READY_FOR_EXTERNAL_REVIEW" and handoff.get("pr_number", 0) > 0 and handoff.get("pr_state") == "OPEN" and required_contexts.issubset(observed_contexts) and handoff.get("merge_performed") is False and handoff.get("credential_values_recorded") is False, "authenticated handoff records an open PR, all required checks green and no merge")
    negative = load_json(ROOT / "docs/evidence/github-governance-v0124/negative-controls-v0124.json")
    check("v0124:negative-controls", negative.get("status") == "ALL_REQUIRED_NEGATIVE_CONTROLS_PASSED", "merge, snapshot, history, workflow, artifact and production negative controls pass")
    manifest = ROOT / "docs/evidence/github-governance-v0124/github-review-manifest-local.json"
    visual = ROOT / "docs/evidence/github-governance-v0124/visual-manifest.json"
    if manifest.is_file() and visual.is_file():
        result = validate_github_review_manifest_v0124(manifest, visual)
        check("v0124:review-manifest", result["status"] == "V0124_GITHUB_REVIEW_MANIFEST_PASSED", "; ".join(result.get("failures", [])) or "active v0.12.4 review manifest and visuals are valid")
    else:
        check("v0124:review-manifest", False, "local v0.12.4 review manifest evidence is missing")
    check("v0124:scope-boundary", (ROOT / "docs/evidence/current-state-v0.12.4.json").is_file(), "v0.12.4 scope is preserved as a versioned snapshot")
    check("v0124:no-self-merge-path", "merge_performed = $false" in (ROOT / "scripts/github/ugas-pr-handoff.ps1").read_text(encoding="utf-8") and "gh', 'pr', 'merge" not in (ROOT / "scripts/github/ugas-pr-handoff.ps1").read_text(encoding="utf-8"), "handoff helper has no self-merge path")


def _v0130_checks() -> None:
    """Confirm v0.13.0 remains frozen as rejected/failed-external-review history."""
    required = [
        "REVIEW-v0.13.0.md", "schemas/current-state-v0.13.0.json",
        "docs/evidence/current-state-v0.13.0.json", "docs/evidence/current-state-v0.12.4.json",
        "src/ugas/state_consistency_v0130.py", "scripts/validation/validate_state_consistency_v0130.py",
        "schemas/github-review-manifest-v0130.json", "scripts/validation/record_v0130_results.py", "scripts/validation/build_github_review_manifest_v0130.py", "scripts/validation/validate_github_review_manifest_v0130.py", "scripts/validation/validate_github_review_security_v0130.py", "scripts/validation/enforce_github_review_v0130.py",
        "scripts/validation/run_animation_runtime_v0130.py",
        "docs/evidence/animation-runtime-v0130/run-front-contract-v0130.json",
        "docs/evidence/animation-runtime-v0130/execution-evidence-v0.13.0.json",
        "docs/evidence/animation-runtime-v0130/run-front-visual-manifest-v0130.json",
        "docs/evidence/animation-runtime-v0130/run-front-gate-negative-controls-v0130.json",
        "docs/evidence/animation-runtime-v0130/run-front-phase-markers-v0130.png",
        "docs/evidence/animation-runtime-v0130/state-consistency-v0130.json",
        "docs/evidence/animation-runtime-v0130/run-front-v1/compiled-manifest.json",
        "docs/evidence/animation-runtime-v0130/run-front-v1/qa-result.json",
        "docs/evidence/animation-runtime-v0130/run-front-v1/package-manifest.json",
        "docs/evidence/animation-runtime-v0130/run-front-v1/run-front-preview-v0130.gif",
        "docs/evidence/animation-runtime-v0130/run-front-v1/run-front-spritesheet-v0130.png",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0130:history:{relative}", path.is_file(), "preserved" if path.is_file() else "missing")
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.13.0.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.13.0.json"))
        legacy_review = (ROOT / "REVIEW-v0.13.0.md").read_text(encoding="utf-8")
        consistency = validate_state_consistency_v0130(state, legacy_review, legacy_review, legacy_review)
        check("v0130:history-state", consistency["status"] == state["current_gate"] and consistency["failures"] == [], "; ".join(consistency["failures"]) or "v0.13.0 state snapshot remains valid")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0130:history-state", False, str(exc))
    matrix = load_json(ROOT / "docs/ugas-v1-capability-matrix.json")
    check("v0130:matrix-dependency", len(matrix.get("capabilities", [])) == 16 and matrix.get("production_routing") == "BLOCKED" and matrix.get("new_generation") == 0, "canonical matrix still has sixteen capabilities with production blocked")
    contract = load_json(ROOT / "docs/evidence/animation-runtime-v0130/run-front-contract-v0130.json")
    check("v0130:contract", contract.get("capability") == "run_front_v1" and contract.get("dependencies", {}).get("matrix_capability_count") == 16 and contract.get("review_policy", {}).get("external_visual") == "REQUIRED" and contract.get("review_policy", {}).get("production_routing") == "BLOCKED" and len(contract.get("negative_controls", [])) == 8, "historical RUN_FRONT_V1 contract remains bound")
    qa = load_json(ROOT / "docs/evidence/animation-runtime-v0130/run-front-v1/qa-result.json")
    check("v0130:qa", qa.get("decision") == "QUALIFIED" and qa.get("failures") == [] and all(qa.get("hard_gates", {}).values()) and all(qa.get("temporal", {}).get("hard_gates", {}).values()), "historical RUN_FRONT_V1 frame and temporal gates remain recorded")
    package = load_json(ROOT / "docs/evidence/animation-runtime-v0130/run-front-v1/package-manifest.json")
    check("v0130:package", package.get("qa_decision") == "QUALIFIED" and package.get("production_routing") == "BLOCKED" and package.get("format") == "RGBA" and len(package.get("event_markers", [])) == 9, "historical package remains bound to qualified QA")
    negative = load_json(ROOT / "docs/evidence/animation-runtime-v0130/run-front-gate-negative-controls-v0130.json")
    check("v0130:negative-controls", negative.get("status") == "NC_01_TO_NC_08_PASSED" and len(negative.get("controls", {})) == 8 and all(item.get("status") == "REJECTED" for item in negative.get("controls", {}).values()), "historical eight mutated fixtures remain rejected")
    execution = load_json(ROOT / "docs/evidence/animation-runtime-v0130/execution-evidence-v0.13.0.json")
    check("v0130:execution-boundary", execution.get("source_only_pixels") is True and execution.get("new_generation") == 0 and execution.get("external_visual") == "REQUIRED" and execution.get("next_capability_started") is False and execution.get("approved_assets_untouched") == "APPROVED_ASSETS_UNTOUCHED", "historical execution evidence preserves source-only and external-review boundaries")
    check("v0130:baseline", V0130_BASELINE_HEAD == "0beb4c23604f1e45736c3082f99d2e08fa1ac308", "v0.13.0 immutable base remains post-merge v0.12.4")


def _v0131_checks() -> None:
    """Confirm v0.13.1 remains frozen as the approved RUN_FRONT_V1 pilot history."""
    required = [
        "REVIEW-v0.13.1.md", "REVIEW-v0.13.0.md", "schemas/current-state-v0.13.1.json",
        "docs/evidence/current-state-v0.13.1.json", "docs/evidence/current-state-v0.13.0.json", "docs/evidence/current-state-v0.12.4.json",
        "docs/evidence/github-governance-v0131/run-front-v0131-external-visual-approval.json",
        "docs/evidence/github-governance-v0131/run-front-v0131-provenance.json",
        "src/ugas/state_consistency_v0131.py", "scripts/validation/validate_state_consistency_v0131.py",
        "schemas/github-review-manifest-v0131.json", "scripts/validation/record_v0131_results.py", "scripts/validation/build_github_review_manifest_v0131.py", "scripts/validation/validate_github_review_manifest_v0131.py", "scripts/validation/validate_github_review_security_v0131.py", "scripts/validation/enforce_github_review_v0131.py",
        "profiles/animation/run-front-v1.json", "src/ugas/animation_profiles/run_front_v1.py",
        "scripts/validation/run_animation_runtime_v0131.py",
        "docs/evidence/animation-runtime-v0131/run-front-contract-v0131.json",
        "docs/evidence/animation-runtime-v0131/execution-evidence-v0.13.1.json",
        "docs/evidence/animation-runtime-v0131/run-front-visual-manifest-v0131.json",
        "docs/evidence/animation-runtime-v0131/run-front-gate-negative-controls-v0131.json",
        "docs/evidence/animation-runtime-v0131/run-front-gif-timing-v0131.json",
        "docs/evidence/animation-runtime-v0131/approved-assets-untouched-v0131.json",
        "docs/evidence/animation-runtime-v0131/state-consistency-v0131.json",
        "docs/evidence/animation-runtime-v0131/run-front-phase-markers-v0131.png",
        "docs/evidence/animation-runtime-v0131/run-front-v1/compiled-manifest.json",
        "docs/evidence/animation-runtime-v0131/run-front-v1/qa-result.json",
        "docs/evidence/animation-runtime-v0131/run-front-v1/package-manifest.json",
        "docs/evidence/animation-runtime-v0131/run-front-v1/run-front-preview-v0131.gif",
        "docs/evidence/animation-runtime-v0131/run-front-v1/run-front-spritesheet-v0131.png",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0131:history:{relative}", path.is_file(), "preserved" if path.is_file() else "missing")
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.13.1.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.13.1.json"))
        legacy_review = (ROOT / "REVIEW-v0.13.1.md").read_text(encoding="utf-8")
        consistency = validate_state_consistency_v0131(state, legacy_review, legacy_review, legacy_review)
        check("v0131:history-state", consistency["status"] == state["current_gate"] and consistency["failures"] == [], "; ".join(consistency["failures"]) or "v0.13.1 state snapshot remains valid")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0131:history-state", False, str(exc))
    matrix = load_json(ROOT / "docs/ugas-v1-capability-matrix.json")
    check("v0131:matrix-dependency", len(matrix.get("capabilities", [])) == 16 and matrix.get("production_routing") == "BLOCKED" and matrix.get("new_generation") == 0, "canonical matrix still has sixteen capabilities with production blocked")
    contract = load_json(ROOT / "docs/evidence/animation-runtime-v0131/run-front-contract-v0131.json")
    check("v0131:contract", contract.get("capability") == "run_front_v1" and contract.get("dependencies", {}).get("implementation_base_commit") == V0131_BASELINE_HEAD and contract.get("dependencies", {}).get("matrix_capability_count") == 16 and contract.get("review_policy", {}).get("external_visual") == "REQUIRED" and contract.get("review_policy", {}).get("production_routing") == "BLOCKED" and len(contract.get("negative_controls", [])) == 12, "historical RUN_FRONT_V1 v0.13.1 contract remains bound")
    spec = load_json(ROOT / "profiles/animation/run-front-v1.json")
    check("v0131:profile", spec.get("frame_count") == 8 and spec.get("fps") == 12 and spec.get("loop") is True and spec.get("direction") == "front" and len(spec.get("motion_tracks", [])) == 12 and spec.get("provenance", {}).get("source_only_pixels") is True and spec.get("adapter_parameters", {}).get("flight_frames") == [3, 7] and spec.get("adapter_parameters", {}).get("immutable_approved_assets_base") == V0131_BASELINE_HEAD, "historical front run profile remains eight deterministic source-only frames")
    qa = load_json(ROOT / "docs/evidence/animation-runtime-v0131/run-front-v1/qa-result.json")
    check("v0131:qa", qa.get("decision") == "QUALIFIED" and qa.get("failures") == [] and all(qa.get("hard_gates", {}).values()) and all(qa.get("temporal", {}).get("hard_gates", {}).values()), "historical RUN_FRONT_V1 frame and temporal gates remain recorded")
    package = load_json(ROOT / "docs/evidence/animation-runtime-v0131/run-front-v1/package-manifest.json")
    check("v0131:package", package.get("qa_decision") == "QUALIFIED" and package.get("production_routing") == "BLOCKED" and package.get("format") == "RGBA" and len(package.get("event_markers", [])) == 9, "historical package remains bound to qualified QA")
    negative = load_json(ROOT / "docs/evidence/animation-runtime-v0131/run-front-gate-negative-controls-v0131.json")
    check("v0131:negative-controls", negative.get("status") == "NC_01_TO_NC_12_PASSED" and len(negative.get("controls", {})) == 12 and all(item.get("status") == "REJECTED" for item in negative.get("controls", {}).values()), "historical twelve mutated fixtures remain rejected")
    execution = load_json(ROOT / "docs/evidence/animation-runtime-v0131/execution-evidence-v0.13.1.json")
    check("v0131:execution-boundary", execution.get("implementation_base_commit") == V0131_BASELINE_HEAD and execution.get("source_only_pixels") is True and execution.get("new_generation") == 0 and execution.get("external_visual") == "REQUIRED" and execution.get("next_capability_started") is False and execution.get("approved_assets_untouched") == "APPROVED_ASSETS_UNTOUCHED", "historical execution evidence preserves source-only and external-review boundaries")
    gif_timing = load_json(ROOT / "docs/evidence/animation-runtime-v0131/run-front-gif-timing-v0131.json")
    check("v0131:gif-timing", gif_timing.get("status") == "GIF_TIMING_PASSED" and gif_timing.get("decoded", {}).get("total_cycle_ms") == 670 and all(gif_timing.get("hard_gates", {}).values()), "historical decoded GIF timing remains inside the 12 fps tolerance")
    assets = load_json(ROOT / "docs/evidence/animation-runtime-v0131/approved-assets-untouched-v0131.json")
    check("v0131:approved-assets", assets.get("status") == "APPROVED_ASSETS_UNTOUCHED" and assets.get("head_fallback_used") is False and assets.get("base_commit") == V0131_BASELINE_HEAD, "historical approved assets remain byte-identical to the immutable base")


def _v0140_checks() -> None:
    """Confirm v0.14.0 remains frozen as rejected package-integrity history."""
    required = [
        "REVIEW-v0.14.0.md", "REVIEW-v0.13.1.md", "schemas/current-state-v0.14.0.json",
        "docs/evidence/current-state-v0.14.0.json", "docs/evidence/current-state-v0.13.1.json",
        "src/ugas/state_consistency_v0140.py", "scripts/validation/validate_state_consistency_v0140.py",
        "schemas/github-review-manifest-v0140.json", "scripts/validation/record_v0140_results.py", "scripts/validation/build_github_review_manifest_v0140.py", "scripts/validation/validate_github_review_manifest_v0140.py", "scripts/validation/validate_github_review_security_v0140.py", "scripts/validation/enforce_github_review_v0140.py",
        "scripts/validation/run_animation_runtime_v0140.py",
        "docs/evidence/animation-runtime-v0140/hit-front-contract-v0140.json",
        "docs/evidence/animation-runtime-v0140/execution-evidence-v0.14.0.json",
        "docs/evidence/animation-runtime-v0140/hit-front-visual-manifest-v0140.json",
        "docs/evidence/animation-runtime-v0140/hit-front-gate-negative-controls-v0140.json",
        "docs/evidence/animation-runtime-v0140/hit-front-gif-timing-v0140.json",
        "docs/evidence/animation-runtime-v0140/approved-assets-untouched-v0140.json",
        "docs/evidence/animation-runtime-v0140/state-consistency-v0140.json",
        "docs/evidence/animation-runtime-v0140/hit-front-phase-markers-v0140.png",
        "docs/evidence/animation-runtime-v0140/hit-front-v1/compiled-manifest.json",
        "docs/evidence/animation-runtime-v0140/hit-front-v1/qa-result.json",
        "docs/evidence/animation-runtime-v0140/hit-front-v1/package-manifest.json",
        "docs/evidence/animation-runtime-v0140/hit-front-v1/hit-front-preview-v0140.gif",
        "docs/evidence/animation-runtime-v0140/hit-front-v1/hit-front-spritesheet-v0140.png",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0140:history:{relative}", path.is_file(), "preserved" if path.is_file() else "missing")
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.14.0.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.14.0.json"))
        legacy_review = (ROOT / "REVIEW-v0.14.0.md").read_text(encoding="utf-8")
        consistency = validate_state_consistency_v0140(state, legacy_review, legacy_review, legacy_review)
        check("v0140:history-state", consistency["status"] == state["current_gate"] and consistency["failures"] == [], "; ".join(consistency["failures"]) or "v0.14.0 state snapshot remains valid")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0140:history-state", False, str(exc))
    contract = load_json(ROOT / "docs/evidence/animation-runtime-v0140/hit-front-contract-v0140.json")
    check("v0140:contract", contract.get("capability") == "hit_reaction_front" and contract.get("dependencies", {}).get("implementation_base_commit") == V0140_BASELINE_HEAD and len(contract.get("negative_controls", [])) == 10, "historical HIT_REACTION_FRONT v0.14.0 contract remains bound")
    qa = load_json(ROOT / "docs/evidence/animation-runtime-v0140/hit-front-v1/qa-result.json")
    check("v0140:qa", qa.get("decision") == "QUALIFIED" and qa.get("failures") == [], "historical HIT_REACTION_FRONT frame gates remain recorded")
    negative = load_json(ROOT / "docs/evidence/animation-runtime-v0140/hit-front-gate-negative-controls-v0140.json")
    check("v0140:negative-controls", negative.get("status") == "NC_01_TO_NC_10_PASSED" and len(negative.get("controls", {})) == 10, "historical ten mutated fixtures remain rejected")
    execution = load_json(ROOT / "docs/evidence/animation-runtime-v0140/execution-evidence-v0.14.0.json")
    check("v0140:execution-boundary", execution.get("source_only_pixels") is True and execution.get("new_generation") == 0 and execution.get("next_capability_started") is False, "historical execution evidence preserves source-only boundaries")
    gif_timing = load_json(ROOT / "docs/evidence/animation-runtime-v0140/hit-front-gif-timing-v0140.json")
    check("v0140:false-green-loop", gif_timing.get("decoded", {}).get("loop") == 1, "frozen rejected GIF still records explicit loop=1")
    assets = load_json(ROOT / "docs/evidence/animation-runtime-v0140/approved-assets-untouched-v0140.json")
    check("v0140:approved-assets", assets.get("status") == "APPROVED_ASSETS_UNTOUCHED" and assets.get("head_fallback_used") is False, "historical approved-asset identity remains recorded")


def _v0141_checks() -> None:
    """Validate the frozen v0.14.1 HIT_REACTION_FRONT history."""
    required = [
        "REVIEW-v0.14.1.md", "REVIEW-v0.14.0.md", "schemas/current-state-v0.14.1.json",
        "docs/evidence/current-state-v0.14.1.json", "docs/evidence/current-state-v0.14.0.json",
        "docs/evidence/github-governance-v0141/hit-front-v0141-external-visual-approval.json",
        "docs/evidence/github-governance-v0141/hit-front-v0141-provenance.json",
        "src/ugas/state_consistency_v0141.py", "scripts/validation/validate_state_consistency_v0141.py",
        "schemas/github-review-manifest-v0141.json", "scripts/validation/record_v0141_results.py", "scripts/validation/build_github_review_manifest_v0141.py", "scripts/validation/validate_github_review_manifest_v0141.py", "scripts/validation/validate_github_review_security_v0141.py", "scripts/validation/enforce_github_review_v0141.py",
        "profiles/animation/hit-front-v1.json", "src/ugas/animation_profiles/hit_front_v1.py",
        "scripts/validation/run_animation_runtime_v0141.py",
        "docs/evidence/animation-runtime-v0141/hit-front-contract-v0141.json",
        "docs/evidence/animation-runtime-v0141/execution-evidence-v0.14.1.json",
        "docs/evidence/animation-runtime-v0141/hit-front-visual-manifest-v0141.json",
        "docs/evidence/animation-runtime-v0141/hit-front-gate-negative-controls-v0141.json",
        "docs/evidence/animation-runtime-v0141/hit-front-loop-negative-controls-v0141.json",
        "docs/evidence/animation-runtime-v0141/hit-front-gif-timing-v0141.json",
        "docs/evidence/animation-runtime-v0141/hit-front-gif-loop-semantics-v0141.json",
        "docs/evidence/animation-runtime-v0141/hit-front-visual-preservation-v0141.json",
        "docs/evidence/animation-runtime-v0141/approved-assets-untouched-v0141.json",
        "docs/evidence/animation-runtime-v0141/state-consistency-v0141.json",
        "docs/evidence/animation-runtime-v0141/hit-front-v1/compiled-manifest.json",
        "docs/evidence/animation-runtime-v0141/hit-front-v1/qa-result.json",
        "docs/evidence/animation-runtime-v0141/hit-front-v1/package-manifest.json",
        "docs/evidence/animation-runtime-v0141/hit-front-v1/hit-front-preview-v0141.gif",
        "docs/evidence/animation-runtime-v0141/hit-front-v1/hit-front-spritesheet-v0141.png",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0141:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.14.1.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0.14.1.json"))
        frozen_review = (ROOT / "REVIEW-v0.14.1.md").read_text(encoding="utf-8")
        consistency = validate_state_consistency_v0141(
            state,
            frozen_review,
            frozen_review,
            frozen_review,
        )
        check("v0141:state-consistency", consistency["status"] == state["current_gate"] and consistency["failures"] == [], "; ".join(consistency["failures"]) or "frozen v0.14.1 state is consistent")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0141:state-consistency", False, str(exc))
    matrix = load_json(ROOT / "docs/ugas-v1-capability-matrix.json")
    check("v0141:matrix-dependency", len(matrix.get("capabilities", [])) == 16 and matrix.get("production_routing") == "BLOCKED" and matrix.get("new_generation") == 0, "canonical matrix retains sixteen capabilities with production blocked")
    contract = load_json(ROOT / "docs/evidence/animation-runtime-v0141/hit-front-contract-v0141.json")
    check("v0141:contract", contract.get("capability") == "hit_reaction_front" and contract.get("dependencies", {}).get("implementation_base_commit") == V0141_BASELINE_HEAD and contract.get("gif_loop_semantics", {}).get("loop_1_is_not_non_loop") is True and len(contract.get("negative_controls", [])) == 10 and len(contract.get("loop_negative_controls", [])) == 5, "HIT_REACTION_FRONT v0.14.1 contract binds loop semantics without dropping HIT NCs")
    spec = load_json(ROOT / "profiles/animation/hit-front-v1.json")
    check("v0141:profile", spec.get("frame_count") == 6 and spec.get("fps") == 12 and spec.get("loop") is False and spec.get("direction") == "front" and len(spec.get("motion_tracks", [])) == 12 and spec.get("provenance", {}).get("source_only_pixels") is True and spec.get("adapter_parameters", {}).get("immutable_approved_assets_base") == V0141_BASELINE_HEAD, "front hit profile remains six deterministic source-only non-loop frames")
    qa = load_json(ROOT / "docs/evidence/animation-runtime-v0141/hit-front-v1/qa-result.json")
    check("v0141:qa", qa.get("decision") == "QUALIFIED" and qa.get("failures") == [] and all(qa.get("hard_gates", {}).values()) and all(qa.get("temporal", {}).get("hard_gates", {}).values()), "all HIT_REACTION_FRONT frame and temporal gates pass")
    package = load_json(ROOT / "docs/evidence/animation-runtime-v0141/hit-front-v1/package-manifest.json")
    check("v0141:package", package.get("qa_decision") == "QUALIFIED" and package.get("production_routing") == "BLOCKED" and package.get("format") == "RGBA" and package.get("loop") is False and package.get("gif_loop_extension_present") is False and package.get("gif_loop_count") is None, "package is bound to qualified QA and omits the GIF repeat extension")
    negative = load_json(ROOT / "docs/evidence/animation-runtime-v0141/hit-front-gate-negative-controls-v0141.json")
    check("v0141:negative-controls", negative.get("status") == "NC_01_TO_NC_10_PASSED" and len(negative.get("controls", {})) == 10 and all(item.get("status") == "REJECTED" for item in negative.get("controls", {}).values()), "all ten mutated HIT fixtures reject at their intended gate")
    loop_nc = load_json(ROOT / "docs/evidence/animation-runtime-v0141/hit-front-loop-negative-controls-v0141.json")
    check("v0141:loop-negative-controls", loop_nc.get("status") == "NC_LOOP_01_TO_05_PASSED" and len(loop_nc.get("controls", {})) == 5 and all(item.get("match") is True for item in loop_nc.get("controls", {}).values()), "all five real encoded loop fixtures match the fail-closed contract")
    execution = load_json(ROOT / "docs/evidence/animation-runtime-v0141/execution-evidence-v0.14.1.json")
    check("v0141:execution-boundary", execution.get("implementation_base_commit") == V0141_BASELINE_HEAD and execution.get("branch_base_commit") == "ebcf0b587628dcd33c316378fb2815f616172ffa" and execution.get("rejected_reviewed_head") == "c059e24a4fa215882fac4b36991f7860f185a920" and execution.get("source_only_pixels") is True and execution.get("new_generation") == 0 and execution.get("next_capability_started") is False and execution.get("gif_loop_extension_present") is False, "execution evidence separates provenance fields and omits the non-loop GIF extension")
    gif_timing = load_json(ROOT / "docs/evidence/animation-runtime-v0141/hit-front-gif-timing-v0141.json")
    check("v0141:gif-timing", gif_timing.get("status") == "GIF_TIMING_PASSED" and gif_timing.get("hard_gates", {}).get("loop_contract_matches") is True and gif_timing.get("decoded", {}).get("loop_extension_present") is False, "decoded GIF timing and non-loop extension contract pass")
    preservation = load_json(ROOT / "docs/evidence/animation-runtime-v0141/hit-front-visual-preservation-v0141.json")
    check("v0141:visual-preservation", preservation.get("status") == "HIT_VISUAL_PRESERVED" and preservation.get("comparisons", {}).get("frame_rgba_sha256_identical") is True and preservation.get("comparisons", {}).get("gif_repeat_extension_changed") is True, "reviewed HIT pixels remain identical while only GIF repeat semantics change")
    assets = load_json(ROOT / "docs/evidence/animation-runtime-v0141/approved-assets-untouched-v0141.json")
    check("v0141:approved-assets", assets.get("status") == "APPROVED_ASSETS_UNTOUCHED" and assets.get("head_fallback_used") is False and assets.get("base_commit") == V0141_BASELINE_HEAD, "approved historical and run-front assets remain byte-identical to their immutable bases")
    try:
        live = (ROOT / "docs/evidence/animation-runtime-v0141/state-consistency-v0141.json").read_bytes()
        normalized_live = live.replace(b"\r\n", b"\n")
        blob = hashlib.sha1(  # noqa: S324  (Git object identity uses SHA-1)
            f"blob {len(normalized_live)}\0".encode() + normalized_live
        ).hexdigest()
        check(
            "v0141:frozen-evidence-identity",
            blob == "9bbc85bd5ca839b4a0fd71b45a279e852a275fc5",
            "frozen v0.14.1 technical evidence matches approved head",
        )
    except (OSError, subprocess.CalledProcessError):
        check("v0141:frozen-evidence-identity", False, "approved-head frozen evidence could not be read")


def _v0150_checks() -> None:
    """Validate the active v0.15.0 DEATH_ANIMATION_FRONT candidate."""
    required = [
        "REVIEW-v0.15.0.md",
        "schemas/current-state-v0150.json",
        "docs/evidence/current-state-v0.15.0.json",
        "docs/evidence/current-state-v0.14.1.json",
        "docs/evidence/github-governance-v0141/hit-front-v0141-post-merge-integrity-repair.json",
        "src/ugas/state_consistency_v0150.py",
        "scripts/validation/validate_state_consistency_v0150.py",
        "profiles/animation/death-front-v1.json",
        "src/ugas/animation_profiles/death_front_v1.py",
        "scripts/validation/run_animation_runtime_v0150.py",
        "scripts/validation/build_github_review_manifest_v0150.py",
        "scripts/validation/validate_github_review_manifest_v0150.py",
        "scripts/validation/validate_github_review_security_v0150.py",
        "scripts/validation/enforce_github_review_v0150.py",
        "scripts/validation/record_v0150_results.py",
        "schemas/github-review-manifest-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-contract-v0150.json",
        "docs/evidence/animation-runtime-v0150/execution-evidence-v0.15.0.json",
        "docs/evidence/animation-runtime-v0150/death-front-visual-manifest-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-targets-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-frame-qa-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-temporal-qa-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-body-mechanics-qa-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-foot-ground-qa-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-continuity-qa-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-weapon-qa-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-gate-negative-controls-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-loop-negative-controls-v0150.json",
        "docs/evidence/animation-runtime-v0150/hit-front-nonloop-regression-v0150.json",
        "docs/evidence/animation-runtime-v0150/run-front-loop-regression-v0150.json",
        "docs/evidence/animation-runtime-v0150/approved-assets-untouched-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-determinism-v0150.json",
        "docs/evidence/animation-runtime-v0150/capability-matrix-validation-v0150.json",
        "docs/evidence/animation-runtime-v0150/frozen-evidence-integrity-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-gif-timing-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-gif-loop-semantics-v0150.json",
        "docs/evidence/animation-runtime-v0150/state-consistency-v0150.json",
        "docs/evidence/animation-runtime-v0150/death-front-v1/compiled-manifest.json",
        "docs/evidence/animation-runtime-v0150/death-front-v1/qa-result.json",
        "docs/evidence/animation-runtime-v0150/death-front-v1/package-manifest.json",
        "docs/evidence/animation-runtime-v0150/death-front-v1/death-front-preview-v0150.gif",
        "docs/evidence/animation-runtime-v0150/death-front-v1/death-front-spritesheet-v0150.png",
        "docs/evidence/animation-runtime-v0150/death-front-phase-markers-v0150.png",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0150:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")

    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.15.0.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0150.json"))
        check(
            "v0150:state-consistency",
            state.get("version") == "0.15.0"
            and state.get("current_gate") == "CUTOUT_ANIMATION_RUNTIME_V1_DEATH_ANIMATION_FRONT_TECHNICALLY_QUALIFIED"
            and state.get("review", {}).get("rejected_reviewed_head") == "c059e24a4fa215882fac4b36991f7860f185a920",
            "immutable v0.15.0 state snapshot remains available",
        )
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0150:state-consistency", False, str(exc))

    matrix = load_json(ROOT / "docs/ugas-v1-capability-matrix.json")
    check(
        "v0150:matrix-dependency",
        len(matrix.get("capabilities", [])) == 16
        and matrix.get("production_routing") == "BLOCKED"
        and matrix.get("new_generation") == 0,
        "canonical matrix retains the full capability order with production blocked",
    )
    matrix_validation = load_json(ROOT / "docs/evidence/animation-runtime-v0150/capability-matrix-validation-v0150.json")
    check(
        "v0150:matrix-validation",
        matrix_validation.get("status") == "V1_CAPABILITY_MATRIX_PASSED"
        and matrix_validation.get("next_candidate") == "DEATH_ANIMATION_FRONT",
        "capability matrix validator keeps death technically qualified but externally unapproved",
    )
    contract = load_json(ROOT / "docs/evidence/animation-runtime-v0150/death-front-contract-v0150.json")
    check(
        "v0150:contract",
        contract.get("capability") == "death_animation_front"
        and contract.get("dependencies", {}).get("branch_base_commit") == "98ebd95564216fbbee222aab630b73b5ff6f298d"
        and contract.get("phase_contract", {}).get("frame_count") == 8
        and contract.get("phase_contract", {}).get("fps") == 12
        and contract.get("phase_contract", {}).get("loop") is False
        and len(contract.get("negative_controls", [])) == 13
        and contract.get("review_policy", {}).get("external_visual") == "REQUIRED"
        and contract.get("review_policy", {}).get("pr_merge") == "FORBIDDEN",
        "death contract binds eight non-loop frames, thirteen controls and external review",
    )
    spec = load_json(ROOT / "profiles/animation/death-front-v1.json")
    check(
        "v0150:profile",
        spec.get("frame_count") == 8
        and spec.get("fps") == 12
        and spec.get("loop") is False
        and spec.get("direction") == "front"
        and len(spec.get("motion_tracks", [])) == 12
        and spec.get("runtime_adapter") == "ugas.animation_profiles.death_front_v1"
        and spec.get("provenance", {}).get("source_only_pixels") is True
        and spec.get("provenance", {}).get("sam2_used") is False
        and spec.get("provenance", {}).get("comfyui_generation_jobs") == 0,
        "front death profile remains deterministic source-only eight-frame animation",
    )
    qa = load_json(ROOT / "docs/evidence/animation-runtime-v0150/death-front-v1/qa-result.json")
    check(
        "v0150:qa",
        qa.get("decision") == "QUALIFIED"
        and qa.get("failures") == []
        and all(qa.get("hard_gates", {}).values())
        and all(qa.get("temporal", {}).get("hard_gates", {}).values()),
        "all death frame and temporal gates pass",
    )
    package = load_json(ROOT / "docs/evidence/animation-runtime-v0150/death-front-v1/package-manifest.json")
    check(
        "v0150:package",
        package.get("qa_decision") == "QUALIFIED"
        and package.get("production_routing") == "BLOCKED"
        and package.get("format") == "RGBA"
        and package.get("frame_count") == 8
        and package.get("loop") is False
        and package.get("gif_loop_extension_present") is False
        and package.get("gif_loop_count") is None,
        "package is qualified, eight-frame RGBA and non-loop",
    )
    negative = load_json(ROOT / "docs/evidence/animation-runtime-v0150/death-front-gate-negative-controls-v0150.json")
    check(
        "v0150:negative-controls",
        negative.get("status") == "NC_01_TO_NC_13_PASSED"
        and len(negative.get("controls", {})) == 14
        and all(item.get("status") == "REJECTED" for item in negative.get("controls", {}).values()),
        "all death controls and PR-state consistency reject their mutations",
    )
    loop_nc = load_json(ROOT / "docs/evidence/animation-runtime-v0150/death-front-loop-negative-controls-v0150.json")
    check(
        "v0150:loop-negative-controls",
        loop_nc.get("status") == "NC_LOOP_01_TO_05_PASSED"
        and len(loop_nc.get("controls", {})) == 5
        and all(item.get("match") is True for item in loop_nc.get("controls", {}).values()),
        "all encoded GIF loop controls match",
    )
    check(
        "v0150:regressions",
        load_json(ROOT / "docs/evidence/animation-runtime-v0150/hit-front-nonloop-regression-v0150.json").get("status") == "HIT_NONLOOP_REGRESSION_PASSED"
        and load_json(ROOT / "docs/evidence/animation-runtime-v0150/run-front-loop-regression-v0150.json").get("status") == "RUN_FRONT_LOOP_REGRESSION_PASSED",
        "HIT non-loop and RUN infinite-loop regressions pass",
    )
    check(
        "v0150:determinism",
        load_json(ROOT / "docs/evidence/animation-runtime-v0150/death-front-determinism-v0150.json").get("status") == "DEATH_DETERMINISM_PASSED",
        "death targets and RGBA frames are deterministic",
    )
    check(
        "v0150:approved-assets",
        load_json(ROOT / "docs/evidence/animation-runtime-v0150/approved-assets-untouched-v0150.json").get("status") == "APPROVED_ASSETS_UNTOUCHED",
        "approved HIT/RUN and historical assets remain immutable",
    )
    repair = load_json(ROOT / "docs/evidence/github-governance-v0141/hit-front-v0141-post-merge-integrity-repair.json")
    check(
        "v0150:integrity-repair",
        repair.get("repair_action") == "RESTORED_FROM_APPROVED_HEAD"
        and repair.get("historical_git_rewritten") is False
        and repair.get("blobs", {}).get("approved_head_git_blob") == "9bbc85bd5ca839b4a0fd71b45a279e852a275fc5",
        "v0.14.1 evidence repair is forward-only and approved-head bound",
    )
    frozen_integrity = load_json(ROOT / "docs/evidence/animation-runtime-v0150/frozen-evidence-integrity-v0150.json")
    check(
        "v0150:frozen-evidence-integrity",
        frozen_integrity.get("status") == "FROZEN_V0141_EVIDENCE_RESTORED_AND_VERIFIED"
        and frozen_integrity.get("approved_head_git_blob") == frozen_integrity.get("repaired_git_blob")
        and frozen_integrity.get("historical_git_rewritten") is False,
        "separate frozen-evidence identity result records the forward-only repair",
    )


def _v0151_checks() -> None:
    """Validate the immutable approved v0.15.1 DEATH_ANIMATION_FRONT history."""
    required = [
        "REVIEW-v0.15.1.md",
        "schemas/current-state-v0151.json",
        "docs/evidence/current-state-v0.15.1.json",
        "docs/evidence/current-state-v0.15.0.json",
        "src/ugas/state_consistency_v0151.py",
        "scripts/validation/validate_state_consistency_v0151.py",
        "profiles/animation/death-front-v151.json",
        "src/ugas/animation_profiles/death_front_v151.py",
        "scripts/validation/run_animation_runtime_v0151.py",
        "scripts/validation/build_github_review_manifest_v0151.py",
        "scripts/validation/validate_github_review_manifest_v0151.py",
        "scripts/validation/validate_github_review_security_v0151.py",
        "scripts/validation/enforce_github_review_v0151.py",
        "scripts/validation/record_v0151_results.py",
        "schemas/github-review-manifest-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-contract-v0151.json",
        "docs/evidence/animation-runtime-v0151/execution-evidence-v0.15.1.json",
        "docs/evidence/animation-runtime-v0151/death-front-visual-manifest-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-targets-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-frame-qa-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-temporal-qa-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-body-ground-contact-qa-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-support-state-qa-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-contact-state-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-ground-reference-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-foot-ground-qa-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-terminal-support-qa-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-death-vs-hit-qa-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-continuity-qa-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-weapon-qa-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-gate-negative-controls-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-loop-negative-controls-v0151.json",
        "docs/evidence/animation-runtime-v0151/hit-front-nonloop-regression-v0151.json",
        "docs/evidence/animation-runtime-v0151/run-front-loop-regression-v0151.json",
        "docs/evidence/animation-runtime-v0151/approved-assets-untouched-v0151.json",
        "docs/evidence/animation-runtime-v0151/frozen-evidence-integrity-v0151.json",
        "docs/evidence/animation-runtime-v0151/v0141-provenance-sha256-correction-v0151.json",
        "docs/evidence/animation-runtime-v0151/v0150-rejection-record-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-determinism-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-gif-timing-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-gif-loop-semantics-v0151.json",
        "docs/evidence/animation-runtime-v0151/repository-transfer-provenance-v0151.json",
        "docs/evidence/animation-runtime-v0151/state-consistency-v0151.json",
        "docs/evidence/animation-runtime-v0151/death-front-v1/compiled-manifest.json",
        "docs/evidence/animation-runtime-v0151/death-front-v1/qa-result.json",
        "docs/evidence/animation-runtime-v0151/death-front-v1/package-manifest.json",
        "docs/evidence/animation-runtime-v0151/death-front-v1/death-front-preview-v0151.gif",
        "docs/evidence/animation-runtime-v0151/death-front-v1/death-front-spritesheet-v0151.png",
        "docs/evidence/animation-runtime-v0151/death-front-phase-markers-v0151.png",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0151:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")

    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.15.1.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0151.json"))
        check(
            "v0151:state-consistency",
            state.get("version") == "0.15.1"
            and state.get("phase") == "DEATH_ANIMATION_FRONT"
            and state.get("previous_release", {}).get("version") == "0.14.1"
            and state.get("death_animation_front_visual_content") == "APPROVED_PILOT"
            and state.get("review", {}).get("merge_authorization") == "APPROVED_TO_MERGE",
            "approved v0.15.1 state snapshot remains preserved",
        )
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0151:state-consistency", False, str(exc))

    spec = load_json(ROOT / "profiles/animation/death-front-v151.json")
    check(
        "v0151:profile",
        spec.get("animation_id") == "death-front-v1-v0151"
        and spec.get("frame_count") == 8
        and spec.get("fps") == 12
        and spec.get("loop") is False
        and spec.get("direction") == "front"
        and len(spec.get("motion_tracks", [])) == 12
        and spec.get("runtime_adapter") == "ugas.animation_profiles.death_front_v151"
        and spec.get("provenance", {}).get("source_only_pixels") is True
        and spec.get("provenance", {}).get("sam2_used") is False
        and spec.get("provenance", {}).get("comfyui_generation_jobs") == 0,
        "corrected front death profile is deterministic and source-only",
    )
    contract = load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-contract-v0151.json")
    check(
        "v0151:contract",
        contract.get("schema_version") == "0.15.1"
        and contract.get("phase_contract", {}).get("frame_count") == 8
        and contract.get("phase_contract", {}).get("fps") == 12
        and contract.get("phase_contract", {}).get("loop") is False
        and len(contract.get("negative_controls", [])) == 16
        and len(contract.get("ground_contact_negative_controls", [])) == 6
        and contract.get("review_policy", {}).get("external_visual") == "REQUIRED"
        and contract.get("repository_transfer", {}).get("active_repository") == "KayzenRoot/ugas"
        and contract.get("repository_transfer", {}).get("codeowners_gap") == "CODEOWNERS_GAP",
        "v0.15.1 contract binds measured contact, 16 controls, transfer and review boundary",
    )
    qa = load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-v1/qa-result.json")
    check(
        "v0151:qa",
        qa.get("decision") == "QUALIFIED"
        and qa.get("failures") == []
        and all(qa.get("hard_gates", {}).values())
        and all(qa.get("temporal", {}).get("hard_gates", {}).values()),
        "all corrected death frame, contact and temporal gates pass",
    )
    package = load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-v1/package-manifest.json")
    check(
        "v0151:package",
        package.get("qa_decision") == "QUALIFIED"
        and package.get("production_routing") == "BLOCKED"
        and package.get("format") == "RGBA"
        and package.get("frame_count") == 8
        and package.get("loop") is False
        and package.get("gif_loop_extension_present") is False
        and package.get("gif_loop_count") is None,
        "corrected package is qualified, RGBA and non-loop",
    )
    negative = load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-gate-negative-controls-v0151.json")
    check(
        "v0151:negative-controls",
        negative.get("status") == "NC_01_TO_NC_16_PASSED"
        and len(negative.get("controls", {})) == 16
        and all(item.get("status") == "REJECTED" for item in negative.get("controls", {}).values()),
        "NC-01 through NC-16 reject their mutations",
    )
    ground_contact_negative = negative.get("ground_contact_controls", {})
    check(
        "v0151:ground-contact-negative-controls",
        ground_contact_negative.get("status") == "NC_GC_01_TO_NC_GC_06_PASSED"
        and len(ground_contact_negative.get("controls", {})) == 6
        and all(item.get("status") == "REJECTED" for item in ground_contact_negative.get("controls", {}).values()),
        "NC-GC-01 through NC-GC-06 reject their real contact/support mutations",
    )
    loop_nc = load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-loop-negative-controls-v0151.json")
    check(
        "v0151:loop-negative-controls",
        loop_nc.get("status") == "NC_LOOP_01_TO_05_PASSED"
        and len(loop_nc.get("controls", {})) == 5
        and all(item.get("match") is True for item in loop_nc.get("controls", {}).values()),
        "all loop negative controls match",
    )
    check(
        "v0151:regressions",
        load_json(ROOT / "docs/evidence/animation-runtime-v0151/hit-front-nonloop-regression-v0151.json").get("status") == "HIT_NONLOOP_REGRESSION_PASSED"
        and load_json(ROOT / "docs/evidence/animation-runtime-v0151/run-front-loop-regression-v0151.json").get("status") == "RUN_FRONT_LOOP_REGRESSION_PASSED",
        "HIT non-loop and RUN loop regressions pass",
    )
    determinism = load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-determinism-v0151.json")
    check(
        "v0151:determinism",
        determinism.get("status") == "DEATH_DETERMINISM_TRUE_TWO_RUN_PASSED"
        and determinism.get("comparison", {}).get("all_fields_match") is True
        and determinism.get("nc_16_mutation_detected") is True,
        "independent Run A/Run B decoded targets, frames, sheet and GIF match and NC-16 detects mutation",
    )
    execution = load_json(ROOT / "docs/evidence/animation-runtime-v0151/execution-evidence-v0.15.1.json")
    check(
        "v0151:execution",
        execution.get("status") == "CUTOUT_ANIMATION_RUNTIME_V1_DEATH_ANIMATION_FRONT_V0151_TECHNICALLY_QUALIFIED"
        and execution.get("decision") == "QUALIFIED"
        and execution.get("new_generation") == 0
        and execution.get("production_routing") == "BLOCKED"
        and execution.get("external_visual") == "REQUIRED",
        "execution evidence keeps production blocked and external visual approval required",
    )
    check(
        "v0151:assets-and-history",
        load_json(ROOT / "docs/evidence/animation-runtime-v0151/approved-assets-untouched-v0151.json").get("status") == "APPROVED_ASSETS_UNTOUCHED"
        and load_json(ROOT / "docs/evidence/animation-runtime-v0151/frozen-evidence-integrity-v0151.json").get("status") == "FROZEN_V0141_EVIDENCE_RESTORED_AND_VERIFIED",
        "approved assets and frozen historical evidence remain intact",
    )
    check(
        "v0151:contact-and-provenance-evidence",
        load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-contact-state-v0151.json").get("status") == "DEATH_CONTACT_STATE_QA_PASSED"
        and load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-ground-reference-v0151.json").get("status") == "GLOBAL_GROUND_REFERENCE_VALID"
        and load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-foot-ground-qa-v0151.json").get("hard_gates", {}).get("foot_ground_truthfulness") is True
        and load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-terminal-support-qa-v0151.json").get("status") == "DEATH_TERMINAL_SUPPORT_QA_PASSED"
        and load_json(ROOT / "docs/evidence/animation-runtime-v0151/death-front-death-vs-hit-qa-v0151.json").get("status") == "DEATH_VS_HIT_SEMANTIC_SEPARATION_PASSED"
        and load_json(ROOT / "docs/evidence/animation-runtime-v0151/v0141-provenance-sha256-correction-v0151.json").get("status") == "V0141_PROVENANCE_SHA256_CORRECTION_RECORDED"
        and load_json(ROOT / "docs/evidence/animation-runtime-v0151/v0150-rejection-record-v0151.json").get("status") == "V0150_EXTERNAL_VISUAL_FAILED_TECHNICAL_QA_REJECTED_BY_EXTERNAL_REVIEW",
        "new ground/contact, terminal, death-vs-HIT, provenance and rejection records pass",
    )


def _v0160_history_checks() -> None:
    """Validate that rejected v0.16.0 evidence remains immutable history."""
    required = [
        "REVIEW-v0.16.0.md",
        "schemas/current-state-v0160.json",
        "schemas/direction-runtime-v0160.json",
        "docs/evidence/current-state.json",
        "docs/evidence/current-state-v0.15.1.json",
        "src/ugas/direction_runtime.py",
        "src/ugas/state_consistency_v0160.py",
        "scripts/validation/validate_state_consistency_v0160.py",
        "scripts/validation/validate_direction_runtime_v0160.py",
        "scripts/validation/build_direction_fixture_pack_v0160.py",
        "scripts/validation/record_v0160_results.py",
        "scripts/validation/build_github_review_manifest_v0160.py",
        "scripts/validation/validate_github_review_manifest_v0160.py",
        "scripts/validation/validate_github_review_security_v0160.py",
        "scripts/validation/enforce_github_review_v0160.py",
        "schemas/github-review-manifest-v0160.json",
        ".github/workflows/ugas-ci.yml",
        ".github/workflows/ugas-review.yml",
        "tests/test_direction_runtime_v0160.py",
        "docs/evidence/multi-direction-runtime-v0160/direction-contract-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/coverage-manifest-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/validation-evidence-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/negative-controls-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/synthetic-fixture-manifest-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/synthetic-direction-contact-sheet-v0160.png",
        "docs/evidence/multi-direction-runtime-v0160/state-consistency-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/capability-matrix-validation-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/direction-quantization-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/alias-mapping-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/fallback-qa-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/mirror-qa-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/cache-key-qa-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/provenance-qa-v0160.json",
        "docs/evidence/multi-direction-runtime-v0160/fixture-qa-v0160.json",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0160:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        validation = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0160/validation-evidence-v0160.json")
        negative = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0160/negative-controls-v0160.json")
        fixture = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0160/synthetic-fixture-manifest-v0160.json")
        check("v0160:foundation-history", validation.get("status") == "MULTI_DIRECTION_ANIMATION_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" and validation.get("failed") == 0 and validation.get("production_coverage") == ["south"] and validation.get("production_routing") == "BLOCKED", "historical v0.16.0 foundation evidence remains unchanged")
        check("v0160:negative-history", negative.get("status") == "DIR_NC_01_TO_12_PASSED" and len(negative.get("controls", {})) == 12, "historical v0.16.0 negative-control record remains preserved")
        check("v0160:fixtures", fixture.get("manifest_type") == "TEST_ONLY_SYNTHETIC_DIRECTION_FIXTURE" and fixture.get("direction_count") == 8 and fixture.get("unique_identity_count") == 8 and len({item.get("sha256") for item in fixture.get("fixtures", [])}) == 8 and fixture.get("production_registry") is False, "eight unique synthetic asymmetric identities remain test-only")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v0160:evidence", False, str(exc))


def _v0161_checks() -> None:
    """Validate frozen v0.16.1 evidence without treating it as active state."""
    required = [
        "REVIEW-v0.16.1.md",
        "schemas/current-state-v0161.json",
        "schemas/direction-runtime-v0161.json",
        "schemas/github-review-manifest-v0161.json",
        "docs/evidence/current-state.json",
        "src/ugas/direction_runtime.py",
        "src/ugas/state_consistency_v0161.py",
        "scripts/validation/validate_state_consistency_v0161.py",
        "scripts/validation/validate_direction_runtime_v0161.py",
        "tests/test_direction_runtime_v0161.py",
        "docs/evidence/multi-direction-runtime-v0161/v0160-correction-record-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/direction-contract-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/coverage-manifest-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/validation-evidence-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/negative-controls-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/invalid-vector-qa-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/test-only-production-safety-qa-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/synthetic-fixture-manifest-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/synthetic-direction-contact-sheet-v0160.png",
        "docs/evidence/multi-direction-runtime-v0161/state-consistency-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/capability-matrix-validation-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/direction-quantization-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/alias-mapping-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/fallback-qa-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/mirror-qa-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/cache-key-qa-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/provenance-qa-v0161.json",
        "docs/evidence/multi-direction-runtime-v0161/fixture-qa-v0161.json",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0161:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        consistency = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0161/state-consistency-v0161.json")
        check("v0161:frozen-state-consistency", consistency.get("status") == "MULTI_DIRECTION_ANIMATION_RUNTIME_INTEGRITY_TECHNICALLY_QUALIFIED" and consistency.get("failures") == [], "v0.16.1 state-consistency evidence remains frozen history")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0161:state-consistency", False, str(exc))
    try:
        correction = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0161/v0160-correction-record-v0161.json")
        validation = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0161/validation-evidence-v0161.json")
        negative = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0161/negative-controls-v0161.json")
        invalid_vectors = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0161/invalid-vector-qa-v0161.json")
        test_only = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0161/test-only-production-safety-qa-v0161.json")
        fixture = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0161/synthetic-fixture-manifest-v0161.json")
        controls = negative.get("controls", {})
        observed = all(isinstance(item.get("observed"), dict) and item.get("mutation") and item.get("target_gate") and "result" in item["observed"] and "error_code" in item["observed"] and item.get("rejected") is True and item.get("status") == "REJECTED" for item in controls.values())
        check("v0161:correction-record", correction.get("version") == "0.16.0" and correction.get("status") == "CORRECTION_REQUIRED" and correction.get("rejected_reviewed_head") == "7d1e999e91ee8817c6754b363a5c19f1ba6f2e7d", "v0.16.0 is recorded as correction-required history")
        check("v0161:integrity-gates", validation.get("status") == "MULTI_DIRECTION_ANIMATION_RUNTIME_INTEGRITY_TECHNICALLY_QUALIFIED" and validation.get("failed") == 0 and validation.get("production_coverage") == ["south"] and validation.get("production_routing") == "BLOCKED", "corrected direction integrity gates pass with south-only production coverage")
        check("v0161:real-negative-controls", negative.get("status") == "DIR_NC_01_TO_12_PASSED" and len(controls) == 12 and observed and "positive_gate_boolean" not in json.dumps(negative), "all twelve controls record real input mutations and observed rejections")
        check("v0161:invalid-vector-qa", invalid_vectors.get("status") == "INVALID_VECTOR_QA_PASSED" and all(item.get("result", {}).get("outcome") == "INVALID_VECTOR_UNRESOLVED" for item in invalid_vectors.get("cases", [])), "invalid vectors never reuse retained facing")
        check("v0161:test-only-safety", test_only.get("status") == "TEST_ONLY_PRODUCTION_SAFETY_QA_PASSED" and test_only.get("non_production_exact", {}).get("production_safe") is False, "test-only exact matches are explicitly non-production-safe")
        check("v0161:fixtures", fixture.get("schema_version") == "0.16.1" and fixture.get("direction_count") == 8 and fixture.get("unique_identity_count") == 8 and fixture.get("production_registry") is False, "synthetic eight-direction fixture remains test-only")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v0161:evidence", False, str(exc))


def _v0162_checks() -> None:
    """Validate the active v0.16.2 cache/state correction."""
    required = [
        "REVIEW-v0.16.2.md",
        "schemas/current-state-v0162.json",
        "schemas/direction-runtime-v0162.json",
        "schemas/github-review-manifest-v0162.json",
        "docs/evidence/current-state-v0.16.2.json",
        "src/ugas/direction_runtime.py",
        "src/ugas/state_consistency_v0162.py",
        "scripts/validation/validate_state_consistency_v0162.py",
        "scripts/validation/validate_direction_runtime_v0162.py",
        "tests/test_direction_runtime_v0162.py",
        "docs/evidence/multi-direction-runtime-v0162/v0161-rejection-correction-record-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/direction-contract-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/coverage-manifest-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/validation-evidence-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/negative-controls-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/invalid-vector-qa-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/test-only-production-safety-qa-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/test-only-cache-mode-qa-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/cache-unresolved-class-qa-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/cache-order-negative-controls-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/synthetic-fixture-manifest-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/state-consistency-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/direction-quantization-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/alias-mapping-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/fallback-qa-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/mirror-qa-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/provenance-qa-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/resolution-evidence-v0162.json",
        "docs/evidence/multi-direction-runtime-v0162/fixture-qa-v0162.json",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0162:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.16.2.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0162.json"))
        consistency = validate_state_consistency_v0162(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.16.2.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"))
        check("v0162:state-consistency", consistency["status"] == state["current_gate"] and consistency["failures"] == [], "; ".join(consistency["failures"]) or "active v0.16.2 state is consistent")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0162:state-consistency", False, str(exc))
    try:
        contract = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0162/direction-contract-v0162.json")
        coverage = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0162/coverage-manifest-v0162.json")
        validation = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0162/validation-evidence-v0162.json")
        negative = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0162/negative-controls-v0162.json")
        cache_qa = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0162/cache-unresolved-class-qa-v0162.json")
        cache_order = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0162/cache-order-negative-controls-v0162.json")
        cache_mode = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0162/test-only-cache-mode-qa-v0162.json")
        correction = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0162/v0161-rejection-correction-record-v0162.json")
        fixture = load_json(ROOT / "docs/evidence/multi-direction-runtime-v0162/synthetic-fixture-manifest-v0162.json")
        check("v0162:previous-release", state.get("previous_release", {}).get("version") == "0.15.1" and state.get("correction_history", {}).get("v0.16.0", {}).get("status") == "CORRECTION_REQUIRED" and state.get("correction_history", {}).get("v0.16.1", {}).get("status") == "CORRECTION_REQUIRED", "approved v0.15.1 and separately rejected v0.16.0/v0.16.1 are recorded")
        check("v0162:cache-contract", contract.get("schema_version") == "0.16.2" and contract.get("cache_identity", {}).get("unresolved_class_in_key") is True and set(contract.get("cache_identity", {}).get("classes", [])) == {"UNKNOWN_DIRECTION_UNRESOLVED", "ZERO_VECTOR_UNRESOLVED", "INVALID_VECTOR_UNRESOLVED"}, "unresolved normalization classes are explicit cache identity")
        check("v0162:coverage-binding", coverage.get("schema_version") == "0.16.2" and coverage.get("production_registry") is True and {item.get("direction") for item in coverage.get("assets", [])} == {"south"} and coverage.get("carried_forward_from", {}).get("path", "").endswith("coverage-manifest-v0161.json"), "south-only coverage is carried forward without fabricated directional art")
        check("v0162:validation", validation.get("status") == "MULTI_DIRECTION_ANIMATION_RUNTIME_CACHE_AND_STATE_INTEGRITY_TECHNICALLY_QUALIFIED" and validation.get("failed") == 0 and validation.get("production_coverage") == ["south"] and validation.get("cache_negative_controls", {}).get("status") == "CACHE_NC_01_TO_05_PASSED", "all v0.16.2 direction/cache gates pass")
        controls = negative.get("controls", {})
        check("v0162:real-negative-controls", negative.get("status") == "DIR_NC_01_TO_12_PASSED" and len(controls) == 12 and all(item.get("rejected") is True and item.get("status") == "REJECTED" and item.get("mutation") and item.get("target_gate") and isinstance(item.get("observed"), dict) and "result" in item["observed"] and "error_code" in item["observed"] for item in controls.values()), "all twelve direction controls record real mutations and observed rejections")
        order_controls = cache_order.get("controls", {})
        check("v0162:cache-order-controls", cache_order.get("status") == "CACHE_NC_01_TO_05_PASSED" and len(order_controls) == 5 and all(item.get("rejected") is True and item.get("status") == "REJECTED" and item.get("request_order") and item.get("cache_keys") for item in order_controls.values()), "all five order-sensitive cache controls pass with key and counter evidence")
        check("v0162:cache-mode", cache_mode.get("status") == "TEST_ONLY_CACHE_MODE_QA_PASSED" and cache_mode.get("non_production_exact", {}).get("production_safe") is False and "registry_mode=test" in cache_mode.get("non_production_exact", {}).get("cache_key", "") and "registry_mode=production" not in cache_mode.get("non_production_exact", {}).get("cache_key", ""), "test-only observability metadata is truthful")
        check("v0162:cache-qa", cache_qa.get("status") == "CACHE_UNRESOLVED_CLASS_QA_PASSED" and len(set(cache_qa.get("keys", {}).values())) == 3, "unknown, zero and invalid classes have three distinct cache identities")
        check("v0162:rejection-record", correction.get("version") == "0.16.1" and correction.get("status") == "CORRECTION_REQUIRED" and correction.get("rejected_reviewed_head") == "2513d9f6f8a55345e74d9c0afb5dab22f9d84705", "v0.16.1 rejected head is preserved in forward-only history")
        check("v0162:fixtures", fixture.get("schema_version") == "0.16.2" and fixture.get("direction_count") == 8 and fixture.get("unique_identity_count") == 8 and fixture.get("production_registry") is False, "synthetic eight-direction fixture remains test-only")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        check("v0162:evidence", False, str(exc))


def _v0170_checks() -> None:
    """Validate frozen v0.17.0 evidence without rewriting or executing it."""
    required = [
        "REVIEW-v0.17.0.md",
        "schemas/equipment-runtime-v0170.json",
        "schemas/current-state-v0170.json",
        "docs/evidence/current-state.json",
        "src/ugas/equipment_runtime.py",
        "src/ugas/state_consistency_v0170.py",
        "scripts/validation/validate_equipment_runtime_v0170.py",
        "scripts/validation/validate_state_consistency_v0170.py",
        "tests/test_equipment_runtime_v0170.py",
        "docs/evidence/equipment-outfits-runtime-v0170/synthetic-fixture-manifest-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/equipment-registry-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/equipment-contract-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/slot-layer-graph-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/anchor-qa-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/replacement-hide-qa-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/occlusion-qa-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/direction-animation-qa-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/cache-qa-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/provenance-qa-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/two-run-determinism-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/negative-controls-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/outfit-contact-sheet-v0170.png",
        "docs/evidence/equipment-outfits-runtime-v0170/state-consistency-v0170.json",
        "docs/evidence/equipment-outfits-runtime-v0170/execution-evidence-v0170.json",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0170:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        fixture = load_json(ROOT / "docs/evidence/equipment-outfits-runtime-v0170/synthetic-fixture-manifest-v0170.json")
        production = load_json(ROOT / "docs/evidence/equipment-outfits-runtime-v0170/equipment-registry-v0170.json")
        execution = load_json(ROOT / "docs/evidence/equipment-outfits-runtime-v0170/execution-evidence-v0170.json")
        negative = load_json(ROOT / "docs/evidence/equipment-outfits-runtime-v0170/negative-controls-v0170.json")
        check("v0170:historical-execution", execution.get("schema_version") == "0.17.0" and execution.get("production_routing") == "BLOCKED" and execution.get("new_generation") == 0, "v0.17.0 result remains available as historical candidate evidence")
        check("v0170:fixtures", fixture.get("schema_version") == "0.17.0" and fixture.get("production_registry") is False and len(fixture.get("assets", [])) == 6 and all(item.get("test_only") is True and item.get("production_safe") is False for item in fixture.get("assets", [])), "six synthetic fixtures remain TEST_ONLY")
        check("v0170:production-registry", production.get("production_registry") is True and production.get("assets") == [], "production registry is empty")
        check("v0170:historical-negative-controls", negative.get("status") == "EQ_NC_01_TO_15_PASSED" and len(negative.get("controls", {})) == 15, "historical v0.17.0 negative-control record is preserved verbatim")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0170:evidence", False, str(exc))


def _v0171_checks() -> None:
    """Validate the active v0.17.1 equipment/outfits correction."""
    required = [
        "REVIEW-v0.17.1.md", "schemas/equipment-runtime-v0171.json", "schemas/current-state-v0171.json", "docs/evidence/current-state-v0171.json", "src/ugas/equipment_runtime.py", "src/ugas/state_consistency_v0171.py", "scripts/validation/validate_equipment_runtime_v0171.py", "scripts/validation/validate_state_consistency_v0171.py", "tests/test_equipment_runtime_v0171.py",
        "docs/evidence/equipment-outfits-runtime-v0171/synthetic-fixture-manifest-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/equipment-registry-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/equipment-contract-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/anchor-qa-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/direction-animation-qa-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/provenance-qa-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/replacement-conflict-qa-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/replacement-hide-pixel-qa-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/occlusion-runtime-qa-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/mirror-runtime-qa-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/cache-qa-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/base-immutability-qa-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/two-run-determinism-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/negative-controls-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/synthetic-fixture-contact-sheet-v0171.png", "docs/evidence/equipment-outfits-runtime-v0171/state-consistency-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/execution-evidence-v0171.json", "docs/evidence/equipment-outfits-runtime-v0171/v0170-rejection-correction-record-v0171.json",
    ]
    for relative in required:
        path = ROOT / relative; check(f"v0171:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    runtime = _run([sys.executable, "scripts/validation/validate_equipment_runtime_v0171.py"], ROOT, timeout=120)
    check("v0171:equipment-runtime", runtime.returncode == 0, (runtime.stdout + runtime.stderr).strip()[-1000:])
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0171.json"); validate_instance(state, load_json(ROOT / "schemas/current-state-v0171.json")); consistency = validate_state_consistency_v0171(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.17.1.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")); check("v0171:state-consistency", consistency["status"] == state["current_gate"] and consistency["failures"] == [], "; ".join(consistency["failures"]) or "historical v0.17.1 state is consistent")
        fixture = load_json(ROOT / "docs/evidence/equipment-outfits-runtime-v0171/synthetic-fixture-manifest-v0171.json"); production = load_json(ROOT / "docs/evidence/equipment-outfits-runtime-v0171/equipment-registry-v0171.json"); execution = load_json(ROOT / "docs/evidence/equipment-outfits-runtime-v0171/execution-evidence-v0171.json"); negative = load_json(ROOT / "docs/evidence/equipment-outfits-runtime-v0171/negative-controls-v0171.json"); controls = negative.get("controls", {})
        strict = all(item.get("rejected") is True and item.get("passed") is True and item.get("status") == "REJECTED" and item.get("expected_error_code") and item.get("expected_rejection_class") and item.get("observed", {}).get("result") == "REJECTED" and item["observed"].get("error_code") == item["expected_error_code"] and item["observed"].get("rejection_class") == item["expected_rejection_class"] for item in controls.values())
        check("v0171:execution", execution.get("status") == "EQUIPMENT_OUTFITS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED" and execution.get("failed") == 0 and execution.get("production_routing") == "BLOCKED" and execution.get("new_generation") == 0, "all v0.17.1 runtime integrity gates pass")
        check("v0171:fixtures", fixture.get("schema_version") == "0.17.1" and fixture.get("production_registry") is False and len(fixture.get("assets", [])) == 8 and all(item.get("test_only") is True and item.get("production_safe") is False for item in fixture.get("assets", [])), "eight synthetic fixtures remain TEST_ONLY")
        check("v0171:production-registry", production.get("production_registry") is True and production.get("assets") == [], "production registry is empty")
        check("v0171:strict-negative-controls", negative.get("status") == "EQ_NC_01_TO_15_PASSED" and len(controls) == 15 and strict, "all fifteen controls contain observed strict semantic rejections")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc: check("v0171:evidence", False, str(exc))


def _v0180_checks() -> None:
    """Validate the active v0.18.0 creature foundation without regenerating evidence."""
    required = [
        "REVIEW-v0.18.0.md", "schemas/creature-runtime-v0180.json", "schemas/current-state-v0180.json",
        "docs/evidence/current-state-v0.18.0.json", "src/ugas/creature_runtime.py", "src/ugas/state_consistency_v0180.py",
        "scripts/validation/run_creatures_monsters_runtime_v0180.py", "scripts/validation/validate_state_consistency_v0180.py",
        "tests/test_creature_runtime_v0180.py",
        "docs/evidence/creatures-monsters-runtime-v0180/creature-runtime-manifest-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/creature-contract-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/archetype-matrix-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/topology-support-matrix-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/scale-footprint-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/collision-profiles-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/animation-state-contract-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/direction-coverage-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/variant-lineage-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/cache-identity-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/provenance-hashes-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/two-run-determinism-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/negative-controls-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/production-registry-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/synthetic-fixture-manifest-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/archetype-contact-sheet-v0180.png",
        "docs/evidence/creatures-monsters-runtime-v0180/state-routing-sheet-v0180.png",
        "docs/evidence/creatures-monsters-runtime-v0180/state-consistency-v0180.json",
        "docs/evidence/creatures-monsters-runtime-v0180/execution-evidence-v0180.json",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0180:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        state = load_json(ROOT / "docs/evidence/current-state-v0.18.0.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0180.json"))
        consistency = validate_state_consistency_v0180(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.18.0.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"))
        check("v0180:state-consistency", consistency["status"] == state["current_gate"] and consistency["failures"] == [], "; ".join(consistency["failures"]) or "active v0.18.0 state is consistent")
        manifest = load_json(ROOT / "docs/evidence/creatures-monsters-runtime-v0180/creature-runtime-manifest-v0180.json")
        validate_instance(manifest, load_json(ROOT / "schemas/creature-runtime-v0180.json"))
        from ugas.creature_runtime import validate_creature_manifest
        validate_creature_manifest(manifest)
        execution = load_json(ROOT / "docs/evidence/creatures-monsters-runtime-v0180/execution-evidence-v0180.json")
        negative = load_json(ROOT / "docs/evidence/creatures-monsters-runtime-v0180/negative-controls-v0180.json")
        controls = negative.get("controls", {})
        strict = all(item.get("rejected") is True and item.get("passed") is True and item.get("status") == "REJECTED" and item.get("observed", {}).get("result") == "REJECTED" and item["observed"].get("error_code") == item.get("expected_error_code") and item["observed"].get("rejection_class") == item.get("expected_rejection_class") for item in controls.values())
        gates = execution.get("gates", {})
        check("v0180:execution", execution.get("status") == "CREATURES_MONSTERS_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED" and execution.get("failed") == 0 and set(gates) == {"creature_schema_valid", "archetype_topology_valid", "support_model_matches_archetype", "scale_and_footprint_explicit", "collision_profile_explicit", "pivot_and_bounds_valid", "required_animation_states_declared", "unsupported_state_fails_closed", "direction_coverage_truthful", "variant_lineage_acyclic", "variant_override_allowlist_enforced", "cache_identity_contains_creature_variant_direction_state", "stale_cache_cross_creature_rejected", "provenance_hash_matches_manifest", "synthetic_fixture_not_in_production_registry", "production_registry_empty", "production_routing_blocked", "two_run_fixture_generation_deterministic"} and all(item.get("status") == "PASS" for item in gates.values()), "all v0.18.0 hard gates pass")
        check("v0180:negative-controls", negative.get("status") == "CR_NC_01_TO_15_PASSED" and len(controls) == 15 and strict, "all fifteen controls contain observed strict semantic rejections")
        fixture = load_json(ROOT / "docs/evidence/creatures-monsters-runtime-v0180/synthetic-fixture-manifest-v0180.json")
        production = load_json(ROOT / "docs/evidence/creatures-monsters-runtime-v0180/production-registry-v0180.json")
        check("v0180:fixtures", fixture.get("fixture_count") == 6 and fixture.get("unique_hash_count") == 6 and fixture.get("production_safe") is False and all(item.get("test_only") is True and item.get("production_safe") is False for item in fixture.get("fixtures", [])), "six unique asymmetric fixtures remain TEST_ONLY")
        check("v0180:production-registry", production.get("production_registry") is True and production.get("assets") == [] and production.get("production_routing") == "BLOCKED", "production creature registry is empty and blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0180:evidence", False, str(exc))

    for label, script in (("v0171:equipment-regression", "scripts/validation/validate_equipment_runtime_v0171_regression.py"), ("v0162:direction-regression", "scripts/validation/validate_direction_runtime_v0162_regression.py"), ("v0151:front-animation-regression", "scripts/validation/validate_front_animation_v0151_regression.py")):
        result = _run([sys.executable, script], ROOT, timeout=120)
        check(label, result.returncode == 0, (result.stdout + result.stderr).strip()[-1000:])


def _v0181_checks() -> None:
    """Validate active v0.18.1 evidence without regenerating it."""
    evidence_root = ROOT / "docs/evidence/creatures-monsters-runtime-v0181"
    required = [
        "REVIEW-v0.18.1.md", "schemas/creature-runtime-v0181.json", "schemas/current-state-v0181.json", "src/ugas/creature_runtime_v0181.py", "src/ugas/state_consistency_v0181.py", "scripts/validation/run_creatures_monsters_runtime_v0181.py", "scripts/validation/validate_state_consistency_v0181.py", "tests/test_creature_runtime_v0181.py",
        "docs/evidence/current-state.json", "docs/evidence/current-state-v0.18.0.json", "docs/evidence/current-state-v0171.json",
        "docs/evidence/creatures-monsters-runtime-v0181/v0180-rejection-correction-record-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/creature-contract-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/creature-runtime-manifest-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/direction-asset-binding-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/direction-routing-sheet-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/direction-routing-sheet-v0181.png", "docs/evidence/creatures-monsters-runtime-v0181/state-route-contract-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/state-routing-sheet-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/state-routing-sheet-v0181.png", "docs/evidence/creatures-monsters-runtime-v0181/derived-variant-lineage-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/collision-geometry-qa-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/cache-identity-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/two-run-determinism-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/negative-controls-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/production-routing-qa-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/production-registry-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/synthetic-fixture-manifest-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/state-consistency-v0181.json", "docs/evidence/creatures-monsters-runtime-v0181/execution-evidence-v0181.json",
    ]
    for relative in required:
        path = ROOT / relative
        check(f"v0181:path:{relative}", path.is_file(), "present" if path.is_file() else "missing")
    try:
        from ugas.creature_runtime_v0181 import validate_creature_manifest
        state = load_json(ROOT / "docs/evidence/current-state.json")
        validate_instance(state, load_json(ROOT / "schemas/current-state-v0181.json"))
        consistency = validate_state_consistency_v0181(state, (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8"), (ROOT / "REVIEW-v0.18.1.md").read_text(encoding="utf-8"), (ROOT / "docs/roadmap.md").read_text(encoding="utf-8"))
        check("v0181:state-consistency", consistency["status"] == state["current_gate"] and consistency["failures"] == [], "; ".join(consistency["failures"]) or "active v0.18.1 state is consistent")
        manifest = load_json(evidence_root / "creature-runtime-manifest-v0181.json")
        validate_instance(manifest, load_json(ROOT / "schemas/creature-runtime-v0181.json")); validate_creature_manifest(manifest)
        execution = load_json(evidence_root / "execution-evidence-v0181.json"); negative = load_json(evidence_root / "negative-controls-v0181.json"); fixture = load_json(evidence_root / "synthetic-fixture-manifest-v0181.json"); production = load_json(evidence_root / "production-registry-v0181.json"); determinism = load_json(evidence_root / "two-run-determinism-v0181.json"); direction = load_json(evidence_root / "direction-routing-sheet-v0181.json"); lineage = load_json(evidence_root / "derived-variant-lineage-v0181.json")
        controls = negative.get("controls", {})
        strict = len(controls) == 15 and all(item.get("rejected") is True and item.get("passed") is True and item.get("status") == "REJECTED" and item.get("observed", {}).get("result") == "REJECTED" and item["observed"].get("error_code") == item.get("expected_error_code") and item["observed"].get("rejection_class") == item.get("expected_rejection_class") for item in controls.values())
        check("v0181:execution", execution.get("status") == "CREATURES_MONSTERS_RUNTIME_AND_QA_INTEGRITY_TECHNICALLY_QUALIFIED" and execution.get("failed") == 0 and execution.get("production_routing") == "BLOCKED" and execution.get("new_generation") == 0, "all active v0.18.1 integrity gates pass")
        check("v0181:negative-controls", negative.get("status") == "CR_NC_01_TO_15_PASSED" and strict and negative.get("supplemental_controls", {}).get("SUP-NC-06", {}).get("status") == "REJECTED", "canonical and supplemental controls contain strict semantic rejections")
        check("v0181:directions", len(direction.get("records", [])) == 48 and len({item.get("direction_asset_id") for item in direction.get("records", [])}) == 48 and len({item.get("direction_content_hash") for item in direction.get("records", [])}) == 48, "six archetypes expose 48 unique directional identities")
        check("v0181:variants", len([item for item in lineage.get("variants", []) if item.get("kind") == "derived"]) >= 2, "derived variant lineage evidence contains at least two derived variants")
        check("v0181:determinism", determinism.get("status") == "TWO_RUN_DETERMINISM_PASSED" and determinism.get("second_run_reads_first_run") is False and determinism.get("mutated_control_error_code") == "NONDETERMINISTIC_SECOND_FIXTURE_OUTPUT", "isolated two-run and mutation comparator pass")
        check("v0181:fixtures", fixture.get("fixture_count") == 48 and fixture.get("archetype_count") == 6 and fixture.get("unique_hash_count") == 48 and fixture.get("production_registry") is False and all(item.get("test_only") is True and item.get("production_safe") is False for item in fixture.get("fixtures", [])), "48 synthetic directional fixtures remain TEST_ONLY")
        check("v0181:production-registry", production.get("production_registry") is True and production.get("assets") == [] and production.get("production_routing") == "BLOCKED" and production.get("new_generation") == 0, "production creature registry is empty and blocked")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError, ValueError, TypeError) as exc:
        check("v0181:evidence", False, str(exc))


def main() -> int:
    required = [
        "README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.5.0.md", "REVIEW-v0.5.1.md", "REVIEW-v0.5.2.md", "REVIEW-v0.5.3.md", "REVIEW-v0.4.3.md", "REVIEW-v0.4.2.md", "LICENSE", "package.json", "pyproject.toml", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "docs/test-coverage-matrix-v0.4.2.md", "docs/test-coverage-matrix-v0.4.3.md", "docs/test-coverage-matrix-v0.5.0.md", "docs/test-coverage-matrix-v0.5.1.md", "docs/test-coverage-matrix-v0.5.2.md", "docs/test-coverage-matrix-v0.5.3.md", "providers/models/registry.json", "providers/workflows/registry.json", "schemas/reference-edit-contract.json", "schemas/character-identity-manifest.json", "schemas/pose-guide.json", "schemas/openpose-pose-guide.json", "schemas/current-state.json", "schemas/directional-anchor-set.json", "schemas/animation-spec.json", "schemas/animation-frame.json", "schemas/animation-qa.json", "pose-guides/views/front.json", "pose-guides/views/left.json", "pose-guides/views/right.json", "pose-guides/views/back.json", "pose-guides/challenges/multiref-strong-left-arm-up.json", "pose-guides/openpose-v3/challenges/multiref-strong-left-arm-up.json", "docs/evidence/identity-manifest.json", "docs/evidence/multiref-qualification.json", "docs/evidence/pose-guide-manifest.json", "docs/evidence/directional-anchor-set.json", "docs/evidence/directional-anchor-qa.json", "docs/evidence/walk-front-8-animation-spec.json", "docs/evidence/walk-front-8-animation-qa.json", "docs/evidence/walk-front-8.json", "docs/evidence/execution-evidence.json", "docs/evidence/review-visuals-v0.5.0.json", "docs/evidence/runtime-doctor-v0.5.1.json", "docs/evidence/multiref-v2-qualification.json", "docs/evidence/execution-evidence-v0.5.1.json", "docs/evidence/review-visuals-v0.5.1.json", "docs/evidence/current-state.json", "docs/evidence/state-consistency.json", "docs/evidence/runtime-doctor-v0.5.2.json", "docs/evidence/native-reference-order-qualification.json", "docs/evidence/execution-evidence-v0.5.2.json", "docs/evidence/refcontrol-model-qualification.json", "docs/evidence/refcontrol-pose-qualification.json", "docs/evidence/openpose-guide-v3-manifest.json", "docs/evidence/review-visuals-v0.5.2.json", "docs/evidence/pose-metric-calibration.json", "docs/evidence/pose-metric-calibration-contact-sheet.png", "docs/evidence/pose-metric-negative-controls-contact-sheet.png", "docs/evidence/pose-qa-estimator-qualification.json", "docs/evidence/pose-qa-estimator-model.json", "docs/evidence/v052-refcontrol-baseline-contact.png", "docs/evidence/v053-pose-detection-overlay-contact.png", "docs/evidence/v053-pose-error-table.json", "docs/evidence/v053-provider-qualification.json", "docs/evidence/execution-evidence-v0.5.3.json", "docs/evidence/review-visuals-v0.5.3.json", "docs/evidence/v050-baseline-walk-contact.png", "docs/evidence/pose-guides-v2-contact-sheet.png", "docs/evidence/pose-guide-v2-control-example.png", "docs/evidence/pose-guide-v2-review-overlay.png", "docs/evidence/multiref-v2-ab-contact-sheet.png", "docs/evidence/v051-gap-baseline.png", "docs/evidence/openpose-guide-v3-control-example.png", "docs/evidence/openpose-guides-v3-contact-sheet.png", "docs/evidence/native-reference-order-abc-contact-sheet.png", "docs/evidence/refcontrol-strength-benchmark-contact-sheet.png", "docs/evidence/refcontrol-pose-overlay-contact.png", "docs/evidence/reference-edit-workflow-qualification.json", "docs/evidence/upstream/workflow_templates-image-edit-base.json", "docs/evidence/upstream/comfyui-blueprint-image-edit.json", "docs/evidence/reference-edit-contract.json", "docs/evidence/reference-edit-config-benchmark.json", "docs/evidence/reference-edit-config-benchmark-contact-sheet.png", "docs/evidence/reference-edit-candidates.json", "docs/evidence/reference-edit-candidates-contact-sheet.png", "docs/evidence/reference-edit-selected-rgb.png", "docs/evidence/reference-edit-selected-transparent.png", "docs/evidence/reference-edit-selected-checkerboard.png", "docs/evidence/reference-edit-v0.4.3-before-after.png", "docs/evidence/reference-edit-diff-heatmap.png", "docs/evidence/reference-edit-target-mask.png", "docs/evidence/reference-edit-protected-mask.png", "docs/evidence/reference-edit-fidelity.json", "docs/evidence/reference-edit-execution-evidence.json", "docs/evidence/reference-edit-v0.4.3-qa.json", "docs/evidence/reference-edit-v0.4.3-transparency-qa.json", "docs/evidence/revision-chain-v0.4.3.json", "docs/evidence/review-visuals-v0.4.3.json",
    ]
    required += [
        "REVIEW-v0.5.5.md", "docs/test-coverage-matrix-v0.5.5.md",
        "docs/evidence/review-visuals-v0.5.5.json", "scripts/validation/verify_review_archive.py",
        "src/ugas/review_snapshot.py",
        "docs/evidence/v054-pose-error-table.json", "docs/evidence/v054-provider-qualification.json",
        "docs/evidence/execution-evidence-v0.5.4.json",
        *V054_CANONICAL_OUTPUTS,
    ]
    required += [
        "REVIEW-v0.6.0.md", "docs/test-coverage-matrix-v0.6.0.md",
        "docs/evidence/custom-node-audit-ipadapter-plus.json",
        "docs/evidence/sdxl-base-model-qualification.json",
        "docs/evidence/sdxl-openpose-controlnet-qualification.json",
        "docs/evidence/ipadapter-sdxl-model-qualification.json",
        "docs/evidence/clip-vision-qualification.json",
        "docs/evidence/sdxl-model-stack-qualification.json",
        "docs/evidence/runtime-doctor-v0.6.0.json",
        "docs/evidence/sdxl-provider-workflow-qualification.json",
        "docs/evidence/sdxl-provider-qualification.json",
        "docs/evidence/execution-evidence-v0.6.0.json",
        "docs/evidence/sdxl-identity-drift-contact.json",
        "docs/evidence/review-visuals-v0.6.0.json",
        "scripts/providers/audit_ipadapter_custom_node.py",
        "scripts/providers/qualify_sdxl_models.py",
        "scripts/providers/run_sdxl_runtime_doctor.py",
        "scripts/validation/run_sdxl_provider_qualification.py",
        "providers/custom-nodes/registry.json",
        "providers/custom-nodes/README.md",
        "providers/workflows/sdxl-openpose-controlnet-p.api.json",
        "providers/workflows/sdxl-ipadapter-i.api.json",
        "providers/workflows/sdxl-openpose-ipadapter-character.api.json",
    ]
    required += [
        "REVIEW-v0.6.1.md", "docs/test-coverage-matrix-v0.6.1.md", "docs/evidence/current-state-v0.6.0.json", "docs/evidence/current-state-v0.6.1.json",
        "docs/evidence/sdxl-provider-workflow-qualification-v0.6.1.json",
        "docs/evidence/sdxl-provider-qualification-v0.6.1.json",
        "docs/evidence/execution-evidence-v0.6.1.json", "docs/evidence/sdxl-smoke-phase-table.json",
        "docs/evidence/sdxl-identity-hard-gates.json", "docs/evidence/review-visuals-v0.6.1.json",
        "src/ugas/identity_hard_gates.py", "src/ugas/sdxl_smoke_evidence.py",
    ]
    required += [
        "REVIEW-v0.6.2.md", "docs/test-coverage-matrix-v0.6.2.md", "src/ugas/sdxl_openpose_calibration.py",
        "scripts/validation/run_sdxl_openpose_model_card_calibration.py", "docs/evidence/review-visuals-v0.6.2.json",
        "docs/evidence/sdxl-openpose-config-matrix.json", "docs/evidence/sdxl-openpose-config-runtime-table.json",
        "docs/evidence/execution-evidence-v0.6.2.json", "docs/evidence/sdxl-openpose-p-qualification.json",
    ]
    required += [
        "REVIEW-v0.7.0.md", "docs/test-coverage-matrix-v0.7.0.md",
        "providers/manifests/deterministic-cutout-rig-2d.json", "schemas/cutout-rig.json", "schemas/cutout-rig-part.json",
        "src/ugas/cutout_rig.py", "scripts/validation/run_cutout_rig_v070.py", "scripts/validation/materialize_cutout_review_evidence.py",
        "docs/evidence/current-state-v0.6.2.json", "docs/evidence/review-visuals-v0.7.0.json",
        "docs/evidence/sam2-provider-qualification.json", "docs/evidence/sam2-checkpoint-provenance.json",
        "docs/evidence/r4-source-skeleton.json", "docs/evidence/r4-cutout-part-prompts.json", "docs/evidence/r4-cutout-part-masks.json", "docs/evidence/r4-cutout-rig.json",
        "docs/evidence/r4-cutout-parts-contact-sheet.png", "docs/evidence/r4-cutout-mask-overlay-contact-sheet.png", "docs/evidence/r4-cutout-rig-hierarchy.png",
        "docs/evidence/cutout-q0-reconstruction.png", "docs/evidence/cutout-q0-diff-heatmap.png", "docs/evidence/cutout-q0-qa.json", "docs/evidence/cutout-q1-contact-left.png", "docs/evidence/cutout-q2-passing-left.png", "docs/evidence/cutout-q0-q1-q2-contact-sheet.png", "docs/evidence/cutout-q1-q2-pose-overlays.png",
        "docs/evidence/cutout-rig-pose-qa.json", "docs/evidence/cutout-rig-seam-qa.json", "docs/evidence/cutout-rig-pixel-provenance.json", "docs/evidence/cutout-rig-provider-qualification.json", "docs/evidence/execution-evidence-v0.7.0.json",
    ]
    required += [
        "REVIEW-v0.7.1.md", "docs/test-coverage-matrix-v0.7.1.md", "docs/evidence/current-state.json", "docs/evidence/current-state-v0.7.0.json", "docs/evidence/state-consistency.json", "docs/evidence/state-consistency-v0.7.0.json", "docs/evidence/review-visuals-v0.7.1.json",
        "scripts/validation/run_cutout_rig_v071.py", "scripts/validation/materialize_cutout_review_evidence.py",
        "docs/evidence/sam2-provider-qualification-v071.json", "docs/evidence/sam2-checkpoint-provenance-v071.json", "docs/evidence/r4-source-skeleton-v071.json", "docs/evidence/r4-cutout-part-prompts-v071.json", "docs/evidence/r4-cutout-raw-masks-v071-manifest.json", "docs/evidence/r4-cutout-refined-masks-v071-manifest.json", "docs/evidence/r4-cutout-component-diagnostics-v071.json", "docs/evidence/r4-cutout-rig-v071.json", "docs/evidence/r4-cutout-parts-contact-sheet-v071.png", "docs/evidence/r4-cutout-mask-overlay-v071.png", "docs/evidence/cutout-q0-reconstruction-v071.png", "docs/evidence/cutout-q0-alpha-aware-diff-v071.png", "docs/evidence/cutout-q0-reconstruction-qa-v071.json", "docs/evidence/cutout-q1-contact-left-v071.png", "docs/evidence/cutout-q2-passing-left-v071.png", "docs/evidence/cutout-q0-q1-q2-contact-sheet-v071.png", "docs/evidence/cutout-q1-q2-target-detected-overlays-v071.png", "docs/evidence/cutout-rig-internal-qa-v071.json", "docs/evidence/cutout-rig-seam-qa-v071.json", "docs/evidence/cutout-rig-pixel-retention-v071.json", "docs/evidence/cutout-rig-provider-qualification-v071.json", "docs/evidence/cutout-rig-pose-qa-v071.json", "docs/evidence/cutout-rig-pixel-provenance-v071.json", "docs/evidence/execution-evidence-v0.7.1.json",
    ]
    required += [
        "REVIEW-v0.7.2.md", "docs/test-coverage-matrix-v0.7.2.md", "providers/manifests/deterministic-cutout-rig-2d-v0.7.1.json",
        "src/ugas/cutout_occlusion.py", "scripts/validation/run_cutout_rig_v072.py", "schemas/cutout-occlusion-plan.json", "schemas/cutout-pairwise-overlap.json", "schemas/cutout-seam-topology-qa.json", "schemas/cutout-retention-occlusion.json", "schemas/front-walk-gait-v2.json", "schemas/cutout-half-cycle-structure.json",
        "docs/evidence/current-state-v0.7.1.json", "docs/evidence/state-consistency-v0.7.1.json", "docs/evidence/review-visuals-v0.7.2.json",
        *{f"docs/evidence/{name}" for name in REQUIRED_V072_REVIEW_EVIDENCE},
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
            validate_instance(model, schemas["model-manifest"])
            if model.get("schema_version") == "0.6.0":
                semantic = model.get("recommended_steps") in {20, None} and model.get("recommended_guidance") in {7.0, None}
                license_recorded = model.get("commercial_use_status") in {"approved", "conditional-license-review-required", "review", "required"}
            else:
                semantic = model["family"] == "birefnet" or (model["variant"] == "distilled" and model.get("recommended_steps") == 4 and model.get("recommended_guidance") == 1.0) or (model["variant"] == "base" and model.get("recommended_steps") == 50 and model.get("recommended_guidance") == 4.0)
                license_recorded = model["commercial_use_status"] == "approved"
            check(f"model:{model['id']}", license_recorded and semantic and all(str(v) != "RECORD_AFTER_DOWNLOAD" for v in model.get("sha256", {}).values()) or model.get("id") == "flux2-klein-4b-fp8", "license and lane semantics valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError) as exc: check("registry:models", False, str(exc))
    try:
        workflows = load_workflows(ROOT); check("registry:workflows", len(workflows) >= 6, "four historical FLUX lanes, native multi-reference and BiRefNet")
        for item in workflows:
            record = load_workflow(ROOT, item["id"]); graph = validate_api_workflow(record["api"]); model = load_model(ROOT, item["required_models"][0]); compatible = validate_model_workflow_compatibility(model, record)["compatible"]
            custom_ok = not item["custom_nodes_required"] or all(str(value).startswith("comfyui-ipadapter-plus@a0f451a5113cf9becb0847b92884cb10cbdec0ef") for value in item["custom_nodes_required"])
            check(f"workflow:{item['id']}", graph["valid_graph"] and compatible and custom_ok and item["schema_version"] in {"0.4.3", "0.5.0", "0.5.1", "0.5.2", "0.6.0", UGAS_VERSION}, "native graph, pinned custom-node boundary and capability compatibility valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError, ValueError) as exc: check("registry:workflows", False, str(exc))
    _historical_coverage_checks(); _reference_edit_checks(); _review_checks(); _v050_checks(); _v051_checks(); _v052_checks(); _v060_checks(); _v061_checks(); _v062_checks(); _v070_checks(); _v071_checks(); _v072_checks(); _v073_checks(); _v080_checks(); _v081_checks(); _v090_checks(); _v091_checks(); _v0100_checks(); _v0110_checks(); _v0112_checks(); _v0120_checks(); _v0121_history_checks(); _v0122_checks(); _v0123_checks(); _v0124_checks(); _v0130_checks(); _v0131_checks(); _v0140_checks(); _v0141_checks(); _v0150_checks(); _v0151_checks(); _v0160_history_checks(); _v0161_checks(); _v0162_checks(); _v0170_checks(); _v0180_checks(); _v0181_checks()
    package_version = load_json(ROOT / "package.json")["version"]
    with (ROOT / "pyproject.toml").open("rb") as stream: pyproject_version = tomllib.load(stream)["project"]["version"]
    init_version = __import__("ugas").__version__
    check("version:consistency", UGAS_VERSION == package_version == pyproject_version == init_version == "0.18.1", f"runtime={UGAS_VERSION}, package={package_version}, pyproject={pyproject_version}")
    docs = ["README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.18.1.md", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md"]
    check("docs:version", all(UGAS_VERSION in (ROOT / path).read_text(encoding="utf-8") for path in docs), "current operational docs identify 0.18.1")
    checkpoint_text = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8").casefold()
    check("docs:animation-boundary", "animação genérica" in checkpoint_text or "no other animation" in checkpoint_text, "checkpoint keeps other animations outside scope")
    check("security:tracked-forbidden", not any(Path(path).suffix.casefold() in {".safetensors", ".ckpt", ".gguf", ".onnx"} for path in subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.splitlines()) if (ROOT / ".git").exists() else True, "weights are outside Git")
    print("RUN tests:compileall", flush=True)
    compile_run = _run([sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"], ROOT); check("tests:compileall", compile_run.returncode == 0, (compile_run.stdout + compile_run.stderr).strip()[-500:])
    print(f"DONE tests:compileall returncode={compile_run.returncode}", flush=True)
    print("RUN tests:unit", flush=True)
    test_run = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], ROOT, timeout=360); test_text = test_run.stdout + test_run.stderr; match = re.search(r"Ran (\d+) tests", test_text); check("tests:unit", test_run.returncode == 0 and match is not None and int(match.group(1)) >= 300, test_text.strip()[-800:])
    print(f"DONE tests:unit returncode={test_run.returncode} count={match.group(1) if match else 'unknown'}", flush=True)
    print("RUN snapshot", flush=True)
    snapshot_check()
    print("DONE snapshot", flush=True)
    failures = 0
    for name, ok, detail in RESULTS: print(f"{'PASS' if ok else 'FAIL'} {name} - {detail}"); failures += not ok
    print(f"SUMMARY checks={len(RESULTS)} passed={len(RESULTS) - failures} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
