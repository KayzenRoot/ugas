---
name: provider-workflow-registry
description: Registers versioned provider workflows with inputs outputs model requirements and safety constraints for reproducible game asset jobs. Use before resolving a workflow.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# provider-workflow-registry

## Description and trigger
Use when a provider request needs a named, versioned workflow.

## When to use
Register inputs, outputs, model requirements, and safety constraints for workflows.

## When NOT to use
Do not execute an opaque or unversioned workflow.

## Conceptual dependencies
ComfyUI provider, model registry, and generation schemas.

## Execution
Resolve a workflow manifest and record its version in provenance.

## Outputs
Reproducible workflow selection metadata.

## Limits and care
Only a bootstrap workflow contract is included; no heavy production graph is bundled.
