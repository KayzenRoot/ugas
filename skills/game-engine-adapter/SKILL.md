---
name: game-engine-adapter
description: Translates neutral game asset contracts into engine-specific import guidance for Godot Unity Unreal or custom toolchains. Use after reliable context detection.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# game-engine-adapter

## Description and trigger
Use when translating an asset contract into engine-specific import guidance.

## When to use
Map neutral manifests to Godot, Unity, Unreal, or a declared custom toolchain.

## When NOT to use
Do not write engine code or mutate project settings without explicit scope.

## Conceptual dependencies
Context resolver, toolchain, manifests, and validators.

## Execution
Identify engine markers, preserve neutral source metadata, and list manual review points.

## Outputs
Engine adapter notes and import checklist.

## Limits and care
Unknown engines remain unknown; no unsafe assumptions.
