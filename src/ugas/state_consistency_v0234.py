"""Fail-closed state and live PR rules for VFX correction v0.23.4."""

from __future__ import annotations

from typing import Any, Mapping

VERSION = "0.23.4"
PHASE = "VFX_ASSET_FAMILY"
BASELINE_MAIN_SHA = "b08b9c3df74ef6a23046be396289e2fd72dc336b"
FEATURE_BRANCH = "codex/v0.23.0-vfx-asset-family-runtime-foundation"
PR_NUMBER = 14
CURRENT_GATE = "VFX_ASSET_FAMILY_RUNTIME_CORRECTION_F29R_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED"
NEXT_ACTION = "external_review_vfx_asset_family_v0234"
GOVERNED_MERGE_ACTION = "governed_merge_vfx_pr_14"
ORCHESTRATION_ACTION = "start_orchestration_runtime_hardening"
NEXT_CANDIDATE = "ORCHESTRATION_RUNTIME_HARDENING"
REQUIRED_MAIN_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke")
LIVE_HEAD_SOURCE = "GitHub LIVE exact-head metadata"


def _check(failures: list[str], condition: bool, code: str) -> None:
    if not condition:
        failures.append(code)


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str = "", roadmap_text: str = "", matrix: Mapping[str, Any] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    _check(failures, state.get("schema_version") == VERSION and state.get("version") == VERSION, "version")
    _check(failures, state.get("phase") == PHASE, "phase")
    _check(failures, state.get("baseline_main_sha") == BASELINE_MAIN_SHA and state.get("vfx_base_main_sha") == BASELINE_MAIN_SHA, "baseline-main-sha")
    _check(failures, state.get("current_gate") == CURRENT_GATE, "current-gate")
    _check(failures, state.get("next_candidate") == NEXT_CANDIDATE and state.get("allowed_next_actions") == [NEXT_ACTION], "next-action")
    _check(failures, state.get("production_approved") is False and state.get("production_routing") == "BLOCKED" and state.get("new_generation") == 0, "production-boundary")
    _check(failures, state.get("vfx_asset_family") == "TECHNICALLY_QUALIFIED_FOUNDATION" and state.get("vfx_asset_family_external_review") == "REQUIRED", "vfx-status")
    _check(failures, state.get("real_vfx_asset_coverage") == "NONE" and state.get("synthetic_vfx_fixture") == "TEST_ONLY", "fixture-boundary")
    forbidden = set(state.get("forbidden_actions", []))
    for required in ("direct_main_push", "force_push_or_history_rewrite", "enable_production_routing", "new_generation", "orchestration_runtime_hardening", "real_vfx_assets", "provider_generation", "diffusion_generation"):
        _check(failures, required in forbidden, f"forbidden:{required}")
    review = state.get("review") or {}
    _check(failures, review.get("repository") == "KayzenRoot/ugas" and review.get("pr_number") == PR_NUMBER and review.get("pr_state") == "OPEN", "review-pr")
    _check(failures, review.get("branch_base_commit") == BASELINE_MAIN_SHA and review.get("baseline_head") == BASELINE_MAIN_SHA and review.get("feature_branch") == FEATURE_BRANCH, "review-binding")
    _check(failures, review.get("execution_mode") == "GITHUB_PR_FIRST" and review.get("merge_policy") == "NO_SELF_MERGE_UNTIL_EXTERNAL_REVIEW" and review.get("external_review_required") is True and review.get("do_not_merge") is True and review.get("head_sha_source") == LIVE_HEAD_SOURCE, "review-boundary")
    _check(failures, review.get("head_sha") is None, "review-head-must-be-live-only")
    _check(failures, review.get("required_contexts") == ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence"], "required-contexts")
    evidence = state.get("evidence") or {}
    _check(failures, evidence.get("vfx_root") == "docs/evidence/vfx-asset-family-runtime-v0234/", "evidence-root")
    _check(failures, "VFX_ASSET_FAMILY" in checkpoint_text and CURRENT_GATE in checkpoint_text and "v0.23.4" in checkpoint_text, "checkpoint-binding")
    _check(failures, "v0.23.4" in roadmap_text and NEXT_ACTION in roadmap_text, "roadmap-binding")
    if matrix is not None:
        _check(failures, matrix.get("version") == VERSION and matrix.get("next_candidate") == NEXT_CANDIDATE, "matrix-binding")
    return {"status": CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED", "version": VERSION, "phase": PHASE, "current_gate": CURRENT_GATE, "failures": failures, "baseline_main_sha": BASELINE_MAIN_SHA, "allowed_next_actions": [NEXT_ACTION], "production_routing": state.get("production_routing"), "production_approved": state.get("production_approved"), "new_generation": state.get("new_generation")}


def _context_records(ci: Mapping[str, Any]) -> list[Mapping[str, Any]] | None:
    contexts = ci.get("context_records")
    return [item for item in contexts if isinstance(item, Mapping)] if isinstance(contexts, list) else None


def _exact_post_merge_ci(live: Mapping[str, Any]) -> bool:
    merge_sha, current_main_sha, ci = live.get("merge_commit_sha"), live.get("current_main_sha"), live.get("post_merge_main_ci")
    if not all(isinstance(value, str) and len(value) == 40 for value in (merge_sha, current_main_sha)) or merge_sha != current_main_sha or not isinstance(ci, Mapping) or ci.get("commit_sha") != merge_sha:
        return False
    contexts = _context_records(ci)
    if contexts is None or len(contexts) != 2 or {item.get("context", item.get("name")) for item in contexts} != set(REQUIRED_MAIN_CONTEXTS):
        return False
    return all(item.get("context", item.get("name")) in REQUIRED_MAIN_CONTEXTS and item.get("head_sha") == merge_sha and item.get("status") == "completed" and item.get("conclusion") == "success" for item in contexts)


def validate_live_pr_binding(live: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    _check(failures, live.get("source") == "GITHUB_LIVE", "live-source")
    _check(failures, live.get("repository") == "KayzenRoot/ugas" and live.get("pr_number") == PR_NUMBER, "live-pr")
    _check(failures, live.get("branch") == FEATURE_BRANCH and live.get("base_sha") == BASELINE_MAIN_SHA, "live-branch-base")
    _check(failures, live.get("pr_state") in {"OPEN", "MERGED"} and isinstance(live.get("head_sha"), str) and len(live.get("head_sha", "")) == 40, "live-head")
    if live.get("pr_state") == "OPEN":
        _check(failures, live.get("merged") is False, "open-not-merged")
    return {"status": "LIVE_PR_BINDING_VALID" if not failures else "LIVE_PR_BINDING_FAILED", "failures": failures, "source_mode": "GITHUB_LIVE"}


def resolve_next_actions(state: Mapping[str, Any], live: Mapping[str, Any]) -> dict[str, Any]:
    binding = validate_live_pr_binding(live)
    if binding["failures"]:
        return {"allowed_next_actions": [], "orchestration_allowed": False, "source_mode": "GITHUB_LIVE", "reason": "live PR binding invalid", "failures": binding["failures"]}
    if live.get("pr_state") == "OPEN" and live.get("external_approval") is False and live.get("merged") is False:
        return {"allowed_next_actions": [NEXT_ACTION], "orchestration_allowed": False, "source_mode": "GITHUB_LIVE", "reason": "external review required"}
    if live.get("pr_state") == "OPEN" and live.get("external_approval") is True and live.get("merged") is False:
        return {"allowed_next_actions": [GOVERNED_MERGE_ACTION], "orchestration_allowed": False, "source_mode": "GITHUB_LIVE", "reason": "external approval recorded but merge not performed"}
    if live.get("pr_state") == "MERGED" and live.get("external_approval") is True and live.get("merged") is True and _exact_post_merge_ci(live):
        return {"allowed_next_actions": [ORCHESTRATION_ACTION], "orchestration_allowed": True, "source_mode": "GITHUB_LIVE", "reason": "exact merged-main CI proof is complete"}
    return {"allowed_next_actions": [], "orchestration_allowed": False, "source_mode": "GITHUB_LIVE", "reason": "exact live closure proof incomplete; fail closed"}
