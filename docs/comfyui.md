# ComfyUI integration

UGAS v0.3.1 uses the official ComfyUI HTTP API. `ComfyUIClient` has bounded timeouts, response-size limits, structured HTTP/protocol/execution errors and capped polling.

## Evidence contract

`/system_stats` proves only that an endpoint answered. The capability probe additionally checks `/features`, `/models/{folder}`, `/object_info`, the selected exact model manifest, the API workflow and the approved license. States are `unknown`, `unavailable`, `declared`, `ready` and `verified`; only the last two may be selected for a real job, and only a passed smoke test makes `verified`.

## Official workflow/model path

The MVP uses native FLUX.2 Klein nodes with no arbitrary custom-node installation. The registry points to official Comfy-Org/BFL sources, records exact files and requires hashes after download. The FP8 candidate is preferred where VRAM permits; the NVFP4 candidate is an explicit lower-VRAM fallback, not an invisible substitution.

## API flow

`POST /prompt` -> bounded history polling -> output descriptors -> `GET /view` -> SHA-256 -> PNG/alpha QA -> provenance/registry. Reference upload is implemented at `/upload/image`, but reference-edit generation remains an explicit capability gap until its workflow is qualified. The current qualified workflow produces a 2D master only; Sprite Pilot rejects grid > 1 until a grid workflow is qualified.

Never expose ComfyUI publicly and never put tokens or local private configuration in the repository.
