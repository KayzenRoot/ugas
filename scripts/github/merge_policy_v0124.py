"""Pure fail-closed merge policy used by governance tests and review tooling."""

from __future__ import annotations

from typing import Any, Iterable


def merge_blockers(
    checks: Iterable[dict[str, Any]],
    *,
    required_names: Iterable[str],
    external_approval: dict[str, Any] | None,
    expected_pr_number: int,
    expected_head_sha: str,
    actual_pr_number: int,
    actual_head_sha: str,
) -> list[str]:
    required = list(required_names)
    by_name = {str(item.get("name")): item for item in checks}
    failures: list[str] = []
    for name in required:
        if name not in by_name:
            failures.append(f"required-check-missing:{name}")
        elif by_name[name].get("state") != "SUCCESS":
            failures.append(f"required-check-not-success:{name}")
    if not external_approval or external_approval.get("approved") is not True:
        failures.append("explicit-external-approval-required")
    if not external_approval or external_approval.get("pr_number") != expected_pr_number or external_approval.get("head_sha") != expected_head_sha:
        failures.append("external-approval-exact-pr-head-binding-required")
    if actual_pr_number != expected_pr_number:
        failures.append("pr-number-mismatch")
    if actual_head_sha != expected_head_sha:
        failures.append("head-sha-mismatch")
    return failures


def can_merge(*args: Any, **kwargs: Any) -> bool:
    """Return true only when every explicit blocker has been cleared."""

    return not merge_blockers(*args, **kwargs)
