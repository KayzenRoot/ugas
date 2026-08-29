# UGAS Prompt 02 v0.3.0 Review

## STATUS
READY_FOR_REVIEW. Real local 2D MVP is validated; external approval, human visual approval and production approval are not claimed.

## VERSION
0.3.0

## PHASE
Real 2D ComfyUI / RTX 5050 MVP foundation

## OBJECTIVE
Execute a structured 2D asset request through a qualified local ComfyUI workflow, retrieve PNG output, perform technical QA, record provenance and register the result without secrets or weights in Git.

## SCOPE
ComfyUI HTTP client, evidence-gated routing, native workflow/model registries, Windows/NVIDIA render-node tooling, durable image jobs, PNG/sprite pilot processing, consumer runtime, tests, docs and safe GitHub review packaging.

## COMPLETED
- v0.2.1 baseline preserved: 38 skills, bounded context, profiles, bootstrap and non-destructive refresh.
- HTTP client covers health/features/model and node inventory, prompt submission, queue/history, output retrieval and upload.
- Capability states, exact model/workflow records, hash/license gates, durable job states, technical PNG QA, provenance and duplicate-aware registry added.
- CLI and consumer runtime are self-contained and independent of the original checkout path.
- Clone-directory documentation regression fixed.
- Official ComfyUI `0.34.0` installed outside the repository with `comfy-cli 1.19.0` and CUDA PyTorch.
- RTX 5050 smoke passed at 256x256; PNG retrieved and technical QA passed.

## NOT COMPLETED
- Human visual approval and production approval remain pending.
- Reference-edit, full animation, 3D/Blender, audio, cloud/paid providers and later prompts are explicitly not started.
- Human visual approval and production approval are not automatic.

## FILES CREATED/CHANGED
See Git metadata in the review ZIP. Main additions are `src/ugas/comfyui_client.py`, `capabilities.py`, `model_registry.py`, `workflow_registry.py`, `jobs.py`, `image_utils.py`, `qa.py`, `provenance.py`, `asset_registry.py`, `generation.py`, `render_node.py`, new v0.3 schemas, model/workflow registries, CLI, docs, tests and checkpoints.

## ARCHITECTURE DECISIONS
Native ComfyUI nodes only; no arbitrary custom-node installation. Local/private endpoints only by default. A manifest or generic health response never proves a capability. Weights and generated outputs stay outside Git. Technical validity, visual review and production readiness are separate states.

## COMFYUI CLIENT
Implemented and fake-server tested for `/system_stats`, `/features`, `/models`, `/models/{folder}`, `/object_info`, `POST /prompt`, `GET /prompt`, `/history/{id}`, `/view` and structured error paths. Polling is bounded with backoff and output responses have size limits.

## RENDER NODE
`ugas render-node doctor/setup/start/stop/status/probe` implemented. Configuration/workspace default to `%LOCALAPPDATA%\\UGAS`; default bind is `127.0.0.1`. Official `comfy-cli` help was inspected before version-sensitive install flags.

## GPU/HARDWARE EVIDENCE
Windows build `10.0.26200.0`, Python `3.12.10`, NVIDIA GeForce RTX 5050, driver `610.74`, 8,151 MB total and 3,364 MB free at preflight. ComfyUI runtime evidence reports version `0.34.0`, PyTorch `2.13.0+cu130`, 8,546,484,224 bytes total VRAM and 7,413,432,320 bytes free before smoke. `nvidia-smi` was available.

## MODELS QUALIFIED
`flux2-klein-4b-nvfp4` qualified with Apache-2.0, exact files and SHA-256: diffusion `F66FAE...F381AB`, encoder `3EAB03...9206CA8`, VAE `D64F3A...F9C4B5`. The FP8 candidate remains `candidate` pending its own download/hash/smoke.

## WORKFLOWS QUALIFIED
`flux2-klein-4b-text-to-image` qualified: native API graph, 12 required node classes present, live-valid against `/object_info`, smoke passed; workflow hash `c7f56d...14174dd`.

## SPRITE PILOT
Master-image path and deterministic grid crop/compose/metadata utilities are implemented. Real job `job-7ee864bb798b4a03a2d6568575ef4399` produced a 256x256 RGBA master (`e0a5914259efa17e57890e985b4f67e154bf915f4ff04ab2f39514fc4b864b9a`) and 1x1 sheet (`a9cc794a2f9480e138f5d4787e3eadd9500e4f75e1b7ead28d30fd43b59e73d6`). Technical output status is `TECHNICAL_VALID` with `VISUAL_REVIEW_REQUIRED`; no production-ready claim is emitted. Evidence: `docs/evidence/sprite-pilot.json`.

## CAPABILITY EVIDENCE
States are `unknown`, `unavailable`, `declared`, `ready`, `verified`. Declared is explicitly not selected for a real job. The pre-smoke evidence was `ready`; after the passed smoke it is `verified` in `docs/evidence/comfyui-smoke.json`.

## TESTS AND RESULTS
Baseline before v0.3: 13/13 tests and 104/104 validation checks. Current automated suite: 18 tests passed; current repository validation: 120 checks passed. Fake-server submit -> history -> view PNG, fresh consumer runtime, Unicode-safe Windows probe and real RTX 5050 smoke pass.

## SECURITY / LICENSE CHECKS
No secrets are stored. Review ZIP excludes weights, generated large artifacts, caches, private config and credentials. The qualified NVFP4 model is Apache-2.0 with exact hashes. Remote endpoints require private networking.

## CONSUMER INSTALLATION TEST
Passed in a temporary fresh consumer: installer copied `.game-assets/tools/ugas_runtime.py` and package; invoking the copied runtime from a different working directory returned `0.3.0` without the source checkout on `PYTHONPATH`.

## GIT / GITHUB
Repository: https://github.com/csn1985-ship-it/ugas.git. Baseline branch was `main` at `8935818`; this review is prepared for the final v0.3 commit/push, with the resulting HEAD recorded by Git and the handoff.

## PENDING
Human visual review, production approval and optional FP8 qualification. GitHub publication and the safe review ZIP are finalization actions covered by this handoff.

## BLOCKERS
The first `comfy-cli install` failed because its generated uv override path split the repository path containing spaces. An explicit official ComfyUI checkout and no-space install invocation resolved it. No current in-scope runtime blocker remains; visual approval is intentionally a human gate.

## CHECKPOINT UPDATED
`CHECKPOINT.md` is the source-of-truth progress record and is updated with each gate.

## NEXT STEP
Finalize publication by committing/pushing the reviewed source, then generate the safe review ZIP as the last filesystem action and hand off its path.

## DEFINITION OF DONE
Authorized source/docs/tests/manifests implemented; fake and repository validations green; real hardware outcome honest; no critical/high in-scope findings; GitHub pushed if authenticated; safe fresh ZIP generated last.

## REVIEW ZIP PATH
Generated during finalization; the exact absolute path is returned in the handoff.
