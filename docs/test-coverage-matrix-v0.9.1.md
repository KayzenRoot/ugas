# UGAS v0.9.1 test coverage matrix

| Requirement | Evidence | Automated proof | Negative control |
|---|---|---|---|
| Generic QA decision contract | `generic-runtime-contract-v091.json` | `qa_compiled` and `package_compiled` bind animation ID, spec SHA, compiled-manifest SHA, `decision`, hard gates, and `failures` | Arbitrary status qualifies; non-QUALIFIED decision, false gate, and non-empty failures are rejected |
| Alternative timing | `timing-alternative-qualification-v091.json` | Schema and runtime normalize exactly one timing representation | fps-only and duration-only pass; both and neither fail |
| Synthetic two-key profile | `generic-dummy-package-qualification-v091.json` | Fixture compiles, qualifies, and packages through the generic adapter contract | The three fail-closed package mutations are exercised |
| Walk replay integrity | `walk-replay-qualification-v091.json` | Eight RGBA hashes, spritesheet, and GIF match the v0.8.1 canonical outputs | Any changed frame or package hash fails the replay gate |
| Idle canonical replay | `idle-requalification-v091.json` | Twelve target and canonical RGBA hashes remain unchanged across two deterministic runs | New output duplication is prohibited and production routing remains blocked |
| Dual-foot plant QA | `idle-dual-foot-drift-qa-v091.json` | Sole error, penetration, cyclic projected sole drift, and ankle horizontal drift are measured per side | +2 sole error fails; +3 ankle drift fails; +1.5 ankle drift passes |
| Layer bbox temporal QA | `idle-layer-bbox-temporal-qa-v091.json` | Alpha bboxes and area arrays are measured from presented `head` and `torso_pelvis` layers | Head-only and torso-only instability fail independently |
| Idle occlusion policy | `idle-occlusion-policy-v091.json` | Explicit allowed pairs, constant z-order, critical collisions, and unexpected overlap fraction are measured | Forbidden meaningful overlap fails |
| State/governance boundary | `current-state.json`, `state-consistency-v091.json` | Active state is v0.9.1 and stops at external idle review | `production_routing=BLOCKED`, no generation, and external approval `REQUIRED` are enforced |
| Review index v2 | `review-index-v0.9.1.json` | Canonical artifact hashes and historical visual set are validated | No top-level self-asserted `head_commit`; external reviewer resolves final HEAD |

## Commands

```powershell
python -m compileall -q src scripts tests
python -m unittest discover -s tests -q
python scripts/validation/run_animation_runtime_v091.py --json
python scripts/validation/validate_review_index_v091.py
python scripts/validation/run_validation.py
```

No model weights, SAM2 runtime, ComfyUI generation, or diffusion output is part of this slice.
