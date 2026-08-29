---
name: game-visual-regression
description: Defines evidence for comparing game asset renders against approved visual references including capture conditions and review thresholds. Use when images are actually available.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# game-visual-regression

## Description and trigger
Use when comparing an asset render to an approved reference.

## When to use
Define reference identity, capture conditions, and review thresholds.

## When NOT to use
Do not fabricate screenshots or assert a pass without comparable images.

## Conceptual dependencies
Art DNA, provenance, registry, and validator.

## Execution
Record reference and comparison evidence; separate automated and human review.

## Outputs
A visual regression record or an explicit not-run status.

## Limits and care
The bootstrap establishes the contract but does not bundle a CV renderer.
