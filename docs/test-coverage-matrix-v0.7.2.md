# UGAS test coverage matrix v0.7.2

| Requirement | Automated coverage | Evidence |
|---|---|---|
| Preserve v0.7.1 historical suite | Existing 203-test suite remains green; v0.7.1 rig tests remain schema-bound | `tests/test_cutout_rig_v071.py`, historical review ZIP |
| Baseline source/mask/part integrity | Hashes of canonical R4, raw/refined masks and RGBA parts | `run_cutout_rig_v072.py`, `execution-evidence-v0.7.2.json` |
| Plan topology and hash binding | Ten adjacency edges, four complete phase plans, shared render/QA hash | `test_cutout_occlusion_v072.py`, `cutout-occlusion-plan-v072.json` |
| Pairwise overlap classification | JOINT, EXPECTED, UNEXPECTED, CRITICAL fixtures and hard gates | `cutout-pairwise-overlap-matrix-v072.json` |
| Topological seam QA | Perfect/1 px pass, 3 px gap fail, connectivity and hole gate | `cutout-seam-topology-qa-v072.json` |
| Retention/occlusion provenance | Expected hidden pixels, unexplained loss, clipping, front/back thresholds | `cutout-retention-occlusion-v072.json` |
| Q0 reconstruction regression | alpha IoU, RGB MAE, bbox drift, no-residual and no-generated-pixel gates | `cutout-q0-regression-v072-qa.json` |
| K1–K4 technical pose qualification | Internal affine metrics, safe margins, no duplicate/detached body, weapon corridor | `cutout-rig-provider-qualification-v072.json` |
| MediaPipe QA | Four target/detected overlays and unchanged historical thresholds | `cutout-key-poses-target-detected-overlays-v072.png` |
| Front-walk gait v2 | Contact separation, passing centerline, hip ratio, bounded depth/root proxy | `cutout-front-walk-gait-v2.json` |
| Half-cycle structure | K1↔K3 and K2↔K4 reflection, arm inversion and sword attachment | `cutout-half-cycle-structure-v072.json` |
| Execution boundary | SAM2=0, ComfyUI=0, walk/spritesheet/GIF not run | `execution-evidence-v0.7.2.json` |
| State consistency | Active gate synchronized with review/checkpoint and previous v0.7.1 state | `current-state.json`, `state-consistency.json` |
| Archive integrity | CRC, traversal, hash, clean extraction compile/tests/validation | `scripts/validation/verify_review_archive.py` |
| No-Git snapshot | Archived tree and extracted snapshot remain self-validating without `.git` | `run_validation.py` |

Historical v0.7.1 intent remains separate from the active v0.7.2 qualification. External visual approval is deliberately not automated or inferred.
