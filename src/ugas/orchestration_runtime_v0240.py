"""Provider-neutral orchestration control plane for UGAS v0.24.0.

This module is deliberately TEST_ONLY.  It owns request/DAG identity,
deterministic scheduling, bounded execution state, retries, checkpoints,
cache identity and evidence-safe telemetry without importing or calling a
provider client.  The real generation pipeline remains unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json
import ntpath
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


VERSION = "0.24.0"
SCHEMA_VERSION = VERSION
TEST_ONLY_MARKER = "TEST_ONLY"
SUPPORTED_ASSET_FAMILIES = (
    "equipment_outfits",
    "creatures_monsters",
    "items_props",
    "environment_tilesets",
    "maps_minimap",
    "ui_asset_family",
    "vfx_asset_family",
)

REQUEST_FIELDS = {
    "schema_version", "request_id", "project_id", "request_kind", "asset_family",
    "operation", "inputs", "dependency_refs", "outputs", "quality_profile",
    "budget_profile", "priority", "timeout_seconds", "retry_policy",
    "idempotency_key", "production_intent", "test_only", "request_hash",
}
REQUEST_REQUIRED = REQUEST_FIELDS - {"request_hash"}
DAG_FIELDS = {"schema_version", "dag_id", "project_id", "request_hash", "nodes", "dag_hash"}
NODE_FIELDS = {
    "node_id", "dependencies", "operation", "input_contract_hash", "dependency_hashes",
    "timeout_seconds", "retry_policy", "resource_class", "scheduling_key", "priority",
    "asset_family",
}
MAX_NODES = 64
MAX_DEPTH = 16
MAX_FANOUT = 16
MAX_RETRIES = 3
MAX_TELEMETRY_FIELDS = 24
MAX_TELEMETRY_STRING = 160


class OrchestrationContractError(RuntimeError):
    """A fail-closed contract rejection with a stable class."""

    def __init__(self, rejection_class: str, detail: str):
        self.rejection_class = rejection_class
        self.detail = detail
        super().__init__(f"{rejection_class}: {detail}")


class RetryableExecutionError(RuntimeError):
    error_class = "TRANSIENT_EXECUTION_ERROR"


class NonRetryableExecutionError(RuntimeError):
    error_class = "EXECUTION_CONTRACT_ERROR"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _reject(rejection_class: str, detail: str) -> None:
    raise OrchestrationContractError(rejection_class, detail)


def strict_boolean_observation(observed: Any) -> bool:
    """Return true only for the literal boolean True."""

    return type(observed) is bool and observed is True


def strict_gate(gate_id: str, observed: Any, detail: str = "") -> dict[str, Any]:
    """Preserve the real observed value/type while applying a strict gate."""

    passed = strict_boolean_observation(observed)
    return {
        "gate_id": gate_id,
        "observed": observed,
        "observed_type": type(observed).__name__,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
    }


def _assert_no_unknown(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        _reject("ORCH_UNKNOWN_FIELD", f"{label} contains unknown fields: {unknown}")


def _assert_sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value.casefold()):
        _reject("ORCH_HASH_INVALID", f"{label} must be a lowercase SHA-256 hex digest")


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _validate_no_secret_like(value: Any) -> None:
    secret_words = ("token", "api_key", "apikey", "password", "authorization", "secret", "credential", "private_key")
    if any(any(word in key.casefold() for word in secret_words) for key in _walk_keys(value)):
        _reject("ORCH_SECRET_LIKE_DATA_REJECTED", "secret-like fields are not allowed in orchestration evidence")


def _validate_project_identity(request: Mapping[str, Any], expected_project_id: str | None = None) -> None:
    project_id = request.get("project_id")
    if not isinstance(project_id, str) or not project_id or project_id.strip() != project_id:
        _reject("ORCH_PROJECT_ID_INVALID", "project_id must be a non-empty canonical string")
    if expected_project_id is not None and project_id != expected_project_id:
        _reject("ORCH_CROSS_PROJECT_IDENTITY", "request project identity does not match the execution project")
    refs = request.get("dependency_refs", [])
    for reference in refs:
        if not isinstance(reference, Mapping) or reference.get("project_id") != project_id:
            _reject("ORCH_CROSS_PROJECT_IDENTITY", "dependency reference crosses project identity")


def validate_request(request: Mapping[str, Any], expected_project_id: str | None = None) -> dict[str, Any]:
    if not isinstance(request, Mapping):
        _reject("ORCH_REQUEST_INVALID", "request must be an object")
    value = copy.deepcopy(dict(request))
    _assert_no_unknown(value, REQUEST_FIELDS, "request")
    missing = sorted(REQUEST_REQUIRED - set(value))
    if missing:
        _reject("ORCH_REQUEST_REQUIRED_FIELD_MISSING", f"request is missing {missing}")
    if value.get("schema_version") != SCHEMA_VERSION:
        _reject("ORCH_REQUEST_SCHEMA_UNSUPPORTED", "unsupported request schema")
    if value.get("request_kind") != "ASSET_OPERATION":
        _reject("ORCH_REQUEST_KIND_INVALID", "only ASSET_OPERATION is supported")
    if value.get("asset_family") not in SUPPORTED_ASSET_FAMILIES:
        _reject("ORCH_UNKNOWN_ASSET_FAMILY", "asset family is not in the closed runtime registry")
    if value.get("operation") not in {"VALIDATE", "EXECUTE", "RESUME"}:
        _reject("ORCH_OPERATION_INVALID", "unsupported orchestration operation")
    if not isinstance(value.get("request_id"), str) or not value["request_id"]:
        _reject("ORCH_REQUEST_ID_INVALID", "request_id is required")
    if not isinstance(value.get("idempotency_key"), str) or not value["idempotency_key"]:
        _reject("ORCH_IDEMPOTENCY_KEY_INVALID", "idempotency_key is required")
    if not isinstance(value.get("inputs"), Mapping) or not isinstance(value.get("outputs"), Mapping):
        _reject("ORCH_IO_CONTRACT_INVALID", "inputs and outputs must be objects")
    if not isinstance(value.get("dependency_refs"), list):
        _reject("ORCH_DEPENDENCY_REFS_INVALID", "dependency_refs must be a list")
    if type(value.get("production_intent")) is not bool or value["production_intent"] is not False:
        _reject("ORCH_PRODUCTION_INTENT_REJECTED", "production_intent must be the literal false")
    if type(value.get("test_only")) is not bool or value["test_only"] is not True:
        _reject("ORCH_TEST_ONLY_MARKER_REQUIRED", "test_only must be the literal true")
    if not isinstance(value.get("priority"), int) or isinstance(value["priority"], bool) or not 0 <= value["priority"] <= 100:
        _reject("ORCH_PRIORITY_INVALID", "priority must be an integer from 0 through 100")
    if not isinstance(value.get("timeout_seconds"), int) or isinstance(value["timeout_seconds"], bool) or not 1 <= value["timeout_seconds"] <= 3600:
        _reject("ORCH_TIMEOUT_INVALID", "timeout_seconds must be a bounded positive integer")
    retry = value.get("retry_policy")
    if not isinstance(retry, Mapping) or set(retry) - {"max_attempts", "retryable_errors"}:
        _reject("ORCH_RETRY_POLICY_INVALID", "retry_policy schema is invalid")
    if not isinstance(retry.get("max_attempts"), int) or isinstance(retry["max_attempts"], bool) or not 1 <= retry["max_attempts"] <= MAX_RETRIES:
        _reject("ORCH_RETRY_POLICY_INVALID", "retry_policy.max_attempts exceeds the bounded limit")
    if not isinstance(retry.get("retryable_errors"), list) or not all(isinstance(item, str) for item in retry["retryable_errors"]):
        _reject("ORCH_RETRY_POLICY_INVALID", "retryable_errors must be a string list")
    _validate_project_identity(value, expected_project_id)
    _validate_no_secret_like(value)
    supplied_hash = value.pop("request_hash", None)
    computed_hash = sha256_value(value)
    if supplied_hash is not None and supplied_hash != computed_hash:
        _reject("ORCH_REQUEST_HASH_MISMATCH", "request hash does not match canonical request bytes")
    value["request_hash"] = computed_hash
    return value


def build_request(**kwargs: Any) -> dict[str, Any]:
    value = {"schema_version": SCHEMA_VERSION, **kwargs}
    return validate_request(value)


def _node_contract_payload(node: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(node[key]) for key in NODE_FIELDS if key not in {"dependency_hashes"} and key in node}


def node_contract_hash(node: Mapping[str, Any]) -> str:
    return sha256_value(_node_contract_payload(node))


def _validate_node(node: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(node, Mapping):
        _reject("ORCH_DAG_NODE_INVALID", "DAG node must be an object")
    value = copy.deepcopy(dict(node))
    _assert_no_unknown(value, NODE_FIELDS, "DAG node")
    missing = sorted(NODE_FIELDS - set(value))
    if missing:
        _reject("ORCH_DAG_NODE_REQUIRED_FIELD_MISSING", f"DAG node is missing {missing}")
    if not isinstance(value["node_id"], str) or not value["node_id"]:
        _reject("ORCH_DAG_NODE_ID_INVALID", "node_id is required")
    if not isinstance(value["dependencies"], list) or not all(isinstance(item, str) for item in value["dependencies"]):
        _reject("ORCH_DAG_DEPENDENCY_INVALID", "dependencies must be a string list")
    if len(value["dependencies"]) != len(set(value["dependencies"])):
        _reject("ORCH_DAG_DUPLICATE_DEPENDENCY", "node dependencies must be unique")
    if not isinstance(value["dependency_hashes"], Mapping):
        _reject("ORCH_DAG_DEPENDENCY_HASHES_INVALID", "dependency_hashes must be an object")
    if set(value["dependency_hashes"]) != set(value["dependencies"]):
        _reject("ORCH_DAG_DEPENDENCY_HASHES_INVALID", "dependency hash keys must equal dependencies")
    _assert_sha(value["input_contract_hash"], "input_contract_hash")
    for dependency_hash in value["dependency_hashes"].values():
        _assert_sha(dependency_hash, "dependency_hash")
    if not isinstance(value["timeout_seconds"], int) or isinstance(value["timeout_seconds"], bool) or not 1 <= value["timeout_seconds"] <= 3600:
        _reject("ORCH_DAG_TIMEOUT_INVALID", "node timeout is not bounded")
    retry = value["retry_policy"]
    if not isinstance(retry, Mapping) or set(retry) - {"max_attempts", "retryable_errors"} or not isinstance(retry.get("retryable_errors"), list):
        _reject("ORCH_DAG_RETRY_POLICY_INVALID", "node retry policy is invalid")
    if not isinstance(retry.get("max_attempts"), int) or isinstance(retry["max_attempts"], bool) or not 1 <= retry["max_attempts"] <= MAX_RETRIES:
        _reject("ORCH_DAG_RETRY_POLICY_INVALID", "node retry count is unbounded")
    if "EXECUTION_CONTRACT_ERROR" in retry["retryable_errors"]:
        _reject("ORCH_NONRETRYABLE_ERROR_POLICY_REJECTED", "contract/security errors may not be retried")
    if not isinstance(value["resource_class"], str) or not value["resource_class"]:
        _reject("ORCH_DAG_RESOURCE_CLASS_INVALID", "resource_class is required")
    if not isinstance(value["scheduling_key"], str) or not value["scheduling_key"]:
        _reject("ORCH_DAG_SCHEDULING_KEY_INVALID", "scheduling_key is required")
    if not isinstance(value["priority"], int) or isinstance(value["priority"], bool) or not 0 <= value["priority"] <= 100:
        _reject("ORCH_DAG_PRIORITY_INVALID", "node priority is not bounded")
    if value["asset_family"] not in SUPPORTED_ASSET_FAMILIES:
        _reject("ORCH_UNKNOWN_ASSET_FAMILY", "node asset family is not supported")
    return value


def build_dag(request: Mapping[str, Any], nodes: list[Mapping[str, Any]], dag_id: str = "dag-1") -> dict[str, Any]:
    validated_request = validate_request(request)
    if not isinstance(nodes, list) or not nodes or len(nodes) > MAX_NODES:
        _reject("ORCH_DAG_BOUNDS_EXCEEDED", "DAG node count is outside the bounded range")
    prepared: list[dict[str, Any]] = []
    for raw in nodes:
        item = copy.deepcopy(dict(raw))
        item.setdefault("dependency_hashes", {})
        prepared.append(item)
    by_id = {item["node_id"]: item for item in prepared}
    if len(by_id) != len(prepared):
        _reject("ORCH_DAG_DUPLICATE_NODE_ID", "node identifiers must be unique")
    for item in prepared:
        for dependency in item["dependencies"]:
            if dependency not in by_id:
                _reject("ORCH_DAG_MISSING_DEPENDENCY", f"unknown dependency {dependency}")
            item["dependency_hashes"][dependency] = node_contract_hash(by_id[dependency])
        _validate_node(item)
    dag = {"schema_version": SCHEMA_VERSION, "dag_id": dag_id, "project_id": validated_request["project_id"], "request_hash": validated_request["request_hash"], "nodes": prepared}
    return validate_dag(dag, validated_request)


def _depths(nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    memo: dict[str, int] = {}
    visiting: set[str] = set()
    def depth(node_id: str) -> int:
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            _reject("ORCH_DAG_CYCLE", "DAG contains a cycle")
        visiting.add(node_id)
        parents = nodes[node_id]["dependencies"]
        memo[node_id] = 1 + max((depth(parent) for parent in parents), default=0)
        visiting.remove(node_id)
        return memo[node_id]
    for node_id in nodes:
        depth(node_id)
    return memo


def validate_dag(dag: Mapping[str, Any], request: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(dag, Mapping):
        _reject("ORCH_DAG_INVALID", "DAG must be an object")
    value = copy.deepcopy(dict(dag))
    _assert_no_unknown(value, DAG_FIELDS, "DAG")
    if value.get("schema_version") != SCHEMA_VERSION:
        _reject("ORCH_DAG_SCHEMA_UNSUPPORTED", "unsupported DAG schema")
    nodes_raw = value.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw or len(nodes_raw) > MAX_NODES:
        _reject("ORCH_DAG_BOUNDS_EXCEEDED", "DAG node count is outside the bounded range")
    nodes = [_validate_node(item) for item in nodes_raw]
    by_id = {item["node_id"]: item for item in nodes}
    if len(by_id) != len(nodes):
        _reject("ORCH_DAG_DUPLICATE_NODE_ID", "node identifiers must be unique")
    if request is not None:
        validated_request = validate_request(request)
        if value.get("project_id") != validated_request["project_id"]:
            _reject("ORCH_CROSS_PROJECT_IDENTITY", "DAG project does not match request project")
        if value.get("request_hash") != validated_request["request_hash"]:
            _reject("ORCH_DAG_REQUEST_HASH_MISMATCH", "DAG is not bound to the request")
    for item in nodes:
        if item["node_id"] in item["dependencies"]:
            _reject("ORCH_DAG_SELF_DEPENDENCY", "node cannot depend on itself")
        for dependency in item["dependencies"]:
            if dependency not in by_id:
                _reject("ORCH_DAG_MISSING_DEPENDENCY", f"unknown dependency {dependency}")
            expected = node_contract_hash(by_id[dependency])
            if item["dependency_hashes"].get(dependency) != expected:
                _reject("ORCH_DAG_STALE_DEPENDENCY_HASH", f"dependency hash is stale for {dependency}")
    depths = _depths(by_id)
    if max(depths.values()) > MAX_DEPTH:
        _reject("ORCH_DAG_DEPTH_EXCEEDED", "DAG depth exceeds the bounded limit")
    fanout = {node_id: 0 for node_id in by_id}
    for item in nodes:
        for dependency in item["dependencies"]:
            fanout[dependency] += 1
    if max(fanout.values(), default=0) > MAX_FANOUT:
        _reject("ORCH_DAG_FANOUT_EXCEEDED", "DAG fanout exceeds the bounded limit")
    supplied_hash = value.pop("dag_hash", None)
    computed_hash = sha256_value(value)
    if supplied_hash is not None and supplied_hash != computed_hash:
        _reject("ORCH_DAG_HASH_MISMATCH", "DAG hash does not match canonical DAG bytes")
    value["nodes"] = nodes
    value["dag_hash"] = computed_hash
    return value


def deterministic_schedule(dag: Mapping[str, Any]) -> list[str]:
    value = validate_dag(dag)
    nodes = {item["node_id"]: item for item in value["nodes"]}
    remaining = {node_id: set(item["dependencies"]) for node_id, item in nodes.items()}
    schedule: list[str] = []
    while remaining:
        ready = sorted((node_id for node_id, deps in remaining.items() if not deps), key=lambda node_id: (-nodes[node_id]["priority"], node_id))
        if not ready:
            _reject("ORCH_DAG_CYCLE", "DAG could not produce a dependency-first schedule")
        for node_id in ready:
            schedule.append(node_id)
            remaining.pop(node_id)
            for deps in remaining.values():
                deps.discard(node_id)
    return schedule


ALLOWED_TRANSITIONS = {
    "PLANNED": {"VALIDATED", "CANCELLED", "BLOCKED"},
    "VALIDATED": {"READY", "CANCELLED", "BLOCKED"},
    "READY": {"DISPATCHED", "CANCELLED", "BLOCKED"},
    "DISPATCHED": {"RUNNING", "CANCELLED", "FAILED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "CANCELLED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
    "BLOCKED": set(),
}
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED", "BLOCKED"}


def _event_hash(previous: str, event: Mapping[str, Any]) -> str:
    return sha256_value({"previous_event_hash": previous, "event": event})


@dataclass
class FakeExecutor:
    """Deterministic executor; no provider/client import or network path."""

    executions: int = 0
    provider_submit_calls: int = 0

    def execute(self, request: Mapping[str, Any], node: Mapping[str, Any]) -> dict[str, Any]:
        self.executions += 1
        result_hash = sha256_value({"request_hash": request["request_hash"], "node_id": node["node_id"], "input_contract_hash": node["input_contract_hash"]})
        return {
            "status": "SUCCEEDED",
            "execution_id": f"fake-{result_hash[:16]}",
            "result_hash": result_hash,
            "provider": None,
            "synthetic": True,
            "test_only": True,
        }


@dataclass
class OrchestrationRuntime:
    request: dict[str, Any]
    dag: dict[str, Any]
    max_concurrency: int = 4
    family_limits: dict[str, int] = field(default_factory=dict)
    executor: FakeExecutor = field(default_factory=FakeExecutor)
    states: dict[str, str] = field(init=False)
    results: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    attempts: dict[str, int] = field(default_factory=dict, init=False)
    events: list[dict[str, Any]] = field(default_factory=list, init=False)
    active: int = field(default=0, init=False)
    peak_concurrency: int = field(default=0, init=False)
    _last_event_hash: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.request = validate_request(self.request)
        self.dag = validate_dag(self.dag, self.request)
        if not isinstance(self.max_concurrency, int) or isinstance(self.max_concurrency, bool) or not 1 <= self.max_concurrency <= MAX_NODES:
            _reject("ORCH_CONCURRENCY_BOUND_INVALID", "global concurrency must be bounded")
        self.states = {node["node_id"]: "PLANNED" for node in self.dag["nodes"]}

    @property
    def scheduler_hash(self) -> str:
        return sha256_value(deterministic_schedule(self.dag))

    def transition(self, node_id: str, new_state: str, detail: str = "") -> dict[str, Any]:
        if node_id not in self.states:
            _reject("ORCH_UNKNOWN_NODE", f"unknown node {node_id}")
        current = self.states[node_id]
        if new_state not in ALLOWED_TRANSITIONS.get(current, set()):
            _reject("ORCH_ILLEGAL_STATE_TRANSITION", f"{current} -> {new_state} is not allowed")
        self.states[node_id] = new_state
        event = {"sequence": len(self.events) + 1, "node_id": node_id, "from": current, "to": new_state, "detail": detail}
        event["event_hash"] = _event_hash(self._last_event_hash, event)
        self._last_event_hash = event["event_hash"]
        self.events.append(event)
        return copy.deepcopy(event)

    def dispatch(self, node_id: str) -> dict[str, Any]:
        state = self.states.get(node_id)
        if state is None:
            _reject("ORCH_UNKNOWN_NODE", f"unknown node {node_id}")
        if state in TERMINAL_STATES:
            return {"duplicate": True, "state": state, "result": copy.deepcopy(self.results.get(node_id))}
        if state == "DISPATCHED" or state == "RUNNING":
            return {"duplicate": True, "state": state, "result": copy.deepcopy(self.results.get(node_id))}
        if state == "PLANNED":
            self.transition(node_id, "VALIDATED")
        if self.states[node_id] == "VALIDATED":
            self.transition(node_id, "READY")
        self.transition(node_id, "DISPATCHED")
        return {"duplicate": False, "state": "DISPATCHED"}

    def cancel(self, node_id: str) -> dict[str, Any]:
        if node_id not in self.states:
            _reject("ORCH_UNKNOWN_NODE", f"unknown node {node_id}")
        if self.states[node_id] in TERMINAL_STATES:
            return {"node_id": node_id, "state": self.states[node_id], "idempotent": True}
        self.transition(node_id, "CANCELLED", "explicit bounded cancellation")
        return {"node_id": node_id, "state": "CANCELLED", "idempotent": False}

    def retry(self, node_id: str) -> None:
        if node_id not in self.states:
            _reject("ORCH_UNKNOWN_NODE", f"unknown node {node_id}")
        if self.states[node_id] in TERMINAL_STATES:
            _reject("ORCH_RETRY_AFTER_TERMINAL_REJECTED", "terminal execution cannot be retried")
        _reject("ORCH_RETRY_ONLY_THROUGH_BOUNDED_RUN", "retry is controlled by the bounded execution loop")

    def _blocked_by_dependency(self, node: Mapping[str, Any]) -> bool:
        return any(self.states[dependency] in {"FAILED", "CANCELLED", "BLOCKED"} for dependency in node["dependencies"])

    def _admit(self, node: Mapping[str, Any]) -> None:
        if self.active >= self.max_concurrency:
            _reject("ORCH_GLOBAL_CONCURRENCY_EXCEEDED", "global concurrency bound exceeded")
        family_limit = self.family_limits.get(node["asset_family"], self.max_concurrency)
        running_family = sum(1 for node_id, state in self.states.items() if state == "RUNNING" and self._node(node_id)["asset_family"] == node["asset_family"])
        if running_family >= family_limit:
            _reject("ORCH_FAMILY_CONCURRENCY_EXCEEDED", "asset family concurrency bound exceeded")

    def _node(self, node_id: str) -> dict[str, Any]:
        return next(node for node in self.dag["nodes"] if node["node_id"] == node_id)

    def _execute_one(self, node: dict[str, Any], fault: str | None = None) -> None:
        node_id = node["node_id"]
        self.dispatch(node_id)
        self._admit(node)
        self.transition(node_id, "RUNNING")
        self.active += 1
        self.peak_concurrency = max(self.peak_concurrency, self.active)
        max_attempts = node["retry_policy"]["max_attempts"]
        retryable = set(node["retry_policy"]["retryable_errors"])
        try:
            for attempt in range(1, max_attempts + 1):
                self.attempts[node_id] = attempt
                try:
                    if fault == "timeout":
                        raise RetryableExecutionError("deterministic timeout")
                    if fault == "retryable" and attempt == 1:
                        raise RetryableExecutionError("deterministic transient error")
                    if fault == "nonretryable":
                        raise NonRetryableExecutionError("deterministic contract error")
                    self.results[node_id] = self.executor.execute(self.request, node)
                    self.transition(node_id, "SUCCEEDED")
                    return
                except RetryableExecutionError as exc:
                    if type(exc).error_class not in retryable or attempt >= max_attempts:
                        self.transition(node_id, "FAILED", type(exc).error_class)
                        return
                except NonRetryableExecutionError as exc:
                    self.transition(node_id, "FAILED", type(exc).error_class)
                    return
        finally:
            self.active -= 1

    def run(self, faults: Mapping[str, str] | None = None, cancellations: Iterable[str] = ()) -> dict[str, Any]:
        fault_map = dict(faults or {})
        cancellation_set = set(cancellations)
        for node_id in deterministic_schedule(self.dag):
            node = self._node(node_id)
            if node_id in cancellation_set:
                self.cancel(node_id)
                continue
            if self._blocked_by_dependency(node):
                if self.states[node_id] == "PLANNED":
                    self.transition(node_id, "BLOCKED", "dependency terminal failure")
                continue
            if self.states[node_id] in TERMINAL_STATES:
                continue
            self._execute_one(node, fault_map.get(node_id))
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_hash": self.request["request_hash"],
            "dag_hash": self.dag["dag_hash"],
            "scheduler_hash": self.scheduler_hash,
            "states": copy.deepcopy(self.states),
            "results": copy.deepcopy(self.results),
            "attempts": copy.deepcopy(self.attempts),
            "events": copy.deepcopy(self.events),
            "event_sequence": len(self.events),
            "event_hash": self._last_event_hash,
            "peak_concurrency": self.peak_concurrency,
            "provider_submit_calls": self.executor.provider_submit_calls,
            "test_only": True,
        }

    def checkpoint(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        completed = {node_id: result["result_hash"] for node_id, result in self.results.items() if self.states.get(node_id) == "SUCCEEDED"}
        snapshot["completed_result_hashes"] = completed
        snapshot["completed_hash"] = sha256_value(completed)
        snapshot["checkpoint_hash"] = sha256_value(snapshot)
        return snapshot


def validate_checkpoint(checkpoint: Mapping[str, Any], request: Mapping[str, Any], dag: Mapping[str, Any], completed_results: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if not isinstance(checkpoint, Mapping):
        _reject("ORCH_CHECKPOINT_INVALID", "checkpoint must be an object")
    value = copy.deepcopy(dict(checkpoint))
    supplied_hash = value.pop("checkpoint_hash", None)
    if supplied_hash is None or supplied_hash != sha256_value(value):
        _reject("ORCH_CHECKPOINT_TAMPERED", "checkpoint hash is absent or invalid")
    request_value = validate_request(request)
    dag_value = validate_dag(dag, request_value)
    if value.get("request_hash") != request_value["request_hash"]:
        _reject("ORCH_CHECKPOINT_STALE", "checkpoint request identity is stale")
    if value.get("dag_hash") != dag_value["dag_hash"]:
        _reject("ORCH_CHECKPOINT_STALE", "checkpoint DAG identity is stale")
    if value.get("scheduler_hash") != sha256_value(deterministic_schedule(dag_value)):
        _reject("ORCH_CHECKPOINT_SCHEDULER_MISMATCH", "checkpoint scheduler identity is stale")
    if value.get("test_only") is not True:
        _reject("ORCH_CHECKPOINT_INVALID", "checkpoint must remain TEST_ONLY")
    states = value.get("states")
    if not isinstance(states, Mapping) or any(state not in ALLOWED_TRANSITIONS for state in states.values()):
        _reject("ORCH_CHECKPOINT_INVALID", "checkpoint contains an unknown state")
    completed = value.get("completed_result_hashes", {})
    if not isinstance(completed, Mapping) or value.get("completed_hash") != sha256_value(completed):
        _reject("ORCH_CHECKPOINT_RESULT_HASH_TAMPERED", "completed result identity is invalid")
    if completed_results is not None:
        for node_id, result_hash in completed.items():
            result = completed_results.get(node_id)
            if not isinstance(result, Mapping) or result.get("result_hash") != result_hash or result.get("status") != "SUCCEEDED":
                _reject("ORCH_CHECKPOINT_RESULT_HASH_TAMPERED", f"completed result is not bound for {node_id}")
    sequence = value.get("event_sequence")
    events = value.get("events")
    if not isinstance(sequence, int) or not isinstance(events, list) or sequence != len(events):
        _reject("ORCH_CHECKPOINT_EVENT_SEQUENCE_INVALID", "event sequence is not monotonic")
    previous = ""
    for expected_sequence, event in enumerate(events, 1):
        if event.get("sequence") != expected_sequence or event.get("event_hash") != _event_hash(previous, {key: event[key] for key in event if key != "event_hash"}):
            _reject("ORCH_CHECKPOINT_EVENT_SEQUENCE_INVALID", "event hash chain is invalid")
        previous = event["event_hash"]
    return {"status": "PASS", "request_hash": request_value["request_hash"], "dag_hash": dag_value["dag_hash"], "completed": len(completed), "event_sequence": sequence}


def atomic_write_checkpoint(path: Path, checkpoint: Mapping[str, Any]) -> Path:
    target = Path(path)
    if target.exists() and target.is_symlink():
        _reject("ORCH_SYMLINK_PATH_REJECTED", "checkpoint target may not be a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(dict(checkpoint), ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def validate_safe_relative_path(value: str, *, root: Path | None = None) -> str:
    if not isinstance(value, str) or not value or ntpath.isabs(value) or value.startswith("/"):
        _reject("ORCH_ABSOLUTE_PATH_REJECTED", "absolute output paths are forbidden")
    parts = Path(value.replace("\\", "/")).parts
    if ".." in parts:
        _reject("ORCH_PATH_TRAVERSAL_REJECTED", "path traversal is forbidden")
    if root is not None:
        candidate = (root / Path(*parts)).resolve()
        root_resolved = root.resolve()
        if candidate != root_resolved and root_resolved not in candidate.parents:
            _reject("ORCH_PATH_TRAVERSAL_REJECTED", "resolved path escapes output root")
    return "/".join(parts)


def validate_output_identity(project_id: str, output: Mapping[str, Any]) -> None:
    if output.get("project_id") != project_id:
        _reject("ORCH_CROSS_PROJECT_OUTPUT", "output project identity does not match request")
    validate_safe_relative_path(output.get("path", ""))


def validate_schedule_observation(dag: Mapping[str, Any], observed: Any) -> None:
    expected = deterministic_schedule(dag)
    if observed != expected:
        _reject("ORCH_SCHEDULER_NONDETERMINISTIC", "observed schedule differs from the canonical schedule")


def validate_concurrency_observation(peak: Any, global_limit: int, family_limits: Mapping[str, int] | None = None, family_peaks: Mapping[str, int] | None = None) -> None:
    if not isinstance(peak, int) or peak < 0 or peak > global_limit:
        _reject("ORCH_GLOBAL_CONCURRENCY_EXCEEDED", "observed peak exceeds global concurrency")
    for family, family_peak in (family_peaks or {}).items():
        if family_peak > (family_limits or {}).get(family, global_limit):
            _reject("ORCH_FAMILY_CONCURRENCY_EXCEEDED", f"observed peak exceeds family bound for {family}")


def validate_no_dynamic_nodes(initial_node_ids: Iterable[str], observed_node_ids: Iterable[str]) -> None:
    if set(initial_node_ids) != set(observed_node_ids):
        _reject("ORCH_DYNAMIC_NODE_REJECTED", "execution introduced or removed a node")


def validate_idempotent_replay(executions_before: Any, executions_after: Any, duplicate: Any) -> None:
    if duplicate is True and executions_after != executions_before:
        _reject("ORCH_IDEMPOTENT_REPLAY_VIOLATION", "duplicate dispatch executed work twice")


def validate_terminal_immutability(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    if before.get("states") != after.get("states") or before.get("results") != after.get("results"):
        _reject("ORCH_TERMINAL_MUTATION_REJECTED", "terminal execution changed after cancellation/retry input")


def validate_circuit_access(breaker: "CircuitBreaker", attempted: Any) -> None:
    if breaker.state == "OPEN" and attempted is True:
        _reject("ORCH_CIRCUIT_BREAKER_BYPASS", "open circuit accepted a dispatch")


def validate_provider_submit_count(observed: Any) -> None:
    if type(observed) is not int or observed != 0:
        _reject("ORCH_REAL_PROVIDER_SUBMIT_REJECTED", "provider submission count must remain zero")


def validate_production_boundary(record: Mapping[str, Any]) -> None:
    if record.get("production_routing") != "BLOCKED" or record.get("production_approved") is not False or record.get("new_generation") != 0:
        _reject("ORCH_PRODUCTION_BOUNDARY_REJECTED", "production routing, approval and generation must remain blocked")


def validate_no_repo_local_uads(repo_root: Path) -> None:
    if (Path(repo_root) / ".uads").exists():
        _reject("ORCH_REPO_LOCAL_UADS_FOOTPRINT", "UADS runtime state must remain outside the repository")


def sanitize_telemetry(event: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"event", "request_hash", "dag_hash", "node_id", "state", "sequence", "status", "resource_class", "duration_ms", "error_class"}
    _validate_no_secret_like(event)
    _assert_no_unknown(event, allowed, "telemetry")
    value = copy.deepcopy(dict(event))
    for key, child in value.items():
        if isinstance(child, str) and (ntpath.isabs(child) or "\\" in child and ":" in child):
            _reject("ORCH_TELEMETRY_PATH_REJECTED", f"telemetry field {key} contains an absolute path")
        if isinstance(child, str) and len(child) > MAX_TELEMETRY_STRING:
            _reject("ORCH_TELEMETRY_BOUNDS_EXCEEDED", f"telemetry field {key} is too long")
    if len(value) > MAX_TELEMETRY_FIELDS:
        _reject("ORCH_TELEMETRY_BOUNDS_EXCEEDED", "telemetry event has too many fields")
    return value


class ExecutionCache:
    """In-memory cache keyed by project, request identity and DAG identity."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str], dict[str, Any]] = {}

    def put(self, request: Mapping[str, Any], dag: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
        if any(state != "SUCCEEDED" for state in snapshot.get("states", {}).values()):
            _reject("ORCH_CACHE_NON_SUCCESS_REJECTED", "failed, blocked or cancelled execution cannot populate success cache")
        key = (request["project_id"], request["idempotency_key"], dag["dag_hash"])
        entry = {"source_execution_id": sha256_value(snapshot)[0:16], "result_hashes": copy.deepcopy(snapshot.get("completed_result_hashes", {})), "status": "SUCCEEDED", "project_id": request["project_id"], "request_hash": request["request_hash"], "dag_hash": dag["dag_hash"]}
        self._entries[key] = entry
        return copy.deepcopy(entry)

    def get(self, request: Mapping[str, Any], dag: Mapping[str, Any]) -> dict[str, Any] | None:
        entry = self._entries.get((request["project_id"], request["idempotency_key"], dag["dag_hash"]))
        if entry is None or entry.get("status") != "SUCCEEDED":
            return None
        return copy.deepcopy(entry)


@dataclass
class CircuitBreaker:
    failure_threshold: int = 2
    state: str = "CLOSED"
    failures: int = 0

    def allow(self) -> bool:
        return self.state in {"CLOSED", "HALF_OPEN"}

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"

    def half_open(self) -> None:
        if self.state == "OPEN":
            self.state = "HALF_OPEN"

    def record_success(self) -> None:
        self.failures = 0
        self.state = "CLOSED"


class CircuitRegistry:
    def __init__(self) -> None:
        self._breakers: dict[tuple[str, str], CircuitBreaker] = {}

    def for_identity(self, project_id: str, request_id: str) -> CircuitBreaker:
        return self._breakers.setdefault((project_id, request_id), CircuitBreaker())


def adapt_legacy_generation_request(legacy: Mapping[str, Any], project_id: str) -> dict[str, Any]:
    """Narrow adapter: map old job identity into the new control plane only."""

    allowed = {"job_id", "asset_family", "inputs", "outputs", "profile", "seed"}
    _assert_no_unknown(legacy, allowed, "legacy generation request")
    return build_request(
        request_id=str(legacy.get("job_id", "legacy-request")),
        project_id=project_id,
        request_kind="ASSET_OPERATION",
        asset_family=legacy.get("asset_family"),
        operation="EXECUTE",
        inputs={"legacy": copy.deepcopy(legacy.get("inputs", {})), "profile": legacy.get("profile"), "seed": legacy.get("seed")},
        dependency_refs=[],
        outputs=copy.deepcopy(legacy.get("outputs", {})),
        quality_profile="legacy-compatible",
        budget_profile="bounded-test-only",
        priority=0,
        timeout_seconds=60,
        retry_policy={"max_attempts": 1, "retryable_errors": []},
        idempotency_key=f"legacy:{legacy.get('job_id', 'unknown')}",
        production_intent=False,
        test_only=True,
    )


HARD_GATE_IDS = (
    "canonical_request", "request_hash", "dag_schema", "dag_acyclic", "dag_dependency_hashes",
    "scheduler_dependency_first", "scheduler_priority_lexical", "scheduler_deterministic", "bounded_global_concurrency",
    "bounded_family_concurrency", "no_dynamic_nodes", "state_transition_contract", "terminal_immutability",
    "idempotent_dispatch", "failure_isolation", "bounded_cancellation", "bounded_retry", "retryable_error_class",
    "timeout_determinism", "no_retry_after_success", "no_retry_after_cancel", "circuit_breaker_isolated",
    "checkpoint_binding", "checkpoint_tamper_rejection", "resume_identity", "cache_identity", "cache_success_only",
    "result_provenance", "fake_executor_determinism", "provider_submit_count_zero", "asset_contracts_read_only",
    "telemetry_sanitized", "production_boundary", "legacy_adapter_narrow", "historical_closure_binding",
)


def evaluate_hard_gates(observations: Mapping[str, Any]) -> dict[str, Any]:
    gates = {gate_id: strict_gate(gate_id, observations.get(gate_id), "actual checker observation") for gate_id in HARD_GATE_IDS}
    return {"schema_version": SCHEMA_VERSION, "gates": gates, "overall_pass": all(item["status"] == "PASS" for item in gates.values())}


__all__ = [
    "ALLOWED_TRANSITIONS", "CircuitBreaker", "CircuitRegistry", "ExecutionCache", "FakeExecutor",
    "HARD_GATE_IDS", "MAX_DEPTH", "MAX_FANOUT", "MAX_NODES", "OrchestrationContractError",
    "OrchestrationRuntime", "RetryableExecutionError", "SUPPORTED_ASSET_FAMILIES", "VERSION",
    "adapt_legacy_generation_request", "atomic_write_checkpoint", "build_dag", "build_request",
    "canonical_json", "deterministic_schedule", "evaluate_hard_gates", "node_contract_hash",
    "sanitize_telemetry", "sha256_value", "strict_boolean_observation", "strict_gate",
    "validate_checkpoint", "validate_circuit_access", "validate_concurrency_observation", "validate_dag", "validate_idempotent_replay", "validate_no_dynamic_nodes",
    "validate_no_repo_local_uads", "validate_output_identity", "validate_production_boundary",
    "validate_provider_submit_count", "validate_request", "validate_safe_relative_path", "validate_terminal_immutability",
    "validate_schedule_observation",
]
