# Providers and routing

Provider manifests describe contracts; they do not create availability evidence.

| Provider | Scope | v0.3.1 role |
|---|---|---|
| `provider-comfyui` | local | real 2D MVP when capability is `ready`/`verified` |
| `provider-remote-render-node` | remote/private | probe and route only when independently verified |
| `provider-huggingface` | remote metadata/fallback | license/quota review; no implicit hosted inference |

`unknown`, `unavailable`, `declared`, `ready` and `verified` are not interchangeable. Provider manifests expose transport contracts and declared surfaces; only `asset_capabilities_qualified` from workflow/model evidence can select a real job. `paid-disabled` excludes paid providers while retaining self-hosted options. A final 3D model requires `3d-model`; this v0.3.1 slice has no qualified 3D workflow and therefore cannot select ComfyUI for it.
