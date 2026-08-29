# Installing UGAS 0.3.0

Python 3.10+ is required. Installation downloads the small Python runtime and Pillow only; model weights and ComfyUI stay outside the Git checkout.

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

The clone directory is `ugas`; all commands are intentionally relative to the actual clone and do not depend on a different historical project name.

## Render node

```powershell
ugas render-node doctor
ugas render-node setup
comfy --help
comfy install --help
comfy install
ugas render-node start
ugas render-node probe
```

UGAS inspects the installed comfy-cli help before using version-sensitive options. Its default workspace is under the user local application data directory, not the repository. The default bind is `127.0.0.1`; remote use requires explicit private-network configuration.

## Model and workflow qualification

`providers/models/registry.json` records exact files, sources, SHA-256 values, license status, VRAM expectations and qualification evidence. A model is not qualified from its name or a `/models` filename alone. The native FLUX.2 Klein workflow is API-format and requires live `/object_info` validation plus a smoke test.

```powershell
ugas models list
ugas models qualify flux2-klein-4b-nvfp4
ugas workflows list
ugas workflows validate flux2-klein-4b-text-to-image --url http://127.0.0.1:8188
ugas capability --model flux2-klein-4b-nvfp4
```

## Consumer runtime

```powershell
python scripts/bootstrap/install_consumer.py C:\path\to\my-game
```

The installer copies a self-contained runtime to `C:\path\to\my-game\.game-assets\tools`. A fresh consumer can invoke that copied launcher from another working directory; it does not reference this checkout by absolute path. `--force` is required for refresh and user registry/provenance/reference history is preserved.

## Real generation

```powershell
ugas generate image "initial warrior sprite, centered, transparent background" --width 256 --height 256 --seed 7
ugas generate sprite-pilot "initial warrior sprite sheet master" --width 256 --height 256 --seed 7
```

Generation fails closed unless capability evidence is `ready` or `verified`. Output QA is technical only: `TECHNICAL_VALID` and `VISUAL_REVIEW_REQUIRED` are distinct from human approval and `PRODUCTION_READY`.

## Troubleshooting

- `comfy` unavailable: install the official comfy-cli in the isolated user environment and rerun setup.
- capability `unavailable`: inspect the recorded missing endpoint, native node, exact model, hash/license or workflow evidence.
- GPU memory failure: record the OOM as evidence and use only the explicitly registered lower-VRAM candidate; do not silently switch models.
- `reference-edit`: intentionally reports a capability gap until a qualified reference workflow exists.
- GitHub publication: push only source/docs/tests/manifests; never weights, generated output, caches, secrets or private network settings.
