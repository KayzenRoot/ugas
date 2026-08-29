---
name: game-rigging-studio
description: Defines 3D game skeleton deformation retargeting and export contracts for rigged models. Use when a model needs a reviewable rig brief without changing gameplay controllers.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# game-rigging-studio

## Description and trigger
Use when a 3D model needs a declared skeleton or deformation contract.

## When to use
Define bones, naming, retargeting assumptions, and export constraints.

## When NOT to use
Do not change gameplay animation state machines.

## Conceptual dependencies
3D model, animation-3d, profile, and engine adapter.

## Execution
Return a rig brief and a clear validation checklist.

## Outputs
Rig manifest candidate.

## Limits and care
V0.2 does not execute DCC software or retarget production rigs.
