# game-runtime-validator

## Description and trigger
Use when checking that an asset package can be consumed by a game runtime.

## When to use
Verify engine import assumptions, paths, formats, and declared runtime budgets.

## When NOT to use
Do not claim in-game behavior from a static manifest alone.

## Conceptual dependencies
Engine adapter, toolchain, asset validator, and performance budget.

## Execution
Check available local evidence and report skipped runtime checks precisely.

## Outputs
Runtime readiness result with evidence and gaps.

## Limits and care
No game runtime is launched by the V0.2 bootstrap tests.
