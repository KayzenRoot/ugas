# Installing UGAS 0.2.1

Python 3.10 or newer is required. The runtime uses only the Python standard library; no model, GPU toolkit, Docker image, or provider installation is required for the bootstrap.

## Clone and validate

```powershell
git clone https://github.com/csn1985-ship-it/ugas.git
cd universal-game-asset-studio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python scripts/tests/run_tests.py
python scripts/validation/run_validation.py
```

If editable installation is not desired, the scripts work directly from the checkout with `python scripts/...`.

## Agent Skills

The tested repository-local route installs all 38 skills by default:

```powershell
python scripts/bootstrap/install_skills.py C:\path\to\my-game
```

Use `--mode core` for the six bootstrap skills, or select a profile-oriented set:

```powershell
python scripts/bootstrap/install_skills.py C:\path\to\my-game --mode profile --profile topdown-rpg-mmorpg-2d
```

An explicit `--skills` list is also supported. Existing skill directories are never replaced without `--force`. The installed skills are self-contained copies from this checkout and do not depend on temporary extraction paths. No unverified `npx skills` command is required; if another Agent Skills CLI is used, verify its current repository syntax separately.

## Consumer bootstrap

```powershell
python scripts/bootstrap/inspect_consumer.py C:\path\to\my-game
python scripts/bootstrap/install_consumer.py C:\path\to\my-game
```

Inspection reports engine, dimension, scan bounds, `profile_recommendation`, `profile_confidence`, and `profile_evidence`. The installer chooses an evidence-backed profile when possible. For a project with unknown style or dimension it creates `profile-pending`; pass an explicit profile when the owner has decided.

The installer creates `.game-assets/` and records detected context, profile data, provider policy, bounded scan evidence, and bootstrap provenance. `--force` refreshes generated metadata but preserves `asset-registry.json`, `provenance.jsonl`, `CHECKPOINT.md`, existing `references/`, and existing `manifests/` contents. It does not change gameplay code.

## Provider readiness

```powershell
python scripts/providers/comfyui_healthcheck.py --dry-run
python scripts/providers/comfyui_healthcheck.py --url http://127.0.0.1:8188
python scripts/providers/remote_render_node_healthcheck.py --dry-run
python scripts/providers/remote_render_node_healthcheck.py --endpoint http://remote-render-node:8188
python scripts/providers/capability_probe.py --dry-run
```

The local ComfyUI healthcheck reads local `/system_stats`. The remote check reads the configured remote endpoint. Local GPU detection is a separate local-only probe; it never asserts the remote RTX 5050 state. Keep endpoints and credentials out of Git and use a private network for the Render Node.

## Routing semantics

`available`, `unavailable`, and `unknown` are distinct. Without a probe, providers are `unknown` and no provider is selected. Routing filters capabilities before fallback: final 3D models require `3d-model`, while concept/reference work can use `3d-reference`. `paid-disabled` excludes only `paid`; `self-hosted` remains eligible.

## Troubleshooting

- `FileExistsError`: inspect `.game-assets/` and use `--force` only after reviewing consumer data.
- `profile-pending`: provide an explicit profile or add authoritative project evidence; UGAS does not silently assume generic 2D.
- `ComfyUI unavailable`: use the dry-run contract and do not mark a generation result complete.
- no local GPU: the bootstrap does not require one; configure and probe a private remote endpoint separately.
- GitHub publication blocked: verify authentication, then set the repository remote and push reviewed commits. Never store tokens in files.
