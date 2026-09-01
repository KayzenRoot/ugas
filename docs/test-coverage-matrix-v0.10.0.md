# UGAS v0.10.0 test coverage matrix

| Requirement | Evidence | Automated proof | Negative control |
|---|---|---|---|
| Optional generic event markers | `generic-event-marker-contract-v0100.json` | load, canonical order, marker hash, and propagation through manifest/QA/package | Duplicate ID, out-of-range frame, and non-canonical order reject |
| Loop/non-loop lifecycle | `non-loop-runtime-contract-v0100.json` | Generic helper evaluates closing edge only for loops and requires non-loop final validity | Invalid non-loop final frame produces a lifecycle gap |
| Attack scope and frozen timeline | `attack-front-v1/compiled-manifest.json`, `attack-event-marker-qa-v0100.json` | 10 front frames, 12 fps, non-loop, exact A0–A9 phases and markers | Wrong marker/timeline or duplicate target hash fails |
| Source-only provenance | `execution-evidence-v0.10.0.json` | R4 SHA, source-only pixels, zero generation counts | SAM2/ComfyUI/diffusion/new-generation fields are hard-bound to zero |
| Temporal pose bounds | `attack-temporal-qa-v0100.json` | Angle delta, angular acceleration, root, head, target-hash and lifecycle gates | Any threshold failure enters `ATTACK_FRONT_POSE_GAP` |
| Weapon sweep and hit | `attack-weapon-sweep-qa-v0100.json` | Pivot, active window 3–6, hit frame 5, tip path, peak motion and collision gates | Sword/head critical and sword/torso forbidden penetrations fail |
| Sequential foot grounding | `attack-foot-ground-qa-v0100.json` | Both feet, sole/penetration, A0→A1 through A8→A9, no closing pair | Positive slide fixture is rejected by sequential drift gate |
| Structural and occlusion integrity | Per-frame QA and structural records | Structural coverage, seams, retention, constant z-order and measured pairwise policy | Unexpected/critical overlap remains a hard failure |
| Independent pose estimator | Per-frame target/detected overlays in `attack-visual-manifest-v0100.json` | MediaPipe measurable joints, PCK, NME, limb MAE, front orientation | Estimator or visual gap is reported; thresholds are not relaxed |
| Package contract | `package-manifest.json`, `metadata.json` | Decision, hard-gate and failure-list checks; 5×2 RGBA package | Failed decision, false gate, hash mismatch, or non-empty failures block package |
| State and publication boundary | `current-state.json`, `state-consistency-v0100.json`, review index | Attack technical gate, historical pilot decisions, production block and exact baseline | External attack review remains required; no self-asserted final HEAD |
