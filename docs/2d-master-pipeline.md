# 2D master pipeline v0.4.2

The master specification keeps canvas, occupancy, declared margins, pivot, QA thresholds and provenance machine-readable. The generation prompt stays visual: full body, neutral stance, readable anatomy, separated arms, weapon beside the body and simple background.

Base and Distilled are not interchangeable: Distilled uses 4 steps/guidance 1.0; Base uses 50 steps/guidance 4.0. Compatibility is checked before `/prompt`.

Candidate selection applies hard gates before ranking. `edge_clipping` means contact with the canvas edge; `safe_margin_ok` consumes the spec margins and is independently required. A failed candidate is never promoted, and automatic corrective retries are bounded at two rounds.

## Immutable revision chain

The selected RGB master is R1. Background removal creates R2 in a new revision directory, storing its RGBA output, mask, checkerboard and metadata together. A reference edit creates R3 in another directory; the next background removal creates R4 without mutating R2 or R3. Every revision records `output_sha256` and `derived_from` revision/hash.

`python -m ugas.cli asset verify-integrity <asset-id> --json` checks unique IDs and paths, hashes, ordering, derivation ancestry, current revision, approval binding and recomputed readiness.

Native BiRefNet is mask-producing; the original RGB remains the subject source when alpha is joined. Transparency QA records alpha-zero/opaque/partial, near-opaque foreground fraction, soft-edge fraction, geometry, halo and RGB MAE. Structural QA compares immutable R2/R4 with IoU >= 0.70, centroid drift <= 0.08 and bbox scale delta <= 0.15, rejecting same-path or pixel-identical non-noop edits.

Human review remains mandatory. Technical and structural gates do not approve art, and animation remains outside this increment.
