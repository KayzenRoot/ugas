# Provider routing

Provider manifests are declarations. The router must combine them with policy and live or dry-run availability. A manifest with a healthy-looking endpoint does not prove a live service is reachable.

| Provider | Role | V0.2 behavior |
| --- | --- | --- |
| `provider-comfyui` | primary local visual provider | manifest, workflow contract, `/system_stats` probe, dry-run |
| `provider-remote-render-node` | private remote ComfyUI host | RTX 5050 target, private-network contract, dry-run |
| `provider-huggingface` | alternative/fallback | manifest and route decision; no model download or inference |

Every selected provider must be recorded in the generation request and provenance. License and model policy remain explicit inputs.
