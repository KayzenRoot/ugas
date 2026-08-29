# 2D master pipeline v0.4.3

The production-shaped chain is `R1 RGB master -> R2 transparent source -> R3 selected reference edit RGB -> R4 transparent edited result`. Each revision owns an immutable output, metadata and checkerboard preview under its own ID directory. The v0.4.2 source chain is copied into a new v0.4.3 asset so its historical revisions are never mutated.

Reference edit is a separate capability. The contract permits only blue-steel armor to become deep cobalt/navy. It protects identity, face/skin/exposure, hair, proportions, pose, camera, silhouette, sword, black cloth and all non-target pixels. IoU and centroid are useful structural checks, but appearance QA additionally measures foreground luminance ratios/percentiles, head luminance/MAE, global change fraction, target hue movement and protected RGB MAE/change fraction.

The fresh pilot benchmarks official Base image-edit 20 steps/CFG 5/Euler against the legacy 50/4 configuration, with two unique seeds per configuration. It then runs four unique-seed generative candidates. Every job records client job ID, Comfy prompt ID, source/instruction/contract/workflow/model hashes, seed, timestamps, runtime, exact history key and returned output references. A pre-existing target or wrong history binding is invalid evidence.

If a high-confidence HSV target mask exists, the deterministic route changes hue near 220 degrees while preserving luminance, texture and alpha; the documented sword-like connected component is excluded. Outside-target pixels remain bit-for-bit unchanged before BiRefNet. Deterministic output still receives native BiRefNet comparison and human review. If the mask is uncertain, the route is recorded as `TARGET_MASK_UNCERTAIN` and generative candidates remain the only route.

Temporary candidates stay in unique job folders and never enter the revision list. Zero eligible generative/deterministic candidates yields `NO_ACCEPTABLE_REFERENCE_EDIT`; a local quality failure is not hidden by selecting a structurally similar image. R4 is never considered production-ready without explicit human visual approval bound to the exact revision/hash.
