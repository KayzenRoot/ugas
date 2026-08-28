# game-asset-orchestrator

## Description and trigger
Use whenever a request concerns game art, assets, visual references, or asset packaging.

## When to use
Classify the request, load project context, plan work, select subskills and a provider, then validate and record the result.

## When NOT to use
Do not route gameplay, backend, matchmaking, or unrelated engineering work into asset production.

## Conceptual dependencies
Context, profiles, Art DNA, registry, planner, provider router, and validators.

## Execution
Resolve intent before generation; reuse registry items before proposing new work; keep the server/game project authoritative.

## Outputs
An explainable asset plan, provider decision, validation result, and provenance event.

## Limits and care
V0.2 is orchestration infrastructure only; no mass generation or irreversible paid action.
