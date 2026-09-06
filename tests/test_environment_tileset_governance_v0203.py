"""Focused executable tests for the v0.20.3 QA/governance correction."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ugas.environment_tileset_governance_v0203 import (  # noqa: E402
    EnvironmentTileRegistry,
    EnvironmentTilesetContractError,
    ProductionRoutingPolicy,
    recompute_manifest_provenance,
    validate_autotile_matrix,
    validate_origin_roundtrips,
    validate_origin_semantics,
)
from ugas.environment_tileset_runtime_v0202 import generate_fixture_pack  # noqa: E402


class EnvironmentTilesetGovernanceV0203Tests(unittest.TestCase):
    def _fixture(self):
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        manifest = generate_fixture_pack(root)
        self.addCleanup(directory.cleanup)
        return root, manifest

    def _candidate(self, manifest):
        candidate = copy.deepcopy(manifest)
        candidate.update({"test_only": False, "production_safe": True, "production_approved": True, "production_routing": "ENABLED"})
        return recompute_manifest_provenance(candidate)

    def test_enabled_isolated_candidate_uses_shared_semantics(self):
        root, manifest = self._fixture()
        registry = EnvironmentTileRegistry(production=True, production_policy=ProductionRoutingPolicy("ENABLED"), root=root)
        registry.register(self._candidate(manifest))
        self.assertEqual(1, len(registry.entries))

    def test_candidate_hash_tampering_is_semantic_rejection(self):
        root, manifest = self._fixture()
        candidate = self._candidate(manifest)
        candidate["tiles"][0]["binding"]["file_sha256"] = "tampered"
        candidate = recompute_manifest_provenance(candidate)
        registry = EnvironmentTileRegistry(production=True, production_policy=ProductionRoutingPolicy("ENABLED"), root=root)
        with self.assertRaisesRegex(EnvironmentTilesetContractError, "STANDALONE_TILE_BYTES_HASH_MISMATCH"):
            registry.register(candidate)

    def test_matrix_mutation_is_incomplete(self):
        _, manifest = self._fixture()
        mutation = copy.deepcopy(manifest)
        mutation["terrain_families"][0]["autotile_variants"].pop()
        with self.assertRaisesRegex(EnvironmentTilesetContractError, "AUTOTILE_MATRIX_INCOMPLETE"):
            validate_autotile_matrix(mutation)

    def test_origin_semantics_negative_control_is_real(self):
        _, manifest = self._fixture()
        metrics = manifest["metrics"]

        def ignores_origin(x, y, value):
            return (float(x), float(y))

        with self.assertRaisesRegex(EnvironmentTilesetContractError, "ORIGIN_SEMANTICS_IGNORED"):
            validate_origin_semantics(ignores_origin, metrics)

    def test_origin_inverse_negative_control_is_real(self):
        _, manifest = self._fixture()
        metrics = manifest["metrics"]

        def broken_inverse(world_x, world_y, value):
            return (int(round(world_x)) + 1, int(round(world_y)))

        with self.assertRaisesRegex(EnvironmentTilesetContractError, "GRID_ORIGIN_ROUNDTRIP_FAILED"):
            validate_origin_roundtrips(metrics, [(0, 0), (1, 1), (-2, 3)], inverse=broken_inverse)


if __name__ == "__main__":
    unittest.main()
