---
name: game-generation-provider-router
description: Selects a capable and evidenced game asset provider using policy availability capability cost class and 2D or 3D requirements. Use before any provider request or fallback decision.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# game-generation-provider-router

## Description and trigger
Use when an asset plan needs a generation provider.

## When to use
Resolve `free-first`, `local-first`, `remote-first`, or `paid-disabled` against capability and availability.

## When NOT to use
Do not submit a job when capability, consent, budget, or provider availability is unknown.

## Conceptual dependencies
Provider manifests, policy, capability probes, and generation request schema.

## Execution
Order ComfyUI, Render Node, and Hugging Face according to policy; return the selected provider and fallbacks.

## Outputs
An auditable routing decision, including unavailable-provider reasons.

## Limits and care
Routing never stores secrets and never implies a job was generated.
