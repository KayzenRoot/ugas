# Universal Game Asset Studio (UGAS)

UGAS is a provider-agnostic bootstrap for a game asset studio. It gives humans and coding agents a shared contract for planning, directing, registering, validating, reusing, and eventually generating 2D and 3D assets. Version 0.2 is infrastructure: it does not mass-generate final art or ship model weights.

## Why UGAS exists

Game projects often lose time to inconsistent art direction, unclear asset ownership, provider-specific prompts, and files that cannot be traced back to a profile or license decision. UGAS creates a small, reviewable control plane around those problems:

- profiles for pixel RPGs, MMORPGs, space strategy, cards, platformers, and 3D styles;
- Agent Skills for installation, orchestration, planning, art direction, registry, validation, and providers;
- a consumer installer that creates a local `.game-assets/` contract;
- deterministic dry-run routing for 2D, 3D, and non-asset requests;
- ComfyUI as the primary local provider contract;
- a private-network Render Node contract for an RTX 5050 PC;
- Hugging Face as an explicit alternative, subject to availability and license review;
- provenance, budgets, dependencies, naming, and review checkpoints.

## Quick start

From a clone of this repository:

```powershell
python -m pip install -e .
python scripts/bootstrap/install_consumer.py C:\path\to\my-game --profile topdown-rpg-mmorpg-2d
python scripts/bootstrap/install_skills.py C:\path\to\my-game --skills game-asset-installer game-asset-orchestrator
```

The installer detects common project markers such as Godot, Unity, Unreal, JavaScript/TypeScript, Rust, and Python. It writes the selected profile and provider policy into `my-game/.game-assets/`. Run `python scripts/validation/run_validation.py` to check this checkout, or `python scripts/tests/run_tests.py` to run the test suite.

## Installing with an agent

Give Cursor, Codex, or another agent the public URL of this repository and ask it to inspect the Agent Skills. The equivalent local mechanism is:

```powershell
python scripts/bootstrap/install_skills.py C:\path\to\my-game --destination .agents\skills
python scripts/bootstrap/install_consumer.py C:\path\to\my-game --profile generic-2d
```

The agent should use `game-asset-installer` for setup and `game-asset-orchestrator` for future asset requests. Skills are intentionally short and use progressive disclosure; the orchestrator selects narrower skills only when needed.

## A consumer project after bootstrap

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

The registry is metadata-first. A generated asset is not treated as approved until its manifest, license metadata, provenance, technical checks, and any required human visual review are present.

## Example routing

```powershell
python scripts/providers/route_provider.py --request "Criar vila humana 2D de MMORPG" --dry-run
python scripts/providers/route_provider.py --request "Criar planetas e naves de jogo idle espacial" --dry-run
python scripts/providers/route_provider.py --request "Criar boss 3D stylized" --dry-run
python scripts/providers/route_provider.py --request "Ajustar matchmaking do jogo" --dry-run
```

The first three requests resolve to asset plans and local ComfyUI under `local-first`. Matchmaking is rejected as non-asset work. If local ComfyUI and the Render Node are unavailable, the router reports Hugging Face as the fallback rather than pretending that generation occurred.

## ComfyUI and Render Node

ComfyUI is represented by a versioned provider manifest, a bootstrap workflow manifest, a `/system_stats` health contract, and dry-run readiness checks. A separate RTX 5050 Render Node is expected to host ComfyUI behind a private network such as Tailscale. Do not expose ComfyUI directly to the public internet. Set consumer-local endpoints out of band; no credentials belong in this repository.

```powershell
python scripts/providers/comfyui_healthcheck.py --dry-run
python scripts/providers/capability_probe.py --dry-run
```

V0.2 does not install ComfyUI, download models, submit real jobs, or make a local GPU claim. Those operations belong to a later, explicitly scoped phase.

## Repository map

`skills/` contains the Agent Skills. `profiles/` contains the ten initial game profiles. `schemas/` and `templates/` define machine-readable contracts. `providers/` contains provider and workflow manifests. `src/ugas/` contains the small runtime used by the installer and dry-run tools. `examples/` shows three consumer shapes. `docs/` contains architecture and operating guidance.

## Security and limitations

UGAS never requires a secret in tracked files. Provider endpoints and tokens are consumer-local. Remote rendering should use a private network and least-privilege access. The bootstrap cannot prove external provider uptime, license ownership, visual quality, engine runtime behavior, or GitHub publication. Its tests prove file contracts, JSON parsing, installer behavior, routing decisions, and dry-run readiness only.

## Roadmap

1. Add an explicitly approved ComfyUI client with workflow validation and job lifecycle persistence.
2. Add engine adapters and real technical import checks for Godot, Unity, and Unreal.
3. Add approved model/workflow registries with license evidence and cache policies.
4. Add visual regression and runtime harnesses backed by real project fixtures.
5. Add governed asset packaging and release automation.

## Contributing

Keep contracts small, deterministic, provider-agnostic, and evidence-backed. Add or update tests with every behavior change. Do not commit credentials, model weights, generated caches, or unreviewed reference assets. See `INSTALL.md`, `docs/architecture.md`, and `REVIEW-v0.2.md` before opening a pull request.

## License

UGAS is released under the MIT License. Provider services, models, references, and generated assets may have separate terms; the license auditor contract requires those terms to be recorded independently.
