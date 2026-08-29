# Provider routing

Provider manifests are declarations. The router must combine them with policy and live or dry-run availability. A manifest with a healthy-looking endpoint does not prove a live service is reachable.

| Provider | Role | V0.2.1 behavior |
| --- | --- | --- |
| `provider-comfyui` | primary local visual provider | `local` cost class, capability manifest, local `/system_stats` probe, dry-run |
| `provider-remote-render-node` | private remote ComfyUI host | `self-hosted` cost class, RTX 5050 target, remote `/system_stats` contract, dry-run |
| `provider-huggingface` | alternative/fallback | manifest and route decision; no model download or inference |

Every selected provider must be recorded in the generation request and provenance. License and model policy remain explicit inputs.

The router filters capability before fallback. A final 3D model requires `3d-model`; a 3D concept/reference request requires `3d-reference`; a 2D provider is never selected for a final 3D model. A manifest is not availability evidence, and an unprobed provider remains `unknown`.
