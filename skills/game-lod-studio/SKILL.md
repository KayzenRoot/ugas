# game-lod-studio

## Description and trigger
Use when a 3D asset needs distance-based representations.

## When to use
Define LOD count, screen thresholds, polygon targets, and material simplification.

## When NOT to use
Do not optimize before the source model and performance budget are known.

## Conceptual dependencies
3D model, material, budget manager, and runtime validator.

## Execution
Return a LOD contract tied to the profile budget.

## Outputs
LOD manifest candidate and checks.

## Limits and care
V0.2 does not generate or benchmark meshes.
