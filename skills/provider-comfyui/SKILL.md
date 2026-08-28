# provider-comfyui

## Description and trigger
Use when ComfyUI is the selected or evaluated visual-generation provider.

## When to use
Use the health, capability, workflow, job, polling, and output contracts.

## When NOT to use
Do not submit jobs without explicit policy approval, endpoint reachability, or a declared workflow.

## Conceptual dependencies
Provider manifest, workflow registry, generation schemas, and provenance.

## Execution
Probe `/system_stats`, resolve a versioned workflow, and record job state transitions.

## Outputs
Dry-run readiness or an evidence-backed provider response.

## Limits and care
No credentials, model downloads, or real asset generation are required in V0.2.
