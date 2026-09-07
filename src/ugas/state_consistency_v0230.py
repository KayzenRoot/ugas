"""Machine-authoritative active-state checks for the v0.23.0 VFX slice."""

from __future__ import annotations

from typing import Any, Mapping


VERSION = "0.23.0"
PHASE = "VFX_ASSET_FAMILY"
BASELINE_MAIN_SHA = "b08b9c3df74ef6a23046be396289e2fd72dc336b"
CURRENT_GATE = "VFX_ASSET_FAMILY_RUNTIME_FOUNDATION_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED"
NEXT_ACTION = "external_review_vfx_asset_family_v0230"
NEXT_CANDIDATE = "ORCHESTRATION_RUNTIME_HARDENING"


class StateConsistencyError(ValueError):
    def __init__(self, rejection_class: str, detail: str = "") -> None:
        self.rejection_class = rejection_class
        self.detail = detail
        super().__init__(f"{rejection_class}: {detail}" if detail else rejection_class)


def _check(failures: list[str], condition: bool, code: str) -> None:
    if not condition:
        failures.append(code)


def validate_state_consistency(state: Mapping[str, Any], checkpoint_text: str = "", roadmap_text: str = "", matrix: Mapping[str, Any] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    _check(failures, state.get("schema_version") == VERSION, "schema-version")
    _check(failures, state.get("version") == VERSION, "version")
    _check(failures, state.get("phase") == PHASE, "phase")
    _check(failures, state.get("baseline_main_sha") == BASELINE_MAIN_SHA and state.get("vfx_base_main_sha") == BASELINE_MAIN_SHA, "baseline-main-sha")
    _check(failures, state.get("current_gate") == CURRENT_GATE, "current-gate")
    _check(failures, state.get("next_candidate") == NEXT_CANDIDATE, "next-candidate")
    _check(failures, state.get("allowed_next_actions") == [NEXT_ACTION], "allowed-next-actions")
    _check(failures, state.get("production_approved") is False and state.get("production_routing") == "BLOCKED" and state.get("new_generation") == 0, "production-boundary")
    _check(failures, state.get("vfx_asset_family") == "TECHNICALLY_QUALIFIED_FOUNDATION" and state.get("vfx_asset_family_external_review") == "REQUIRED", "vfx-status")
    _check(failures, state.get("ui_asset_family") == "APPROVED_FOUNDATION" and state.get("ui_asset_family_lifecycle") == "MERGED_CLOSED", "ui-transition")
    _check(failures, state.get("real_vfx_asset_coverage") == "NONE" and state.get("synthetic_vfx_fixture") == "TEST_ONLY", "fixture-boundary")
    forbidden = set(state.get("forbidden_actions", []))
    for required in ("direct_main_push", "force_push_or_history_rewrite", "enable_production_routing", "new_generation", "orchestration_runtime_hardening", "real_vfx_assets"):
        _check(failures, required in forbidden, f"forbidden:{required}")
    review = state.get("review") or {}
    _check(failures, review.get("repository") == "KayzenRoot/ugas", "review-repository")
    _check(failures, review.get("branch_base_commit") == BASELINE_MAIN_SHA and review.get("baseline_head") == BASELINE_MAIN_SHA, "review-base")
    _check(failures, review.get("feature_branch") == "codex/v0.23.0-vfx-asset-family-runtime-foundation", "review-branch")
    _check(failures, review.get("execution_mode") == "GITHUB_PR_FIRST" and review.get("merge_policy") == "NO_SELF_MERGE_UNTIL_EXTERNAL_REVIEW", "review-policy")
    _check(failures, review.get("external_review_required") is True and review.get("do_not_merge") is True, "review-boundary")
    _check(failures, isinstance(review.get("required_contexts"), list) and len(review["required_contexts"]) == 3, "required-contexts")
    evidence = state.get("evidence") or {}
    _check(failures, evidence.get("vfx_root") == "docs/evidence/vfx-asset-family-runtime-v0230/", "evidence-root")
    _check(failures, "VFX_ASSET_FAMILY" in checkpoint_text and CURRENT_GATE in checkpoint_text, "checkpoint-binding")
    _check(failures, "v0.23.0" in roadmap_text and NEXT_ACTION in roadmap_text, "roadmap-binding")
    if matrix is not None:
        _check(failures, matrix.get("version") == VERSION and matrix.get("next_candidate") == NEXT_CANDIDATE, "matrix-binding")
    status = CURRENT_GATE if not failures else "STATE_CONSISTENCY_FAILED"
    return {"status": status, "version": VERSION, "phase": PHASE, "current_gate": CURRENT_GATE, "failures": failures, "baseline_main_sha": BASELINE_MAIN_SHA, "allowed_next_actions": [NEXT_ACTION], "production_routing": state.get("production_routing"), "production_approved": state.get("production_approved"), "new_generation": state.get("new_generation")}


def resolve_next_actions(state: Mapping[str, Any], live: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the one safe next action from live PR/check data.

    The tracked state supplies semantics; GitHub LIVE supplies current PR/main
    facts.  A missing or incomplete live proof returns no action.
    """
    pr_state = live.get("pr_state")
    approved = live.get("external_approval")
    merged = live.get("merged")
    ci = live.get("post_merge_main_ci")
    ci_success = isinstance(ci, Mapping) and ci.get("status") == "success" and ci.get("contexts") == ["UGAS CI / unit-and-validation", "UGAS CI / docker-smoke"]
    if pr_state == "OPEN" and approved is False and merged is False:
        return {"allowed_next_actions": [NEXT_ACTION], "orchestration_allowed": False, "source_mode": "GITHUB_LIVE", "reason": "external review required"}
    if pr_state == "OPEN" and approved is True and merged is False:
        return {"allowed_next_actions": ["governed_merge_vfx_pr_14"], "orchestration_allowed": False, "source_mode": "GITHUB_LIVE", "reason": "external approval recorded but merge not performed"}
    if pr_state == "MERGED" and approved is True and merged is True and ci_success:
        return {"allowed_next_actions": ["start_orchestration_runtime_hardening"], "orchestration_allowed": True, "source_mode": "GITHUB_LIVE", "reason": "merged-main CI proof is complete"}
    return {"allowed_next_actions": [], "orchestration_allowed": False, "source_mode": "GITHUB_LIVE", "reason": "live closure proof incomplete; fail closed"}
