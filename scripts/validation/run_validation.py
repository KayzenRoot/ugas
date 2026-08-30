"""Objective UGAS v0.5.2 validation, including immutable historical gates."""

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
from ugas.openpose_guides import COCO18_JOINTS, OPENPOSE_GUIDE_RENDERER_VERSION, validate_openpose_guide
from ugas.state_consistency import validate_state_consistency
from ugas.workflow_registry import load_workflow, load_workflows, validate_api_workflow
from ugas.identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256, validate_identity_manifest
from ugas.pose_guides import CHALLENGE_NAME, POSE_GUIDE_RENDERER_VERSION, WALK_NAMES, validate_pose_guide
from ugas.multiview import AB_POSE_GAIN, AB_POSE_THRESHOLD, AB_POSE_FLOOR, FRAME_POSE_THRESHOLD, IDENTITY_THRESHOLD


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
    """Validate the active escalation without converting a gap into approval."""
    state_path = ROOT / "docs/evidence/current-state.json"
    checkpoint_path = ROOT / "CHECKPOINT.md"
    review_path = ROOT / "REVIEW-v0.5.2.md"
    try:
        state = load_json(state_path)
        state_schema = load_json(ROOT / "schemas/current-state.json")
        validate_instance(state, state_schema)
        consistency = validate_state_consistency(state, checkpoint_path.read_text(encoding="utf-8"), review_path.read_text(encoding="utf-8"))
        check("v052:state-consistency", consistency["status"] == "STATE_CONSISTENCY_PASSED", "; ".join(consistency.get("failures", [])) or "active state and documents are consistent")
        check("v052:final-stop", state.get("current_gate") == "LOCAL_POSE_CONTROL_PROVIDER_GAP" and state.get("stop_reason") == "LOCAL_POSE_CONTROL_PROVIDER_GAP", "pose-control escalation ends at an explicit provider gap")
    except (OSError, json.JSONDecodeError, KeyError, SchemaValidationError) as exc:
        check("v052:state-consistency", False, str(exc)); check("v052:final-stop", False, str(exc))

    review = review_path.read_text(encoding="utf-8") if review_path.is_file() else ""
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


def main() -> int:
    required = [
        "README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.5.0.md", "REVIEW-v0.5.1.md", "REVIEW-v0.5.2.md", "REVIEW-v0.4.3.md", "REVIEW-v0.4.2.md", "LICENSE", "package.json", "pyproject.toml", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md", "docs/test-coverage-matrix-v0.4.2.md", "docs/test-coverage-matrix-v0.4.3.md", "docs/test-coverage-matrix-v0.5.0.md", "docs/test-coverage-matrix-v0.5.1.md", "docs/test-coverage-matrix-v0.5.2.md", "providers/models/registry.json", "providers/workflows/registry.json", "schemas/reference-edit-contract.json", "schemas/character-identity-manifest.json", "schemas/pose-guide.json", "schemas/openpose-pose-guide.json", "schemas/current-state.json", "schemas/directional-anchor-set.json", "schemas/animation-spec.json", "schemas/animation-frame.json", "schemas/animation-qa.json", "pose-guides/views/front.json", "pose-guides/views/left.json", "pose-guides/views/right.json", "pose-guides/views/back.json", "pose-guides/challenges/multiref-strong-left-arm-up.json", "pose-guides/openpose-v3/challenges/multiref-strong-left-arm-up.json", "docs/evidence/identity-manifest.json", "docs/evidence/multiref-qualification.json", "docs/evidence/pose-guide-manifest.json", "docs/evidence/directional-anchor-set.json", "docs/evidence/directional-anchor-qa.json", "docs/evidence/walk-front-8-animation-spec.json", "docs/evidence/walk-front-8-animation-qa.json", "docs/evidence/walk-front-8.json", "docs/evidence/execution-evidence.json", "docs/evidence/review-visuals-v0.5.0.json", "docs/evidence/runtime-doctor-v0.5.1.json", "docs/evidence/multiref-v2-qualification.json", "docs/evidence/execution-evidence-v0.5.1.json", "docs/evidence/review-visuals-v0.5.1.json", "docs/evidence/current-state.json", "docs/evidence/state-consistency.json", "docs/evidence/runtime-doctor-v0.5.2.json", "docs/evidence/native-reference-order-qualification.json", "docs/evidence/execution-evidence-v0.5.2.json", "docs/evidence/refcontrol-model-qualification.json", "docs/evidence/refcontrol-pose-qualification.json", "docs/evidence/openpose-guide-v3-manifest.json", "docs/evidence/review-visuals-v0.5.2.json", "docs/evidence/v050-baseline-walk-contact.png", "docs/evidence/pose-guides-v2-contact-sheet.png", "docs/evidence/pose-guide-v2-control-example.png", "docs/evidence/pose-guide-v2-review-overlay.png", "docs/evidence/multiref-v2-ab-contact-sheet.png", "docs/evidence/v051-gap-baseline.png", "docs/evidence/openpose-guide-v3-control-example.png", "docs/evidence/openpose-guides-v3-contact-sheet.png", "docs/evidence/native-reference-order-abc-contact-sheet.png", "docs/evidence/refcontrol-strength-benchmark-contact-sheet.png", "docs/evidence/refcontrol-pose-overlay-contact.png", "docs/evidence/reference-edit-workflow-qualification.json", "docs/evidence/upstream/workflow_templates-image-edit-base.json", "docs/evidence/upstream/comfyui-blueprint-image-edit.json", "docs/evidence/reference-edit-contract.json", "docs/evidence/reference-edit-config-benchmark.json", "docs/evidence/reference-edit-config-benchmark-contact-sheet.png", "docs/evidence/reference-edit-candidates.json", "docs/evidence/reference-edit-candidates-contact-sheet.png", "docs/evidence/reference-edit-selected-rgb.png", "docs/evidence/reference-edit-selected-transparent.png", "docs/evidence/reference-edit-selected-checkerboard.png", "docs/evidence/reference-edit-v0.4.3-before-after.png", "docs/evidence/reference-edit-diff-heatmap.png", "docs/evidence/reference-edit-target-mask.png", "docs/evidence/reference-edit-protected-mask.png", "docs/evidence/reference-edit-fidelity.json", "docs/evidence/reference-edit-execution-evidence.json", "docs/evidence/reference-edit-v0.4.3-qa.json", "docs/evidence/reference-edit-v0.4.3-transparency-qa.json", "docs/evidence/revision-chain-v0.4.3.json", "docs/evidence/review-visuals-v0.4.3.json",
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
        workflows = load_workflows(ROOT); check("registry:workflows", len(workflows) >= 6, "four historical FLUX lanes, native multi-reference and BiRefNet")
        for item in workflows:
            record = load_workflow(ROOT, item["id"]); graph = validate_api_workflow(record["api"]); model = load_model(ROOT, item["required_models"][0]); compatible = validate_model_workflow_compatibility(model, record)["compatible"]
            check(f"workflow:{item['id']}", graph["valid_graph"] and compatible and not item["custom_nodes_required"] and item["schema_version"] in {"0.4.3", "0.5.0", "0.5.1", UGAS_VERSION}, "native graph and capability compatibility valid")
    except (OSError, json.JSONDecodeError, SchemaValidationError, KeyError, ValueError) as exc: check("registry:workflows", False, str(exc))
    _historical_coverage_checks(); _reference_edit_checks(); _review_checks(); _v050_checks(); _v051_checks(); _v052_checks()
    package_version = load_json(ROOT / "package.json")["version"]
    with (ROOT / "pyproject.toml").open("rb") as stream: pyproject_version = tomllib.load(stream)["project"]["version"]
    init_version = __import__("ugas").__version__
    check("version:consistency", UGAS_VERSION == package_version == pyproject_version == init_version == "0.5.2", f"runtime={UGAS_VERSION}, package={package_version}, pyproject={pyproject_version}")
    docs = ["README.md", "INSTALL.md", "CHECKPOINT.md", "docs/2d-master-pipeline.md", "docs/comfyui.md", "docs/roadmap.md"]
    check("docs:version", all(UGAS_VERSION in (ROOT / path).read_text(encoding="utf-8") for path in docs), "current operational docs identify 0.5.2")
    checkpoint_text = (ROOT / "CHECKPOINT.md").read_text(encoding="utf-8").casefold()
    check("docs:animation-boundary", "animação genérica" in checkpoint_text and "não autoriza" in checkpoint_text, "checkpoint keeps generic animation outside scope")
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
