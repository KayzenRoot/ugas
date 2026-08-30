"""Fail-closed RefControl LoRA verification and strength benchmark."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any

from .comfyui_client import ComfyUIClient
from .generation import QUALITY_MODEL, _model_names, _run_job, _unique_job_dir, background_remove
from .identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256
from .image_utils import sha256
from .master_assets import write_json
from .model_registry import file_sha256, load_model, verify_model_files
from .multiview import AB_POSE_GAIN, _contact_sheet_with_labels, _score_output, normalize_frame
from .openpose_guides import OPENPOSE_GUIDE_RENDERER_VERSION, guide_hash
from .pose_control import _legacy_guide
from .workflow_registry import bind_workflow, load_workflow, validate_api_workflow, workflow_hash


REFCONTROL_MODEL_ID = "xocialize-refcontrol-flux2-klein-4b-pose-lora"
REFCONTROL_FILE = "refcontrol-pose-klein-4b.safetensors"
REFCONTROL_STRENGTHS = (0.8, 0.9, 1.0)
REFCONTROL_TRIAGE_SEEDS = (52711, 52712)
REFCONTROL_CONFIRMATION_SEED = 52713
REFCONTROL_PROMPT_CORE = "refcontrol, apply pose from image 1 with reference from image 2"


class RefControlError(RuntimeError):
    pass


def _repo_model_root() -> Path:
    return Path.home() / "AppData" / "Local" / "UGAS" / "comfyui" / "models"


def _read_native_gap(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "docs/evidence/native-reference-order-qualification.json"
    if not path.is_file():
        raise RefControlError("native reference-order qualification evidence is missing")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    if evidence.get("status") != "NATIVE_REFERENCE_ORDER_POSE_CONTROL_GAP":
        raise RefControlError("RefControl is forbidden unless native reference-order status is a gap")
    return evidence


def _reverify_license(model: dict[str, Any]) -> dict[str, Any]:
    source = str(model["source"]).rstrip("/")
    revision = str(model["source_revision"])
    card_url = f"{source}/raw/{revision}/README.md"
    request = urllib.request.Request(card_url, headers={"User-Agent": "UGAS/0.5.2 license verifier"})
    with urllib.request.urlopen(request, timeout=30) as response:
        card = response.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
    lower = card.casefold()
    approved = "apache-2.0" in lower or "apache 2.0" in lower
    return {"status": "LICENSE_REVERIFIED" if approved else "MODEL_LICENSE_GAP", "source": source, "revision": revision, "card_url": card_url, "license": "Apache-2.0" if approved else None, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "card_sha256": hashlib.sha256(card.encode("utf-8")).hexdigest()}


def verify_refcontrol_model(repo_root: Path, *, model_root: Path | None = None, endpoint: str = "http://127.0.0.1:8188") -> dict[str, Any]:
    native = _read_native_gap(repo_root)
    model = load_model(repo_root, REFCONTROL_MODEL_ID)
    root = (model_root or _repo_model_root()).resolve()
    destination = root / "loras" / REFCONTROL_FILE
    expected = model["sha256"]["loras/refcontrol-pose-klein-4b.safetensors"]
    try:
        license_evidence = _reverify_license(model)
    except Exception as exc:
        evidence = {"schema_version": "0.5.2", "status": "MODEL_LICENSE_GAP", "stop_reason": "MODEL_LICENSE_GAP", "native_gap_status": native.get("status"), "model_id": REFCONTROL_MODEL_ID, "source": model.get("source"), "source_revision": model.get("source_revision"), "file": REFCONTROL_FILE, "expected_sha256": expected, "license_error": f"{type(exc).__name__}: {exc}"}
        write_json(repo_root / "docs/evidence/refcontrol-model-qualification.json", evidence)
        return evidence
    download = None
    if destination.is_file():
        actual = file_sha256(destination)
        if actual.casefold() != expected.casefold():
            evidence = {"schema_version": "0.5.2", "status": "MODEL_HASH_MISMATCH", "stop_reason": "MODEL_HASH_MISMATCH", "native_gap_status": native.get("status"), "model_id": REFCONTROL_MODEL_ID, "source": model.get("source"), "source_revision": model.get("source_revision"), "file": str(destination), "expected_sha256": expected, "actual_sha256": actual, "bytes": destination.stat().st_size, "license": license_evidence}
            write_json(repo_root / "docs/evidence/refcontrol-model-qualification.json", evidence)
            return evidence
    else:
        url = model["download_files"]["loras/refcontrol-pose-klein-4b.safetensors"]
        try:
            from .model_registry import download_exact
            download = download_exact(url, destination, expected, timeout=180.0)
        except Exception as exc:
            evidence = {"schema_version": "0.5.2", "status": "MODEL_HASH_MISMATCH", "stop_reason": "MODEL_HASH_MISMATCH", "native_gap_status": native.get("status"), "model_id": REFCONTROL_MODEL_ID, "source": model.get("source"), "source_revision": model.get("source_revision"), "file": str(destination), "expected_sha256": expected, "actual_sha256": file_sha256(destination) if destination.is_file() else None, "bytes": destination.stat().st_size if destination.is_file() else None, "license": license_evidence, "download_error": f"{type(exc).__name__}: {exc}"}
            write_json(repo_root / "docs/evidence/refcontrol-model-qualification.json", evidence)
            return evidence
    verification = verify_model_files(model, root)
    actual = file_sha256(destination) if destination.is_file() else None
    evidence = {
        "schema_version": "0.5.2",
        "status": "MODEL_HASH_AND_LICENSE_VERIFIED" if verification["qualified"] else "MODEL_HASH_MISMATCH",
        "stop_reason": None if verification["qualified"] else "MODEL_HASH_MISMATCH",
        "native_gap_status": native.get("status"),
        "model_id": REFCONTROL_MODEL_ID,
        "base_model_id": model.get("base_model_id"),
        "source": model.get("source"),
        "source_revision": model.get("source_revision"),
        "file": str(destination),
        "filename": REFCONTROL_FILE,
        "expected_sha256": expected,
        "actual_sha256": actual,
        "bytes": destination.stat().st_size if destination.is_file() else None,
        "approx_size": "92.4 MB",
        "license": license_evidence,
        "download": download,
        "verification": verification,
        "weights_outside_git": True,
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(repo_root / "docs/evidence/refcontrol-model-qualification.json", evidence)
    return evidence


def inspect_refcontrol_native_loader(repo_root: Path, client: ComfyUIClient) -> dict[str, Any]:
    info = client.node_info()
    candidates = []
    for node_name in ("LoraLoaderModelOnly", "LoraLoader"):
        node = info.get(node_name)
        required = ((node or {}).get("input") or {}).get("required", {}) if isinstance(node, dict) else {}
        output = (node or {}).get("output", []) if isinstance(node, dict) else []
        native = isinstance(node, dict) and node.get("python_module") in {"nodes", "comfy_extras.nodes_model_merging"}
        compatible = native and "model" in required and "lora_name" in required and "strength_model" in required and "MODEL" in output
        candidates.append({"node": node_name, "present": isinstance(node, dict), "python_module": node.get("python_module") if isinstance(node, dict) else None, "required_inputs": sorted(required), "outputs": output, "native": native, "compatible": compatible})
    selected = next((item for item in candidates if item["compatible"]), None)
    return {"status": "REFCONTROL_NATIVE_LORA_LOADER_FOUND" if selected else "REFCONTROL_NATIVE_LORA_LOAD_GAP", "selected": selected, "candidates": candidates, "object_info_sha256": hashlib.sha256(json.dumps({key: info.get(key) for key in ("LoraLoaderModelOnly", "LoraLoader")}, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(), "custom_nodes_required": []}


def _overlay(repo_root: Path, record: dict[str, Any], guide: dict[str, Any], destination: Path) -> Path:
    from PIL import Image, ImageDraw
    source = Path(record["normalized_output"])
    image = Image.open(source).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    legacy = _legacy_guide(guide)["keypoints"]
    result = record["score"]["pose"]["keypoints"]
    names = (("shoulder_left", "elbow_left"), ("elbow_left", "hand_left"), ("shoulder_right", "elbow_right"), ("elbow_right", "hand_right"), ("pelvis", "knee_left"), ("knee_left", "foot_left"), ("pelvis", "knee_right"), ("knee_right", "foot_right"), ("weapon_grip", "weapon_tip"))
    lower = {"pelvis", "knee_left", "foot_left", "knee_right", "foot_right"}
    for left, right in names:
        a, b = legacy[left], legacy[right]
        key_left = result.get(left, {}).get("hit", False); key_right = result.get(right, {}).get("hit", False)
        color = (40, 235, 100, 220) if key_left and key_right else (235, 45, 45, 230)
        if left in lower or right in lower:
            color = (40, 190, 255, 230) if key_left and key_right else (255, 150, 30, 230)
        draw.line((a[0], a[1], b[0], b[1]), fill=color, width=5)
    for name, point in legacy.items():
        hit = result.get(name, {}).get("hit", False)
        color = (40, 235, 100, 235) if hit else (235, 45, 45, 235)
        if name in lower:
            color = (40, 190, 255, 235) if hit else (255, 150, 30, 235)
        x, y = point; draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=False)
    return destination


def _run_refcontrol_candidate(repo_root: Path, client: ComfyUIClient, *, strength: float, seed: int, anchor: Path, guide_image: Path, guide: dict[str, Any], output_root: Path) -> dict[str, Any]:
    workflow_id = "flux2-klein-base-4b-quality-refcontrol-pose"
    record = load_workflow(repo_root, workflow_id)
    ref_model = load_model(repo_root, REFCONTROL_MODEL_ID)
    base_model = load_model(repo_root, QUALITY_MODEL)
    uploads = [client.upload_image(anchor), client.upload_image(guide_image)]
    uploaded = [item.get("name") or item.get("filename") for item in uploads]
    if not all(isinstance(item, str) and item for item in uploaded):
        raise RefControlError("ComfyUI upload did not return exact reference filenames")
    workflow = bind_workflow(record["api"], prompt=f"{REFCONTROL_PROMPT_CORE}. Preserve exact face, armor, black cloth, sword and proportions; full body, no text, no watermark.", seed=seed, width=512, height=512, model_names=_model_names(base_model), image_filenames=[str(uploaded[0]), str(uploaded[1])], lora_name=REFCONTROL_FILE, lora_strength=strength)
    graph = validate_api_workflow(workflow, node_info=client.node_info())
    if not graph["live_valid"]:
        raise RefControlError(f"RefControl workflow native node validation failed: {graph['missing_nodes']}")
    stage = f"refcontrol-strength-{strength:.1f}-seed-{seed}"
    job_dir = _unique_job_dir(repo_root, output_root, stage)
    prompt = f"{REFCONTROL_PROMPT_CORE}. Preserve exact face, armor, black cloth, sword and proportions; full body, no text, no watermark."
    input_hashes = {"reference_order": ["openpose-coco18-pose-guide", "identity-anchor"], "reference_filenames": [str(uploaded[1]), str(uploaded[0])], "reference_sha256": [sha256(guide_image), sha256(anchor)], "canonical_anchor_sha256": ANCHOR_SHA256, "openpose_guide_image_sha256": sha256(guide_image), "openpose_guide_json_sha256": guide_hash(guide), "lora_sha256": ref_model["sha256"]["loras/refcontrol-pose-klein-4b.safetensors"]}
    context = {"phase": "POSE_CONTROL_ESCALATION", "stage": stage, "reference_order": ["openpose-coco18-pose-guide", "identity-anchor"], "prompt_core": REFCONTROL_PROMPT_CORE, "source_anchor_revision_id": ANCHOR_REVISION_ID, "source_anchor_sha256": ANCHOR_SHA256, "guide_sha256": guide_hash(guide), "lora_model_id": REFCONTROL_MODEL_ID, "lora_filename": REFCONTROL_FILE, "lora_strength": strength, "previous_frame_chaining": False, "workflow_template_sha256": record["sha256"], "workflow_bound_sha256": workflow_hash(workflow)}
    result, outputs = _run_job(repo_root, client, workflow, output_dir=job_dir, filename=f"{stage}.png", profile="generic-2d", capability="refcontrol-pose-edit", workflow_id=workflow_id, model_id=REFCONTROL_MODEL_ID, prompt=prompt, seed=seed, width=512, height=512, input_hashes=input_hashes, qualification_context=context, workflow_sha256=workflow_hash(workflow))
    generated = Path(outputs[0]["path"])
    transparency = background_remove(repo_root, str(generated), endpoint=client.base_url, output_dir=job_dir / "background-removal", promote=False)
    legacy = _legacy_guide(guide)
    normalized = job_dir / "normalized.png"
    normalization = normalize_frame(Path(transparency["output"]), normalized, frame_name=stage, guide=legacy)
    score = _score_output(normalized, legacy, anchor)
    execution = result["job"].get("execution_evidence", {})
    return {"schema_version": "0.5.2", "strength": strength, "seed": seed, "workflow_id": workflow_id, "workflow_template_sha256": record["sha256"], "workflow_bound_sha256": workflow_hash(workflow), "model_id": REFCONTROL_MODEL_ID, "lora_filename": REFCONTROL_FILE, "lora_strength": strength, "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "reference_order": ["openpose-coco18-pose-guide", "identity-anchor"], "reference_filenames": [str(uploaded[1]), str(uploaded[0])], "input_hashes": input_hashes, "output": str(generated), "output_sha256": sha256(generated), "normalized_output": str(normalized), "normalized_sha256": sha256(normalized), "background_removal": transparency, "normalization": normalization, "score": score, "eligible": bool(score.get("technical", {}).get("eligible") and score.get("identity_pass") and score.get("pose", {}).get("pose_score", 0) >= 0.80), "execution_evidence": execution, "fresh_binding": execution.get("fresh_binding") is True, "previous_frame_input": None}


def _strength_summary(records: list[dict[str, Any]], strength: float, baseline_mean: float) -> dict[str, Any]:
    items = [item for item in records if item.get("strength") == strength]
    scored = [item for item in items if item.get("score")]
    poses = [float(item["score"]["pose"]["pose_score"]) for item in scored]
    identities = [float(item["score"]["identity"]["identity_descriptor_score"]) for item in scored]
    weapons = [item["score"].get("weapon_present") is True for item in scored]
    valid = len(items) == 3 and len(scored) == 3 and all(item.get("eligible") and item.get("fresh_binding") is True for item in items) and len(weapons) == 3 and all(weapons)
    mean = sum(poses) / len(poses) if poses else 0.0
    return {"strength": strength, "records": len(items), "scored": len(scored), "pose_mean": round(mean, 6), "pose_floor": round(min(poses), 6) if poses else 0.0, "pose_gain_over_A": round(mean - baseline_mean, 6), "identity_min": round(min(identities), 6) if identities else 0.0, "weapon_3_of_3": len(weapons) == 3 and all(weapons), "fresh_3_of_3": len(items) == 3 and all(item.get("fresh_binding") is True for item in items), "valid_before_threshold": valid, "qualified": bool(valid and mean >= baseline_mean + AB_POSE_GAIN and mean >= 0.88 and min(poses, default=0.0) >= 0.80)}


def qualify_refcontrol(repo_root: Path, *, endpoint: str = "http://127.0.0.1:8188", model_root: Path | None = None) -> dict[str, Any]:
    native = _read_native_gap(repo_root)
    native_execution: dict[str, Any] = {}
    native_execution_path = repo_root / "docs/evidence/execution-evidence-v0.5.2.json"
    if native_execution_path.is_file():
        try:
            previous_execution = json.loads(native_execution_path.read_text(encoding="utf-8"))
            native_execution = previous_execution.get("native_benchmark", previous_execution)
        except (OSError, json.JSONDecodeError):
            native_execution = {}
    model = verify_refcontrol_model(repo_root, model_root=model_root, endpoint=endpoint)
    client = ComfyUIClient(endpoint, timeout=90.0)
    loader = inspect_refcontrol_native_loader(repo_root, client)
    model["native_loader"] = loader
    write_json(repo_root / "docs/evidence/refcontrol-model-qualification.json", model)
    if model.get("status") != "MODEL_HASH_AND_LICENSE_VERIFIED":
        return {"schema_version": "0.5.2", "status": model.get("status"), "stop_reason": model.get("stop_reason"), "model": model, "native_loader": loader}
    if loader.get("status") != "REFCONTROL_NATIVE_LORA_LOADER_FOUND":
        evidence = {"schema_version": "0.5.2", "status": "REFCONTROL_NATIVE_LORA_LOAD_GAP", "stop_reason": "REFCONTROL_NATIVE_LORA_LOAD_GAP", "model": model, "native_loader": loader}
        write_json(repo_root / "docs/evidence/refcontrol-pose-qualification.json", evidence)
        return evidence
    guide_path = repo_root / native["guide"]["path"]
    guide = json.loads(guide_path.read_text(encoding="utf-8"))
    guide_image = repo_root / native["guide"]["control_path"]
    anchor = repo_root / "docs/evidence/reference-edit-selected-transparent.png"
    baseline_mean = float(native.get("baseline_A_pose_mean", 0.0))
    records: list[dict[str, Any]] = []
    execution_records: list[dict[str, Any]] = []
    for strength in REFCONTROL_STRENGTHS:
        for seed in REFCONTROL_TRIAGE_SEEDS:
            try:
                item = _run_refcontrol_candidate(repo_root, client, strength=strength, seed=seed, anchor=anchor, guide_image=guide_image, guide=guide, output_root=repo_root / "tmp" / "pose-control-v052" / "refcontrol")
                records.append(item)
                execution_records.append({"stage": f"refcontrol-{strength:.1f}-{seed}", "image_edit": item["execution_evidence"], "background_removal": item["background_removal"].get("execution_evidence", {}), "reference_order": item["reference_order"], "workflow_sha256": item["workflow_bound_sha256"], "lora_strength": strength})
            except Exception as exc:
                records.append({"schema_version": "0.5.2", "strength": strength, "seed": seed, "error": f"{type(exc).__name__}: {exc}", "fresh_binding": False, "previous_frame_input": None})
    triage_summaries = [_strength_summary(records, strength, baseline_mean) for strength in REFCONTROL_STRENGTHS]
    winner = max(triage_summaries, key=lambda item: (item["pose_mean"], item["identity_min"], -item["strength"]))
    if winner["scored"]:
        strength = winner["strength"]
        try:
            item = _run_refcontrol_candidate(repo_root, client, strength=strength, seed=REFCONTROL_CONFIRMATION_SEED, anchor=anchor, guide_image=guide_image, guide=guide, output_root=repo_root / "tmp" / "pose-control-v052" / "refcontrol")
            records.append(item)
            execution_records.append({"stage": f"refcontrol-confirmation-{strength:.1f}-{REFCONTROL_CONFIRMATION_SEED}", "image_edit": item["execution_evidence"], "background_removal": item["background_removal"].get("execution_evidence", {}), "reference_order": item["reference_order"], "workflow_sha256": item["workflow_bound_sha256"], "lora_strength": strength})
        except Exception as exc:
            records.append({"schema_version": "0.5.2", "strength": strength, "seed": REFCONTROL_CONFIRMATION_SEED, "error": f"{type(exc).__name__}: {exc}", "fresh_binding": False, "previous_frame_input": None})
    summaries = [_strength_summary(records, strength, baseline_mean) for strength in REFCONTROL_STRENGTHS]
    qualified = [item for item in summaries if item["qualified"]]
    status = "REFCONTROL_POSE_QUALIFIED" if qualified else "LOCAL_POSE_CONTROL_PROVIDER_GAP"
    stop_reason = None if qualified else "LOCAL_POSE_CONTROL_PROVIDER_GAP"
    overlays: list[Path] = []
    labels: list[str] = []
    for item in records:
        if item.get("score"):
            path = _overlay(repo_root, item, guide, repo_root / "tmp" / "pose-control-v052" / "refcontrol-overlays" / f"strength-{item['strength']:.1f}-seed-{item['seed']}.png")
            overlays.append(path); labels.append(f"strength={item['strength']:.1f} seed={item['seed']} pose={item['score']['pose']['pose_score']:.3f} id={item['score']['identity']['identity_descriptor_score']:.3f}")
    overlay_contact = None
    if overlays:
        sheet = _contact_sheet_with_labels(overlays, labels, repo_root / "tmp" / "pose-control-v052" / "refcontrol-overlays" / "contact.png", 3)
        shutil.copy2(sheet["path"], repo_root / "docs/evidence/refcontrol-pose-overlay-contact.png")
        overlay_contact = "docs/evidence/refcontrol-pose-overlay-contact.png"
    paths = [Path(item["normalized_output"]) for item in records if item.get("normalized_output")]
    labels_strength = [f"strength={item['strength']:.1f} seed={item['seed']} pose={item['score']['pose']['pose_score']:.3f}" for item in records if item.get("normalized_output")]
    strength_contact = None
    if paths:
        sheet = _contact_sheet_with_labels(paths, labels_strength, repo_root / "tmp" / "pose-control-v052" / "refcontrol-strength-contact.png", 3)
        shutil.copy2(sheet["path"], repo_root / "docs/evidence/refcontrol-strength-benchmark-contact-sheet.png")
        strength_contact = "docs/evidence/refcontrol-strength-benchmark-contact-sheet.png"
    execution = {
        "schema_version": "0.5.2",
        "status": status,
        "records": execution_records,
        "record_count": len(execution_records),
        "fresh_binding_required": True,
        "all_prompt_ids_present": len(execution_records) == 9 and all(bool(item.get("image_edit", {}).get("prompt_id")) for item in execution_records),
        "all_history_bindings_exact": len(execution_records) == 9 and all(item.get("image_edit", {}).get("history_key_matches_prompt_id") is True for item in execution_records),
        "stale_output_rejected": len(execution_records) == 9 and all(item.get("image_edit", {}).get("target_existed_before_submission") is False for item in execution_records),
        "previous_frame_chaining": False,
        "native_benchmark": native_execution,
        "native_benchmark_evidence": "docs/evidence/native-reference-order-qualification.json",
        "refcontrol_benchmark_evidence": "docs/evidence/refcontrol-pose-qualification.json",
    }
    write_json(repo_root / "docs/evidence/execution-evidence-v0.5.2.json", execution)
    evidence = {"schema_version": "0.5.2", "status": status, "stop_reason": stop_reason, "native_gap": native.get("status"), "model": model, "native_loader": loader, "contract": {"base_model": QUALITY_MODEL, "reference_order": ["openpose-coco18-pose-guide", "identity-anchor"], "prompt_core": REFCONTROL_PROMPT_CORE, "strengths": list(REFCONTROL_STRENGTHS), "triage_seeds": list(REFCONTROL_TRIAGE_SEEDS), "confirmation_seed": REFCONTROL_CONFIRMATION_SEED, "renderer_version": OPENPOSE_GUIDE_RENDERER_VERSION}, "baseline_A_pose_mean": baseline_mean, "triage": triage_summaries, "confirmation_strength": winner["strength"], "records": records, "strength_contact_sheet": strength_contact, "pose_overlay_contact": overlay_contact, "execution_evidence": "docs/evidence/execution-evidence-v0.5.2.json", "human_visual_review": "required", "production_approval": "not-granted"}
    write_json(repo_root / "docs/evidence/refcontrol-pose-qualification.json", evidence)
    return evidence
