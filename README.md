# UGAS 0.4.1

Universal Game Asset Studio is a provider-agnostic control plane for a governed 2D master-sprite workflow over local ComfyUI. This slice corrects the FLUX.2 Klein Base/Distilled mismatch before any multi-frame animation work.

The current pipeline is:

`visual request -> machine master spec -> short visual prompt -> FAST/QUALITY lane -> hard candidate gates -> eligible selection -> native BiRefNet -> alpha QA/checkerboard -> measurable reference edit -> BiRefNet -> silhouette QA -> VISUAL_REVIEW_REQUIRED`

## Model lanes

- FAST: `flux2-klein-4b-distilled-nvfp4`, 4 steps, guidance 1.0.
- QUALITY: `flux2-klein-4b-base-nvfp4`, 50 steps, guidance 4.0.

Both lanes are explicitly represented in `providers/models/registry.json` and their API graphs in `providers/workflows/`. The loader rejects a variant/parameter mismatch before submitting a ComfyUI job. Weights are downloaded to the local ComfyUI model directory and are never committed.

## Commands

```powershell
python -m pip install -e .
python -m unittest -q
python scripts/validation/run_validation.py
python -m ugas.cli capability --model flux2-klein-4b-distilled-nvfp4 --workflow flux2-klein-4b-distilled-text-to-image --json
python -m ugas.cli benchmark quality "stylized fantasy human warrior with blue steel armor" --seed 4301 --width 512 --height 512 --json
python -m ugas.cli generate master-sprite "stylized fantasy human warrior with blue steel armor" --quality-policy quality-first --candidates 3 --width 512 --height 512 --json
```

`quality-first`, `balanced` and `fast` are policy choices, not visual approval. An automatic fallback records why QUALITY was unavailable. Candidates with clipping, invalid dimensions, empty output, duplicate content, out-of-range occupancy, bad centering, oversized files or invalid transparency are ineligible; if none pass, the result is `NO_ACCEPTABLE_CANDIDATE`.

## Scope boundary

This release covers one 2D master sprite, transparent-background QA, native BiRefNet and one identity-preserving reference edit. Animation clips, grids greater than 1, production LoRAs, 3D, Blender, audio, cloud inference and paid providers remain out of scope. The LoRAs `Limbicnation/pixel-art-lora` and `fal/flux-2-klein-4b-spritesheet-lora` are backlog items only.

See [INSTALL.md](INSTALL.md), [docs/2d-master-pipeline.md](docs/2d-master-pipeline.md), [docs/comfyui.md](docs/comfyui.md), [CHECKPOINT.md](CHECKPOINT.md) and [REVIEW-v0.4.1.md](REVIEW-v0.4.1.md).

UGAS is MIT licensed. Provider services, model weights, references and generated assets can have separate terms.
