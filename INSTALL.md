# Installing UGAS 0.4.2

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m compileall -q src scripts tests
python -m unittest -q
python scripts/validation/run_validation.py
```

For real local generation, run ComfyUI privately at `http://127.0.0.1:8188`. Place the exact registered files below the ComfyUI model root:

- `diffusion_models/flux-2-klein-4b-nvfp4.safetensors` for FAST;
- `diffusion_models/flux-2-klein-base-4b-nvfp4.safetensors` for QUALITY;
- shared `text_encoders/qwen_3_4b_fp4_flux2.safetensors` and `vae/flux2-vae.safetensors`;
- `background_removal/birefnet.safetensors` for transparency.

Verify exact files with `python -m ugas.cli models qualify <model-id>`. The registry records SHA-256, license and hardware evidence; weights, caches, `.env`, tokens and generated output do not belong in Git.

## Revision and QA contract

New asset revisions live in unique `tmp/assets/<asset-id>/revisions/<revision-id>/` directories. Background removal keeps the original RGB and joins only the native BiRefNet alpha; the resulting transparency evidence includes near-opaque alpha and RGB-preservation metrics. `python -m ugas.cli asset verify-integrity <asset-id> --json` is the integrity auditor.

The reference-edit chain is R1 RGB master -> R2 transparent master -> R3 edited RGB -> R4 transparent edited result. Structural QA compares R2 and R4. Human visual approval is a separate decision and is not inferred automatically.

The consumer installer remains safe-refresh aware: use `ugas install <consumer-root> --force` only when intentionally refreshing an existing `.game-assets` contract. Animation, grids greater than 1, 3D/Blender, audio, hosted inference and paid providers are outside 0.4.2.
