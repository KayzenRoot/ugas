# game-asset-budget-manager

## Description and trigger
Use when an asset request needs technical, performance, or provider budget checks.

## When to use
Apply profile budgets for texture size, atlas area, polygon count, draw calls, and job cost policy.

## When NOT to use
Do not silently increase limits to make an output pass.

## Conceptual dependencies
Profile, performance budget, provider policy, and validator.

## Execution
Compare requested targets with limits and report the first violated constraint.

## Outputs
A pass/fail budget report and any required review decision.

## Limits and care
V0.2 does not charge providers or enforce billing.
