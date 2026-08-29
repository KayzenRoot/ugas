---
name: game-material-studio
description: Plans 3D game materials and texture sets with channels resolution color space shader assumptions and compression. Use for material manifests tied to a profile.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# game-material-studio

## Description and trigger
Use for 3D material and texture set planning.

## When to use
Define channels, resolution, color space, shader assumptions, and compression.

## When NOT to use
Do not modify engine shaders or claim a material is compatible without an adapter check.

## Conceptual dependencies
3D model, Art DNA, budget manager, and engine adapter.

## Execution
Return a material manifest and validation targets.

## Outputs
Material plan with provenance and license requirements.

## Limits and care
No model downloads or large texture generation in V0.2.
