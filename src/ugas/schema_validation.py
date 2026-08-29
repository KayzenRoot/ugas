"""Dependency-free subset validator for the JSON Schema contracts we ship.

If jsonschema is installed, callers may use it separately. This module keeps
the production bootstrap and validation scripts usable without dependencies.
"""

from __future__ import annotations

import re
from typing import Any


class SchemaValidationError(ValueError):
    pass


JSON_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def validate_schema_document(schema: dict[str, Any]) -> None:
    """Check the supported Draft 2020-12 vocabulary and its structure."""
    if not isinstance(schema, dict):
        raise SchemaValidationError("schema must be an object")
    if not str(schema.get("$schema", "")).endswith("/draft/2020-12/schema"):
        raise SchemaValidationError("schema must declare Draft 2020-12")

    def walk(node: Any, location: str) -> None:
        if not isinstance(node, dict):
            raise SchemaValidationError(f"{location} must be an object")
        if "type" in node:
            types = node["type"] if isinstance(node["type"], list) else [node["type"]]
            if not types or any(item not in JSON_TYPES for item in types):
                raise SchemaValidationError(f"{location}.type contains an invalid JSON type")
        if "required" in node:
            if not isinstance(node["required"], list) or any(not isinstance(item, str) for item in node["required"]):
                raise SchemaValidationError(f"{location}.required must be a string list")
        if "properties" in node:
            if not isinstance(node["properties"], dict):
                raise SchemaValidationError(f"{location}.properties must be an object")
            for key, value in node["properties"].items():
                if not isinstance(key, str):
                    raise SchemaValidationError(f"{location}.properties has a non-string key")
                walk(value, f"{location}.properties.{key}")
        if "items" in node:
            walk(node["items"], f"{location}.items")
        if "enum" in node and (not isinstance(node["enum"], list) or not node["enum"]):
            raise SchemaValidationError(f"{location}.enum must be a non-empty list")
        if "additionalProperties" in node and not isinstance(node["additionalProperties"], bool):
            raise SchemaValidationError(f"{location}.additionalProperties must be boolean")
        if "pattern" in node:
            try:
                re.compile(node["pattern"])
            except re.error as exc:
                raise SchemaValidationError(f"{location}.pattern is invalid: {exc}") from exc

    walk(schema, "$")


def validate_instance(instance: Any, schema: dict[str, Any], path: str = "$") -> None:
    expected = schema.get("type")
    expected_types = expected if isinstance(expected, list) else [expected] if expected else []
    if expected_types and not any(_matches_type(instance, item) for item in expected_types):
        raise SchemaValidationError(f"{path} must be {', '.join(expected_types)}")
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaValidationError(f"{path} must be one of {schema['enum']}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                raise SchemaValidationError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(instance).difference(properties))
            if unknown:
                raise SchemaValidationError(f"{path} has unknown properties {unknown}")
        for key, child_schema in properties.items():
            if key in instance:
                validate_instance(instance[key], child_schema, f"{path}.{key}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise SchemaValidationError(f"{path} has too few items")
        if "items" in schema:
            for index, item in enumerate(instance):
                validate_instance(item, schema["items"], f"{path}[{index}]")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise SchemaValidationError(f"{path} is too short")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise SchemaValidationError(f"{path} does not match the required pattern")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool) and instance < schema.get("minimum", instance):
        raise SchemaValidationError(f"{path} is below the minimum")
