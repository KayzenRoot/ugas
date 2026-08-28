# game-provenance-manager

## Description and trigger
Use for every bootstrap, generation request, output, import, or review transition.

## When to use
Append timestamped, actor, input, provider, and status events.

## When NOT to use
Do not log secrets, access tokens, or raw private prompts that the project policy excludes.

## Conceptual dependencies
Registry, manifests, provider router, and checkpoints.

## Execution
Append JSON Lines events without rewriting historical entries.

## Outputs
An auditable `provenance.jsonl` stream.

## Limits and care
Timestamps are evidence of recording, not proof that an external operation succeeded.
