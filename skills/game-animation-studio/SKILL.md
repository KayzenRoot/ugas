---
name: game-animation-studio
description: Defines 2D game animation clips timing loops pivots and state mapping for sprite assets. Use when a sprite set needs an explicit animation contract.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# game-animation-studio

## Description and trigger
Use for 2D animation clips and frame sequences.

## When to use
Define clip names, timing, loop policy, pivot, and state mapping.

## When NOT to use
Do not alter gameplay state machines as part of asset work.

## Conceptual dependencies
Sprite studio, profile, runtime validator, and engine adapter.

## Execution
Return a clip contract and timing checks.

## Outputs
Animation manifest and validation targets.

## Limits and care
Animation semantics remain owned by the consumer game.
