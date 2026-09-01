# UGAS v0.9.0 review

## STATUS

Technically qualified locally; external idle-front review is required.

## VERSION

UGAS 0.9.0.

## PHASE

REUSABLE_DETERMINISTIC_ANIMATION_RUNTIME.

## OBJECTIVE

Provide a reusable, deterministic animation runtime with a generic lifecycle and a qualified 12-frame front idle pilot.

## BASELINE / EXTERNAL WALK APPROVAL

Baseline and implementation base: `46ba3ae87558ff26055e14aa8d9c6f3ee147333c`. The recorded decision `FRONT_WALK_V081_PILOT_VISUAL_APPROVED` is limited to pipeline/pilot scope. It is not a production-quality approval.

Historical governance markers remain explicit: `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`, `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`, and `REVIEW_ARCHIVE_VERIFIED` are preserved from prior slices. The active boundary records `production_routing=BLOCKED`, `sam2_runs=0`, `comfyui_generation_jobs=0`, and external approval `not-claimed`.

## IMMUTABILITY

The v0.8.1 code, PNGs, JSON evidence, GIF, and historical review remain unchanged. v0.9.0 records only new attestations and replay references.

## ANIMATION SPEC V1

Specs are `profiles/animation/walk-front-v1.json` and `profiles/animation/idle-front-v1.json`. Frame count is bounded to 2..64, timing has exactly one representation, direction is canonical, and key bindings are hash-bound.

## GENERIC RUNTIME ARCHITECTURE

`python -m ugas.animation validate-spec`, `compile`, `qa`, and `package` are profile-independent lifecycle commands. `src/ugas/animation.py` contains no walk/front/exact-frame-count policy; adapters own profile semantics.

## WALK V081 REPLAY

The generic adapter reproduces all eight canonical v0.8.1 RGBA PNG bytes and the 4x2 spritesheet byte-for-byte. The historical GIF is byte-identical. A negative target-hash mutation produces `ANIMATION_RUNTIME_WALK_REPLAY_GAP`.

## IDLE FRONT SPEC

Idle front is 12 frames at 8 fps, 125 ms per frame, 1.5 seconds, front direction, and a 6x2 512-cell package. I0 through I11 use fixed harmonic skeleton parameters. I11 is distinct from I0 and the target hash set contains 11 distinct targets.

## IDLE FRAME QA

All 12 frames passed source hash binding, target binding, global uniform transform, alpha safe margin, structural holes, layer integrity, occlusion, retention, MediaPipe measurability/PCK/NME/angle gates, source-only pixels, sword attachment, and duplicate-body checks.

## DUAL FOOT PLANT QA

Both feet are measured in every frame against projected source-alpha sole anchors. Sole error, penetration, frame-to-frame sole drift, and ankle horizontal drift remain within the frozen profile limits; there is no swing-foot exemption.

## IDLE TEMPORAL / LOOP QA

The frozen run passed joint delta, angular acceleration, root vertical/horizontal, head step, bbox CV/height variation, sword motion, zero z-order switches, loop boundary, and distinct-target gates.

## PROVENANCE / STRUCTURAL / OCCLUSION

Pixels come only from the R4 source parts and the v0.7.3 source-derived structural core. `sam2_runs=0`, `comfyui_generation_jobs=0`, diffusion runs are zero, recolor/generated-pixel paths are absent, and weights are not tracked.

## VISUAL EVIDENCE

The hash-bound manifest `docs/evidence/review-visuals-v0.9.0.json` records 84 visual roles: 12 canonical transparent frames, 12 checkerboards, 12 target/detected overlays, 12 alpha-bbox overlays, 12 feet-ground overlays, 12 structural maps, plus required sheets and package previews.

## SPRITESHEET / METADATA / GIF

The idle package is RGBA 3072x1024, 6x2 cells, 12 frames, 8 fps, 125 ms, looping. The GIF is review-only; the registry remains pilot/technical-qualified and production routing is BLOCKED.

## GITHUB-FIRST REVIEW INDEX V2

`docs/evidence/review-index-v0.9.0.json` uses `sha256-canonical-path-list-v1`, binds baseline and implementation base separately, excludes itself from its artifact set, and records `index_build_git_head` only as an ancestor build fact. The final HEAD must be resolved by an external reviewer; no old self-referential `head_commit` is used.

## NO SAM2 / NO COMFYUI / NO GENERATION

No SAM2 rerun, ComfyUI generation, diffusion, ControlNet, IP-Adapter, or source-mask mutation was performed for this slice.

## TESTS

Required compileall, unittest discovery, schema negatives, replay negatives, deterministic repeat, foot/z-order/zero-motion/overmotion negatives, package fail-closed, provenance scan, index v2, and historical v0.8.1 regression tests are implemented.

## VALIDATION

The full validation command is `python scripts/validation/run_validation.py`. The final recorded result is required to be all PASS.

## TRACKED SNAPSHOT / GITHUB

GitHub-first publication is on `main`. All v0.9.0 JSON, PNG, and GIF evidence is tracked; no review ZIP is generated.

## SECURITY / LICENSES

No model weights, credentials, or private runtime paths are committed. Existing MIT licensing and third-party provenance records remain authoritative.

## EXTERNAL VISUAL REVIEW STATUS

Walk v0.8.1: `APPROVED_PILOT`. Idle front v1: `REQUIRED`. Production approval: not claimed.

## BLOCKERS / GAPS

External visual review of idle front is pending. Attack, hit, death, additional directions, and production enablement remain outside this slice.

## DECISIONS

The successful idle technical gate is `CUTOUT_ANIMATION_RUNTIME_V1_IDLE_FRONT_TECHNICALLY_QUALIFIED`. Only `external_review_idle_front` is allowed next.

## NEXT STEP

An external reviewer resolves the final Git HEAD and reviews the tracked idle evidence on GitHub.

## DEFINITION OF DONE

Done for v0.9.0 means generic spec/compile/QA/package APIs, identical walk replay, qualified 12-frame idle, hash-bound evidence/index v2, full tests, and GitHub publication. It does not mean production approval.
