# game-context-resolver

## Description and trigger
Use at the start of an installation or asset task when engine context is unknown.

## When to use
Inspect files and identify engine, language, dimension hints, and confidence.

## When NOT to use
Do not infer a high-confidence engine from a single ambiguous folder name.

## Conceptual dependencies
Filesystem inspection and profile selection.

## Execution
Use known project markers, return detected files, and preserve unknown values when evidence is insufficient.

## Outputs
An inspectable context object consumed by installer and adapter skills.

## Limits and care
Detection is advisory; never mutate the consumer project during inspection.
