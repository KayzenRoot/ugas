# UGAS 2D master pipeline

## Contract

`schemas/master-asset-spec.json` turns a human request into a reproducible visual contract. It records profile, Art DNA, style, palette, outline, lighting, detail density, canvas, occupancy, margins, pivot, transparency requirement, positive/negative prompt material, references and deterministic seeds. `ugas generate master-sprite` persists the JSON spec and the compiled prompt instead of relying on hidden agent context.

## Candidate flow

1. Compile the prompt from profile + Art DNA + spec.
2. Generate 1-6 independent seeds, with a safe default of 4, beginning at a qualified 384x384 resolution.
3. Run PNG, dimensions, non-empty, clipping, occupancy, centering, duplicate/perceptual-hash and size checks for each candidate.
4. Create `candidates-contact-sheet.png` and `candidate-set.json`.
5. Select `best_technical_candidate` by deterministic objective metrics only. Visual assessment remains pending.

## Native transparency flow

`ugas background remove <asset-id>` uploads the current master, validates native BiRefNet nodes, submits the registered graph, saves the transparent PNG and a small mask copy, and records halo metrics. `TRANSPARENCY_VALID` requires real alpha values below 255 and a non-zero transparent fraction.

## Reference edit flow

`ugas refine master-sprite <asset-id> --instruction "..."` uploads the current revision, injects the image filename into the official FLUX.2 Klein image-edit graph, and creates a new revision. The old file remains immutable. Provenance includes `derived_from`, reference SHA-256, instruction, workflow/model IDs and output SHA-256.

## Quality states

```text
GENERATED
  -> TECHNICAL_VALID
  -> TRANSPARENCY_VALID (when required)
  -> VISUAL_REVIEW_REQUIRED
  -> VISUALLY_APPROVED (explicit `ugas visual approve`)
  -> PRODUCTION_READY
```

Approval records actor, timestamp, revision ID, output hash and note. Any new revision has pending approval; technical validity alone can never produce production readiness. A future visual evaluator may populate `machine_assessment`, but it is not a substitute for `human_approval`.
