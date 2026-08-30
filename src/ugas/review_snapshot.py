"""Shared security filename rules for the review snapshot boundary.

The review packager is intentionally ignored because it is a local delivery
tool, but its security matcher is kept in the distributed package so tests and
the tracked archive verifier exercise the same rules.  Matching is anchored
to complete path components or complete filename patterns; generic words such
as ``seed``, ``tokenizer`` and ``monkey`` are not secrets by themselves.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path


SECURITY_DIRECTORY_NAMES = frozenset({
    ".aws", ".azure", ".gcloud", "credentials", "secrets", "wallet_backup",
})

SECURITY_EXACT_FILENAMES = frozenset({"id_rsa", "id_ed25519"})

SECURITY_ANCHORED_FILENAME_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("dotenv file .env(.*)", re.compile(r"^\.env(?:\..*)?$", re.IGNORECASE)),
    ("credential basename", re.compile(r"^credentials?(?:[._-].*)?$", re.IGNORECASE)),
    ("secret basename", re.compile(r"^secrets?(?:[._-].*)?$", re.IGNORECASE)),
    ("auth basename", re.compile(r"^(?:auth|authorization)(?:[._-].*)?$", re.IGNORECASE)),
    ("private-key basename", re.compile(r"^private[_-]?key(?:[._-].*)?$", re.IGNORECASE)),
    ("API-token basename", re.compile(r"^api[_-]?token(?:[._-].*)?$", re.IGNORECASE)),
    ("access-token basename", re.compile(r"^access[_-]?token(?:[._-].*)?$", re.IGNORECASE)),
    ("service-account-key basename", re.compile(r"^service[_-]?account[_-]?key(?:[._-].*)?$", re.IGNORECASE)),
    ("wallet/recovery basename", re.compile(r"^(?:wallet|wallet[_-]?(?:backup|recovery)|seed[_-]?phrase|recovery[_-]?seed|mnemonic)(?:[._-].*)?$", re.IGNORECASE)),
)

SECURITY_FILE_PATTERNS: tuple[str, ...] = (
    "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks",
)


def security_exclusion_reason(relative: Path | str) -> str | None:
    """Return a specific security reason, or ``None`` when the path is safe."""

    path = Path(relative)
    parts = [part.casefold() for part in path.parts]
    filename = path.name.casefold()
    for component in parts[:-1]:
        if component in SECURITY_DIRECTORY_NAMES:
            return f"security: excluded directory component '{component}'"
    if filename in SECURITY_EXACT_FILENAMES:
        return f"security: exact sensitive filename '{filename}'"
    for label, pattern in SECURITY_ANCHORED_FILENAME_PATTERNS:
        if pattern.fullmatch(filename):
            return f"security: anchored filename pattern '{label}'"
    for pattern in SECURITY_FILE_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return f"security: filename pattern '{pattern}'"
    return None


def self_test_sensitive_matcher() -> dict[str, object]:
    """Exercise the public/non-secret and secret filename contract."""

    must_include = (
        "docs/evidence/v054-lanes/a-seed-54701.png",
        "docs/evidence/v054-lanes/c-seed-54702.png",
        "docs/evidence/v054-lanes/r-seed-54703.png",
        "docs/evidence/some-model-seed-metadata.json",
        "docs/evidence/tokenizer.json",
        "docs/evidence/monkey.png",
    )
    must_exclude = (
        ".env", ".env.local", "credentials.json", "private_key.pem", "id_rsa",
        "service-account-key.json", "api_token.txt", "access_token.txt",
        "seed_phrase.txt", "recovery_seed.txt", "mnemonic.txt", "wallet_backup/secret.json",
    )
    failures: list[str] = []
    for value in must_include:
        if security_exclusion_reason(Path(value)) is not None:
            failures.append(f"must-include matched: {value}")
    for value in must_exclude:
        if security_exclusion_reason(Path(value)) is None:
            failures.append(f"must-exclude did not match: {value}")
    return {
        "status": "SENSITIVE_MATCHER_SELF_TEST_PASSED" if not failures else "SENSITIVE_MATCHER_SELF_TEST_FAILED",
        "must_include_count": len(must_include),
        "must_exclude_count": len(must_exclude),
        "failures": failures,
    }
