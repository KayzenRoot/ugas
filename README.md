# UGAS 0.4.2

Universal Game Asset Studio is a provider-agnostic control plane for a governed 2D master-sprite workflow over local ComfyUI. This corrective slice makes asset revisions immutable and evidence hash-verifiable before any multi-frame animation work.

Pipeline:

`visual request -> machine master spec -> short visual prompt -> FAST/QUALITY lane -> safe-margin hard gates -> selected RGB R1 -> native BiRefNet -> immutable transparent R2 -> measured reference edit R3 -> native BiRefNet -> immutable transparent R4 -> structural QA -> human review`

## Model lanes

- FAST: `flux2-klein-4b-distilled-nvfp4`, 4 steps, guidance 1.0.
- QUALITY: `flux2-klein-4b-base-nvfp4`, 50 steps, guidance 4.0.

Base and Distilled remain explicit in the registries and API graphs. The loader rejects a family, variant, steps or guidance mismatch before submitting a ComfyUI job. Weights stay in the local ComfyUI model directory and are never committed.

## Immutable revisions

Every asset revision receives a new ID-owned directory under `tmp/assets/<asset-id>/revisions/<revision-id>/`. It owns its `output.png`, optional `mask.png`, `checkerboard.png` and `metadata.json`. New background-removal and reference-edit operations never overwrite a previous revision; standalone jobs also use unique directories.

Run `python -m ugas.cli asset verify-integrity <asset-id> --json` to verify paths, hashes, ordering, derivation ancestry, current revision, approval binding and recomputed readiness.

## QA and commands

```powershell
python -m pip install -e .
python -m compileall -q src scripts tests
python -m unittest -q
python scripts/validation/run_validation.py
python -m ugas.cli generate master-sprite "stylized fantasy human warrior with blue steel armor" --quality-policy quality-first --candidates 3 --width 512 --height 512 --transparent --json
python -m ugas.cli asset verify-integrity <asset-id> --json
```

Native BiRefNet supplies the matte while the original RGB source is preserved. Transparency QA records alpha geometry, near-opaque and soft-edge fractions, and RGB MAE on strong foreground pixels. Human visual approval is never inferred from technical or structural QA.

## Scope boundary

This release covers one 2D master sprite, immutable transparency/reference-edit revisions, safe margins, structural QA and review evidence. Animation clips, grids greater than 1, production LoRAs, 3D, Blender, audio, cloud inference and paid providers remain out of scope. The LoRAs `Limbicnation/pixel-art-lora` and `fal/flux-2-klein-4b-spritesheet-lora` are backlog only.

See [INSTALL.md](INSTALL.md), [docs/2d-master-pipeline.md](docs/2d-master-pipeline.md), [CHECKPOINT.md](CHECKPOINT.md), [docs/test-coverage-matrix-v0.4.2.md](docs/test-coverage-matrix-v0.4.2.md) and [REVIEW-v0.4.2.md](REVIEW-v0.4.2.md).

UGAS is MIT licensed. Provider services, model weights, references and generated assets can have separate terms.
