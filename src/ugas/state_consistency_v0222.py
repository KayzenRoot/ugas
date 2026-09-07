"""Fail-closed active state and capability lifecycle for UI v0.22.2."""

from __future__ import annotations

from typing import Any, Mapping


CURRENT_VERSION = "0.22.2"
CURRENT_PHASE = "UI_ASSET_FAMILY"
CURRENT_GATE = "UI_ASSET_FAMILY_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED"
BASELINE_MAIN_SHA = "1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3"
FEATURE_BRANCH = "codex/v0.22.0-ui-asset-family-runtime-foundation"
NEXT_ACTION = "external_review_ui_asset_family_v0222"
NEXT_CANDIDATE = "UI_ASSET_FAMILY"
CANONICAL_CLOSURE_AUTHORITY = "docs/evidence/github-governance-v0220/v0213-post-merge-binding.json"
SUPERSEDED_CLOSURE_AUTHORITY = "docs/evidence/github-governance-v0220/v0213-closure-completion-binding.json"
POST_MERGE_CLOSURE_BINDING = "docs/evidence/github-governance-v0221/v0213-closure-completion-binding-v2.json"
REQUIRED_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke", "UGAS Review / evidence")
MAIN_CONTEXTS = ("UGAS CI / unit-and-validation", "UGAS CI / docker-smoke")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(char in "0123456789abcdef" for char in value.casefold())


def validate_state_consistency(state: Mapping[str, Any], binding: Mapping[str, Any] | None = None, checkpoint_text: str = "", review_text: str = "", roadmap_text: str = "") -> dict[str, Any]:
    failures: list[str] = []
    expected = {
        "schema_version": CURRENT_VERSION, "version": CURRENT_VERSION, "phase": CURRENT_PHASE, "current_gate": CURRENT_GATE,
        "next_candidate": NEXT_CANDIDATE, "ui_asset_family": "TECHNICALLY_QUALIFIED_FOUNDATION", "ui_asset_family_external_review": "REQUIRED",
        "maps_minimap_assets": "APPROVED_FOUNDATION", "maps_minimap_lifecycle": "MERGED_CLOSED", "maps_minimap_runtime_external_review": "APPROVED_FOUNDATION",
        "real_ui_asset_coverage": "NONE", "synthetic_ui_fixture": "TEST_ONLY", "production_routing": "BLOCKED", "new_generation": 0, "next_capability_started": False,
    }
    failures.extend(f"{key}_invalid" for key, value in expected.items() if state.get(key) != value)
    if "main_sha" in state:
        failures.append("main_sha_forbidden")
    if state.get("baseline_main_sha") != BASELINE_MAIN_SHA or state.get("ui_base_main_sha") != BASELINE_MAIN_SHA:
        failures.append("baseline_main_sha_invalid")
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        failures.append("allowed_next_actions_invalid")
    forbidden = state.get("forbidden_actions")
    if not isinstance(forbidden, list) or not {"vfx_asset_family", "orchestration_runtime_hardening", "enable_production_routing", "new_generation"}.issubset(forbidden):
        failures.append("forbidden_boundaries_incomplete")
    ui_gate = _mapping(state.get("ui_start_gate"))
    if ui_gate.get("status") != "ACTIVE_FOUNDATION" or ui_gate.get("authority") != "REPOSITORY_STATE" or ui_gate.get("capability") != "UI_ASSET_FAMILY":
        failures.append("ui_start_gate_invalid")
    vfx_gate = _mapping(state.get("vfx_start_gate"))
    if vfx_gate.get("status") != "BLOCKED" or vfx_gate.get("authority") != "GITHUB_LIVE" or vfx_gate.get("condition") != "UI_APPROVED_FOUNDATION_MERGED_CLOSED_AND_POST_MERGE_MAIN_CI_SUCCESS":
        failures.append("vfx_start_gate_invalid")
    review = _mapping(state.get("review"))
    expected_review = {"repository": "KayzenRoot/ugas", "baseline_head": BASELINE_MAIN_SHA, "branch_base_commit": BASELINE_MAIN_SHA, "feature_branch": FEATURE_BRANCH, "execution_mode": "GITHUB_PR_FIRST", "external_review_required": True, "merge_authorization": "NOT_AUTHORIZED_UNTIL_SOL_APPROVAL", "do_not_merge": True}
    failures.extend(f"review:{key}" for key, value in expected_review.items() if review.get(key) != value)
    if review.get("pr_state") != "OPEN" or review.get("pr_number") != 13:
        failures.append("review:live_pr_binding")
    if review.get("head_sha") not in {None, ""} and not _is_sha(review.get("head_sha")):
        failures.append("review:head_sha")
    history = _mapping(state.get("correction_history"))
    h221 = _mapping(history.get("v0.22.1"))
    if h221.get("status") != "CORRECTION_REQUIRED" or h221.get("rejected_reviewed_head") != "9afcf52143f27db3bfbb88fa4394e0e77f9c404a" or h221.get("historical_evidence_unchanged") is not True:
        failures.append("v0221_history_invalid")
    h213 = _mapping(history.get("v0.21.3"))
    authority = _mapping(state.get("closure_authority"))
    if authority.get("canonical") != CANONICAL_CLOSURE_AUTHORITY or authority.get("authority_version") != "0.21.3" or SUPERSEDED_CLOSURE_AUTHORITY not in authority.get("superseded", []):
        failures.append("closure_authority_pointer_invalid")
    if h213.get("record") != CANONICAL_CLOSURE_AUTHORITY or state.get("closure_completion_binding") != CANONICAL_CLOSURE_AUTHORITY or state.get("post_merge_closure_binding") != POST_MERGE_CLOSURE_BINDING:
        failures.append("closure_authority_pointer_conflict")
    if authority.get("canonical") in authority.get("superseded", []):
        failures.append("closure_authority_self_superseded")
    if binding is not None:
        if binding.get("canonical_v0213_closure_authority") != CANONICAL_CLOSURE_AUTHORITY or SUPERSEDED_CLOSURE_AUTHORITY not in binding.get("superseded_authorities", []):
            failures.append("binding:canonical_closure_authority_invalid")
        if binding.get("baseline_main_sha") != BASELINE_MAIN_SHA or binding.get("historical_roots_immutable") is not True:
            failures.append("binding:baseline_or_history_invalid")
    active = "\n".join((checkpoint_text, review_text, roadmap_text))
    for literal in (CURRENT_VERSION, CURRENT_PHASE, CURRENT_GATE, NEXT_ACTION, "baseline_main_sha", "GITHUB LIVE", "production_routing=BLOCKED", "new_generation=0", "maps_minimap_lifecycle=MERGED_CLOSED", "vfx_start_gate=BLOCKED"):
        if literal.casefold() not in active.casefold():
            failures.append(f"active_documents_missing:{literal}")
    return {"status": CURRENT_GATE if not failures else "UI_STATE_CONSISTENCY_FAILED", "schema_version": CURRENT_VERSION, "failures": failures, "checked": {"version": state.get("version"), "phase": state.get("phase"), "current_gate": state.get("current_gate"), "baseline_main_sha": state.get("baseline_main_sha"), "allowed_next_actions": state.get("allowed_next_actions"), "pr_state": review.get("pr_state"), "production_routing": state.get("production_routing"), "canonical_closure_authority": authority.get("canonical")}}


def _main_ci_success(live: Mapping[str, Any]) -> bool:
    ci = _mapping(live.get("post_merge_main_ci"))
    contexts = ci.get("contexts", [])
    names = tuple(item.get("name") for item in contexts if isinstance(item, Mapping))
    return names == MAIN_CONTEXTS and tuple(ci.get("supported_contexts", [])) == MAIN_CONTEXTS and all(item.get("status") == "completed" and item.get("conclusion") == "success" and item.get("head_sha") for item in contexts)


def resolve_next_actions(state: Mapping[str, Any], live_closure: Mapping[str, Any] | None) -> dict[str, Any]:
    """Resolve the lifecycle from GitHub LIVE facts; tracked prose cannot unlock VFX."""
    if state.get("allowed_next_actions") != [NEXT_ACTION]:
        return {"status": "UI_STATE_CONSISTENCY_FAILED", "allowed_next_actions": [NEXT_ACTION], "next_candidate": NEXT_CANDIDATE, "failures": ["tracked_action_invalid"]}
    live = _mapping(live_closure)
    if live.get("source_mode") != "GITHUB_LIVE" or live.get("pr_number") != 13:
        return {"status": "UI_STATE_CONSISTENCY_FAILED", "allowed_next_actions": [NEXT_ACTION], "next_candidate": NEXT_CANDIDATE, "failures": ["live_source_or_pr_invalid"]}
    approved = live.get("external_approval") is True
    merged = live.get("merged") is True
    if not approved:
        return {"status": "UI_ASSET_FAMILY_EXTERNAL_REVIEW_REQUIRED", "allowed_next_actions": [NEXT_ACTION], "next_candidate": NEXT_CANDIDATE, "vfx_allowed": False, "failures": ["external_review_unresolved"]}
    if not merged:
        return {"status": "UI_ASSET_FAMILY_APPROVED_AWAITING_GOVERNED_MERGE", "allowed_next_actions": ["governed_merge_pr_13"], "next_candidate": NEXT_CANDIDATE, "vfx_allowed": False, "failures": ["approved_but_unmerged"]}
    if not _main_ci_success(live):
        return {"status": "UI_ASSET_FAMILY_MERGED_POST_MAIN_CI_PENDING_OR_FAILED", "allowed_next_actions": ["resolve_post_merge_closure_pr_13"], "next_candidate": NEXT_CANDIDATE, "vfx_allowed": False, "failures": ["post_merge_main_ci_not_success"]}
    return {"status": "UI_ASSET_FAMILY_APPROVED_FOUNDATION_MERGED_CLOSED", "allowed_next_actions": ["start_vfx_asset_family_v0230"], "next_candidate": "VFX_ASSET_FAMILY", "vfx_allowed": True, "failures": []}


__all__ = ["BASELINE_MAIN_SHA", "CANONICAL_CLOSURE_AUTHORITY", "CURRENT_GATE", "CURRENT_PHASE", "CURRENT_VERSION", "FEATURE_BRANCH", "MAIN_CONTEXTS", "NEXT_ACTION", "NEXT_CANDIDATE", "POST_MERGE_CLOSURE_BINDING", "REQUIRED_CONTEXTS", "SUPERSEDED_CLOSURE_AUTHORITY", "resolve_next_actions", "validate_state_consistency"]
