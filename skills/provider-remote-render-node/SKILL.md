# provider-remote-render-node

## Description and trigger
Use when a separate PC, including an RTX 5050 node, hosts ComfyUI.

## When to use
Route over a private network with health checks and a fallback provider.

## When NOT to use
Do not expose ComfyUI directly to the public internet or embed credentials.

## Conceptual dependencies
ComfyUI provider, router, capability probe, and provenance.

## Execution
Require a private endpoint, verify availability, and fall back deterministically when unavailable.

## Outputs
Remote-node readiness or fallback evidence.

## Limits and care
The RTX 5050 is a documented target, not a claimed local GPU in this repository.
