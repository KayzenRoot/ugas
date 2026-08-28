# game-asset-reuse-engine

## Description and trigger
Use before proposing new asset generation.

## When to use
Search the registry and references for compatible existing assets.

## When NOT to use
Do not reuse an item with incompatible license, profile, dimensions, or validation state.

## Conceptual dependencies
Registry, Art DNA, dependency graph, and license auditor.

## Execution
Compare requested properties, return matches and reasons for rejection, then allow a new plan only if needed.

## Outputs
An explicit reuse decision.

## Limits and care
Similarity is not identity; human approval remains required for ambiguous matches.
