# UGAS Checkpoint

## STATUS
READY_FOR_EXTERNAL_REVIEW — Prompt 02-C v0.3.1 correction implemented; external approval, visual approval and production approval are not claimed.

## VERSION
0.3.1

## PHASE
Distributable registry, evidence-driven capabilities and 2D QA hardening

## OBJECTIVE
Make the v0.3.0 real 2D MVP reproducible from the public tracked snapshot without falsely qualifying 3D, full animation or transparency.

## SCOPE
Correct model-registry tracking, tracked-snapshot validation, capability-based routing, alpha QA, master-only Sprite Pilot semantics, version consistency, visual review evidence and publication packaging.

## COMPLETED
- `providers/models/registry.json` is explicitly unignored and contains the previously verified NVFP4 hashes, license and qualification evidence; weights remain ignored.
- Provider manifests separate transport from asset qualification; only qualified workflow/model evidence can select an asset provider.
- ComfyUI 2D master capability remains qualified; 3D, material, LOD and full animation remain capability gaps.
- `inspect_png()` preserves source mode and reports alpha/transparency statistics; `requires_transparency=True` fails opaque/RGB output.
- Sprite Pilot accepts only `columns=1` and `rows=1`; grid > 1 fails closed with the documented error.
- Project/runtime/package/docs version surfaces are aligned to `0.3.1`; unchanged schema contracts remain `0.3.0` and are documented.
- Review packaging includes a small real Sprite Pilot preview and corresponding audit JSON without weights, caches or secrets.

## IN PROGRESS
- External audit and human visual review of the real 2D evidence.

## PENDING
- Human visual approval and production approval.
- Optional FP8 qualification.

## BLOCKERS
No known critical/high in-scope blocker remains after the registry tracking, routing, snapshot, version, alpha and Sprite Pilot corrections. The real sample is technically valid but visual approval remains a human gate.

## DECISIONS
- `providers/models/registry.json` is versioned metadata; local model weights are never versioned.
- Transport health or manifest declarations never qualify an asset capability.
- The current ComfyUI workflow qualifies only 2D text-to-image/master sprite output.
- RGB, RGBA opaque and RGBA transparent states are reported separately; non-empty content is not used as a transparency proxy.
- Grid/animation claims require a separately qualified workflow; none exists in v0.3.1.
- Prompt 03, full animation, Blender, 3D, audio and paid providers are not started.

## TEST EVIDENCE
`python -m compileall src scripts tests` passed; unit suite `23/23` passed; repository validation `143/143` passed, including the tracked `git archive HEAD` snapshot, isolated editable install, public CLI commands and controlled unavailable capability. The validation also covers version consistency, model/workflow registry loading, capability routing, 3D/animation gaps, RGB/RGBA alpha cases, 1x1 Sprite Pilot and grid rejection. Real ComfyUI evidence remains in `docs/evidence/comfyui-smoke.json`; visual audit evidence is generated under `__REVIEW__/visual-evidence/` in the final ZIP.

## NEXT STEP
Complete the external/human review gate. No new product slice may start from this checkpoint without separate authorization.

## DEFINITION OF DONE
Registry is tracked in GitHub and the review ZIP; the public tracked snapshot installs and validates; qualified routing is evidence-driven; alpha/transparency and Sprite Pilot semantics are honest; versions agree; all required tests pass; GitHub and the final self-validating review ZIP are published; no critical/high in-scope finding remains.

## BACKLOG
Future authorized work only: qualified reference-edit, full animation/grid workflows, 3D/Blender, audio or additional providers.
