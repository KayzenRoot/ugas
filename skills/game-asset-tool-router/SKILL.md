# game-asset-tool-router

## Description and trigger
Use when selecting a tool or subskill for a requested asset type.

## When to use
Map sprites, tilesets, animation, UI, VFX, models, materials, rigging, and LOD work to the smallest relevant skill set.

## When NOT to use
Do not select tools for non-asset requests or tools that are not declared in the project toolchain.

## Conceptual dependencies
Request classification, engine adapter, profile, and toolchain.

## Execution
Return an ordered tool plan with inputs, outputs, and validation requirements.

## Outputs
Deterministic subskill routing with no hidden side effects.

## Limits and care
Tool routing is advisory in V0.2 and does not execute external applications.
