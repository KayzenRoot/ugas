---
name: provider-model-registry
description: Records provider model identifiers revisions licenses size classes and capability tags for game asset workflows. Use before selecting a model and never infer permission.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# provider-model-registry

## Description and trigger
Use when a provider needs a model reference for a workflow.

## When to use
Record model identifier, revision, license, size class, and capability tags.

## When NOT to use
Do not download or silently select a model outside the project policy.

## Conceptual dependencies
Provider manifest, license auditor, budget manager, and workflow registry.

## Execution
Use stable metadata and require human review for licensing or cost ambiguity.

## Outputs
Provider model metadata suitable for a generation request.

## Limits and care
V0.2 ships no model weights or large caches.
