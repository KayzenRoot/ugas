# game-asset-dependency-graph

## Description and trigger
Use when an asset relies on sources, variants, materials, animations, or packaging outputs.

## When to use
Record nodes and directed edges so changes can be traced.

## When NOT to use
Do not invent dependencies from filenames alone.

## Conceptual dependencies
Registry, manifests, provenance, and engine adapter.

## Execution
Validate stable IDs and reject cycles where the declared graph forbids them.

## Outputs
`asset-dependencies.json` and a reviewable dependency explanation.

## Limits and care
V0.2 models metadata only and does not rebuild downstream assets.
