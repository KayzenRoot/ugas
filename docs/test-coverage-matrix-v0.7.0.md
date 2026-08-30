# UGAS v0.7.0 Test Coverage Matrix

| Area | Evidence / test | Gate |
|---|---|---|
| Baseline regression | Existing v0.6.2 suite, 161-test floor | Preserve historical behavior |
| Source skeleton | `r4-source-skeleton.json` | 12 core joints plus nose, measurable MediaPipe source |
| SAM2 runtime | `sam2-provider-qualification.json` | Official pinned SAM2.1 Small, import/checkpoint/inference smoke |
| SAM2 provenance | `sam2-checkpoint-provenance.json` | Exact external checkpoint hash; no Git/package copy |
| Prompt construction | `r4-cutout-part-prompts.json` | Eleven deterministic geometry prompts, no manual click |
| Masks | `r4-cutout-part-masks.json` and mask PNGs | Coverage >= .95, unassigned <= .05, overlap <= .03, pure/nonempty |
| Rig schema | `r4-cutout-rig.json`, `cutout-rig.json` | R4 revision/hash, eleven parts, pelvis hierarchy, bounded transform contract |
| Q0 reconstruction | `cutout-q0-qa.json` | Alpha IoU >= .98, RGB MAE <= 3, bbox drift <= 2 px |
| Q1/Q2 geometry | `cutout-rig-pose-qa.json` | Internal root/pivot/angle/scale/disconnect gates |
| Q1/Q2 estimator | `cutout-rig-pose-qa.json` | Existing MediaPipe thresholds unchanged; current result remains gap |
| Seams | `cutout-rig-seam-qa.json` | Zero disconnect/duplicate body components; fragments retained for review |
| Provenance | `cutout-rig-pixel-provenance.json` | Generated pixels 0, source provenance >= .98, recolor/nonuniform 0 |
| Execution boundary | `execution-evidence-v0.7.0.json` | Zero ComfyUI jobs, one SAM2 rig pass, no walk |
| Review integrity | `review-visuals-v0.7.0.json` and archive verifier | Hash-bound visual roles and clean extracted validation |

The final status is `CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP`; this matrix records the failed gates instead of treating the implementation as qualified.
