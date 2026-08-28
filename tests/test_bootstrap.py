import json
import tempfile
import unittest
from pathlib import Path

from ugas.constants import CONSUMER_FILES, PROFILES, PROVIDERS, SCHEMAS, SKILLS
from ugas.installer import install_consumer
from ugas.providers import comfyui_healthcheck, detect_render_capability
from ugas.router import route_request


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_expected_directories_and_documents_exist(self):
        expected = ["docs", "skills", "profiles", "templates", "schemas", "providers", "scripts", "examples", "tests", "README.md", "INSTALL.md"]
        for item in expected:
            with self.subTest(item=item):
                self.assertTrue((ROOT / item).exists())

    def test_every_skill_has_trigger_and_limits(self):
        for skill in SKILLS:
            with self.subTest(skill=skill):
                content = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").casefold()
                self.assertIn("trigger", content)
                self.assertIn("when not", content)
                self.assertIn("limits", content)

    def test_profiles_and_schemas_are_valid_json(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                value = json.loads((ROOT / "profiles" / f"{profile}.json").read_text(encoding="utf-8"))
                self.assertEqual(profile, value["id"])
                self.assertIn("budgets", value)
        for schema in SCHEMAS:
            with self.subTest(schema=schema):
                value = json.loads((ROOT / "schemas" / f"{schema}.json").read_text(encoding="utf-8"))
                self.assertTrue(value["$schema"])
                self.assertTrue(value["required"])

    def test_templates_and_workflow_manifest_are_valid_json(self):
        for template in ["studio.json", "profile.json", "art-dna.json", "asset-standards.json", "performance-budget.json", "toolchain.json", "asset-registry.json", "asset-dependencies.json"]:
            with self.subTest(template=template):
                self.assertIsInstance(json.loads((ROOT / "templates" / template).read_text(encoding="utf-8")), dict)
        workflow = json.loads((ROOT / "providers" / "workflows" / "comfyui-bootstrap.json").read_text(encoding="utf-8"))
        self.assertEqual("provider-comfyui", workflow["provider"])

    def test_provider_manifests_exist(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                value = json.loads((ROOT / "providers" / "manifests" / f"{provider}.json").read_text(encoding="utf-8"))
                self.assertEqual(provider, value["id"])
                self.assertTrue(value["capabilities"])


class InstallerTests(unittest.TestCase):
    def test_installer_creates_consumer_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            consumer = Path(directory) / "godot-game"
            consumer.mkdir()
            (consumer / "project.godot").write_text("[application]\n", encoding="utf-8")
            result = install_consumer(ROOT, consumer, "pixel-rpg-2d")
            self.assertEqual("installed", result["status"])
            target = consumer / ".game-assets"
            for filename in CONSUMER_FILES:
                with self.subTest(filename=filename):
                    self.assertTrue((target / filename).exists())
            self.assertEqual("godot", json.loads((target / "studio.json").read_text(encoding="utf-8"))["engine"])
            self.assertEqual("0.2", json.loads((target / "profile.json").read_text(encoding="utf-8"))["schema_version"])


class RoutingTests(unittest.TestCase):
    def test_required_dry_run_routes(self):
        checks = {
            "Criar vila humana 2D de MMORPG": ("2d", ["sprite", "tileset", "animation"]),
            "Criar planetas e naves de jogo idle espacial": ("2d", ["sprite", "background", "ui", "vfx"]),
            "Criar boss 3D stylized": ("3d", ["model", "material", "animation", "lod"]),
        }
        for request, (dimension, asset_types) in checks.items():
            with self.subTest(request=request):
                result = route_request(request)
                self.assertTrue(result["asset_studio_relevant"])
                self.assertEqual(dimension, result["dimension"])
                self.assertEqual(asset_types, result["asset_types"])
                self.assertEqual("provider-comfyui", result["provider"])

    def test_non_asset_request_is_rejected(self):
        result = route_request("Ajustar matchmaking do jogo")
        self.assertFalse(result["asset_studio_relevant"])
        self.assertIsNone(result["provider"])

    def test_render_node_unavailable_falls_back(self):
        result = route_request("Criar boss 3D stylized", providers={"provider-comfyui": False, "provider-remote-render-node": False})
        self.assertEqual("provider-huggingface", result["provider"])


class ProviderReadinessTests(unittest.TestCase):
    def test_comfyui_and_render_node_dry_runs(self):
        self.assertEqual("dry-run-ready", comfyui_healthcheck(dry_run=True)["status"])
        result = detect_render_capability(dry_run=True)
        self.assertEqual("contract-ready", result["status"])
        self.assertIn("RTX 5050", result["gpu"])


if __name__ == "__main__":
    unittest.main()
