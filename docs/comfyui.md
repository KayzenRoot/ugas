# ComfyUI v0.4.1

UGAS uses the official local ComfyUI HTTP API with native nodes only. The model registry has explicit FLUX.2 Klein Base and Distilled records and four compatible API workflows:

- `flux2-klein-4b-distilled-text-to-image`: FAST, 4/1.0;
- `flux2-klein-base-4b-quality-text-to-image`: QUALITY, 50/4.0;
- the matching Distilled/Base image-edit workflows;
- `birefnet-background-removal` for native transparency.

Health, inventory and node discovery are evidence inputs, not proof of visual quality. A real qualification needs exact hashes, a live job and persisted smoke evidence. If QUALITY fails from OOM after the supported local/offload attempt, the evidence says `unavailable_on_this_hardware`; it is never silently run with FAST parameters.

The request path is `/upload/image` for a reference, graph binding, `/prompt`, bounded history polling, `/view`, PNG/alpha QA, provenance and revision persistence. Keep ComfyUI on localhost/private networks and never put tokens, private configuration, weights or generated outputs in the repository.
