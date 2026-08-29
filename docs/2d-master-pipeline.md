# 2D master pipeline v0.4.1

The master specification separates machine composition constraints from generation language. `canvas_target`, occupancy, margins, pivot, QA thresholds and provenance remain in `master-asset-spec.json`; the compiled prompt is short visual language with full-body framing, neutral pose, readable anatomy, separated arms and a weapon beside—not crossing—the torso.

The two generation lanes are not interchangeable: Distilled uses 4 steps/guidance 1.0, while Base uses 50 steps/guidance 4.0. Compatibility is checked by family, variant, steps and guidance before `/prompt`.

Candidate hard gates run before ranking. A candidate is eligible only when its PNG, dimensions, content, uniqueness, clipping, occupancy, centering, file size and transparency requirements pass. Soft scoring runs only over eligible candidates. Two bounded corrective retry rounds are recorded; no least-bad candidate is promoted.

After selection, the required order is native BiRefNet, alpha statistics and checkerboard preview, a measurable reference edit, BiRefNet again, and structural QA. Structural QA records source/output SHA-256, silhouette IoU (minimum 0.70), centroid drift (maximum 0.08), bounding-box scale delta (maximum 0.15), and pixel-identity rejection. Any new edit invalidates prior transparency and approval.

Human review remains mandatory. `production_ready` is false until technical QA, transparency QA when required, same-revision visual approval and approval/output SHA equality all pass.
