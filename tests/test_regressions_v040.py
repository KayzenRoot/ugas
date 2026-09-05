"""Restored v0.4.0 behavioral regression coverage adapted to v0.4.2."""

from __future__ import annotations

import json
import tempfile
import threading
import tomllib
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from ugas.capabilities import mark_verified, probe_comfy_capability
from ugas.comfyui_client import ComfyUIClient, ComfyUIExecutionError, ComfyUITimeoutError
from ugas.constants import CONSUMER_FILES, PROFILES, PROVIDERS, SCHEMAS, SKILLS
from ugas.context import resolve_project_context
from ugas.generation import GenerationError, sprite_pilot
from ugas.image_utils import crop_grid, inspect_png
from ugas.installer import install_consumer
from ugas.jobs import JobError, new_job, transition
from ugas.master_assets import approve_visual, asset_status, candidate_metrics, compile_prompt, make_master_spec
from ugas.providers import comfyui_healthcheck, detect_local_gpu_capability, remote_render_node_healthcheck
from ugas.qa import validate_output
from ugas.router import route_request
from ugas.schema_validation import validate_instance, validate_schema_document
from ugas.skills import validate_skill_frontmatter
from ugas.workflow_registry import bind_workflow, load_workflow


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class RepositoryContractRegressionTests(unittest.TestCase):
    def test_expected_directories_and_documents_exist(self):
        expected = [
            "docs", "skills", "profiles", "templates", "schemas", "providers", "scripts", "examples", "tests",
            "README.md", "INSTALL.md", "CHECKPOINT.md", "REVIEW-v0.3.1.md", "REVIEW-v0.4.0.md", "REVIEW-v0.4.2.md",
            "providers/models/registry.json", "providers/workflows/registry.json",
            "providers/workflows/flux2-klein-base-4b-quality-image-edit.api.json",
            "providers/workflows/birefnet-background-removal.api.json",
        ]
        for item in expected:
            with self.subTest(item=item):
                self.assertTrue((ROOT / item).exists())

    def test_every_skill_has_valid_agent_skills_frontmatter(self):
        self.assertEqual(38, len(SKILLS))
        for skill in SKILLS:
            with self.subTest(skill=skill):
                path = ROOT / "skills" / skill / "SKILL.md"
                valid, errors, values = validate_skill_frontmatter(path.read_text(encoding="utf-8"), skill)
                self.assertTrue(valid, errors)
                self.assertEqual(skill, values["name"])
                self.assertNotIn("disable-model-invocation", path.read_text(encoding="utf-8"))
                content = path.read_text(encoding="utf-8").casefold()
                self.assertIn("trigger", content)
                self.assertIn("when not", content)
                self.assertIn("limits", content)

    def test_profiles_and_schema_documents_validate(self):
        schemas = {name: load_json(ROOT / "schemas" / f"{name}.json") for name in SCHEMAS}
        for schema_name, schema in schemas.items():
            with self.subTest(schema=schema_name):
                validate_schema_document(schema)
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        for profile in PROFILES:
            with self.subTest(profile=profile):
                value = load_json(ROOT / "profiles" / f"{profile}.json")
                validate_instance(value, schemas["profile"])
                self.assertEqual("0.2.1", value["schema_version"])
        validate_instance(load_json(ROOT / "templates" / "profile.json"), schemas["profile"])

    def test_templates_provider_and_workflow_instances_validate(self):
        schemas = {name: load_json(ROOT / "schemas" / f"{name}.json") for name in SCHEMAS}
        pairs = {"art-dna.json": "art-dna", "asset-registry.json": "asset-registry", "performance-budget.json": "performance-budget", "toolchain.json": "toolchain"}
        for filename, schema_name in pairs.items():
            with self.subTest(template=filename):
                validate_instance(load_json(ROOT / "templates" / filename), schemas[schema_name])
        for provider in PROVIDERS:
            manifest = load_json(ROOT / "providers" / "manifests" / f"{provider}.json")
            validate_instance(manifest, schemas["provider-manifest"])
            self.assertIn(manifest["cost_class"], {"local", "self-hosted", "free-tier", "paid"})
            self.assertNotIn("3d-model", manifest["capabilities"])
            self.assertNotIn("animation", manifest["capabilities"])
        for workflow in (ROOT / "providers" / "workflows").glob("*.json"):
            if workflow.name == "registry.json" or workflow.name.endswith(".api.json"):
                continue
            with self.subTest(workflow=workflow.name):
                validate_instance(load_json(workflow), schemas["workflow-manifest"])


class ContextAndInstallerRegressionTests(unittest.TestCase):
    def test_engine_markers_and_dimension_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unity = root / "unity"; (unity / "Assets").mkdir(parents=True); (unity / "ProjectSettings").mkdir(); (unity / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3\n", encoding="utf-8")
            self.assertEqual(("unity", "unknown"), (resolve_project_context(unity).engine, resolve_project_context(unity).dimension))
            godot = root / "godot"; godot.mkdir(); (godot / "project.godot").write_text("[application]\n", encoding="utf-8"); self.assertEqual(("godot", "unknown"), (resolve_project_context(godot).engine, resolve_project_context(godot).dimension))
            unreal = root / "unreal"; unreal.mkdir(); (unreal / "Game.uproject").write_text("{}", encoding="utf-8"); self.assertEqual("unreal", resolve_project_context(unreal).engine)
            web = root / "web"; web.mkdir(); (web / "package.json").write_text(json.dumps({"dependencies": {"pixi.js": "^8.0.0"}}), encoding="utf-8"); context = resolve_project_context(web); self.assertEqual(("pixijs", "2d"), (context.engine, context.dimension)); self.assertEqual("generic-2d", context.profile_recommendation); self.assertEqual("medium", context.profile_confidence)

    def test_context_scan_is_bounded_and_skips_heavy_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / ".git").mkdir(); (root / ".git" / "project.godot").write_text("[application]\n", encoding="utf-8"); (root / "node_modules").mkdir(); (root / "node_modules" / "package.json").write_text("{}", encoding="utf-8")
            context = resolve_project_context(root)
            self.assertEqual("unknown", context.engine); self.assertIn(".git", context.scan_summary["skipped_directories"]); self.assertIn("node_modules", context.scan_summary["skipped_directories"]); self.assertLessEqual(context.scan_summary["files_scanned"], 5000); self.assertEqual([], context.detected_files)

    def test_installer_auto_selection_and_refresh_preserve_history(self):
        with tempfile.TemporaryDirectory() as directory:
            consumer = Path(directory) / "game"; consumer.mkdir(); first = install_consumer(ROOT, consumer); self.assertEqual("profile-pending", first["profile"]); self.assertEqual("unknown", first["profile_confidence"]); target = consumer / ".game-assets"
            for filename in CONSUMER_FILES: self.assertTrue((target / filename).exists())
            registry = target / "asset-registry.json"; registry.write_text(json.dumps({"schema_version": "0.2.1", "assets": [{"id": "keep-me", "status": "draft"}]}), encoding="utf-8"); provenance = target / "provenance.jsonl"; provenance.write_text('{"event":"user-history"}\n', encoding="utf-8"); references = target / "references" / "approved.txt"; references.write_text("keep", encoding="utf-8"); manifests = target / "manifests" / "custom.json"; manifests.write_text("{}", encoding="utf-8")
            refreshed = install_consumer(ROOT, consumer, profile_id="pixel-rpg-2d", force=True); self.assertIn("asset-registry.json", refreshed["preserved"]); self.assertIn("keep-me", registry.read_text(encoding="utf-8")); self.assertIn("user-history", provenance.read_text(encoding="utf-8")); self.assertIn("bootstrap-refreshed", provenance.read_text(encoding="utf-8")); self.assertTrue(references.exists()); self.assertTrue(manifests.exists()); self.assertEqual("pixel-rpg-2d", load_json(target / "profile.json")["id"])


class RoutingRegressionTests(unittest.TestCase):
    def test_default_availability_is_unknown(self):
        result = route_request("Criar vila humana 2D de MMORPG"); self.assertIsNone(result["provider"]); self.assertEqual("unknown", result["routing_status"]); self.assertEqual([], result["available_providers"])

    def test_asset_and_non_asset_classification(self):
        result = route_request("Criar vila humana 2D de MMORPG", availability={"provider-comfyui": "available", "provider-remote-render-node": "available", "provider-huggingface": "available"}); self.assertTrue(result["asset_studio_relevant"]); self.assertEqual(["sprite", "tileset", "animation"], result["asset_types"]); self.assertIsNone(result["provider"]); self.assertEqual("capability_gap", result["routing_status"]); self.assertIn("animation", result["capability_gaps"]["provider-comfyui"]); irrelevant = route_request("Ajustar matchmaking do jogo"); self.assertFalse(irrelevant["asset_studio_relevant"]); self.assertIsNone(irrelevant["provider"])

    def test_3d_final_never_falls_back_to_2d_provider(self):
        result = route_request("Criar boss 3D stylized", availability={"provider-comfyui": "unavailable", "provider-remote-render-node": "unavailable", "provider-huggingface": "available"}); self.assertEqual("3d", result["dimension"]); self.assertEqual("capability_gap", result["routing_status"]); self.assertIsNone(result["provider"]); self.assertIn("3d-model", result["capability_gaps"]["provider-huggingface"])

    def test_paid_disabled_keeps_self_hosted_remote_eligible(self):
        result = route_request("Criar boss 3D stylized", policy="paid-disabled", availability={"provider-comfyui": "unavailable", "provider-remote-render-node": "available", "provider-huggingface": "available"}); self.assertIsNone(result["provider"]); self.assertEqual("capability_gap", result["routing_status"])

    def test_qualified_2d_evidence_selects_comfyui_for_master_sprite(self):
        result = route_request("Criar um master sprite 2D do guerreiro", capability_evidence={"provider-comfyui": {"state": "verified", "asset_capabilities_declared": ["2d", "sprite-master", "sprite-generation"], "asset_capabilities_qualified": ["2d", "sprite-master", "sprite-generation"]}}); self.assertEqual("provider-comfyui", result["provider"]); self.assertEqual("resolved", result["routing_status"])

    def test_partial_mmorpg_plan_exposes_animation_gap(self):
        result = route_request("Criar vila humana 2D de MMORPG", capability_evidence={"provider-comfyui": {"state": "verified", "asset_capabilities_qualified": ["2d", "sprite-master", "sprite-generation"]}}); self.assertIsNone(result["provider"]); self.assertEqual("capability_gap", result["routing_status"]); self.assertIn("animation", result["capability_gaps"]["provider-comfyui"]); self.assertIn("sprite-generation", result["asset_capability_coverage"]["provider-comfyui"])

    def test_capability_gap_skips_preferred_provider_and_uses_capable_fallback(self):
        result = route_request("Criar sprite de inventário", availability={"provider-comfyui": "available", "provider-remote-render-node": "available"}, capabilities={"provider-comfyui": ["2d"], "provider-remote-render-node": ["2d", "sprite-generation"]}); self.assertEqual("provider-remote-render-node", result["provider"]); self.assertIn("sprite-generation", result["capability_gaps"]["provider-comfyui"])


class ProviderReadinessRegressionTests(unittest.TestCase):
    def test_local_and_remote_dry_runs_are_separate(self):
        comfy = comfyui_healthcheck(dry_run=True); self.assertEqual(("local", "dry-run-ready"), (comfy["scope"], comfy["status"])); local = detect_local_gpu_capability(dry_run=True); self.assertEqual("local", local["scope"]); remote = remote_render_node_healthcheck(dry_run=True); self.assertEqual(("remote", "dry-run-ready"), (remote["scope"], remote["status"])); self.assertIn("no local nvidia-smi", remote["checks"])


class VersionAndImageQARegressionTests(unittest.TestCase):
    def test_version_surfaces_are_consistent(self):
        import ugas
        from ugas.constants import UGAS_VERSION
        package = load_json(ROOT / "package.json")
        with (ROOT / "pyproject.toml").open("rb") as stream: pyproject = tomllib.load(stream)
        self.assertEqual("0.20.0", UGAS_VERSION); self.assertEqual(UGAS_VERSION, ugas.__version__); self.assertEqual(UGAS_VERSION, package["version"]); self.assertEqual(UGAS_VERSION, pyproject["project"]["version"])
        for filename in ("README.md", "INSTALL.md", "CHECKPOINT.md"): self.assertIn(UGAS_VERSION, (ROOT / filename).read_text(encoding="utf-8"))

    def test_alpha_and_transparency_stats_distinguish_rgb_and_rgba(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); rgb = root / "rgb.png"; opaque = root / "opaque.png"; transparent = root / "transparent.png"; Image.new("RGB", (2, 2), (255, 0, 0)).save(rgb); Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(opaque); alpha = Image.new("RGBA", (3, 3), (0, 0, 0, 0)); alpha.putpixel((1, 1), (255, 0, 0, 255)); alpha.save(transparent)
            rgb_info = inspect_png(rgb); opaque_info = inspect_png(opaque); transparent_info = inspect_png(transparent); self.assertEqual("RGB", rgb_info["source_mode"]); self.assertFalse(rgb_info["has_alpha_channel"]); self.assertFalse(rgb_info["has_transparent_pixels"]); self.assertIsNone(rgb_info["alpha_min"]); self.assertTrue(opaque_info["has_alpha_channel"]); self.assertFalse(opaque_info["has_transparent_pixels"]); self.assertEqual(255, opaque_info["alpha_min"]); self.assertTrue(transparent_info["has_alpha_channel"]); self.assertTrue(transparent_info["has_transparent_pixels"]); self.assertEqual(0, transparent_info["alpha_min"]); self.assertEqual("TECHNICAL_VALID", validate_output(rgb)["status"]); self.assertEqual("failed", validate_output(rgb, requires_transparency=True)["status"]); self.assertEqual("failed", validate_output(opaque, requires_transparency=True)["status"]); self.assertEqual("TECHNICAL_VALID", validate_output(transparent, requires_transparency=True)["status"])


class ComfyAndPipelineRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.png_file = Path(tempfile.mktemp(suffix=".png")); Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(cls.png_file)

        class Handler(BaseHTTPRequestHandler):
            history_calls = 0
            def log_message(self, *_args): pass
            def _send(self, value, status=200, content_type="application/json"):
                data = value if isinstance(value, bytes) else json.dumps(value).encode(); self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            def do_GET(self):
                if self.path == "/system_stats": return self._send({"system": {"comfyui_version": "test"}, "devices": [{"name": "RTX 5050"}]})
                if self.path == "/features": return self._send({"supports": ["api"]})
                if self.path == "/models": return self._send(["diffusion_models", "text_encoders", "vae"])
                if self.path == "/models/diffusion_models": return self._send(["flux-2-klein-base-4b-nvfp4.safetensors"])
                if self.path == "/models/text_encoders": return self._send(["qwen_3_4b_fp4_flux2.safetensors"])
                if self.path == "/models/vae": return self._send(["flux2-vae.safetensors"])
                if self.path == "/object_info": return self._send({name: {} for name in ["UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode", "EmptyFlux2LatentImage", "RandomNoise", "KSamplerSelect", "Flux2Scheduler", "CFGGuider", "SamplerCustomAdvanced", "VAEDecode", "SaveImage", "ReferenceLatent"]})
                if self.path.startswith("/history/"):
                    Handler.history_calls += 1; return self._send({"test-prompt": {"outputs": {"13": {"images": [{"filename": "test.png", "subfolder": "", "type": "output"}]}}}} if Handler.history_calls > 1 else {})
                if self.path.startswith("/view?"): return self._send(cls.png_file.read_bytes(), content_type="image/png")
                return self._send({"error": "not found"}, 404)
            def do_POST(self):
                if self.path == "/upload/image":
                    length = int(self.headers.get("Content-Length", "0")); self.rfile.read(length); return self._send({"name": "uploaded-reference.png", "subfolder": "", "type": "input"})
                if self.path == "/prompt":
                    length = int(self.headers.get("Content-Length", "0")); json.loads(self.rfile.read(length)); return self._send({"prompt_id": "test-prompt"})
                return self._send({"error": "bad"}, 400)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler); cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start(); cls.endpoint = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=2); cls.png_file.unlink(missing_ok=True)

    def test_client_api_flow_and_output_retrieval(self):
        client = ComfyUIClient(self.endpoint, timeout=2); self.assertEqual("test", client.health()["system"]["comfyui_version"]); prompt = client.submit_workflow({"1": {"class_type": "SaveImage", "inputs": {}}}); item = client.poll_history(prompt["prompt_id"], timeout=3, initial_interval=0.01); outputs = client.fetch_history_outputs(item); self.assertEqual(b"\x89PNG", outputs[0]["data"][:4])

    def test_reference_upload_and_official_workflow_injection(self):
        client = ComfyUIClient(self.endpoint, timeout=2); uploaded = client.upload_image(self.png_file); self.assertEqual("uploaded-reference.png", uploaded["name"]); record = load_workflow(ROOT, "flux2-klein-base-4b-quality-image-edit"); bound = bind_workflow(record["api"], prompt="keep identity; make armor blue", seed=11, width=4, height=4, model_names={"__MODEL__": "model.safetensors", "__CLIP__": "clip.safetensors", "__VAE__": "vae.safetensors"}, image_filename=uploaded["name"]); self.assertEqual("uploaded-reference.png", bound["6"]["inputs"]["image"]); self.assertEqual(11, bound["12"]["inputs"]["noise_seed"]); self.assertEqual("ReferenceLatent", bound["8"]["class_type"])

    def test_client_error_and_route_evidence(self):
        client = ComfyUIClient(self.endpoint)
        with patch.object(ComfyUIClient, "_json", return_value={"error": "node failed"}):
            with self.assertRaises(ComfyUIExecutionError): client.submit_workflow({"1": {"class_type": "X", "inputs": {}}})
        result = route_request("Criar sprite de inventário", capability_evidence={"provider-comfyui": {"state": "declared", "capability": "2d"}}); self.assertIsNone(result["provider"]); self.assertEqual("unknown", result["routing_status"])

    def test_client_timeout_is_structured(self):
        client = ComfyUIClient("http://127.0.0.1:1", timeout=0.01)
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(ComfyUITimeoutError): client.health()

    def test_capability_state_and_image_pipeline(self):
        client = ComfyUIClient(self.endpoint)
        with patch("ugas.capabilities.load_model", return_value={"id": "m", "license": "Apache-2.0", "commercial_use_status": "approved", "status": "qualified", "qualification_evidence": {"hashes_verified": True}, "sha256": {}, "exact_files": ["diffusion_models/flux-2-klein-base-4b-nvfp4.safetensors"], "model_folders": {"diffusion_models": "diffusion_models"}}), patch("ugas.capabilities.load_workflow", return_value={"version": "test", "sha256": "abc", "api": {"1": {"class_type": "SaveImage", "inputs": {}}}}):
            evidence = probe_comfy_capability(ROOT, client, "m", "w")
        self.assertEqual("ready", evidence["state"]); self.assertEqual("verified", mark_verified(evidence, {"status": "passed"})["state"])
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sheet.png"; Image.new("RGBA", (8, 4), (0, 255, 0, 255)).save(source); result = crop_grid(source, Path(directory) / "frame.png", 2, 1); self.assertEqual(2, len(result["frames"])); self.assertEqual("TECHNICAL_VALID", validate_output(source)["status"])

    def test_job_transitions_are_bounded(self):
        job = new_job(consumer_project_id=None, asset_request_id="r", profile="generic-2d", provider="provider-comfyui", capability="2d", workflow={}, models=[], prompts={}, seed=1, dimensions={"width": 4, "height": 4}, parameters={})
        for state in ("validated", "queued", "running", "succeeded", "postprocessed", "validated_output", "registered"): job = transition(job, state)
        with self.assertRaises(JobError): transition(job, "failed")

    def test_sprite_pilot_allows_only_qualified_1x1_master(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "master.png"; Image.new("RGB", (4, 4), (255, 0, 0)).save(source); output_dir = root / "output"
            with patch("ugas.generation.generate_image", return_value={"output": str(source), "job": {"job_id": "job-test"}}):
                result = sprite_pilot(ROOT, endpoint=self.endpoint, prompt="master", output_dir=output_dir, columns=1, rows=1)
            self.assertTrue(Path(result["sprite_sheet"]).exists())
            with self.assertRaisesRegex(GenerationError, "v0.4.3"): sprite_pilot(ROOT, endpoint=self.endpoint, prompt="grid", output_dir=output_dir, columns=2, rows=1)


class MasterAssetRegressionTests(unittest.TestCase):
    def test_prompt_compiler_is_reproducible(self):
        profile = load_json(ROOT / "profiles" / "generic-2d.json"); left = make_master_spec("human warrior, stylized fantasy", profile=profile, profile_id="generic-2d", candidates=3, seed=10, asset_id="asset-fixed", width=384, height=384); right = make_master_spec("human warrior, stylized fantasy", profile=profile, profile_id="generic-2d", candidates=3, seed=10, asset_id="asset-fixed", width=384, height=384); self.assertEqual(left.to_dict(), right.to_dict()); self.assertEqual(compile_prompt(left.to_dict(), profile), compile_prompt(right.to_dict(), profile))

    def test_candidate_metrics_and_visual_gate_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "master.png"; image = Image.new("RGBA", (32, 32), (0, 0, 0, 0));
            for y in range(6, 28):
                for x in range(8, 24): image.putpixel((x, y), (255, 0, 0, 255))
            image.save(output); metrics = candidate_metrics(output, width=32, height=32, requires_transparency=True); self.assertTrue(metrics["alpha_ok"]); self.assertTrue(metrics["occupancy_ok"]); asset_path = root / "asset.json"; revision = {"schema_version": "0.4.2", "revision_id": "revision-1", "asset_id": "asset-test", "revision_number": 1, "derived_from": None, "output_path": str(output), "output_sha256": inspect_png(output)["sha256"], "technical_status": "TECHNICAL_VALID", "transparency_status": "TRANSPARENCY_VALID", "state": "VISUAL_REVIEW_REQUIRED", "visual_approval": {"status": "pending"}, "production_ready": False}; asset_path.write_text(json.dumps({"schema_version": "0.4.2", "asset_id": "asset-test", "requires_transparency": True, "current_revision": revision, "revisions": [revision]}), encoding="utf-8"); self.assertFalse(asset_status(root, str(asset_path))["production_ready"]); approved = approve_visual(root, str(asset_path), "looks readable at gameplay distance"); self.assertTrue(approved["production_ready"]); self.assertEqual("revision-1", approved["visual_approval"]["revision_id"])


if __name__ == "__main__":
    unittest.main()
