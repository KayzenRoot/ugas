"""Native multi-reference, pose fidelity and reproducible walk pilot orchestration."""

from __future__ import annotations

import colorsys
import hashlib
import json
import math
import shutil
import time
import urllib.request
from collections import deque
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .capabilities import probe_comfy_capability
from .comfyui_client import ComfyUIClient
from .constants import UGAS_VERSION
from .generation import QUALITY_EDIT, QUALITY_MODEL, _model_names, _run_job, _unique_job_dir, background_remove
from .identity import ANCHOR_ASSET_ID, ANCHOR_REVISION_ID, ANCHOR_SHA256, build_identity_manifest, validate_identity_manifest, write_identity_manifest
from .image_utils import compose_sheet, inspect_png, sha256
from .master_assets import candidate_metrics, checkerboard_preview, write_json
from .model_registry import load_model
from .pose_guides import BASELINE_Y, CANVAS, CENTERLINE_X, CHALLENGE_NAME, POSE_GUIDE_RENDERER_VERSION, WALK_NAMES, challenge_guide, ensure_pose_guides, guide_hash, render_challenge_guide, render_pose_guide, render_pose_guides, validate_pose_guide
from .workflow_registry import bind_workflow, load_workflow, validate_api_workflow, workflow_hash

UPSTREAM_REPO = "Comfy-Org/workflow_templates"
UPSTREAM_PATH = "templates/image_flux2_klein_image_edit_4b_base.json"
UPSTREAM_COMMIT = "04f33569dad7a1d277429bda9f35209dfa4d91cf"
UPSTREAM_URL = "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/refs/heads/main/templates/image_flux2_klein_image_edit_4b_base.json"
UPSTREAM_SHA256 = "346cd9a63bfe34a5a9207f50c34a87feaf4e70806d13c9d2738fd521133670d0"

POSE_METRICS_VERSION = "2.0.0"
IDENTITY_METRICS_VERSION = "2.0.0"
AB_SEEDS = 3
AB_POSE_THRESHOLD = 0.70
AB_POSE_FLOOR = 0.60
AB_POSE_GAIN = 0.15
FRAME_POSE_THRESHOLD = 0.62
IDENTITY_THRESHOLD = 0.58
HEIGHT_VARIANCE_MAX = 0.05
ROOT_DRIFT_MAX = 12.0
LOOP_CLOSURE_FACTOR_MAX = 3.0

POSE_SEGMENTS = (
    ("shoulder_left", "elbow_left"), ("elbow_left", "hand_left"),
    ("shoulder_right", "elbow_right"), ("elbow_right", "hand_right"),
    ("pelvis", "knee_left"), ("knee_left", "foot_left"),
    ("pelvis", "knee_right"), ("knee_right", "foot_right"),
    ("weapon_grip", "weapon_tip"),
)
LOWER_BODY_SEGMENTS = {("pelvis", "knee_left"), ("knee_left", "foot_left"), ("pelvis", "knee_right"), ("knee_right", "foot_right")}


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
    root = repo_root / "docs/evidence/upstream"; root.mkdir(parents=True, exist_ok=True); source = root / "workflow_templates-image-edit-base.json"
    try:
        raw = urllib.request.urlopen(UPSTREAM_URL, timeout=20).read()
        if hashlib.sha256(raw).hexdigest() != UPSTREAM_SHA256: raise MultiViewError("official upstream template SHA changed during qualification")
        source.write_bytes(raw)
    except Exception:
        if not source.is_file() or sha256(source) != UPSTREAM_SHA256: raise
    node = client.node_info("ReferenceLatent"); node_path = root / "comfyui-object-info-reference-latent.json"; write_json(node_path, node)
    info = {"schema_version": UGAS_VERSION, "repository": UPSTREAM_REPO, "path": UPSTREAM_PATH, "commit": UPSTREAM_COMMIT, "url": UPSTREAM_URL, "source_sha256": UPSTREAM_SHA256, "materialized_path": str(source.relative_to(repo_root)).replace("\\", "/"), "comfyui_version": client.health().get("system", {}).get("comfyui_version"), "reference_latent_object_info_path": str(node_path.relative_to(repo_root)).replace("\\", "/"), "reference_latent_object_info_sha256": sha256(node_path), "reference_latent_present": bool(node), "native_multi_reference_description": ((node.get("ReferenceLatent") or {}).get("description") if isinstance(node, dict) else None), "custom_nodes_required": [], "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    write_json(root / "flux2-klein-multireference-upstream.json", info); return info


def _guide_image(repo_root: Path, relative: str) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    guide_path = repo_root / relative; guide = json.loads(guide_path.read_text(encoding="utf-8")); kind = "walk-front-8" if guide.get("guide_type") == "walk" else "views"
    rendered = render_pose_guides(repo_root, kind); item = next(item for item in rendered["guides"] if item["control"]["guide_id"] == guide["guide_id"])
    return guide, Path(item["control"]["path"]), item["control"]


def _mask_points(path: Path, size: int = 128, threshold: int = 32) -> set[tuple[int, int]]:
    from PIL import Image
    with Image.open(path) as source:
        image = source.convert("RGBA"); alpha = image.getchannel("A").resize((size, size), Image.Resampling.BILINEAR)
        return {(x, y) for y in range(size) for x in range(size) if alpha.getpixel((x, y)) >= threshold}


def _guide_mask(guide: dict[str, Any], size: int = 128) -> set[tuple[int, int]]:
    from PIL import Image, ImageDraw
    image = Image.new("L", (size, size), 0); draw = ImageDraw.Draw(image); points = guide["keypoints"]; scale = size / CANVAS
    def p(name: str) -> tuple[float, float]: return points[name][0] * scale, points[name][1] * scale
    profile = guide.get("view") in {"left", "right"} or guide.get("guide_type") == "qualification-challenge"
    hx, hy = p("head"); rx, ry = ((18, 23) if profile else (24, 24)); draw.ellipse((hx - rx * scale, hy - ry * scale, hx + rx * scale, hy + ry * scale), fill=255)
    draw.line((*p("neck"), *p("pelvis")), fill=255, width=max(1, round(34 * scale)))
    shoulder_l, shoulder_r, pelvis = p("shoulder_left"), p("shoulder_right"), p("pelvis"); torso_width = 26 if profile else 42
    draw.polygon([(shoulder_l[0] - torso_width * scale, shoulder_l[1]), (shoulder_r[0] + torso_width * scale, shoulder_r[1]), (pelvis[0] + 25 * scale, pelvis[1] + 30 * scale), (pelvis[0] - 25 * scale, pelvis[1] + 30 * scale)], fill=255)
    width = max(1, round((15 if profile else 18) * scale))
    for left, right in POSE_SEGMENTS[:-1]: draw.line((*p(left), *p(right)), fill=255, width=width)
    draw.line((*p("weapon_grip"), *p("weapon_tip")), fill=255, width=max(1, round(8 * scale)))
    for name in ("shoulder_left", "shoulder_right", "elbow_left", "elbow_right", "hand_left", "hand_right", "pelvis", "knee_left", "knee_right"):
        x, y = p(name); radius = max(1, round(10 * scale)); draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    return {(x, y) for y in range(size) for x in range(size) if image.getpixel((x, y)) > 0}


def _distance_map(points: set[tuple[int, int]], size: int) -> list[list[int]]:
    distances = [[size + 1 for _ in range(size)] for _ in range(size)]; queue: deque[tuple[int, int]] = deque()
    for x, y in points:
        if 0 <= x < size and 0 <= y < size and distances[y][x] != 0: distances[y][x] = 0; queue.append((x, y))
    while queue:
        x, y = queue.popleft(); next_distance = distances[y][x] + 1
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1), (x + 1, y + 1)):
            if 0 <= nx < size and 0 <= ny < size and next_distance < distances[ny][nx]: distances[ny][nx] = next_distance; queue.append((nx, ny))
    return distances


def _chamfer(left: set[tuple[int, int]], right: set[tuple[int, int]], size: int) -> float:
    if not left or not right: return 1.0
    left_dist, right_dist = _distance_map(left, size), _distance_map(right, size)
    one_way = sum(right_dist[y][x] for x, y in left) / len(left); other_way = sum(left_dist[y][x] for x, y in right) / len(right)
    return round((one_way + other_way) / 2 / size, 6)


def _pose_metrics(path: Path, guide: dict[str, Any], *, size: int = 128) -> dict[str, Any]:
    output_points = _mask_points(path, size); guide_points = _guide_mask(guide, size); distances = _distance_map(output_points, size)
    keypoint_results = {}
    for name, point in guide.get("keypoints", {}).items():
        x, y = round(point[0] * size / CANVAS), round(point[1] * size / CANVAS); radius = round(16 * size / CANVAS); keypoint_results[name] = {"hit": bool(0 <= x < size and 0 <= y < size and distances[y][x] <= radius), "distance_px": distances[y][x] if 0 <= x < size and 0 <= y < size else size + 1, "radius_px": radius}
    hits = sum(item["hit"] for item in keypoint_results.values()) / max(1, len(keypoint_results))
    segment_results = {}; lower_results = {}; guide_keypoints = guide.get("keypoints", {})
    for left, right in POSE_SEGMENTS:
        samples = []
        for index in range(13):
            ratio = index / 12; x = round((guide_keypoints[left][0] * (1 - ratio) + guide_keypoints[right][0] * ratio) * size / CANVAS); y = round((guide_keypoints[left][1] * (1 - ratio) + guide_keypoints[right][1] * ratio) * size / CANVAS); radius = round(12 * size / CANVAS); samples.append(0 <= x < size and 0 <= y < size and distances[y][x] <= radius)
        value = sum(samples) / len(samples); key = f"{left}->{right}"; segment_results[key] = round(value, 6)
        if (left, right) in LOWER_BODY_SEGMENTS: lower_results[key] = round(value, 6)
    segment_coverage = sum(segment_results.values()) / max(1, len(segment_results)); lower_coverage = sum(lower_results.values()) / max(1, len(lower_results)); chamfer = _chamfer(guide_points, output_points, size); silhouette_score = max(0.0, min(1.0, 1.0 - chamfer / 0.28))
    bbox = None
    if output_points: bbox = [min(x for x, _ in output_points), min(y for _, y in output_points), max(x for x, _ in output_points) + 1, max(y for _, y in output_points) + 1]
    guide_bbox = [min(x for x, _ in guide_points), min(y for _, y in guide_points), max(x for x, _ in guide_points) + 1, max(y for _, y in guide_points) + 1] if guide_points else None
    output_ratio = ((bbox[2] - bbox[0]) / max(1, bbox[3] - bbox[1])) if bbox else 0.0; guide_ratio = ((guide_bbox[2] - guide_bbox[0]) / max(1, guide_bbox[3] - guide_bbox[1])) if guide_bbox else 0.0
    bbox_diagnostic = max(0.0, 1.0 - min(1.0, abs(output_ratio - guide_ratio) / max(0.01, guide_ratio))) if guide_ratio else 0.0
    pose_score = round(0.45 * hits + 0.35 * segment_coverage + 0.20 * silhouette_score, 6)
    return {"metrics_version": POSE_METRICS_VERSION, "guide_keypoint_hit_rate": round(hits, 6), "keypoints": keypoint_results, "guide_segment_coverage": round(segment_coverage, 6), "segments": segment_results, "lower_body_guide_coverage": round(lower_coverage, 6), "guide_silhouette_distance": chamfer, "guide_silhouette_score": round(silhouette_score, 6), "pose_score": pose_score, "pose_threshold": FRAME_POSE_THRESHOLD, "bbox_aspect_ratio_diagnostic": round(bbox_diagnostic, 6), "output_mask_bbox_128": bbox, "guide_mask_bbox_128": guide_bbox}


def _region_stats(image: Any, bbox: tuple[int, int, int, int], alpha_min: int = 48) -> dict[str, Any]:
    pixels = []
    for y in range(max(0, bbox[1]), min(image.height, bbox[3])):
        for x in range(max(0, bbox[0]), min(image.width, bbox[2])):
            r, g, b, a = image.getpixel((x, y))
            if a >= alpha_min: pixels.append((r, g, b))
    if not pixels: return {"count": 0, "mean_rgb": [0.0, 0.0, 0.0], "mean_hsv": [0.0, 0.0, 0.0], "luma_histogram": [0.0] * 8}
    mean = [sum(item[index] for item in pixels) / len(pixels) for index in range(3)]; hsv = [colorsys.rgb_to_hsv(*(value / 255 for value in mean))]
    luma = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels]; histogram = [0.0] * 8
    for value in luma: histogram[min(7, int(value / 256 * 8))] += 1
    histogram = [value / len(pixels) for value in histogram]
    return {"count": len(pixels), "mean_rgb": [round(value, 3) for value in mean], "mean_hsv": [round(value, 6) for value in hsv[0]], "luma_histogram": [round(value, 6) for value in histogram]}


def _visual_descriptor(path: Path) -> dict[str, Any]:
    from PIL import Image
    with Image.open(path) as source:
        image = source.convert("RGBA"); alpha = image.getchannel("A"); bbox = alpha.getbbox()
        if not bbox: return {"bbox": None, "body_proportions": {}, "weapon_outer_fraction": 0.0, "weapon_present": False, "regions": {}}
        left, top, right, bottom = bbox; width, height = right - left, bottom - top
        def region(x0: float, y0: float, x1: float, y1: float) -> dict[str, Any]: return _region_stats(image, (round(left + width * x0), round(top + height * y0), round(left + width * x1), round(top + height * y1)))
        all_stats = _region_stats(image, bbox); outer = 0; metallic_outer = 0; total = 0
        for y in range(top, bottom):
            for x in range(left, right):
                if alpha.getpixel((x, y)) >= 48:
                    total += 1
                    if x < left + width * .28 or x > left + width * .72:
                        outer += 1
                        r, g, b, _ = image.getpixel((x, y)); metallic_outer += int(max(r, g, b) - min(r, g, b) < 70 and max(r, g, b) > 95)
        head = region(.2, .0, .8, .25); armor = region(.15, .20, .85, .60); cloth = region(.15, .52, .85, .95)
        proportions = {"bbox_width": width / CANVAS, "bbox_height": height / CANVAS, "bbox_ratio": width / max(1, height), "head_area_fraction": head["count"] / max(1, width * height), "armor_area_fraction": armor["count"] / max(1, width * height), "cloth_area_fraction": cloth["count"] / max(1, width * height)}
        weapon_fraction = outer / max(1, total); metallic_fraction = metallic_outer / max(1, outer); return {"bbox": [left, top, right, bottom], "regions": {"whole": all_stats, "head_face": head, "armor_palette_material": armor, "black_cloth": cloth}, "body_proportions": {key: round(value, 6) for key, value in proportions.items()}, "weapon_outer_fraction": round(weapon_fraction, 6), "weapon_metallic_outer_fraction": round(metallic_fraction, 6), "weapon_present": metallic_fraction >= 0.02}


def _hist_similarity(left: list[float], right: list[float]) -> float:
    return max(0.0, 1.0 - sum(abs(a - b) for a, b in zip(left, right)) / 2)


def _region_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    if not left.get("count") or not right.get("count"): return 0.0
    rgb = max(0.0, 1.0 - sum(abs(a - b) for a, b in zip(left["mean_rgb"], right["mean_rgb"])) / (3 * 255)); hsv = max(0.0, 1.0 - sum(abs(a - b) for a, b in zip(left["mean_hsv"], right["mean_hsv"])) / 3); hist = _hist_similarity(left["luma_histogram"], right["luma_histogram"])
    return round(.55 * rgb + .25 * hsv + .20 * hist, 6)


def _identity_descriptor(path: Path, anchor: Path) -> dict[str, Any]:
    candidate, reference = _visual_descriptor(path), _visual_descriptor(anchor)
    if not candidate.get("bbox") or not reference.get("bbox"): return {"metrics_version": IDENTITY_METRICS_VERSION, "identity_descriptor_score": 0.0, "weapon_present": False, "components": {}, "failure_reasons": ["missing_foreground"]}
    region_scores = {key: _region_similarity(candidate["regions"].get(key, {}), reference["regions"].get(key, {})) for key in ("armor_palette_material", "head_face", "black_cloth")}
    keys = ("bbox_width", "bbox_height", "bbox_ratio", "head_area_fraction", "armor_area_fraction", "cloth_area_fraction"); differences = [abs(candidate["body_proportions"].get(key, 0.0) - reference["body_proportions"].get(key, 0.0)) / max(.01, abs(reference["body_proportions"].get(key, 0.0))) for key in keys]; body_score = max(0.0, 1.0 - min(1.0, sum(differences) / len(differences)))
    weapon_reference = reference.get("weapon_outer_fraction", 0.0); weapon_present = bool(candidate.get("weapon_present") and candidate.get("weapon_outer_fraction", 0.0) >= max(.01, weapon_reference * .25)); weapon_score = 1.0 if weapon_present else 0.0
    score = round(.28 * region_scores["armor_palette_material"] + .22 * region_scores["head_face"] + .15 * region_scores["black_cloth"] + .20 * body_score + .15 * weapon_score, 6)
    failures = []
    if score < IDENTITY_THRESHOLD: failures.append("identity_descriptor_below_threshold")
    if not weapon_present: failures.append("weapon_missing_or_not_detected")
    if region_scores["head_face"] < .45: failures.append("head_face_drift")
    if region_scores["armor_palette_material"] < .45: failures.append("armor_palette_drift")
    if body_score < .55: failures.append("body_proportion_drift")
    return {"metrics_version": IDENTITY_METRICS_VERSION, "identity_descriptor_score": score, "threshold": IDENTITY_THRESHOLD, "weapon_present": weapon_present, "components": {"armor_palette_material": region_scores["armor_palette_material"], "head_face": region_scores["head_face"], "black_cloth": region_scores["black_cloth"], "body_proportions": round(body_score, 6), "weapon_presence": weapon_score}, "candidate_descriptor": candidate, "anchor_descriptor": reference, "failure_reasons": failures}


def _score_output(path: Path, guide: dict[str, Any], anchor: Path) -> dict[str, Any]:
    info = inspect_png(path); technical = candidate_metrics(path, width=CANVAS, height=CANVAS, requires_transparency=True, margins={"left": 8, "top": 8, "right": 8, "bottom": 8}, occupancy_target={"min": 0.01, "max": 0.92}); pose = _pose_metrics(path, guide); identity = _identity_descriptor(path, anchor)
    pose_pass = pose["pose_score"] >= FRAME_POSE_THRESHOLD; identity_pass = identity["identity_descriptor_score"] >= IDENTITY_THRESHOLD and identity["weapon_present"]
    return {"path": str(path), "sha256": sha256(path), "png": info, "technical": technical, "pose": pose, "identity": identity, "pose_pass": pose_pass, "identity_pass": identity_pass, "weapon_present": identity["weapon_present"], "eligible": bool(technical.get("eligible") and pose_pass and identity_pass), "rejection_reasons": list(technical.get("hard_gate_failures", [])) + ([] if pose_pass else ["pose_score_below_threshold"]) + ([] if identity_pass else identity.get("failure_reasons", ["identity_score_below_threshold"])), "human_visual_review": "required"}


def _run_reference(repo_root: Path, client: ComfyUIClient, *, workflow_id: str, anchor: Path, guide: Path | None, guide_json_sha256: str | None = None, prompt: str, seed: int, output_root: Path, stage: str) -> dict[str, Any]:
    model = load_model(repo_root, QUALITY_MODEL); record = load_workflow(repo_root, workflow_id); uploads = [client.upload_image(anchor)] + ([client.upload_image(guide)] if guide else []); filenames = [item.get("name") or item.get("filename") for item in uploads]
    if not all(isinstance(item, str) and item for item in filenames): raise MultiViewError("ComfyUI upload did not return exact filenames")
    workflow = bind_workflow(record["api"], prompt=prompt, seed=seed, width=CANVAS, height=CANVAS, model_names=_model_names(model), image_filenames=[str(item) for item in filenames]); graph = validate_api_workflow(workflow, node_info=client.node_info())
    if not graph["live_valid"]: raise MultiViewError(f"workflow native node validation failed: {graph['missing_nodes']}")
    job_dir = _unique_job_dir(repo_root, output_root, stage); guide_hash_value = guide_json_sha256 or (sha256(guide) if guide else None)
    result, outputs = _run_job(repo_root, client, workflow, output_dir=job_dir, filename=f"{stage}.png", profile="generic-2d", capability="multi-reference-edit", workflow_id=workflow_id, model_id=QUALITY_MODEL, prompt=prompt, seed=seed, width=CANVAS, height=CANVAS, input_hashes={"reference_0_identity_anchor_sha256": sha256(anchor), "reference_1_pose_view_guide_image_sha256": sha256(guide) if guide else None, "reference_1_pose_view_guide_json_sha256": guide_hash_value}, qualification_context={"stage": stage, "reference_order": ["identity/style/material/character", "pose/view/guide"] if guide else ["identity/style/material/character"], "source_anchor_revision_id": ANCHOR_REVISION_ID, "source_anchor_sha256": ANCHOR_SHA256, "guide_sha256": guide_hash_value, "previous_frame_chaining": False}, workflow_sha256=workflow_hash(workflow))
    output = Path(outputs[0]["path"]); execution = result["job"].get("execution_evidence", {}); return {"stage": stage, "seed": seed, "workflow_id": workflow_id, "workflow_sha256": workflow_hash(workflow), "model_id": QUALITY_MODEL, "output": str(output), "output_sha256": sha256(output), "execution_evidence": execution, "reference_filenames": filenames, "input_hashes": {"reference_0": sha256(anchor), "reference_1_image": sha256(guide) if guide else None, "reference_1_json": guide_hash_value}, "fresh_binding": execution.get("fresh_binding", False), "previous_frame_input": None}


def _runtime_doctor(repo_root: Path, endpoint: str) -> dict[str, Any]:
    client = ComfyUIClient(endpoint, timeout=40.0); health = client.safe_health(); node_info = client.safe_call(client.node_info); model = load_model(repo_root, QUALITY_MODEL); workflow = load_workflow(repo_root, "flux2-klein-base-4b-quality-multi-reference-edit"); multi_cap = probe_comfy_capability(repo_root, client, QUALITY_MODEL, "flux2-klein-base-4b-quality-multi-reference-edit", capability="multi-reference-edit"); biref_cap = probe_comfy_capability(repo_root, client, "birefnet", "birefnet-background-removal", capability="background-removal")
    result = {"schema_version": UGAS_VERSION, "status": "READY" if health.get("status") == "healthy" and multi_cap.get("state") in {"ready", "verified"} and biref_cap.get("state") in {"ready", "verified"} else "LOCAL_POSE_CONTROL_GAP", "endpoint": endpoint, "health": health, "reference_latent_node": {"present": node_info.get("status") == "ok" and "ReferenceLatent" in node_info.get("value", {}), "object_info": node_info.get("value", {}).get("ReferenceLatent") if node_info.get("status") == "ok" else None}, "workflow": {"id": workflow["id"], "sha256": workflow["sha256"], "parameters": workflow.get("parameters", {})}, "model_hashes": {"model_id": model["id"], "manifest_status": model.get("status"), "expected_sha256": model.get("sha256", {}), "exact_files": model.get("exact_files", [])}, "capabilities": {"multi_reference": multi_cap, "background_removal": biref_cap}, "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    write_json(repo_root / "docs/evidence/runtime-doctor-v0.5.1.json", result); return result


def _append_execution(repo_root: Path, records: list[dict[str, Any]], *, status: str) -> dict[str, Any]:
    path = repo_root / "docs/evidence/execution-evidence-v0.5.1.json"; current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema_version": UGAS_VERSION, "records": []}; current["schema_version"] = UGAS_VERSION; current["records"] = current.get("records", []) + records; current["status"] = status; current["fresh_binding_required"] = True; current["all_prompt_ids_present"] = all(bool(item.get("image_edit", {}).get("prompt_id")) for item in current["records"]); current["all_history_bindings_exact"] = all(item.get("image_edit", {}).get("history_key_matches_prompt_id") is True for item in current["records"]); current["stale_output_rejected"] = all(item.get("image_edit", {}).get("target_existed_before_submission") is False for item in current["records"]); current["previous_frame_chaining"] = False; write_json(path, current); return current


def _reset_execution(repo_root: Path) -> None:
    path = repo_root / "docs/evidence/execution-evidence-v0.5.1.json"
    write_json(path, {"schema_version": UGAS_VERSION, "records": [], "status": "RUNNING", "fresh_binding_required": True, "all_prompt_ids_present": True, "all_history_bindings_exact": True, "stale_output_rejected": True, "previous_frame_chaining": False})


def _contact_sheet_with_labels(paths: list[Path], labels: list[str], destination: Path, columns: int = 4) -> dict[str, Any]:
    from PIL import Image, ImageDraw
    if not paths: raise MultiViewError("contact sheet requires at least one image")
    panel_h = CANVAS + 34; rows = math.ceil(len(paths) / columns); sheet = Image.new("RGBA", (columns * CANVAS, rows * panel_h), (248, 248, 248, 255)); draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        with Image.open(path) as source: panel = source.convert("RGBA")
        x, y = (index % columns) * CANVAS, (index // columns) * panel_h; sheet.alpha_composite(panel, (x, y + 34)); draw.rectangle((x, y, x + CANVAS, y + 33), fill=(255, 255, 255, 255)); draw.text((x + 8, y + 10), labels[index][:85], fill=(25, 30, 38, 255))
    destination.parent.mkdir(parents=True, exist_ok=True); sheet.save(destination, format="PNG", optimize=False); return {"path": str(destination), "sha256": sha256(destination), "count": len(paths), "labels": labels}


def _write_v051_visual_manifest(repo_root: Path, *, walk_available: bool = False, anchors_available: bool = False) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    def add(archive_name: str, relative: str, revision_id: str = "v0.5.1") -> None:
        path = repo_root / relative
        if path.is_file(): entries.append({"archive_name": archive_name, "source_path": relative.replace("\\", "/"), "revision_id": revision_id, "sha256": sha256(path) if path.suffix.casefold() not in {".json", ".md", ".txt"} else hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()})
    for name in ("v050-baseline-walk-contact.png", "pose-guides-v2-contact-sheet.png", "pose-guide-v2-control-example.png", "pose-guide-v2-review-overlay.png", "multiref-v2-ab-contact-sheet.png"): add(name, f"docs/evidence/{name}", "historical-v0.5.0" if name.startswith("v050") else "v0.5.1")
    if anchors_available:
        for name in ("directional-anchor-candidates-v2-contact-sheet.png", "directional-anchors-v2-contact-sheet.png"): add(name, f"docs/evidence/{name}")
    if walk_available:
        for name in ("walk-v2-candidates-contact-sheet.png", "walk-v2-selected-contact-sheet.png", "walk-v2-pose-overlay-contact.png", "walk-v2-identity-drift-contact.png", "walk-v2-spritesheet.png", "walk-v2-preview.gif"): add(name, f"docs/evidence/{name}")
    manifest = {"schema_version": UGAS_VERSION, "manifest_type": "review-visual-evidence", "review_state": "walk" if walk_available else "anchors" if anchors_available else "multiref-gap", "images": entries, "renderer_version": POSE_GUIDE_RENDERER_VERSION, "human_visual_review": "required", "production_approval": "not-granted"}; write_json(repo_root / "docs/evidence/review-visuals-v0.5.1.json", manifest); return manifest


def qualify_multiref(repo_root: Path, *, endpoint: str = "http://127.0.0.1:8188", asset_id: str = ANCHOR_ASSET_ID, seed_base: int = 50501) -> dict[str, Any]:
    identity = write_identity_manifest(repo_root, asset_id=asset_id); guides = ensure_pose_guides(repo_root); anchor = _anchor(repo_root); _copy(repo_root / "docs/evidence/walk-front-8-contact-sheet.png", repo_root / "docs/evidence/v050-baseline-walk-contact.png"); _reset_execution(repo_root)
    challenge = render_challenge_guide(repo_root); challenge_guide_value = challenge["guide"]; challenge_image = Path(challenge["control"]["path"]); _copy(challenge_image, repo_root / "docs/evidence/pose-guide-v2-control-example.png"); _copy(Path(challenge["review"]["path"]), repo_root / "docs/evidence/pose-guide-v2-review-overlay.png"); view_render = render_pose_guides(repo_root, "views"); _copy(Path(view_render["review_contact_sheet"]["path"]), repo_root / "docs/evidence/pose-guides-v2-contact-sheet.png")
    client = ComfyUIClient(endpoint, timeout=40.0); doctor = _runtime_doctor(repo_root, endpoint); upstream = _record_upstream(repo_root, client)
    prompt = "Single full-body game character. Image 1 is the canonical identity anchor and controls identity, style, materials, palette, armor, cloth, head, sword and proportions. Image 2 is a mannequin pose guide only. The character in image 1 must stand in the exact pose and strict left profile of image 2, including the arm above the head and the advanced leg. Do not copy the mannequin, its background or any labels. Keep the same face, armor, black cloth, sword and proportions, full body, transparent-ready, no text, no watermark, no redesign."
    records: list[dict[str, Any]] = []; execution_records: list[dict[str, Any]] = []; contact_paths: list[Path] = []; labels: list[str] = []
    if doctor["status"] != "READY":
        evidence = {"schema_version": UGAS_VERSION, "status": "MULTI_REFERENCE_POSE_CONTROL_GAP", "asset_id": asset_id, "stop_reason": "LOCAL_POSE_CONTROL_GAP", "runtime_doctor": doctor, "guide": {"path": f"pose-guides/challenges/{CHALLENGE_NAME}.json", "sha256": guide_hash(challenge_guide_value), "rendered_control_sha256": sha256(challenge_image), "renderer_version": POSE_GUIDE_RENDERER_VERSION}, "records": [], "comparison": {"qualification_rule": "blocked before fresh A/B because local capability evidence is not ready"}}
        write_json(repo_root / "docs/evidence/multiref-v2-qualification.json", evidence); _append_execution(repo_root, [], status=evidence["status"]); _write_v051_visual_manifest(repo_root); return {"status": evidence["status"], "qualification": str(repo_root / "docs/evidence/multiref-v2-qualification.json"), "stop_reason": evidence["stop_reason"]}
    for mode, workflow_id, guide_arg in (("A-canonical-only", QUALITY_EDIT, None), ("B-canonical-plus-mannequin", "flux2-klein-base-4b-quality-multi-reference-edit", challenge_image)):
        for offset in range(AB_SEEDS):
            seed = seed_base + offset; record: dict[str, Any] = {"mode": mode, "seed": seed, "guide_json_sha256": guide_hash(challenge_guide_value), "guide_image_sha256": sha256(challenge_image), "eligible": False}
            try:
                generated = _run_reference(repo_root, client, workflow_id=workflow_id, anchor=anchor, guide=guide_arg, guide_json_sha256=guide_hash(challenge_guide_value) if guide_arg else None, prompt=prompt, seed=seed, output_root=repo_root / "tmp/multiview-v2/ab" / mode, stage=f"multiref-v2-{mode.lower().replace('-', '_')}-{offset}")
                record.update(generated); execution_record = {"stage": f"multiref-v2-{mode}-{offset}", "image_edit": generated["execution_evidence"], "background_removal": {}}; execution_records.append(execution_record)
                normalized, normalization = _transparent_candidate(repo_root, client, Path(generated["output"]), repo_root / "tmp/multiview-v2/ab" / mode / f"candidate-{offset}", f"multiref-v2-{mode}-{offset}", challenge_guide_value); execution_record["background_removal"] = normalization.get("transparency", {}).get("execution_evidence", {}); scored = _score_output(normalized, challenge_guide_value, anchor); record.update(normalized_path=str(normalized), normalized_sha256=sha256(normalized), normalization=normalization, score=scored, eligible=bool(scored["technical"].get("eligible") and scored["identity_pass"])); contact_paths.append(normalized); labels.append(f"{mode} seed={seed} pose={scored['pose']['pose_score']:.3f} id={scored['identity']['identity_descriptor_score']:.3f}")
            except Exception as exc: record.update({"error": f"{type(exc).__name__}: {exc}", "rejection_reasons": ["generation_or_transparency_failed"]})
            records.append(record)
    contact = _contact_sheet_with_labels(contact_paths, labels, repo_root / "tmp/multiview-v2/ab/contact-sheet.png", 2) if contact_paths else None
    if contact: _copy(Path(contact["path"]), repo_root / "docs/evidence/multiref-v2-ab-contact-sheet.png")
    a = [item for item in records if item.get("mode") == "A-canonical-only" and item.get("score")]; b = [item for item in records if item.get("mode") == "B-canonical-plus-mannequin" and item.get("score")]
    a_pose = sum(item["score"]["pose"]["pose_score"] for item in a) / len(a) if a else 0.0; b_pose = sum(item["score"]["pose"]["pose_score"] for item in b) / len(b) if b else 0.0; b_identity = min((item["score"]["identity"]["identity_descriptor_score"] for item in b), default=0.0); b_valid = len(b) == AB_SEEDS and all(item["score"]["technical"].get("eligible") and item["score"]["pose"]["pose_score"] >= AB_POSE_FLOOR and item["score"]["identity_pass"] and item["fresh_binding"] for item in b); meaningful_gain = b_pose >= a_pose + AB_POSE_GAIN
    qualified = len(a) == AB_SEEDS and b_valid and meaningful_gain and b_pose >= AB_POSE_THRESHOLD
    status = "MULTI_REFERENCE_QUALIFIED" if qualified else "MULTI_REFERENCE_POSE_CONTROL_GAP"; comparison = {"A_scored_count": len(a), "A_complete": len(a) == AB_SEEDS, "A_pose_adherence_mean": round(a_pose, 6), "B_scored_count": len(b), "B_complete": len(b) == AB_SEEDS, "B_pose_adherence_mean": round(b_pose, 6), "B_pose_gain": round(b_pose - a_pose, 6), "B_identity_min": round(b_identity, 6), "B_valid": b_valid, "meaningful_B_pose_gain": meaningful_gain, "pose_metric": "keypoint_hit_rate + segment_coverage + normalized_chamfer_silhouette; bbox ratio diagnostic only", "qualification_rule": f"all {AB_SEEDS} B records valid; B >= A + {AB_POSE_GAIN}; B >= {AB_POSE_THRESHOLD}; no B < {AB_POSE_FLOOR}; identity and weapon gates pass"}
    evidence = {"schema_version": UGAS_VERSION, "status": status, "capability": "multi-reference-edit", "asset_id": asset_id, "canonical_anchor": {"asset_id": ANCHOR_ASSET_ID, "revision_id": ANCHOR_REVISION_ID, "sha256": ANCHOR_SHA256}, "runtime_doctor": doctor, "upstream": upstream, "conditioning_contract": {"reference[0]": "canonical identity/style/material/character anchor", "reference[1]": "filled deterministic mannequin pose/view guide", "previous_frame_chaining": False, "independent_text_to_image_frames": False}, "workflow_id": "flux2-klein-base-4b-quality-multi-reference-edit", "native_reference_latent_count": 4, "same_transformation_model_and_seed_pairs": True, "guide": {"path": f"pose-guides/challenges/{CHALLENGE_NAME}.json", "sha256": guide_hash(challenge_guide_value), "rendered_control_path": "docs/evidence/pose-guide-v2-control-example.png", "rendered_control_sha256": sha256(repo_root / "docs/evidence/pose-guide-v2-control-example.png"), "renderer_version": POSE_GUIDE_RENDERER_VERSION}, "records": records, "comparison": comparison, "contact_sheet": "docs/evidence/multiref-v2-ab-contact-sheet.png" if contact else None, "stop_reason": None if qualified else "MULTI_REFERENCE_POSE_CONTROL_GAP", "human_visual_review": "required", "production_approval": "not-granted"}
    write_json(repo_root / "docs/evidence/multiref-v2-qualification.json", evidence); _append_execution(repo_root, execution_records, status=status); _write_v051_visual_manifest(repo_root); return {"status": status, "qualification": str(repo_root / "docs/evidence/multiref-v2-qualification.json"), "records": records, "comparison": comparison}


def normalize_frame(source: Path, destination: Path, *, frame_name: str, guide: dict[str, Any]) -> dict[str, Any]:
    from PIL import Image
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        if image.size != (CANVAS, CANVAS): raise MultiViewError("frame normalization requires 512x512 source")
        bbox = image.getchannel("A").getbbox()
        if not bbox: raise MultiViewError("frame has no alpha foreground")
        left, top, right, bottom = bbox; dx = CENTERLINE_X - ((left + right) / 2); dy = BASELINE_Y - bottom
        source_bbox = [left, top, right, bottom]
        scale = min(1.0, 496 / max(1, right - left), (BASELINE_Y - 8) / max(1, bottom - top))
        for _ in range(12):
            resized = image if scale >= 0.999999 else image.resize((max(1, round(CANVAS * scale)), max(1, round(CANVAS * scale))), Image.Resampling.LANCZOS)
            scaled_bbox = resized.getchannel("A").getbbox()
            if not scaled_bbox: raise MultiViewError("frame lost alpha foreground during uniform scaling")
            scaled_left, scaled_top, scaled_right, scaled_bottom = scaled_bbox
            dx = CENTERLINE_X - ((scaled_left + scaled_right) / 2); dy = BASELINE_Y - scaled_bottom
            if scaled_left + dx >= 8 and scaled_right + dx <= 504 and scaled_top + dy >= 8 and scaled_bottom + dy <= 504: break
            scale *= 0.99
        else:
            raise MultiViewError("frame cannot be normalized within safe margins")
        canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0)); canvas.alpha_composite(resized, (round(dx), round(dy))); destination.parent.mkdir(parents=True, exist_ok=True); canvas.save(destination, format="PNG", optimize=False)
    return {"frame_name": frame_name, "path": str(destination), "sha256": sha256(destination), "alpha_bbox_before": source_bbox, "alpha_bbox_scaled": [scaled_left, scaled_top, scaled_right, scaled_bottom], "source_pivot": {"x": round((left + right) / 2, 3), "y": bottom}, "translation": {"x": round(dx, 3), "y": round(dy, 3)}, "delta_applied": {"x": round(dx, 3), "y": round(dy, 3)}, "scale": round(scale, 6), "pivot_policy": "centerline x 256, ground baseline y 478", "ground_baseline": BASELINE_Y, "guide_sha256": guide_hash(guide), "normalization_status": "SCALED_UNIFORM_AND_TRANSLATED" if scale < 0.999999 else "TRANSLATED_NO_STRETCH"}


def _transparent_candidate(repo_root: Path, client: ComfyUIClient, generated: Path, root: Path, label: str, guide: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    transparent = background_remove(repo_root, str(generated), endpoint=client.base_url, output_dir=root / "birefnet", promote=False); normalized = root / "normalized.png"; normalization = normalize_frame(Path(transparent["output"]), normalized, frame_name=label, guide=guide); qa = candidate_metrics(normalized, width=CANVAS, height=CANVAS, requires_transparency=True, margins={"left": 8, "top": 8, "right": 8, "bottom": 8}, occupancy_target={"min": 0.01, "max": 0.92}); normalization["transparency"] = transparent; normalization["qa"] = qa; return normalized, normalization


def _candidate_ranking_key(item: dict[str, Any]) -> tuple[float, float, float, float, int]:
    score = item.get("score", {}); technical = score.get("technical", {}); return (-float(score.get("pose", {}).get("pose_score", 0.0)), -float(score.get("identity", {}).get("identity_descriptor_score", 0.0)), -float(1.0 if technical.get("safe_margin_ok") else 0.0), -float(score.get("identity", {}).get("candidate_descriptor", {}).get("body_proportions", {}).get("bbox_height", 0.0)), int(item.get("seed", 0)))


def _select_best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [item for item in candidates if item.get("eligible") and item.get("score", {}).get("pose_pass") and item.get("score", {}).get("identity_pass")]
    return sorted(eligible, key=_candidate_ranking_key)[0] if eligible else None


def _directional_selected_record(record: dict[str, Any]) -> dict[str, Any]:
    score = record["score"]; return {"candidate": record.get("candidate"), "seed": record.get("seed"), "path": record.get("normalized_path"), "sha256": record.get("normalized_sha256"), "pose_score": score["pose"]["pose_score"], "identity_descriptor_score": score["identity"]["identity_descriptor_score"], "weapon_present": score["weapon_present"], "guide_sha256": record.get("guide_sha256"), "source_anchor_sha256": ANCHOR_SHA256, "ranking_key": list(_candidate_ranking_key(record))}


def generate_directional_anchors(repo_root: Path, asset_id: str = ANCHOR_ASSET_ID, *, endpoint: str = "http://127.0.0.1:8188", directions: list[str] | None = None, seed_base: int = 50601) -> dict[str, Any]:
    qualification_path = repo_root / "docs/evidence/multiref-v2-qualification.json"; qualification = json.loads(qualification_path.read_text(encoding="utf-8")) if qualification_path.is_file() else {}
    if qualification.get("status") != "MULTI_REFERENCE_QUALIFIED": return {"status": "BLOCKED", "stop_reason": "MULTI_REFERENCE_POSE_CONTROL_GAP"}
    anchor = _anchor(repo_root); client = ComfyUIClient(endpoint, timeout=40.0); selected: dict[str, Any] = {}; candidates: list[dict[str, Any]] = []; requested = directions or ["front", "left", "right", "back"]; selected_paths: list[Path] = []; selected_labels: list[str] = []; candidate_paths: list[Path] = []; candidate_labels: list[str] = []
    front = repo_root / "docs/evidence/anchor-front-v2.png"; _copy(anchor, front); selected["front"] = {"path": str(front.relative_to(repo_root)).replace("\\", "/"), "sha256": sha256(front), "source": "exact-v0.4.3-R4-no-regeneration", "guide": "pose-guides/views/front.json"}; selected_paths.append(front); selected_labels.append("front | exact R4")
    prompt_base = "Use image 1 as the exact canonical character identity/style/material anchor. Use image 2 as a filled deterministic mannequin view guide only. Produce a single full-body game sprite for the requested strict view, preserving face, armor, black cloth, sword, palette and proportions. No diagram, no text, no watermark, no extra limbs, no crop."
    for index, direction in enumerate(item for item in requested if item != "front"):
        guide, guide_image, guide_render = _guide_image(repo_root, f"pose-guides/views/{direction}.json"); eligible: list[dict[str, Any]] = []
        for candidate_index in range(2):
            seed = seed_base + index * 10 + candidate_index; record: dict[str, Any] = {"direction": direction, "candidate": candidate_index + 1, "seed": seed, "guide": f"pose-guides/views/{direction}.json", "guide_sha256": guide_hash(guide), "guide_image_sha256": guide_render["sha256"], "eligible": False, "temporary": True}
            try:
                generated = _run_reference(repo_root, client, workflow_id="flux2-klein-base-4b-quality-multi-reference-edit", anchor=anchor, guide=guide_image, guide_json_sha256=guide_hash(guide), prompt=prompt_base + f" Requested strict view: {direction}.", seed=seed, output_root=repo_root / "tmp/multiview-v2/anchors" / direction, stage=f"anchor-v2-{direction}-{candidate_index}"); normalized, normalization = _transparent_candidate(repo_root, client, Path(generated["output"]), repo_root / "tmp/multiview-v2/anchors" / direction / f"candidate-{candidate_index}", f"anchor-v2-{direction}", guide); score = _score_output(normalized, guide, anchor); record.update(generated, normalized_path=str(normalized), normalized_sha256=sha256(normalized), normalization=normalization, score=score, eligible=score["eligible"], rejection_reasons=score["rejection_reasons"]); candidate_paths.append(normalized); candidate_labels.append(f"{direction} candidate {candidate_index + 1} | pose={score['pose']['pose_score']:.3f} id={score['identity']['identity_descriptor_score']:.3f} {'PASS' if score['eligible'] else 'REJECT'}");
                if record["eligible"]: eligible.append(record)
            except Exception as exc: record.update({"error": f"{type(exc).__name__}: {exc}", "rejection_reasons": ["generation_or_transparency_failed"]})
            candidates.append(record)
        best = _select_best_candidate(eligible)
        if best is None:
            result = {"schema_version": UGAS_VERSION, "status": "NO_ACCEPTABLE_DIRECTIONAL_ANCHOR", "asset_id": asset_id, "anchor_set": selected, "candidates": candidates, "stop_reason": "NO_ACCEPTABLE_DIRECTIONAL_ANCHOR"}; write_json(repo_root / "docs/evidence/directional-anchor-v2-qa.json", result); write_json(repo_root / "docs/evidence/directional-anchor-set-v2.json", result); return {"status": result["status"], "direction": direction, "candidates": candidates}
        target = repo_root / "docs/evidence" / f"anchor-{direction}-v2.png"; _copy(Path(best["normalized_path"]), target); selected[direction] = {**_directional_selected_record(best), "path": str(target.relative_to(repo_root)).replace("\\", "/"), "sha256": sha256(target)}; selected_paths.append(target); selected_labels.append(f"{direction} | selected candidate {best['candidate']} | pose={best['score']['pose']['pose_score']:.3f} id={best['score']['identity']['identity_descriptor_score']:.3f}")
    candidate_sheet = _contact_sheet_with_labels(candidate_paths, candidate_labels, repo_root / "tmp/multiview-v2/anchors/candidates-contact-sheet.png", 3); selected_sheet = _contact_sheet_with_labels(selected_paths, selected_labels, repo_root / "tmp/multiview-v2/anchors/selected-contact-sheet.png", 4); _copy(Path(candidate_sheet["path"]), repo_root / "docs/evidence/directional-anchor-candidates-v2-contact-sheet.png"); _copy(Path(selected_sheet["path"]), repo_root / "docs/evidence/directional-anchors-v2-contact-sheet.png")
    result = {"schema_version": UGAS_VERSION, "status": "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED", "asset_id": asset_id, "anchor_set": selected, "directions": requested, "candidate_count_per_generated_direction": 2, "candidates": candidates, "candidate_selection_policy": "pose_score, then identity_descriptor_score, then safe margin, then scale stability, seed only as exact tie-breaker", "candidate_contact_sheet": "docs/evidence/directional-anchor-candidates-v2-contact-sheet.png", "selected_contact_sheet": "docs/evidence/directional-anchors-v2-contact-sheet.png", "human_visual_review": "required", "production_approval": "not-granted"}; write_json(repo_root / "docs/evidence/directional-anchor-set-v2.json", result); write_json(repo_root / "docs/evidence/directional-anchor-v2-qa.json", {"schema_version": UGAS_VERSION, "status": result["status"], "directions": {direction: {"status": "TECHNICAL_POSE_IDENTITY_GATE_PASSED", "visual_review": "required"} for direction in requested}, "candidates": candidates, "selection_policy": result["candidate_selection_policy"]}); _write_v051_visual_manifest(repo_root, anchors_available=True); return result


def _mask_iou(left: set[tuple[int, int]], right: set[tuple[int, int]]) -> float:
    return len(left & right) / max(1, len(left | right))


def _horizontal_flip(points: set[tuple[int, int]], size: int = 128) -> set[tuple[int, int]]: return {(size - 1 - x, y) for x, y in points}


def _robust_outlier(values: list[float]) -> dict[str, Any]:
    if not values: return {"median": 0.0, "mad": 0.0, "outlier_indices": []}
    center = median(values); mad = median([abs(value - center) for value in values]); limit = center + max(.02, 3 * mad); return {"median": round(center, 6), "mad": round(mad, 6), "limit": round(limit, 6), "outlier_indices": [index for index, value in enumerate(values) if value > limit]}


def _temporal_qa(frames: list[Path], guides: list[dict[str, Any]], frame_scores: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from PIL import Image, ImageChops, ImageStat
    scores = frame_scores or [{} for _ in frames]; hashes = [sha256(path) for path in frames]; unique = len(set(hashes)) == len(hashes); differences: list[float] = []; bboxes = []; masks = []
    for path in frames:
        with Image.open(path) as opened: alpha = opened.convert("RGBA"); bboxes.append(alpha.getchannel("A").getbbox()); masks.append(_mask_points(path, 128))
    for left, right in zip(frames, frames[1:] + frames[:1]):
        with Image.open(left) as a, Image.open(right) as b: differences.append(round(sum(ImageStat.Stat(ImageChops.difference(a.convert("RGB"), b.convert("RGB"))).mean) / 3 / 255, 6))
    heights = [box[3] - box[1] for box in bboxes if box]; root_positions = [((box[0] + box[2]) / 2, box[3]) for box in bboxes if box]; height_variance = (max(heights) - min(heights)) / max(1, sum(heights) / len(heights)) if heights else 1.0; root_drift = max(math.dist(root_positions[0], item) for item in root_positions) if root_positions else 999.0
    pose_scores = [float(item.get("pose", {}).get("pose_score", 0.0)) for item in scores]; lower_scores = [float(item.get("pose", {}).get("lower_body_guide_coverage", 0.0)) for item in scores]; identity_scores = [float(item.get("identity", {}).get("identity_descriptor_score", 0.0)) for item in scores]; weapon = [bool(item.get("weapon_present")) for item in scores]
    half_cycle = [{"phase_pair": [index, index + 4], "silhouette_iou_after_mirror": round(_mask_iou(masks[index], _horizontal_flip(masks[index + 4])), 6)} for index in range(min(4, len(masks) - 4))]; phase_values = [item["silhouette_iou_after_mirror"] for item in half_cycle]; adjacent_stats = _robust_outlier(differences[:-1]); loop_ratio = differences[-1] / max(.001, adjacent_stats["median"]) if differences else 999.0; outlier_indices = adjacent_stats["outlier_indices"] + ([len(differences) - 1] if loop_ratio > LOOP_CLOSURE_FACTOR_MAX else [])
    motion_range = max(lower_scores) - min(lower_scores) if lower_scores else 0.0; gait_motion = bool(differences and median(differences) >= .01 and motion_range >= .08); identity_stability = bool(identity_scores and min(identity_scores) >= IDENTITY_THRESHOLD and weapon and all(weapon))
    gates = {"eight_frames": len(frames) == 8, "unique_sha256": unique, "pose_phase_adherence": bool(pose_scores) and len(pose_scores) == 8 and min(pose_scores) >= FRAME_POSE_THRESHOLD, "lower_body_motion": gait_motion, "half_cycle_mirror": bool(phase_values) and min(phase_values) >= .32, "adjacent_outliers": not outlier_indices, "loop_closure": bool(differences) and loop_ratio <= LOOP_CLOSURE_FACTOR_MAX, "identity_stability": identity_stability, "height_variance": height_variance <= HEIGHT_VARIANCE_MAX, "root_drift": root_drift <= ROOT_DRIFT_MAX, "weapon_presence": len(weapon) == 8 and all(weapon)}
    status = "TEMPORAL_QA_PASSED" if all(gates.values()) else "WALK_TEMPORAL_QA_FAILED"
    return {"metrics_version": "2.0.0", "frame_count": len(frames), "unique_sha256": unique, "hashes": hashes, "pose_scores": [round(value, 6) for value in pose_scores], "lower_body_guide_coverage": [round(value, 6) for value in lower_scores], "identity_descriptor_scores": [round(value, 6) for value in identity_scores], "weapon_present": weapon, "adjacent_frame_difference": differences, "adjacent_difference_statistics": adjacent_stats, "loop_closure_ratio": round(loop_ratio, 6), "loop_closure_factor_max": LOOP_CLOSURE_FACTOR_MAX, "outlier_indices": outlier_indices, "half_cycle_mirror": half_cycle, "half_cycle_mirror_min_iou": min(phase_values) if phase_values else 0.0, "gait_motion_range": round(motion_range, 6), "gait_motion_median_difference": round(median(differences), 6) if differences else 0.0, "height_variance": round(height_variance, 6), "height_variance_max": HEIGHT_VARIANCE_MAX, "root_position_before_normalization": [[round(x, 3), round(y, 3)] for x, y in root_positions], "root_drift_before_normalization": round(root_drift, 6), "root_drift_max": ROOT_DRIFT_MAX, "guides": [guide_hash(guide) for guide in guides], "no_previous_frame_chaining": True, "gates": gates, "status": status}


def frame_diff_contact(frames: list[Path], destination: Path) -> dict[str, Any]:
    from PIL import Image, ImageChops, ImageEnhance
    if len(frames) < 2: raise MultiViewError("at least two frames are required for a diff contact sheet")
    diffs = []
    for left, right in zip(frames, frames[1:] + frames[:1]):
        with Image.open(left) as a, Image.open(right) as b: diffs.append(ImageEnhance.Contrast(ImageChops.difference(a.convert("RGBA"), b.convert("RGBA"))).enhance(3.0))
    sheet = Image.new("RGBA", (CANVAS * 4, CANVAS * 2), (0, 0, 0, 255))
    for index, diff in enumerate(diffs): sheet.alpha_composite(diff, ((index % 4) * CANVAS, (index // 4) * CANVAS))
    destination.parent.mkdir(parents=True, exist_ok=True); sheet.save(destination, format="PNG", optimize=False); return {"path": str(destination), "sha256": sha256(destination), "frame_count": len(frames), "comparison": "adjacent cyclic RGBA absolute differences, contrast x3", "visual_review": "required"}


def _pose_overlay_contact(repo_root: Path, selected: list[Path], guides: list[dict[str, Any]], destination: Path) -> dict[str, Any]:
    from PIL import Image, ImageDraw
    rendered = render_pose_guides(repo_root, "walk-front-8")
    controls = [item["control"]["path"] for item in rendered["guides"]]
    panels = []
    for index, (frame, guide) in enumerate(zip(selected, guides)):
        control = controls[index]
        with Image.open(control) as left, Image.open(frame) as right: panel = Image.new("RGBA", (CANVAS * 2, CANVAS + 30), (255, 255, 255, 255)); panel.alpha_composite(left.convert("RGBA"), (0, 30)); panel.alpha_composite(right.convert("RGBA"), (CANVAS, 30)); ImageDraw.Draw(panel).text((8, 8), f"{guide['frame_name']} | guide / output", fill=(20, 25, 30, 255)); panels.append(panel)
    sheet = Image.new("RGBA", (CANVAS * 2, (CANVAS + 30) * 4), (248, 248, 248, 255))
    for index, panel in enumerate(panels): sheet.alpha_composite(panel, (0, index * (CANVAS + 30)))
    destination.parent.mkdir(parents=True, exist_ok=True); sheet.save(destination, format="PNG", optimize=False); return {"path": str(destination), "sha256": sha256(destination), "frame_count": len(panels)}


def _identity_drift_contact(selected: list[Path], anchor: Path, destination: Path) -> dict[str, Any]:
    from PIL import Image, ImageChops, ImageEnhance, ImageDraw
    panels = []
    with Image.open(anchor) as reference:
        for index, frame in enumerate(selected):
            with Image.open(frame) as current: diff = ImageEnhance.Contrast(ImageChops.difference(current.convert("RGBA"), reference.convert("RGBA"))).enhance(4.0); panel = Image.new("RGBA", (CANVAS, CANVAS + 30), (255, 255, 255, 255)); panel.alpha_composite(diff, (0, 30)); ImageDraw.Draw(panel).text((8, 8), f"frame {index:02d} | identity drift x4", fill=(20, 25, 30, 255)); panels.append(panel)
    sheet = Image.new("RGBA", (CANVAS * 4, (CANVAS + 30) * 2), (248, 248, 248, 255))
    for index, panel in enumerate(panels): sheet.alpha_composite(panel, ((index % 4) * CANVAS, (index // 4) * (CANVAS + 30)))
    destination.parent.mkdir(parents=True, exist_ok=True); sheet.save(destination, format="PNG", optimize=False); return {"path": str(destination), "sha256": sha256(destination), "frame_count": len(panels)}


def generate_walk_frame_candidate(repo_root: Path, client: ComfyUIClient, *, anchor: Path, guide_image: Path, guide: dict[str, Any], frame_name: str, seed: int, attempt: int, output_root: Path, prompt: str) -> dict[str, Any]:
    """Generate one independent candidate, including reference, BiRefNet and every gate."""
    generated = _run_reference(repo_root, client, workflow_id="flux2-klein-base-4b-quality-multi-reference-edit", anchor=anchor, guide=guide_image, guide_json_sha256=guide_hash(guide), prompt=prompt, seed=seed, output_root=output_root, stage=f"{frame_name}-attempt-{attempt}"); normalized, normalization = _transparent_candidate(repo_root, client, Path(generated["output"]), output_root / f"candidate-{attempt}", frame_name, guide); score = _score_output(normalized, guide, anchor); record = {"frame_name": frame_name, "attempt": attempt, "seed": seed, **generated, "raw_output": generated["output"], "raw_output_sha256": generated["output_sha256"], "path": str(normalized), "sha256": sha256(normalized), "normalized_path": str(normalized), "normalized_sha256": sha256(normalized), "alpha_bbox_before": normalization["alpha_bbox_before"], "source_pivot": normalization["source_pivot"], "translation": normalization["translation"], "delta_applied": normalization["delta_applied"], "scale": normalization["scale"], "pivot_policy": normalization["pivot_policy"], "ground_baseline": normalization["ground_baseline"], "guide_sha256": guide_hash(guide), "guide_image_sha256": sha256(guide_image), "normalization_status": normalization["normalization_status"], "normalization": normalization, "score": score, "pose_score": score["pose"]["pose_score"], "identity_descriptor_score": score["identity"]["identity_descriptor_score"], "weapon_present": score["weapon_present"], "eligible": bool(score["eligible"] and generated["fresh_binding"]), "rejection_reasons": score["rejection_reasons"] + ([] if generated["fresh_binding"] else ["fresh_execution_binding_failed"]), "previous_frame_input": None, "temporary": True}
    return record


def _write_walk_failure(repo_root: Path, *, frame_name: str, frame_records: list[dict[str, Any]], all_candidates: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    qa = {"schema_version": UGAS_VERSION, "status": reason, "animation": "walk", "view": "front", "frame_count": 8, "failed_frame": frame_name, "frames": frame_records, "candidates": all_candidates, "stop_reason": reason, "partial_cycle_not_accepted": True, "spritesheet_created": False, "human_visual_review": "required"}; write_json(repo_root / "docs/evidence/walk-v2-temporal-qa.json", qa); _write_v051_visual_manifest(repo_root); return qa


def generate_walk_pilot(repo_root: Path, asset_id: str = ANCHOR_ASSET_ID, *, endpoint: str = "http://127.0.0.1:8188", frames: int = 8, seed_base: int = 50701) -> dict[str, Any]:
    if frames != 8: return {"status": "BLOCKED", "stop_reason": "walk-front-8 requires exactly 8 frames"}
    qualification = json.loads((repo_root / "docs/evidence/multiref-v2-qualification.json").read_text(encoding="utf-8")) if (repo_root / "docs/evidence/multiref-v2-qualification.json").is_file() else {}
    if qualification.get("status") != "MULTI_REFERENCE_QUALIFIED": return {"status": "BLOCKED", "stop_reason": "MULTI_REFERENCE_POSE_CONTROL_GAP"}
    anchors = json.loads((repo_root / "docs/evidence/directional-anchor-set-v2.json").read_text(encoding="utf-8")) if (repo_root / "docs/evidence/directional-anchor-set-v2.json").is_file() else {}
    if anchors.get("status") != "DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED": return {"status": "BLOCKED", "stop_reason": "DIRECTIONAL_ANCHOR_QUALITY_GAP"}
    anchor = _anchor(repo_root); client = ComfyUIClient(endpoint, timeout=40.0); rendered = render_pose_guides(repo_root, "walk-front-8"); guides = [json.loads((repo_root / "pose-guides/walk-front-8" / f"{name}.json").read_text(encoding="utf-8")) for name in WALK_NAMES]; guide_images = [Path(item["control"]["path"]) for item in (item for item in rendered["guides"])]
    frame_records: list[dict[str, Any]] = []; selected_paths: list[Path] = []; selected_guides: list[dict[str, Any]] = []; selected_scores: list[dict[str, Any]] = []; all_candidates: list[dict[str, Any]] = []; execution_records: list[dict[str, Any]] = []
    for index, (frame_name, guide, guide_image) in enumerate(zip(WALK_NAMES, guides, guide_images)):
        prompt = f"Single full-body game character. Frame guide name: {frame_name}, phase: {guide['phase']}. Image 1 defines exact identity, face, armor, black cloth, sword, palette and proportions. Image 2 defines the exact front-facing pose only. Keep camera and direction frontal and constant. Do not redesign face, armor or sword; do not copy the mannequin, background, labels or text; no extra limbs, no watermark."
        attempts: list[dict[str, Any]] = []; chosen: dict[str, Any] | None = None
        for attempt in range(1, 4):
            if attempt == 3 and attempts and any(item.get("eligible") for item in attempts): break
            seed = seed_base + index * 10 + attempt - 1
            try:
                record = generate_walk_frame_candidate(repo_root, client, anchor=anchor, guide_image=guide_image, guide=guide, frame_name=frame_name, seed=seed, attempt=attempt, output_root=repo_root / "tmp/multiview-v2/walk-front-8" / frame_name, prompt=prompt); attempts.append(record); all_candidates.append(record); execution_records.append({"stage": f"walk-v2-{frame_name}-attempt-{attempt}", "image_edit": record["execution_evidence"], "background_removal": record["normalization"].get("transparency", {}).get("execution_evidence", {})})
                if record["eligible"]: chosen = record; break
            except Exception as exc: failure = {"frame_name": frame_name, "attempt": attempt, "seed": seed, "eligible": False, "previous_frame_input": None, "error": f"{type(exc).__name__}: {exc}", "anchor_sha256": ANCHOR_SHA256, "guide_sha256": guide_hash(guide), "guide_image_sha256": sha256(guide_image)}; attempts.append(failure); all_candidates.append(failure)
        if chosen is None:
            _append_execution(repo_root, execution_records, status="NO_ACCEPTABLE_FRAME")
            return {"status": "NO_ACCEPTABLE_FRAME", "failed_frame": frame_name, "qa": _write_walk_failure(repo_root, frame_name=frame_name, frame_records=frame_records, all_candidates=all_candidates, reason="NO_ACCEPTABLE_FRAME")}
        frame_records.append({"frame_name": frame_name, "selected": chosen, "attempts": attempts}); selected_paths.append(Path(chosen["normalized_path"])); selected_guides.append(guide); selected_scores.append(chosen["score"])
    temporal = _temporal_qa(selected_paths, selected_guides, selected_scores); _append_execution(repo_root, execution_records, status=temporal["status"])
    qa = {"schema_version": UGAS_VERSION, "status": "WALK_VISUAL_REVIEW_REQUIRED" if temporal["status"] == "TEMPORAL_QA_PASSED" else "WALK_TEMPORAL_QA_FAILED", "animation": "walk", "view": "front", "frames": frame_records, "temporal": temporal, "human_visual_review": "required", "production_approval": "not-granted"}; write_json(repo_root / "docs/evidence/walk-v2-temporal-qa.json", qa)
    candidate_sheet = _contact_sheet_with_labels([Path(item["normalized_path"]) for item in all_candidates if item.get("normalized_path")], [f"{item['frame_name']} attempt {item['attempt']} | pose={item.get('score', {}).get('pose', {}).get('pose_score', 0):.3f} id={item.get('score', {}).get('identity', {}).get('identity_descriptor_score', 0):.3f}" for item in all_candidates if item.get("normalized_path")], repo_root / "tmp/multiview-v2/walk-front-8/candidates-contact-sheet.png", 4); _copy(Path(candidate_sheet["path"]), repo_root / "docs/evidence/walk-v2-candidates-contact-sheet.png")
    if temporal["status"] != "TEMPORAL_QA_PASSED":
        qa["spritesheet_created"] = False; write_json(repo_root / "docs/evidence/walk-v2-temporal-qa.json", qa); _write_v051_visual_manifest(repo_root); return {"status": "WALK_TEMPORAL_QA_FAILED", "qa": qa}
    sheet_root = repo_root / "docs/evidence"; tracked_frames = []
    for index, path in enumerate(selected_paths): tracked = sheet_root / f"walk-v2-frame-{index:02d}.png"; _copy(path, tracked); tracked_frames.append(tracked)
    selected_sheet = _contact_sheet_with_labels(tracked_frames, [f"{index:02d} {guide['frame_name']} | pose={score['pose']['pose_score']:.3f} id={score['identity']['identity_descriptor_score']:.3f}" for index, (guide, score) in enumerate(zip(selected_guides, selected_scores))], repo_root / "tmp/multiview-v2/walk-front-8/selected-contact-sheet.png", 4); _copy(Path(selected_sheet["path"]), sheet_root / "walk-v2-selected-contact-sheet.png"); overlay = _pose_overlay_contact(repo_root, tracked_frames, selected_guides, sheet_root / "walk-v2-pose-overlay-contact.png"); drift = _identity_drift_contact(tracked_frames, anchor, sheet_root / "walk-v2-identity-drift-contact.png"); diff = frame_diff_contact(tracked_frames, sheet_root / "walk-v2-frame-diff-contact.png")
    from PIL import Image
    frames_rgba = [Image.open(path).convert("RGBA") for path in tracked_frames]; frames_rgba[0].save(sheet_root / "walk-v2-preview.gif", save_all=True, append_images=frames_rgba[1:], duration=125, loop=0, disposal=2); sheet = compose_sheet(tracked_frames, sheet_root / "walk-v2-spritesheet.png", 8)
    metadata = {"schema_version": UGAS_VERSION, "animation": "walk", "view": "front", "frames": 8, "fps": 8, "loop": True, "frame_width": CANVAS, "frame_height": CANVAS, "pivot_policy": "centerline x 256, ground baseline y 478", "frame_files": [str(path.relative_to(repo_root)).replace("\\", "/") for path in tracked_frames], "frame_hashes": [sha256(path) for path in tracked_frames], "spritesheet": "docs/evidence/walk-v2-spritesheet.png", "preview_gif": "docs/evidence/walk-v2-preview.gif", "selected_contact_sheet": "docs/evidence/walk-v2-selected-contact-sheet.png", "pose_overlay_contact": "docs/evidence/walk-v2-pose-overlay-contact.png", "identity_drift_contact": "docs/evidence/walk-v2-identity-drift-contact.png", "frame_diff_contact": "docs/evidence/walk-v2-frame-diff-contact.png", "temporal_qa": temporal["status"], "visual_review": "required", "production_approval": "not-granted"}; write_json(sheet_root / "walk-v2-animation-spec.json", metadata); qa["outputs"] = metadata; qa["spritesheet_created"] = True; write_json(sheet_root / "walk-v2-temporal-qa.json", qa); _write_v051_visual_manifest(repo_root, walk_available=True, anchors_available=True); return {"status": "WALK_VISUAL_REVIEW_REQUIRED", "metadata": str(sheet_root / "walk-v2-animation-spec.json"), "qa": qa, "spritesheet": str(sheet_root / "walk-v2-spritesheet.png"), "preview": str(sheet_root / "walk-v2-preview.gif")}


def identity_inspect(repo_root: Path, asset_id: str = ANCHOR_ASSET_ID) -> dict[str, Any]:
    manifest = build_identity_manifest(repo_root, asset_id); return {"status": validate_identity_manifest(manifest, repo_root)["status"], "manifest": manifest}
