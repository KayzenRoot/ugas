# Installing UGAS

UGAS 0.2 is a lightweight repository bootstrap. Python 3.10 or newer is required. The runtime uses only the Python standard library, so a virtual environment is recommended but no model, GPU toolkit, Docker image, or global provider installation is required.

## Manual installation

```powershell
git clone <public-ugas-url>
cd universal-game-asset-studio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python scripts/validation/run_validation.py
```

On macOS/Linux, use `source .venv/bin/activate`. If editable installation is not desired, the checkout scripts still work directly with `python scripts/...`.

## Agent or skills installation

If the environment supports `npx skills`, an agent may install the skills from the public repository using that tool's normal repository syntax. The repository-local equivalent, which works without a global skills CLI, is:

```powershell
python scripts/bootstrap/install_skills.py C:\path\to\my-game --destination .agents\skills
```

Use `--skills` to select a small set, or omit it to install the core installer, orchestrator, resolver, planner, tool router, and provider router. The script refuses to overwrite an existing skill unless `--force` is passed.

## Consumer project bootstrap

```powershell
python scripts/bootstrap/inspect_consumer.py C:\path\to\my-game
python scripts/bootstrap/install_consumer.py C:\path\to\my-game --profile generic-2d --policy local-first
```

Choose one of the profiles in `profiles/`. The installer creates `.game-assets/` and records the detected engine, language, profile, provider policy, and bootstrap provenance. It does not change gameplay code or install ComfyUI.

## Provider readiness

```powershell
python scripts/providers/comfyui_healthcheck.py --dry-run
python scripts/providers/comfyui_healthcheck.py --url http://127.0.0.1:8188
python scripts/providers/comfyui_config.py --dry-run
python scripts/providers/capability_probe.py --dry-run
```

The live healthcheck only reads ComfyUI `/system_stats` and exits nonzero when the endpoint is unavailable. The RTX 5050 Render Node is a documented remote target; use a private network, set its endpoint in consumer-local configuration, and keep credentials out of Git.

## Troubleshooting

- `FileExistsError` during install: inspect `.game-assets/`; use `--force` only after reviewing existing consumer files.
- Unknown engine: pass a profile and review `toolchain.json`; unknown is an honest result, not a failure of the game project.
- ComfyUI unavailable: use the dry-run to confirm the contract, then let the router fall back according to policy. Do not mark a generated result complete.
- No GPU detected: V0.2 does not require a local GPU. A Render Node remains a separate, private endpoint.
- GitHub publication unavailable: verify `gh auth status`, then create the public repository and push only after reviewing the tracked-file scan. This checkout never stores tokens.
