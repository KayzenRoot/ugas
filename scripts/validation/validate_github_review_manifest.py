"""Validate the v0.12.3 GitHub review manifest and truthful visual transport."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ugas.schema_validation import validate_instance, validate_schema_document
from build_review_visual_transport_v0123 import decoded_pixel_hash, detect_media_type


EXPECTED_SOURCES = {
    "docs/evidence/observability-v0122/dashboard-docker-overview-v0122.png",
    "docs/evidence/observability-v0122/dashboard-docker-live-activity-v0122.png",
}
EXPECTED_GATES = {"unit_tests", "official_validation", "state_consistency", "capability_matrix", "visual_transport", "manifest_validation", "security"}
PNG_SIGNATURE = "89504E470D0A1A0A"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(root: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or path.startswith(("/", "\\")):
        raise ValueError(f"absolute-path:{path}")
    return root / candidate


def validate_declared_media_type(path: Path, declared: str) -> str | None:
    """Return a failure when a declaration disagrees with magic bytes."""
    try:
        actual = detect_media_type(path.read_bytes())
    except (OSError, ValueError) as exc:
        return f"media-signature:{path.as_posix()}:{type(exc).__name__}:{exc}"
    if actual != declared:
        return f"media-declaration-mismatch:{path.as_posix()}:declared={declared}:actual={actual}"
    return None


def validate_visual_manifest(visuals: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    failures: list[str] = []
    try:
        visual_schema = json.loads((root / "schemas/review-visual-transport-v1.json").read_text(encoding="utf-8"))
        validate_schema_document(visual_schema)
        validate_instance(visuals, visual_schema)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        failures.append(f"visual-schema:{type(exc).__name__}:{exc}")
    if visuals.get("schema_version") != "1.0":
        failures.append("visual-schema-version-invalid")
    if visuals.get("manifest_type") != "review-visual-transport":
        failures.append("visual-manifest-type-invalid")
    items = visuals.get("visuals")
    if not isinstance(items, list) or len(items) != 2:
        return {"status": "FAIL", "failures": failures + ["visual-manifest-must-contain-two-transport-files"], "visual_count": len(items) if isinstance(items, list) else 0}
    seen_sources: set[str] = set()
    seen_transports: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            failures.append("visual-entry-not-object")
            continue
        source_name = str(item.get("source_path", ""))
        transport_name = str(item.get("transport_path", ""))
        seen_sources.add(source_name)
        seen_transports.add(transport_name)
        if source_name not in EXPECTED_SOURCES:
            failures.append(f"unexpected-source:{source_name}")
            continue
        if not transport_name.startswith("docs/evidence/github-review-v0123/visuals/") or not transport_name.endswith(".png"):
            failures.append(f"transport-path-invalid:{transport_name}")
            continue
        try:
            source = _relative(root, source_name)
            transport = _relative(root, transport_name)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        if not source.is_file():
            failures.append(f"source-missing:{source_name}")
            continue
        if not transport.is_file():
            failures.append(f"transport-missing:{transport_name}")
            continue
        source_bytes = source.read_bytes()
        transport_bytes = transport.read_bytes()
        try:
            source_type = detect_media_type(source_bytes)
            transport_type = detect_media_type(transport_bytes)
        except ValueError as exc:
            failures.append(f"signature:{exc}")
            continue
        source_declaration_failure = validate_declared_media_type(source, item.get("source_media_type"))
        transport_declaration_failure = validate_declared_media_type(transport, item.get("transport_media_type"))
        if source_declaration_failure:
            failures.append(source_declaration_failure)
        if transport_declaration_failure:
            failures.append(transport_declaration_failure)
        if source_type != item.get("source_media_type") or source_type != "image/jpeg":
            failures.append(f"source-media-type-mismatch:{source_name}")
        if transport_type != item.get("transport_media_type") or transport_type != "image/png":
            failures.append(f"transport-media-type-mismatch:{transport_name}")
        if transport_bytes[:8].hex().upper() != PNG_SIGNATURE or item.get("transport_signature") != PNG_SIGNATURE:
            failures.append(f"png-signature-mismatch:{transport_name}")
        if item.get("source_size") != len(source_bytes) or item.get("source_sha256") != digest(source):
            failures.append(f"source-byte-hash-mismatch:{source_name}")
        if item.get("transport_size") != len(transport_bytes) or item.get("transport_sha256") != digest(transport):
            failures.append(f"transport-byte-hash-mismatch:{transport_name}")
        try:
            from PIL import Image

            with Image.open(source) as source_image, Image.open(transport) as transport_image:
                source_image.load()
                transport_image.load()
                source_pixels = decoded_pixel_hash(source_image)
                transport_pixels = decoded_pixel_hash(transport_image)
                if (item.get("width"), item.get("height")) != source_image.size or transport_image.size != source_image.size:
                    failures.append(f"dimensions-mismatch:{source_name}")
                if item.get("source_decoded_pixel_sha256") != source_pixels or item.get("transport_decoded_pixel_sha256") != transport_pixels:
                    failures.append(f"decoded-pixel-hash-mismatch:{source_name}")
                if not item.get("decoded_pixel_equal") or source_pixels != transport_pixels:
                    failures.append(f"decoded-pixels-not-equivalent:{source_name}")
        except (OSError, ValueError) as exc:
            failures.append(f"decode:{source_name}:{type(exc).__name__}:{exc}")
    if seen_sources != EXPECTED_SOURCES:
        failures.append("source-set-invalid")
    if len(seen_transports) != 2:
        failures.append("transport-paths-not-unique")
    return {"status": "PASS" if not failures else "FAIL", "failures": failures, "visual_count": len(items)}


def _result_is_truthful(result: dict[str, Any], *, validation: bool = False) -> bool:
    total_key = "checks" if validation else "count"
    total = result.get(total_key)
    if result.get("status") == "passed":
        return result.get("exit_code") == 0 and result.get("parse_status") == "parsed" and isinstance(total, int) and result.get("passed") == total and result.get("failed") == 0
    return result.get("status") in {"failed", "parse_failed", "not_run"} and result.get("exit_code") is not None


def validate(manifest_path: Path, visual_path: Path) -> dict[str, Any]:
    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "schemas/github-review-manifest-v1.json").read_text(encoding="utf-8"))
        validate_schema_document(schema)
        validate_instance(manifest, schema)
        visuals = json.loads(visual_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return {"status": "GITHUB_REVIEW_MANIFEST_FAILED", "failures": [f"schema:{type(exc).__name__}: {exc}"]}

    if manifest.get("schema_version") != "1.0" or manifest.get("manifest_type") != "github-native-review":
        failures.append("manifest-identity-invalid")
    pr = manifest.get("pull_request", {})
    number = pr.get("number")
    gaps = set(manifest.get("known_gaps", []))
    context = manifest.get("gap_context", {})
    if number and "GITHUB_PR_CREATE_GAP" in gaps:
        failures.append("pr-number-positive-cannot-have-github-pr-create-gap")
    if number == 0 and context.get("source") == "local_rehearsal" and "LOCAL_REHEARSAL_PR_NOT_AVAILABLE" not in gaps:
        failures.append("local-rehearsal-gap-description-missing")
    if any(item in gaps for item in ("GITHUB_RULESET_GAP", "CODEOWNERS_GAP")) and not context.get("explicit_gap_input"):
        failures.append("repository-gap-not-backed-by-explicit-context")
    if manifest.get("change_statistics", {}).get("files") != len(manifest.get("changed_files", [])):
        failures.append("change-statistics-file-count-mismatch")
    if not _result_is_truthful(manifest.get("tests", {})):
        failures.append("unit-result-not-truthful")
    if not _result_is_truthful(manifest.get("validation", {}), validation=True):
        failures.append("validation-result-not-truthful")
    gates = manifest.get("gates", [])
    gate_ids = {item.get("id") for item in gates if isinstance(item, dict)}
    if gate_ids != EXPECTED_GATES:
        failures.append("gate-set-invalid")
    if manifest.get("overall_status") != ("PASS" if gates and all(item.get("status") == "PASS" for item in gates) else "FAIL"):
        failures.append("overall-status-does-not-match-gates")
    visual_result = validate_visual_manifest(visuals, ROOT)
    failures.extend(f"visual:{item}" for item in visual_result.get("failures", []))
    return {"status": "GITHUB_REVIEW_MANIFEST_PASSED" if not failures else "GITHUB_REVIEW_MANIFEST_FAILED", "failures": failures, "changed_file_count": len(manifest.get("changed_files", [])), "visual_count": visual_result.get("visual_count", 0), "overall_status": manifest.get("overall_status"), "base_sha": pr.get("base_sha"), "head_sha": pr.get("head_sha")}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", default=str(ROOT / "docs/evidence/github-review-v0123/github-review-manifest-local.json"))
    parser.add_argument("visual", nargs="?")
    parser.add_argument("--result-output")
    args = parser.parse_args()
    manifest = Path(args.manifest)
    visual = Path(args.visual) if args.visual else manifest.with_name("visual-manifest.json")
    result = validate(manifest, visual)
    if args.result_output:
        Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "GITHUB_REVIEW_MANIFEST_PASSED" else 1)
