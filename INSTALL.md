# Installing UGAS 0.4.1

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest -q
python scripts/validation/run_validation.py
```

For real local generation, run ComfyUI privately at `http://127.0.0.1:8188`. Place the exact registered files below the ComfyUI model root:

- `diffusion_models/flux-2-klein-4b-nvfp4.safetensors` for FAST;
- `diffusion_models/flux-2-klein-base-4b-nvfp4.safetensors` for QUALITY;
- the shared `text_encoders/qwen_3_4b_fp4_flux2.safetensors` and `vae/flux2-vae.safetensors`;
- `background_removal/birefnet.safetensors` for transparency.

Verify exact files with `python -m ugas.cli models qualify <model-id>`. The registry records SHA-256, license and hardware evidence; no weight, cache, `.env`, token or generated output belongs in Git.

The consumer installer remains safe-refresh aware: use `ugas install <consumer-root> --force` only when intentionally refreshing an existing `.game-assets` contract. Full animation, grids greater than 1, 3D/Blender, audio, hosted inference and paid providers are outside 0.4.1.
