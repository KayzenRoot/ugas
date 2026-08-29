# UGAS Prompt 02-C v0.3.1 Review

## STATUS
READY_FOR_EXTERNAL_REVIEW. The stabilization correction is implemented for public-snapshot review. Human visual approval and production approval are not claimed.

## VERSION
0.3.1

## PHASE
Distributable registry, evidence-driven capabilities and 2D QA hardening

## OBJECTIVE
Make the real v0.3.0 2D MVP reproducible from a public tracked snapshot and remove false claims about provider capabilities, alpha transparency and sprite grids.

## SCOPE
`.gitignore`/registry tracking, public snapshot validation, provider capability separation, routing regressions, alpha QA, master-only Sprite Pilot, version consistency, real visual evidence and review packaging. Prompt 03 and new product capabilities are excluded.

## AUDIT FINDINGS ADDRESSED
- A / critical: `providers/models/registry.json` is explicitly unignored and tracked; the exact previously verified NVFP4 hashes and license remain unchanged.
- B / high: static manifests now describe transport only; asset selection requires qualified capability evidence. 3D, material, LOD and full animation are not qualified.
- C / high: validation now exercises an exact `git archive HEAD` tracked snapshot with isolated install, CLI, tests and validation.
- D / medium: project/runtime/package/docs version surfaces are aligned to `0.3.1`; unchanged contract schemas intentionally remain `0.3.0`.
- E / medium: PNG QA preserves source mode and distinguishes alpha channel, transparent pixels, alpha bounds and content.
- F / medium: Sprite Pilot is master-only; any grid greater than 1 fails closed with `sprite-grid workflow not qualified in v0.3.1`.

## MODEL REGISTRY TRACKING
The registry contains `flux2-klein-4b-nvfp4` as `qualified` only with the original exact SHA-256 values, Apache-2.0 approval and smoke evidence. `flux2-klein-4b-fp8` remains `candidate` because its hashes and smoke are not complete. No model weight is tracked.

## FRESH CLONE / TRACKED SNAPSHOT TEST
`scripts/validation/run_validation.py` creates an exact `git archive HEAD`, extracts it to a temporary directory, creates an isolated Python environment, runs editable installation, `ugas --version`, `ugas models list`, `ugas workflows list`, unit tests and nested validation. It also verifies a controlled unavailable capability response when ComfyUI is absent. The validation explicitly checks tracked model/workflow registries and a tracked native API workflow JSON.

## PROVIDER CAPABILITY MODEL
Routing separates transport capabilities, declared asset capabilities and qualified asset capabilities. Health, availability and manifests cannot qualify an asset pipeline. The current local ComfyUI evidence qualifies `2d`, `sprite-master` and `sprite-generation` for the native FLUX.2 Klein workflow. Remote Render Node requires its own remote workflow evidence; Hugging Face hosted inference remains disabled.

## ROUTING TESTS
Covered cases include a qualified 2D master selecting ComfyUI, an unqualified 2D request returning a capability gap, final 3D model/material/LOD returning a capability gap, full 8-frame animation returning a gap, and an MMORPG request exposing qualified partial coverage plus animation gap rather than selecting one provider for the whole request.

## ALPHA / TRANSPARENCY QA
`inspect_png()` records `source_mode`, `has_alpha_channel`, `has_transparent_pixels`, `alpha_min`, `alpha_max`, `opaque_fraction`, `transparent_fraction` and `non_empty_content`. RGB cannot claim transparency; RGBA opaque has an alpha channel but no transparent pixels; RGBA with any alpha below 255 has real transparency. `validate_output(..., requires_transparency=True)` fails closed when transparency is absent.

## SPRITE PILOT SEMANTICS
The real pilot remains a 1x1 master-image path. `columns=1, rows=1` is accepted and produces metadata; `columns * rows > 1` is rejected before generation because no qualified sprite-grid/animation workflow exists.

## VERSION CONSISTENCY
`pyproject.toml`, `package.json`, `src/ugas/constants.py`, `src/ugas/__init__.py`, CLI help, README, INSTALL, CHECKPOINT and this review use `0.3.1`. Existing profile/skill/schema instances retain `0.2.1`/`0.3.0` where those contracts were not changed; this distinction is documented.

## TESTS AND RESULTS
The prior v0.3.0 baseline was 18/18 unit tests and 120/120 repository checks. Final v0.3.1 validation is `23/23` unit tests and `143/143` repository checks. It includes an exact tracked `git archive HEAD` snapshot with isolated editable install, public CLI commands and controlled unavailable capability, plus regressions for the six audit findings, version consistency, tracked registries, qualified routing, 3D/animation gaps, RGB/RGBA alpha cases, transparency requirements, 1x1 Sprite Pilot and grid rejection. `python -m compileall src scripts tests` also passed.

## VISUAL EVIDENCE
The final review ZIP includes `__REVIEW__/visual-evidence/sprite-pilot-preview.png` copied from the real pilot master and `__REVIEW__/visual-evidence/sprite-pilot.json`. The source is 256x256 PNG, SHA-256 `e0a5914259efa17e57890e985b4f67e154bf915f4ff04ab2f39514fc4b864b9a`, source mode `RGB`, with no alpha channel and no transparent pixels. Visual approval is `pending`; the evidence is never marked production-ready.

## SECURITY / LICENSE
Weights, outputs, caches, credentials, `.env` files and private configuration remain excluded. The qualified NVFP4 model is recorded as Apache-2.0 with exact hashes. The review generator validates forbidden paths and the visual evidence is a small audit copy only.

## GIT / GITHUB
Repository: https://github.com/csn1985-ship-it/ugas.git. The correction is prepared for the current `main` flow; the final handoff records the resulting commit and remote ref. The registry must be present in both `git ls-files` and the remote commit.

## FILES CHANGED
`.gitignore`, `package.json`, version/docs/checkpoints, provider manifests, capability/router code, alpha QA, generation/Sprite Pilot guard, validation/tests and the review ZIP generator. Existing v0.3.0 review remains historical.

## PENDING
Human visual review, production approval and optional FP8 qualification. Prompt 03 and all excluded product capabilities remain not started.

## BLOCKERS
No known critical/high in-scope blocker remains if the final tracked-snapshot, remote-tracking and review-ZIP checks pass. The sample's visual approval is intentionally a human gate.

## CHECKPOINT UPDATED
`CHECKPOINT.md` contains the v0.3.1 source-of-truth status, decisions, evidence expectations and explicit no-Prompt-03 boundary.

## NEXT STEP
Run the final tracked-snapshot validation, commit/push the correction, rerun validation from the public commit, and create the self-validating review ZIP as the final filesystem action.

## DEFINITION OF DONE
The model registry is in Git/ZIP/GitHub; the tracked snapshot installs and passes; routing is evidence-driven; 3D/full animation are gaps; alpha QA is truthful; Sprite Pilot cannot fake a grid; versions agree; all regressions pass; GitHub is updated; the final ZIP validates itself; no critical/high in-scope finding remains.

## REVIEW ZIP PATH
Generated during finalization; the exact absolute path is returned in the handoff.
