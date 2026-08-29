# UGAS 0.4.3

Universal Game Asset Studio is a provider-agnostic control plane for a governed 2D master-sprite workflow over local ComfyUI. This correction adds reference-edit fidelity evidence without changing the historical v0.4.2 text-to-image lanes.

Pipeline corrente:

`visual request -> master spec -> FAST/QUALITY text-to-image -> R1 RGB -> BiRefNet R2 -> independently qualified image-edit benchmark -> fresh generative candidates -> deterministic armor recolour fallback -> R3 RGB -> BiRefNet R4 -> structural + appearance QA -> human review`

The reference-edit contract permits only blue-steel armor to deep cobalt/navy steel. Face identity, skin tone and facial exposure, hair, proportions, pose, camera, silhouette, sword, black cloth and the pre-removal composition are protected. Structural IoU is not identity proof; the fidelity gate also measures luminance, head stability, target direction and protected-region changes.

The Base image-edit workflow is capability-specific: official native graph, Euler, Flux2Scheduler, 20 steps and CFG 5. Text-to-image remains Base 50/4 and Distilled 4/1.0. The legacy 50/4 image-edit configuration is retained only as a labeled benchmark comparison.

Run the bounded pilot against the local ComfyUI instance:

```powershell
python -m ugas reference-edit pilot <source-asset-id> --candidates 4 --seed-base 10401 --url http://127.0.0.1:8188 --json
```

The pilot uses fresh prompt IDs, unique seeds, unique job directories and exact history/output hashes. Generative candidates are temporary until selected; a deterministic recolour is eligible only when its documented HSV mask confidence is sufficient. Zero eligible candidates produces `NO_ACCEPTABLE_REFERENCE_EDIT` and does not create R3.

Engineering validation:

```powershell
python -m unittest -q
python scripts/validation/run_validation.py
```

Human visual approval is never inferred from technical QA. The current pilot is technically `VISUAL_REVIEW_REQUIRED`; animation, multi-frame grids, pose generation, custom nodes, 3D/Blender, audio, cloud inference and paid providers remain outside this increment.

See [INSTALL.md](INSTALL.md), [docs/2d-master-pipeline.md](docs/2d-master-pipeline.md), [docs/comfyui.md](docs/comfyui.md), [CHECKPOINT.md](CHECKPOINT.md), [docs/test-coverage-matrix-v0.4.3.md](docs/test-coverage-matrix-v0.4.3.md) and [REVIEW-v0.4.3.md](REVIEW-v0.4.3.md).

UGAS is MIT licensed. Provider services, model weights, references and generated assets can have separate terms.
