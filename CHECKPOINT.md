# UGAS Checkpoint

## STATUS
READY_FOR_REVIEW — Prompt 02 v0.3.0 real 2D MVP locally validated. External approval and visual/production approval are not claimed.

## VERSION
0.3.0

## PHASE
Real 2D ComfyUI / RTX 5050 MVP foundation

## OBJECTIVE
Provide a testable, evidence-gated path from a structured 2D asset request to a retrieved PNG, technical QA, provenance and consumer registry entry.

## SCOPE
ComfyUI client, native workflow/model registries, capability evidence, Windows/NVIDIA render-node tooling, durable jobs, image/sprite utilities, consumer runtime, tests and review package.

## COMPLETED
- v0.2.1 baseline retained: 38 skills, consumer bootstrap, profiles and routing.
- v0.3 schemas, ComfyUI HTTP client, registries, evidence model, job state machine, PNG QA and provenance modules added.
- CLI commands and isolated consumer runtime added.
- Clone-directory documentation regression corrected.
- Official ComfyUI `v0.34.0` installed outside the repo with `comfy-cli 1.19.0` and CUDA PyTorch.
- RTX 5050 smoke passed using NVFP4 FLUX.2 Klein at 256x256; PNG retrieved, hashed and technically validated.

## IN PROGRESS
- Human visual review and external review handoff.

## PENDING
- Human visual review and production approval.
- Optional FP8 qualification.

## BLOCKERS
Historical setup attempt hit the comfy-cli path-with-spaces bug; the explicit official checkout plus no-space install invocation succeeded. The machine has an RTX 5050 and the real smoke passed.

## DECISIONS
- No arbitrary custom nodes; native ComfyUI nodes only.
- Apache-2.0 approved model candidates only; weights stay outside Git.
- `ready` requires server, nodes, exact model inventory, workflow and license; `verified` additionally requires smoke success.
- Reference-edit, full animation, 3D, audio, cloud and paid paths remain out of scope.

## TEST EVIDENCE
Baseline before v0.3 work: 13/13 unit tests and 104/104 validation checks passed. Current: 18/18 unit tests and 120/120 validation checks passed; real smoke and Sprite Pilot evidence are recorded in `docs/evidence/`.

## NEXT STEP
Finalize publication by committing/pushing source and evidence, then generate the fresh review ZIP as the final filesystem action.

## DEFINITION OF DONE
All authorized source/docs/tests/manifests are implemented; fake-server and local validation are green; real hardware outcome is recorded honestly; no critical/high in-scope findings remain; GitHub is pushed if authenticated; a fresh safe review ZIP exists.

## BACKLOG
Later prompt: qualified reference-edit, animation/3D/audio/cloud work only with separate authorization.
