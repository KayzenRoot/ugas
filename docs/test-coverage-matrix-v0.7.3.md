# UGAS test coverage matrix v0.7.3

| Requirement | Automated coverage | Evidence |
|---|---|---|
| Preserve v0.7.2 history | Versioned state/provider snapshots and byte-stable historical files | `current-state-v0.7.2.json`, `state-consistency-v0.7.2.json`, `deterministic-cutout-rig-2d-v0.7.2.json` |
| Structural core provenance | Source alpha/masks/skeleton derivation, no generated pixels, no head/sword coverage | `cutout-structural-core-v073.json`, `cutout-structural-core-mask-v073.png` |
| Structural coverage | Independent expected envelope, hole fraction/component gates, torso/belt/pelvis coverage | `cutout-structural-coverage-v073.json` |
| K4 historical hole regression | v0.7.2 K4 fixture fails against the v0.7.3 structural envelope | `tests/test_cutout_structural_v073.py`, `cutout-structural-hole-overlay-v073.png` |
| Layer integrity | Source area × uniform scale², forward transformed bbox, clipping/loss/gain gates | `cutout-layer-integrity-v073.json`, `cutout-layer-integrity-calibration-v073.json` |
| Authorized regions | Explicit phase geometry for attachments, joints, grip and documented blade/trail thigh | `cutout-authorized-occlusion-regions-v073.json` |
| Pairwise overlap V3 | Strict joint corridor, explicit region, front/back z-order, critical pair zero | `cutout-pairwise-overlap-matrix-v073.json` |
| Topological seam | Historical ten-edge QA retained with one-pixel AA and negative gap fixture | `cutout-seam-topology-qa-v073.json` |
| Retention/occlusion | Independent integrity first; visible thresholds and unexpected occluder fail | `cutout-retention-occlusion-v073.json` |
| Q0 regression | Alpha IoU, RGB MAE, source provenance, no residual/generated pixels | `cutout-q0-regression-v073-qa.json`, `cutout-q0-regression-v073.png` |
| K1–K4 pose qualification | Frozen v0.7.2 target hashes, affine transforms, MediaPipe metrics and overlays | `cutout-rig-provider-qualification-v073.json`, key-pose PNGs |
| Visual evidence | Checkerboard-first, waist zoom, structural-hole overlay and target/detected overlay | `cutout-key-poses-checkerboard-v073.png`, `cutout-key-poses-waist-zoom-v073.png`, `cutout-key-poses-target-detected-overlays-v073.png` |
| Source owner diagnostics | Owner at source, target displacement and core duplication for every hole | `cutout-structural-hole-owner-diagnostics-v073.json` |
| Execution boundary | SAM2=0, ComfyUI=0, walk/spritesheet/GIF not run | `execution-evidence-v0.7.3.json` |
| State consistency | Active gate synchronized with review/checkpoint and previous external rejection | `current-state.json`, `state-consistency.json` |
| Archive integrity | CRC, traversal, hashes, secret scan, clean extraction self-validation | `scripts/validation/verify_review_archive.py` |
| No-Git snapshot | Extracted archive validates without `.git` | `scripts/validation/run_validation.py` |

The external visual rejection of v0.7.2 remains immutable history. Local technical qualification is not external approval, and walk remains blocked until that review.
