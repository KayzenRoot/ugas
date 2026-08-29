# Providers and routing

Provider manifests describe contracts; they do not create availability evidence.

| Provider | Scope | v0.3.0 role |
|---|---|---|
| `provider-comfyui` | local | real 2D MVP when capability is `ready`/`verified` |
| `provider-remote-render-node` | remote/private | probe and route only when independently verified |
| `provider-huggingface` | remote metadata/fallback | license/quota review; no implicit hosted inference |

`unknown`, `unavailable`, `declared`, `ready` and `verified` are not interchangeable. A declared manifest or generic health response cannot select a real job. `paid-disabled` excludes paid providers while retaining self-hosted options. A final 3D model requires `3d-model`; a 2D provider cannot satisfy it.
