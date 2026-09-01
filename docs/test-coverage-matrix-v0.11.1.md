# UGAS v0.11.1 test coverage matrix

| Area | Evidence / test | Gate |
|---|---|---|
| Generic motion curves | `generic-motion-curve-regression-v0111.json`, `tests/test_motion_curves_v0110.py` | Positive and negative contract controls pass; `motion_curves.py` unchanged |
| Weapon pre-render | `weapon-continuity-pre-render-v0111.json`, `tests/test_weapon_continuity_v0111.py` | Follow path, ratio, retention, acceleration, reversal and V11 recovery bounds pass |
| Weapon post-render | `weapon-continuity-post-render-v0111.json`, `attack-v2-weapon-arc-qa-v0111.json` | Same metrics agree within `0.001`; collision, clipping, alpha and provenance gates pass |
| Negative controls | `execution-evidence-v0.11.1.json` | All required false-green regressions reject; near-ready control passes |
| Temporal / lifecycle | `attack-v2-temporal-qa-v0111.json` | 12 sequential non-loop frames and frozen markers pass |
| Body mechanics | `attack-v2-body-mechanics-qa-v0111.json` | Root, torso, arm, counter-motion and head mechanics pass |
| Feet / balance | `attack-v2-foot-ground-qa-v0111.json` | Sole, penetration, drift and support corridor pass |
| Structural / pose | `qa-result.json`, visual manifest and overlays | Integrity, occlusion, seam, retention, MediaPipe and source-only gates pass |
| Historical replay | `historical-replay-v0111.json` | v0.10.0 attack-v1, v0.8.1 walk and v0.9.0 idle preserved |
| Governance | current state, schema, state validator, review index | External review required; production blocked; no generation |

The package is pilot-only. Local technical qualification is not external visual approval.
