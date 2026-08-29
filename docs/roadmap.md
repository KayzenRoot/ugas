# UGAS roadmap

## v0.4.3 - current slice

Correct the v0.4.2 reference-edit quality failure. This slice independently qualifies the image-edit workflow, records fresh execution binding, adds an explicit color-only edit contract, benchmarks official and legacy parameters, runs a bounded generative candidate set, and uses deterministic armor recolour when the target mask is confident. Photometric, head, protected-region, transparency and revision-integrity evidence are required before human review.

## Release gate

The current pilot is technically `READY_FOR_REVIEW / VISUAL_REVIEW_REQUIRED`. Production readiness is false until a human explicitly approves the selected R4 revision and SHA-256. External approval is not inferred.

## Next gated increment

Only after this correction is accepted may a new prompt define the next scope. Animation, multi-frame idle/walk/run/attack/death, spritesheets, pose generation, ControlNet/IP-Adapter, custom nodes, 3D/Blender, audio, cloud inference, paid providers and production LoRAs are not authorized by v0.4.3.
