# ComfyUI integration

UGAS 0.4.0 uses the official local ComfyUI HTTP API with no custom nodes. The client bounds timeouts, response sizes and history polling, and supports multipart `/upload/image` for reference images.

## Official sources used

- FLUX.2 Klein 4B image edit blueprint: `Comfy-Org/ComfyUI` `blueprints/Image Edit (Flux.2 Klein 4B).json`.
- FLUX.2 Klein workflow template: `Comfy-Org/workflow_templates`.
- Native BiRefNet background removal template and documentation.
- BFL/Hugging Face FLUX.2 Klein 4B NVFP4 card and Comfy-Org/Hugging Face BiRefNet card.

UGAS stores flattened API graphs under `providers/workflows/` and records the official source in the workflow registry. Flattening is limited to the standard native graph nodes required by the official blueprint; no blueprint UUID is submitted as an arbitrary custom node.

## Capability evidence

`/system_stats` proves only endpoint health. A capability probe also checks `/features`, `/models/{folder}`, `/object_info`, exact model inventory, registered workflow graph and approved license. States are `unknown`, `unavailable`, `declared`, `ready` and `verified`. Routing can select an asset capability only from qualified evidence; static manifests and health do not qualify it.

The v0.4.0 capability targets are:

- `sprite-master`: qualified by the existing local FLUX.2 Klein text-to-image smoke;
- `reference-edit`: verified only after an actual `/upload/image` plus image-edit job and provenance;
- `background-removal`: verified only after an actual native BiRefNet job;
- `transparent-sprite-master`: verified only after alpha QA finds pixels below 255;
- `animation` and `sprite-grid > 1`: explicit capability gaps.

## FLUX.2 Klein reference edit

The registered workflow uses `LoadImage`, `VAEEncode`, `ReferenceLatent`, `GetImageSize`, native FLUX.2 Klein sampling nodes and `SaveImage`. UGAS uploads the selected master, injects the returned filename, validates every required class through `/object_info`, submits API format, polls `/history`, fetches `/view`, and records workflow/model IDs, hashes, seed, input SHA-256 and derived revision. The source revision is never overwritten.

## BiRefNet transparency

The registered graph uses `LoadBackgroundRemovalModel`, `RemoveBackground`, `InvertMask`, `JoinImageWithAlpha`, `MaskToImage` and two `SaveImage` outputs. The model belongs in `models/background_removal/birefnet.safetensors`. One output is the RGBA result and the other is the small audit mask. UGAS requires `has_alpha_channel=true`, `has_transparent_pixels=true` and `transparent_fraction > 0`; RGB-to-RGBA conversion is not evidence. A simple border semi-transparency check reports a possible halo without pretending to be advanced computer vision.

## API flow

`POST /upload/image` (reference) -> native API graph injection -> `POST /prompt` -> bounded history polling -> `GET /view` -> SHA-256/PNG/alpha QA -> revision/provenance/evidence. Never expose ComfyUI publicly and never put tokens or local private configuration in the repository.
