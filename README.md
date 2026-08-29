# Universal Game Asset Studio (UGAS)

UGAS 0.4.0 is a provider-agnostic control plane for reproducible 2D master-sprite production over local ComfyUI. It adds a deterministic master-asset spec and Art DNA prompt compiler, candidate generation/ranking, native BiRefNet background removal, transparent PNG QA, official FLUX.2 Klein reference editing, revision provenance and explicit visual-approval gates.

## What is included

- 38 Agent Skills and the non-destructive consumer bootstrap from v0.2.1;
- ComfyUI API client for health, model/node discovery, workflow jobs, output retrieval and `/upload/image` reference uploads;
- registered API workflows for FLUX.2 Klein text-to-image, FLUX.2 Klein image editing and native BiRefNet background removal;
- deterministic `master-asset-spec`, Art DNA prompt compilation, seeds and candidate-set/contact-sheet manifests;
- objective candidate QA: PNG validity, dimensions, clipping, occupancy, centering, alpha, duplicate/perceptual hash, halo and file-size checks;
- explicit quality states: `GENERATED`, `TECHNICAL_VALID`, `TRANSPARENCY_VALID`, `VISUAL_REVIEW_REQUIRED`, `VISUALLY_APPROVED` and `PRODUCTION_READY`;
- revision-safe reference editing with `derived_from` and reference SHA-256 provenance;
- evidence-based routing where `reference-edit`, `background-removal` and `transparent-sprite-master` require qualified evidence;
- honest scope boundary: full animation, `sprite-grid > 1`, 3D, Blender, audio, paid providers and cloud inference remain gaps.

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

The public CLI returns machine-readable JSON. Operational failures return a nonzero exit code.

## Real 2D master pipeline

```powershell
ugas render-node setup
ugas render-node start
ugas capability --model flux2-klein-4b-nvfp4 --workflow flux2-klein-4b-text-to-image
ugas generate master-sprite "human warrior, stylized fantasy, top-down 3/4" --profile topdown-rpg-mmorpg-2d --candidates 4 --transparent --json
ugas candidates show <asset-id> --json
ugas refine master-sprite <asset-id> --instruction "keep the same character; make the sword shorter and armor blue" --json
ugas background remove <asset-id> --json
ugas asset status <asset-id> --json
ugas visual approve <asset-id> --note "reviewed by the art owner" --json
```

`--candidates` accepts 1-6 and defaults to 4. The implementation starts from a qualified 384x384 path; 512 is only a later benchmark decision. `--transparent` runs native BiRefNet and requires actual alpha values below 255. If a required real workflow or model is not qualified, UGAS returns a capability gap instead of substituting a paid provider, custom node or cosmetic RGB-to-RGBA conversion.

## Master versus reference edit versus animation

Master generation creates independent deterministic candidates and selects only `best_technical_candidate`. Reference edit uploads the selected master to ComfyUI, applies an instruction, and writes a new revision without overwriting its source. Transparency is a separate native BiRefNet stage with an auditable foreground mask. Full animation and sprite grids are not inferred from any of these stages and remain future capabilities.

## Quality gates

`TECHNICAL_VALID` is not artistic approval. `VISUALLY_APPROVED` requires an explicit `ugas visual approve` action recording actor, timestamp, revision and output hash. `PRODUCTION_READY` is impossible without current technical/transparency checks and approval for the same revision. Optional machine assessment is kept separate from human approval.

## Consumer bootstrap

```powershell
python scripts/bootstrap/install_skills.py C:\path\to\my-game
python scripts/bootstrap/inspect_consumer.py C:\path\to\my-game
python scripts/bootstrap/install_consumer.py C:\path\to\my-game
```

The consumer contract is `.game-assets/` with profile, Art DNA, standards, budgets, toolchain, registry, provenance, checkpoint and copied runtime. Refresh requires `--force` and preserves user registry/history/references/manifests.

## Safety and licensing

Model metadata is tracked; weights, generated output, caches, credentials and private endpoint configuration are not. FLUX.2 Klein 4B NVFP4 is recorded as Apache-2.0; Comfy-Org BiRefNet is recorded as MIT with an exact SHA-256. Commercial use still requires the applicable model and output-policy review. ComfyUI remains bound to localhost/private networks.

## Repository map

`src/ugas/` contains the runtime; `providers/models/` and `providers/workflows/` contain tracked registries and API templates; `schemas/` defines contracts; `docs/` contains operations and evidence; `CHECKPOINT.md` and `REVIEW-v0.4.0.md` contain the current slice while earlier reviews remain historical.

## License

UGAS is MIT licensed. Provider services, model weights, references and generated assets may have separate terms.
