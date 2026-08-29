# Universal Game Asset Studio (UGAS)

UGAS is a provider-agnostic bootstrap and control plane for game-asset work. Version 0.2.1 stabilizes the infrastructure: it does not generate final art, download model weights, run Blender, submit real ComfyUI jobs, or start Prompt 02.

## What v0.2.1 provides

- 38 Agent Skills with valid YAML frontmatter and folder-matching names;
- complete, core, and profile-scoped skill installation into `.agents/skills`;
- bounded project discovery for Godot, Unity, Unreal, Phaser, PixiJS, Three.js, Babylon.js, and custom projects;
- ten schema-backed profiles plus an honest `profile-pending` state when evidence is insufficient;
- a `.game-assets/` consumer contract with profile recommendation, confidence, evidence, provenance, registry, and checkpoint files;
- capability- and availability-aware dry-run routing for 2D, 3D reference, and final 3D model requests;
- explicit `available`, `unavailable`, and `unknown` provider states;
- separate local ComfyUI/local-GPU probes and remote Render Node probes;
- non-destructive refresh behavior that preserves registry, provenance history, references, and manifests.

## Quick start

From a clone of this repository:

```powershell
python -m pip install -e .
python scripts/bootstrap/install_skills.py C:\path\to\my-game
python scripts/bootstrap/inspect_consumer.py C:\path\to\my-game
python scripts/bootstrap/install_consumer.py C:\path\to\my-game
python scripts/tests/run_tests.py
python scripts/validation/run_validation.py
```

The default skill installation copies all 38 skills. Use `--mode core` for the six bootstrap skills or `--mode profile --profile stylized-3d` for a profile-oriented set. `--force` is required to replace an existing skill directory. Consumer installation discovers the engine and recommends a profile from evidence; pass `--profile <id>` when the project owner has made that decision. Unknown style or dimension remains `profile-pending` instead of silently becoming generic 2D.

## Agent installation block

Copy this block into an agent task:

```text
Repository: https://github.com/csn1985-ship-it/ugas.git
Install the complete UGAS Agent Skills set into the consumer project with:
python scripts/bootstrap/install_skills.py <consumer-root>
Then inspect and bootstrap the consumer with:
python scripts/bootstrap/inspect_consumer.py <consumer-root>
python scripts/bootstrap/install_consumer.py <consumer-root>
Do not generate real assets or start a later prompt unless separately authorized.
```

The repository-local installer is the tested installation route. A third-party Agent Skills CLI may have different syntax; verify that tool independently before relying on it.

## Consumer contract

```text
.game-assets/
  studio.json
  profile.json
  art-dna.json
  asset-standards.json
  performance-budget.json
  toolchain.json
  asset-registry.json
  asset-dependencies.json
  provenance.jsonl
  CHECKPOINT.md
  INSTALLATION-REVIEW.md
  references/
  manifests/
```

Refresh with `--force` only after reviewing the consumer. UGAS preserves `asset-registry.json`, `provenance.jsonl`, `CHECKPOINT.md`, existing files under `references/` and `manifests/`, and provenance history. It updates generated bootstrap metadata without deleting those records.

## Routing and provider contracts

Provider manifests declare capabilities and cost classes (`local`, `self-hosted`, `free-tier`, or `paid`). No probe means `unknown`; unknown is not treated as available. `paid-disabled` excludes only providers declared `paid`, so a self-hosted remote Render Node remains eligible.

```powershell
python scripts/providers/route_provider.py --request "Criar vila humana 2D de MMORPG" --comfyui available --render-node available --huggingface available --dry-run
python scripts/providers/route_provider.py --request "Criar boss 3D stylized" --huggingface available --dry-run
python scripts/providers/comfyui_healthcheck.py --dry-run
python scripts/providers/remote_render_node_healthcheck.py --dry-run
python scripts/providers/capability_probe.py --dry-run
```

A final 3D model requires `3d-model`; a 2D provider is never used as a silent fallback. A concept/reference request is a different capability. ComfyUI health and GPU detection are local probes. The Render Node healthcheck calls the configured remote endpoint and never runs local `nvidia-smi` on behalf of that node. All real generation, credentials, model downloads, and external service availability remain outside this bootstrap.

## Repository map

`skills/` contains the Agent Skills. `profiles/` contains the ten profiles. `schemas/` and `templates/` define machine-readable contracts. `providers/` contains provider and workflow manifests. `src/ugas/` contains the dependency-free runtime. `examples/` shows three consumer shapes. `docs/` contains operating guidance. `REVIEW-v0.2.1.md` records the correction evidence.

## Security and limitations

UGAS never requires a secret in tracked files. Provider endpoints and tokens are consumer-local. Remote rendering should use a private network and least-privilege access. Local checks prove file contracts, bounded discovery, installer behavior, routing decisions, and dry-run readiness; they do not prove provider uptime, model licensing, visual quality, engine runtime behavior, or external GitHub approval.

## License

UGAS is released under the MIT License. Provider services, models, references, and generated assets may have separate terms and must be reviewed independently.
