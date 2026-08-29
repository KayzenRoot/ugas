# Installing UGAS 0.4.3

UGAS requires Python 3.10 or newer, Pillow and a local ComfyUI server. The supported real pilot target is an NVIDIA RTX 5050 with ComfyUI native nodes and locally installed, hash-registered model files.

```powershell
python -m pip install -e .
python -m ugas --version
python scripts/validation/run_validation.py
```

Start ComfyUI on `http://127.0.0.1:8188`, then verify the provider and nodes:

```powershell
python -m ugas comfyui-health --json
python -m ugas workflows validate flux2-klein-base-4b-quality-image-edit --url http://127.0.0.1:8188 --json
```

The image-edit lane is independently qualified from the text-to-image lanes. Base image-edit uses the official native graph with Euler, Flux2Scheduler, 20 steps and CFG 5; Base text-to-image remains 50/4 and Distilled remains 4/1.0. BiRefNet is native and preserves the selected RGB while supplying the alpha matte.

Run the fresh corrective pilot with a known v0.4.2 asset containing R1/R2:

```powershell
python -m ugas reference-edit pilot <source-asset-id> --instruction "Change armor color/material tint from blue steel to deep cobalt/navy steel." --candidates 4 --seed-base 10401 --json
```

The command creates a fresh v0.4.3 asset chain, benchmarks official and legacy reference-edit parameters, records every prompt/history/output binding, runs four generative candidates, evaluates deterministic recolour when the target mask is confident, promotes only the selected R3 and creates R4 after native background removal. Technical output remains pending human visual approval.

Model weights must stay outside Git and must match `providers/models/registry.json` hashes before a production claim. Do not commit `.env`, credentials, caches, `tmp/` or `review/`. Animation, grids larger than 1, custom nodes, hosted inference and paid providers are outside 0.4.3.
