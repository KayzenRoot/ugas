---
name: game-asset-registry
description: Registers and reviews game asset identity status paths dimensions licensing and provenance as reusable metadata. Use when an asset enters or changes state in the project registry.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# game-asset-registry

## Description and trigger
Use when registering, finding, or reviewing a game asset.

## When to use
Keep identity, status, paths, dimensions, licensing, and provenance references in one source of truth.

## When NOT to use
Do not register an unvalidated output as production-ready.

## Conceptual dependencies
Asset manifest, provenance, license auditor, and dependency graph.

## Execution
Validate required fields, preserve stable IDs, and record state transitions.

## Outputs
Registry entries that support reuse and packaging.

## Limits and care
The registry is metadata; it does not copy or publish binary assets in V0.2.
