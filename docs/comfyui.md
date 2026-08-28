# ComfyUI contract

UGAS treats ComfyUI as the priority visual provider without requiring a user to operate its UI manually. The contract anticipates installation, health, GPU and CUDA capability detection, model and workflow registries, HTTP/WebSocket clients, job submission, polling, output retrieval, logs, and Render Node integration.

V0.2 implements the safe foundation only:

- `providers/manifests/provider-comfyui.json` declares capabilities and credential policy;
- `providers/workflows/comfyui-bootstrap.json` declares a versioned, minimal workflow contract;
- `scripts/providers/comfyui_healthcheck.py --dry-run` proves the probe shape without network access;
- `scripts/providers/comfyui_config.py --dry-run` renders an install/configuration plan without writing secrets;
- the live probe reads `GET /system_stats` and reports `healthy` or `unavailable` without retry storms;
- `scripts/providers/capability_probe.py` can inspect `nvidia-smi` when explicitly run, but does not install drivers or models.

Future job submission must validate the workflow, bind a request ID, record a provider revision, poll with bounded retries, and store output paths plus provenance. Tokens belong in environment or a local secret manager, never in a workflow file.
