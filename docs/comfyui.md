# ComfyUI v0.4.3

UGAS targets local ComfyUI `0.34.0` with native nodes only. The verified pilot machine is an NVIDIA RTX 5050 with 8.546 GB reported VRAM and PyTorch `2.13.0+cu130`.

## Lanes

Text-to-image semantics remain unchanged: Distilled uses 4 steps / CFG 1.0 and Base uses 50 steps / CFG 4.0. The image-edit capability has its own Base qualification: the native Comfy-Org Image Edit graph, `ReferenceLatent`, Euler, `Flux2Scheduler`, 20 steps and CFG 5. The 50/4 image-edit graph is retained as a legacy benchmark candidate only. No custom nodes are required.

The qualification record is [reference-edit-workflow-qualification.json](evidence/reference-edit-workflow-qualification.json), with materialized upstream JSON under [evidence/upstream](evidence/upstream). The local API graph is adapted only by replacing explicit public markers (`__MODEL__`, `__IMAGE__`, `__SEED__`, dimensions and prompt); topology and native nodes remain intact.

## Fresh evidence

Every submission uses a unique UGAS job ID as ComfyUI `client_id`. The resulting evidence binds that ID to the exact `prompt_id`, the `history/{prompt_id}` record and each `/view` filename/subfolder/type plus SHA-256. Unique seeds and per-job directories prevent stale output reuse. Runtime is compared with same-machine candidates; an unexplained small fraction is `SUSPICIOUS_EXECUTION_EVIDENCE` and cannot qualify.

## Transparency

BiRefNet is used natively after an RGB edit to produce the alpha matte. UGAS joins the original RGB with the native alpha, validates alpha quality/RGB preservation and keeps the resulting R4 in a new immutable revision. A comparison run uses `promote=False` and cannot create a revision.

Weights stay in the local model directory and are verified against the registry; they are never tracked or included in review packages.
