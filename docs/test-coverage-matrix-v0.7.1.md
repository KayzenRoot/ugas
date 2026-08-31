# UGAS test coverage matrix v0.7.1

| Requirement | Automated coverage | Evidence | Gate |
|---|---|---|---|
| Preserve v0.7.0 tests | Existing 183-test suite retained | `tests/test_cutout_rig_v070.py` and historical test modules | pass |
| Hips and explicit side mapping | Q1/Q2 target invariants and asymmetric fixture | `r4-cutout-target-adapter-v071.json` | pass |
| Weapon attachment | Wrist, local angle, bounded swing and protected corridor | target adapter JSON | pass |
| Raw/refined separation | Distinct directories, manifests and file hashes | raw/refined manifests | pass |
| Component QA | Meaningful component thresholds and torso/sword limits | component diagnostics JSON | pass |
| Foreground ownership | Semantic union, strict ownership and unassigned fraction | refined mask manifest | pass |
| Q0 no residual | Parts-only compose path and fallback false | Q0 QA and rig provenance JSON | pass |
| Joint blending | Source-bound bands, zero copied patches | rig/provenance JSON | pass |
| Internal geometry | Forward affine matrix, pivot, angle, drift and scale | internal QA JSON | pass |
| Seam QA | Real bbox, margin, clipping, holes, gaps and occupancy | seam QA JSON | Q1/Q2 gap preserved |
| Pixel retention | Per-part expected/visible/occluded pixels | retention JSON | Q2 gap preserved |
| Target vs detected | Target and MediaPipe skeleton metadata | pose QA and overlay contact sheet | recorded |
| Runtime boundary | Zero ComfyUI, zero frame segmentation, no walk | execution evidence JSON | pass |
| State consistency | Active state matches checkpoint/review/history | state-consistency JSON | pass |
| Review integrity | Manifest hashes and clean extraction self-test | review manifest/verifier | required |
