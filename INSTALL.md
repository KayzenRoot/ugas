# Installing UGAS 0.4.0

Python 3.10+ is required. Installation installs the small Python runtime and Pillow only; ComfyUI and model weights remain outside the Git checkout.

## Clone and validate

```powershell
git clone https://github.com/csn1985-ship-it/ugas.git
Set-Location .\ugas
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python scripts/tests/run_tests.py
python scripts/validation/run_validation.py
```

The validator works both in a normal Git checkout and in a review snapshot extracted without `.git`. In the latter context, Git-only checks report `SKIP_EXTERNAL_GIT_CONTEXT`; required distributable files are still validated.

## Render node and models

```powershell
ugas render-node doctor
ugas render-node setup
ugas render-node start
ugas models list
ugas models qualify flux2-klein-4b-nvfp4
ugas models qualify birefnet
ugas workflows validate flux2-klein-4b-image-edit --url http://127.0.0.1:8188
ugas workflows validate birefnet-background-removal --url http://127.0.0.1:8188
```

The model registry records the exact source, folder, license, SHA-256 and qualification state. Weights are not downloaded into this repository. BiRefNet must be placed at `ComfyUI/models/background_removal/birefnet.safetensors`; UGAS never installs `rembg`, ControlNet, IP-Adapter or arbitrary custom nodes for this slice.

The current 8 GB-class target starts at 384x384. Benchmark 512 only after observing available VRAM; an OOM is recorded as a gap, not hidden by an unregistered model.

## Master, transparency and refinement

```powershell
ugas generate master-sprite "human warrior, stylized fantasy, top-down 3/4" --profile topdown-rpg-mmorpg-2d --candidates 4 --transparent --json
ugas candidates show <asset-id> --json
ugas background remove <asset-id> --json
ugas refine master-sprite <asset-id> --instruction "keep the same character; make the sword shorter and armor blue" --json
ugas asset status <asset-id> --json
ugas visual approve <asset-id> --note "explicit art-owner approval" --json
```

The master command persists the full spec, compiled prompt, seeds, per-candidate QA and contact sheet. The recommended candidate remains `VISUAL_REVIEW_REQUIRED`. Native BiRefNet must produce `has_alpha_channel=true`, `has_transparent_pixels=true` and `transparent_fraction > 0`. Refinement writes a new revision with `derived_from` and the input SHA-256; the original file is never overwritten.

## Consumer runtime

```powershell
python scripts/bootstrap/install_consumer.py C:\path\to\my-game
```

The installer copies the runtime under `C:\path\to\my-game\.game-assets\tools` and does not depend on the checkout path. `--force` is required for refresh and user registry, provenance, references and manifests are preserved.

## Scope and troubleshooting

Full animation, `sprite-grid > 1`, 3D/Blender, audio, hosted inference and paid providers are outside v0.4.0. A `capability_gap` is expected when the endpoint, exact models, native nodes, license or real smoke evidence are unavailable. Keep ComfyUI on localhost/private networks and never commit weights, `.env`, tokens, caches or generated outputs.
