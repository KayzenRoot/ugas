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
