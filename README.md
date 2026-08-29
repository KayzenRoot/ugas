# Universal Game Asset Studio (UGAS)

UGAS 0.3.1 is a provider-agnostic control plane for a real, local 2D MVP over ComfyUI. It hardens the distributable model registry, tracked-snapshot validation, capability evidence, alpha QA and the honest master-only Sprite Pilot. A green static check or `/system_stats` response is not a generation proof.

## What is included

- 38 Agent Skills and the non-destructive consumer bootstrap from v0.2.1;
- ComfyUI API client for `/system_stats`, `/features`, `/models`, `/object_info`, `/prompt`, `/history`, `/view` and `/upload/image`;
- explicit capability states: `unknown`, `unavailable`, `declared`, `ready`, `verified`;
- native-node FLUX.2 Klein workflow and Apache-2.0 model candidates, with exact-file/hash/license gates;
- `doctor`, `setup`, `start`, `stop`, `status` and `probe` render-node commands;
- `generate image`, a reference-edit capability gap, and a master-only sprite-pilot (grid > 1 fails closed);
- technical PNG validation, provenance and duplicate-aware asset registry updates;
- self-contained consumer runtime copied under `.game-assets/tools`, independent of the original checkout path.

## Quick start

```powershell
git clone https://github.com/csn1985-ship-it/ugas.git
Set-Location .\ugas
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python scripts/tests/run_tests.py
python scripts/validation/run_validation.py
```

The repository-local scripts work directly from the checkout. The package entry point is `ugas`; machine-readable commands return JSON and nonzero status on operational failure.

## Zero-to-render with Cursor/Codex

Run from the repository root:

```powershell
ugas render-node doctor
ugas render-node setup
# Install ComfyUI with the official comfy-cli in the reported isolated workspace.
ugas render-node start
ugas capability --model flux2-klein-4b-nvfp4 --workflow flux2-klein-4b-text-to-image
ugas generate image "initial warrior sprite, centered, transparent background" --width 256 --height 256 --seed 7
```

The first real job is allowed only when evidence is `ready` or `verified`, which requires a reachable server, native nodes, exact model inventory, approved license and validated workflow. A successful job is `TECHNICAL_VALID` with `VISUAL_REVIEW_REQUIRED`; UGAS never silently marks visual output production-ready.

## Consumer bootstrap

```powershell
python scripts/bootstrap/install_skills.py C:\path\to\my-game
python scripts/bootstrap/inspect_consumer.py C:\path\to\my-game
python scripts/bootstrap/install_consumer.py C:\path\to\my-game
```

The consumer contract is `.game-assets/` with profile, Art DNA, standards, budgets, toolchain, registry, provenance, checkpoint and a copied runtime. Refresh requires `--force` and preserves user registry/history/references/manifests.

## Scope and safety

The v0.3.1 correction still stops at real 2D ComfyUI/render-node foundation and a 1x1 master-image pilot. Full animation, 3D/Blender, audio, cloud inference, paid providers and reference-edit generation remain outside this slice. Weights, caches, outputs, credentials and private endpoint configuration are never committed. Remote endpoints must stay on a private network.

Provider/model terms are independent of UGAS. Commercial use requires an explicit license decision in the model registry. Local readiness is not external approval or production approval.

## Repository map

`src/ugas/` contains the runtime; `providers/models/` and `providers/workflows/` contain tracked registries and API templates; `schemas/` defines contracts; `docs/` contains operations and evidence; `REVIEW-v0.3.1.md` and `CHECKPOINT.md` contain current evidence; earlier reviews remain historical.

## License

UGAS is MIT licensed. Provider services, model weights, references and generated assets may have separate terms.
