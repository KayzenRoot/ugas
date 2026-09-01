# UGAS review v0.9.1

## STATUS

`TECHNICALLY_QUALIFIED_LOCALLY`; external idle visual review is still `REQUIRED`. Production remains `BLOCKED`.

## VERSION

UGAS v0.9.1, generic reusable deterministic animation runtime QA integrity correction.

## PHASE

`REUSABLE_DETERMINISTIC_ANIMATION_RUNTIME`.

## OBJECTIVE

Correct the v0.9.0 generic runtime contract and requalify only the existing front walk replay and front idle pilot without changing the R4 rig, masks, canonical pixels, animation scope, or provider lane.

## V0.9.0 EXTERNAL AUDIT FINDINGS

The correction addresses five findings: generic package qualification was coupled to profile status; timing did not enforce one representation; dual-foot QA omitted cyclic projected sole and ankle drift; temporal bbox QA did not independently measure presented head and torso layers; and occlusion relied on a literal hard-gate assignment instead of measured policy.

## BASELINE IMMUTABILITY

The implementation base is `16c60c9ff934a55adefc82a99d81dafb52d1047c`; the parent baseline is `46ba3ae87558ff26055e14aa8d9c6f3ee147333c`. The R4 identity, eleven-part rig, masks, targets, walk frames, idle target hashes, and source-only pixel policy remain hash-bound. The review index records these commits separately.

Historical governance remains visible and immutable: `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`, `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`, and `REVIEW_ARCHIVE_VERIFIED` are prior recorded states, not new work in this slice.

## GENERIC QA DECISION CONTRACT

`package_compiled` accepts only a schema-valid QA result with matching animation ID, spec SHA, and compiled-manifest SHA; `decision=QUALIFIED`; every hard gate literally true; and `failures=[]`. Profile-specific `status` is preserved as descriptive metadata and is not an allowlist. The synthetic fixture proves qualification with `SYNTHETIC_FIXTURE_TECHNICALLY_OK`.

## GENERIC PACKAGE LIFECYCLE

The lifecycle is validate spec → compile manifest → adapter QA → generic hash-bound QA result → package. A package is not created when decision, a hard gate, or the failure list is invalid. The package carries `qa_decision=QUALIFIED` and remains pilot-only.

## TIMING ALTERNATIVE SCHEMA

Animation specs require exactly one positive `fps` or positive `per_frame_duration_ms`. fps-only and duration-only fixtures are valid and normalize internally to both runtime values; both-present and neither-present fixtures fail closed. The source spec is not mutated during normalization.

## GENERIC DUMMY PROFILE PROOF

The nonproduction two-key fixture compiles and packages through the same public generic contract as the production profiles. Its arbitrary status is accepted because the decision is `QUALIFIED`. Mutants with a failed decision, false hard gate, or non-empty failures are rejected before package creation.

## WALK V081 REPLAY REGRESSION

The eight v0.8.1 front-walk RGBA frames replay byte-identically. The canonical spritesheet SHA-256 is `58da93252731e10622fbd3966158ef11411e4e307f6b066979c60c7c8acd0f1a`; the canonical GIF SHA-256 is `3f83604c9c1c152e36eced14d906c705e153da9f59627df0175ca6905e0aa87b`. Both remain `BYTE_IDENTICAL`.

## IDLE CANONICAL REPLAY

The twelve idle frames replay deterministically twice. Target hashes and canonical RGBA hashes are unchanged from v0.9.0. The package layout remains 6x2; no duplicate canonical PNG set is generated.

## DUAL-FOOT DRIFT QA

Each side measures sole error, ground penetration, cyclic frame-to-frame projected sole drift, and ankle horizontal drift from baseline. All twelve cyclic pairs are present, including I11→I0. The negative controls prove +2 sole error fails, +3 ankle drift fails, and +1.5 ankle drift passes.

## HEAD / TORSO LAYER BBOX QA

The head bbox and area arrays are measured from the presented `head` layer; torso bbox and area arrays are measured from `torso_pelvis`. Each has twelve samples and its own coefficient-of-variation gate. Composite foreground height remains a separate metric. Head-only and torso-only negative controls fail independently.

## IDLE OCCLUSION POLICY

The policy measures explicit allowed pairs, constant z-order, critical collisions, unexpected overlap fraction, and meaningful forbidden overlap. The idle plan contains explicit allowed pair keys; no literal unconditional `pair["hard_gates"]["no_meaningful_outside_authorized_overlap"] = True` override remains. A forbidden overlap fixture fails.

## IDLE REQUALIFICATION

The idle adapter returns `decision=QUALIFIED`, all frame and temporal hard gates pass, and the package QA decision is `QUALIFIED`. The idle technical gate is not an external visual approval.

## REVIEW INDEX V2

`docs/evidence/review-index-v0.9.1.json` is a canonical SHA-256 path-list index. It includes the mandatory v0.9.1 JSON evidence and the historical v0.9.0 visual source set. It has no top-level `head_commit`; `index_build_git_head` is the build provenance, while final HEAD resolution belongs to the external reviewer. `executor_cannot_self_assert_final_head=true`.

## NO SAM2 / NO COMFYUI / NO GENERATION

This correction performs no SAM2 run, ComfyUI generation, diffusion run, or new-generation job: `sam2_runs=0`, `comfyui_generation_jobs=0`, `diffusion_runs=0`, `new_generation=0`. Existing source-only outputs are replayed and measured.

## TESTS

The focused v0.9.1 contract suite covers generic status independence, timing alternatives, fail-closed package mutations, dual-foot negative controls, and independent head/torso bbox controls. The complete command is `python -m unittest discover -s tests -q`.

## VALIDATION

Required validation is compileall, the complete unittest suite, the v0.9.1 runtime runner, the v0.9.1 review-index validator, and the full historical-plus-active `run_validation.py` gate. Counts are recorded in the review index after the final clean validation.

## TRACKED SNAPSHOT / GITHUB

The target branch is `main` in `https://github.com/csn1985-ship-it/ugas.git`. Source, schemas, tests, evidence, review, and validators are tracked; weights and review ZIPs are excluded. Publication is verified by matching local `HEAD` and `origin/main`; remote CI status is not inferred from local evidence.

## EXTERNAL VISUAL REVIEW STATUS

The v0.8.1 walk pilot remains `APPROVED_PILOT`. Idle front remains `REQUIRED` and `not-claimed`. No local technical result is represented as external idle approval.

## BLOCKERS / GAPS

The remaining blocker is external visual review of the idle front pilot. Production routing is `BLOCKED`. No new animation, direction, generation provider, SAM2 run, ComfyUI job, or diffusion lane is authorized by this correction.

## DECISIONS

Use a generic `decision=QUALIFIED` package gate; preserve profile status; require one timing representation; measure both feet and presented layer bboxes independently; use measured occlusion policy; preserve canonical replay hashes; and keep external final HEAD resolution separate from the executor's build provenance.

## NEXT STEP

The only allowed next action is `external_review_idle_front`.

## DEFINITION OF DONE

Done locally when all v0.9.1 tests, runtime evidence, schema checks, full validation, and review-index hash checks pass, with main published at the resulting commit. The phase is complete for external handoff, not for production: idle external review is still `REQUIRED`, `production_routing=BLOCKED`, and final HEAD must be resolved by the external reviewer.
