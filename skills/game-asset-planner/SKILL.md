---
name: game-asset-planner
description: Turns a classified game asset request into an ordered plan with asset types dependencies acceptance checks and profile budgets. Use after context resolution and before provider selection.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# game-asset-planner

## Description and trigger
Use after an asset request has been classified and before provider selection.

## When to use
Break a request into asset types, dependencies, acceptance checks, and budgets.

## When NOT to use
Do not create a production pipeline or commit to a paid job from a plan.

## Conceptual dependencies
Profile, Art DNA, registry, dependency graph, and budget manager.

## Execution
Produce a small ordered plan with reuse checks, technical targets, and validation gates.

## Outputs
A human-readable plan and machine-readable generation request candidate.

## Limits and care
Plans must call out assumptions and unknowns instead of inventing project facts.
