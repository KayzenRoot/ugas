# UGAS v0.6.2 test coverage matrix

This matrix is the implementation and acceptance map for `PROMPT-05D-UGAS-SDXL-OPENPOSE-MODEL-CARD-CALIBRATION-v0.6.2`. Historical v0.6.1 evidence remains immutable; the active slice is P-only.

| Area | Required proof | Automated coverage | Runtime evidence |
|---|---|---|---|
| Version and state | `0.6.2`, phase, current gate, historical v0.6.1 status | `test_state_consistency_v052.py`, `run_validation.py` | `docs/evidence/current-state.json`, `state-consistency.json` |
| Model-card operating point | Base SDXL + xinsir OpenPose only; Apache-2.0 source; no downloads | `test_sdxl_openpose_calibration_v062.py` | `sdxl-openpose-config-matrix.json` |
| Live scheduler mapping | `object_info` observes `euler_ancestral` and `normal` | calibration test and validator | matrix `scheduler_mapping` and object-info hash |
| Exact matrix | P0 512/20/euler/normal/0.9; P1 768/30/euler_ancestral/normal/1.0; P2 1024/30/euler_ancestral/normal/1.0 | calibration unit tests | matrix and runtime table |
| Guide fidelity | COCO-18 JSON rendered directly at 512/768/1024; no raster upscale | guide renderer tests | three guide PNGs, JSON/renderer/PNG hashes |
| P-only boundary | no IP-Adapter, I, PI, identity R4, benchmark, anchors, walk or new provider | graph and evidence boundary tests | qualification and execution evidence |
| Fresh execution | seed 62701, exact history/prompt/raw SHA, fresh target | execution evidence tests | raw P0/P1/P2 records and overlays |
| P2 memory policy | at most one supported `/free` retry; parameters unchanged; hardware gap is explicit after repeated OOM | retry-policy tests | runtime table and P2 attempts |
| Raw pose gate | frozen v0.5.4 thresholds, before BiRefNet | pose qualification tests | per-output metrics and overlays |
| Human-form technical gate | one primary human, MediaPipe detectability, no frame/stencil auto-approval | human-form contract tests | per-output QA and visual-review flag |
| Conditional confirmation | only after Stage A pass; seeds 62711/62712/62713; otherwise NOT_RUN | confirmation policy tests | qualification and execution evidence |
| Historical integrity | v0.6.1 152-test audit, v0.6.0 and v0.5.5 evidence preserved | historical validation checks | preserved review files and manifests |
| Publication | compileall, unit tests, validation, archive self-test, clean main and origin parity | `run_validation.py`, archive verifier | final review ZIP and SHA-256 |

Acceptance remains fail-closed: technical qualification does not grant production or external approval, and human visual review remains separate from automated pose metrics.
