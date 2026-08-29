# UGAS v0.2.1 Correction Review

## STATUS

`IN_PROGRESS` — implementation and local validation are complete; final Git commit and publication verification remain open.

## VERSAO

`0.2.1` — `PROMPT-01C-UGAS-CORRECAO-v0.2.1.pdf`.

## FASE

Correction/stabilization of the v0.2 bootstrap foundation. Prompt 02, real generation, model downloads, Blender, and production jobs were not started.

## OBJETIVO

Make the existing UGAS bootstrap truthful, bounded, schema-valid, capability-aware, installable as complete Agent Skills, and safe to refresh.

## ESCOPO

Agent Skills compliance; complete installation; context/profile resolution; schemas/templates/instances; provider availability/capability routing; local/remote probes; regressions; documentation; review evidence; Git and publication readiness.

## PROBLEMAS CORRIGIDOS

- Added valid frontmatter with exact folder-matching names to all 38 skills.
- Changed skill installation default from a six-skill subset to the complete 38-skill set, with explicit `full`, `core`, and `profile` modes.
- Added bounded discovery that skips heavy/generated directories and records counts instead of serializing unbounded paths.
- Corrected Unity detection to root `ProjectSettings/ProjectVersion.txt`; Godot remains dimension `unknown` without evidence.
- Added evidence-backed profile recommendation and explicit `profile-pending` behavior.
- Aligned profile schema, ten profile instances, and the complete profile template on schema version `0.2.1`.
- Added provider cost classes, capability filtering, unknown availability, 3D final-model requirements, and self-hosted remote eligibility under `paid-disabled`.
- Separated local GPU, local ComfyUI, and remote Render Node probes.
- Made `--force` refresh preserve registry, provenance history, references, manifests, and checkpoint.

## ARQUIVOS ALTERADOS

The correction touched the runtime, installer/validation scripts, 38 `skills/*/SKILL.md` files, profiles/templates/schemas/manifests, examples, tests, documentation, and this review. `create_review_zip.py` and `review/` remain local ignored review tooling/artifacts from the separate review-zip prompt.

## SKILLS VALIDATED

38/38 skills validated by `src/ugas/skills.py` for initial YAML frontmatter, exact folder/name match, rich description, MIT license field, UGAS version metadata, trigger/non-use/limits sections, and absence of `disable-model-invocation`. `skills-ref` was not installed; the internal dependency-free validator was used.

## INSTALLATION TEST

`python scripts/bootstrap/install_skills.py <temp-consumer>` — exit `0`, installed `38/38` skills by default. Consumer bootstrap smoke test — exit `0`; all `CONSUMER_FILES` were created. Profile output includes `profile_recommendation`, `profile_confidence`, and `profile_evidence`.

## ENGINE DETECTION TESTS

Synthetic fixtures passed for Unity (`Assets/` + root `ProjectSettings/ProjectVersion.txt`), Godot (`project.godot`, dimension remains `unknown`), Unreal (`*.uproject`), and PixiJS (`package.json`). Heavy directories were skipped and bounded scan counts were recorded.

## SCHEMA VALIDATION

The dependency-free Draft 2020-12 subset validator checked all 10 schema documents, all 10 profiles, the complete profile template, provider manifests, workflow manifests, and generated consumer instances. `jsonschema` was not required for the runtime.

## PROVIDER ROUTING TESTS

Validated: no probe yields `unknown` and no selection; 2D requests require 2D-compatible capabilities; final 3D model requests require `3d-model`; 3D requests do not silently fall back to a 2D-only provider; capability gaps are explicit; `paid-disabled` excludes only `paid` and keeps `self-hosted` Render Node eligible.

## SAFE REFRESH TEST

The `--force` installer regression preserved a user registry entry, a provenance history line, an existing reference, an existing manifest, and the checkpoint while appending a refresh provenance event.

## COMFYUI/RENDER NODE CONTRACT

Local ComfyUI uses local `/system_stats`; local GPU detection is a separate local-only `nvidia-smi` probe. The remote Render Node uses a separate configured remote `/system_stats` endpoint and never runs local GPU detection for the remote machine. No credential, model, or real job was used.

## TESTES E RESULTADOS

- `python scripts/tests/run_tests.py` — exit `0`, `13` tests passed.
- `python scripts/validation/run_validation.py` — exit `0`, `104` checks passed with no failures.
- `python -m compileall -q src scripts tests` — required final check.
- Secret scan over tracked text — required final check; no credentials may be committed.

## GIT STATUS

Final status and commit hash must be recorded after the last tracked-file change. The separate review-zip tool's local `create_review_zip.py` and `review/` outputs are ignored; no generated archive is part of the source commit.

## GITHUB/PUBLICACAO

Target supplied by the user: `https://github.com/csn1985-ship-it/ugas.git`. Publication is only marked complete after remote verification and a successful push. If authentication or network access blocks that operation, the exact state is `BLOQUEADO_PUBLICACAO` with the commands required to finish it.

## PENDENCIAS

External provider uptime, model/license approval, visual quality, engine runtime imports, real ComfyUI jobs, and external GitHub review are not proven by this bootstrap correction.

## BLOQUEIOS

No local implementation blocker is known. GitHub publication remains conditional on remote authentication and network access at final verification.

## RISCOS

Profile recommendation is evidence-based but not human approval. Provider manifests declare capability; they do not prove service availability. A remote endpoint must remain private and consumer-local.

## PROXIMO PASSO

Review the final tracked diff, commit the v0.2.1 correction, verify `origin`, and push `main` if authenticated. Stop here before any later prompt or real asset generation.

## DEFINITION OF DONE

Done when all 38 skills, install modes, bounded context/profile behavior, schemas/templates/instances, capability-aware routing, separated probes, safe refresh, tests, docs, final review, clean committed Git state, and GitHub publication state are objectively evidenced. Prompt 02 and real generation remain not started.
