"""Small dependency-free Agent Skills frontmatter validator."""

from __future__ import annotations

import re


FRONTMATTER_RE = re.compile(r"\A---\r?\n(?P<body>.*?)\r?\n---\r?\n", re.DOTALL)
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("SKILL.md must start with YAML frontmatter")
    values: dict[str, str] = {}
    in_metadata = False
    for raw_line in match.group("body").splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith("  ") and in_metadata:
            key, separator, value = raw_line.strip().partition(":")
            if separator:
                values[f"metadata.{key.strip()}"] = value.strip().strip('"\'')
            continue
        key, separator, value = raw_line.partition(":")
        if not separator:
            raise ValueError(f"invalid frontmatter line: {raw_line}")
        key = key.strip()
        values[key] = value.strip().strip('"\'')
        in_metadata = key == "metadata"
    return values


def validate_skill_frontmatter(text: str, expected_name: str) -> tuple[bool, list[str], dict[str, str]]:
    try:
        values = parse_frontmatter(text)
    except ValueError as exc:
        return False, [str(exc)], {}
    errors: list[str] = []
    name = values.get("name", "")
    description = values.get("description", "")
    if not name:
        errors.append("name is required")
    elif not NAME_RE.fullmatch(name):
        errors.append("name must be lowercase kebab-case")
    elif name != expected_name:
        errors.append(f"name {name!r} does not match folder {expected_name!r}")
    if len(description) < 40:
        errors.append("description must be specific and at least 40 characters")
    if not values.get("license"):
        errors.append("license is required")
    if values.get("metadata.ugas-version") != "0.2.1":
        errors.append("metadata.ugas-version must be 0.2.1")
    return not errors, errors, values
