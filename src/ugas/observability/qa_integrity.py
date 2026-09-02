"""Cached, fail-closed validation of the active observability evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from ..schema_validation import validate_instance, validate_schema_document
from ..state_consistency_v0121 import validate_state_consistency


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


TEXT_SUFFIXES = {".json", ".md", ".txt", ".py", ".toml", ".js", ".html", ".css"}


def _digest(path: Path) -> str:
    data = path.read_bytes()
    if path.name.casefold() == "license" or path.suffix.casefold() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_qa_semantics(tests: Mapping[str, Any], validation: Mapping[str, Any]) -> list[str]:
    """Return explicit QA-NC failures for malformed or contradictory counts."""
    failures: list[str] = []
    if not (tests.get("status") == "passed" and tests.get("failed") == 0 and tests.get("passed") == tests.get("count") and isinstance(tests.get("count"), int) and tests.get("count", 0) > 0):
        failures.append("tests_must_be_passed_failed_zero_passed_equals_count")
    if not (validation.get("status") == "passed" and validation.get("failed") == 0 and validation.get("passed") == validation.get("checks") and isinstance(validation.get("checks"), int) and validation.get("checks", 0) > 0):
        failures.append("validation_must_be_passed_failed_zero_passed_equals_checks")
    return failures


def _head(repo_root: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, timeout=0.8, check=False, shell=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"


def validate_review_index(repo_root: Path, path: Path) -> dict[str, Any]:
    failures: list[str] = []
    try:
        value = _load(path)
        schema = _load(repo_root / "schemas" / "review-index-v0.12.1.json")
        validate_schema_document(schema)
        validate_instance(value, schema)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return {"status": "GAP", "failures": [f"review-index:{type(exc).__name__}: {exc}"], "checked_at": _now(), "head": _head(repo_root)}
    if value.get("version") != "0.12.1":
        failures.append("review-index-version-invalid")
    if value.get("production_routing") != "BLOCKED":
        failures.append("review-index-production-routing-invalid")
    external = value.get("external_visual_review", {})
    if external.get("attack_front_v2_approval") != "APPROVED_PILOT" or external.get("observability_dashboard_approval") != "REQUIRED":
        failures.append("review-index-external-review-boundary-invalid")
    if value.get("scope_boundary") != {"local_only": True, "read_only": True, "telemetry_upload": False, "new_generation": 0, "new_asset_family": False, "animation_pixels_changed": False}:
        failures.append("review-index-scope-boundary-invalid")
    artifacts = value.get("artifact_set", {}).get("artifacts", [])
    listed = {item.get("path") for item in artifacts}
    required_evidence = (
        "security-xss.json", "qa-negative-controls-v0121.json", "pipeline-live-stage-v0121.json",
        "orphan-reconciliation-v0121.json", "system-gpu-process-v0121.json", "stale-last-known-v0121.json",
        "file-activity-v0121.json", "preview-security-v0121.json", "external-review-v0112-binding-correction-v0121.json",
        "animation-regression-v0112-v0121.json", "test-results-v0121.json", "validation-results-v0121.json",
    )
    failures.extend(
        f"required-evidence-missing:{name}"
        for name in required_evidence
        if not (repo_root / "docs/evidence/observability-v0121" / name).is_file()
        or f"docs/evidence/observability-v0121/{name}" not in listed
    )
    screenshots = (
        "dashboard-overview.png", "dashboard-system-gpu-processes.png", "dashboard-live-pipeline-stage.png",
        "dashboard-qa-events.png", "dashboard-mobile.png",
    )
    failures.extend(
        f"required-screenshot-missing:{name}"
        for name in screenshots
        if not (repo_root / "docs/evidence/observability-v0121" / name).is_file()
        or f"docs/evidence/observability-v0121/{name}" not in listed
    )
    if value.get("review_index") in listed:
        failures.append("review-index-self-referential")
    if value.get("artifact_set", {}).get("artifact_set_sha256") != hashlib.sha256(_canonical(artifacts).encode("utf-8")).hexdigest():
        failures.append("review-index-artifact-set-hash-invalid")
    for item in artifacts:
        relative = item.get("path", "")
        local = repo_root / relative
        if not relative or not local.is_file():
            failures.append(f"artifact-missing:{relative}")
        elif _digest(local) != item.get("sha256"):
            failures.append(f"artifact-hash-mismatch:{relative}")
    tests = value.get("tests", {})
    validation = value.get("validation", {})
    failures.extend(validate_qa_semantics(tests, validation))
    build_head = value.get("publication", {}).get("index_build_git_head")
    final_head = _head(repo_root)
    if build_head and final_head != "UNKNOWN":
        try:
            ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", build_head, final_head], cwd=repo_root, timeout=0.8, check=False, shell=False)
            if ancestor.returncode != 0:
                failures.append("review-index-build-head-not-ancestor")
        except (OSError, subprocess.TimeoutExpired):
            failures.append("review-index-ancestor-check-unavailable")
    return {"status": "PASS" if not failures else "GAP", "failures": failures, "checked_at": _now(), "head": final_head, "index_build_head": build_head, "artifact_count": len(artifacts), "visual_count": value.get("artifact_set", {}).get("visual_count")}


class ActiveEvidenceCache:
    """Cache canonical validation until an authoritative file changes."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._fingerprint: tuple[tuple[str, int, int], ...] | None = None
        self._value: dict[str, Any] | None = None

    def _files(self) -> tuple[Path, ...]:
        return (
            self.repo_root / "docs/evidence/current-state.json",
            self.repo_root / "schemas/current-state.json",
            self.repo_root / "CHECKPOINT.md",
            self.repo_root / "REVIEW-v0.12.1.md",
            self.repo_root / "docs/evidence/review-index-v0.12.1.json",
            self.repo_root / "schemas/review-index-v0.12.1.json",
        )

    def _key(self) -> tuple[tuple[str, int, int], ...]:
        values: list[tuple[str, int, int]] = []
        for path in self._files():
            try:
                stat = path.stat()
                values.append((str(path), stat.st_mtime_ns, stat.st_size))
            except OSError:
                values.append((str(path), 0, 0))
        return tuple(values)

    def validate(self) -> dict[str, Any]:
        fingerprint = self._key()
        if fingerprint == self._fingerprint and self._value is not None:
            return self._value
        failures: list[str] = []
        state: dict[str, Any] | None = None
        index_result: dict[str, Any]
        try:
            state = _load(self.repo_root / "docs/evidence/current-state.json")
            schema = _load(self.repo_root / "schemas/current-state.json")
            validate_schema_document(schema)
            validate_instance(state, schema)
            consistency = validate_state_consistency(state, (self.repo_root / "CHECKPOINT.md").read_text(encoding="utf-8"), (self.repo_root / "REVIEW-v0.12.1.md").read_text(encoding="utf-8"))
            if consistency.get("failures"):
                failures.extend(f"state:{item}" for item in consistency["failures"])
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            failures.append(f"state:{type(exc).__name__}: {exc}")
        index_result = validate_review_index(self.repo_root, self.repo_root / "docs/evidence/review-index-v0.12.1.json")
        failures.extend(f"index:{item}" for item in index_result.get("failures", []))
        tests: dict[str, Any] = {}
        validation: dict[str, Any] = {}
        try:
            index = _load(self.repo_root / "docs/evidence/review-index-v0.12.1.json")
            tests = index.get("tests", {})
            validation = index.get("validation", {})
        except (OSError, json.JSONDecodeError):
            pass
        if state and state.get("production_approved") is not False:
            failures.append("governance:production_approved_must_remain_false")
        if state and state.get("production_routing") != "BLOCKED":
            failures.append("governance:production_routing_must_remain_blocked")
        result = {
            "status": "PASS" if not failures and index_result.get("status") == "PASS" else "GAP",
            "checked_at": _now(),
            "validated_head": _head(self.repo_root),
            "failures": failures,
            "current_state": {"version": state.get("version"), "gate": state.get("current_gate"), "production_routing": state.get("production_routing"), "production_approved": state.get("production_approved"), "external_visual_review": state.get("external_visual_review")} if state else None,
            "tests": tests,
            "validation": validation,
            "review_index": index_result,
        }
        self._fingerprint = fingerprint
        self._value = result
        return result
