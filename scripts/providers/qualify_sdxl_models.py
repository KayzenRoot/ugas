"""Register and verify the exact SDXL provider artifacts outside Git.

The default invocation is read-only. ``--download`` is allowed only after the
v0.6.0 state-consistency gate has passed and downloads the four explicitly
bound files into the external ComfyUI model root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
COMFY_ROOT = Path.home() / "AppData" / "Local" / "UGAS" / "comfyui"
MODEL_ROOT = COMFY_ROOT / "models"
EVIDENCE_ROOT = ROOT / "docs" / "evidence"

MODEL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "sdxl-base-1.0",
        "source": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0",
        "source_revision": "462165984030d82259a11f4367a4eed129e94a7b",
        "filename": "sd_xl_base_1.0.safetensors",
        "folder": "checkpoints",
        "bytes": 6938078334,
        "sha256": "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b",
        "license": "CreativeML Open RAIL++-M",
        "commercial_use_status": "conditional-license-review-required",
        "evidence": "sdxl-base-model-qualification.json",
    },
    {
        "id": "xinsir-controlnet-openpose-sdxl-1.0",
        "source": "https://huggingface.co/xinsir/controlnet-openpose-sdxl-1.0",
        "source_revision": "23f966cd5cfdd3f7729c903e243d87152162d2b7",
        "filename": "xinsir-controlnet-openpose-sdxl-1.0.safetensors",
        "folder": "controlnet",
        "bytes": 2502139104,
        "sha256": "b8524e557a7df60d081f5d4a0eb109967d107df217943bf88c2d99b9ebcc06c5",
        "license": "Apache-2.0",
        "commercial_use_status": "approved",
        "evidence": "sdxl-openpose-controlnet-qualification.json",
    },
    {
        "id": "ipadapter-plus-sdxl-vit-h",
        "source": "https://huggingface.co/h94/IP-Adapter",
        "source_revision": "018e402774aeeddd60609b4ecdb7e298259dc729",
        "filename": "ip-adapter-plus_sdxl_vit-h.safetensors",
        "folder": "ipadapter",
        "bytes": 847517512,
        "sha256": "3f5062b8400c94b7159665b21ba5c62acdcd7682262743d7f2aefedef00e6581",
        "license": "Apache-2.0",
        "commercial_use_status": "approved",
        "evidence": "ipadapter-sdxl-model-qualification.json",
    },
    {
        "id": "clip-vision-vit-h",
        "source": "https://huggingface.co/h94/IP-Adapter",
        "source_revision": "018e402774aeeddd60609b4ecdb7e298259dc729",
        "filename": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
        "folder": "clip_vision",
        "bytes": 2528373448,
        "sha256": "6ca9667da1ca9e0b0f75e46bb030f7e011f44f86cbfb8d5a36590fcd7507b030",
        "license": "Apache-2.0",
        "commercial_use_status": "approved",
        "evidence": "clip-vision-qualification.json",
        "variant": "OpenCLIP-ViT-H-14",
        "pairing": "ip-adapter-plus_sdxl_vit-h.safetensors",
    },
)

DOWNLOAD_PATHS = {
    "sdxl-base-1.0": "sd_xl_base_1.0.safetensors",
    "xinsir-controlnet-openpose-sdxl-1.0": "diffusion_pytorch_model.safetensors",
    "ipadapter-plus-sdxl-vit-h": "sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors",
    "clip-vision-vit-h": "models/image_encoder/model.safetensors",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _state() -> dict[str, Any]:
    return json.loads((EVIDENCE_ROOT / "current-state.json").read_text(encoding="utf-8"))


def _check_state_for_download() -> None:
    state = _state()
    if state.get("version") != "0.6.0":
        raise RuntimeError("MODEL_DOWNLOAD_BLOCKED: active state is not v0.6.0")
    if state.get("current_gate") not in {"SDXL_MODEL_QUALIFICATION_REQUIRED", "SDXL_PROVIDER_RUNTIME_REQUIRED", "SDXL_P_I_PI_SMOKE_REQUIRED", "SDXL_STRENGTH_BENCHMARK_REQUIRED", "SDXL_POSE_PROVIDER_CONFIRMATION_REQUIRED"}:
        raise RuntimeError(f"MODEL_DOWNLOAD_BLOCKED: state gate is {state.get('current_gate')}")
    audit = json.loads((EVIDENCE_ROOT / "custom-node-audit-ipadapter-plus.json").read_text(encoding="utf-8"))
    if audit.get("audit_status") != "CUSTOM_NODE_AUDIT_PASSED" or audit.get("commit") != "a0f451a5113cf9becb0847b92884cb10cbdec0ef":
        raise RuntimeError("MODEL_DOWNLOAD_BLOCKED: pinned custom-node audit is not passed")


def _url(spec: dict[str, Any]) -> str:
    return f"{spec['source']}/resolve/{spec['source_revision']}/{DOWNLOAD_PATHS[spec['id']]}"


def _verify(spec: dict[str, Any], path: Path) -> dict[str, Any]:
    present = path.is_file()
    actual_bytes = path.stat().st_size if present else None
    actual_sha = _sha256(path) if present else None
    bytes_ok = present and actual_bytes == spec["bytes"]
    hash_ok = present and actual_sha and actual_sha.casefold() == spec["sha256"].casefold()
    return {
        "path": str(path),
        "filename": spec["filename"],
        "expected_bytes": spec["bytes"],
        "actual_bytes": actual_bytes,
        "expected_sha256": spec["sha256"],
        "actual_sha256": actual_sha,
        "present": present,
        "bytes_match": bool(bytes_ok),
        "hash_match": bool(hash_ok),
        "verified": bool(bytes_ok and hash_ok),
    }


def _download(spec: dict[str, Any], path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    digest = hashlib.sha256()
    resume_at = temporary.stat().st_size if temporary.is_file() else 0
    if resume_at:
        with temporary.open("rb") as existing:
            for chunk in iter(lambda: existing.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
    total = resume_at
    try:
        headers = {"User-Agent": "UGAS/0.6.0"}
        if resume_at:
            headers["Range"] = f"bytes={resume_at}-"
        request = urllib.request.Request(_url(spec), headers=headers)
        with urllib.request.urlopen(request, timeout=120) as response:
            resumed = resume_at and getattr(response, "status", 200) == 206
            if not resumed:
                temporary.unlink(missing_ok=True)
                digest = hashlib.sha256()
                total = 0
            output = temporary.open("ab" if resumed else "wb")
            with output:
                for chunk in iter(lambda: response.read(8 * 1024 * 1024), b""):
                    output.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
        actual = digest.hexdigest()
        if total != spec["bytes"] or actual.casefold() != spec["sha256"].casefold():
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"MODEL_HASH_MISMATCH: {spec['id']} bytes={total} sha256={actual}")
        temporary.replace(path)
        return _verify(spec, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def qualify(download: bool = False, comfy_root: Path = COMFY_ROOT) -> dict[str, Any]:
    if download:
        _check_state_for_download()
    model_root = comfy_root / "models"
    artifacts = []
    failures = []
    for spec in MODEL_SPECS:
        path = model_root / spec["folder"] / spec["filename"]
        try:
            verification = _download(spec, path) if download and not path.exists() else _verify(spec, path)
        except RuntimeError as exc:
            verification = {"path": str(path), "verified": False, "error": str(exc)}
        if not verification.get("verified"):
            failures.append("MODEL_HASH_MISMATCH" if verification.get("present") else "MODEL_ARTIFACT_MISSING")
        artifacts.append({**spec, "download_url": _url(spec), "verification": verification})
    return {
        "schema_version": "0.6.0",
        "qualified_at": _now(),
        "status": "MODEL_ARTIFACTS_VERIFIED" if not failures else sorted(set(failures))[0],
        "download_requested": download,
        "weights_outside_git": True,
        "artifacts": artifacts,
        "failures": failures,
    }


def _update_registry(result: dict[str, Any]) -> None:
    """Record hash qualification in Git while keeping conditional licenses explicit."""
    path = ROOT / "providers" / "models" / "registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    by_id = {item.get("id"): item for item in registry.get("models", [])}
    for artifact in result["artifacts"]:
        item = by_id.get(artifact["id"])
        if item is None:
            continue
        verified = bool(artifact.get("verification", {}).get("verified"))
        item["status"] = "qualified" if verified else "candidate"
        item["qualification_evidence"] = {
            "status": "MODEL_ARTIFACT_HASH_VERIFIED" if verified else result["status"],
            "hashes_verified": verified,
            "license_recorded": bool(artifact.get("license")),
            "commercial_use_status": artifact.get("commercial_use_status"),
            "evidence": f"docs/evidence/{artifact['evidence']}",
        }
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--comfy-root", type=Path, default=COMFY_ROOT)
    args = parser.parse_args()
    result = qualify(args.download, args.comfy_root)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    for artifact in result["artifacts"]:
        path = EVIDENCE_ROOT / artifact["evidence"]
        path.write_text(json.dumps({**artifact, "status": "MODEL_HASH_AND_LICENSE_VERIFIED" if artifact["verification"].get("verified") and artifact["commercial_use_status"] == "approved" else "MODEL_ARTIFACT_VERIFIED_LICENSE_REVIEW_REQUIRED" if artifact["verification"].get("verified") else result["status"]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (EVIDENCE_ROOT / "sdxl-model-stack-qualification.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _update_registry(result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result["failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
