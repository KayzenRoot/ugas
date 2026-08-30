"""Native multi-reference, directional-anchor and walk pilot orchestration."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any

from .comfyui_client import ComfyUIClient
from .constants import UGAS_VERSION
from .generation import QUALITY_EDIT, QUALITY_MODEL, _model_names, _run_job, _unique_job_dir, background_remove
from .identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256, build_identity_manifest, validate_identity_manifest, write_identity_manifest
from .image_utils import compose_sheet, inspect_png, sha256
from .master_assets import candidate_metrics, checkerboard_preview, write_json
from .pose_guides import BASELINE_Y, CENTERLINE_X, WALK_NAMES, ensure_pose_guides, render_pose_guides, validate_pose_guide
from .workflow_registry import bind_workflow, load_workflow, validate_api_workflow, workflow_hash
from .model_registry import load_model

UPSTREAM_REPO = "Comfy-Org/workflow_templates"
UPSTREAM_PATH = "templates/image_flux2_klein_image_edit_4b_base.json"
UPSTREAM_COMMIT = "04f33569dad7a1d277429bda9f35209dfa4d91cf"
UPSTREAM_URL = "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/refs/heads/main/templates/image_flux2_klein_image_edit_4b_base.json"
UPSTREAM_SHA256 = "346cd9a63bfe34a5a9207f50c34a87feaf4e70806d13c9d2738fd521133670d0"


class MultiViewError(RuntimeError):
    pass


def _json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, destination); return str(destination)


def _anchor(repo_root: Path) -> Path:
    path = repo_root / "docs/evidence/reference-edit-selected-transparent.png"
    if not path.is_file() or sha256(path) != ANCHOR_SHA256: raise MultiViewError("approved R4 anchor is missing or hash-invalid")
    return path


def _record_upstream(repo_root: Path, client: ComfyUIClient) -> dict[str, Any]:
    root = repo_root / "docs/evidence/upstream"; root.mkdir(parents=True, exist_ok=True)
    source = root / "workflow_templates-image-edit-base.json"
    try:
        raw = urllib.request.urlopen(UPSTREAM_URL, timeout=20).read()
        if hashlib.sha256(raw).hexdigest() != UPSTREAM_SHA256: raise MultiViewError("official upstream template SHA changed during qualification")
        source.write_bytes(raw)
    except Exception:
        if not source.is_file() or sha256(source) != UPSTREAM_SHA256: raise
    node = client.node_info("ReferenceLatent")
    node_path = root / "comfyui-object-info-reference-latent.json"; write_json(node_path, node)
    node_sha = sha256(node_path)
    info = {"schema_version": UGAS_VERSION, "repository": UPSTREAM_REPO, "path": UPSTREAM_PATH, "commit": UPSTREAM_COMMIT, "url": UPSTREAM_URL, "source_sha256": UPSTREAM_SHA256, "materialized_path": str(source.relative_to(repo_root)).replace("\\", "/"), "comfyui_version": client.health().get("system", {}).get("comfyui_version"), "reference_latent_object_info_path": str(node_path.relative_to(repo_root)).replace("\\", "/"), "reference_latent_object_info_sha256": node_sha, "reference_latent_present": bool(node), "native_multi_reference_description": ((node.get("ReferenceLatent") or {}).get("description") if isinstance(node, dict) else None), "custom_nodes_required": [], "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    write_json(root / "flux2-klein-multireference-upstream.json", info)
    return info


def _guide_image(repo_root: Path, view: str) -> tuple[dict[str, Any], Path]:
    guide_path = repo_root / "pose-guides/views" / f"{view}.json"
    guide = json.loads(guide_path.read_text(encoding="utf-8")); rendered = render_pose_guides(repo_root, "views")
    image = next(Path(item["path"]) for item in rendered["guides"] if Path(item["path"]).stem == view)
    return guide, image


def _score_output(path: Path, guide: dict[str, Any], anchor: Path) -> dict[str, Any]:
    from PIL import Image, ImageChops, ImageStat
    info = inspect_png(path); metrics = candidate_metrics(path, width=512, height=512, requires_transparency=False, margins={"left": 20, "top": 20, "right": 20, "bottom": 20}, occupancy_target={"min": 0.01, "max": 0.92})
    with Image.open(path) as output_opened, Image.open(anchor) as anchor_opened:
        output = output_opened.convert("RGB"); reference = anchor_opened.convert("RGB").resize(output.size)
        mae = sum(ImageStat.Stat(ImageChops.difference(output, reference)).mean) / 3 / 255
    bbox = metrics.get("foreground_bbox") or [0, 0, 512, 512]
    guide_points = guide.get("keypoints", {})
    guide_box = [min(point[0] for point in guide_points.values()), min(point[1] for point in guide_points.values()), max(point[0] for point in guide_points.values()), max(point[1] for point in guide_points.values())] if guide_points else [0, 0, 512, 512]
    output_ratio = (bbox[2] - bbox[0]) / max(1, bbox[3] - bbox[1]); guide_ratio = (guide_box[2] - guide_box[0]) / max(1, guide_box[3] - guide_box[1])
    pose_adherence = max(0.0, 1.0 - min(1.0, abs(output_ratio - guide_ratio) / max(0.01, guide_ratio)))
    return {"path": str(path), "sha256": sha256(path), "png": info, "structural": metrics, "identity_mae_normalized": round(mae, 6), "identity_score": round(max(0.0, 1.0 - mae), 6), "pose_adherence_heuristic": round(pose_adherence, 6), "human_visual_review": "required"}


def _run_reference(repo_root: Path, client: ComfyUIClient, *, workflow_id: str, anchor: Path, guide: Path | None, prompt: str, seed: int, output_root: Path, stage: str) -> dict[str, Any]:
    model = load_model(repo_root, QUALITY_MODEL); record = load_workflow(repo_root, workflow_id)
    uploads = [client.upload_image(anchor)] + ([client.upload_image(guide)] if guide else [])
    filenames = [item.get("name") or item.get("filename") for item in uploads]
    if not all(isinstance(item, str) and item for item in filenames): raise MultiViewError("ComfyUI upload did not return exact filenames")
    workflow = bind_workflow(record["api"], prompt=prompt, seed=seed, width=512, height=512, model_names=_model_names(model), image_filenames=[str(item) for item in filenames])
    graph = validate_api_workflow(workflow, node_info=client.node_info())
    if not graph["live_valid"]: raise MultiViewError(f"workflow native node validation failed: {graph['missing_nodes']}")
    job_dir = _unique_job_dir(repo_root, output_root, stage)
    result, outputs = _run_job(repo_root, client, workflow, output_dir=job_dir, filename=f"{stage}.png", profile="generic-2d", capability="multi-reference-edit", workflow_id=workflow_id, model_id=QUALITY_MODEL, prompt=prompt, seed=seed, width=512, height=512, input_hashes={"reference_0_identity_anchor_sha256": sha256(anchor), "reference_1_pose_view_guide_sha256": sha256(guide) if guide else None}, qualification_context={"stage": stage, "reference_order": ["identity/style/material/character", "pose/view/guide"] if guide else ["identity/style/material/character"], "source_anchor_revision_id": ANCHOR_REVISION_ID, "source_anchor_sha256": ANCHOR_SHA256, "guide_sha256": sha256(guide) if guide else None, "previous_frame_chaining": False}, workflow_sha256=workflow_hash(workflow))
    output = Path(outputs[0]["path"]); return {"stage": stage, "seed": seed, "workflow_id": workflow_id, "workflow_sha256": workflow_hash(workflow), "model_id": QUALITY_MODEL, "output": str(output), "output_sha256": sha256(output), "execution_evidence": result["job"].get("execution_evidence", {}), "reference_filenames": filenames, "input_hashes": {"reference_0": sha256(anchor), "reference_1": sha256(guide) if guide else None}, "fresh_binding": result["job"].get("execution_evidence", {}).get("fresh_binding", False)}


def qualify_multiref(repo_root: Path, *, endpoint: str = "http://127.0.0.1:8188", asset_id: str = ANCHOR_ASSET_ID, seed_base: int = 50501) -> dict[str, Any]:
    identity = write_identity_manifest(repo_root, asset_id=asset_id); guides = ensure_pose_guides(repo_root); guide, guide_image = _guide_image(repo_root, "left"); anchor = _anchor(repo_root); client = ComfyUIClient(endpoint, timeout=40.0)
    upstream = _record_upstream(repo_root, client); prompt = "Single full-body game character. Reference[0] is the canonical identity anchor and controls identity, style, materials, palette, armor, cloth, head, sword and proportions. Reference[1] is a deterministic pose/view guide only and controls the left-facing view and pose. Apply the guide geometry without copying its diagram, text, or background. Keep the transparent-ready character centered, full body, no extra limbs, no redesign, no text, no watermark."
    records: list[dict[str, Any]] = []; contact_paths: list[Path] = []
    for mode, workflow_id, guide_arg in (("A-canonical-only", QUALITY_EDIT, None), ("B-canonical-plus-guide", "flux2-klein-base-4b-quality-multi-reference-edit", guide_image)):
        for offset in range(2):
            seed = seed_base + offset
            try:
                record = _run_reference(repo_root, client, workflow_id=workflow_id, anchor=anchor, guide=guide_arg, prompt=prompt, seed=seed, output_root=repo_root / "tmp/multiview/ab" / mode, stage=f"multiref-{mode.lower().replace('-', '_')}-{offset}")
                scored = _score_output(Path(record["output"]), guide, anchor); records.append({"mode": mode, **record, "score": scored}); contact_paths.append(Path(record["output"]))
            except Exception as exc:
                records.append({"mode": mode, "seed": seed, "workflow_id": workflow_id, "eligible": False, "error": f"{type(exc).__name__}: {exc}"})
    contact = None
    if contact_paths:
        contact = compose_sheet(contact_paths, repo_root / "tmp/multiview/ab/contact-sheet.png", 2); _copy(Path(contact["path"]), repo_root / "docs/evidence/multiref-ab-contact-sheet.png")
    a = [item["score"] for item in records if item.get("mode") == "A-canonical-only" and item.get("score")]
    b = [item["score"] for item in records if item.get("mode") == "B-canonical-plus-guide" and item.get("score")]
    a_pose = sum(item["pose_adherence_heuristic"] for item in a) / len(a) if a else 0.0; b_pose = sum(item["pose_adherence_heuristic"] for item in b) / len(b) if b else 0.0
    b_identity = min((item["identity_score"] for item in b), default=0.0); b_margin = all(item["structural"].get("safe_margin_ok", False) for item in b)
    qualification = b and a and b_margin and b_identity >= 0.35 and (b_pose >= a_pose + 0.02 or b_pose >= 0.72)
    status = "MULTI_REFERENCE_QUALIFIED" if qualification else "MULTI_REFERENCE_QUALITY_GAP"
    evidence = {"schema_version": UGAS_VERSION, "status": status, "capability": "multi-reference-edit", "asset_id": asset_id, "canonical_anchor": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "conditioning_contract": {"reference[0]": "canonical identity/style/material/character anchor", "reference[1]": "deterministic pose/view guide", "previous_frame_chaining": False, "independent_text_to_image_frames": False}, "upstream": upstream, "workflow_id": "flux2-klein-base-4b-quality-multi-reference-edit", "native_reference_latent_count": 4, "same_transformation_model_and_seed_pairs": True, "guide": {"path": "pose-guides/views/left.json", "sha256": _json_hash(guide), "rendered_path": str(guide_image)}, "records": records, "comparison": {"A_pose_adherence_mean": round(a_pose, 6), "B_pose_adherence_mean": round(b_pose, 6), "B_identity_min": round(b_identity, 6), "B_safe_margin": b_margin, "meaningful_B_pose_gain": bool(b_pose >= a_pose + 0.02), "qualification_rule": "B must improve pose adherence materially or be strongly adherent while preserving identity and margins", "heuristic_requires_human_visual_review": True}, "contact_sheet": "docs/evidence/multiref-ab-contact-sheet.png" if contact else None, "stop_reason": None if qualification else "MULTI_REFERENCE_QUALITY_GAP"}
    write_json(repo_root / "docs/evidence/multiref-qualification.json", evidence); write_json(repo_root / "docs/evidence/pose-guide-manifest.json", {**guides, "render": render_pose_guides(repo_root, "walk-front-8")})
    return {"status": status, "asset_id": asset_id, "identity": identity, "pose_guides": guides, "qualification": str(repo_root / "docs/evidence/multiref-qualification.json"), "records": records, "comparison": evidence["comparison"]}


def normalize_frame(source: Path, destination: Path, *, frame_name: str, guide: dict[str, Any]) -> dict[str, Any]:
    from PIL import Image
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        if image.size != (512, 512): raise MultiViewError("frame normalization requires 512x512 source")
        bbox = image.getchannel("A").getbbox()
        if not bbox: raise MultiViewError("frame has no alpha foreground")
        left, top, right, bottom = bbox; dx = CENTERLINE_X - ((left + right) / 2); dy = BASELINE_Y - bottom
        if left + dx < 8 or right + dx > 504 or top + dy < 8 or bottom + dy > 504: raise MultiViewError("frame cannot be normalized within safe margins")
        canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0)); canvas.alpha_composite(image, (round(dx), round(dy))); destination.parent.mkdir(parents=True, exist_ok=True); canvas.save(destination, format="PNG", optimize=False)
    return {"frame_name": frame_name, "path": str(destination), "sha256": sha256(destination), "alpha_bbox_before": [left, top, right, bottom], "translation": {"x": round(dx, 3), "y": round(dy, 3)}, "scale": 1.0, "pivot_policy": "centerline x 256, ground baseline y 478", "ground_baseline": BASELINE_Y, "guide_sha256": _json_hash(guide), "normalization_status": "TRANSLATED_NO_STRETCH"}


def _transparent_candidate(repo_root: Path, client: ComfyUIClient, generated: Path, root: Path, label: str, guide: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    transparent = background_remove(repo_root, str(generated), endpoint=client.base_url, output_dir=root / "birefnet", promote=False)
    normalized = root / "normalized.png"; metrics = normalize_frame(Path(transparent["output"]), normalized, frame_name=label, guide=guide); qa = candidate_metrics(normalized, width=512, height=512, requires_transparency=True, margins={"left": 8, "top": 8, "right": 8, "bottom": 8}, occupancy_target={"min": 0.01, "max": 0.92})
    metrics["transparency"] = transparent; metrics["qa"] = qa; return normalized, metrics


def generate_directional_anchors(repo_root: Path, asset_id: str = ANCHOR_ASSET_ID, *, endpoint: str = "http://127.0.0.1:8188", directions: list[str] | None = None, seed_base: int = 50601) -> dict[str, Any]:
    qualification = json.loads((repo_root / "docs/evidence/multiref-qualification.json").read_text(encoding="utf-8"))
    if qualification.get("status") != "MULTI_REFERENCE_QUALIFIED": return {"status": "BLOCKED", "stop_reason": "MULTI_REFERENCE_QUALITY_GAP"}
    anchor = _anchor(repo_root); client = ComfyUIClient(endpoint, timeout=40.0); selected: dict[str, Any] = {}; candidates: list[dict[str, Any]] = []; requested = directions or ["front", "left", "right", "back"]
    front = repo_root / "docs/evidence/anchor-front.png"; _copy(anchor, front); selected["front"] = {"path": str(front), "sha256": sha256(front), "source": "exact-v0.4.3-R4-no-regeneration", "guide": "pose-guides/views/front.json"}
    prompt_base = "Use reference[0] as the exact canonical character identity/style/material anchor. Use reference[1] only as the deterministic view guide. Produce a single full-body game sprite for the requested view, preserving face, armor, black cloth, sword, palette and proportions. No diagram, no text, no watermark, no extra limbs, no crop."
    for index, direction in enumerate(item for item in requested if item != "front"):
        guide, guide_image = _guide_image(repo_root, direction); eligible: list[dict[str, Any]] = []
        for candidate in range(2):
            seed = seed_base + index * 10 + candidate; record: dict[str, Any] = {"direction": direction, "candidate": candidate + 1, "seed": seed, "guide": str(repo_root / "pose-guides/views" / f"{direction}.json"), "guide_sha256": _json_hash(guide), "eligible": False}
            try:
                generated = _run_reference(repo_root, client, workflow_id="flux2-klein-base-4b-quality-multi-reference-edit", anchor=anchor, guide=guide_image, prompt=prompt_base + f" Requested view: {direction}.", seed=seed, output_root=repo_root / "tmp/multiview/anchors" / direction, stage=f"anchor-{direction}-{candidate}")
                normalized, metrics = _transparent_candidate(repo_root, client, Path(generated["output"]), repo_root / "tmp/multiview/anchors" / direction / f"candidate-{candidate}", f"anchor-{direction}", guide); record.update(generated, normalized_path=str(normalized), normalized_sha256=sha256(normalized), metrics=metrics, eligible=bool(metrics["qa"].get("eligible")), rejection_reasons=metrics["qa"].get("hard_gate_failures", []));
                if record["eligible"]: eligible.append(record)
            except Exception as exc: record.update({"error": f"{type(exc).__name__}: {exc}", "rejection_reasons": ["generation_or_transparency_failed"]})
            candidates.append(record)
        if not eligible: write_json(repo_root / "docs/evidence/directional-anchor-set.json", {"schema_version": UGAS_VERSION, "status": "NO_ACCEPTABLE_DIRECTIONAL_ANCHOR", "asset_id": asset_id, "selected": selected, "candidates": candidates, "stop_reason": "NO_ACCEPTABLE_DIRECTIONAL_ANCHOR"}); write_json(repo_root / "docs/evidence/directional-anchor-qa.json", {"schema_version": UGAS_VERSION, "status": "NO_ACCEPTABLE_DIRECTIONAL_ANCHOR", "candidates": candidates}); return {"status": "NO_ACCEPTABLE_DIRECTIONAL_ANCHOR", "direction": direction, "candidates": candidates}
        eligible.sort(key=lambda item: (len(item.get("rejection_reasons", [])), item["seed"])); best = eligible[0]; target = repo_root / "docs/evidence" / f"anchor-{direction}.png"; _copy(Path(best["normalized_path"]), target); selected[direction] = {"path": str(target), "sha256": sha256(target), "candidate": best["seed"], "guide": best["guide"], "guide_sha256": best["guide_sha256"], "source_anchor_sha256": ANCHOR_SHA256}
    paths = [Path(selected[direction]["path"]) for direction in ("front", "left", "right", "back") if direction in selected]; sheet = compose_sheet(paths, repo_root / "tmp/multiview/anchors/contact-sheet.png", 4); _copy(Path(sheet["path"]), repo_root / "docs/evidence/directional-anchors-contact-sheet.png")
    result = {"schema_version": UGAS_VERSION, "status": "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED", "asset_id": asset_id, "anchor_set": selected, "directions": requested, "candidate_count_per_generated_direction": 2, "candidates": candidates, "contact_sheet": "docs/evidence/directional-anchors-contact-sheet.png", "human_visual_review": "required", "production_approval": "not-granted"}; write_json(repo_root / "docs/evidence/directional-anchor-set.json", result); write_json(repo_root / "docs/evidence/directional-anchor-qa.json", {"schema_version": UGAS_VERSION, "status": result["status"], "directions": {direction: {"status": "TECHNICAL_GATE_PASSED", "visual_review": "required"} for direction in requested}, "candidates": candidates}); return result


def _temporal_qa(frames: list[Path], guides: list[dict[str, Any]]) -> dict[str, Any]:
    from PIL import Image, ImageChops, ImageStat
    hashes = [sha256(path) for path in frames]; unique = len(set(hashes)) == len(hashes); differences = []
    bboxes = []
    for path in frames:
        with Image.open(path) as opened: bboxes.append(opened.convert("RGBA").getchannel("A").getbbox())
    for left, right in zip(frames, frames[1:] + frames[:1]):
        with Image.open(left) as a, Image.open(right) as b: differences.append(round(sum(ImageStat.Stat(ImageChops.difference(a.convert("RGB"), b.convert("RGB"))).mean) / 3 / 255, 6))
    heights = [box[3] - box[1] for box in bboxes if box]; pivots = [((box[0] + box[2]) / 2, box[3]) for box in bboxes if box]
    return {"frame_count": len(frames), "unique_sha256": unique, "hashes": hashes, "adjacent_frame_difference": differences, "adjacent_difference_lower_bound": 0.002, "adjacent_difference_upper_bound": 0.85, "adjacent_differences_ok": all(0.002 <= value <= 0.85 for value in differences), "height_variance": round((max(heights) - min(heights)) / max(1, sum(heights) / len(heights)), 6) if heights else 1.0, "height_variance_max": 0.12, "pivot_jitter": round(max(math.dist(pivots[0], item) for item in pivots) if pivots else 999, 6), "pivot_jitter_max": 8.0, "guides": [_json_hash(guide) for guide in guides], "no_previous_frame_chaining": True, "loop_compatible": bool(differences and differences[-1] <= 0.85), "outlier": None, "status": "TEMPORAL_QA_PASSED" if len(frames) == 8 and unique and all(0.002 <= value <= 0.85 for value in differences) and (max(heights) - min(heights)) / max(1, sum(heights) / len(heights)) <= 0.12 and (max(math.dist(pivots[0], item) for item in pivots) if pivots else 999) <= 8 else "TEMPORAL_QA_FAILED"}


def frame_diff_contact(frames: list[Path], destination: Path) -> dict[str, Any]:
    from PIL import Image, ImageChops, ImageEnhance
    if len(frames) < 2: raise MultiViewError("at least two frames are required for a diff contact sheet")
    diffs = []
    for left, right in zip(frames, frames[1:] + frames[:1]):
        with Image.open(left) as a, Image.open(right) as b:
            diff = ImageEnhance.Contrast(ImageChops.difference(a.convert("RGBA"), b.convert("RGBA"))).enhance(3.0)
            diffs.append(diff)
    destination.parent.mkdir(parents=True, exist_ok=True); sheet = Image.new("RGBA", (512 * 4, 512 * 2), (0, 0, 0, 255))
    for index, diff in enumerate(diffs): sheet.alpha_composite(diff, ((index % 4) * 512, (index // 4) * 512))
    sheet.save(destination, format="PNG", optimize=False)
    return {"path": str(destination), "sha256": sha256(destination), "frame_count": len(frames), "comparison": "adjacent cyclic RGBA absolute differences, contrast x3", "visual_review": "required"}


def generate_walk_pilot(repo_root: Path, asset_id: str = ANCHOR_ASSET_ID, *, endpoint: str = "http://127.0.0.1:8188", frames: int = 8, seed_base: int = 50701) -> dict[str, Any]:
    if frames != 8: return {"status": "BLOCKED", "stop_reason": "walk-front-8 requires exactly 8 frames"}
    anchors_path = repo_root / "docs/evidence/directional-anchor-set.json"
    anchors = json.loads(anchors_path.read_text(encoding="utf-8")) if anchors_path.is_file() else {}
    if anchors.get("status") != "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED": return {"status": "BLOCKED", "stop_reason": "DIRECTIONAL_ANCHOR_QUALITY_GAP"}
    anchor = _anchor(repo_root); client = ComfyUIClient(endpoint, timeout=40.0); frame_records: list[dict[str, Any]] = []; selected_paths: list[Path] = []; selected_guides: list[dict[str, Any]] = []
    for index, frame_name in enumerate(WALK_NAMES):
        guide_path = repo_root / "pose-guides/walk-front-8" / f"{frame_name}.json"; guide = json.loads(guide_path.read_text(encoding="utf-8")); guide_image = render_pose_guides(repo_root, "walk-front-8")["guides"][index]["path"]; chosen = None; attempts = []
        for attempt in range(2):
            seed = seed_base + index * 10 + attempt
            try:
                normalized, metrics = _transparent_candidate(repo_root, client, Path(generated["output"]), repo_root / "tmp/multiview/walk-front-8" / frame_name / f"candidate-{attempt}", frame_name, guide); attempt_record = {"frame_name": frame_name, "attempt": attempt + 1, "seed": seed, **generated, "path": str(normalized), "sha256": sha256(normalized), "normalized_path": str(normalized), "normalized_sha256": sha256(normalized), "alpha_bbox_before": metrics["alpha_bbox_before"], "translation": metrics["translation"], "scale": metrics["scale"], "pivot_policy": metrics["pivot_policy"], "ground_baseline": metrics["ground_baseline"], "guide_sha256": metrics["guide_sha256"], "normalization_status": metrics["normalization_status"], "metrics": metrics, "eligible": bool(metrics["qa"].get("eligible")), "previous_frame_input": None}; attempts.append(attempt_record)
                if attempt_record["eligible"]: chosen = attempt_record; break
            except Exception as exc: attempts.append({"frame_name": frame_name, "attempt": attempt + 1, "seed": seed, "eligible": False, "error": f"{type(exc).__name__}: {exc}", "previous_frame_input": None})
        if chosen is None:
            evidence = {"schema_version": UGAS_VERSION, "status": "NO_ACCEPTABLE_FRAME", "animation": "walk", "view": "front", "frame_count": 8, "failed_frame": frame_name, "frames": frame_records, "failed_attempts": attempts, "stop_reason": "NO_ACCEPTABLE_FRAME", "partial_cycle_not_accepted": True}; write_json(repo_root / "docs/evidence/walk-front-8-animation-qa.json", evidence); write_json(repo_root / "docs/evidence/walk-front-8.json", evidence); return {"status": "NO_ACCEPTABLE_FRAME", "failed_frame": frame_name, "evidence": str(repo_root / "docs/evidence/walk-front-8-animation-qa.json")}
        frame_records.append({"frame_name": frame_name, "selected": chosen, "attempts": attempts}); selected_paths.append(Path(chosen["normalized_path"])); selected_guides.append(guide)
    temporal = _temporal_qa(selected_paths, selected_guides)
    qa = {"schema_version": UGAS_VERSION, "status": "WALK_CYCLE_VISUAL_REVIEW_REQUIRED" if temporal["status"] == "TEMPORAL_QA_PASSED" else "NO_ACCEPTABLE_FRAME", "animation": "walk", "view": "front", "frames": frame_records, "temporal": temporal, "human_visual_review": "required"}
    write_json(repo_root / "docs/evidence/walk-front-8-animation-qa.json", qa)
    if temporal["status"] != "TEMPORAL_QA_PASSED": write_json(repo_root / "docs/evidence/walk-front-8.json", qa); return {"status": "NO_ACCEPTABLE_FRAME", "qa": qa}
    sheet_root = repo_root / "docs/evidence"; sheet = compose_sheet(selected_paths, sheet_root / "walk-front-8-spritesheet.png", 8); contact = compose_sheet(selected_paths, sheet_root / "walk-front-8-contact-sheet.png", 4)
    from PIL import Image
    with Image.open(selected_paths[0]) as first:
        frames_rgba = [Image.open(path).convert("RGBA") for path in selected_paths]
        frames_rgba[0].save(sheet_root / "walk-front-8-preview.gif", save_all=True, append_images=frames_rgba[1:], duration=125, loop=0, disposal=2)
    metadata = {"schema_version": UGAS_VERSION, "animation": "walk", "view": "front", "frames": 8, "fps": 8, "loop": True, "frame_width": 512, "frame_height": 512, "pivot_policy": "centerline x 256, ground baseline y 478", "frame_files": [str(path.relative_to(repo_root)).replace("\\", "/") for path in selected_paths], "frame_hashes": [sha256(path) for path in selected_paths], "spritesheet": str((sheet_root / "walk-front-8-spritesheet.png").relative_to(repo_root)).replace("\\", "/"), "preview_gif": str((sheet_root / "walk-front-8-preview.gif").relative_to(repo_root)).replace("\\", "/"), "contact_sheet": str((sheet_root / "walk-front-8-contact-sheet.png").relative_to(repo_root)).replace("\\", "/"), "temporal_qa": temporal["status"], "visual_review": "required"}
    diff = frame_diff_contact(selected_paths, sheet_root / "walk-frame-diff-contact.png"); metadata["frame_diff_contact"] = str((sheet_root / "walk-frame-diff-contact.png").relative_to(repo_root)).replace("\\", "/"); write_json(sheet_root / "walk-front-8.json", metadata); write_json(sheet_root / "walk-front-8-animation-spec.json", metadata); qa["outputs"] = metadata; qa["frame_diff_contact"] = diff; write_json(sheet_root / "walk-front-8-animation-qa.json", qa); return {"status": "WALK_CYCLE_VISUAL_REVIEW_REQUIRED", "metadata": str(sheet_root / "walk-front-8.json"), "qa": qa, "spritesheet": str(sheet_root / "walk-front-8-spritesheet.png"), "preview": str(sheet_root / "walk-front-8-preview.gif")}


def identity_inspect(repo_root: Path, asset_id: str = ANCHOR_ASSET_ID) -> dict[str, Any]:
    manifest = build_identity_manifest(repo_root, asset_id); return {"status": validate_identity_manifest(manifest, repo_root)["status"], "manifest": manifest}
